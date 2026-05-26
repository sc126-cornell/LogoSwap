---
quick_id: 260527-1xq
slug: colleague-handoff-doc
date: 2026-05-27
description: 寫給接手 LogoSwap 同事的 HANDOFF.md(整合路徑決策樹 + AGPL 含義 + 核心領域知識)
status: complete
---

# Quick Task: Colleague Handoff Doc

## Goal

產出 `HANDOFF.md` 放在 repo 根目錄,與既有 `README.md` 並存。職責切分:

- **README.md** 服務 AGPL public audience — 部署方式、環境變數、限制清單
- **HANDOFF.md** 服務接手同事 — 整合決策、AGPL 情境變化、核心領域知識

## Why now

User 計畫把專案交給同事整合進公司內部簽核網站(memory: project_deployment_licensing 2026-05-27 pivot)。同事接手前需要一份決策指南 + 領域知識備忘,避免:

1. 沒看清楚就走整合路徑 C(完全融入 codebase)踩 AGPL 地雷
2. 不知道「真正移除 vs 覆蓋」的核心價值,將來換套件破壞 invariant
3. 前端自己手算座標換算,redact 到錯誤位置(不可逆)

## Tasks

- [x] 讀既有 README.md 抓重複內容(避免 HANDOFF 變成複製品)
- [ ] 寫 HANDOFF.md(7 節)
  - 30 秒專案介紹 + 核心價值
  - 三條整合路徑決策樹 + 各路徑 AGPL 含義
  - AGPL 注意事項(再觸發情境表 + 三條必守規則)
  - Docker 部署(reference README,不重寫)
  - API 整合契約(指 OpenAPI)
  - 核心領域知識備忘(redaction、PDF.js viewport、為何不用 pypdf、永遠存新檔)
  - 接手後第一週建議
- [ ] 更新 STATE.md 加入 Quick Tasks Completed 區段(目前不存在)
- [ ] 寫 SUMMARY.md
- [ ] 本地 commit(per feedback_commit_push_cadence: 不 push)

## Out of scope

- 不重寫 README.md 已涵蓋的部署細節 — 用 markdown link reference
- 不變更任何程式碼
- 不 push 到 GitHub remote(user preference)
- 不開新 milestone(這是 inter-milestone 的 quick doc task)
