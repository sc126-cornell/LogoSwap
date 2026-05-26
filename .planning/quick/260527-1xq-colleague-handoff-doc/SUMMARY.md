---
quick_id: 260527-1xq
slug: colleague-handoff-doc
status: complete
completed_at: 2026-05-27
---

# Summary

新增 `HANDOFF.md`(repo root)做為接手同事的整合決策與領域知識文件,跟既有公開 README.md 並存,職責切分:

- README.md → AGPL public audience(部署、env、限制清單)
- HANDOFF.md → 接手同事(整合路徑決策、AGPL 情境變化、核心領域知識)

## Output

- `HANDOFF.md`(新增,8 節,~180 行)
- `.planning/STATE.md`(新增 Quick Tasks Completed 區段,記錄此次 task)
- `.planning/quick/260527-1xq-colleague-handoff-doc/PLAN.md` + `SUMMARY.md`

## Key decisions captured in HANDOFF.md

1. **三條整合路徑的 AGPL 含義差異** — A(microservice)與 B(FE 融入 + BE 獨立)都是乾淨的;C(完全融入 codebase)需要全站開源、買 Artifex 商業授權、或結構性隔離三選一
2. **內部使用 §13 豁免的四個前提** — 外部存取 / 子公司存取 / M&A / SaaS 化任一改變即重新觸發,需法務 review
3. **核心領域知識備忘** — redaction 真正移除原理、PDF.js viewport 座標換算、為何不用 pypdf、永遠存新檔(STRIDE invariant)
4. **接手第一週 5 步建議** — 跑起來 / 跑測試 / 讀三個檔 / 決定整合路徑 / 法務知會

## Avoided duplication

README.md 已涵蓋的部署細節、env vars、embedding contract、limitations 不重寫,以 markdown link 指向。HANDOFF 只寫 README 沒寫的決策/領域層內容。

## Commit

Local commit only(per `feedback_commit_push_cadence`:inter-milestone doc 不 push;同事整合啟動再決定要不要 push 一個 handoff release commit)。
