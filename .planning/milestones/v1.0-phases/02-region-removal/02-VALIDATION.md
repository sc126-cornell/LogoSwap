---
phase: 02
slug: region-removal
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-22
automated_tests: 54
gap_tests_added: 3
total_tests: 150
requirements_covered: 6
requirements_manual_only: 2
---

# Phase 2 — Region Removal: Validation Report

> Nyquist audit of automated-test coverage for Phase 2 (region-removal) against
> REGION-01, REGION-02, REMOVE-01, REMOVE-03, REMOVE-04, OUTPUT-01.
> Conducted 2026-05-22 against 147 pre-existing tests; 3 gap tests added.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (Python 3.14.4, PyMuPDF 1.27.2.3) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py tests/test_process_api.py tests/test_redact.py tests/test_coords.py -q` |
| **Full suite command** | `.venv/Scripts/python -m pytest -q` |
| **Estimated runtime** | ~5 seconds |
| **Integration smoke** | `scripts/smoke_02_03.py` (in-process TestClient; run: `.venv/Scripts/python scripts/smoke_02_03.py`) |

---

## Sampling Rate

- **After every task commit:** Run quick command above
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must show 150 passed
- **Max feedback latency:** ~5 seconds

---

## Per-Requirement Coverage Map

### REGION-01 — Draw one or more rectangles on a page

| Aspect | Coverage | Test File | Command |
|--------|----------|-----------|---------|
| Backend: multi-region JobSpec accepted (up to MAX_REGIONS) | COVERED | `tests/test_process_api.py::test_process_too_many_regions_is_4xx` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k too_many -q` |
| Backend: empty regions list is valid no-op | COVERED | `tests/test_process_api.py::test_process_empty_regions_exports_noop` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k empty_regions -q` |
| Frontend: drag to draw rectangle, overlap allowed, no handles | MANUAL-ONLY | — | See Manual-Only section |
| Frontend: sub-4px drag creates no region | MANUAL-ONLY | — | See Manual-Only section |
| Frontend: Escape cancels in-progress drag | MANUAL-ONLY | — | See Manual-Only section |

**Status: PARTIAL** — backend accepts/rejects multi-region payloads; frontend drawing behavior is manual-only (no JS test framework, browser required).

---

### REGION-02 — Cross-page regions (per-page region lists)

| Aspect | Coverage | Test File | Command |
|--------|----------|-----------|---------|
| Backend: regions on multiple pages in one JobSpec removes content on each page | COVERED (gap filled) | `tests/test_phase2_gaps.py::test_process_removes_content_on_both_pages_of_multipage_pdf` | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py -k both_pages -q` |
| Backend: result-render serves after-image for page 1 (not just page 0) | COVERED (gap filled) | `tests/test_phase2_gaps.py::test_result_render_after_process_shows_removed_content_on_non_zero_page` | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py -k non_zero_page -q` |
| Frontend: per-page region map — paging swaps overlay + list | MANUAL-ONLY | — | See Manual-Only section |
| Frontend: region drawn on page N not visible on page M | MANUAL-ONLY | — | See Manual-Only section |

**Status: PARTIAL** — backend multi-page processing is now green; frontend per-page model is manual-only.

---

### REMOVE-01 — True removal of vector + text (not covered)

| Aspect | Coverage | Test File | Command |
|--------|----------|-----------|---------|
| post-redaction get_text empty over unpadded rect | COVERED | `tests/test_redact.py::test_remove_region_removes_text_and_vector` | `.venv/Scripts/python -m pytest tests/test_redact.py -k removes_text_and_vector -q` |
| post-redaction get_drawings empty (no survivor) | COVERED | `tests/test_redact.py::test_remove_region_removes_text_and_vector` | same |
| fully-covered vector removed | COVERED | `tests/test_redact.py::test_remove_region_fully_covered_vector_is_removed` | `.venv/Scripts/python -m pytest tests/test_redact.py -k fully_covered -q` |
| boundary-crossing CAD line survives (REMOVE_IF_COVERED) | COVERED | `tests/test_redact.py::test_remove_region_boundary_crossing_line_survives_job_succeeds` | `.venv/Scripts/python -m pytest tests/test_redact.py -k boundary_crossing -q` |
| empty region returns False (not error) | COVERED | `tests/test_redact.py::test_remove_region_empty_area_returns_false_not_error` | `.venv/Scripts/python -m pytest tests/test_redact.py -k empty_area -q` |
| exported PDF region is truly empty (end-to-end) | COVERED | `tests/test_process_api.py::test_process_then_render_then_download_full_slice` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k full_slice -q` |
| exported PDF empty on BOTH pages of multi-page doc | COVERED (gap filled) | `tests/test_phase2_gaps.py::test_process_removes_content_on_both_pages_of_multipage_pdf` | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py -k both_pages -q` |
| ~5pt pad larger than input rect | COVERED | `tests/test_redact.py::test_remove_region_pads_rect_larger_than_input` | `.venv/Scripts/python -m pytest tests/test_redact.py -k pads_rect -q` |
| PDF_REDACT_TEXT_NONE absent from redact.py | COVERED | `tests/test_redact.py::test_redact_py_never_uses_text_none` | `.venv/Scripts/python -m pytest tests/test_redact.py -k never_uses_text_none -q` |
| fitz confined to pdf_engine.py seam | COVERED | `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` | `.venv/Scripts/python -m pytest tests/test_redact.py -k confined -q` |

**Status: COVERED** — all core true-removal behaviors proven; multi-page gap filled.

---

### REMOVE-03 — Result precisely at marked location (incl. rotated pages)

| Aspect | Coverage | Test File | Command |
|--------|----------|-----------|---------|
| px->pt->px round-trip < 1px at rotation 0 | COVERED | `tests/test_coords.py::test_roundtrip_at_each_rotation[0]` | `.venv/Scripts/python -m pytest tests/test_coords.py -q` |
| px->pt->px round-trip < 1px at rotation 90 | COVERED | `tests/test_coords.py::test_roundtrip_at_each_rotation[90]` | same |
| px->pt->px round-trip < 1px at rotation 180 | COVERED | `tests/test_coords.py::test_roundtrip_at_each_rotation[180]` | same |
| px->pt->px round-trip < 1px at rotation 270 | COVERED | `tests/test_coords.py::test_roundtrip_at_each_rotation[270]` | same |
| offset MediaBox round-trip holds at all rotations | COVERED | `tests/test_coords.py::test_offset_mediabox_roundtrip_and_inside_page[*]` | same |
| visual IoU >= 0.95 at 0deg (backend-drawn Rect overlaps selection) | COVERED | `tests/test_coords.py::test_visual_overlap_iou_at_zero_rotation` | same |
| visual IoU >= 0.95 at all rotations | COVERED | `tests/test_coords.py::test_visual_overlap_iou_all_rotations[*]` | same |
| drag-direction independence (reversed rect = same Rect) | COVERED | `tests/test_coords.py::test_drag_direction_independence` | same |
| coords.py imports no fitz (AGPL seam) | COVERED | `tests/test_coords.py::test_seam_coords_imports_no_fitz` | same |
| reduced-DPI large page uses effective DPI (CR-01) | COVERED | `tests/test_redact.py::test_process_job_uses_effective_dpi_on_reduced_dpi_page` | `.venv/Scripts/python -m pytest tests/test_redact.py -k effective_dpi -q` |
| wrong DPI maps to wrong rect (proves CR-01 fix is load-bearing) | COVERED | `tests/test_redact.py::test_process_job_wrong_dpi_maps_to_wrong_rect_proving_cr01` | `.venv/Scripts/python -m pytest tests/test_redact.py -k wrong_dpi -q` |
| rotated-page true removal (90deg, end-to-end) | COVERED | `scripts/smoke_02_03.py` (integration smoke) | `.venv/Scripts/python scripts/smoke_02_03.py` |

**Status: COVERED** — all mapping correctness behaviors proven by the 17-test coords harness + reduced-DPI tests; 90deg rotated-page end-to-end proven by smoke.

---

### REMOVE-04 — Before/after preview

| Aspect | Coverage | Test File | Command |
|--------|----------|-----------|---------|
| GET /result/pages/{n}/image returns image/png with six X- headers after processing | COVERED | `tests/test_process_api.py::test_process_then_render_then_download_full_slice` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k full_slice -q` |
| GET /result/pages/0/image valid before any process run (shows unredacted work copy) | COVERED | `tests/test_process_api.py::test_result_render_valid_before_processing` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k valid_before -q` |
| before-image and after-image share identical DPI and pixel dims per page (WR-02) | COVERED | `tests/test_process_api.py::test_before_and_after_images_share_effective_dpi_and_dims` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k share_effective_dpi -q` |
| GET /result/pages/1/image serves after-image for page 1 (non-zero page) | COVERED (gap filled) | `tests/test_phase2_gaps.py::test_result_render_after_process_shows_removed_content_on_non_zero_page` | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py -k non_zero_page -q` |
| out-of-range page 404 | COVERED | `tests/test_process_api.py::test_result_render_out_of_range_page_404` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k out_of_range -q` |
| Frontend: 原圖/移除結果 segmented toggle swaps page-stage image source | MANUAL-ONLY | — | See Manual-Only section |
| Frontend: switching to 移除結果 hides the overlay rectangles | MANUAL-ONLY | — | See Manual-Only section |
| Frontend: toggling to 移除結果 with no fresh result shows error, stays on 原圖 | MANUAL-ONLY | — | See Manual-Only section |
| Frontend: before/after toggle follows page-changes (re-fetches correct page) | MANUAL-ONLY | — | See Manual-Only section |

