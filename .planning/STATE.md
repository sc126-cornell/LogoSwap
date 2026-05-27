---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Harden against Illustrator-class attacks on CAD-generated PDFs
status: planning
last_updated: "2026-05-27T16:37:48.036Z"
last_activity: 2026-05-27
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-28 — milestone v1.1 started)

**Core value:** 能乾淨地「移除而非覆蓋」供應商商標圖案與文字,換上我司商標,產出品牌正確的 PDF。
**Current focus:** v1.1 — 落地 Option B(content-stream surgery 真正刪除零面積 type='f' fills),關閉 Illustrator-class 編輯器拔掉 image XObject overlay 後的 CAD-glyph 重現攻擊面。

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-05-27 — Milestone v1.1 started

## Deferred Items

延到未來 milestone 再決定優先級:

| Category | Item | Status | Reason |
|---|---|---|---|
| Integration | `is_raster_fallback_image(page, xref)` getter | Deferred 自 v1.0 | colleague-system integration 出現時再加;HANDOFF.md 已交付 |
| Integration | 嵌入式整合(colleague approval site) | Deferred 自 v1.0 | API base path + iframe-friendly 設計已預留;實際整合需求出現時啟動 |
| Self-doc | `residual_whitepaint` 顯式列入 `_PROCESS_STATUS` | Deferred 自 v1.0 | dict.get fallback 已正確映射 422 |
| UAT | 超大影像錯誤訊息實機驗證(WR-03 megapixel cap UI) | Deferred 自 v1.0 | 自動測試覆蓋 OK,UI 字串待 ≥89MP 真檔 |
| Batch | 多檔批次處理 | Deferred 自 v1.0 | 須引入 task queue(Celery + Redis);v1 採手動單檔互動 |

**Promoted from Deferred to Active(2026-05-28):**
- ~~Option B — content-stream surgery 真正刪除 zero-area sources~~ → **v1.1 active(第一優先)**。原 deferral 假設「Option A 對使用者實質不可恢復」已被 2026-05-28 forensic attack script 證明不成立(Illustrator 可拔 image XObject overlay)。

## Quick Tasks Completed

Inter-milestone ad-hoc tasks(`/gsd-quick`),不算入 milestone progress:

| Date | Slug | Description | Artifacts |
|---|---|---|---|
| 2026-05-27 | colleague-handoff-doc | 寫 `HANDOFF.md`(整合路徑決策樹 + AGPL 變化情境 + 核心領域知識備忘),供同事接手整合進公司內部簽核網站 | `HANDOFF.md`(新增,repo root);`.planning/quick/260527-1xq-colleague-handoff-doc/` |
| 2026-05-27 | cleanup-v1-debug-artifacts | 清理 milestone v1.0 hotfix 06(dCt-residue)累積的 72 個 root scratch artifacts:1 個樣本 PDF 搬 `samples/`、4 個 forensic 證據歸檔 `.planning/debug/scratch/v1.0-hotfix06/`、67 個純 scratch 直接刪;`.gitignore` 加入 root-anchored 防護 pattern;`debug/resolved/redact-whitepaint-residue.md` 與 `hotfix-06/06-HOTFIX-REVIEW.md` 路徑引用更新 | `samples/`(新增);`.planning/debug/scratch/v1.0-hotfix06/`(新增);`.planning/quick/260527-251-cleanup-v1-debug-artifacts/`;`.gitignore`(modified) |

## Session Continuity

Last session: 2026-05-28
Stopped at: Milestone v1.1 started — PROJECT.md + STATE.md initialized;將進入 requirements 定義。
Resume file: None.
