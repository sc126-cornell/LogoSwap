---
phase: 04-raster-image-support
plan: 04-02
subsystem: redact + pipeline + pdf_engine
tags:
  - phase-04
  - redact
  - raster
  - image-pixels
  - per-region-dispatch
  - mvp-vertical-slice
  - upload-02
  - remove-02
dependency_graph:
  requires:
    - "04-01: pdf_engine.image_to_a4_pdf + storage.pristine_path + ingest dispatch"
    - "Phase 2: redact.remove_region + apply_redactions seam + coords.pixels_to_pdf_rect"
    - "Phase 3: place_logo + auto-pick + manifest"
  provides:
    - "pdf_engine.IMAGE_PIXELS 常數 export + rect_overlaps_image(page, rect) -> bool wrapper"
    - "redact.remove_region_vector(原 remove_region rename,body 不變)"
    - "redact.remove_region_raster(新 entry,IMAGE_PIXELS + fill=None + 只 text 殘留斷言)"
    - "pipeline.process_job per-region dispatch by rect_overlaps_image(D-05)"
    - "in-memory fixtures:image_only_pdf_bytes / dual_layer_ocr_pdf_bytes / mixed_vector_raster_pdf_bytes"
  affects:
    - "Phase 5 部署:Phase 4 raster 路徑已完整,save_doc(garbage=4) 既有,部署無新風險"
tech_stack:
  added: []
  patterns:
    - "Per-region raster/vector dispatch:pipeline 為 dispatcher,redact 兩 entry 各自 single-purpose"
    - "Raster fill=None + IMAGE_PIXELS(實測推翻 CONTEXT 初步 fill=(1,1,1) 傾向,Pitfall A 防護)"
    - "Raster 殘留斷言只查 text(allowed legitimate drawings;Pitfall 3 雙層 OCR 仍封堵)"
key_files:
  created: []
  modified:
    - "app/services/pdf_engine.py"
    - "app/services/redact.py"
    - "app/services/pipeline.py"
    - "tests/conftest.py"
    - "tests/test_redact.py"
    - "tests/test_process_api.py"
    - "tests/test_ingest.py"
key-decisions:
  - "D-09 raster 分支 fill=None(不是 (1,1,1))— RESEARCH 推翻 CONTEXT 初步傾向,IMAGE_PIXELS 自身已把像素變白,加 fill=(1,1,1) 會留 type='fs' fill drawing 假陽性(Pitfall A)"
  - "D-05 dispatch 機制放在 pipeline.process_job 內(per-region if/else)— 保 redact 模組單一職責,pipeline 已是 dispatcher,不引入新模組"
  - "Rename remove_region → remove_region_vector(body byte-identical),raster 為 sibling — reader 一眼可辨,不靠多型"
  - "Raster 分支殘留斷言只查 text(D-09)— raster 區允許合法 drawing 共存(CAD signature on scan),但 text(Pitfall 3 雙層 OCR leak)必須保留"
  - "T-04-02-02 GREEN commit 同時更新 pipeline.py(Rule 3 fix):rename 不更新 caller 會 break 全 vector PDF test;符合 deviation Rule 3 自動修復 blocker"
requirements-completed:
  - UPLOAD-02
  - REMOVE-02
metrics:
  duration: "~11 min"
  completed_date: "2026-05-23"
  tasks_completed: 3
  files_modified: 7
  files_created: 0
  tests_added: 14
  tests_total: 233
---

# Phase 4 Plan 04-02: Raster 移除分支 + per-region dispatch Summary

**One-liner:** 在 pdf_engine 加 IMAGE_PIXELS 常數 + rect_overlaps_image 探測 wrapper,redact.py 拆 remove_region 為 vector / raster 兩 entry point(raster 用 fill=None + IMAGE_PIXELS + 只查 text 殘留),pipeline.process_job 改為每框先探測 image overlap 再 dispatch — 影像型/掃描型/雙層 OCR PDF 框選後框內 image pixel 真正被抹白,Pitfall 3 雙層 leak 端到端封堵,logo 置入沿用 Phase 3 不動。

## Performance

- **Duration:** ~11 min
- **Started:** 2026-05-23T08:42:57Z
- **Completed:** 2026-05-23T08:53:20Z
- **Tasks:** 3
- **Files modified:** 7
- **Tests added:** 14
- **Tests total:** 233(baseline 219 → +14;既有 zero-regression)