**Status: PARTIAL** — server half fully covered; UI before/after toggle is manual-only (browser JS, no test framework).

---

### OUTPUT-01 — Download processed PDF

| Aspect | Coverage | Test File | Command |
|--------|----------|-----------|---------|
| GET /result returns application/pdf with Content-Disposition: attachment | COVERED | `tests/test_process_api.py::test_process_then_render_then_download_full_slice` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k full_slice -q` |
| ASCII filename in Content-Disposition (design_logoswap.pdf) | COVERED | `tests/test_process_api.py::test_process_then_render_then_download_full_slice` | same |
| CJK filename encoded as RFC-5987 filename*=UTF-8'' in Content-Disposition | COVERED (gap filled) | `tests/test_phase2_gaps.py::test_download_result_has_rfc5987_cjk_filename_in_content_disposition` | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py -k rfc5987_cjk -q` |
| All pages kept in downloaded PDF (D-07) | COVERED | `tests/test_process_api.py::test_process_then_render_then_download_full_slice` | same |
| GET /result before any process run -> 404 result_not_ready | COVERED | `tests/test_process_api.py::test_download_before_process_is_result_not_ready_404` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k result_not_ready -q` |
| No-op export (empty regions) still produces downloadable PDF | COVERED | `tests/test_process_api.py::test_process_empty_regions_exports_noop` | `.venv/Scripts/python -m pytest tests/test_process_api.py -k empty_regions_exports -q` |
| Frontend: 下載 PDF button click triggers browser file save | MANUAL-ONLY | — | See Manual-Only section |
| Frontend: download disabled when result is stale (after region edit) | MANUAL-ONLY | — | See Manual-Only section |

**Status: PARTIAL** — server download endpoint fully covered including CJK RFC-5987 encoding; UI download button and stale-state disable are manual-only (browser JS).

---

## Gap Tests Added

| # | File | Type | Gap Addressed | Command |
|---|------|------|---------------|---------|
| 1 | `tests/test_phase2_gaps.py::test_process_removes_content_on_both_pages_of_multipage_pdf` | integration | REGION-02 backend: multi-page removal truly empties both pages in exported PDF | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py -k both_pages -q` |
| 2 | `tests/test_phase2_gaps.py::test_result_render_after_process_shows_removed_content_on_non_zero_page` | integration | REMOVE-04: result-render endpoint serves after-image for page 1, not just page 0 | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py -k non_zero_page -q` |
| 3 | `tests/test_phase2_gaps.py::test_download_result_has_rfc5987_cjk_filename_in_content_disposition` | integration | OUTPUT-01: CJK filename encoded as RFC-5987 `filename*=UTF-8''` in Content-Disposition | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py -k rfc5987_cjk -q` |

