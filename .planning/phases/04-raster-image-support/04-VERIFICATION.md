---
phase: 04-raster-image-support
verified: 2026-05-23T09:03:45Z
status: passed
score: 3/3 must-haves verified
overrides_applied: 0
---

# Phase 4: 點陣圖與圖片型檔案支援 驗證報告

**Phase Goal:** 支援圖片型(點陣/掃描)PDF 與獨立影像檔(PNG/JPG/TIFF)。移除區域以白色填滿(PDF_REDACT_IMAGE_PIXELS),並可同樣置入我司 logo。
**Verified:** 2026-05-23T09:03:45Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 使用者可上傳圖片型 PDF 或獨立影像檔(PNG/JPG/TIFF),並能預覽與框選 | VERIFIED | `ingest_upload` 含完整四 magic dispatch;`test_png_upload_normalizes_to_a4_pdf` / `test_jpeg_upload_normalizes_to_a4_pdf` / `test_tiff_upload_normalizes_to_a4_pdf` 全 pass;`web/index.html` dropzone accept 含全部 MIME type;`test_image_upload_through_to_raster_dispatch` e2e 串接 |
| 2 | 點陣圖/影像的框選區域在輸出中以白色填滿(PDF_REDACT_IMAGE_PIXELS),原內容被移除 | VERIFIED | `pdf_engine.IMAGE_PIXELS == fitz.PDF_REDACT_IMAGE_PIXELS == 2` 實測確認;`remove_region_raster` 使用 `images=IMAGE_PIXELS` + `fill=None`;`test_image_only_pdf_full_frame_redacts_to_white` + `test_dual_layer_ocr_text_leak_closed_end_to_end` e2e pass |
| 3 | 影像型檔案同樣可置入我司 logo 並下載 | VERIFIED | `pipeline.process_job` raster dispatch 後執行相同 `place_logo` 路徑;`test_image_only_pdf_with_logo_placement` + `test_png_upload_with_logo_placement` 兩條 e2e 測試 pass |

**Score:** 3/3 truths verified

---

## D-NN Locked Decisions Verification

