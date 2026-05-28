---
phase: 07-option-b-implementation-content-stream-surgery
plan: 03
subsystem: pdf
tags: [pymupdf, content-stream, regression, security, agpl-seam, shape1-locator, gap-closure, sec-01]

# Dependency graph
requires:
  - phase: 07-option-b-implementation-content-stream-surgery (Plan 07-01)
    provides: "delete_zero_area_type_f_fills_inside + Shape 1/2 locator + 14 TEST-03 unit tests"
  - phase: 07-option-b-implementation-content-stream-surgery (Plan 07-02)
    provides: "redact.remove_region_vector Option B wiring + xfail-strict decorator removal"
provides:
  - "_build_shape1_candidate_index 單次掃描索引(single-pass O(1) lookup,取代舊 per-zaf 全串流 finditer)"
  - "bbox-keyed per-zaf ≥1 覆蓋 cardinality(Option ii)— 重複-bbox glyph 全刪,D-A5 fail-safe 保留"
  - "_NUMBER leading-dot decimal 修正([-+]?(?:\\d+\\.?\\d*|\\.\\d+))— 解 PScript5 -.061 / .06 漏抓"
  - "attack precondition 重設計:Option B true removal → 無 overlay 可拔 + region 乾淨 = PASS"
  - "figure-glyph-01 fixture 重新 sanitize 自 B-3012IP 真實零面積 cluster(含非零 original_supplier_zero_area_count)"
  - "SEC-01 acceptance gate 通過:3 illustrator-attack regression case 全綠"
  - "T-06-01 + T-02-07 close-via-Option-B evidence(mixed-glyph 通過)"
affects: [07-SECURITY, 08-phase8-live-uat]

# Tech tracking
tech-stack:
  added: []  # 無新 runtime/dev 套件
  patterns:
    - "Shape 1 locator = single-pass candidate index(鏡像 Shape 2),value 為 list 支援合法重複-bbox glyph"
    - "Option (ii) cardinality:per-zaf-bbox ≥1 覆蓋(非 1:1 M==N),真實安全閘是 attack post-condition 而非 byte-range 計數"
    - "PDF number regex 必須涵蓋 leading-dot real(-.061 / .5);PScript5 CAD glyph 大量使用"
    - "attack precondition 承認 true removal:無 overlay AND region 髒 才算漏洞"

key-files:
  created:
    - ".planning/phases/07-option-b-implementation-content-stream-surgery/07-03-SUMMARY.md"
  modified:
    - "app/services/pdf_engine.py"          # Shape 1 locator rework + _NUMBER fix(唯一 production code)
    - "tests/test_pdf_engine.py"            # +3 Shape 1 單元測試(14 → 17)
    - "tests/test_illustrator_attack_regression.py"  # attack precondition 重設計
    - "tests/fixtures/cad-glyph/figure-glyph-01.pdf"  # 重新 sanitize 自 B-3012IP
    - "tests/fixtures/cad-glyph/figure-glyph-01.json" # manifest 含非零 original_supplier_zero_area_count

key-decisions:
  - "Shape 1 採 single-pass _build_shape1_candidate_index(鏡像 Shape 2),取代舊 _locate_shape1_byte_range 的 O(zafs × stream) per-zaf 全掃"
  - "cardinality 採 Option (ii)(per-zaf-bbox ≥1 覆蓋,刪該 bbox 全部 range),非 Option (i)(M==N 精確)— 供應商把單一 logo 分解為多筆同 bbox 描邊"
  - "_NUMBER 修正為涵蓋 leading-dot real 是 mixed-glyph 14%→100% 命中率的決定性根因(Rule 1 bug,Task 3 執行中發現)"
  - "attack precondition 重設計而非降標準:兩道真實安全閘 white≥98% + count==0 門檻一字未放鬆"
  - "figure-glyph 採 SCOPE 3(a)— 自 B-3012IP 真實零面積 cluster 重新 sanitize(非退化 control fixture)"

patterns-established:
  - "Shape 1 candidate index value 為 list(setdefault 累加)以支援合法重複-bbox glyph 全刪"
  - "module-level compiled regex hoist(_NUMBER / _CM_RE / _POINT_RE / _FILL_OP_RE)避免 hot-path 重編譯"

requirements-completed: [SEC-01, SEC-02, SEC-03, TEST-03]

# Metrics
duration: ~95min
completed: 2026-05-28
---

# Phase 7 Plan 03: SEC-01 Gap Closure — Shape 1 Locator Rework Summary

