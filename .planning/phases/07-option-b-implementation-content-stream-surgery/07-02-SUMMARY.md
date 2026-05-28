---
phase: 07-option-b-implementation-content-stream-surgery
plan: 02
subsystem: pdf
tags: [pymupdf, redaction, dispatcher, regression, security, agpl-seam, content-stream]

# Dependency graph
requires:
  - phase: 07-option-b-implementation-content-stream-surgery (Plan 07-01)
    provides: "pdf_engine.delete_zero_area_type_f_fills_inside + pdf_engine.log_xobject_intersect helpers (AGPL seam) + 14 TEST-03 unit tests + baseline 315+3+3"
provides:
  - "redact.remove_region_vector 在 line 195/197 boundary 接入 Option B(delete_zero_area_type_f_fills_inside + log_xobject_intersect),wiring 完成"
  - "redact.py 模組層級 `import logging` + `logger`(non-fitz,AGPL seam 不破)"
  - "tests/test_illustrator_attack_regression.py 移除 @pytest.mark.xfail(strict=True) decorator(Phase 6 → Phase 7 binding handoff signal 已扣)"
  - "structured log event option_b_deleted 在 redact.py emit"
affects: [07-SECURITY, 08-phase8-live-uat, 06-fixture-re-sanitize-decision]

# Tech tracking
tech-stack:
  added: []  # 無新 runtime/dev 套件 — 只用 stdlib logging
  patterns:
    - "Option B = upstream defense:在既有 Phase 5 Hotfix 06 dispatcher 之前真正刪除 page-level 零面積 type='f' source;既有 dense/sparse dispatcher 退為 form-XObject nested residue last-mile defense"
    - "fail-safe helper 呼叫不包 try/except(D-A5 設計:helper 內部 return 0 + logger.warning,caller 包 try 反而吞掉 SEC-03 透明化)"

key-files:
  created:
    - ".planning/phases/07-option-b-implementation-content-stream-surgery/07-02-SUMMARY.md"
  modified:
    - "app/services/redact.py"
    - "tests/test_illustrator_attack_regression.py"
    - "tests/test_redact.py"  # Rule 1 deviation — dense end-to-end test 升級反映 Option B 真刪

key-decisions:
  - "Option B helper 傳入 fitz.Rect 物件 `rect`(非 user_rect tuple)— Plan 07-01 helper 簽名收 fitz.Rect 並內部自行轉 tuple"
  - "dense end-to-end 測試(test_remove_region_vector_dense_real_zero_area_paths_end_to_end)更新為斷言 Option B 真刪後 post-count==0 + 無 raster overlay(true-removal 取代 overlay cover)"
  - "SEC-01 acceptance gate 未通過 — 3 個 illustrator-attack regression case FAIL(非 PASS),經 diagnostic 確認為 Plan 07-01 helper 限制 + fixture/attack-model 範圍問題,非 07-02 integration bug;依 sec_01 acceptance note 不在 07-02 內擴張 scope 修補,標記 Self-Check FAILED 交 orchestrator 裁量"

patterns-established:
  - "繁中 inline comment 標記 Option B dispatcher block(memory feedback_language)"
  - "Rule 1 deviation:當生產行為正確地 obsolete 既有測試的不變量,更新該測試以反映新正確行為(不改既有 dispatcher production code)"

requirements-completed: []  # SEC-01/SEC-02/SEC-03 wiring 已落地,但 SEC-01 acceptance gate 未通過 → 不標記完成,交 orchestrator/verifier 決定

# Metrics
duration: ~75min
completed: 2026-05-28
---

# Phase 7 Plan 02: Option B Dispatcher Integration + xfail Flip Summary

**把 Plan 07-01 的 Option B helper 接進 redact.remove_region_vector 的 line 195/197 boundary(2 LOC import + ~15 LOC dispatcher block,既有 dispatcher 一字不改),並拔除 Phase 6 三個 xfail-strict regression decorator;Option B 對 text-glyph fixture 真正刪除 page-level 零面積 source(count 1→0、render 99.59% 白),但 SEC-01 acceptance gate 未過 — 3 個 regression case 因 Plan 07-01 helper 在 mixed-glyph(3396 ZAF cardinality fail-safe)限制 + figure-glyph 既有 residual_content 斷言 + text-glyph 缺 Option A overlay 可攻擊(attack precondition)而 FAIL,屬上游 scope,標記 Self-Check FAILED 交 orchestrator。**

