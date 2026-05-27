# Phase 1: 輸入與預覽骨幹 - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

上傳單一向量 PDF → 伺服器以 PyMuPDF 渲染頁面 → 瀏覽器多頁預覽(導航 + 縮放),原始檔完整保留(三目錄分離)。本階段只做上傳與預覽,不含框選/移除/置入(後續階段)。
</domain>

<decisions>
## Implementation Decisions

### 頁面瀏覽方式 (Page browsing)
- **D-01:** 一次顯示一頁 + 導航(上一頁/下一頁、跳頁、頁碼指示),**非**連續捲動。理由:最簡單、渲染最省,且與 Phase 2「每頁框選」一致。

### 預覽渲染與縮放 (Render & zoom)
- **D-02:** 伺服器以高 DPI 渲染預覽,**預設 200 DPI**(適合 CAD 細線清晰度)。縮放採 **CSS 放大**現有 PNG,不在縮放時重新向伺服器要圖。
- **D-03:** 後端渲染端點須在回應明確帶出「實際渲染 DPI + 頁面 metadata(旋轉、頁面點數尺寸、像素尺寸)」,供 Phase 2 座標對應使用。縮放策略不影響座標對應(以實際渲染 DPI 為準)。

### 上傳限制 (Upload limits)
- **D-04:** 檔案大小上限 **50MB**,頁數上限 **30 頁**。超過以結構化 4xx 拒絕(對應 UI-SPEC「檔案過大」文案,訊息帶出上限值)。此為威脅模型 DoS 緩解的具體參數(MAX_UPLOAD_BYTES、MAX_PAGES)。

### 品牌外觀與主題 (Brand & theming)
- **D-05:** 整體風格:**專業、簡約**。
- **D-06:** 提供 **淺色 / 深色(light/dark)模式切換**。**此更新了 UI-SPEC 原本「Phase 1 僅淺色、dark mode 延後」的決定** —— 主題系統於 Phase 1 即建立雙主題。切換鈕置於工具列;初次依 `prefers-color-scheme`,使用者選擇以 localStorage 記住。視為既有 UI 外觀的實作決策,非新功能。
- **D-07:** 淺色模式強調色沿用 **`#2563EB`(專業藍)**;深色模式強調色用 **琥珀色 `#F59E0B`(amber-500,可調)**。強調色仍只保留給「主要動作 + 目前頁碼指示」(沿用 UI-SPEC 60/30/10 與 reserved-for 規則)。token 以 CSS 變數實作雙主題(`:root` 淺色 + `[data-theme="dark"]` 覆寫,或 `prefers-color-scheme` + 覆寫)。

### Claude's Discretion
- 深色模式的面板/表面色階(surface/panel 深色 hex)、切換鈕圖示與確切位置、200 DPI 的記憶體/像素預算上限保護(可加 DPI 或 max-pixel 上限),交由規劃/執行決定;維持專業簡約並遵守 UI-SPEC token 規則即可。
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design contract
- `.planning/phases/01-input-preview/01-UI-SPEC.md` — UI 設計合約(token、版面、繁中文案、狀態)。**注意:本 CONTEXT 的 D-06/D-07 更新其「僅淺色」為雙主題(淺色藍 / 深色琥珀)+ 切換鈕。** UI-SPEC 色彩/Defaults 段落已同步更新。

### Project research
- `.planning/research/SUMMARY.md` — 鎖定的技術棧與架構(伺服器端 PNG 渲染、三目錄保留、座標 seam、AGPL 隔離)
- `.planning/research/STACK.md` — 版本與函式庫
- `.planning/research/ARCHITECTURE.md` — 元件、build order、座標對應
- `.planning/research/PITFALLS.md` — 領域陷阱(redaction 真正移除、座標、檔案保留)

### Existing phase plans (to be revised to incorporate this CONTEXT)
- `.planning/phases/01-input-preview/01-01-PLAN.md`、`01-02-PLAN.md`、`SKELETON.md`
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- 尚無程式碼(greenfield)。Phase 1 即建立後端與前端骨架。

### Established Patterns
- UI-SPEC 已定義 CSS 變數 token 系統、page-stage(relative 定位,供 Phase 2 overlay)、API-first seam(`web/js/api.js`)。

### Integration Points
- 前端僅透過 `api.js` 與後端 REST 溝通;主題切換為純前端(CSS 變數 + localStorage),不影響後端 API。
</code_context>

<specifics>
## Specific Ideas

- 深色模式以琥珀色(`#F59E0B`)為顯目強調色;整體專業、簡約。
- 預覽清晰度偏向 CAD 細線可辨識(故選高 DPI 200)。
</specifics>

<deferred>
## Deferred Ideas

- 連續捲動式 PDF 檢視、縮圖列導航 — 本階段選「一次一頁 + 導航」,未採用;日後若需要再議。
- 縮放時重新以更高 DPI 渲染(更清晰但較慢)— 本階段用 CSS 縮放;若清晰度不足可於後續優化。

(主題切換視為既有 UI 外觀的實作決策,非新功能,故納入本階段而非延後。)
</deferred>

---

*Phase: 1-輸入與預覽骨幹*
*Context gathered: 2026-05-22*
