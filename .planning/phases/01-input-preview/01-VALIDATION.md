---
phase: 1
slug: 01-input-preview
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-22
tests_total: 93
tests_green: 93
tests_red: 0
requirements_covered: 4
requirements_partial: 0
requirements_missing: 0
manual_only_count: 5
---

# Phase 1 — Validation Strategy: 輸入與預覽骨幹 (input-preview)

> Nyquist compliance audit for Phase 1. Requirements: UPLOAD-01, UPLOAD-04, PREVIEW-01, PREVIEW-02.
> Backend suite: 93 pytest tests, all green. Frontend behaviors that require a real browser are
> classified as manual-only (no JS test framework introduced — vanilla-JS, no build step).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (backend); `node --check` syntax only (frontend JS — no JS test framework) |
| **Config file** | `pytest.ini` (disables cache provider, sets `testpaths = tests`) |
| **Quick run command** | `.venv\Scripts\python -m pytest tests/test_phase1_gaps.py -v` |
| **Full suite command** | `.venv\Scripts\python -m pytest -q` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv\Scripts\python -m pytest -q`
- **After every plan wave:** Run `.venv\Scripts\python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~2 seconds

---

## Per-Requirement Coverage Map

### UPLOAD-01 — Upload single vector PDF

> Requirement: A POST of a vector PDF to /sessions returns a session_id, page_count, and filename (201).
> Over-limit (>50 MB or >30 pages) returns a structured 4xx whose message states the limit. Non-PDF returns structured 4xx, not a crash.

| Behavior | Test File | Test Name | Command | Status |
|----------|-----------|-----------|---------|--------|
| POST /sessions returns 201 + session_id + page_count | `tests/test_api.py` | `test_post_sessions_valid_pdf_returns_201` | `.venv\Scripts\python -m pytest tests/test_api.py::test_post_sessions_valid_pdf_returns_201 -v` | green |
| POST /sessions 201 body includes `filename` field | `tests/test_phase1_gaps.py` | `test_upload_response_includes_filename_field` | `.venv\Scripts\python -m pytest tests/test_phase1_gaps.py::test_upload_response_includes_filename_field -v` | green |
| `filename` is sanitized before echoing back (path-traversal name) | `tests/test_phase1_gaps.py` | `test_upload_response_filename_sanitized` | `.venv\Scripts\python -m pytest tests/test_phase1_gaps.py::test_upload_response_filename_sanitized -v` | green |
| Oversize upload → 413 + limit-bearing message ("50") | `tests/test_api.py` | `test_post_sessions_oversize_returns_413_with_limit` | `.venv\Scripts\python -m pytest tests/test_api.py::test_post_sessions_oversize_returns_413_with_limit -v` | green |
| Size-guard exact boundary (equal size accepted, +1 byte rejected) | `tests/test_api.py` | `test_post_sessions_size_guard_boundary` | `.venv\Scripts\python -m pytest tests/test_api.py::test_post_sessions_size_guard_boundary -v` | green |
| Too-many-pages → 413 + limit-bearing message ("30") | `tests/test_api.py` | `test_post_sessions_too_many_pages_returns_413_with_limit` | `.venv\Scripts\python -m pytest tests/test_api.py::test_post_sessions_too_many_pages_returns_413_with_limit -v` | green |
| Non-PDF payload → structured 4xx (415 or 422), never 500 | `tests/test_api.py` | `test_post_sessions_txt_payload_is_structured_4xx_not_500` | `.venv\Scripts\python -m pytest tests/test_api.py::test_post_sessions_txt_payload_is_structured_4xx_not_500 -v` | green |
| Content-sniff rejects non-PDF (ingest layer) | `tests/test_ingest.py` | `test_ingest_non_pdf_bytes_rejected_as_typed_error`, `test_ingest_plain_text_rejected_as_typed_error` | `.venv\Scripts\python -m pytest tests/test_ingest.py -v` | green |

