---
phase: 03-logo-placement
plan: 02
subsystem: logo-placement (insert-after-redaction)
tags: [LOGO-02, place_logo, keep_proportion, single-xref, D-01, D-06, fitz-seam]
requires:
  - "03-01: logo.resolve(logo_id)->bytes (manifest allowlist), logos.getSelectedLogoId(), LogoError->4xx handler, regions.notifyJobInputChanged stale hook"
  - "Phase 2 spine: pipeline.process_job per-region loop, redact.remove_region (apply_redactions), coords.pixels_to_pdf_rect, pdf_engine fitz seam, /result render of work copy, regions.js action/before-after machine"
provides:
  - "pdf_engine.place_logo(page, rect, *, stream, xref) -> int (the only new fitz call) + get_image_rects(page, xref) verification wrapper"
  - "JobSpec.logo_id optional global field (D-01) — the /process contract for a placed logo"
  - "pipeline places one global logo after remove_region on the same pdf_rect, dedup via reused xref"
  - "regions.js sends logo_id on /process + conditional 移除+置入結果 after-label (D-06)"
affects:
  - app/services/pdf_engine.py
  - app/models.py
  - app/services/pipeline.py
  - app/api/process.py
  - web/js/regions.js
  - tests/test_logo.py
  - tests/test_process_api.py
tech-stack:
  added: []
  patterns:
    - "place_logo wraps insert_image(keep_proportion=True, overlay=True) — contain+center default (LOGO-02), inserted AFTER apply_redactions (Pitfall 1)"
    - "resolve the one global logo ONCE outside the loop; embed on first region (stream=bytes), reuse returned xref (stream=None) on the rest — single-xref dedup (D-01/Pitfall 4)"
    - "place regardless of remove_region's `removed` flag (A1 — the user framed the rect as a replacement target)"
    - "conditional after-label set via textContent in JS (refreshResultLabel), never hardcoded in HTML"
key-files:
  created:
    - .planning/phases/03-logo-placement/03-02-SUMMARY.md
  modified:
    - app/services/pdf_engine.py
    - app/models.py
    - app/services/pipeline.py
    - app/api/process.py
    - web/js/regions.js
    - tests/test_logo.py
    - tests/test_process_api.py
decisions:
  - "[03-02] place_logo is the ONLY new fitz call (in pdf_engine.py); pipeline.py stays fitz-free — AGPL seam intact, enforced by the existing AST grep test"
  - "[03-02] keep_proportion=True + overlay=True passed explicitly for clarity; keep_proportion=False is absent (the stretch anti-pattern, LOGO-02)"
  - "[03-02] logo placed AFTER remove_region (which runs apply_redactions internally) so it survives; placed REGARDLESS of the removed flag (A1)"
  - "[03-02] one global logo dedups to a single xref across N regions/pages (reuse the returned xref); no logo_id = pure Phase-2 removal; original SHA-256 unchanged (D-05)"
  - "[03-02] D-06 result-with-logo needs ZERO new rendering — /result renders the work copy which now contains the logo; only the after-label text changes conditionally"
metrics:
  duration: ~15 min
  completed: 2026-05-22
---

# Phase 3 Plan 02: Logo Placement (insert-after-redaction) Summary

Completes the LOGO-02 vertical slice: a selected global logo is placed (centered, aspect-preserved via `keep_proportion=True`) into every framed region on the SAME `pdf_rect` the removal used, inserted strictly AFTER `redact.remove_region` so it survives while the supplier text/vector stay truly removed; one global logo reuses a single embedded `xref` across all regions; no `logo_id` is pure Phase-2 removal; the original is byte-for-byte unchanged (D-05); and the before/after "after" segment conditionally reads 移除+置入結果 with the work-copy render already containing the logo (D-06, zero new rendering).

## What Was Built

**Task 1 — backend (TDD, RED→GREEN):**
- `pdf_engine.place_logo(page, rect, *, stream, xref) -> int` — the SOLE new fitz call, a thin wrapper over `page.insert_image(rect, stream=, xref=, keep_proportion=True, overlay=True)`; returns the embedded image xref. Plus `get_image_rects(page, xref) -> list` (mirrors `get_text_words_in_rect`) so the LOGO-02 test asserts the placed bbox without importing fitz.
- `JobSpec.logo_id: str | None = Field(default=None, max_length=128, ...)` — the optional global-logo contract (D-01); `max_length` is cheap defense-in-depth (V5), no charset validator needed (resolution is a manifest-dict lookup, T-03-01). Docstring updated; `process.py` `process_session` docstring notes the field (handler unchanged — it passes the whole `JobSpec` through).
- `pipeline.process_job`: added `logo` to the imports line (stays fitz-free); resolves `logo_bytes = logo.resolve(job_spec.logo_id) if job_spec.logo_id else None` and `logo_xref = 0` ONCE above the loop; inside the loop, AFTER `remove_region`, places the logo on the same `pdf_rect` regardless of `removed` (A1), embedding on the first region and reusing the xref thereafter (D-01/Pitfall 4). `LogoError` propagates to the main.py 4xx handler (mirrors `RedactError`).
- `tests/test_logo.py` (+3): bbox-within-rect+aspect-preserved, survives-redaction, single-xref-across-2-pages. `tests/test_process_api.py` (+2): no-`logo_id` = no embedded image (D-01), original SHA-256 unchanged across a remove+insert run (D-05).

**Task 2 — frontend:**
- `regions.js`: imports `getSelectedLogoId` from `./logos.js`; `applyRemoval` now posts `{ dpi, regions, logo_id: getSelectedLogoId() || null }` (api.js seam unchanged — it JSON-stringifies the whole spec).
- Conditional after-label: `refreshResultLabel()` sets `#view-result` `.textContent` to `移除+置入結果` (logo selected) or `移除結果` (null); called from `updateActionGroup` (so a logo-change via `notifyJobInputChanged` refreshes it) and `initRegions`. New COPY strings `resultLabelWithLogo` / `resultLabelNoLogo` / `beforeafterAria`.
- Broadened the toggle aria-label to `切換處理前後對照` (set via `setAttribute` in `initRegions`). Action-group state machine + buttons (`apply-removal`/`download-pdf`) unchanged (D-01 single flow).

## Deviations from Plan

None — plan executed exactly as written. The conftest `logo_png_bytes` / `logo_library` fixtures and the `JobSpec.logo_id` (already silently accepted by Pydantic before this plan, which is why the RED tests failed on "no image embedded" rather than a validation error) were exactly as the prior wave left them.

## Authentication Gates

None — no auth in this project (internal LAN, v1).

## Tests

- `tests/test_logo.py` — now 8 tests (5 prior LOGO-01 + 3 new LOGO-02): all green.
- `tests/test_process_api.py` — +2 (no-logo pure removal, remove+insert SHA-256): all green.
- Full suite: 160 passed (155 prior + 5 new), including `test_fitz_import_confined_to_engine_seam` confirming `pipeline.py` did not leak fitz after `place_logo` landed.
- Static (regions.js): sends `logo_id`; relabel strings live in JS (Task 2 node check passes).

## Known Stubs

None.

## Self-Check: PASSED

- Created/modified files exist on disk (pdf_engine.py, models.py, pipeline.py, process.py, regions.js, test_logo.py, test_process_api.py, this SUMMARY).
- All three per-task commits present: 043f115 (RED), d343aec (GREEN backend), 01e01c7 (frontend).
