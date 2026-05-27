# Phase 1: 輸入與預覽骨幹 — Discussion Log

**Date:** 2026-05-22
**Mode:** discuss --chain (interactive)

> Human-reference audit only. Canonical decisions live in `01-CONTEXT.md`.
> This discussion happened AFTER plans were created (user: "抱歉我忘記先 discuss") — plans will be revised to incorporate these decisions.

## Areas discussed

### 頁面瀏覽方式 (Page browsing)
- Options presented: 一次一頁+導航(建議) / 連續捲動 / 縮圖列+主檢視
- Selected: **一次一頁 + 導航**
- Note: 與 Phase 2「每頁框選」一致;渲染最省。

### 渲染與縮放 (Render & zoom)
- Options presented: 中 DPI + CSS 縮放(建議) / 高 DPI + CSS 縮放 / 縮放時重新渲染
- Selected: **高 DPI + CSS 縮放** → 定為預設 **200 DPI**。

### 上傳限制 (Upload limits)
- Options presented: 中等 50MB/30頁(建議) / 寬鬆 100MB/80頁 / 保守 20MB/10頁
- Selected: **中等 50MB / 30 頁**。

### 品牌外觀與主題 (Brand & theme)
- Options presented: 沿用預設(建議) / 公司品牌色 / 品牌色+字體
- Selected (with freeform elaboration): 沿用預設 + **專業、簡約**風格 + **新增 light/dark 切換**,**深色模式用琥珀色強調**。
- Outcome: 淺色藍 `#2563EB` / 深色琥珀 `#F59E0B` + 切換鈕(`prefers-color-scheme` 初始、localStorage 記憶)。**UI-SPEC 已同步更新(原「僅淺色」改為雙主題)。**

## Deferred ideas
- 連續捲動式 PDF 檢視、縮圖列導航。
- 縮放時重新以更高 DPI 渲染(更清晰但較慢)。

## Plan impact (for replanning)
- **01-02(前端)**:新增雙主題 CSS 變數 token + light/dark 切換鈕 + localStorage 記憶偏好;縮放採 CSS 放大。
- **01-01(後端)**:render 端點預設 `get_pixmap(dpi=200)`;上傳限制常數 `MAX_UPLOAD_BYTES=50MB`、`MAX_PAGES=30`(驅動「檔案過大」錯誤文案)。
- 單頁 + 導航維持不變(原計畫已如此)。

---
*Phase: 1-輸入與預覽骨幹*
*Logged: 2026-05-22*