## Accomplishments

- **UPLOAD-02 + REMOVE-02 完整達成:** image-only PDF 上傳 → 框選 → 套用後框內 image xref 真正被自動移除(整框時)/ 像素被抹白(部分框時),`test_image_only_pdf_full_frame_redacts_to_white` 端到端證實。
- **Pitfall 3 雙層 OCR text leak 端到端封堵:** 雙層 OCR PDF(掃描底圖 + OCR 文字層)框選後 `page.get_text("words", clip=rect) == []`,`test_dual_layer_ocr_text_leak_closed_end_to_end` 證實 — Ctrl+A 不能複製出供應商文字。
- **Phase 4 success criteria #3 達成:** 影像型檔案沿用 Phase 3 logo 置入路徑,`test_image_only_pdf_with_logo_placement` 證實 logo 在 raster redact 後依然存在(Pitfall 1 invariant 不變)。
- **04-01 → 04-02 vertical slice 串接:** `test_image_upload_through_to_raster_dispatch` 證實 PNG upload → ingest 正規化為 A4 PDF → /process raster dispatch → 下載 `scan_logoswap.pdf` 一條鏈端到端。
- **Vector PDF 路徑 zero-regression:** `remove_region_vector` body 與 Phase 2 byte-identical,既有 200+ 個 Phase 1–3 + 04-01 測試全 pass。
- **AGPL seam 不破:** `redact.py` / `pipeline.py` 仍不 import fitz,IMAGE_PIXELS 常數 / rect_overlaps_image helper 都經 pdf_engine wrapper 引用。

## Task Commits

每個任務在 RED→GREEN cycle 中各自原子 commit:

1. **T-04-02-01 RED — raster fixtures + IMAGE_PIXELS/rect_overlaps_image tests:** `301858a` (test)
2. **T-04-02-01 GREEN — IMAGE_PIXELS const + rect_overlaps_image wrapper:** `d84eead` (feat)
3. **T-04-02-02 RED — rename callers + raster-branch tests:** `350a483` (test)
4. **T-04-02-02 GREEN — split redact entry points + pipeline dispatch:** `1cc24ee` (feat)
5. **T-04-02-03 — image-only/dual-OCR/PNG-upload e2e + idempotent raster:** `6d73711` (test)

_本 plan TDD gate 完整:每對 (test, feat) commit 前後相連,RED → GREEN 順序可 git log 直接驗證。T-04-02-03 為純 e2e 測試(實作已在 T-04-02-02 GREEN 落地,Rule 3 fix),無新 feat commit 必要。_

## Files Created/Modified

### Backend Python(3 files)

| File | 變動範圍 |
|------|---------|
| `app/services/pdf_engine.py` | +`IMAGE_PIXELS = fitz.PDF_REDACT_IMAGE_PIXELS` 常數 export(line 224);+`rect_overlaps_image(page, rect) -> bool` wrapper(line 337+,page.get_images() + get_image_rects + AABB inclusive overlap);module-level redaction-seam comment 加入 IMAGE_PIXELS 描述 |
| `app/services/redact.py` | rename `remove_region` → `remove_region_vector`(body byte-identical,只更名 + docstring 微調);新增 `remove_region_raster` sibling(fill=None + apply_redactions(images=IMAGE_PIXELS, text=TEXT_REMOVE, graphics=LINE_ART_REMOVE_IF_COVERED) + 只 text 殘留斷言);module docstring 重寫為兩個 entry point 並列 |
| `app/services/pipeline.py` | 第 237 行 `redact.remove_region(page, pdf_rect)` 改為 dispatch:`if pdf_engine.rect_overlaps_image(page, pdf_rect): remove_region_raster else: remove_region_vector`(+5 行 comment);module docstring 加入 D-05 dispatch 說明 |

### Tests(4 files)