## Performance

- **Duration:** ~75 min(含多輪 9-min full-pipeline diagnostic 確認 SEC-01 失敗根因)
- **Tasks:** 2
- **Files modified:** 2 production-path(`app/services/redact.py` 為唯一 production code;`tests/` 兩檔)

## Accomplishments

- **Option B wiring(Task 1)** — `app/services/redact.py::remove_region_vector` 在 `residual_content` raise 之後、既有 Hotfix 06 dispatcher 之前,插入 Option B dispatcher block:
  - `deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, rect)` + `if deleted > 0:` → `logger.info("option_b_deleted", extra={...})`
  - `pdf_engine.log_xobject_intersect(page, rect, logger=logger)`(SEC-03 透明化)
  - 模組層級 `import logging` + `logger = logging.getLogger(__name__)`(non-fitz,AGPL seam 不破)
- **既有 dispatcher 完整保留** — line 197-258(zero_area_count dispatcher + Option A overlay + cover_zero_area_artefacts + HONEST LIMITATION comment)**0 deletions**(`git diff app/services/redact.py | grep '^-[^-]' | wc -l` == 0)
- **xfail flip(Task 2)** — `tests/test_illustrator_attack_regression.py` 移除 `@pytest.mark.xfail(strict=True, reason=...)` decorator(line 74-82),保留 `@pytest.mark.parametrize`
- **Option B 對 text-glyph-01 證實有效** — diagnostic:region 零面積 count 1→0、OUTPUT region render 99.59% 白、無 Option A overlay(true removal 成功)

## Task Commits

1. **Task 1: wire Option B into redact dispatcher** — `a09b39f` (feat)
2. **Task 2: remove xfail-strict decorator** — `96e5bad` (test)

**Plan metadata:** (this commit) (docs)

## Files Created/Modified

- `app/services/redact.py` — +2 LOC import(`import logging` + `logger`)+ ~15 LOC Option B dispatcher block(繁中 comment + 2 helper 呼叫 + structured log)。既有 dispatcher 0 改動。
- `tests/test_illustrator_attack_regression.py` — 移除 9 行 xfail decorator(`@pytest.mark.xfail(strict=True, ...)`),parametrize 保留。
- `tests/test_redact.py` — [Rule 1 deviation] `test_remove_region_vector_dense_real_zero_area_paths_end_to_end` 更新斷言(見 Deviations)。

## Production-code scope audit(Phase 7 整體)

`git diff --stat 96bb49f..HEAD -- app/`(Phase 7 base 至本 plan):

```
 app/services/pdf_engine.py | 523 +++++  (Plan 07-01)
 app/services/redact.py     |  25 +++   (Plan 07-02)
 2 files changed, 548 insertions(+)
```

只命中 2 檔,符合 [BLOCKING] production scope invariant。

## redact.py 改動 audit(僅新增、無刪除既有 code)

```
+import logging
+logger = logging.getLogger(__name__)
... (residual_content raise 之後)
+    # Phase 7 Option B — page-level content-stream surgery (SEC-01)。 [繁中 comment block]
+    deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, rect)
+    if deleted > 0:
+        logger.info("option_b_deleted", extra={"page_index": page.number, "count": deleted})
+    pdf_engine.log_xobject_intersect(page, rect, logger=logger)
```

`git diff app/services/redact.py` 無任何 `-` 開頭(僅新增)。既有 line 197-258 dispatcher 字面保留。

## AGPL seam invariant

`grep -rn "^import fitz" app/` → 單行:`app/services/pdf_engine.py:21`。
`redact.py` 加的是 `import logging`(stdlib,non-fitz)。
AGPL guard test `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` → **PASSED**。

## Decisions Made

