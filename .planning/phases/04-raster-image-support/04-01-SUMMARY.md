---
phase: 04-raster-image-support
plan: 04-01
subsystem: ingest + storage + pdf_engine + frontend
tags:
  - phase-04
  - ingest
  - image-normalization
  - pillow
  - mvp-vertical-slice
  - upload-03
dependency_graph:
  requires:
    - "Phase 1: ingest._looks_like_pdf magic-sniff pattern"
    - "Phase 1: storage three-directory layout + chmod 0o444 originals"
    - "Phase 2: pipeline.process_job deferred-mutation"
    - "Phase 3: logo placement + auto-pick (unchanged for image type)"
  provides:
    - "pdf_engine.image_to_a4_pdf + A4_WIDTH_PT/A4_HEIGHT_PT (Phase 4-02 raster dispatch base)"
    - "storage.pristine_path + write_pristine_copy (pipeline reset source — image bytes never opened as PDF)"
    - "ingest._sniff_kind four-magic dispatch + _ingest_image Pillow chain"
    - "Three new typed IngestError codes (unsupported_image_format/multi_page_tiff_unsupported/corrupt_image)"
    - "Unified dropzone accepting PDF + PNG + JPG + TIFF"
  affects:
    - "app/services/pipeline.py reset source: originals/ → pristine/ (PDF reset path SHA-256 invariant strengthened)"
tech_stack:
  added:
    - "Pillow 12.x: Image.open / verify / n_frames / convert(RGB) / load chain"
  patterns:
    - "Magic-header sniff with image-magic offset=0 + PDF-magic ≤8 leading offset (D-12 defense vs polyglot)"
    - "Pillow CMYK→RGB + RGBA flatten chain (D-03, Pitfall D + G defense)"
    - "Three-write ingest persistence: originals (raw bytes, 0o444) + work (PDF) + pristine (PDF reset source)"
key_files:
  created: []
  modified:
    - "app/services/pdf_engine.py"
    - "app/services/ingest.py"
    - "app/services/pipeline.py"
    - "app/storage.py"
    - "app/config.py"
    - "app/main.py"
    - "app/api/sessions.py"
    - "web/index.html"
    - "web/js/app.js"
    - "web/js/api.js"
    - "tests/conftest.py"
    - "tests/test_ingest.py"
    - "tests/test_process_api.py"
decisions:
  - "Pillow re-emits PNG for PNG/TIFF paths and JPEG for JPEG paths (byte-near-exact passthrough for JPEG via PyMuPDF's JPEG XObject; lossless after drop-alpha for PNG/TIFF)"
  - "Pillow verify() check kept exactly as logo._validate_png (read .format BEFORE verify; verify invalidates the Image object)"
  - "Defensive 1-page assertion after image_to_a4_pdf — guards against future regression where the wrapper could fail to produce a valid PDF"
  - "Pipeline reset source now pristine/ for ALL upload types (PDF + image), not branching by upload kind — simpler invariant, fewer code paths"
metrics:
  duration: "~50 min"
  completed_date: "2026-05-23"
  tasks_completed: 3
  files_modified: 13
  files_created: 0
  tests_added: 19
  tests_total: 219
---

# Phase 4 Plan 04-01: 影像 ingest 垂直切片 Summary

**One-liner:** Phase 4 第一條 vertical slice 完成 — dropzone 同時接受 PDF + PNG/JPG/TIFF,影像在 ingest 階段以 magic-header sniff + Pillow 驗證鏈正規化為 A4 portrait 單頁 PDF,走完既有 Phase 1–3 預覽 / 框選 / 套用 / 下載流程,輸出 `{stem}_logoswap.pdf`,AGPL seam 不破、SHA-256 D-05 不變性更強。

---

## Files Modified

### Backend Python(7 files)

