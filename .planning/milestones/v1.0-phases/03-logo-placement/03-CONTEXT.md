# Phase 3: 商標置入 - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

在 Phase 2 已「真正移除」的框選區域內,放上我司商標。建立固定商標庫(`logos/` + `manifest.json`)供瀏覽挑選,選定的 logo 以維持長寬比(`insert_image` `keep_proportion`,LOGO-02)置入移除區域,沿用既有 deferred-mutation 流程(只對 work 副本套用、原始檔永不變)整合進結果預覽與匯出。移除與置入可在同一流程中完成並下載。

**不含(歸其他階段):** 點陣圖/掃描型 PDF 與獨立影像檔的置入(Phase 4)、per-region 不同 logo、移除框與置入框分離、logo 透明度/旋轉/拖曳微調、商標自助上傳 UI。
</domain>

<decisions>
## Implementation Decisions

### Logo 與區域對應 (Logo-to-region mapping)
- **D-01:** 全域單一 logo。套用後,JobSpec 內**所有**移除區域都置入同一個選定的 logo。`JobSpec` 擴充為帶一個**選用的全域 `logo_id`**(`{dpi, regions[], logo_id?}`);未選 logo 時為純移除,維持 Phase 2 行為。不做 per-region 不同 logo(列入 deferred)。理由:符合「移除供應商標 → 在同一位置換我司標」的核心用途,最簡單、契約改動最小。

### 區域內貼合與對齊 (Fit & alignment)
- **D-02:** logo 在每個移除區域框內「置中、完整顯示」(contain):維持長寬比(`keep_proportion`,LOGO-02 鎖定)縮到框內並**置中**,長寬比與框不符處自然留白。對齊採置中,非靠邊。

### 商標庫內容與格式 (Library content & format)
- **D-03:** 格式為 **PNG 去背**(含 alpha 透明)。v1 庫可容納**多個版本**(如水平/直式/深淺),非單一檔。不支援 SVG(`insert_image` 不直接吃 SVG,需先轉點陣 — 列入 deferred)。
- **D-04:** 商標庫 = `logos/` 目錄 + `manifest.json` 描述。manifest 每筆至少帶 `id`、檔名、顯示名(供選擇器顯示),(選用)尺寸/版型標籤。庫為**固定唯讀資產**,由管理者放檔(v1 無上傳 UI)。

### 選擇器 UI 與置入預覽 (Picker UI & preview)
- **D-05:** logo 選擇器為**側欄縮圖網格**,沿用雙主題 token 與繁中文案。
- **D-06:** **結果預覽含 logo**:延伸現有「移除結果」after-image,在後端對 work 副本套用「移除 + logo 置入」後渲染,讓使用者在下載前於「原圖 / 移除+置入結果」對照中就看到 logo 已就定位。

### Claude's Discretion
- 縮圖網格的版面細節、選取狀態樣式、側欄確切位置;`manifest.json` 的精確 schema/欄位;未選 logo 時的行為(預設純移除,download/套用按鈕狀態);更換 logo 或變更選取是否使既有結果失效(沿用 Phase 2「編輯框選使結果失效、需『重新套用』」模式);logo alpha 邊緣的渲染細節;商標庫的種子內容(可先放 placeholder logo)。維持沿用 UI-SPEC token、雙主題與繁中文案。
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — LOGO-01(固定商標庫瀏覽/挑選)、LOGO-02(置入並維持長寬比)

### Project research
- `.planning/research/STACK.md` — PyMuPDF `insert_image`(`keep_proportion`、`stream=`/`filename=`、alpha)API
- `.planning/research/ARCHITECTURE.md` — deferred-mutation、座標對應、AGPL seam(fitz 單一檔)、build order
- `.planning/research/PITFALLS.md` — 座標系陷阱、檔案保留、redaction 真正移除(置入緊接移除之後)
- `.planning/research/SUMMARY.md` — 鎖定棧與架構