| File | 變動範圍 |
|------|---------|
| `tests/conftest.py` | 新增 3 個 in-memory builder + 3 個 pytest fixture:`_build_image_only_pdf` / `_build_dual_layer_ocr_pdf` / `_build_mixed_vector_raster_pdf`(產出 bytes,test harness 沿用 `_build_pdf` 風格直接 import fitz)|
| `tests/test_redact.py` | 既有 4 處 `redact.remove_region(...)` mechanical rename → `redact.remove_region_vector(...)`;+9 個新測試(4 個 T-04-02-01 helper unit + 5 個 T-04-02-02 raster-branch unit/integration)|
| `tests/test_process_api.py` | +4 個 e2e 整合測試:`test_image_only_pdf_full_frame_redacts_to_white` / `test_image_only_pdf_with_logo_placement` / `test_dual_layer_ocr_text_leak_closed_end_to_end` / `test_image_upload_through_to_raster_dispatch` |
| `tests/test_ingest.py` | +1 個整合測試:`test_image_upload_consecutive_processes_idempotent`(PNG 連續兩次 process 大小差 <1KB,reset-from-pristine 在 image+raster 路徑下成立)|

## Decisions Made

1. **D-09 raster 分支 `fill=None`(不是 (1,1,1)):** Plan 文件已鎖,executor 嚴格遵守。RESEARCH 實測證實 `fill=(1,1,1)` 會留下 `type='fs'`、`fill=(1,1,1)`、rect == redact_rect 的 fill drawing,擊穿 vector branch 的 `get_drawings_fully_inside` 假陽性檢查。IMAGE_PIXELS 自身已抹白像素,annot fill 不需也不該。
2. **Dispatch 放在 pipeline.process_job(D-05):** redact 模組保持「兩個 single-purpose entry point」,不知道 dispatch 條件;pipeline 已是 per-region dispatcher,加 1 行 `if pdf_engine.rect_overlaps_image(...)` 即可。未來若改為 client-controlled mode(per-region 不同 image-redact 模式,v1.x deferred)只需在此處加 hint 解析。
3. **Rename + sibling(非多型):** `remove_region` rename 為 `remove_region_vector`,新 `remove_region_raster` 為 sibling;reader 看 pipeline dispatch 一眼可辨。若改為多型(`remove_region(page, rect, mode)`),殘留斷言差異會被內部 if/else 隱藏,測試也需傳 mode 參數。
4. **Raster 分支殘留斷言只查 text:** D-09 設計選擇 — raster 區允許合法 drawing 共存(scan 上的 CAD signature、annotation),但 text(Pitfall 3 雙層 OCR leak)是供應商內容洩漏風險,必須斷言。`test_raster_fill_none_no_drawing_residual` 證實這個設計是必要的(fill=None 才不會 break vector branch 的 fully_inside 斷言)。
5. **T-04-02-02 GREEN commit 同時改 pipeline.py(Rule 3 deviation):** 純 rename `remove_region` → `remove_region_vector` 會立即 break 所有 vector PDF 測試(pipeline.py 第 237 行 `redact.remove_region(...)` 變 AttributeError)。Plan 結構將 pipeline dispatch 列在 T-04-02-03,但實際上 T-04-02-02 GREEN commit 必須同時更新 pipeline 才能讓既有 test 通過,屬 Rule 3 blocking issue 自動修復。T-04-02-03 commit 因此變為純 e2e 測試 commit(沒有新 feat 改動,實作已就位)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] T-04-02-02 GREEN 內含 pipeline.py dispatch 更新**

- **Found during:** Task T-04-02-02(redact.py rename)
- **Issue:** Plan 結構將 `remove_region` → `remove_region_vector` rename 列在 T-04-02-02,將 pipeline dispatch 列在 T-04-02-03。但純執行 rename 後,`pipeline.py:237` 仍呼叫 `redact.remove_region(...)`,執行 `pytest tests/ -q` 8 個既有 vector PDF integration 測試立即 `AttributeError: module 'app.services.redact' has no attribute 'remove_region'`。
- **Fix:** 在 T-04-02-02 GREEN commit 同時把 pipeline.py 第 237 行改為 `rect_overlaps_image` dispatch + if/else 兩分支。這個變動本來就是 T-04-02-03 Step 1 的內容,只是位置前移 — pipeline.py dispatch 與 redact rename 邏輯耦合(rename 沒有反向相容 alias),物理上無法在不同 commit 各自 green。
- **Files modified:** `app/services/pipeline.py`(commit `1cc24ee`)
- **Verification:** T-04-02-02 GREEN 後 `pytest tests/ -q` 228 passed(223 baseline + 5 new raster tests);T-04-02-03 為純 e2e 測試新增,無新 feat commit 必要。
- **Committed in:** `1cc24ee` (T-04-02-02 GREEN 同 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 blocking — pipeline.py 與 redact rename 邏輯耦合,必須同 commit 改動)
**Impact on plan:** 零功能差;只影響 commit 邊界位置,plan 三任務全部完成。T-04-02-03 變為純 e2e 測試 commit(實作已落地),task-commit cadence 仍維持 「per task 1 commit pair」。