**UPLOAD-01 verdict: COVERED** — all behaviors have passing automated tests.

---

### UPLOAD-04 — Original preserved write-once

> Requirement: The uploaded original is stored immutably under originals/ and is byte-for-byte unchanged after any later operation (ingest, render, page fetch). Processing uses a work/ copy; outputs/ reserved.

| Behavior | Test File | Test Name | Command | Status |
|----------|-----------|-----------|---------|--------|
| Original file is byte-for-byte identical to uploaded bytes immediately after ingest | `tests/test_ingest.py` | `test_ingest_original_is_byte_for_byte_identical` | `.venv\Scripts\python -m pytest tests/test_ingest.py::test_ingest_original_is_byte_for_byte_identical -v` | green |
| Original file is chmod 0o444 (read-only) after write | `tests/test_storage.py` | `test_write_original_is_read_only_after_write` | `.venv\Scripts\python -m pytest tests/test_storage.py::test_write_original_is_read_only_after_write -v` | green |
| Work-copy path is distinct from original and lives under work/ | `tests/test_storage.py` | `test_work_path_differs_from_original_and_lives_under_work` | `.venv\Scripts\python -m pytest tests/test_storage.py::test_work_path_differs_from_original_and_lives_under_work -v` | green |
| Original hash unchanged after a full ingest+render cycle (render reads work/ only) | `tests/test_api.py` | `test_original_unchanged_after_rendering` | `.venv\Scripts\python -m pytest tests/test_api.py::test_original_unchanged_after_rendering -v` | green |
| Three-directory layout created on new_session() | `tests/test_storage.py` | `test_new_session_creates_exactly_three_dirs` | `.venv\Scripts\python -m pytest tests/test_storage.py::test_new_session_creates_exactly_three_dirs -v` | green |

**UPLOAD-04 verdict: COVERED** — immutability is structurally proven by hash assertions and mode check.

---

### PREVIEW-01 — Server-rendered page preview

> Requirement: Each page is served as a server-rendered PNG via GET /sessions/{id}/pages/{n}/image. Default render DPI is 200 (D-02). The response carries 6 metadata headers for the Phase 2 coordinate seam.

| Behavior | Test File | Test Name | Command | Status |
|----------|-----------|-----------|---------|--------|
| Page image returns 200 + content-type image/png + PNG signature | `tests/test_api.py` | `test_get_page_image_returns_png_with_all_headers` | `.venv\Scripts\python -m pytest tests/test_api.py::test_get_page_image_returns_png_with_all_headers -v` | green |
| Default DPI is 200 (X-Render-Dpi == "200") | `tests/test_api.py` | `test_get_page_image_returns_png_with_all_headers` | (same) | green |
| All six X-... headers present (X-Page-Width-Pt, X-Page-Height-Pt, X-Page-Rotation, X-Render-Dpi, X-Image-Width-Px, X-Image-Height-Px) | `tests/test_api.py` | `test_get_page_image_returns_png_with_all_headers` | (same) | green |
| Six headers present for non-zero page index (page 1) | `tests/test_phase1_gaps.py` | `test_second_page_image_carries_metadata_headers` | `.venv\Scripts\python -m pytest tests/test_phase1_gaps.py::test_second_page_image_carries_metadata_headers -v` | green |
| Out-of-range page → 404 | `tests/test_api.py` | `test_get_page_image_out_of_range_returns_404` | `.venv\Scripts\python -m pytest tests/test_api.py::test_get_page_image_out_of_range_returns_404 -v` | green |
| /meta endpoint returns PageMeta JSON with dpi==200 and valid dims | `tests/test_api.py` | `test_get_page_meta_returns_pagemeta_with_default_dpi` | `.venv\Scripts\python -m pytest tests/test_api.py::test_get_page_meta_returns_pagemeta_with_default_dpi -v` | green |
| Render scale is DPI-derived (img_w ≈ page_w_pt * dpi / 72 ± 2 px) | `tests/test_render.py` | `test_render_scale_is_derived_from_dpi` | `.venv\Scripts\python -m pytest tests/test_render.py::test_render_scale_is_derived_from_dpi -v` | green |
| DPI clamped to [MIN_DPI, MAX_DPI] | `tests/test_render.py` | `test_render_dpi_clamped_to_bounds` | `.venv\Scripts\python -m pytest tests/test_render.py::test_render_dpi_clamped_to_bounds -v` | green |

