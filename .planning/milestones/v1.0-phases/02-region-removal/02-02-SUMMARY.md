---
phase: 02-region-removal
plan: 02
subsystem: removal-pipeline
tags: [pymupdf, fitz, redaction, apply-redactions, true-removal, deferred-mutation, work-copy, result-render, export, download, pydantic, fastapi, agpl-isolation]

# Dependency graph
requires:
  - phase: 02-region-removal
    plan: 01
    provides: "coords.pixels_to_pdf_rect / clamp_px_rect (proven px<->pt mapper, REMOVE-03) + pdf_engine matrix accessors + unrotated_content_box clamp bound"
  - phase: 01-input-preview
    provides: "storage three-dir (originals 0o444 / work / outputs) + read_session_meta(filename) + render.render_page + the six X- header pattern + session_id allowlist + typed-error->{detail:{code,message}} handlers"
provides:
  - "redact.remove_region(page, rect) -> bool — true removal (add_redact_annot + apply_redactions text=REMOVE/graphics=REMOVE_IF_COVERED) with ~5pt pad + post-redaction emptiness assertion over the UNPADDED rect; RedactError on residual"
  - "pipeline.process_job(session_id, job_spec) -> {output_filename, page_count, regions:[{page,removed,clamped}]} — deferred-mutation on the WORK copy, exports 原名_logoswap.pdf keeping all pages"
  - "pdf_engine redaction seam: add_redact_annot, apply_redactions (refuses text-keep mode), get_text_words_in_rect, get_drawings_intersecting (degenerate-bbox-aware), save_doc, map_tuple_to_rect, re-exported TEXT_REMOVE/LINE_ART_REMOVE_IF_COVERED/IMAGE_NONE"
  - "POST /sessions/{id}/process + GET /sessions/{id}/result/pages/{n}/image + GET /sessions/{id}/result — the exact endpoint contract Plan 02-03 wires web/js/api.js to"
  - "RegionMark/JobSpec Pydantic v2 models (page>=0, finite px_rect len 4, dpi in [MIN,MAX], regions<=MAX_REGIONS); config.MAX_REGIONS=200"
