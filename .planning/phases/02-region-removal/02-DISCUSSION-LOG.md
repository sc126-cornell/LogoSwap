# Phase 2: 框選與真正移除(向量)+ 下載 — Discussion Log

**Date:** 2026-05-22
**Mode:** discuss --chain (interactive)

> Human-reference audit only. Canonical decisions live in `02-CONTEXT.md`.

## Areas discussed (all four selected)

### 框選互動 (Region drawing UX)
- Options: 畫+刪+清除(建議) / 再加控制點調整 / 只畫+清除全部
- Selected: **畫+刪+清除**(允許重疊,不做 handles)。

### 移除範圍 (What gets removed)
- Options: 全部移除(建議) / 每區可選(文字/向量)
- Selected: **全部移除**(框內文字+向量;per-region 控制列為 v1.x)。

### 前後對照 (Before/after preview)
- Options: 切換鈕(建議) / 滑桿 / 並排
- Selected: **切換鈕**(原圖↔結果,單頁 page-stage 內切換)。

### 輸出方式 (Output)
- Options: 原名+後綴、保留全部頁(建議) / 只輸出修改頁 / 每次自訂檔名
- Selected: **原名+`_logoswap`、保留全部頁**,下載前可預覽確認。

## Cross-cutting
- 採「延後改檔」:框選先存前端,redaction 只在結果預覽/匯出時於後端對 work 副本執行,原始檔不變。
- 座標對應為技術核心(研究/規劃處理),不在討論範圍。

## Deferred ideas
- per-region 移除模式、控制點調整、滑桿/並排對照、只輸出修改頁/自訂檔名。

---
*Phase: 2-region-removal*
*Logged: 2026-05-22*