**PREVIEW-01 verdict: COVERED** — server-rendered PNG + all 6 headers verified for both page 0 and page 1.

---

### PREVIEW-02 — Multi-page navigation

> Requirement: Page count and per-page addressing (0..page_count-1) support multi-page navigation. Every valid page in the range is independently addressable via the image and meta endpoints.

| Behavior | Test File | Test Name | Command | Status |
|----------|-----------|-----------|---------|--------|
| POST /sessions returns correct page_count for a 2-page PDF | `tests/test_api.py` | `test_post_sessions_valid_pdf_returns_201` | `.venv\Scripts\python -m pytest tests/test_api.py::test_post_sessions_valid_pdf_returns_201 -v` | green |
| GET /sessions/{id} returns page_count matching ingest | `tests/test_api.py` | `test_get_session_returns_page_count` | `.venv\Scripts\python -m pytest tests/test_api.py::test_get_session_returns_page_count -v` | green |
| Page 1 (non-zero index) image endpoint returns 200 + PNG | `tests/test_phase1_gaps.py` | `test_second_page_image_returns_200_png_for_multipage_doc` | `.venv\Scripts\python -m pytest tests/test_phase1_gaps.py::test_second_page_image_returns_200_png_for_multipage_doc -v` | green |
| Page 1 /meta returns page_no == 1 with valid dims | `tests/test_phase1_gaps.py` | `test_second_page_meta_returns_correct_page_no` | `.venv\Scripts\python -m pytest tests/test_phase1_gaps.py::test_second_page_meta_returns_correct_page_no -v` | green |
| Last valid page (page_count-1) is reachable (no off-by-one in range check) | `tests/test_phase1_gaps.py` | `test_last_page_of_multipage_doc_is_reachable` | `.venv\Scripts\python -m pytest tests/test_phase1_gaps.py::test_last_page_of_multipage_doc_is_reachable -v` | green |
| Page beyond range (999) returns 404 | `tests/test_api.py` | `test_get_page_image_out_of_range_returns_404` | `.venv\Scripts\python -m pytest tests/test_api.py::test_get_page_image_out_of_range_returns_404 -v` | green |

**PREVIEW-02 verdict: COVERED** — full 0..page_count-1 range addressability proven including boundary (last page) and non-zero index.

---

## Per-Task Verification Map

| Task ID | Plan | Requirement | Test Type | Automated Command | File | Status |
|---------|------|-------------|-----------|-------------------|------|--------|
| 01-01-T1 | 01 | UPLOAD-01, UPLOAD-04 | unit | `.venv\Scripts\python -m pytest tests/test_storage.py tests/test_ingest.py -q` | `tests/test_storage.py`, `tests/test_ingest.py` | green |
| 01-01-T2 | 01 | PREVIEW-01, PREVIEW-02 | integration | `.venv\Scripts\python -m pytest tests/test_render.py tests/test_api.py -q` | `tests/test_render.py`, `tests/test_api.py` | green |
| 01-01-gaps | 01 | UPLOAD-01, PREVIEW-02 | integration | `.venv\Scripts\python -m pytest tests/test_phase1_gaps.py -v` | `tests/test_phase1_gaps.py` | green |
| 01-02-T1 | 02 | UPLOAD-01 (frontend) | manual-only | `node --check web/js/api.js web/js/app.js` (syntax); browser required for upload flow | `web/js/api.js`, `web/js/app.js` | see manual |
| 01-02-T2 | 02 | — (theme, D-06/D-07) | manual-only | `node --check web/js/theme.js` (syntax); browser required for theme behavior | `web/js/theme.js` | see manual |
| 01-02-T3 | 02 | PREVIEW-01, PREVIEW-02 (frontend) | manual-only | `node --check web/js/viewer.js` (syntax); browser required for nav/zoom | `web/js/viewer.js` | see manual |

