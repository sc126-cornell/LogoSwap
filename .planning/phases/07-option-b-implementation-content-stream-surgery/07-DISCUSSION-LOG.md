# Phase 7: Option B Implementation — Content-Stream Surgery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 7-option-b-implementation-content-stream-surgery
**Areas discussed:** A (parsing strategy), B (form-XObject log), C (insertion point), D (plan split)
**Mode:** default (interactive) + --chain (auto-advance to plan-phase after CONTEXT.md commit)

---

## Gray Area 選擇

呈現給使用者 5 個 gray areas(視覺空間限 4 個 + 1 個 Claude 裁量):

| Option | Description | Selected |
|--------|-------------|----------|
| A. Content-stream parsing 策略 | regex vs token parser vs get_drawings-based reverse lookup | ✓ |
| B. Form XObject 安全偵測 (SEC-03) | log 形式 + intersect 偵測 | ✓ |
| C. 插入點在 redact.py | line 195 後 / dispatcher 內 / dense branch only | ✓ |
| D. Plan split 與測試策略 | 1 / 2 / 3 plans | ✓ |
| E. Error handling on parse failure | (Claude 裁量範圍,not surfaced) | fail-safe + log warning |

**User's choice:** 全選 4 個 area;E 為 Claude 裁量。

---

## Area A: Content-stream parsing 策略

### Q1/4 — Parsing 策略

| Option | Description | Selected |
|--------|-------------|----------|
| (a) regex on `m/l/f/B` 算子序列 + 5 個 safe-skip context | 與 Phase 6 attack helper 同套思路 + minimum-change | ✓ |
| (b) token-based mini PDF parser | 規範但重(150-300 行)+ 與 5330290 教訓衝突 | |
| (c) `page.get_drawings()` reverse-lookup to content-stream offset | 需 fitz API 未證實的 offset 映射欄位 | |

**User's choice:** (a) — 與 Phase 6 attack script regex 同套思路。5 個 safe-skip context:BT/ET、BI/EI/ID、`(...)` literal、`<...>` hex、`%...\n` comments。

---

## Area B: Form XObject 安全偵測

### Q2/4 — 框選區與 form XObject 重疊時 log 形式

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Python stdlib `logging.warning` structured event | lightweight + future-friendly | ✓ |
| (b) 寫進 process result metadata 讓 frontend 顯示 banner | 跨 module + 動 web/js,違反 v1.1 不動 frontend | |
| (c) `RedactError("option_b_xobject_intersect", ...)` 中止 process | 太硬,使用者面不改變(Option A overlay 仍作 fallback) | |

**User's choice:** (a) — `logger.warning("option_b_xobject_intersect", extra={page_index, user_rect, xobject_count})`。前端不感知;Phase 8 才考慮 user-facing banner(如必要)。

---

## Area C: 插入點在 redact.py

### Q3/4 — Option B 插哪行

| Option | Description | Selected |
|--------|-------------|----------|
| (a) line 195 後 + line 232 前 — upstream defense | Option B 跑完 count → 0;dispatcher 自然 no-op;form-XObject 殘留時才走 last-mile | ✓ |
| (b) 在 dispatcher 內,Option B 後 count 決定 dense/sparse | 跨 module 邊界 + dispatcher 邏輯複雜化 | |
| (c) 只在 dense branch (count >= 100) 試 Option B | 與 SEC-02 no-op 衝突(count = 0 時 Option B 不執行) | |

**User's choice:** (a) — upstream defense,line 195 `residual_content` assertion 之後、line 232 `zero_area_count` 之前插入 ~6-10 行。既有 dispatcher 不重寫,作 form-XObject 殘留的 last-mile defense。

---

## Area D: Plan split

### Q4/4 — 切幾個 plan

| Option | Description | Selected |
|--------|-------------|----------|
| (a) 1 plan all-in-one | 中間狀態難分離,違反 hotfix-class 紀律 | |
| (b) 2 plans:07-01 helper + TEST-03 / 07-02 redact.py integration + flip xfail | 與 Phase 6 同型結構 + 2 waves 清晰 | ✓ |
| (c) 3 plans | 過度拆分 + orchestration overhead | |