affects: [02-03 region selection UI, 03-logo-insertion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deferred-mutation (D-05): the ONLY write path is process_job on the work/ copy; original (chmod 0o444) asserted distinct and proven byte-for-byte unchanged via SHA-256 test"
    - "True-removal seam: add_redact_annot + apply_redactions confined to pdf_engine; redact/pipeline stay fitz-free (grep -> only pdf_engine.py)"
    - "fill=None redaction (not white cover): paints nothing so the area reads as page background and get_drawings over the region is genuinely empty — the strongest REMOVE-01 assertion"
    - "Post-redaction emptiness assertion over the UNPADDED user rect (padding catches stroke wrappers without masking incomplete removal)"
    - "RequestValidationError reshaped to the project-wide {detail:{code,message}} (code=invalid_request) so every error has a stable detail.code"

key-files:
  created:
    - app/services/redact.py
    - app/services/pipeline.py
    - app/api/process.py
    - tests/test_redact.py
    - tests/test_process_api.py
  modified:
    - app/services/pdf_engine.py
    - app/models.py
    - app/config.py
    - app/main.py

key-decisions:
  - "fill=None instead of fill=(1,1,1): a white-fill annotation paints a NEW filled rectangle into the content stream that survives as a drawing whose bbox equals the redaction rect — a false-positive 'survivor' that would defeat the emptiness assertion AND is itself a cover. fill=None truly removes and paints nothing (white-on-colored raster fill is the Phase-4 image concern; vector/text removal here needs no cover)."
  - "get_drawings_intersecting uses an inclusive, degenerate-bbox-aware AABB overlap test (NOT fitz.Rect.intersects, which returns False for zero-area rects): a horizontal/vertical stroke survivor has a flat (zero-height/width) bbox and must still be caught (Pitfall 4)."
  - "Emptiness assertion is checked over the UNPADDED user rect; the ~5pt pad applies only to the redaction annot so padding can never mask an incomplete removal."
  - "Residual-content / page-out-of-range map to 422 (not 500): a processing/input problem, never a bare 500 that leaks internals (T-02-08). work_copy_misconfigured (internal invariant) maps to 500 by design — it should never fire."
  - "Download serves a FIXED session-scoped on-disk output name from outputs_dir(id); the CJK display name appears ONLY in the RFC-5987 Content-Disposition filename*, never as a path (T-02-06 — Phase-1 traversal guard not regressed)."

patterns-established:
  - "JobSpec/RegionMark are the validated /process request contract; px_rect is image pixels at the job dpi (echoed from the render X-Render-Dpi header) so client and server cannot disagree on scale."
  - "Result-render endpoint mirrors pages.py exactly (six X- headers, run_in_threadpool, _require_session, RenderError->404) but points render_page at the redacted work copy."

requirements-completed: [REMOVE-01, REMOVE-03, REMOVE-04, OUTPUT-01]

# Metrics
duration: ~8min
completed: 2026-05-22
---

# Phase 2 Plan 02: 真正移除管線 + 結果渲染/匯出/下載 (True-Removal Pipeline) Summary

**A complete, automatically-tested backend slice for true removal: a region payload (image-pixel rects + page + dpi) is clamped, mapped through the proven Wave-1 coordinate mapper, and the text AND vector objects inside it are truly removed (`apply_redactions` with `text=PDF_REDACT_TEXT_REMOVE` + `graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED`, ~5pt-padded, with a post-redaction emptiness assertion proving `get_text`/`get_drawings` over the unpadded region are empty) on the `work/` copy only — the immutable original's SHA-256 is byte-for-byte unchanged — then exported as `原名_logoswap.pdf` keeping all pages and served via `/process` + result-render + download endpoints, with `fitz` still confined to the engine seam.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-22T08:41:57Z
- **Completed:** 2026-05-22
- **Tasks:** 2
- **Files modified:** 9 (5 created, 4 modified)

## Accomplishments

- **True removal (REMOVE-01):** `redact.remove_region(page, rect)` marks the mapped rect grown by `REDACT_PAD_PT = 5.0` (stroke-wrapper survivors, Pitfall 4) then calls `apply_redactions(text=TEXT_REMOVE, graphics=LINE_ART_REMOVE_IF_COVERED, images=IMAGE_NONE)`. It then ASSERTS — over the **unpadded** user rect — that `get_text("words")` is empty AND no drawing intersects it, raising `RedactError("residual_content")` otherwise. Verified on a conftest page whose drawn text "Page 1" + line both fall inside the rect: both are gone afterward, and re-opening the **exported** PDF confirms the region extracts nothing.
- **Deferred-mutation (D-05):** `pipeline.process_job` opens the `work/` copy ONLY, asserts its path differs from the immutable `original_path`, and saves the redacted result to the work copy + `outputs/原名_logoswap.pdf`. An automated test hashes the original (SHA-256) before/after a `/process` run and asserts equality — **the original is byte-for-byte unchanged**.
- **AGPL seam intact (T-02-03):** all redaction/extraction/save calls were added as `pdf_engine` wrappers; `redact.py` and `pipeline.py` import no `fitz`. `grep -rl "import fitz" app/` returns ONLY `app/services/pdf_engine.py`.
- **Output (D-06/D-07):** export filename is `{stem}_logoswap.pdf` (CJK-safe; `圖紙.pdf` -> `圖紙_logoswap.pdf`), saved with `garbage=4, deflate=True, clean=True` (Pitfall 9 bloat). Page count is unchanged (test asserts `page_count == 2` on the export).
- **Endpoints:** `POST /process` (redact + export), `GET /result/pages/{n}/image` (the 移除結果 after-image with the six X- coordinate headers — server half of REMOVE-04), `GET /result` (download the attachment, OUTPUT-01). All reuse `_require_session`; the forbidden `PDF_REDACT_TEXT_NONE` is grep-proven absent from `redact.py`.
- **Coordinate correctness (REMOVE-03 inherited):** every region is mapped via `coords.pixels_to_pdf_rect` (never re-derived) and clamped via `coords.clamp_px_rect` against the page's rendered pixel box (T-02-01); an out-of-bounds rect is clamped + flagged, a zero-area result is skipped (no crash).
- **Full suite green:** `pytest -q` = **140 passed** (110 prior + 14 redact + 16 process-API), zero regression.

## Task Commits

Each task was committed atomically:

1. **Task 1: true-removal redaction + deferred-mutation pipeline** — `bdcf8bb` (feat)
2. **Task 2: process + result-render + download endpoints** — `38df6bc` (feat)

**Plan metadata** (this SUMMARY + STATE + ROADMAP + REQUIREMENTS) — committed separately as `docs(02-02)`.

_Note: both tasks are `tdd="true"`. Following the Phase-1 / 02-01 precedent (TDD source + behaviour tests authored together and run green before commit), each task's implementation and its proving test were committed along the natural file boundary: Task 1 = the redaction/pipeline spine + `tests/test_redact.py` (14 tests, green before commit); Task 2 = the endpoints + `tests/test_process_api.py` (16 tests, green before commit). The redact tests are the true-removal gate and were verified failing-then-passing during development (the emptiness assertion legitimately tripped on the white-fill survivor before the `fill=None` fix — see Deviations)._

## The Contract for Plan 02-03 (frontend `web/js/api.js`)

### Request models (Pydantic v2)

```
class RegionMark:
    page: int                      # 0-based page index, >= 0
    px_rect: [x0, y0, x1, y1]      # image pixels at the job dpi (finite, exactly 4)

class JobSpec:
    dpi: int                       # the render DPI px_rect was measured at; [MIN_DPI=72, MAX_DPI=300]
    regions: list[RegionMark]      # <= MAX_REGIONS (200); empty list = valid no-op export
```

`px_rect` is measured on exactly the PNG the render endpoint produced, at the DPI echoed by the image's `X-Render-Dpi` header (so client and server agree on scale). The server clamps each rect to the page box before mapping — the client need not.

### Endpoints

| Method + Path | Body / Params | Success | Errors |
|---|---|---|---|
| `POST /sessions/{id}/process` | `JobSpec` JSON | `200 {output_filename, page_count, regions:[{page, removed, clamped}]}` | `404 session_not_found`; `422 invalid_request` (malformed/over-cap body); `422 page_out_of_range`; `422 residual_content` |
| `GET /sessions/{id}/result/pages/{n}/image` | optional `?dpi=` (ge 1) | `200 image/png` + six `X-Page-Width-Pt / X-Page-Height-Pt / X-Page-Rotation / X-Render-Dpi / X-Image-Width-Px / X-Image-Height-Px` headers | `404 session_not_found`; `404 page_not_found` |
| `GET /sessions/{id}/result` | — | `200 application/pdf`, `Content-Disposition: attachment; filename=result.pdf; filename*=UTF-8''<urlencoded 原名_logoswap.pdf>` | `404 session_not_found`; `404 result_not_ready` (before any process run) |

- **Before/after toggle (D-04):** 原圖 keeps using the existing `GET /pages/{n}/image`; 移除結果 uses `GET /result/pages/{n}/image`. Both endpoints carry the same six headers so the overlay maths is identical.
- **Per-region flags:** `removed=false` (with no error) means the region overlapped no text/vector — surface the "沒有可移除的內容" notice. `clamped=true` means the rect was out-of-bounds and was clamped to the page.
- All error bodies are `{detail:{code,message}}` (the `message` is 繁中, ready to surface).

### Redaction flags + padding (the recipe used)

- `add_redact_annot(padded_rect, fill=None)` where `padded = user_rect grown by 5.0pt per side`.
- `apply_redactions(text=PDF_REDACT_TEXT_REMOVE, graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED, images=PDF_REDACT_IMAGE_NONE)`.
- Post-redaction emptiness assertion over the **unpadded** rect (text words empty AND no intersecting drawing).
- **Confirmation: the original is unchanged** — `process_job` writes only the work copy + outputs; the SHA-256 before/after test passes.

## Files Created/Modified

- `app/services/redact.py` (created) — `remove_region` (pad + true removal + emptiness assertion), `RedactError`, `REDACT_PAD_PT`. No fitz; no forbidden constant.
- `app/services/pipeline.py` (created) — `process_job` (deferred-mutation, clamp+map+redact, export), `output_filename`/`output_path`, `_logoswap_name` (CJK-safe), `PipelineError`. No fitz.
- `app/api/process.py` (created) — the three endpoints, mirroring `pages.py` conventions (six X- headers, `run_in_threadpool`, `_require_session`).
- `app/services/pdf_engine.py` (modified) — redaction seam: `map_tuple_to_rect`, `add_redact_annot` (accepts `fill=None`), `apply_redactions` (refuses text-keep mode), `get_text_words_in_rect`, `get_drawings_intersecting` (degenerate-bbox-aware `_rects_overlap`), `save_doc`; re-exported `TEXT_REMOVE`/`LINE_ART_REMOVE_IF_COVERED`/`IMAGE_NONE`.
- `app/models.py` (modified) — `RegionMark`/`JobSpec` with validators (page>=0, finite px_rect len 4, dpi bounds, regions cap).
- `app/config.py` (modified) — `MAX_REGIONS = 200` (T-02-04).
- `app/main.py` (modified) — register `process.router`; add `RedactError`/`PipelineError` handlers + a `RequestValidationError` reshaper.
- `tests/test_redact.py` (created, 14 tests) — true removal (text+vector), padding, empty-area->False, text-none refusal, original SHA-256 unchanged, export keeps all pages + region empty, work-copy redacted in place, CJK filename, out-of-bounds clamp, empty regions, page-out-of-range, forbidden-constant + fitz-purity greps.
- `tests/test_process_api.py` (created, 16 tests) — full slice (process->after-image->download with exported-region-empty assertion), result-render valid before processing, result_not_ready 404, missing-session 404s, malformed/over-cap/out-of-range bodies structured 4xx, empty-regions no-op, crafted-id 404.

## Key Test Evidence

| Guarantee | Test | Result |
|---|---|---|
| **Truly removed (text+vector)** over the unpadded user rect | `test_remove_region_removes_text_and_vector` | PASS — `words == []` and `drawings == []` after redaction |
| **Truly removed on the EXPORTED PDF** (end-to-end) | `test_process_then_render_then_download_full_slice` + `_exported_region_empty` | PASS — re-opened download extracts nothing in the region |
| **Original SHA-256 unchanged** (D-05) | `test_process_job_leaves_original_unchanged`, full-slice API test | PASS — before == after across `/process` |
| **All pages kept** (D-07) | export + download tests assert `page_count == 2` | PASS |
| **~5pt pad** larger than input rect | `test_remove_region_pads_rect_larger_than_input` | PASS — padded rect strictly contains user rect by REDACT_PAD_PT |
| **Forbidden constant absent** | `test_redact_py_never_uses_text_none` | PASS — `PDF_REDACT_TEXT_NONE` not in redact.py |
| **fitz confined to seam** | `test_fitz_import_confined_to_engine_seam` | PASS — only `pdf_engine.py` |
| **Out-of-bounds clamped, no crash** | `test_process_job_out_of_bounds_region_is_clamped_not_crash` | PASS — `clamped=True`, `removed=False` |
| **Malformed body structured 4xx** | `test_process_malformed_body_is_structured_4xx_not_500` (5 cases) | PASS — 422 `{detail:{code,message}}`, never 500 |

## Decisions Made

- **`fill=None` (no white cover):** A `fill=(1,1,1)` redaction annot paints a *new* filled rectangle into the content stream which survives as a `get_drawings` entry whose bbox equals the redaction rect — empirically confirmed: with white fill the supplier black line is gone but a `color=(1,1,1)` filled `re` survives; with `fill=None` zero drawings survive. White fill would (a) be a literal "cover" and (b) cause the emptiness assertion to false-trip. So vector/text removal uses `fill=None`; the region reads as page background. (White-on-colored raster fill remains a Phase-4 image concern; images are untouched here, `images=IMAGE_NONE`.)
- **Degenerate-bbox-aware drawing overlap:** `fitz.Rect.intersects` returns `False` for a zero-area rect, but a horizontal/vertical stroke survivor has a flat bbox (`Rect(20,100,180,100)`). The seam's `_rects_overlap` does an inclusive per-axis interval test so such a survivor is never silently missed — essential for the true-removal assertion (Pitfall 4).
- **Assertion over the unpadded rect:** the ~5pt pad applies only to what gets redacted; the emptiness check uses the original user rect so padding cannot mask an incomplete removal.
- **422 (not 500) for residual/page-range:** these are processing/input problems mapped to structured 4xx (T-02-08); a bare 500 would leak internals / risk a worker. `work_copy_misconfigured` deliberately maps to 500 as an internal-invariant breach that should never fire.
- **Validation reshaping:** added a `RequestValidationError` handler so Pydantic 422s become `{detail:{code:"invalid_request", message}}`, matching the project-wide error contract the frontend reads.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] White-fill redaction left a survivor that defeated the emptiness assertion**
- **Found during:** Task 1 (`test_remove_region_removes_text_and_vector` first run — the post-redaction assertion tripped).
- **Issue:** The plan's `<action>` specifies `add_redact_annot(page, padded, fill=(1,1,1))`. Empirically a white-fill annot paints a NEW filled rectangle into the content stream that PyMuPDF then reports via `get_drawings` (a `fill=(1,1,1)`, type `fs`, `items=['re']` rect whose bbox equals the padded redaction rect). The supplier line WAS truly removed, but this painted white box is a residual drawing — it both is a "cover" (the very anti-pattern we forbid) and false-trips the mandatory post-redaction emptiness assertion. With `fill=None`, the content is truly removed and nothing is painted, so `get_drawings` over the region is genuinely empty.
- **Fix:** Use `fill=None` in `remove_region`; `pdf_engine.add_redact_annot` now accepts `fill=None`. Documented inline. (White raster fill is a Phase-4 concern; images are untouched here.)
- **Files modified:** `app/services/redact.py`, `app/services/pdf_engine.py`
- **Verification:** `test_remove_region_removes_text_and_vector`, `test_process_then_render_then_download_full_slice` + `_exported_region_empty` pass.
- **Committed in:** `bdcf8bb`