**關閉 Plan 07-02 標記 FAILED 的 SEC-01 acceptance gate:把 Shape 1 locator 從 per-zaf 全串流 finditer(765s / 14% 命中)重寫為鏡像 Shape 2 的 single-pass 候選索引 + bbox-keyed Option (ii) cardinality(<5s / 100% 命中、重複-bbox 全刪),並修正 `_NUMBER` 對 PScript5 leading-dot real(`-.061` / `.06`)的漏抓根因 — 此為 mixed-glyph 14%→100% 命中率的決定性修補。同步重設計 attack precondition(承認 Option B true removal → 無 overlay 可拔 + region 乾淨 = PASS,兩道真實安全閘門檻不放鬆),並把 figure-glyph fixture 從 raw B-3012IP 的真實零面積 cluster 重新 sanitize。結果:`python -m pytest -k illustrator_attack -v` 顯示 3 PASSED,全套件 321 passed + 3 skipped + 0 xfailed + 0 failed。**

## Performance

- **Duration:** ~95 min(含 8 輪 throwaway diagnostic 定位 fail-safe 根因 + figure-glyph SCOPE 3 調查 + 重新 sanitize)
- **Tasks:** 3
- **Files modified:** 1 production code(`app/services/pdf_engine.py`)+ 4 test/fixture 檔

## Shape 1 Rework 前後對照(CORE — SCOPE 1)

mixed-glyph-01.pdf 框選區(602,481,827,511)實測:

| 指標 | 修補前(07-02 baseline) | 修補後(07-03) |
|---|---|---|
| **處理時間** | 765s | **1.12s**(實測 `delete_zero_area_type_f_fills_inside`)|
| **Shape 1 命中率** | 249/1742 = 14% | **3396/3396 = 100%**(re + m/l 全 matched)|
| **cardinality 結果** | matched 1903 vs zafs 3396 → MISMATCH → fail-safe return 0 | **無 anomaly,deleted=3396,after count=0** |
| **regression 結果** | FAIL(attack 拔 overlay 後 content-stream gate count>0)| **PASS(白≥98% + count==0)** |

### 三項根因與修補

1. **PERF defect** — 舊 `_locate_shape1_byte_range` 對每個 zaf 做全串流 `_Q_BLOCK_RE.finditer`(O(1742 × 1.3MB))。修補:新增 `_build_shape1_candidate_index` single-pass 掃描一次,逐 q...Q block 解析 cm/points/fill → user-space bbox → 以 round(bbox,3) 為 key、value 為 `list[(start,end)]`(setdefault 累加)。per-zaf 查表降為 O(1) dict access。

2. **CORRECTNESS defect(cardinality)** — 舊規則 `len(matches) == 1` 在重複 bbox 下必失敗(多筆同 bbox 描邊 → return None → ambiguous)。修補:cardinality 改 **Option (ii) bbox-keyed per-zaf ≥1 覆蓋** — 每個 zaf-bbox 在 index 有 ≥1 byte-range 即視為覆蓋成功,刪除該 bbox 全部 range(deduped by `seen`)。任一 zaf-bbox 找不到(`missing_keys` 非空)或 mixed/empty-item zaf → D-A5 fail-safe return 0,絕不破壞性寫回。

3. **`_NUMBER` leading-dot defect(Rule 1 bug,Task 3 執行中發現)** — 舊 `_NUMBER = -?\d+\.?\d*` 要求 `.` 前必有 `\d+`,故 PScript5 的 `-.061` 只 match 到 `061`(= 61),bbox x 從 `609.48` 失真為 `670.42` → byte-range 漏抓。此為 14% 命中率最決定性的根因。修補:`_NUMBER = [-+]?(?:\d+\.?\d*|\.\d+)` 同時接受 `-5` / `5.5` / `5.` / `.5` / `-.061`。

## SEC-01 Acceptance Evidence(PRIMARY gate)

```
$ python -m pytest -k illustrator_attack -v
collected 324 items / 321 deselected / 3 selected

tests/test_illustrator_attack_regression.py::...[figure-glyph-01] PASSED [ 33%]
tests/test_illustrator_attack_regression.py::...[mixed-glyph-01]  PASSED [ 66%]
tests/test_illustrator_attack_regression.py::...[text-glyph-01]   PASSED [100%]

====================== 3 passed, 321 deselected in 6.53s ======================
```

**3 PASSED,0 failed / 0 xfailed / 0 skipped。**

## 全套件 final tally

```
$ python -m pytest 2>&1 | tail -3
======================= 321 passed, 3 skipped in 19.78s =======================
```