## Issues Encountered

無 — plan rules 全部按 RESEARCH / CONTEXT / PLAN 既定設計落地,測試一次跑全綠(除了刻意 RED 階段)。

### 小決策(實作層次的取捨,非 plan 偏離)

1. **`test_raster_dual_layer_ocr_text_residual_empty` rect Y 範圍調整:** plan 範例給 `fitz.Rect(50, 380, 350, 420)`,實測 PyMuPDF `insert_text((100, 400), "SUPPLIER")` 的字基線(baseline)在 y=400,渲染後的 glyph bbox 落在 y≈388–410(11pt 預設字體上探 ~12pt)。executor 微調為 `(50, 388, 400, 412)`,確保 fixture pre-condition `get_text_words_in_rect` 確實能抓到兩個 word,而非因 rect 過寬掃到不存在的位置。e2e 端到端等價版本(`test_dual_layer_ocr_text_leak_closed_end_to_end`)同步調整。
2. **fixture `_build_image_only_pdf` 不依賴 production code:** plan 建議「可改為直接 `import fitz` 構造,planner 建議採此方案」— executor 採用此 safer route,fixture builder 直接用 `fitz.open() + new_page + insert_image`,不呼叫 `app.services.pdf_engine.image_to_a4_pdf`,避免 conftest 與 production code 雙向耦合。

## User Setup Required

無 — Phase 4-02 不引入新的 runtime dependency,不變更 API 契約,不需要設定環境變數或外部服務。

## Next Phase Readiness

### Phase 4 整體達成清單(對應 04-CONTEXT.md 鎖定的所有決定)

| 鎖定決定 | 達成狀態 | 證據 |
|---------|--------|------|
| D-01(影像 A4 fit 置中)| ✅ 04-01 落地 | `image_to_a4_pdf` + `test_image_to_a4_pdf_produces_single_a4_page` |
| D-02(拒多頁 TIFF)| ✅ 04-01 落地 | `test_multi_page_tiff_rejected` |
| D-03(CMYK→RGB)| ✅ 04-01 落地 | `test_cmyk_tiff_normalized_to_rgb` |
| D-04(沿用 50MB / 30 頁上限)| ✅ 04-01 落地 | 既有 config 常數沿用 |
| **D-05(每框獨立 dispatch)** | ✅ **04-02 落地** | `pipeline.py` if/else + `test_rect_overlaps_image_mixed_dispatch` |
| **D-06(雙層 OCR 自然落入 raster)** | ✅ **04-02 落地** | `test_raster_dual_layer_ocr_text_residual_empty` + `test_dual_layer_ocr_text_leak_closed_end_to_end` |
| D-07(UI 不揭露分類)| ✅ 04-01 + 04-02 都不動 UI | `grep -ri "raster\|vector\|scan\|點陣\|向量\|掃描" web/` = 0 hits |
| **D-08(IMAGE_PIXELS 預設,IMAGE_REMOVE 延後)** | ✅ **04-02 落地** | `pdf_engine.IMAGE_PIXELS` 常數 + `remove_region_raster` 用之 |
| **D-09(raster 分支 fill=None)** | ✅ **04-02 落地(RESEARCH 推翻 CONTEXT 初步傾向)** | `remove_region_raster` fill=None + `test_raster_fill_none_no_drawing_residual` |
| D-10(save_doc garbage=4)| ✅ Phase 3 已落地 | `pdf_engine.save_doc` 既有 default,本 plan 無 save 改動 |
| D-11(單一 dropzone)| ✅ 04-01 落地 | `web/index.html` + UI-SPEC 04 |
| D-12(四 magic sniff)| ✅ 04-01 落地 | `_sniff_kind` + `test_sniff_kind_pdf_tolerates_leading_offset_but_images_do_not` |
| D-13(輸出檔名 stem)| ✅ Phase 2 已落地 | `_logoswap_name` + `test_image_upload_through_to_raster_dispatch` (e2e) |