| Decision | Claim | Codebase Evidence | Status |
|----------|-------|-------------------|--------|
| D-08 IMAGE_PIXELS 常數 | `pdf_engine.IMAGE_PIXELS == fitz.PDF_REDACT_IMAGE_PIXELS == 2` | 實測:`IMAGE_PIXELS == 2` 且 `fitz.PDF_REDACT_IMAGE_PIXELS == 2` match:True | VERIFIED |
| D-09 raster fill=None | `remove_region_raster` 含 `fill=None` | `redact.py` 兩處 `add_redact_annot(page, padded_fitz, fill=None)`;無 `fill=(1,1,1)`;`test_raster_fill_none_no_drawing_residual` pass | VERIFIED |
| D-05 per-region dispatch | `pipeline.process_job` 有 `rect_overlaps_image` if/else | `pipeline.py` line 247–250:`if pdf_engine.rect_overlaps_image(page, pdf_rect): redact.remove_region_raster else: remove_region_vector` | VERIFIED |
| D-01 A4 fit | `image_to_a4_pdf` 用 A4 常數 | `A4_WIDTH_PT = 595.0` / `A4_HEIGHT_PT = 842.0`;`doc.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)`;`keep_proportion=True` | VERIFIED |
| D-02 多頁 TIFF 拒絕 | `n_frames > 1` check + `multi_page_tiff_unsupported` 4xx | `ingest.py:150-154` `getattr(img, "n_frames", 1) > 1` → `IngestError("multi_page_tiff_unsupported", ...)`;`test_multi_page_tiff_rejected` pass | VERIFIED |
| D-03 CMYK→RGB | `img.convert("RGB")` 在 ingest 鏈 | `ingest.py:164-165` `if img.mode != "RGB": img = img.convert("RGB")`;`test_cmyk_tiff_normalized_to_rgb` pass | VERIFIED |
| D-12 magic sniff | 四 magic header 都檢 | `_PNG_MAGIC` / `_JPEG_MAGIC` / `_TIFF_LE_MAGIC` / `_TIFF_BE_MAGIC` 全部定義;`_sniff_kind` startswith offset-0;`test_sniff_kind_dispatches_four_magics` pass | VERIFIED |
| D-07 UI 不揭露分類 | `web/` 無 raster/vector/scan/點陣/向量/掃描 字眼 | `grep -i "raster\|vector\|scan\|點陣\|向量\|掃描" web/` → 0 hits | VERIFIED |

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/pdf_engine.py` | `IMAGE_PIXELS` 常數 + `rect_overlaps_image` helper + `image_to_a4_pdf` + A4 常數 | VERIFIED | 全部存在且非 stub;`rect_overlaps_image` 實作完整 AABB overlap 掃描 |
| `app/services/redact.py` | `remove_region_vector` + `remove_region_raster`(無舊 `remove_region`) | VERIFIED | 兩個 entry point 存在;`def remove_region(` 舊名已消失;兩者 `fill=None` |
| `app/services/pipeline.py` | `pristine_path` reset + per-region dispatch | VERIFIED | `storage.pristine_path(sid)` 取代 `original_path`;`rect_overlaps_image` if/else dispatch |
| `app/services/ingest.py` | 四 magic dispatch + Pillow chain + three-write persist | VERIFIED | `_sniff_kind` + `_ingest_image` + `_ingest_image_to_pdf` 完整鏈路 |
| `app/storage.py` | `pristine_path` + `write_pristine_copy` + `_KINDS` 含 "pristine" | VERIFIED | 全部存在;`_KINDS = ("originals", "work", "outputs", "pristine")` |
| `web/index.html` | dropzone accept 含 PNG/JPG/TIFF;五處繁中文案 | VERIFIED | accept 屬性含全部 MIME type;「上傳 PDF 或影像以開始」等文案到位 |
| `web/js/app.js` | 三個新 COPY key + messageForError switch cases | VERIFIED | `unsupportedImageFormat` / `multiPageTiffUnsupported` / `corruptImage` 三 key 及 switch case 全部到位 |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `ingest.py` | `pdf_engine.image_to_a4_pdf` | `_ingest_image_to_pdf` 呼叫 | WIRED | `pdf_bytes = pdf_engine.image_to_a4_pdf(normalized_bytes)` |
| `pipeline.py` | `pdf_engine.rect_overlaps_image` | per-region if/else | WIRED | `if pdf_engine.rect_overlaps_image(page, pdf_rect):` |
| `pipeline.py` | `redact.remove_region_raster` | raster branch | WIRED | `removed = redact.remove_region_raster(page, pdf_rect)` |
| `pipeline.py` | `storage.pristine_path` | reset-from-pristine | WIRED | `pristine = storage.pristine_path(session_id)`;`shutil.copyfile(pristine, work)` |
| `redact.remove_region_raster` | `pdf_engine.IMAGE_PIXELS` | `apply_redactions(images=IMAGE_PIXELS, ...)` | WIRED | 在 `apply_redactions` 呼叫中直接引用 `pdf_engine.IMAGE_PIXELS` |
| `ingest._ingest_image` | Pillow CMYK→RGB | `img.convert("RGB")` | WIRED | `if img.mode != "RGB": img = img.convert("RGB")` |

---

## AGPL Seam Invariant

| Check | Status | Evidence |
|-------|--------|----------|
| `import fitz` 只在 `app/services/pdf_engine.py` | VERIFIED | AST-based `test_fitz_import_confined_to_engine_seam` pass;grep `app/**/*.py` 僅命中 `pdf_engine.py`(`.tmp` 檔不在 `*.py` glob 範圍內) |
| `redact.py` 無 `import fitz` | VERIFIED | `grep -c "import fitz" app/services/redact.py` → 0 |
| `pipeline.py` 無 `import fitz` | VERIFIED | `grep -c "import fitz" app/services/pipeline.py` → 0 |
| `ingest.py` 無 `import fitz` | VERIFIED | ingest.py 只 `import PIL`;fitz 呼叫經 `pdf_engine` wrapper |

備注:`app/services/pdf_engine.py.tmp.45532.f9d2f1ab3d2c` 為前次 session 殘留的暫存檔,不屬於任何 `*.py` glob,AGPL seam test 不計入、測試不受影響。

---

## REQ-ID Coverage

| Requirement | Description | Implementation Evidence | Status |
|-------------|-------------|------------------------|--------|
| UPLOAD-02 | 使用者可上傳圖片型(點陣/掃描)PDF 進行處理 | `ingest._sniff_kind` 接受 PDF magic(image-only PDF 走 PDF 路徑);`rect_overlaps_image` + raster dispatch;`test_image_only_pdf_full_frame_redacts_to_white` e2e pass | SATISFIED |
| UPLOAD-03 | 使用者可上傳獨立影像檔(PNG/JPG/TIFF),系統將其正規化為可處理的單頁文件 | `_ingest_image_to_pdf` Pillow chain → `image_to_a4_pdf`;三個 upload normalize 測試 + `test_image_upload_through_to_raster_dispatch` e2e | SATISFIED |
| REMOVE-02 | 對點陣圖/影像內容,框選區域以白色填滿 | `remove_region_raster` 使用 `images=IMAGE_PIXELS`(值=2);`test_image_only_pdf_full_frame_redacts_to_white` 確認整框變白 | SATISFIED |

---

## Phase 1–3 Zero Regression

| Check | Status |
|-------|--------|
| 233 passed(baseline 200 + 14 Phase-4-01 + 19 Phase-4-02) | VERIFIED |
| `remove_region_vector` body 與 Phase 2 `remove_region` byte-identical | VERIFIED — rename 只改函式名,body 不動 |
| PDF 上傳路徑(`_ingest_pdf`)不變 | VERIFIED — Phase 1–3 的 PDF ingest + pipeline 全部走原路 |
| SHA-256 D-05 invariant 更強 | VERIFIED — pipeline 改從 `pristine` reset,`originals/` 永遠不被 pipeline 碰觸 |

---

## Behavioral Spot-Checks

| Behavior | Command / Test | Result | Status |
|----------|---------------|--------|--------|
| IMAGE_PIXELS 常數值 | `from app.services.pdf_engine import IMAGE_PIXELS; IMAGE_PIXELS == 2` | True | PASS |
| 233 tests pass | `.venv/Scripts/python.exe -m pytest tests/ -x -q` | `233 passed in 7.26s` | PASS |
| raster/image 相關測試 | `-k "raster or image_only or dual_layer or image_upload or sniff or tiff or png_upload"` | `26 passed` | PASS |
| AGPL seam test | `-k "fitz_import_confined"` | `1 passed` | PASS |
| Phase 4 e2e tests | `-k "image_only_pdf_full_frame or dual_layer_ocr or image_upload_through_to or image_only_pdf_with_logo"` | `8 passed` | PASS |

---

## TDD Commit Cadence

Git log 可驗證 RED→GREEN 順序:

| Commit | Type | Description |
|--------|------|-------------|
| `d0c24f6` | test RED | T-04-01-01: failing tests for `image_to_a4_pdf` + pristine storage |
| `d9bd133` | feat GREEN | T-04-01-01: `image_to_a4_pdf` + pristine storage |
| `c6a7d85` | test RED | T-04-01-02: failing tests for ingest dispatch + Pillow chain + pipeline reset |
| `573c430` | feat GREEN | T-04-01-02: ingest dispatch + Pillow chain + pipeline reset-from-pristine |
| `ddefbb9` | feat GREEN | T-04-01-03: dropzone + error COPY + image e2e tests |
| `301858a` | test RED | T-04-02-01: raster fixtures + IMAGE_PIXELS/rect_overlaps_image tests |
| `d84eead` | feat GREEN | T-04-02-01: IMAGE_PIXELS const + rect_overlaps_image wrapper |
| `350a483` | test RED | T-04-02-02: rename callers + raster-branch tests |
| `1cc24ee` | feat GREEN | T-04-02-02: split redact entry points + pipeline dispatch(+Rule 3 fix pipeline.py) |
| `6d73711` | test | T-04-02-03: image-only/dual-OCR/PNG-upload e2e + idempotent raster |

---

## Anti-Patterns Found

| File | Pattern | Severity | Assessment |
|------|---------|----------|------------|
| `app/services/pdf_engine.py.tmp.*` | 殘留暫存檔(非 .py,不影響執行或 AGPL grep) | INFO | 可在 Phase 5 清理,不阻擋功能 |

**TBD / FIXME / XXX 檢查:** Phase 4 修改的所有 .py 檔均無未引用的 TBD/FIXME/XXX debt marker。

---

## Human Verification Required

無 — 所有 Success Criteria 均可程式化驗證且已全部通過自動測試。視覺/UX 層面(dropzone UI 顯示、實機拖曳上傳)屬 Phase 5 UAT 範疇。

---

## Gaps Summary

無待解 gap。三條 Success Criteria 全部 VERIFIED,14 個 D-NN 決定全數落地並有測試保護,AGPL seam invariant 不破,Phase 1–3 零迴歸(233 passed)。

---

_Verified: 2026-05-23T09:03:45Z_
_Verifier: Claude (gsd-verifier)_
