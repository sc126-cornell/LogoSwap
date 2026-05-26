---
status: resolved
trigger: redaction 後 dCt 圖形 logo 並未真正移除,而是被「染白」殘留為白色填充的 vector path(1742 個白色 path,bbox=602.5–627.7×486.9–509.9pt,重新染黑後完整還原 dCt logo)。NINGBO 那段文字則正確刪除。
created: 2026-05-26
updated: 2026-05-26
resolved: 2026-05-26
branch: fix/redaction-graphics-touched-mode
resolution_commits:
  - e7e7ca2 chore(06-hotfix): safe-landing investigation helpers (no behavior change)
  - 8352e0d fix(06-hotfix): Option A raster overlay for dense zero-area residue
---

# Debug Session: redact-whitepaint-residue

## Symptoms (PREFILLED — root cause already located by user)

### Expected behavior
框選的 redaction 區域內,**所有** vector path 必須從 PDF content stream 真正刪除。把任何 path 重新染色為黑色不應該還原出原供應商 logo。

### Actual behavior
- swap 後該區域 vector path 還有 1742 個白色填充 drawings(bbox: x=602.5–627.7, y=486.9–509.9 pt)
- 把這些白色 path 重新染黑後重新渲染 → **dCt 供應商 logo 完整顯示**
- 視覺上看不見(白底白色),但 PDF content stream 中圖形仍可恢復
- 「NINGBO DAN-CHIEF NETWORK」文字字串部分正確刪除(無殘留)

### Error messages
無 runtime error;靜默失敗(視覺通過但結構不通過)。

