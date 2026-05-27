# Phase 2: 框選與真正移除(向量)+ 下載 - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

在預覽頁面上框選一或多個矩形區域(可跨頁),把框內的向量物件與文字「真正移除」(非覆蓋,移除後無法再被選取或抽取),提供移除前後對照確認,再下載新的 PDF。座標對應(瀏覽器像素↔PDF 點,含頁面旋轉與 DPI)是本階段技術核心——先建立並充分測試,再寫移除邏輯。不含 logo 置入(Phase 3)、點陣圖/影像(Phase 4)。
</domain>

<decisions>
## Implementation Decisions

### 框選互動 (Region drawing UX)
- **D-01:** 拖曳畫矩形;可刪除單一區域、可清除全部;**允許區域重疊**。不做控制點(handles)調整——畫錯就刪除重畫,先求穩。
- **D-02:** 框選跨頁(每頁各自的區域清單)。沿用 Phase 1 的 page-stage(`position:relative`)疊上透明 overlay(canvas/div),與頁面影像像素對齊。

### 移除範圍 (What gets removed)
- **D-03:** 框內「全部移除」——文字 + 向量物件一律真正移除(redaction)。不做 per-region 的文字/向量分開選擇(列為 v1.x)。移除後該區域內 `get_text`/`get_drawings` 應為空(驗證斷言)。

### 前後對照 (Before/after preview)
- **D-04:** 以「切換鈕」在「原圖 / 移除結果」之間切換,套用後即時可看(於單頁 page-stage 內切換,不並排、不滑桿)。
- **D-05:** 採「延後改檔」(deferred-mutation):框選與設定先存前端;真正的 redaction 只在「產生結果預覽」與「匯出」時於後端對 work 副本執行,**原始檔永不變**。前後對照的「結果」來自後端對 work 副本套用 redaction 後的渲染。

### 輸出 (Output)
- **D-06:** 輸出檔名 = 原檔名 + `_logoswap` 後綴(例:`drawing.pdf` → `drawing_logoswap.pdf`)。
- **D-07:** 保留全部頁(含未修改頁),輸出為完整 PDF;下載前可在預覽確認結果。

### Claude's Discretion
- 框選矩形的視覺樣式(邊框/半透明填色)、刪除/清除的 UI 位置;redaction 的 ~5pt padding 與 `REMOVE_IF_COVERED` vs `REMOVE_IF_TOUCHED` 選擇(研究建議的技術細節);座標對應模組的實作與測試方式——皆交由研究/規劃/執行決定,維持沿用的 UI-SPEC token 與繁中文案。
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project research (most relevant to this phase)
- `.planning/research/ARCHITECTURE.md` — 座標對應(`derotation_matrix`、DPI scale、top-left 原點)、build order、deferred-mutation
- `.planning/research/PITFALLS.md` — redaction 真正移除(**必須** `apply_redactions` + 移除後抽取斷言)、向量殘留需 padding、座標系陷阱、over/under-removal
- `.planning/research/SUMMARY.md` — 鎖定棧與架構
- `.planning/research/STACK.md` — PyMuPDF redaction API(`add_redact_annot` + `apply_redactions`,flags)

### Phase 1 (built — Phase 2 builds on these)
- `app/services/pdf_engine.py` — fitz/AGPL seam(redaction 應放這裡)
- `app/services/render.py`、`app/api/pages.py` — 渲染 + 六個座標 metadata headers + `/meta`(座標對應的依據)
- `web/js/viewer.js` — page-stage(已預留 overlay);`web/js/api.js` — server seam
- `.planning/phases/01-input-preview/01-CONTEXT.md`、`01-UI-SPEC.md` — Phase 1 決定與 UI 契約(token、雙主題、繁中文案)

(No external specs beyond research + Phase 1 artifacts.)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pdf_engine.py`(fitz 隔離 seam)——redaction 邏輯放這裡,維持 AGPL 邊界。
- `render.py` + `/meta` + 六個座標 headers——提供座標對應所需的實際 DPI、頁面點數尺寸、旋轉、像素尺寸。
- `viewer.js` page-stage(`position:relative`,未 letterbox)——overlay 直接 `position:absolute; inset:0` 疊上。
- `api.js`——新增 redaction/匯出端點的呼叫集中在此。

### Established Patterns
- 三目錄保留(originals 唯讀、work 編輯副本、outputs 結果)——redaction/匯出對 work 副本操作,輸出到 outputs。
- 繁中文案 + 雙主題 token(沿用 Phase 1)。

### Integration Points
- 新增:前端 regions overlay(新檔,如 `web/js/regions.js`)、後端 redaction service + 端點(結果預覽 + 匯出)、座標對應模組(後端集中轉換,如 `app/services/coords.py`)。
</code_context>

<specifics>
## Specific Ideas
- 「乾淨移除」是核心——移除後不可殘留可抽取的文字/向量。
- 延後改檔以支援即時前後對照,且不破壞原始檔。
</specifics>

<deferred>
## Deferred Ideas
- per-region 移除模式(只文字 / 只向量)—— v1.x。
- 控制點調整框選(移動/縮放 handles)—— 目前畫錯重畫;日後可加。
- 滑桿 / 並排對照 —— 目前用切換鈕。
- 只輸出修改頁、下載時自訂檔名 —— 目前保留全部頁 + 固定 `_logoswap` 後綴。
</deferred>

---
*Phase: 2-region-removal*
*Context gathered: 2026-05-22*
