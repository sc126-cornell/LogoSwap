# Phase 8: Documentation Sync + LIVE Rollout - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 8-Documentation Sync + LIVE Rollout
**Areas discussed:** Deploy/UAT ordering, UAT sample & attack-sim, Milestone-close boundary
**Area offered but not selected:** 三道閘範圍（沿用既有標準,未討論）

---

## Deploy/UAT ordering

### Q1 — LIVE-UAT 在哪裡跑、push 時機?

| Option | Description | Selected |
|--------|-------------|----------|
| 本機 Docker 先,後 push Zeabur | 本機容器做 UAT,全綠+final review 後才 push;嚴守 commit-local-never-push | |
| 直接 push Zeabur 當 UAT 環境 | push 觸發部署,線上站點做 UAT;接受 push=deploy（v1.1 小幅+三道閘綠） | ✓ |
| Zeabur 不用了,只本機 Docker | 若 Zeabur 已關;LIVE 用本機 Docker 滿足 | |

**User's choice:** 直接 push Zeabur 當 UAT 環境
**Notes:** 刻意為此小幅、已三道閘綠的 v1.1 覆寫常規 cadence。標為 Phase 8 scoped 例外,不影響日後一般流程。

### Q2 — push/doc-sync/review 順序?

| Option | Description | Selected |
|--------|-------------|----------|
| doc 全做完 → push → UAT → final review + tag | 一次 push 帶齊文件與 code;UAT 綠才 final review/tag | ✓ |
| push 前先跑一次 code-review 保險 | 上 production 前多一道 review,再 push → UAT → tag | |
| 先 push Phase 7 code 驗 LIVE → 再補 doc → 再 push | 兩段 push,先驗證再寫文件 | |

**User's choice:** doc 全做完 → push → UAT → final review + tag
**Notes:** final code-review 落在 push 之後;此 push 為 v1.1 第一次上 production（帶 Phase 6+7+8）。

---

## UAT sample & attack-sim

### Q1 — 端到端 LIVE-UAT 用哪個 CAD-glyph 樣本?

| Option | Description | Selected |
|--------|-------------|----------|
| repo 內 sanitized fixture | tests/fixtures/cad-glyph/（可重現、與 CI parity） | |
| 工程師手上原始 supplier PDF | 未 sanitized 真實檔,最貼近實況;不入 repo | ✓ |
| 兩者都跑 | fixture 驗 attack-sim + 真實檔做 end-to-end | |

**User's choice:** 工程師手上原始 supplier PDF
**Notes:** 前置相依 — 需工程師再提供一份新鮮真實 supplier CAD-glyph PDF;此檔不入 repo。

### Q2 — attack-sim 怎麼對 LIVE 下載輸出檔跑?

| Option | Description | Selected |
|--------|-------------|----------|
| 一次性 scratch 呼叫既有 helper | .planning/debug/scratch/ import _illustrator_attack.py,assert 白≥98%+count==0,跑完退役 | ✓ |
| 包 standalone CLI runner 進 scripts/ | 可重複用但新增維護面 | |
| 你決定 | — | |

**User's choice:** 一次性 scratch 呼叫既有 helper
**Notes:** 符合 minimum-change（5330290 紀律）;不新增 production/test surface。

---

## Milestone-close boundary

### Q1 — Phase 8 收尾做到哪裡?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 8 做到 tag v1.1,complete-milestone 另跑 | tag 在 Phase 8,milestone close 獨立步驟 | |
| Phase 8 一路做到 complete-milestone | plans 含 /gsd-complete-milestone（tag+archive+audit+prep 下版） | ✓ |
| 你決定 | — | |

**User's choice:** Phase 8 一路做到 complete-milestone
**Notes:** 一次收乾淨,不留尾巴;planner 須把 milestone-close 任務排進 Phase 8。

---

## Claude's Discretion

- 三處 LIMITATION docstring / HANDOFF 6.5 / PROJECT Key Decisions 的實際措辭由 planner/executor 依成功標準擬（改寫方向已由成功標準 1 定死）。

## Deferred Ideas

- Standalone LIVE-UAT attack runner（`scripts/`）— 否決,改一次性 scratch。未來 LIVE-UAT 若常態化再評估包成 CLI。
