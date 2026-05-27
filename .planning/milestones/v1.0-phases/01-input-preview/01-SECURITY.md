---
phase: 01
slug: input-preview
status: verified
threats_open: 0
threats_total: 17
threats_closed: 17
asvs_level: 1
created: 2026-05-22
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (two `<threat_model>` blocks: 01-01-PLAN.md backend
> T-01-01..T-01-10, 01-02-PLAN.md frontend T-01-11..T-01-17). This audit VERIFIES each
> declared mitigation exists in the implemented code — it does not scan for new threats.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser/LAN client → POST /sessions | Untrusted file bytes + client filename cross here; no auth (internal LAN) — every caller untrusted. | Multipart file bytes, client-supplied filename |
| Uploaded bytes → PyMuPDF (MuPDF C parser) | Untrusted binary parsed by a C-backed library; known crash/attack surface. | Raw PDF bytes |
| Client filename / `session_id` → filesystem path | Client-controlled strings must never become an unvalidated path component. | filename string, URL path `session_id` |
| work/ editing copy ↔ originals/ immutable source | Internal boundary; the original must remain byte-for-byte intact. | PDF bytes on disk |
| Browser DOM → server API (via web/api.js) | The only client→server crossing; image URLs are GETs, upload is multipart POST. | session_id, page index, dpi |
| Server-rendered PNG → browser display | Browser renders a server image, never parses the PDF (no client PDF parser). | PNG image bytes + X- metadata headers |
| User jump-to-page value → render request | Client page index must be bounded before requesting an image. | integer page index |
| localStorage theme value → document root attribute | Persisted theme string read back and applied as `data-theme`; must be enum-constrained, never reflected as HTML. | "light" / "dark" string |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-01 | Denial of Service | POST /sessions upload size | mitigate | Early streaming size guard in route (`app/api/sessions.py:50-64`: rejects as soon as `len(buf)+len(chunk) > MAX_UPLOAD_BYTES`, 413 `file_too_large`, message carries the MB limit) + re-check in `app/services/ingest.py:67-71`. `MAX_UPLOAD_BYTES=50*1024*1024` (`app/config.py:39`). | closed |
| T-01-02 | Denial of Service | Page count / pixel budget | mitigate | Page-count cap `app/services/ingest.py:95-99` (>`MAX_PAGES` → 413 `too_many_pages`, message carries "30"); `MAX_PAGES=30` (`app/config.py:40`). DPI clamp `app/services/render.py:48-52` to `[72,300]`; additional `MAX_RENDER_PIXELS=40MP` ceiling `app/services/render.py:55-71` scales DPI down for oversized MediaBox (WR-06 fix). | closed |
| T-01-03 | Tampering | PyMuPDF parsing malformed/malicious PDF | mitigate | `fitz.open` wrapped in try/except → typed `PdfEngineError` (`app/services/pdf_engine.py:37-42`); mapped to 422 `corrupt_pdf` in ingest (`app/services/ingest.py:82-86`) and via global handler (`app/main.py:76-83`). Never a bare 500. PyMuPDF pinned 1.27.x (`requirements.txt`). | closed |
| T-01-04 | Tampering / Elevation | Client filename / `session_id` → path traversal | mitigate | **CR-01 fix verified:** `session_id` (the real path-builder) is allowlisted `^[A-Za-z0-9_-]{16,64}$` via `validate_session_id` (`app/storage.py:48-56`) called inside `subdir()` (`app/storage.py:73-89`) BEFORE the path is built, plus `is_relative_to(DATA_DIR)` containment. `InvalidSessionId` → 404 (`app/main.py:64-73`); `session_exists` swallows it → 404 (`app/storage.py:200-211`). `sanitize_filename` (`app/storage.py:104-119`) keeps the client filename display-only; on-disk names are fixed (`source.pdf`/`doc.pdf`). | closed |
| T-01-05 | Tampering | In-place mutation of the original (UPLOAD-04) | mitigate | Original written write-once + `os.chmod(... 0o444)` (`app/storage.py:184-187`); separate work copy written (`app/storage.py:191-197`); render opens the work path only (`app/api/pages.py:44`, `app/services/render.py:94`). Hash-unchanged test asserted (per 01-01-SUMMARY). | closed |
| T-01-06 | Spoofing (type confusion) | Extension-trusted upload | mitigate | Content-sniff PDF header at a small leading offset, not the extension (`app/services/ingest.py:44-53`, offset ≤ 8 per WR-05 fix); authoritative parse backstop via `open_pdf`; non-PDF → 415 `unsupported_type`. | closed |
| T-01-07 | Information Disclosure | Guessable session id/path | mitigate | `session_id = secrets.token_urlsafe(16)` (128-bit, `app/storage.py:98`), not sequential; per-session dirs. Full auth deferred (internal LAN — see Accepted Risks via T-01-09). | closed |
| T-01-08 | Information Disclosure | Stack traces leaking internals | mitigate | Global exception handlers return only `{code, message}` (`app/main.py:46-83`); `get_session` re-parse failure surfaces a generic `session_unreadable` 500, not internal text (`app/api/sessions.py:101-114`, WR-03 fix). | closed |
| T-01-09 | Repudiation | No audit log | accept | Internal single-purpose LAN tool, no auth, no v1 compliance requirement. See Accepted Risks Log (R-01). Revisit at website-embedding milestone. | closed |
| T-01-10 | Denial of Service | Stale temp/session files filling disk | accept | Retention janitor is explicitly Phase 5; per-session dirs make cleanup trivial. See Accepted Risks Log (R-02). | closed |
| T-01-11 | Tampering | Out-of-range jump-to-page index | mitigate | Client clamp `Math.min(Math.max(n,1), pageCount)` (`web/js/viewer.js:189-194`); backend also 404s out-of-range pages (`app/services/render.py:74-80` → `app/api/pages.py:50-54`) — defense in depth. | closed |
| T-01-12 | Information Disclosure | Hardcoded server origin leaking across modules | mitigate | All server contact funneled through `web/js/api.js` via `window.PDFTOOL_API_BASE` (`web/js/api.js:21-22`); grep confirms `PDFTOOL_API_BASE`/`fetch(`/`"/sessions"` appear ONLY in api.js; `theme.js` makes no network calls (no fetch/api import — `web/js/theme.js`). | closed |
| T-01-13 | Tampering | Client-side PDF parser (PDF.js) on untrusted bytes | mitigate | Server-authoritative render enforced; recursive grep for `pdfjs`/`pdf.js`/`PDFJS`/`pdf.worker` under `web/` returns nothing. Browser only loads server-rendered PNGs via `<img>` (`web/js/viewer.js:167`). | closed |
| T-01-14 | Information Disclosure | Reflecting raw server error text into the DOM | mitigate | `app.js` maps `detail.code` to fixed Chinese copy (`web/js/app.js:85-102`); `extractLimit` returns only a parsed numeric token, falling back to `""` (never the raw message) per WR-02 fix (`web/js/app.js:79-83`); written via `textContent` (`web/js/app.js:106`). | closed |
| T-01-15 | Elevation (XSS) | Unescaped dynamic HTML (filename / page numbers) | mitigate | All dynamic text via `textContent` / `createElement` / `createTextNode` / `replaceChildren` (`web/js/viewer.js:105-117`, `web/js/app.js:106`); no `innerHTML`/`outerHTML`/`document.write`/`insertAdjacentHTML` anywhere in `web/` (grep: only mentioned in security comments). | closed |
| T-01-16 | Tampering / Elevation (XSS) | Untrusted value in persisted theme key | mitigate | `theme.js` enum-guards the stored value to `light`/`dark` (`web/js/theme.js:18-27`); invalid → null → falls back to prefers-color-scheme; applied via `setAttribute('data-theme', ...)`/`removeAttribute` (`web/js/theme.js:47-55`), never `innerHTML`. | closed |
| T-01-17 | Repudiation | No client-side audit trail | accept | Internal LAN tool, no auth/compliance in v1 (consistent with T-01-09). See Accepted Risks Log (R-03). | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-01 | T-01-09 | No server-side audit log. Internal single-purpose LAN tool, no auth and no compliance requirement in v1. Per-request logging/audit deferred to the website-embedding milestone. | Plan author (01-01-PLAN.md `<threat_model>`) | 2026-05-22 |
| R-02 | T-01-10 | No retention janitor for stale temp/session files. Disk-fill cleanup is explicitly scoped to Phase 5; the per-session directory layout (originals/work/outputs/{sid}) makes later bulk cleanup trivial. Accepted for Phase 1, flagged for Phase 5. | Plan author (01-01-PLAN.md `<threat_model>`) | 2026-05-22 |
| R-03 | T-01-17 | No client-side audit trail. Internal LAN tool, no auth/compliance need in v1 (consistent with R-01 / T-01-09). | Plan author (01-02-PLAN.md `<threat_model>`) | 2026-05-22 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Flags

None. Both implementation summaries (`01-01-SUMMARY.md` "## Threat surface scan", `01-02-SUMMARY.md` "## Threat surface scan") explicitly report no new security surface beyond the plan-authored threat model: the backend introduced no surface beyond T-01-01..T-01-10 and the frontend "introduces no network endpoint, auth path, file-access pattern, or schema beyond what the threat model already covers (it only consumes the existing backend endpoints)." No `threat_flag` requiring a new threat mapping.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-22 | 17 | 17 | 0 | gsd-security-auditor (Claude) |

Notes: Verified the CR-01 path-traversal fix (commit `5890a31` per 01-REVIEW.md) — the `session_id` allowlist + DATA_DIR containment in `app/storage.py` `subdir()` is the chokepoint for every path-building helper (`original_path`/`work_path`/`outputs_dir`/`meta_path`), so the guard covers all entry points (POST /sessions, GET /sessions/{id}, GET .../pages/{n}/image, .../meta). AGPL isolation confirmed: `import fitz` in exactly one file (`app/services/pdf_engine.py`).

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (R-01, R-02, R-03)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-22