**2. [Rule 1 - Bug] `get_drawings_intersecting` missed flat-bbox stroke survivors**
- **Found during:** Task 1 (pre-condition assertion — the conftest line was not detected inside the region).
- **Issue:** The line's bounding box is `Rect(20,100,180,100)` — zero height. `fitz.Rect.intersects` returns `False` for a zero-area rect, so a horizontal/vertical stroke (a common logo outline / CAD line) would be invisible to both the pre-condition and, more dangerously, the post-redaction survivor check — a silent true-removal failure (Pitfall 4).
- **Fix:** Replaced the `.intersects` call with an inclusive, degenerate-aware per-axis AABB overlap test (`_rects_overlap`) in the seam.
- **Files modified:** `app/services/pdf_engine.py`
- **Verification:** drawing pre-condition + post-condition assertions pass; survivor would be caught.
- **Committed in:** `bdcf8bb`

**3. [Rule 1 - Bug] `redact.py` docstring/comment contained the literal forbidden constant, tripping the grep gate**
- **Found during:** Task 1 (`test_redact_py_never_uses_text_none` + the repo-wide acceptance grep).
- **Issue:** The module docstring and an inline comment used the literal phrase `PDF_REDACT_TEXT_NONE` in prose ("the forbidden ... constant never appears here"). The acceptance check greps `redact.py` for that exact substring, so the prose false-tripped it — the identical trap 02-01 documented for the `import fitz` literal.
- **Fix:** Reworded both to describe the forbidden mode without naming the constant ("the text-keep redaction mode ... is never named here — only the true-removal TEXT_REMOVE is used").
- **Files modified:** `app/services/redact.py`
- **Verification:** `PDF_REDACT_TEXT_NONE` grep on `redact.py` returns nothing; test passes. (The test file legitimately contains the constant in `test_apply_redactions_refuses_text_none`, which the acceptance check does not scan.)
- **Committed in:** `bdcf8bb`