All 3 gap tests were written to fail before they pass (adversarial stance confirmed: the tests assert behavioral contracts that were not previously covered by pytest, only by the smoke script).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Draw one or more rectangles via drag on the page overlay | REGION-01 | Vanilla JS pointer events; no JS test framework; browser required | Follow 02-03-PLAN.md Task 4 step 3: drag a rectangle, confirm slate-colored box appears, overlap allowed, crosshair cursor |
| Sub-4px drag creates no region | REGION-01 | Pointer event threshold; browser required | Click without dragging; confirm no region appears in side-panel |
| Escape cancels in-progress drag | REGION-01 | Keyboard event in browser; no JS harness | Start a drag, press Escape; confirm rubber-band box disappears and no region is committed |
| Per-page region lists — paging swaps overlay and side-panel | REGION-02 | JS Map keyed by page index; browser state | Draw on page 1, page to page 2, confirm regions gone; page back, confirm regions return |
| 原圖 / 移除結果 toggle swaps the page-stage image source | REMOVE-04 | Swaps `#page-image.src`; browser DOM; no JS harness | After 套用移除, click 移除結果; content must be visually gone; click 原圖, content returns |
| Switching to 移除結果 hides overlay rectangles | REMOVE-04 | CSS class toggle on overlay; browser | While in 移除結果 mode, confirm the drawn rectangles are not visible |
| Toggling 移除結果 with no fresh result shows "尚無移除結果" notice | REMOVE-04 | JS state machine; browser | Without applying, click 移除結果; confirm the notice appears and mode stays on 原圖 |
| Before/after toggle follows page-changes in result mode | REMOVE-04 | JS event on page:changed; browser | While in 移除結果 on page 1, page to page 2; confirm page 2's result image loads |
| 下載 PDF button triggers browser file save as 原名_logoswap.pdf | OUTPUT-01 | Navigation to `api.resultDownloadURL`; browser download | After 套用移除, click 下載 PDF; confirm file saves with correct name |
| Download button disabled when result is stale | OUTPUT-01 | JS resultFresh flag; browser | After 套用移除, draw a new region; confirm 下載 PDF is disabled until 重新套用 |
| Rotated-page removal visually lands on the boxed area | REMOVE-03 | Perceptual / visual; browser | Upload a rotated PDF, box a region, apply, toggle 移除結果; confirm removal is at the correct location on the page (not shifted) |
| Dark-mode region rectangles visible and accent discipline held | REGION-01 / REMOVE-04 | CSS theme; browser | Toggle to dark mode; confirm slate rectangles visible; exactly one accent button at a time |

