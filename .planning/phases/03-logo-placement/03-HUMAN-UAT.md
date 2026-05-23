---
status: resolved
phase: 03-logo-placement
source: [03-VERIFICATION.md]
started: 2026-05-22
updated: 2026-05-23
---

## Current Test

[complete]

## Tests

### 1. 側欄縮圖網格在淺色/深色主題下正確渲染
expected: logo 選擇器以縮圖網格顯示於側欄,淺色與深色主題下版面、間距、文字皆正確(沿用既有 token)
result: passed (含後續 hotfix:深色模式下 logo 縮圖白色襯底,使深色文字 logo 清楚可辨)

### 2. 選取狀態的 accent ring
expected: 點選縮圖時出現 accent ring 標示;取消選取時 ring 消失;同一時間僅一個被選取
result: passed (含預設選「自動(依框選形狀)」的調整)

### 3. 結果標籤條件式切換
expected: 有選 logo 時對照標籤顯示「移除+置入結果」;未選 logo 時顯示「移除結果」
result: superseded — 原圖/移除結果切換鈕已於 UAT 期間移除(視圖自動切換);標籤本身改成狀態文字「已套用變更,可以恢復原圖或是下載變更後檔案。」

### 4. logo 置入位置與長寬比
expected: logo 在移除區域內置中、維持長寬比、完整顯示;前後對照預覽與下載的 PDF 中位置/大小一致且正確
result: passed (含 hotfix `0a4f039`:旋轉頁面時 logo 隨頁面方向正立)

### 5. 更換 logo 觸發 stale 機制
expected: 變更 logo 選取會使既有結果失效,顯示正確的繁中「需重新套用」提示
result: passed (含 WR-01 修正:logo 變更時 clearAllBtn 隱藏狀態同步)

### 6. 重新套用取得最新 after-image(WR-01 快取破除)
expected: 「重新套用」後預覽抓取的是最新結果影像(?v= 參數不同),不會顯示舊的快取影像
result: passed (`?v=` 快取破除參數逐次遞增已驗證)

## Summary

total: 6
passed: 5
issues: 0
pending: 0
skipped: 1
blocked: 0

備註:第 3 項因 UAT 期間移除「原圖/移除結果」切換鈕,標籤改以狀態文字呈現,標記為 skipped (superseded by UAT decision)。其餘 5 項皆於 UAT 對話中由使用者逐項確認通過,並補做了多項 hotfix(整頁顯示縮放、灰字對比、更換檔案、自動選標、90° 旋轉作用整份文件、套用後鎖定 + 恢復原圖、原圖渲染修正等)。

## Gaps

無未處理項目。所有 UAT 期間發現的問題均已 fix 並通過 code review(REVIEW-uat.md 5 個 warning 全部修正)。
