---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Harden against Illustrator-class attacks on CAD-generated PDFs
status: executing
stopped_at: Phase 6 context gathered
last_updated: "2026-05-27T18:41:09.066Z"
last_activity: 2026-05-27 -- Phase 6 planning complete
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 2
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-28 — milestone v1.1 started)

**Core value:** 能乾淨地「移除而非覆蓋」供應商商標圖案與文字,換上我司商標,產出品牌正確的 PDF。
**Current focus:** v1.1 Phase 6 — Regression Foundation + Threat Model Re-evaluation(在動 Option B 實作前先把「紅燈」regression test 立起來)。

## Current Position

Phase: 6 of 8 (Regression Foundation + Threat Model Re-evaluation) — first phase of v1.1
Plan: — (plans TBD,待 `/gsd-plan-phase 6`)
Status: Ready to execute
Last activity: 2026-05-27 -- Phase 6 planning complete

Progress: [░░░░░░░░░░] 0% (v1.1 only; v1.0 已歸檔交付)

## Accumulated Context

### Decisions

完整決策日誌在 PROJECT.md Key Decisions 表。最近影響當前工作的決策:

- **2026-05-28** v1.1 啟動:Option B 從 v1.0 Deferred 升格為第一優先,因 forensic attack script 證明 deferral 假設「Option A 對使用者實質不可恢復」不成立
- **v1.0 hotfix-06 教訓**:已穩定的修法上「再加 polish」不是免費的 — Phase 7 落地 Option B 時嚴守 minimum-change,nice-to-have polish 分開 commit 或下次 maintenance sprint
- **AGPL seam**:fitz 嚴格限制在 `app/services/pdf_engine.py` — Option B 新 helper 必須在這個檔案內,不可外溢

### Pending Todos

無(milestone 啟動初期)。

### Blockers/Concerns

- **TEST-01 需要實際樣本**:工程師需提供 ≥3 個出問題的 supplier CAD-glyph PDF。Phase 6 plan 時必須先確認樣本來源與 sanitization 流程(去除供應商 metadata),才能開始寫 fixture-based regression test。

## Deferred Items

延到未來 milestone 再決定優先級:

| Category | Item | Status | Reason |
|---|---|---|---|
| Integration | `is_raster_fallback_image(page, xref)` getter | Deferred 自 v1.0 | colleague-system integration 出現時再加;HANDOFF.md 已交付 |
| Integration | 嵌入式整合(colleague approval site) | Deferred 自 v1.0 | API base path + iframe-friendly 設計已預留;實際整合需求出現時啟動 |
| Self-doc | `residual_whitepaint` 顯式列入 `_PROCESS_STATUS` | Deferred 自 v1.0 | dict.get fallback 已正確映射 422 |
| UAT | 超大影像錯誤訊息實機驗證(WR-03 megapixel cap UI) | Deferred 自 v1.0 | 自動測試覆蓋 OK,UI 字串待 ≥89MP 真檔 |
| Batch | 多檔批次處理 | Deferred 自 v1.0 | 須引入 task queue(Celery + Redis);v1 採手動單檔互動 |
| Security | Form XObject 內 zero-area fills 遞迴 surgery | Deferred from v1.1 SEC-03 | v1.1 採 page-level only + log;實際樣本出現再評估 |
| Security | Zero-area `type='s'`(stroke)surgery | Deferred from v1.1 | 威脅證據都是 type='f';stroke 未出現殘留 |

**Promoted from Deferred to Active(2026-05-28):**

- ~~Option B — content-stream surgery 真正刪除 zero-area sources~~ → **v1.1 active(Phase 7 核心)**。原 deferral 假設「Option A 對使用者實質不可恢復」已被 2026-05-28 forensic attack script 證明不成立(Illustrator 可拔 image XObject overlay)。

## Quick Tasks Completed

Inter-milestone ad-hoc tasks(`/gsd-quick`),不算入 milestone progress:

| Date | Slug | Description | Artifacts |
|---|---|---|---|
| 2026-05-27 | colleague-handoff-doc | 寫 `HANDOFF.md`(整合路徑決策樹 + AGPL 變化情境 + 核心領域知識備忘),供同事接手整合進公司內部簽核網站 | `HANDOFF.md`(新增,repo root);`.planning/quick/260527-1xq-colleague-handoff-doc/` |
| 2026-05-27 | cleanup-v1-debug-artifacts | 清理 milestone v1.0 hotfix 06(dCt-residue)累積的 72 個 root scratch artifacts;`.gitignore` 加入 root-anchored 防護 pattern | `samples/`(新增);`.planning/debug/scratch/v1.0-hotfix06/`(新增);`.gitignore`(modified) |

## Session Continuity

Last session: 2026-05-27T17:47:21.000Z
Stopped at: Phase 6 context gathered
Resume file: .planning/phases/06-regression-foundation-threat-model-re-evaluation/06-CONTEXT.md
