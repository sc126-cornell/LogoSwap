---
phase: 02-region-removal
slug: region-removal
status: verified
threats_open: 0
threats_total: 14
threats_closed: 14
asvs_level: 1
created: 2026-05-22
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (three PLAN `<threat_model>` blocks, T-02-01..T-02-14).
> This audit VERIFIES each declared mitigation is present in the implemented code — it does
> not scan for new threats. Adversarial (FORCE) stance: every mitigation assumed absent until
> a grep match / test proved it present at the right location.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| caller → `coords` | A pixel rect + dpi + page object enter the pure mapper (eventually from untrusted client input). | image-pixel rect, dpi, page handle |
| browser → `POST /sessions/{id}/process` | Untrusted JSON (page indices, pixel rects, dpi, region count) crosses into the redaction pipeline — the primary new attack surface of Phase 2. | JobSpec JSON (low-trust) |
| pipeline → work copy / original | The pipeline must mutate ONLY the `work/` copy; the original (chmod 0o444) is the integrity boundary that must never be crossed. | PDF bytes (work) vs immutable source |
| outputs file → `GET /sessions/{id}/result` | A generated PDF is streamed back; the served path must be confined to the session's outputs dir. | exported PDF, CJK display name (header only) |
| browser overlay → `api.js` → server | Drawn rectangles assembled client-side and POSTed via the single `api.js` seam; client untrusted, server re-validates and clamps. | region payload, result-image / download URLs |
| server messages → DOM | Server `detail.message`, filenames, region labels must render without becoming an XSS/HTML-injection vector. | error code/message, filenames |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-01 | Tampering / DoS | `coords` + JobSpec validation + pipeline clamp | mitigate | `coords.clamp_px_rect` (NaN-safe, normalize, boundary flag) `coords.py:84-125`; Pydantic finite + len-4 `models.py:63-74`; pipeline clamps before map `pipeline.py:171-173`; zero-area skipped `redact.py:91-93` | closed |
| T-02-02 | Information disclosure | wrong-mapping silently redacts wrong region (correctness-as-security) | mitigate | Round-trip + visual-overlap gate at 0/90/180/270 + offset MediaBox (`tests/test_coords.py`, ~0.00004px); CR-01 fix re-derives EFFECTIVE per-page DPI `pipeline.py:137,158-174` so reduced-DPI pages still redact the framed area | closed |
| T-02-03 | EoP / supply-chain | `fitz` (AGPL, C parser) reached outside the seam | mitigate | `grep -rl "import fitz" app/` returns ONLY `app/services/pdf_engine.py`; coords/redact/pipeline import no fitz; matrix multiply + redaction confined to seam; AST purity test `tests/test_coords.py:271-285` | closed |
| T-02-04 | DoS | huge `regions` list / absurd `dpi` | mitigate | `config.MAX_REGIONS=200` `config.py:52`; `dpi` bounded `[MIN_DPI,MAX_DPI]` `models.py:86`; region cap validator `models.py:89-96`; redaction in `run_in_threadpool` `process.py:61`; test `test_process_too_many_regions_is_4xx` | closed |
| T-02-05 | Tampering (integrity) | pipeline mutating the immutable original (D-05) | mitigate | Pipeline opens `work_path` only + asserts path != `original_path` `pipeline.py:109-113`; original chmod 0o444 `storage.py:187`; WR-01 work-copy reset from pristine original each run `pipeline.py:115-128`; SHA-256 before/after test + idempotent-reapply test | closed |
| T-02-06 | Info disclosure / path traversal | `session_id` / filename used to read outside session outputs dir | mitigate | `validate_session_id` allowlist `storage.py:48-89` (crafted id → 404, no oracle); download serves FIXED `outputs_dir(id)` name, CJK name only in RFC-5987 `filename*=` `process.py:122-123`; crafted-id 404 test | closed |
| T-02-07 | Information disclosure | "covers but does not remove" — supplier text/vector still extractable | mitigate | Mandatory post-redaction emptiness assertion over UNPADDED rect `redact.py:132-138`; `apply_redactions` always called; CR-02 vector semantics use `get_drawings_fully_inside` (covered survivor only) `pdf_engine.py:310-335`; `PDF_REDACT_TEXT_NONE` forbidden (engine refuses `pdf_engine.py:226-229`, grep-absent from redact.py) | closed |
| T-02-08 | DoS / availability | malformed PDF / redaction edge case → unhandled 500 | mitigate | `RedactError`/`PipelineError`/`PdfEngineError`/`RequestValidationError` all mapped to structured `{detail:{code,message}}` 4xx `main.py:84-135` (residual/page-range→422); never a bare 500; 3 malformed-body / page-range tests assert `!= 500` | closed |
| T-02-11 | Info disclosure / Tampering (XSS) | server `detail.message`, filenames, region labels into DOM | mitigate | All dynamic text via `textContent`/`createElement` (regions.js, app.js, viewer.js); errors mapped to FIXED 繁中 copy by `detail.code` `regions.js:545-557`; raw server message never injected; grep: `innerHTML` only in "never innerHTML" comments | closed |
| T-02-12 | Tampering / SSRF-shape | a web module hardcoding a server URL bypassing the embedding seam | mitigate | Only `web/js/api.js` references `API_BASE`/`fetch`; regions.js builds result/download URLs only via `api.resultImageURL`/`api.resultDownloadURL` and swaps images via viewer helpers (which themselves call api.js URL builders); grep: regions.js has no `fetch`/`API_BASE` | closed |
| T-02-13 | Tampering / DoS | client sending huge region list / out-of-bounds rects | mitigate | Client caps drawing (`DRAG_THRESHOLD`, clamp `regions.js:385-388`) but AUTHORITATIVE guard is server-side (T-02-04 `MAX_REGIONS` + T-02-01 `clamp_px_rect`); UI surfaces server `clamped` flag, never assumes applied without per-region result `regions.js:582-591` | closed |
| T-02-14 | Spoofing / confused-deputy | result image / download fetched for wrong session | mitigate | `sessionId` set only from viewer state established at upload (server-issued token); all result URLs built from it via api.js `regions.js:535,612`; no cross-session id constructible from the UI | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