**User's choice:** (b) — 2 plans。Plan 07-01 Wave 1:helper + TEST-03 unit tests。Plan 07-02 Wave 2(`depends_on: [07-01]`):redact.py integration + flip Phase 6 xfail + regression verify。

---

## Claude's Discretion(Area E + 細節決策)

### Area E: Error handling on parse failure

**Decision:** Option B 採 **fail-safe** 而非 raise — regex parsing 漏抓或內部 byte-offset 計算出錯時,helper 回傳 0 deleted + `logger.warning("option_b_parse_anomaly", ...)`,不 raise RedactError 中止 pipeline。

**Rationale:**
- 5330290 minimum-change 教訓 — Option B 失敗不該 break v1.0 baseline pipeline
- 既有 Hotfix 06 Option A overlay + `cover_zero_area_artefacts` 仍在 dispatcher 內接 last-mile defense
- Phase 6 regression test 仍會抓到失敗(Option B 沒刪乾淨 → count > 0 → dispatcher 走 dense/sparse → attack test 可能 XFAIL,implementer 自然 debug)
- 不新增 typed error class — Option B 是 internal pipeline step,error code 不需暴露為 4xx/5xx API contract

### Helper 簽名

```python
def delete_zero_area_type_f_fills_inside(
    page: "fitz.Page",
    user_rect: "fitz.Rect",
    tolerance: float = _DEGENERATE_BBOX_EPS,
) -> int:
    """Returns count of zero-area type='f' fills deleted from page content stream."""
```

對齊既有 `count_zero_area_fills_fully_inside(page, rect, tolerance=_DEGENERATE_BBOX_EPS)` 風格(line 699)。

### Multi-stream write-back 沿用 PATTERNS S1

verbatim port from Phase 6 `tests/_illustrator_attack.py`(原 scratch lines 104-115):
- 單 stream:`update_stream(content_xrefs[0], new_bytes, compress=True)`
- 多 stream:寫到 [0] + 清空 [1:]

不重新發明,planner 直接引導 Plan 07-01 implementer 沿用。

### `log_xobject_intersect` 放哪

推薦放 `app/services/pdf_engine.py`(fitz-aware logic 集中)+ 接受 `logger` 作 argument 注入(避免 hardcode logger 與 dependency injection 衝突)。`redact.py` 呼叫時傳入 `logger`。

### Test 檔案放置

推薦 `tests/test_pdf_engine.py`(若不存在則 Plan 07-01 task 新建)或在 `tests/test_redact.py` 加新 `class TestOptionB`。Planner 決定;沿用既有 pytest 結構即可。

### xfail flip 方式

**完全拔 decorator**(per Phase 6 D-D-Option-A xfail-strict 設計目的)。reason 字串本來只在 marker 存在時有意義,留 reason 而拔 strict 是錯誤。完全拔保持 audit trail 在 git history(commit message + diff)。

---

## Scope creep redirected → Deferred

無 — 使用者在 Area A/B/C/D 討論中沒有提出新 capability 要加;所有問題都在 Phase 7 boundary 內。

CONTEXT.md `<deferred>` 區段已列既有 deferred items(form XObject 遞迴 surgery、stroke surgery、auto-detect heuristic、token parser、performance benchmark 等)— 沿用 STATE.md / REQUIREMENTS.md 既有 deferred,不新增。

---

## Discussion meta

- **耗時(estimated):** 4 個 AskUserQuestion 回合,~3 min user-side(精煉每個 area 到 1 個關鍵問題)
- **沒重複問已答的問題:** AGPL seam、minimum-change、5330290 教訓、PATTERNS S1 multi-stream verbatim、Phase 6 xfail-strict handoff 設計、conftest in-memory fixture 哲學、繁中文案、commit/push 節奏 — 全部從 PROJECT.md / STATE.md / Phase 6 06-CONTEXT.md+06-PATTERNS.md+06-RESEARCH.md / memory 載入並在 CONTEXT.md `<domain>` § "Carrying forward" 明示
- **沒被誘導 scope creep:** Phase 7 為 hotfix-class implementation,使用者也沒嘗試加 form-XObject 遞迴 / stroke surgery / Phase 8 文件同步等屬於其他 phase 的 work
- **--chain mode:** discussion 完成後 auto-advance 到 `/gsd-plan-phase 7 --auto` 走 plan + execute