- **傳 fitz.Rect 而非 tuple** — Plan 07-01 helper 簽名收 `user_rect: "fitz.Rect"` 並內部轉 tuple;redact.py 內 `rect`(傳入參數)本就是 fitz.Rect,直接傳 `rect`(非上方的 `user_rect` plain tuple)。不需在 redact.py `import fitz`。
- **不包 try/except** — D-A5:helper 自身 fail-safe(return 0 + 內部 logger.warning),caller 包 try 反而吞掉 SEC-03 透明化 + cardinality 診斷(T-07-12)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] dense end-to-end test 斷言過時(Option B 真刪後 dense overlay 不再 fire)**
- **Found during:** Task 1(整合 Option B 後跑 full baseline,`test_remove_region_vector_dense_real_zero_area_paths_end_to_end` FAILED)
- **Issue:** 該測試合成 120 個 page-level 零面積 fill,斷言 dense 分支插入 1 個 raster overlay image XObject(POST 1)。Option B 現在 upstream 真正刪除這 120 個 page-level source → `zero_area_count` 歸 0 → dense 分支不再 fire → 0 image inserted,POST 1 `assert len(imgs) == 1` 失敗。此為我 Task 1 改動「直接造成」且為「正確的新行為」(true removal 取代 overlay cover,即 SEC-01 的目的)。
- **Fix:** 更新該測試斷言為新正確行為:`post_count == 0`(Option B 真刪)、`len(imgs) == 0`(dense overlay 不再 fire,退為 form-XObject last-mile defense)、無 white-fill drawings、region render 白。docstring 加 PHASE 7 OPTION B UPDATE 說明。**未動任何 production dispatcher code。**
- **Files modified:** `tests/test_redact.py`
- **Verification:** dense + sparse 兩個 dispatcher 測試皆 PASS;full baseline 回到 315 passed + 3 skipped + 3 xfailed(Task 1 結束、Task 2 flip 前)。
- **Committed in:** `a09b39f`(Task 1 commit)

---

**Total deviations:** 1 auto-fixed(1 Rule 1 bug — 測試斷言反映正確的新生產行為)。
**Impact:** 不擴張 production scope(僅改測試斷言,未動既有 dispatcher);Rule 1 的「直接由本 task 改動造成」範圍內。

## Issues Encountered — SEC-01 ACCEPTANCE GATE 未通過(root-cause 已查明)

`python -m pytest -k illustrator_attack -v` → **3 failed**(原期望 3 PASSED)。經三輪 full-pipeline diagnostic(throwaway script,已刪)逐 fixture 查明根因 —— **三個 fixture 因三個不同的上游原因 FAIL,皆非 07-02 integration bug:**

| Fixture | 路由 | RAW region ZAF | process_job 結果 | OUTPUT region ZAF | OUTPUT render 白% | Option A overlay | FAIL 點 |
|---|---|---|---|---|---|---|---|
| `text-glyph-01` | VECTOR | 1 | OK | **0** | **99.59%** | 0 | attack precondition(`n_deleted>=1` line 146)— 無 overlay 可拔 |
| `figure-glyph-01` | VECTOR | 1 | **RAISED `residual_content`** | n/a | n/a | n/a | 既有 residual_content 斷言(Option B block 之前) |
| `mixed-glyph-01` | VECTOR | (3396) | OK | **3396** | 100.00% | 1 | Option B 未刪(`option_b_parse_anomaly` cardinality fail-safe)→ Option A overlay 撐住視覺 → attack 拔 overlay 後 content-stream gate(`==0`)會失敗 |

**逐 fixture 分析:**

1. **`text-glyph-01` — Option B 真正成功,fail 在過時的 attack precondition。** 框選區只有 N=1 零面積 fill,Option B 刪到 0,render 99.59% 白。但框選區內**從來沒有 Option A image-XObject overlay**(N=1 遠低於 `ZERO_AREA_RASTER_THRESHOLD=100`,dense 分支從不 fire),所以 attack 的 `delete_image_xobjects_intersecting` 回傳 0 → `assert n_deleted >= 1`(line 146)失敗。此即 regression test docstring line 143-145 預告的「該重新 sanitize fixture」情境 —— fixture 不夠 dense,無法製造可攻擊的 overlay。**SEC-01 兩道真實 acceptance gate(白≥98% + count==0)其實都滿足。**

2. **`figure-glyph-01` — `process_job` 在既有 `residual_content` 斷言 raise(Option B block 之前)。** 此斷言在我插入的 Option B block **之前**(line 191-195),與 Option B 無關;pre-Phase-7 baseline 亦會 raise(故當時為 XFAIL via exception path)。屬 Phase 4 既有 vector-branch 行為,非 07-02 改動引入。

