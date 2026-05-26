---
status: all_findings_addressed
hotfix_id: 06-dct-residue
review_depth: standard
reviewed_at: 2026-05-26
addressed_at: 2026-05-26
all_addressed_at: 2026-05-26
files_reviewed: 3
diff_base: f911139..HEAD
commits_reviewed:
  - e7e7ca2 chore(06-hotfix): safe-landing investigation helpers (no behavior change)
  - 8352e0d fix(06-hotfix): Option A raster overlay for dense zero-area residue
  - 20974b9 chore(06-hotfix): mark dCt-residue debug session resolved
  - 00a99e4 fix(06-hotfix): address code-review BL-01 + WR-02 + WR-03 (push-blockers)
  - c90e40e docs(06-hotfix): add security audit report (SECURED 5/5)
  - 0bbeb6d docs(06-hotfix): finish debug session metadata update
findings:
  blocker: 1
  critical: 0
  warning: 7
  info: 5
  total: 13
disposition:
  fixed_in_push_window:
    - BL-01: D-01 contract docstring + test updated to acknowledge raster fallback overlay
    - WR-02: added end-to-end integration test with real synthesized zero-area paths (no monkeypatch)
    - WR-03: redact.py module docstring + dispatcher inline comment now mirror engine LIMITATION
  fixed_post_push:
    - WR-01: ZERO_AREA_RASTER_THRESHOLD moved to app/config.py with LOGOSWAP_ZERO_AREA_RASTER_THRESHOLD env override + logger.info("zero_area_dispatch", ...) telemetry per dispatch decision
    - WR-04: assert pix.colorspace.n == 3 and not pix.alpha defence-in-depth pre-condition pinned in replace_region_with_white_raster
    - WR-05: del pix → pix = None (idiomatic refcount drop) + comment corrected (no GC cycle involved)
    - WR-06: rect-normalization contract section added to replace_region_with_white_raster docstring (accepts inverted-tuple inputs by design, matching fitz semantics and the caller's contract)
    - WR-07: CR-02 interaction section added to replace_region_with_white_raster docstring (acknowledges the visual mask trade-off vs sparse-cover branch)
    - IN-01: boundary tests pinning count == THRESHOLD takes dense branch, count == THRESHOLD - 1 takes sparse branch
    - IN-02: defence test pinning residual_whitepaint RedactError fires when get_white_fill_drawings_intersecting returns non-empty under the dense path
    - IN-03: _WHITE_RASTER_FALLBACK_SIZE_PX module-level constant replaces inline 32
    - IN-04: positive observation, no action required
    - IN-05: replace_region_with_white_raster docstring now cross-references .planning/phases/05-ubuntu/hotfix-06-dct-residue/
---

# Hotfix #06 (dCt-residue) — Code Review

**Reviewed:** 2026-05-26
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Hotfix #06 在 `remove_region_vector` 加 density-dispatched zero-area cleanup:當 ≥100 個 zero-area `type='f'` paths 完全落在 user rect 內倖存於 `apply_redactions` 之後,將原本 per-artefact white-cover 策略換成單一 solid-white image XObject overlay。

正面評估:fitz seam 守住(`redact.py` 沒新 import fitz)、IN-01 共享閾值不變式維持、CR-02 邊界跨越語義透過 fully-inside count 保留、`residual_whitepaint` fail-closed post-condition 防守 dense path。

但有以下 material concerns 應在 push 前處理:

- **BL-01(Blocker)**:前測試 `test_process_without_logo_is_pure_removal` 明寫 D-01 契約「無 logo_id 必無 image」,dense-residue dispatcher 對任何過閾值的 vector job 都插一個 image XObject,即使 caller 沒給 logo。下游若依靠這個契約判斷 image-per-page 數會讀到非預期 1。
- **CR-01(Critical)**:dispatch comment 在 `redact.py` 寫「no per-stroke geometry to leak」,但底下 zero-area BLACK source 仍在 content stream;`replace_region_with_white_raster` 的 docstring 老實揭露這點,但兩段文字一致性需要在 caller side 同步。
- **WR-01(Warning)**:Threshold 100 hardcoded,無 env config 路徑、無 runtime log,production 微調需要 redeploy。
- **WR-02(Warning)**:Dense branch end-to-end 測試只 monkey-patch counter,未在合成 PDF 上實際驗證 zero-area path 偵測 + raster overlay 視覺隱藏 + 重新染色攻擊失效。

## Blocker

### BL-01: Dense-residue path 違反 D-01 「無 logo_id 必無 image」契約

**檔案:** `tests/test_process_api.py:285`(契約 assertion);`app/services/redact.py:191-193`(觸發);`app/services/pdf_engine.py:746-810`(機制)
**檢查清單:** #8(向後相容)

`test_process_api.py:283-285`:
```python
for page_no in range(pdf_engine.page_count(out_doc)):
    page = pdf_engine.get_page(out_doc, page_no)
    assert page.get_images() == [], "no logo_id must mean no embedded image (D-01)"
```

dense branch 在 `remove_region_vector` 對任何過閾值的 vector job 插一個 32×32 image XObject(`replace_region_with_white_raster`),與 `auto_logo` / `logo_bytes` 無關。輸出 PDF 因此即使沒要求 logo 也包含 image XObject,「D-01」契約被悄悄打破。

現況:測試 NOT BREAK,因為標準 `_build_pdf` fixture 沒任何 zero-area fills;但實際 dCt-class 用戶上傳會踩到。下游影響:
1. 使用者下載到「沒要求 logo 卻含 image」的 PDF
2. 任何依靠 image-per-page count 區分「有/無 logo」的 colleague-system integration 會誤判
3. D-01 文件契約失效

**Fix 候選(擇一):**
1. **更新契約**:D-01 改寫為「無 logo_id ⇒ 每個觸發 fallback 的 region 至多一個 raster fallback overlay image,其餘 region 0 image」。更新 `test_process_without_logo_is_pure_removal` 改為斷言「任何 image 必須是 32×32 全白 raster fallback」(透過 `pix.width == 32 and pix.height == 32 and all-white-sample`)。
2. **標記 fallback image**:暴露 getter `is_raster_fallback_image(page, xref)` 讓 caller 區分 logo image 與 fallback overlay。Pipeline 可獨立斷言 `# logos placed == # logo_id'd regions`。
3. **條件 short-circuit**:只在 caller opt-in 或 logo 同時被放置時才呼叫 `replace_region_with_white_raster`。避免契約 silent 改變,但重新引入 dCt 洩漏給 no-logo job。

**推薦:** Option 1 + 補一個 pin 新契約的測試。

## Warnings

### WR-01: Threshold 100 是 magic number,無 runtime config 路徑

**檔案:** `app/services/pdf_engine.py:294`
**檢查清單:** #5

`ZERO_AREA_RASTER_THRESHOLD = 100` 是 module-level 常數。docstring(282-293)用「single-digit to low-tens」DC.pdf 對「hundreds to thousands」dCt 的經驗分離說明,號稱對「5–10x 偏移」robust。但:

1. **無 env override**:供應商檔案落在 50–200 zero-area 中間區的話需要改 code + redeploy 才能解。
2. **無 telemetry**:production dispatcher 觸發時沒 log,SRE 沒法從 log 看出哪個 branch 被選。
3. **無 sentinel test**:沒測試 pin 「DC.pdf-class 必須低於 100」 — 未來 PyMuPDF 更新若 doubled zero-area count per glyph,閾值會 silently flip class。

**Fix:**
1. `app.config` 加 env override:`ZERO_AREA_RASTER_THRESHOLD = int(os.getenv("LOGOSWAP_ZERO_AREA_RASTER_THRESHOLD", "100"))`。
2. `remove_region_vector` 加 `logger.info("zero_area_dispatch", extra={"count": ..., "branch": "raster"|"cover"})`。
3. 加 50- 和 150-zero-area 合成 fixture,pin 兩邊 branch 觸發。

### WR-02: Dense-branch end-to-end 測試僅 monkey-patch,未經合成 PDF 實證

**檔案:** `tests/test_redact.py:625-688`(`test_remove_region_vector_dense_zero_area_routes_to_raster_fallback`)
**檢查清單:** #7

dense branch 透過 `monkeypatch.setattr(redact.pdf_engine, "count_zero_area_fills_fully_inside", _forced_count)` 強制觸發。這證明 **分支邏輯**,但 NOT 證明:
1. 合成 PDF 有 ≥100 zero-area `type='f'` paths 時 `count_zero_area_fills_fully_inside` 真的回傳 ≥100
2. `replace_region_with_white_raster` 真的視覺隱藏那些 zero-area paths
3. 重新染色攻擊在輸出 PDF 上真的失效

唯一證據是 manual repro on `3013A-13A-C6-XX-3D02-A01-00040.pdf`,**該檔不在 test suite 內**(repo root scratch)。

**Fix:** 加一個 integration test,合成 / 引入 sanitized fixture(≥100 真實 zero-area `type='f'` paths),end-to-end 跑 `remove_region_vector`,斷言:
- `page.get_images(full=True)` 恰好 1 個
- `get_white_fill_drawings_intersecting` 回傳 []
- render page 中心像素 ≥ (250, 250, 250)
- 模擬重新染色攻擊(walk content stream 把 `fill (1 1 1) rg` 換成紅色)後該矩形仍渲染為白(image XObject 不透明)

### WR-03: `replace_region_with_white_raster` docstring 老實揭露 limitation,但與 `redact.py` 模組層級「true removal」聲明不一致

**檔案:** `app/services/pdf_engine.py:776-791`(docstring);`app/services/redact.py:163-202`(caller);`app/services/redact.py:1-2`(module-level "true removal")
**檢查清單:** #2(T-02-07 / REMOVE-01)

`redact.py:1` 開頭:
> True-removal redaction — the core value (REMOVE-01, threat T-02-07).

`replace_region_with_white_raster` docstring(776-791)誠實:
> The zero-area BLACK source paths remain in the content stream. They are not deleted — only visually superseded by the image overlay.

兩段技術上可調和(zero-area 渲染 0 pixels,視覺上沒可恢復內容),但 dispatcher comment 在 `remove_region_vector`(175-179)寫「no per-stroke geometry to leak」 — 對 COVERS 為真但對底下 BLACK source NOT 為真。只看 dispatcher comment 的 reader 會誤以為 true removal 發生;讀到 `pdf_engine.py:746` 才看到完整真相。

不對稱風險:image XObject 就是一種 cover(更強的、單一的),但專案 core value 對 dense-residue branch 需要加上 footnote。

**Fix:**
1. 更新 `redact.py:175-185` dispatcher inline comment 鏡射 engine docstring 的 `LIMITATION` 段:明說「zero-area BLACK source 仍在 content stream;此 branch 用不透明 image 覆蓋,真正從 content stream 刪除 zero-area sources 需要 content-stream surgery(Option B / 未來 hotfix #07)」。
2. `redact.py` 模組 docstring 加 `TRUE_REMOVAL_LIMITATION` note 把 dense-residue branch 列為「true removal」claim 的已知例外。
3. 考慮把 `replace_region_with_white_raster` rename 成 `overlay_region_with_white_raster` 讓函式名本身傳達「overlay,not removal」。

### WR-04: `clear_with(255)` 對 RGB pixmap 正確但 implicit

**檔案:** `app/services/pdf_engine.py:799-806`
**檢查清單:** #6

```python
pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32), False)
try:
    pix.clear_with(255)
```

`pix.clear_with(value)` 把每個 byte 設成 `value`。3-byte/pixel RGB → `(255, 255, 255)` 白色。`alpha=False` 無 alpha byte。正確。

但兩個 latent trap:
1. 若未來改 `alpha=True`,`clear_with(255)` 把 alpha byte 也設成 255(完全不透明白) — 偶然仍正確,但 comment 沒提。
2. 若未來改 `fitz.csCMYK`,`clear_with(255)` 產生 `(255,255,255,255) CMYK` = 黑墨。同樣 call,反向顏色。

**Fix:** 加 defence-in-depth assertion:
```python
pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32), False)
assert pix.colorspace.n == 3 and not pix.alpha, "clear_with(255) -> white requires 3-channel non-alpha RGB"
pix.clear_with(255)
```

### WR-05: `del pix` in `finally` 必要但非 idiomatic

**檔案:** `app/services/pdf_engine.py:807-810`
**檢查清單:** #6

`del pix` 只 drop local name binding;CPython refcount=1 立即觸發 `Pixmap.__del__`,但非 CPython runtime 不保證。Comment 寫「without waiting for the next gc cycle」也誤導 — CPython refcounting 對非循環 ref 即時回收,無 gc cycle 介入。

**Fix:**
1. `del pix` → `pix = None`(語義等價,更 idiomatic)
2. 或 PyMuPDF 1.27 若 Pixmap 支援 context manager 改用 `with`
3. 訂正 comment:「drop the C buffer immediately rather than at scope exit」(無 gc reference)

### WR-06: `fitz.Rect.normalize()` 接受 inverted-tuple 的契約不對稱

**檔案:** `app/services/pdf_engine.py:793-798`
**檢查清單:** #6

```python
q = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
q.normalize()
if q.width <= 0 or q.height <= 0:
    return
```

正確,但 `(60, 50, 50, 60)` 這種 inverted 輸入會被 normalize 成 `(50, 50, 60, 60)`,然後 image 被畫在 caller 以為是 empty 的 rect 上。同樣 input 給 `cover_zero_area_artefacts` 會得 zero covers(`_rect_contains` 對 normalized inner vs inverted outer 的 fully-inside check 失敗)。契約不對稱。

現況無害(唯一 caller 是 `remove_region_vector`,接收已 normalized fitz.Rect),但未來 caller 若期待 strict-validation 行為會 surprised。

**Fix:** 兩擇一:
- (a) docstring 加 inline 註記:「we accept inverted-tuple inputs because fitz.Rect.normalize swaps them;若未來 caller 期待 strict-validation,在 normalize 前加 `if rect[0] > rect[2] or rect[1] > rect[3]: return`」
- (b) 直接加 strict-validation guard

### WR-07: Dense branch 對 CR-02 邊界跨越線有 mild visual regression

**檔案:** `app/services/redact.py:190-208`;`app/services/pdf_engine.py:746-810`
**檢查清單:** #3(CR-02 preservation)

dense dispatcher 用 `count_zero_area_fills_fully_inside` 做閾值檢查(正確 — 只算 cover routine 會處理的人口)。但 `replace_region_with_white_raster` 把整個 user rect 不透明 image 覆蓋,**not** 只覆蓋 zero-area 人口。任何透過 CR-02 合法倖存的邊界跨越 CAD line(`LINE_ART_REMOVE_IF_COVERED` 保留)的「rect 內部」段落會被視覺遮蓋。

對照 sparse path:`cover_zero_area_artefacts` 只蓋 fully-inside zero-area fills,邊界跨越 CAD line 視覺保留。

dense path 在 rare case(框選同時含密集 CAD glyph 商標 **AND** 合法 through-line)會降低 UX:through-line 的內部段被白色 image 隱藏。

對 dCt class 可接受(整個 rect 反正要被 logo 替換),但 IS 行為差異,應明說。

**Fix:**
1. `replace_region_with_white_raster` docstring 加 CR-02 互動段:「此 branch 用於整個框選 rect 將被 logo 替換的場景;跨越 rect 的 CAD through-lines 內部段視覺隱藏(資料層保留但 rect 內部不渲染),sparse-cover branch 保留 interior rendering」
2. Pipeline 對「no logo + dense residue + detected boundary-crossing line」case surface warning 給 user
3. (out of scope) Option B(content-stream surgery 刪除 zero-area BLACK sources)也可避免 through-line cover-over

## Info

### IN-01: Threshold 邊界(exactly 100)case 未測試

**檔案:** `app/services/redact.py:191`

`if zero_area_count >= pdf_engine.ZERO_AREA_RASTER_THRESHOLD:` 在 100 觸發 dense branch。docstring 寫「at least this many」契約一致,但 `test_remove_region_vector_dense_zero_area_routes_to_raster_fallback` 用 `THRESHOLD + 50`,sparse 測試用 0。無測試 pin `count == THRESHOLD` 進 dense branch。

**Fix:** 加 boundary test:
```python
def test_remove_region_vector_at_threshold_takes_dense_branch(monkeypatch):
    monkeypatch.setattr(redact.pdf_engine, "count_zero_area_fills_fully_inside",
                        lambda p, r: pdf_engine.ZERO_AREA_RASTER_THRESHOLD)
    # ... assert raster fallback fires
```
配對 `THRESHOLD - 1` → sparse case。

### IN-02: `residual_whitepaint` RedactError code 有但無測試

**檔案:** `app/services/redact.py:203-208`

fail-closed guard 健全,但實務上 unreachable(dense branch 刻意不呼叫 `cover_zero_area_artefacts`,本函式 call 不會留下 white-fill drawings)。Defensive 但無測試 capture 意圖不變式。

**Fix:** 加 defence-test(monkeypatch `get_white_fill_drawings_intersecting` 注入假 white-fill drawing 觸發 raise)。

### IN-03: Pixmap 32×32 magic number

**檔案:** `app/services/pdf_engine.py:803`

inline `fitz.IRect(0, 0, 32, 32)`,docstring 在 763-768 解釋選 32 的理由,但 constant 沒命名。

**Fix:** Promote 成 `_WHITE_RASTER_FALLBACK_SIZE_PX = 32` module-level constant。

### IN-04: 樣式正面評論

**檔案:** Throughout
hotfix 沿用既有 docstring + inline-comment convention(terse leading sentence, multi-paragraph context, IN-01 / CR-02 / Pitfall N 顯式引用)。無風格回歸。

### IN-05: docstring 可加 hotfix-06 planning doc 路徑連結

**檔案:** `app/services/pdf_engine.py:749`

docstring 引用「hotfix #06」by name not by path。其他地方專案 convention 是 cite planning docs by path。

**Fix:** docstring 加:
```
See: .planning/phases/05-ubuntu/hotfix-06-dct-residue/ for the dispatch
threshold derivation and the recovery-step analysis.
```

## Invariants Verified (positive findings)

通過的不變式:

1. **fitz seam(T-02-03)**:`redact.py` 不 import fitz;all 引擎存取走 `pdf_engine.*`。新 helpers `count_zero_area_fills_fully_inside` + `replace_region_with_white_raster` 都在 seam 內。既有 `test_fitz_import_confined_to_engine_seam` AST-level 測試會繼續綠燈。
2. **IN-01(共享 `_DEGENERATE_BBOX_EPS`)**:`get_drawings_fully_inside`(line 564)、`cover_zero_area_artefacts`(line 678)、新 `count_zero_area_fills_fully_inside`(line 738)、新 `get_white_fill_drawings_intersecting`(line 628)都用 module-level 常數 0.01。無 drift。
3. **CR-02 contract in counter**:`count_zero_area_fills_fully_inside` 用 `_rect_contains`(fully-inside),正確對齊 `cover_zero_area_artefacts` 的人口,dispatch 算到的 count 等於 cover-population count。邊界跨越 CAD line 不污染 threshold。
4. **`apply_redactions` ordering**:dispatcher 跑在 `apply_redactions` 與 residual assertion 之後 — 兩條 branch 都看 post-redaction state,都不會 trip residual check。
5. **Logo z-order**:`pipeline.process_job` 在 `remove_region_vector` 之後呼叫 `place_logo`,`place_logo` 用 `overlay=True`。32×32 白色 image 先插入(在 `remove_region_vector` 內),logo 後插入(在 pipeline) — logo 落在白色 image 之上。無 LOGO-02 z-order 回歸。
6. **Sparse-path 保留**:count 低於閾值時,`remove_region_vector` 仍呼叫 `cover_zero_area_artefacts` 未變 — DC.pdf hairline-suppression path intact(`test_cover_zero_area_artefacts_paints_white_over_filtered_residues` + `test_cover_zero_area_artefacts_skips_strokes_and_out_of_rect_fills` 兩個既有測試繼續 pin 行為)。

## Files Reviewed

- `app/services/pdf_engine.py`(常數 220-294;white-fill helper 572-632;cover/counter/raster routines 635-810)
- `app/services/redact.py`(89-216 `remove_region_vector` 含新 dispatch)
- `tests/test_redact.py`(hotfix #05/#06 測試 191-732,結構驗收 1077-1101)

## Severity Counts

| 等級 | 數量 |
|---|---:|
| BLOCKER | 1(BL-01) |
| CRITICAL | 0 |
| WARNING | 7(WR-01..07) |
| INFO | 5(IN-01..05) |
| **TOTAL** | **13** |

## Status

`issues_found` — 一個 blocker(BL-01)影響 D-01 文件契約。建議路徑:更新測試契約或 tag raster fallback overlay 後再 push 上 LIVE。