### Phase 1–2 artifacts (built — Phase 3 builds on these)
- `app/services/pdf_engine.py` — fitz/AGPL seam;`insert_image` 應放這裡(維持 `import fitz` 單一檔,T-02-03)
- `app/services/pipeline.py` — `process_job` deferred-mutation 流程;移除迴圈每區算出的 `pdf_rect` 即 logo 目標 rect,save 到 work + outputs(整合點)
- `app/services/redact.py` — 移除邏輯(置入緊接其後)
- `app/services/coords.py` — `pixels_to_pdf_rect`、`clamp_px_rect`(logo 目標 rect = 移除用的同一 pdf_rect)
- `app/api/process.py` — `/process`(JobSpec 擴充)、`/result/.../image`(結果預覽含 logo)、`/result`(下載)端點
- `app/models.py` — `JobSpec` / `RegionMark`(擴充 `logo_id` 的契約)
- `app/config.py` — 限制常數(MAX_REGIONS、DPI;可加 logo 庫路徑/允許清單)
- `app/storage.py` — 三目錄隔離;logo 庫為固定唯讀資產(work/outputs 之外)
- `web/js/api.js` — 唯一 server seam(新增 logo 列表 API 呼叫)
- `web/js/regions.js`、`web/js/viewer.js`、`web/js/app.js` — 區域 overlay、page-stage、動作群組(套用/下載);選擇器與「結果含 logo」串接
- `web/index.html` — 版面(側欄選擇器掛載點)
- `.planning/phases/01-input-preview/01-CONTEXT.md`、`01-UI-SPEC.md` — token、雙主題、繁中文案、page-stage 契約
- `.planning/phases/02-region-removal/02-CONTEXT.md` — 框選/移除/前後對照/deferred-mutation 決定(Phase 3 直接沿用)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pipeline.process_job`:移除迴圈每區已算出 `pdf_rect` — 移除後對**同一 rect** 呼叫 `insert_image(..., keep_proportion=True)` 即完成置入,座標正確性直接繼承 Phase 2 已證明的對應骨幹。
- `pdf_engine`:新增 `place_logo(page, rect, logo_path/stream)` 包住 `insert_image`,維持 fitz 單一檔(AGPL seam)。
- `/result/.../image` 結果渲染端點:work 副本套用後即「移除+置入」成品,前後對照幾乎零改動即可顯示含 logo 的結果。
- `api.js` 唯一 server seam;`regions.js` / 動作群組可掛 logo 選擇器與選取狀態。

### Established Patterns
- deferred-mutation(D-05):移除與置入都只在 `/process` 對 work 副本套用,原始檔永不變;每次套用先從 pristine original 重設 work(WR-01)。
- 三目錄:logo 庫為固定唯讀資產(放 work/outputs 之外)。
- 雙主題 token + 繁中文案 + page-stage overlay 沿用。
- 「編輯使結果失效、需重新套用」動作群組(換 logo 同理使結果 stale)。

### Integration Points
- 後端:`JobSpec` 加選用 `logo_id`;`process_job` 移除後對同一 `pdf_rect` 置入 logo;新增 logo 列表 API(讀 `manifest.json`);`pdf_engine` 新增置入函式。
- 前端:側欄縮圖選擇器(新 UI,經 `api.js` 取 logo 列表);選定 `logo_id` 隨 `/process` 送出;結果預覽沿用既有 after-image(現含 logo)。
- 資產:新增 `logos/` 目錄 + `manifest.json`。
</code_context>

<specifics>
## Specific Ideas

- 核心用途:移除供應商商標 → 在**同一位置**換上我司商標,輸出品牌正確的 PDF。
- 置入緊貼移除區域(同一 rect),維持長寬比、置中,讓替換在視覺上自然。
- 下載前即可在前後對照中確認 logo 的位置與大小。
</specifics>

<deferred>
## Deferred Ideas

- per-region 不同 logo / 逐區開關置入 — v1.x。
- 移除框與置入框分開(獨立置入位置)— v1.x。
- SVG 向量 logo 支援(需轉點陣)— 視需求再議。
- logo 透明度/旋轉/拖曳微調、框內對齊切換(靠邊/可調留白/內距)— 目前固定置中 contain。
- 商標上傳 UI(自助新增 logo 到庫)— v1 由管理者放檔。
- 點陣圖/掃描型 PDF 與獨立影像檔的 logo 置入 — Phase 4。

(討論全程在 phase 範圍內,未偏離。)
</deferred>

---

*Phase: 3-logo-placement*
*Context gathered: 2026-05-22*