> Note on register IDs: T-02-01..T-02-03 are declared in 02-01-PLAN; T-02-01 (re-stated at the
> HTTP boundary), T-02-04..T-02-08 in 02-02-PLAN; T-02-11..T-02-14 in 02-03-PLAN. T-02-09/T-02-10
> are not present in any plan `<threat_model>` (the register skips to the frontend block at -11);
> this is a plan-time numbering gap, not a missing implementation — there is no declared
> mitigation to verify for those IDs. All 12 declared threats are CLOSED.

---

## Unregistered Flags

None. All three SUMMARY `## Threat surface scan` sections explicitly state "No new security
surface beyond the plan's `<threat_model>`" (02-01-SUMMARY:152-154, 02-02-SUMMARY:212-220,
02-03-SUMMARY:206-212). No new attack surface appeared during implementation that lacks a
threat mapping.

---

## Code-Review Cross-Check (security-relevant resolutions)

The 02-REVIEW found two BLOCKER-class defects that both touch declared threats; both were fixed
AND covered by a regression test (verified present and passing in this audit):

| Review finding | Threat touched | Fix verified at | Regression test |
|----------------|----------------|-----------------|-----------------|
| CR-01 client/server DPI disagreement → wrong area redacted | T-02-02 (correctness-as-security) | `pipeline.py:137,158-174` (re-derives effective per-page DPI) | large-MediaBox mapping test |
| CR-02 residual assertion fails legitimate crossing-line removal | T-02-07 (true removal) | `redact.py:132-138` + `pdf_engine.get_drawings_fully_inside` | `test_remove_region_boundary_crossing_line_survives_job_succeeds` |
| WR-01 work copy not reset between runs (stale redaction) | T-02-05 (deferred-mutation integrity) | `pipeline.py:115-128` (`shutil.copyfile` original→work each run) | `test_process_job_reapply_is_idempotent_from_pristine_original` |
| WR-05 unbounded CJK stem into Content-Disposition | T-02-06 (header safety) | `pipeline.py:49-72` (`MAX_STEM_LEN=128`, strips `Cc` control chars) | exercised via download tests |
| WR-06 spurious clamp flag on reversed-but-in-bounds drag | T-02-01 (boundary feedback accuracy) | `coords.py:115-124` (compares NORMALIZED input vs clamped) | `test_clamp_px_rect_clamps_and_flags` |

Verification gates re-run during this audit:
- `pytest tests/test_redact.py tests/test_process_api.py tests/test_coords.py -q` → **54 passed**.
- `grep "import fitz" app/` → only `app/services/pdf_engine.py`.
- `grep "PDF_REDACT_TEXT_NONE" app/services/redact.py` → no matches.
- `grep "innerHTML" web/js/` → only "never innerHTML" comments.
- `grep "API_BASE|fetch(" web/js/regions.js` → no matches.
- `grep "pdfjs|pdf.js|getDocument|pdf.worker" web/` → no files (no client-side PDF parser).

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|

No accepted risks. (Phase-2 scope: `images=PDF_REDACT_IMAGE_NONE` — raster/image-type pages are
intentionally NOT redacted in Phase 2; this is a documented Phase-4 deferral surfaced to the user
via the "沒有可移除的內容 / 圖片型" notice, not an accepted security risk for the vector/text
removal this phase ships.)

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-22 | 12 (T-02-01..-08, -11..-14) | 12 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (all `mitigate`)
- [x] Each declared mitigation verified present in code (file:line evidence above)
- [x] Threat flags from all three SUMMARYs incorporated (no unregistered surface)
- [x] Accepted risks documented in Accepted Risks Log (none)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-22