### Phase 5 前置條件

Phase 4 不引入新的 runtime dependency(PyMuPDF / Pillow 都已在 04-01 / Phase 1 落地),不變更 API 契約(`/sessions/{id}/process` JobSpec shape 不動,client 不需任何 Phase 4 改動),不增加新的 trust boundary(僅在 ingest 多 3 個 magic、redact 多一條 raster 分支)。Phase 5(部署 / 穩固化 / Docker / Ubuntu)可立即啟動。

### Hand-off summary

- **vector PDF 路徑 zero-change(byte-identical body):** `remove_region_vector` 與 Phase 2 `remove_region` body 完全一樣;Phase 1–3 + 04-01 共 219 個既有測試全 pass。
- **raster PDF / image-only PDF / 雙層 OCR PDF 路徑 fully functional:** 5 個 raster unit test + 4 個 e2e test + 1 個 idempotent test = 10 個新增測試證實。
- **logo 置入沿用 Phase 3:** 影像型檔案、image-only PDF 都用同一個 `place_logo` + auto-pick + manifest;Phase 3 success criteria 在 image path 自動繼承(`test_image_only_pdf_with_logo_placement` 證實)。
- **AGPL seam 不破:** `grep -rln "^import fitz\|^from fitz" app/` 仍只命中 `app/services/pdf_engine.py` 一個(.tmp 檔忽略,為先前 session 殘留)。

## Self-Check

**Files modified check:**

- `app/services/pdf_engine.py`: FOUND (modified)
- `app/services/redact.py`: FOUND (modified)
- `app/services/pipeline.py`: FOUND (modified)
- `tests/conftest.py`: FOUND (modified)
- `tests/test_redact.py`: FOUND (modified)
- `tests/test_process_api.py`: FOUND (modified)
- `tests/test_ingest.py`: FOUND (modified)
- `.planning/phases/04-raster-image-support/04-02-SUMMARY.md`: FOUND (this file)

**Commit hashes check:**

- `301858a` test RED T-04-02-01: FOUND
- `d84eead` feat GREEN T-04-02-01: FOUND
- `350a483` test RED T-04-02-02: FOUND
- `1cc24ee` feat GREEN T-04-02-02 + pipeline dispatch (Rule 3 fix): FOUND
- `6d73711` test T-04-02-03 e2e: FOUND

**Verification gate check:**

- `pytest tests/ -q` → 233 passed(baseline 219 + 14 新)
- `pytest -k "raster or image_only or dual_layer or image_upload" -q` → 11 passed
- `grep -l "^import fitz\|^from fitz" app/` → `app/services/pdf_engine.py` only(.tmp 檔為先前 session 殘留,不計)
- `grep -c "def remove_region_vector\|def remove_region_raster" app/services/redact.py` → 2
- `grep -cE "def remove_region\b" app/services/redact.py` → 0(舊名已 rename)
- `grep -c "import fitz" app/services/redact.py` → 0
- `grep -c "pdf_engine.IMAGE_PIXELS" app/services/redact.py` → 2(docstring + apply_redactions call)
- `grep -c "pdf_engine.IMAGE_NONE" app/services/redact.py` → 1(vector branch)
- `grep -c "PDF_REDACT_TEXT_NONE" app/services/redact.py` → 0(forbidden mode 永遠不出現)
- `grep -c "pdf_engine.rect_overlaps_image(" app/services/pipeline.py` → 1(dispatch call site)
- `grep -c "redact.remove_region_vector\|redact.remove_region_raster" app/services/pipeline.py` → 2
- `grep -cE "redact\.remove_region\b" app/services/pipeline.py` → 0
- `grep -c "import fitz" app/services/pipeline.py` → 0
- `grep -Eri "raster|vector|scan|點陣|向量|掃描" web/` → 0 hits(D-07 UI 不揭露分類)

## Self-Check: PASSED

---

*Phase: 04-raster-image-support*
*Completed: 2026-05-23*