---

## Manual-Only Verifications

No JS test framework is in scope for this vanilla-JS, no-build-step project. The following
frontend behaviors can only be verified in a real browser (or with a JS test harness not
introduced in Phase 1). All have passing `node --check` syntax validation.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Upload flow: choose/drag PDF → uploading state → first page renders | UPLOAD-01, PREVIEW-01 | Requires real browser file-picker, fetch(), and DOM state machine | `uvicorn app.main:app --reload`; open `http://127.0.0.1:8000/`; upload a multi-page PDF; confirm 正在上傳檔案… then page image appears |
| Multi-page navigation: prev/next/jump-to-page, page indicator updates | PREVIEW-02 | Requires browser DOM interaction with viewer.js nav controls | After upload, use Next (下一頁) / Prev (上一頁) and jump input; confirm indicator reads 第 X 頁,共 Y 頁 |
| CSS-scale zoom does NOT re-fetch image at different DPI | PREVIEW-02 (D-02) | Requires browser DevTools Network panel to confirm no re-request on zoom | Click 放大/縮小/符合寬度; open DevTools Network; confirm no new image request fires on zoom step |
| Theme toggle switches light↔dark; persists across reload | — (D-06/D-07) | Requires browser localStorage and prefers-color-scheme | Click 切換深淺色模式; confirm accent changes blue→amber; reload; confirm theme persists |
| Error state: non-PDF upload shows verbatim Chinese copy, not crash | UPLOAD-01 | Requires browser fetch flow to exercise app.js error mapping | Upload a .txt file; confirm 無法開啟此檔案 + 此檔案格式不支援… with 重試 |

---

## Frontend Static Checks (Automated)

These `node --check` validations are automated but cover only JS syntax, not runtime behavior.

| File | Check | Command | Result |
|------|-------|---------|--------|
| `web/js/api.js` | Valid JS syntax; PDFTOOL_API_BASE seam present | `node --check web/js/api.js && grep -q PDFTOOL_API_BASE web/js/api.js` | pass |
| `web/js/theme.js` | Valid JS; uses localStorage + prefers-color-scheme + data-theme | `node --check web/js/theme.js` | pass |
| `web/js/viewer.js` | Valid JS; references pageImageURL and pageMeta | `node --check web/js/viewer.js` | pass |
| `web/js/app.js` | Valid JS; state machine copy strings present | `node --check web/js/app.js` | pass |
| `web/` (all JS) | No client-side PDF parser (pdfjs/pdf.js/pdf.worker) | `grep -rl "pdfjs\|pdf\.js\|PDFJS\|pdf\.worker" web/` returns nothing | pass |
| `app/` | `import fitz` in exactly one file (pdf_engine.py) | `grep -rl "import fitz" app/` returns only `app/services/pdf_engine.py` | pass |

---

## Validation Sign-Off

- [x] All 4 requirements (UPLOAD-01, UPLOAD-04, PREVIEW-01, PREVIEW-02) have automated tests
- [x] Coverage gaps filled: UPLOAD-01 `filename` field, PREVIEW-02 non-zero page index
- [x] 93 pytest tests, 93 green, 0 red
- [x] No watch-mode flags in any test command
- [x] Feedback latency ~2 seconds (full suite)
- [x] Frontend behaviors that require a browser are classified as manual-only (5 items)
- [x] No JS test framework introduced (project constraint: vanilla-JS, no build step)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-22