| File | 變動範圍 |
|------|---------|
| `app/services/pdf_engine.py` | +常數 `A4_WIDTH_PT`、`A4_HEIGHT_PT`;+函式 `image_to_a4_pdf(image_bytes) -> bytes`(唯一新 fitz 呼叫;`new_page` + `insert_image(keep_proportion=True)`)|
| `app/services/ingest.py` | 完整改寫:四 magic dispatch(`_sniff_kind`)、Pillow 驗證鏈(`_ingest_image`)、PDF 路徑抽出(`_ingest_pdf`)、影像 → A4 PDF 整合(`_ingest_image_to_pdf`)、`ingest_upload` 為 dispatch shell;+ Pillow import(**zero fitz import**)|
| `app/services/pipeline.py` | `process_job` reset source 從 `original_path` 改為 `pristine_path`(line 105 / 110 / 123 / 129 共 4 處);D-05 SHA-256 invariant 對 originals 更強(pipeline 不再 touch)|
| `app/storage.py` | `_KINDS` 擴為 4 個(+`pristine`);新增 `pristine_path` + `write_pristine_copy` + `_PRISTINE_NAME` |
| `app/config.py` | 新增 `MAX_INGEST_IMAGE_PIXELS = 89_478_485`(Pillow default)+ `JPEG_REENCODE_QUALITY = 90` |
| `app/main.py` | `_INGEST_STATUS` 新增 3 條(unsupported_image_format=415、multi_page_tiff_unsupported=415、corrupt_image=422)|
| `app/api/sessions.py` | `_CODE_STATUS` 同步擴張 3 條(test gate `test_ingest_status_dicts_in_sync` 防漂移)|

### Frontend(3 files)

| File | 變動範圍 |
|------|---------|
| `web/index.html` | dropzone 五處字串 + accept 屬性更新(UI-SPEC 04 鎖定文案 byte-exact)|
| `web/js/app.js` | `COPY.unsupportedType` 文案更新;`COPY` 新增 3 個 key(`unsupportedImageFormat` / `multiPageTiffUnsupported` / `corruptImage`);`messageForError` switch 新增 3 個 case |
| `web/js/api.js` | docstring 補上 3 個新 error code(transport 程式碼不動)|

### Tests(3 files)

| File | 變動範圍 |
|------|---------|
| `tests/conftest.py` | 新增 6 個 in-memory image fixture builders(`_build_png` / `_build_jpeg` / `_build_tiff` / `_build_cmyk_tiff`)+ 6 個 pytest fixtures(`png_bytes` / `jpeg_bytes` / `tiff_bytes` / `multipage_tiff_bytes` / `cmyk_tiff_bytes` / `fake_png_bytes`)|
| `tests/test_ingest.py` | +19 個測試(4 個 T-04-01-01 + 9 個 T-04-01-02 + 6 個 T-04-01-03)|
| `tests/test_process_api.py` | +1 個 image+logo placement integration |

---

## Key Decisions Implemented

1. **D-01 A4 portrait + fit + center + 白底**(`image_to_a4_pdf` 用 `keep_proportion=True`,沿用 Phase 3 `place_logo` 的同一參數,fit/center 語意已驗證,本 plan 不重新測)。
2. **D-02 多頁 TIFF 結構化 4xx 拒絕**(`getattr(img, "n_frames", 1) > 1` → `multi_page_tiff_unsupported` 415,繁中文案「暫不支援多頁 TIFF,請先拆成單頁 TIFF 再上傳。」)。
3. **D-03 CMYK→RGB / RGBA→RGB**(Pillow `convert("RGB")`,Pitfall D 黑框防護 + Pitfall G 透明 PNG 防護;`test_cmyk_tiff_normalized_to_rgb` 證實 CMYK 上傳不 crash 且產出有效 PDF)。
4. **D-04 沿用 50 MB / 30 頁上限**(影像不新增獨立檻;`MAX_INGEST_IMAGE_PIXELS` 只是 Pillow decompression-bomb 防護顯式化,非新檻)。
5. **D-07 UI 不揭露分類**(grep `web/` 對 `raster|vector|scan|點陣|向量|掃描` = 0 hits)。
6. **D-11 單一 dropzone + accept 8 token + 五處字串**(UI-SPEC 04 Copywriting Contract 表逐字落地)。
7. **D-12 四 magic sniff:image 強制 `startswith` offset 0、PDF 容許 ≤8 leading offset**(`test_sniff_kind_pdf_tolerates_leading_offset_but_images_do_not` 證實)。
8. **D-13 輸出檔名 `{stem}_logoswap.pdf`**(沿用 Phase 2 `_logoswap_name`,本 plan 無變動;`test_image_upload_download_filename_uses_stem` 證實 `scan.png → scan_logoswap.pdf`)。
9. **AGPL seam invariant**(`import fitz` / `import pymupdf` 只在 `app/services/pdf_engine.py`;`grep -l "import fitz" app/` 結果 = 1 個檔)。