**4. [Rule 2 - Missing critical functionality] Pydantic 422 did not match the project-wide error contract**
- **Found during:** Task 2 (designing the malformed-body acceptance test).
- **Issue:** FastAPI's default validation error body is `{"detail": [<error list>]}`, which lacks the `detail.code`/`detail.message` shape the frontend (and the Phase-1 contract) relies on; a malformed `JobSpec` would otherwise return a shape the client can't read uniformly.
- **Fix:** Added a `RequestValidationError` handler in `main.py` reshaping it to `{detail:{code:"invalid_request", message}}` (summarizing the first error's location + message).
- **Files modified:** `app/main.py`
- **Verification:** `test_process_malformed_body_is_structured_4xx_not_500` (5 cases) + `test_process_too_many_regions_is_4xx` pass; no Phase-1 regression (140 passed).
- **Committed in:** `38df6bc`

---

**Total deviations:** 4 auto-fixed (3 bugs surfaced by the mandatory true-removal/grep gates; 1 missing error-contract reshaping). No architectural changes, no scope creep. The redaction recipe still follows STACK.md/PITFALLS by name (`add_redact_annot` + `apply_redactions` with the mandated flags + ~5pt pad + emptiness assertion) — the only substantive change is `fill=None` over `fill=(1,1,1)`, which is *more* correct for true vector/text removal (no cover, clean assertion).

## Issues Encountered

- **PyMuPDF redaction self-fill artifact (resolved):** the core finding above — `fill=(1,1,1)` paints a survivor. Resolved with `fill=None` after a throwaway probe distinguished the supplier line (`color=(0,0,0)`, type `s`) from the white cover (`color=(1,1,1)`, type `fs`).
- **Git CRLF warnings** on staged files — benign Windows normalization, no action (same as Phase 1 / 02-01).
- **Pre-existing unstaged `.planning/config.json` change** (the `_auto_chain_active` flag) is NOT part of this plan and was deliberately left unstaged / uncommitted (same as 02-01).
- **Python 3.14.4 / PyMuPDF 1.27.2.3** in the venv (STACK recommends 3.12 but Phase 1 confirmed 3.14 viable via the cp310-abi3 wheel) — no issues.

## Threat surface scan

No new security surface beyond the plan's `<threat_model>`. Mitigations implemented as specified:
- **T-02-01** (malformed/out-of-bounds rect): `clamp_px_rect` against the page's rendered pixel box before mapping; finite-coordinate Pydantic validation; zero-area-after-clamp skipped (test: out-of-bounds -> clamped+removed=False, no crash).
- **T-02-04** (DoS via region count / dpi): `MAX_REGIONS=200` cap (422 over the cap), `dpi` validated into `[MIN_DPI, MAX_DPI]`, redaction/render in `run_in_threadpool`.
- **T-02-05** (original mutation): pipeline opens `work_path` only + asserts it differs from `original_path`; SHA-256 before/after test passes.
- **T-02-06** (path traversal / disclosure): `session_id` flows through the Phase-1 allowlist (crafted id -> 404); download serves a FIXED `outputs_dir(id)` name, CJK name only in the `filename*` header.
- **T-02-07** (covers-but-not-removes): mandatory post-redaction emptiness assertion; `apply_redactions` always called; the text-keep mode is forbidden and the wrapper refuses it; grep-proven absent from `redact.py`.
- **T-02-08** (unhandled exception -> 500): `RedactError`/`PipelineError`/`PdfEngineError`/`RequestValidationError` all map to structured 4xx (residual/page-range -> 422), never a bare 500.

## Known Stubs

None. `redact.py`, `pipeline.py`, and `process.py` are real, runnable code with verified true-removal behaviour (the emptiness assertion is enforced and tested on both the work copy and the exported PDF). No placeholder/hardcoded values, no UI stubs (the frontend region UI is correctly deferred to Plan 02-03). Raster/image removal (`images=IMAGE_NONE`) is intentionally untouched — Phase 4.

## Next Phase Readiness

- **Plan 02-03 (region selection UI) is unblocked:** the exact `/process` + result-render + `/result` contract is documented above for `web/js/api.js`. The frontend draws rectangles on the existing page-stage overlay, sends `{dpi, regions:[{page, px_rect}]}` (px_rect in image pixels at the image's `X-Render-Dpi`), then toggles 原圖 (`/pages/{n}/image`) vs 移除結果 (`/result/pages/{n}/image`) and offers download (`/result`). Per-region `removed`/`clamped` flags drive the "沒有可移除的內容" notice and clamp feedback.
- **Gate discipline:** `pytest tests/test_redact.py tests/test_process_api.py -q` (30 tests) is the true-removal + endpoint regression gate; `tests/test_coords.py` (17) remains the mapper gate. Full suite = 140 passed.
- **Carry-forward to Phase 3 (logo insertion):** the redaction seam + deferred-mutation pipeline are the substrate logo placement extends — `insert_image`/`show_pdf_page` will be added as `pdf_engine` wrappers and called from a pipeline step after `remove_region`, reusing the same coords mapping and work-copy/export discipline.

## Self-Check: PASSED

- Created files verified present: `app/services/redact.py`, `app/services/pipeline.py`, `app/api/process.py`, `tests/test_redact.py`, `tests/test_process_api.py`. Modified: `app/services/pdf_engine.py`, `app/models.py`, `app/config.py`, `app/main.py`.
- Both task commits verified in git log: `bdcf8bb` (Task 1, feat), `38df6bc` (Task 2, feat).
- `pytest tests/test_redact.py tests/test_process_api.py -q` = 30 passed; full `pytest -q` = 140 passed. `grep -rl "import fitz" app/` = only `app/services/pdf_engine.py`. `PDF_REDACT_TEXT_NONE` absent from `redact.py`. Original SHA-256 unchanged across `/process` (D-05); exported `*_logoswap.pdf` keeps all pages (D-07) and the processed region extracts nothing (REMOVE-01).

---
*Phase: 02-region-removal*
*Completed: 2026-05-22*