**321 passed + 3 skipped + 0 xfailed + 0 failed。** 換算:07-02 baseline 315 passed(含 3 attack FAILED)→ Task 2 新增 3 Shape 1 單元測試(318)→ Task 3 把 3 attack flip 為 passed(321)。達 `≥318 passed` 目標。

## TEST-03 unit tests(SCOPE 1 驗證 + 擴充)

`python -m pytest tests/test_pdf_engine.py -q` → **17 passed**(原 14 + 新 3):

- `test_option_b_shape1_high_density_all_matched` — 500 筆不同 bbox m/l 零面積 fill 全刪 + 刪後 count==0 + perf soft-assert <5s。
- `test_option_b_shape1_duplicate_bbox_all_deleted` — 5 筆完全相同 bbox 描邊全刪(鎖定 Option ii list 累加)。
- `test_option_b_shape1_genuine_miss_failsafe` — mixed-item(curve)ZAF → return 0 + content stream 一字未改 + caplog 捕獲 `option_b_parse_anomaly`(鎖定 D-A5 fail-safe 在新 cardinality 下仍不破壞性寫回)。

spike 確認:`Shape.draw_rect(W=0)` 產生 `re`(Shape 2);`Shape.draw_line` 產生 `l`(Shape 1)。Shape 1 fixture 用 `draw_line`。全 in-memory,不 commit binary。

## SCOPE 3 figure-glyph 處置記錄(採 (a) 重新 sanitize)

- **調查:** raw `B-3012IP-WM02-T430.pdf` page 0 有 **3225 個零面積 type='f' fill** 群聚於 PDF 點 `x∈[327, 417], y∈[2475, 3163]`(top cluster cells 在 y=2700-2900,每 cell 600+ 筆)— 真實供應商 CAD glyph 攻擊面,與 mixed-glyph 同型。該 cluster 區無可 extract 文字(純向量 glyph)。
- **修補 (a):** 用既有 `scripts/sanitize_fixture.py` CLI 重新 sanitize:
  ```
  python scripts/sanitize_fixture.py --in <B-3012IP> \
    --out tests/fixtures/cad-glyph/figure-glyph-01.pdf \
    --supplier-name "B-3012IP-SUPPLIER" --region-rect "320,2470,420,3170" \
    --page-index 0 --dpi 144
  ```
  - Self-assert 全過:metadata 全空 + supplier_name 不在 `get_text()` + post zero-area **6289 ≥ 0.9 × 3225**。
  - manifest 含非零 `original_supplier_zero_area_count`(=3225)。
  - 舊 figure-glyph region(1950,80,2300,500)落在真實非零向量幾何 → 觸發 `residual_content`;新 region 落在零面積攻擊面 → 不再 raise,attack 拔 overlay 後 region count==0 + 白≥98% → PASS。
- **附註:** Step 3 brand-glyph strip 命中 0 個 q...Q block(已知 WR-04 cm-aware 限制 — 原 brand 用 cm 變換,byte-offset 啟發式漏抓);但 Step 4 注入 3064 TESTCO 零面積 mark + 原 3225 保留,region 仍有真實零面積攻擊面。fixture metadata 已清空、cluster 無可 extract 文字,public-repo 安全屬性維持。

## T-06-01 / T-02-07 close-via-Option-B handoff signal

**mixed-glyph(高密度真實 supplier,3396 ZAF)現通過** → Option B 真刪 page-level 零面積 source → attack 拔 image XObject overlay 後 content stream 內無內容可重現(白 100% + count 0)。此即 Phase 6 繼承的 **T-06-01 + T-02-07** 的 close 機制。

**供 verifier / 07-SECURITY 記錄:** T-06-01 + T-02-07 由 Phase 6 `accept (P0, transition-pending)` 可改為 **CLOSED via Option B**(本 plan 不寫 07-SECURITY,提供 close evidence:3 illustrator-attack regression PASS + mixed-glyph 100% 命中 + attack post-condition count==0)。

## AGPL seam + production scope invariant

- **AGPL seam:** `grep -rn "^import fitz" app/` → 單行 `app/services/pdf_engine.py:21`。`tests/test_redact.py::test_fitz_import_confined_to_engine_seam` → PASSED。
- **production scope(本 plan):** `git diff --stat f3b7c14..HEAD -- 'app/'` → 僅 `app/services/pdf_engine.py`(124 insertions / 74 deletions)。redact.py 不動(07-02 已 wire)。
- **Shape 2 path 不動:** `_build_shape2_candidate_index` / `_locate_shape2_byte_range` 函式體一字未改(dispatch 改為統一用 `shape2_index.get(key)` ≥1 檢查以對齊 Shape 1 語義,但 helper 本體保留供既有引用)。
- **STEP A/B/E 不動:** get_drawings 4-gate pre-screen、5-context safe-skip mask、multi-stream write-back(asymmetric write-[0]+empty-[1:]、compress=True)逐字保留。

