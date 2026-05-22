---
status: partial
phase: 03-logo-placement
source: [03-VERIFICATION.md]
started: 2026-05-22
updated: 2026-05-22
---

## Current Test

[awaiting human testing]

## Tests

### 1. 側欄縮圖網格在淺色/深色主題下正確渲染
expected: logo 選擇器以縮圖網格顯示於側欄,淺色與深色主題下版面、間距、文字皆正確(沿用既有 token)
result: [pending]

### 2. 選取狀態的 accent ring
expected: 點選縮圖時出現 accent ring 標示;取消選取時 ring 消失;同一時間僅一個被選取
result: [pending]

### 3. 結果標籤條件式切換
expected: 有選 logo 時對照標籤顯示「移除+置入結果」;未選 logo 時顯示「移除結果」
result: [pending]

### 4. logo 置入位置與長寬比
expected: logo 在移除區域內置中、維持長寬比、完整顯示;前後對照預覽與下載的 PDF 中位置/大小一致且正確
result: [pending]

### 5. 更換 logo 觸發 stale 機制
expected: 變更 logo 選取會使既有結果失效,顯示正確的繁中「需重新套用」提示
result: [pending]

### 6. 重新套用取得最新 after-image(WR-01 快取破除)
expected: 「重新套用」後預覽抓取的是最新結果影像(?v= 參數不同),不會顯示舊的快取影像
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