3. **`mixed-glyph-01` — Plan 07-01 helper 在 3396-ZAF 規模下 cardinality fail-safe(D-A5)→ Option B 刪 0 個。** 與 07-01 SUMMARY § Issues Encountered + Open Question NEW-for-07-02 完全吻合(「Real-fixture full-page spike on mixed-glyph-01 (3396 ZAFs) ... fail-safe correctly returns 0 when cardinality drifts」)。框選區 sub-rect 下 3396 ZAF 仍觸發 cardinality drift → `option_b_parse_anomaly` → return 0(無破壞性寫回,符合設計)。既有 Option A dense 分支(count≥100)插 1 個 overlay 撐住視覺(100% 白),但 content stream 內 3396 個 source 仍在 → attack 拔 overlay 後 content-stream gate(`count==0`)失敗。**這是 Plan 07-01 helper 的真實限制(regex anchor matching 在高密度真實 supplier stream 漏抓),非 07-02 wiring bug。**

**處置(per `<sec_01_acceptance_note>` + 5330290 minimum-change):** 不在 07-02 內擴張 scope 改 Plan 07-01 helper、不重新 sanitize fixture、不改 attack helper。標記 `## Self-Check: FAILED`,由 orchestrator/verifier 決定後續(候選:(a) 回 Plan 07-01 強化 helper 對高密度 stream 的 regex anchor / 改用 tokenizer;(b) 重新 sanitize fixture 讓 attack-model 對齊;(c) 調整 regression test 的 attack precondition 以承認「Option B 真刪 → 無 overlay 可拔」是 PASS 條件之一)。

## Stub / Threat scan

- **無新 stub。**
- **Threat flags:** 無新攻擊面 —— Option B wiring 只呼叫既有 AGPL-seam helper;`log_xobject_intersect` 為 side-effect-only。STRIDE register T-07-09..T-07-13 全數由 verify gate 守住(AGPL seam 單行、既有 dispatcher 0 deletions、xfail 完全拔非替換、無 try/except wrap、import-time 無 error)。

## Phase 8 handoff signal

三處 LIMITATION docstring(`pdf_engine.py::replace_region_with_white_raster`、`redact.py` module-level `TRUE_REMOVAL_LIMITATION`、`redact.py` dispatcher inline `HONEST LIMITATION` line 220-227)在 Phase 7 close 時**未更新**(Phase 8 THREAT-02 + DOC-01 才動)。Phase 8 implementer 須知:Option B 對低密度 page-level(N≈1)fixture 已 true-delete;對高密度(mixed-glyph 3396 ZAF)目前 cardinality fail-safe → Option A overlay 接手(SEC-03 已 log)。

## T-06-01 / T-02-07 closure 狀態

**未能宣告 `CLOSED via Option B`** —— SEC-01 acceptance gate(3 regression case)未通過。Option B 對 text-glyph 已證實 true-delete,但 mixed-glyph(高密度真實 supplier)仍依賴 Option A overlay。T-06-01 / T-02-07 維持 Phase 6 `accept (P0, transition-pending)`,待 orchestrator 決定上游修補後再行 close。

## Self-Check: FAILED

**檔案/commit 存在性(全 PASS):**
- FOUND: `app/services/redact.py`(`import logging` + `logger` + Option B dispatcher block)
- FOUND: `tests/test_illustrator_attack_regression.py`(xfail decorator 已移除,parametrize 保留)
- FOUND: `tests/test_redact.py`(dense 測試已更新)
- FOUND: commit `a09b39f`(Task 1, feat)
- FOUND: commit `96e5bad`(Task 2, test)
- AGPL seam 單行 `app/services/pdf_engine.py:21`;AGPL guard test PASSED
- 既有 dispatcher 0 deletions;production scope 只 2 檔

**未通過項(FAILED 原因):**
- **SEC-01 acceptance gate FAILED** — `python -m pytest -k illustrator_attack -v` 顯示 **3 failed**(非 3 passed)。根因為 Plan 07-01 helper 高密度限制(mixed-glyph)+ 既有 residual_content 斷言(figure-glyph)+ 過時 attack precondition(text-glyph),皆上游 scope,非 07-02 integration bug(詳上方 Issues Encountered 逐 fixture 分析 + diagnostic 證據)。
- **Final baseline 未達 `≥318 passed + 3 skipped + 0 xfailed`** — 因 3 regression case 由 xfailed 翻為 **failed**(非 passed)。預期 tally:`315 passed + 3 skipped + 3 failed + 0 xfailed`。

**交 orchestrator 裁量(per 5330290 — 不在 07-02 內擴張 scope 改 helper / fixture / attack-model)。**

---
*Phase: 07-option-b-implementation-content-stream-surgery*
*Completed: 2026-05-28*