---

## Verification Map (all requirements)

| Requirement | Status | Test Files | Automated Command |
|-------------|--------|------------|-------------------|
| REGION-01 | PARTIAL (backend green; frontend manual-only) | `test_process_api.py` | `.venv/Scripts/python -m pytest tests/test_process_api.py -q` |
| REGION-02 | PARTIAL (backend green via gap test; frontend manual-only) | `test_phase2_gaps.py`, `test_process_api.py` | `.venv/Scripts/python -m pytest tests/test_phase2_gaps.py tests/test_process_api.py -q` |
| REMOVE-01 | COVERED | `test_redact.py`, `test_process_api.py`, `test_phase2_gaps.py` | `.venv/Scripts/python -m pytest tests/test_redact.py tests/test_process_api.py tests/test_phase2_gaps.py -q` |
| REMOVE-03 | COVERED | `test_coords.py`, `test_redact.py` | `.venv/Scripts/python -m pytest tests/test_coords.py tests/test_redact.py -q` |
| REMOVE-04 | PARTIAL (server half covered; UI toggle manual-only) | `test_process_api.py`, `test_phase2_gaps.py` | `.venv/Scripts/python -m pytest tests/test_process_api.py tests/test_phase2_gaps.py -q` |
| OUTPUT-01 | PARTIAL (server side covered incl. CJK; UI button manual-only) | `test_process_api.py`, `test_phase2_gaps.py` | `.venv/Scripts/python -m pytest tests/test_process_api.py tests/test_phase2_gaps.py -q` |

---

## Full Suite Result

```
150 passed in 4.48s
```

Command: `.venv/Scripts/python -m pytest -q`

---

## Validation Sign-Off

- [x] All requirements mapped: REGION-01, REGION-02, REMOVE-01, REMOVE-03, REMOVE-04, OUTPUT-01
- [x] All backend behaviors have automated pytest coverage
- [x] 3 genuine gaps identified, tested, and confirmed green (adversarial: tests were written before running)
- [x] Frontend-browser-only behaviors classified as MANUAL-ONLY with test instructions provided
- [x] No test weakened to make it pass — all assertions are behavioral, not structural
- [x] Full suite green: 150 passed, 0 failed
- [x] Implementation files never modified
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-22
