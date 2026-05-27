---
phase: 03-logo-placement
audited: 2026-05-22
asvs_level: 1
block_on: high
threats_total: 5
threats_closed: 5
threats_open: 0
status: secured
---

# Phase 3: Security Audit Report

**Audited:** 2026-05-22
**ASVS Level:** 1
**Disposition source:** PLAN.md `<threat_model>` blocks (03-01, 03-02) — register authored at plan time.
**Method:** Each declared mitigation verified against implemented code (grep + read). Documentation/intent NOT accepted as evidence. Implementation files read-only.

## Threat Register

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-03-01 | Tampering / Info Disclosure | mitigate | CLOSED | `app/services/logo.py`: `resolve()` (L154-172) and `_load_manifest()` (L49-72) treat `logo_id` ONLY as a manifest dict key (`_load_manifest().get(logo_id)`, L162) — never joined to a path. `_resolve_path()` (L75-86) joins the admin `entry["file"]` and asserts `path.is_relative_to(logos_dir.resolve())` (L84), else `LogoError("logo_not_found")` (no oracle). No `LOGOS_DIR / logo_id` construction anywhere. Endpoint `app/api/logos.py` `get_logo_image` (L40-54) maps `logo_not_found`→404. /process path: `app/services/pipeline.py` resolves via `logo.resolve(job_spec.logo_id)` (L159), same allowlist. Test `tests/test_logo.py::test_logo_id_path_traversal_rejected` passes. |
| T-03-02 | Denial of Service | mitigate | CLOSED | `app/config.py`: `MAX_LOGO_BYTES` (L39, 10 MB). `app/services/logo.py` `_validate_png()` checks `path.stat().st_size > config.MAX_LOGO_BYTES` BEFORE decode (L104-108) and Pillow `verify()` catches `Image.DecompressionBombError` (L117). `list_logos()` (L134-151) skips a bad asset via per-entry try/except (L143-149) — never crashes `GET /logos`. Test `test_list_logos_skips_bad_asset` / bad-asset-skip passes. |
| T-03-03 | Denial of Service | mitigate | CLOSED | `app/services/logo.py` `_validate_png()` wraps decode in try/except → typed `LogoError("logo_unreadable")` (L117-118). `app/main.py` `@app.exception_handler(LogoError)` (L122-128) + `_LOGO_STATUS` table (L115-119) map to structured 4xx; never a bare 500. Handler also covers `LogoError` raised inside `/process`. `app/api/logos.py` likewise wraps `resolve` (L47-53). |
| T-03-04 | Tampering (stored XSS) | mitigate | CLOSED | `web/js/logos.js`: all logo/manifest text written via `textContent` (L60,65,66,71,107,117) and DOM built via `createElement` (L96,105,111,115). Manifest `name` reflected via `caption.textContent = name` (L117). No `innerHTML` token in source; no direct `fetch(`. Grep confirms zero matches for both. |
| T-03-05 | Denial of Service (mild) | mitigate | CLOSED | `app/services/pipeline.py`: logo resolved ONCE outside the loop (L155-162); first region embeds (`stream=logo_bytes if logo_xref == 0 else None`), 2nd+ reuse the returned `xref` (L203-209). `app/services/pdf_engine.py` `place_logo()` (L233-258) returns the embedded xref; `save_doc()` (L376-390) compacts with `garbage=4, deflate=True, clean=True`. Test `test_global_logo_single_xref` passes. |

## Carried Threats (informational — verified still intact)

| Threat ID | Disposition | Status | Evidence |
|-----------|-------------|--------|----------|
| T-02-12 (api.js sole seam) | mitigate | CLOSED | `web/js/logos.js` calls only `api.listLogos()` (L140) / `api.logoImageURL()` (L113); no direct `fetch(`. |
| T-02-03 (AGPL fitz seam) | mitigate | CLOSED | `logo.py` imports only `json`/`pathlib`/`PIL`/`config`; `pipeline.py` fitz-free; `place_logo`/`get_image_rects` are the only new fitz calls, confined to `pdf_engine.py`. `test_fitz_import_confined_to_engine_seam` passes. |
| Pitfall 1 (insert after redaction) | mitigate | CLOSED | `pipeline.py` places logo STRICTLY after `redact.remove_region` (L196 then L203-209). `test_logo_survives_redaction` passes. |
| T-02-05 / D-05 (original immutable) | mitigate | CLOSED | Original SHA-256 asserted unchanged across remove+insert run (`tests/test_process_api.py`). |

## Accepted Risks

None declared for this phase. WR-04 (non-PNG asset served as image/png) was a code-review robustness finding; it has been HARDENED in `_validate_png` (L112-113 rejects `img.format != "PNG"` → `logo_invalid`), so it is no longer a residual risk.

## Unregistered Flags

None. Neither `03-01-SUMMARY.md` nor `03-02-SUMMARY.md` contains a `## Threat Flags` section. All new attack surface introduced this phase (the `logo_id` path param, the `logos/` library decode boundary, and manifest text reflected into the picker) is covered by registered threats T-03-01..05. The code-review warnings (WR-01..04, IN-01..04 in 03-REVIEW.md) are robustness/quality findings, not new unmapped attack surface; the security-relevant ones (WR-02 graceful degradation, WR-04 PNG enforcement) are already implemented.

## Audit Trail

- Verification method per disposition: all 5 threats are `mitigate` → grepped for the declared mitigation pattern in cited files and confirmed it applies at every entry point (the standalone `GET /logos/{id}/image` endpoint AND the `/process` pipeline path for T-03-01).
- Mitigation-asserting tests executed via project venv: `tests/test_logo.py`, `tests/test_process_api.py`, `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` — 31 passed.
- Implementation files were NOT modified (read-only audit).