### 新拍板:Planner「雙寫 pristine_pdf」實作

PATTERNS.md 標出的 deferred-mutation 衝突(image 上傳的 originals/ 是 PNG bytes,但 pipeline 既有 reset-from-original 需要 PDF)由本 plan 解決:

- **三目錄 invariant 重新定義**:
  - `originals/{sid}/source.pdf` = 使用者上傳的真實 bytes(PDF 或 PNG/JPG/TIFF);**SHA-256 不變**(D-05 對使用者輸入更強)。
  - `work/{sid}/doc.pdf` = 編輯中的 A4 PDF(影像路徑為正規化結果,PDF 路徑為原 bytes)。
  - `pristine/{sid}/doc.pdf` = pipeline reset source(永遠是 PDF;PDF 路徑下與 originals 同 bytes,影像路徑下與 work 同 bytes)。
- **pipeline.process_job 改為從 pristine 而非 original copy**(line 105 / 110 / 123 / 129 共 4 處)。對 PDF 上傳行為不變(SHA-256 D-05 既有測試全 pass);對影像上傳新解除「originals 不是 PDF 無法開」的潛在 crash。

---

## 新增測試列表(19 個)

### T-04-01-01(4 個,單元層)
- `test_image_to_a4_pdf_produces_single_a4_page` — page_count == 1, page.rect.w/h == 595/842
- `test_image_to_a4_pdf_jpeg_passthrough_is_compact` — JPEG 直通,小檔不膨脹(< 200KB sanity)
- `test_storage_pristine_directory_exists_after_new_session` — `pristine/` 目錄與 `originals/` `work/` `outputs/` 一起建
- `test_storage_write_pristine_copy_writes_bytes_and_distinct_path` — 三路徑互異 + bytes 正確寫入

### T-04-01-02(9 個,單元 + API 整合)
- `test_sniff_kind_dispatches_four_magics` — PDF / PNG / JPEG / TIFF LE / TIFF BE / 隨機 bytes
- `test_sniff_kind_pdf_tolerates_leading_offset_but_images_do_not` — PDF + BOM = pdf,PNG + BOM = None,PDF offset>8 = None
- `test_extension_not_trusted_fake_png` — `evil.png` 但內容是隨機 bytes → 415 unsupported_type(D-12)
- `test_empty_file_message_mentions_image` — 空檔案訊息含「影像」字眼(文案更新)
- `test_corrupt_image_truncated_png` — PNG magic + garbage → 422 corrupt_image
- `test_multi_page_tiff_rejected` — 3-page TIFF → 415 multi_page_tiff_unsupported,訊息含「多頁 TIFF」
- `test_ingest_status_dicts_in_sync` — main._INGEST_STATUS 與 api.sessions._CODE_STATUS 兩 dict keys / values 完全對齊;三個新 code 都有正確 status
- `test_pipeline_resets_work_from_pristine_not_originals` — 刪掉 originals/ 後 /process 仍能成功(證實 reset source 已切換)
- (Phase 1 既有測試全部繼續 pass)