## Task Commits

1. **Task 1: Shape 1 locator rework** — `235e587` (fix)
2. **Task 2: Shape 1 unit tests** — `59f1bd8` (test)
3. **Task 3: precondition redesign + figure-glyph + _NUMBER fix** — `8295930` (fix)

**Plan metadata:** (this commit) (docs)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_NUMBER` regex 漏抓 leading-dot real(`-.061` / `.06`)**
- **Found during:** Task 3(mixed-glyph regression 跑出 white_pct 5.73% + `option_b_parse_anomaly`,diagnostic 逐 q-block 追到 region fill block `1 0 0 1 609.4204 101.7188 cm 0 0 m -.061 0 l .06 0 l f*` 的 `-.061` 被 `_NUMBER` 只 match 到 `061`,bbox x1 從 609.48 失真為 670.42 → 漏抓)
- **Issue:** 舊 `_NUMBER = -?\d+\.?\d*` 要求 `.` 前必有整數位;PScript5 CAD glyph 大量使用無整數部的 real(ISO 32000-1 §7.3.3 合法)。這是 Plan 07-01 helper 與舊 Shape 1 locator 共有的 latent bug,也是 mixed-glyph 14% 命中率的決定性根因。
- **Fix:** `_NUMBER = [-+]?(?:\d+\.?\d*|\.\d+)`,同時涵蓋 leading-dot 與 trailing-dot real。修正後 mixed-glyph 框選區 100% 命中。
- **Files modified:** `app/services/pdf_engine.py`(`_NUMBER` 常數)
- **Verification:** mixed-glyph delete_zero_area_type_f_fills_inside → 3396/3396 matched / after count 0 / 1.12s;regression PASS。
- **Committed in:** `8295930`(Task 3 commit — 與 SCOPE 2/3 一併,因同屬「關閉 SEC-01」的最後一哩)

**Total deviations:** 1 auto-fixed(1 Rule 1 bug — 直接影響 SEC-01 primary gate 的 latent regex 漏抓)。
**Impact:** 不擴張 production scope(僅 `_NUMBER` 常數一行 + Shape 1 索引重寫,皆在 pdf_engine.py 內)。

## Stub / Threat scan

- **無新 stub。**
- **Threat flags:** 無新攻擊面 — Shape 1 rework 全在既有 pdf_engine.py helper 內;無新網路端點 / auth path / 檔案存取 / schema 變更。T-07-14(bbox-keyed cardinality 放寬)由「byte-range 只來自通過 STEP A 4-gate 的 zaf-bbox key + missing_keys 非空即 fail-safe + Task 2 genuine_miss 測試」緩解;T-07-15(perf DoS)由 single-pass 索引緩解(765s→<5s);T-07-16(SEC-01 核心威脅)由 Shape 1 真刪 + 雙閘緩解。

## Self-Check: PASSED

**檔案存在性:**
- FOUND: `app/services/pdf_engine.py`(`_build_shape1_candidate_index` 定義 line 1042 + 呼叫 line 1294;舊 `_locate_shape1_byte_range` 0 occurrences;`_NUMBER` leading-dot fix)
- FOUND: `tests/test_pdf_engine.py`(17 tests:14 + 3 Shape 1)
- FOUND: `tests/test_illustrator_attack_regression.py`(precondition 重設計)
- FOUND: `tests/fixtures/cad-glyph/figure-glyph-01.pdf` + `.json`(重新 sanitize,manifest `original_supplier_zero_area_count`=3225)
- FOUND: `.planning/phases/07-.../07-03-SUMMARY.md`(本檔)

**commit 存在性:**
- FOUND: `235e587`(Task 1, fix)
- FOUND: `59f1bd8`(Task 2, test)
- FOUND: `8295930`(Task 3, fix)

**驗收閘:**
- SEC-01 primary gate:`python -m pytest -k illustrator_attack -v` → 3 PASSED ✓
- 全套件:321 passed + 3 skipped + 0 xfailed + 0 failed ✓(≥318 達標)
- TEST-03:`tests/test_pdf_engine.py` 17 passed ✓
- AGPL seam 單行 + guard test PASSED ✓
- production scope(本 plan)僅 pdf_engine.py ✓
- mixed-glyph region perf 1.12s < 5s ✓
- figure-glyph PASS(非 skip/xfail)✓

---
*Phase: 07-option-b-implementation-content-stream-surgery*
*Completed: 2026-05-28*