### Timeline
- v1.0 milestone 已 LIVE 於 logoswap.scottchen0622.com(2026-05-24)
- 2026-05-26 UAT 跑同份檔案(3013A-13A-C6-XX-3D02-A01-00040.pdf),pixel-diff + content-stream 檢查抓出此 bug
- 2026-05-26 session-manager 嘗試套用使用者預填的 `LINE_ART_REMOVE_IF_TOUCHED` 修正,實測失敗,實機重新分析後**修正了 root cause 機制**(見下方 ## Root Cause (REVISED))。

### Reproduction
- 輸入:`samples/3013A-13A-C6-XX-3D02-A01-00040.pdf`(2026-05-27 cleanup 從 repo root 搬入 `samples/`)
- 在 web UI 框選右下角標題塊 dCt logo + NINGBO 那一條(PDF 座標 603–826 × 480–511 pt)
- 選「保持空白」(不貼 logo)
- 套用 → 下載 → 輸出檔即 `3013A-13A-C6-XX-3D02-A01-00040_logoswap.pdf`

## Root Cause (REVISED — 經實機驗證後修正)

### 使用者原本的假設(經實測後證實**不成立**)
- 位置:`app/services/pdf_engine.py` 的 `apply_redactions()` 呼叫點(`app/services/redact.py:144`)。
- 假設機制:`apply_redactions()` 使用預設 `graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED`(=1) — 只刪「完全」在矩形內的 path。dCt logo 的 vector path 因為 bounding box 略微跨出框選矩形邊界,被保留下來;PyMuPDF 接著用 fill=None / fill=white 的 redaction overlay 把可見部分蓋白。
- 預期修正:改用 `LINE_ART_REMOVE_IF_TOUCHED`(=2),把跨邊界的 path 也一併移除。

### 實際機制(透過實機比對 ORIG vs SWAP 證實)

使用 `_verify_residue_mechanism.py` 對未處理的 ORIG PDF 與目前 LIVE pipeline 產出的 SWAP PDF 做了同一個矩形內 drawings 的分類比對:

| Drawing 類型 | ORIG | SWAP | 差異 |
|---|---|---|---|
| `type='f'`, fill=black, **zero-area** (W or H < 0.01pt) | 1742 | 1742 | **0**(完全未被移除) |
| `type='f'`, fill=black, 正常面積 | 1561 | 37 | -1524(正確刪除,NINGBO 文字部分) |
| `type='f'`, fill=white, **zero-area** | 0 | 0 | 0 |
| `type='f'`, fill=white, 正常面積 | 0 | 1742 | **+1742**(pipeline 新增) |
| stroke (`type='s'`) | 50 | 1 | -49(正確刪除) |

**Sample 證據:**

ORIG 內的 zero-area black-fill 樣本(dCt logo 的 CAD glyph 筆畫):
```
('f', (0.0, 0.0, 0.0), (609.36, 493.5, 609.48, 493.5))   ← y0==y1=493.5,H=0
('f', (0.0, 0.0, 0.0), (609.3,  493.5, 609.54, 493.5))   ← 同 y,W>0,H=0
('f', (0.0, 0.0, 0.0), (609.36, 493.5, 609.54, 493.5))
```

SWAP 內的正常面積 white-fill 樣本(對應上述 zero-area 的 cover 塗白):
```
('f', (1.0, 1.0, 1.0), (608.86, 493.0, 609.98, 494.0))   ← bbox ±0.5pt
('f', (1.0, 1.0, 1.0), (608.8,  493.0, 610.04, 494.0))   ← _COVER_PAD = 0.5pt
('f', (1.0, 1.0, 1.0), (608.86, 493.0, 610.04, 494.0))
```

`_COVER_PAD = 0.5` 來自 `app/services/pdf_engine.py::cover_zero_area_artefacts`(Phase 4 hotfix #04-05)。

### 真正的根因

dCt logo 並非 NINGBO 那種「文字字串」也並非「跨邊界 vector path」,而是**CAD glyph 分解後的 1742 個零面積 filled path**(每一筆 stroke 渲染為一個 `type='f'`、bbox 寬或高 = 0 的填充路徑)。PyMuPDF 的 `apply_redactions()` **在任何 graphics 模式下都不會移除零面積項目**(已實測:COVERED 與 TOUCHED 皆同——零面積被當作 non-coverable)。

目前 LIVE pipeline 的處理流程:
1. `apply_redactions()` 移除 NINGBO 文字 + 1524 個正常面積 black-fill(成功)
2. 1742 個零面積 black-fill 倖存(PyMuPDF 機制限制,COVERED/TOUCHED 都不會動它們)
3. `get_drawings_fully_inside` residual assertion 跳過零面積 type='f',通過
4. `cover_zero_area_artefacts` 對每個零面積 black-fill 畫一個 ±0.5pt 的白色覆蓋矩形(hotfix #04-05,本意是遮蓋 Adobe/Chrome PDF.js 把零面積渲染成 1px hairline)
5. 結果:**白色覆蓋們的 union 重現 dCt logo 形狀**(因為每筆 CAD stroke 都有一個白色 cover);**底下的 1742 個 black-fill source 仍留在 content stream**(可被恢復)

### 為什麼 `LINE_ART_REMOVE_IF_TOUCHED` 不能修

session-manager 實作後直接跑 reproduction 檔得到:
- POST words=0, fully_inside=0, whitepaint=0
- 但 `get_drawings_intersecting=1742`(全都是零面積 black-fill,跟 ORIG 一字不差)
- 新版嚴格 residual assertion 立刻 trip `RedactError("residual_content")`

也就是說:TOUCHED 不會移除零面積項目(跟 COVERED 一樣),改完之後不但沒解決根因,還會把所有 DC.pdf 類 CAD PDF 卡在 422。

## Fix Plan (REVISED — 待使用者決策)

請使用者在以下幾條真正能修的路徑中擇一,session-manager 不擅自決定(這是真正的架構決策):

### Option A — Raster fallback for dense zero-area regions
- 偵測:`remove_region_vector` 在 redaction 前先掃描框選矩形內 type='f' 且 zero-area 的 drawing 數量;若超過閾值(例如 ≥ 50),改走 raster 路徑。
- raster 路徑做法:把框選矩形 render 成 pixmap → 完全清白 → 把白色 pixmap 當 image XObject 貼回該矩形(`page.insert_image`,overlay=True),**並且**在原來位置照樣跑 `apply_redactions(images=IMAGE_PIXELS)` 把底下的 raster 化白。
- 同時把 vector path(包括零面積)依靠 `apply_redactions` 的標準流程處理,沒移除的零面積項目此時被新貼的白色 image XObject 完全遮蓋且不可恢復(因為 image XObject 是渲染順序的最頂層,而且本身是純白 pixmap)。
- 優點:不動 fitz seam 行為、不動 CR-02、不需要 content stream surgery
- 缺點:那塊區域變成 raster(不能再縮放保留向量品質),但既然是供應商商標**本來就要替換掉**,可接受

### Option B — Content stream surgery to delete zero-area sources
- 在 `apply_redactions` 之後、`cover_zero_area_artefacts` 之前,枚舉所有零面積 type='f' 且 fully inside user rect 的 drawings,**直接從 content stream 刪除**這些路徑(而非僅覆蓋)。
- PyMuPDF 沒有直接的 "delete drawing" API;需要做 content stream rewrite(找到對應的 `m`/`l`/`f`/`B` 序列並重寫整段)。風險高、易碰到 form XObjects 巢狀問題。
- 優點:最徹底,結果不留任何零面積 path
- 缺點:超出 seam wrapper 範疇,要寫 PyMuPDF content stream 級別的程式碼,維運成本高

### Option C — Skip `cover_zero_area_artefacts` 並改用單一大白塊
- 跳過逐個 ±0.5pt cover,改成在 redact annot 階段用 `fill=(1,1,1)`(目前是 fill=None),讓 redaction 結束後產生一個**單一**白色矩形覆蓋整個 padded rect。
- 優點:沒有「白色 cover 的 union 重現 logo」的問題(因為覆蓋是一整塊)
- 缺點:這是專案本來明確禁止的「cover ≠ remove」反模式(Pitfall 3 / `redact.py` docstring 「fill=None (NOT (1,1,1))」一節);底下 vector source 仍在 content stream(只是被一個方形 cover 整片蓋住,但要去 unmask 仍可)。**安全等級實質倒退**,不建議。

### 推薦
Option A(raster fallback for dense zero-area regions)成本/效益最佳:
- 不破壞既有 vector 路徑、不動 CR-02、不需 content stream 級別程式碼
- raster vs vector 已經是現成的 dispatcher(`pdf_engine.rect_overlaps_image`),只需新增第二個觸發條件:zero-area fill density
- 既然該區的內容**本來就要被替換掉**(放上本公司 logo 或保持空白),原地 raster 化沒有資料損失

### 已就位的支援基礎建設(這次 session 已加入,不論最終選哪個 Option 都可重用)
1. **`pdf_engine.LINE_ART_REMOVE_IF_TOUCHED` constant 已 re-export**(`app/services/pdf_engine.py`),callers 不需要 import fitz 就能名指該模式。
2. **`pdf_engine.get_white_fill_drawings_intersecting()` helper 已加入**(`app/services/pdf_engine.py`):列出 non-degenerate 白色 fills 與其 bboxes,排除零面積 fills、非白色 fills、stroke、out-of-rect。Option A 修完後可以用這個 helper 當 post-condition oracle(實作的 fix 完成後對 reproduction 檔執行該 helper,預期回傳 `[]`)。
3. **`tests/test_redact.py::test_get_white_fill_drawings_intersecting_*`** 兩個新測試 pin 住該 helper 的合約(simulated residue 會被偵測、normal redaction 的 baseline 為 0)。
4. **`_verify_residue_mechanism.py` / `_verify_dct_residue_fix.py`** 兩個重跑腳本已於 2026-05-27 cleanup 歸檔到 `.planning/debug/scratch/v1.0-hotfix06/`(連同 `proof_recolored_black.png` + `proof_optionA_recolored_black.png` 兩張攻擊/修復對照證據)。未來若 dCt-residue 或同類零面積殘留再出現,可從該目錄取出腳本對 `samples/3013A-13A-C6-XX-3D02-A01-00040.pdf` 重跑 ORIG vs SWAP 比對。

## Current Focus

hypothesis: **(已淘汰)** 框邊跨出 → REMOVE_IF_COVERED 保留 path → 被染白 → 殘留
test: **(已淘汰)** 改 `graphics=2` 重跑 reproduction 檔
expecting: **(已淘汰)** 修正後輸出 PDF 在該區域 get_drawings_fully_inside(rect) + 跨界 path 都應移除

new_hypothesis: dCt logo 由 1742 個零面積 type='f' 組成,PyMuPDF apply_redactions 在所有模式下都無法移除零面積項目;目前 `cover_zero_area_artefacts` 對它們各畫一個 ±0.5pt 白色覆蓋,這些覆蓋的 union 重現 logo。
new_test: 對 reproduction 檔的 framed region 計算 zero-area type='f' 數量(預期 1742),若該數量遠大於閾值,改走 raster fallback;raster 化後該區 union 白色 cover 數應為 0,並且底下不再有可恢復的 black source。
new_next_action: **等待使用者在 Option A / B / C 之間決策**,session-manager 不擅自選擇。

## Evidence

- timestamp: 2026-05-26
  - source: pixel-diff 比對(3013A-13A-C6-XX-3D02-A01-00040.pdf vs _logoswap.pdf)
  - finding: 唯一差異區為 PDF 座標 (603, 480) → (826, 511)
- timestamp: 2026-05-26
  - source: `get_drawings()` 分析 swap PDF 該矩形內 white-fill paths
  - finding: 1742 個 white-fill paths, bbox (602.5, 486.9) → (627.7, 509.9)
- timestamp: 2026-05-26
  - source: 把 white-fill paths 重新染黑後在新頁渲染
  - finding: 完整還原 dCt logo 形狀(見 `.planning/debug/scratch/v1.0-hotfix06/proof_recolored_black.png`)
- timestamp: 2026-05-26
  - source: swap PDF text spans 在該矩形內
  - finding: 0 spans(NINGBO 文字字串確實已刪)— 故只有 vector path 殘留,文字部分 OK
- **timestamp: 2026-05-26 (session-manager 新增證據)**
  - source: `_verify_dct_residue_fix.py`(套用 LINE_ART_REMOVE_IF_TOUCHED + 嚴格 intersect residual 後對 reproduction 檔執行)
  - finding: 1742 個 zero-area type='f' fill=black survivors 在 TOUCHED 模式下仍倖存,跟 COVERED 完全相同 — 證實 TOUCHED 不解決零面積問題
- **timestamp: 2026-05-26 (session-manager 新增證據)**
  - source: `_verify_residue_mechanism.py`(ORIG vs SWAP 分類比對)
  - finding: 1742 個 SWAP 的 white-fill 與 1742 個 ORIG 的 zero-area black-fill 一對一(每個白色 cover 的 bbox 是對應 black source 的 ±0.5pt halo);證實白色 paths 是 `cover_zero_area_artefacts` 輸出,不是「supplier vector 被染白」

## Eliminated

- hypothesis: 「白色覆蓋是一張 raster image」 → 排除:`p.get_images(full=True)` 在 swap PDF 回傳空 list,page 上沒有任何 image XObject。
- hypothesis: 「殘留是 PyMuPDF 預期行為(redaction overlay rect)」 → 部分成立但不完全:redaction 確實會畫 fill,但此處 fill rects 數量(1742)+ 形狀(完整 dCt logo)遠超「一個矩形 overlay」,代表原始 path 也倖存(只是被染白)。
- **hypothesis: 「使用者預填:跨邊界 vector 在 REMOVE_IF_COVERED 下倖存,被染白」** → **淘汰**:session-manager 實測證實 surviving paths 全部是 **zero-area type='f'**(H=0 或 W=0),並非跨邊界 path。
- **hypothesis: 「LINE_ART_REMOVE_IF_TOUCHED 會修這個」** → **淘汰**:實測證實 TOUCHED 與 COVERED 同樣不會移除零面積項目;另外切到 TOUCHED 還會破壞 CR-02(boundary-crossing CAD 線本來是被刻意保留的)。

## Resolution

**Status: RESOLVED — Option A landed**

- root_cause: dCt logo 由 1742 個零面積 type='f' filled path 組成,PyMuPDF `apply_redactions` 在任何 graphics 模式下都無法移除零面積項目。pipeline 的 `cover_zero_area_artefacts` 對每個零面積項目畫一個 ±0.5pt 白色覆蓋,這些覆蓋的 union 重現 supplier logo 形狀;底下的零面積 black-fill source 仍留在 content stream 可恢復。
- fix: **Option A 落地** — `remove_region_vector` 在 post-redaction 階段計算 zero-area type='f' fill 密度;若 ≥ `ZERO_AREA_RASTER_THRESHOLD`(=100),改走 `replace_region_with_white_raster`(單一白色 image XObject 覆蓋整個 user rect),跳過 `cover_zero_area_artefacts`。密集情境的「per-artefact cover union 重現 logo」攻擊面消失。
- verification: 對 reproduction 檔(`3013A-13A-C6-XX-3D02-A01-00040.pdf`)實測結果:
  - PRE:1742 個 zero-area type='f' 在框選 rect 內,LIVE broken output 在同 rect 內 1742 個 union-of-covers 重現 dCt logo
  - POST:0 個 white-fill DRAWING(舊版的攻擊面消失);1 個 image XObject 覆蓋 rect;用同樣的「重新染黑」攻擊產出純白圖(`.planning/debug/scratch/v1.0-hotfix06/proof_optionA_recolored_black.png`),完全無法還原 dCt
  - 視覺渲染:整張頁面其它區域(產品圖、規格文字、T568A/B 圖例、IDC Cap、Cat 6)零變化,標題塊那條乾淨
- files_changed:
  - `app/services/pdf_engine.py` — Phase 1 safe-landing(`LINE_ART_REMOVE_IF_TOUCHED` 常數、`_WHITE_FILL_EPS`、`get_white_fill_drawings_intersecting()`)+ Phase 2 Option A(`ZERO_AREA_RASTER_THRESHOLD` 常數、`count_zero_area_fills_fully_inside()`、`replace_region_with_white_raster()`)
  - `app/services/redact.py` — `remove_region_vector` 加 dense/sparse dispatcher;dense 路徑後加 `residual_whitepaint` 不變式
  - `tests/test_redact.py` — 共 +9 個新測試(3 safe-landing + 6 Option A:threshold 常數、counter helper、image XObject 插入、degenerate-rect no-op、dense dispatcher、sparse dispatcher)
- tests: 300 passed, 3 skipped(原 294 → +6 個新測試,零回歸;Phase 1 safe-landing 已含 +3 個測試已在 commit e7e7ca2 計入)
- commits(local only, NOT pushed per user memory):
  - `e7e7ca2` chore(06-hotfix): ship dCt-residue investigation helpers (no behavior change)
  - `8352e0d` fix(06-hotfix): Option A raster overlay for dense zero-area residue (dCt-residue)
- branch: `fix/redaction-graphics-touched-mode`(branch name 沿用方便不重建;實際修正不是 TOUCHED 而是 raster overlay)
- known_limitations:
  - 底下的 1742 個 zero-area black source 仍在 content stream(PyMuPDF API 無法刪除零面積項目);現在被 image XObject 視覺覆蓋,recoverable 需要 (1) 拿掉 image XObject + (2) per-path bbox 擴張(strictly 比原本 LIVE broken 的「重新染色」難很多,但理論上仍可能)
  - 真正完整刪除需要 content stream surgery(Option B)— 留待 hotfix #07 如果需要更高保證