### T-04-01-03(6 個,端到端 + UI)
- `test_png_upload_normalizes_to_a4_pdf` — PNG → 201、page_count=1、filename=scan.png、work 為 PDF、原 PNG bytes 在 originals/、/pages/0/image 回 PNG
- `test_jpeg_upload_normalizes_to_a4_pdf` — JPEG 同上
- `test_tiff_upload_normalizes_to_a4_pdf` — TIFF 同上
- `test_cmyk_tiff_normalized_to_rgb` — CMYK TIFF → 201,產出有效 1-page PDF(D-03 sanity)
- `test_originals_sha256_unchanged_after_image_run` — 影像 + /process 一輪後,原 PNG SHA-256 不變(D-05 對 image 路徑)
- `test_image_upload_download_filename_uses_stem` — `scan.png` → 下載 Content-Disposition 含 `scan_logoswap.pdf`(D-13)
- `test_png_upload_with_logo_placement`(在 `tests/test_process_api.py`)— image + logo 走完 logo placement 路徑(Phase 4 success criteria #3 部分覆蓋)

---

## Test Results

```
.venv/Scripts/python.exe -m pytest tests/ -q
...
219 passed in 6.65s
```

**Baseline 200 → 本 plan 後 219(+19 新測試,既有 200 全 pass 零迴歸)**。
TDD gate compliance:每個任務都先 commit failing tests(`test(04-01)`,RED)再 commit GREEN(`feat(04-01)`)— git log 可驗證 RED → GREEN 順序。

---

## Pipeline.process_job 契約變化(下游 04-02 必讀)

| 行 | 既有 | 新 | 影響 |
|----|------|----|------|
| 105 | `original = storage.original_path(sid)` | `pristine = storage.pristine_path(sid)` | 重命名;reset source 切換 |
| 110 | `if Path(work) == Path(original)` | `if Path(work) == Path(pristine)` | invariant 對 pristine 而非 original |
| 123 | `if not Path(original).is_file()` | `if not Path(pristine).is_file()` | 不再依賴 originals/ 為 PDF |
| 124 | 訊息「找不到原始檔」 | 訊息「找不到初始 PDF 副本」 | 對使用者表達內部狀態的描述更精確 |
| 129 | `shutil.copyfile(original, work)` | `shutil.copyfile(pristine, work)` | reset source 真實切換 |

**對 PDF 上傳的影響:** zero — PDF 在 ingest 寫 originals 的同時也寫 pristine(同 bytes),pipeline 從 pristine reset 與從 original reset 結果 byte-identical。既有 Phase 1–3 SHA-256 / pipeline 測試全部 pass。

**對 image 上傳的影響:** 結構性必要 — originals/ 為 PNG/JPG/TIFF bytes,若 pipeline 仍從 originals reset 則 `pdf_engine.open_pdf(原始 PNG bytes)` 會 raise `PdfEngineError`,導致 /process 在 image 路徑全 crash。

---

## Hand-off to Plan 04-02

本 plan 完成後,04-02 開始時可直接使用的基礎設施:

1. **`pdf_engine.image_to_a4_pdf`** — 已就位(本 plan 用於 ingest 正規化;04-02 可能不需直接用)。
2. **`storage.pristine_path` / `write_pristine_copy`** — 已就位(pipeline 已從 pristine reset)。
3. **Ingest dispatch** — PNG/JPEG/TIFF 上傳全走 image → A4 PDF 路徑;04-02 不需動 ingest。
4. **UI(dropzone + accept + 三新錯誤碼)** — 已就位;04-02 對 UI 完全零變動。
5. **`pdf_engine.IMAGE_NONE` 常數** — 已有(Phase 2 已 export);04-02 需新增 `IMAGE_PIXELS = fitz.PDF_REDACT_IMAGE_PIXELS`。

04-02 仍需要實作的清單:

- [ ] `pdf_engine.IMAGE_PIXELS` 常數匯出(line ~232 既有 IMAGE_NONE 旁邊)
- [ ] `pdf_engine.rect_overlaps_image(page, rect) -> bool` 新 helper(查每框是否與 image XObject 重疊)
- [ ] `redact.remove_region_vector` / `redact.remove_region_raster` 拆分,或 `remove_region` 內部依 overlap 分流
- [ ] `pipeline.process_job` 每框先呼叫 `pdf_engine.rect_overlaps_image` 再 dispatch
- [ ] raster 分支殘留斷言改用「除了 redact 自己的 fill drawing 外無 drawing」過濾,text 殘留斷言保留(D-09)
- [ ] 加 raster 分支整合測試(image-only PDF 框選整張 → 整張變白底)
- [ ] (sub-task)pdf_engine `save_doc` 已有 garbage=4 deflate=True clean=True,D-10 部分已完成

## Deferred Items / 04-02 邊角需審視

| 項目 | 為何 04-01 不做 | 04-02 何時審視 |
|------|---------------|--------------|
| CMYK colorspace 深度檢查(產出 PDF image 是否真為 RGB / ICCBased)| 本 plan sanity bar 只要求「不 crash + 產出有效 PDF」,深度 colorspace 檢查需要進入 pdf_engine 讀 `page.get_images()` 與 colorspace,屬 04-02 領域 | raster 分支若 IMAGE_PIXELS 結果有色偏,需重新審視 ingest 階段是否真已轉成 sRGB 而非保留 CMYK profile |
| EXIF orientation 自動轉正 | Phase 4 deferred(CONTEXT)— 04-01 對倒置影像不處理,使用者用整份 90° 旋轉 | UAT 若有抱怨倒置可在 04-02 或之後加 |
| 多頁 TIFF 展開成多頁 PDF | 本 plan 拒絕為主;若需求出現屬 v1.x | UAT 若回報屬 v1.x |
| `fill=None` vs `fill=(1,1,1)` 的 raster 分支選擇(D-09 內 raster 分支)| 04-01 不做 redact 分支變更 | **04-02 核心**:raster 分支需要 `fill=(1,1,1)` 配合 IMAGE_PIXELS 才能讓使用者看到「框內變白」;殘留斷言過濾需配套 |

---

## Self-Check

**Files created/modified check:**

- `app/services/pdf_engine.py`: FOUND (modified)
- `app/services/ingest.py`: FOUND (modified)
- `app/services/pipeline.py`: FOUND (modified)
- `app/storage.py`: FOUND (modified)
- `app/config.py`: FOUND (modified)
- `app/main.py`: FOUND (modified)
- `app/api/sessions.py`: FOUND (modified)
- `web/index.html`: FOUND (modified)
- `web/js/app.js`: FOUND (modified)
- `web/js/api.js`: FOUND (modified)
- `tests/conftest.py`: FOUND (modified)
- `tests/test_ingest.py`: FOUND (modified)
- `tests/test_process_api.py`: FOUND (modified)
- `.planning/phases/04-raster-image-support/04-01-SUMMARY.md`: FOUND (this file)

**Commit hashes check:**

- `d0c24f6` test RED 01: FOUND
- `d9bd133` feat GREEN 01: FOUND
- `c6a7d85` test RED 02: FOUND
- `573c430` feat GREEN 02: FOUND
- `ddefbb9` feat GREEN 03: FOUND

**Verification gate check:**

- `pytest tests/ -q` → 219 passed
- `grep -l "import fitz" app/` → only `app/services/pdf_engine.py` (1 file)
- `grep -c "image/png" web/index.html` → 1 (in accept)
- `grep -c "上傳 PDF 或影像以開始" web/index.html` → 1 (heading)
- `grep -c "支援 PDF 檔(單一檔案)" web/index.html` → 0 (old purged)
- `grep -c "選擇 PDF 檔案" web/` → 0 (old purged)
- `grep "raster\|vector\|scan\|點陣\|向量\|掃描" web/` → 0 hits (D-07 honored)

## Self-Check: PASSED
