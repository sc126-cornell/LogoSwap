---
phase: 07-option-b-implementation-content-stream-surgery
verified: 2026-05-28T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  note: "初次 goal-backward verification(無前次 07-VERIFICATION.md)。本 phase 含 07-02 SUMMARY 自標 Self-Check FAILED,但後續 07-03 gap-closure plan 已關閉 SEC-01;本驗證直接對最終 codebase 狀態做反推。"
---

# Phase 7: Option B Implementation — Content-Stream Surgery 驗證報告

**Phase Goal:** 在 `app/services/pdf_engine.py`(AGPL seam)落地 Option B helper — 在 `apply_redactions` 之後、Option A overlay 之前 rewrite page-level content stream,刪除 fully-inside-rect 的零面積 type='f' `m/l/f/B` 算子序列。正常面積 vector PDF 需 no-op(SEC-02);form XObject 內部巢狀 path 需安全處理不誤改(SEC-03,page-level only + log)。完成後 Phase 6 紅燈攻擊測試應全綠。
**Verified:** 2026-05-28
**Status:** passed
**Re-verification:** No — initial verification(直接驗最終 codebase,涵蓋 07-01 / 07-02 / 07-03 三 plan 的累積結果)

## 目標達成度(Goal Achievement)

### Observable Truths(對應 ROADMAP 5 條 Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Phase 6「Illustrator 拔 image XObject → render 框選區」pytest 全綠 — render 區 ≥98% 白 + 框選區內 zero-area type='f' count == 0(content stream 真的被刪) | ✓ VERIFIED | `python -m pytest -k illustrator_attack -v` → **3 passed, 0 xfailed, 0 failed**(figure-glyph / mixed-glyph / text-glyph)。test body `tests/test_illustrator_attack_regression.py:174-185` 對**全部 3 個 parametrized fixture** 無條件斷言 `white_pct >= 98.0` AND `zero_area_count == 0`。content-stream gate(`count_zero_area_fills_in_region`,`tests/_illustrator_attack.py:238-263`)委派至 production `count_zero_area_fills_fully_inside`(讀 content stream,非僅渲染像素)→ mixed-glyph 通過必須是真刪而非 overlay 視覺遮蓋。 |
| 2 | 對 v1.0 既有 fixture(無 zero-area fill 正常 vector PDF)跑 full suite 仍綠,Option B no-op,baseline 不退步 | ✓ VERIFIED | `python -m pytest` → **321 passed + 3 skipped + 0 xfailed + 0 failed**(19.91s)。SEC-02 no-op 行為直接 spike 驗證:正常面積 300×100 vector PDF + 文字 → `delete_zero_area_type_f_fills_inside` return 0 + `read_contents()` bytes byte-for-byte 不變(SPOT-CHECK PASS)。 |
| 3 | Option B helper 單元測試覆蓋 zero-area counter、content-stream rewrite 邊界判定、form XObject 巢狀偵測(page-level only)、no-op、密度梯度(0/1/100/1742) | ✓ VERIFIED | `python -m pytest tests/test_pdf_engine.py -v` → **17 passed**:density gradient `[0][1][100][1742]` + 2 SEC-02 no-op/re-entrant + 5 safe-skip(BT/ET、paren、hex、comment、inline-image)+ 3 SEC-03 form-XObject + 3 Shape 1 高密度/重複-bbox/genuine-miss。 |
| 4 | `grep -rn "import fitz" app/` 仍只在 `app/services/pdf_engine.py` 一行 — AGPL seam 未破 | ✓ VERIFIED | 唯一實際 `import fitz` 語句在 `app/services/pdf_engine.py:21`(其餘命中皆為 docstring / comment 文字)。AGPL guard test `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` → **1 passed**。 |
| 5 | 框選區若位於 form XObject 內,系統不靜默誤改,以 log + safe-skip(SEC-03 page-level only) | ✓ VERIFIED | `log_xobject_intersect`(`pdf_engine.py:1377`)walk `page.get_xobjects()`,intersect 時 emit `option_b_xobject_intersect` warning(structured extra:page_index / user_rect / xobject_count)。`test_option_b_form_xobject_intersect_logged` + `test_option_b_form_xobject_internal_stream_untouched` 證明:log 觸發 + nested XObject xref stream 呼叫前後 bytes 不變(page-level only,不下鑽)。redact.py:220 在 dispatcher block 內呼叫 `log_xobject_intersect`。 |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/pdf_engine.py` | Option B helpers + single-pass Shape 1/2 索引 + safe-skip mask + cardinality fail-safe + log_xobject_intersect | ✓ VERIFIED | `delete_zero_area_type_f_fills_inside`(:1216)、`log_xobject_intersect`(:1377)、`_build_shape1_candidate_index`(:1042)、`_build_shape2_candidate_index`(:1138)、`_build_safe_skip_mask`(:987)、`_splice_out`(:1014)、`_NUMBER` leading-dot fix(:406)。舊 `_locate_shape1_byte_range` 已移除(僅 docstring 引用殘留)。STEP A get_drawings 4-gate(:1256-1272)、STEP D bbox-keyed cardinality fail-safe(:1325-1340)、STEP E asymmetric multi-stream write-back + compress=True(:1359-1372)。 |
| `app/services/redact.py` | line 195/197 boundary Option B dispatcher block + import logging + logger;既有 dispatcher 保留 | ✓ VERIFIED | Option B block(:205-220)在 residual_content raise(:199-203)之後、既有 dispatcher(:222-283)之前。`import logging`(:84)+ `logger`(:92)。`git diff b9cf8af..HEAD -- redact.py` 刪除行數 = **0**(僅新增 25 行)。既有 dense/sparse dispatcher(count_zero_area_fills_fully_inside / replace_region_with_white_raster / cover_zero_area_artefacts)字面保留。 |
| `tests/test_pdf_engine.py` | 17 TEST-03 unit tests | ✓ VERIFIED | 17 passed。fitz license header + in-memory fixtures。 |
| `tests/test_illustrator_attack_regression.py` | xfail decorator 移除 + parametrize 保留 + precondition 重設計 | ✓ VERIFIED | 無 `@pytest.mark.xfail`;`@pytest.mark.parametrize`(:73)保留;precondition 重設計(:165)只在「無 overlay 可拔 AND region 髒」失敗,兩道安全閘門檻(white≥98 / count==0)未放鬆。 |
| `tests/fixtures/cad-glyph/figure-glyph-01.{pdf,json}` | 重新 sanitize 含真實零面積攻擊面 | ✓ VERIFIED | 重新 sanitize 於 commit `8295930`(PDF 182371→197391 bytes);manifest `original_supplier_zero_area_count: 3225`、`synthetic: false`、`sanitization_script_commit_sha: 59f1bd8`。 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `redact.remove_region_vector` | `pdf_engine.delete_zero_area_type_f_fills_inside` | line 213 呼叫(傳 fitz.Rect `rect`) | ✓ WIRED | redact.py:213 + `from . import pdf_engine`(既有 import)。 |
| `redact.remove_region_vector` | `pdf_engine.log_xobject_intersect` | line 220 呼叫(logger=logger 注入) | ✓ WIRED | redact.py:220。 |
| `delete_zero_area_type_f_fills_inside` dispatch | `_build_shape1_candidate_index` | STEP C single-pass O(1) bbox-key 查表 | ✓ WIRED | pdf_engine.py:1294 呼叫;取代 per-zaf 全串流 finditer。 |
| `delete_zero_area_type_f_fills_inside` | `page.read_contents()` + `doc.update_stream` | STEP B read + STEP E multi-stream write-back | ✓ WIRED | pdf_engine.py:1278 read + :1368/:1370-1372 write-back(asymmetric [0]+empty[1:],compress=True)。 |
| `test_illustrator_attack_regression` | production removal pipeline | xfail 移除 → 真實執行 → 3 PASSED | ✓ WIRED | SEC-01 acceptance gate,3 passed。 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `delete_zero_area_type_f_fills_inside` | `ranges_to_delete` → `_splice_out` → `doc.update_stream` | `page.get_drawings()` 4-gate 過濾出的真實 ZAF → shape index byte-range | ✓ FLOWING | Spike: 50 distinct-bbox Shape 1 ZAF → deleted=50 + post-count=0;mixed-glyph 3396 ZAF → after count==0(regression PASS)。非靜態/空回傳。 |
| `log_xobject_intersect` | `n_intersecting` → logger.warning | `page.get_xobjects()` bbox.intersects(user_rect) | ✓ FLOWING | test 證明 intersect 時 n≥1 + warning emit,無 intersect 時 0 + 無 log。 |

### Behavioral Spot-Checks(verifier 自跑,非 SUMMARY 引用)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 高密度 Shape 1 真刪 | direct invoke:50 distinct-bbox m/l ZAF | before=50 deleted=50 after=0 | ✓ PASS |
| SEC-02 no-op | direct invoke:normal-area 300×100 vector + text | deleted=0 bytes_unchanged=True | ✓ PASS |
| SEC-01 acceptance | `pytest -k illustrator_attack -v` | 3 passed in 6.61s | ✓ PASS |
| Full baseline | `pytest` | 321 passed + 3 skipped, 0 failed/xfailed in 19.91s | ✓ PASS |
| TEST-03 unit | `pytest tests/test_pdf_engine.py -v` | 17 passed in 1.79s | ✓ PASS |
| AGPL guard | `pytest ...::test_fitz_import_confined_to_engine_seam -v` | 1 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SEC-01 | 07-02, 07-03 | 真正刪除零面積 type='f' fills(Illustrator 攻擊面關閉) | ✓ SATISFIED | 3 illustrator-attack regression PASS;mixed-glyph(3396 ZAF)content-stream gate count==0 + 白≥98%。 |
| SEC-02 | 07-01, 07-02, 07-03 | 正常面積 vector PDF no-op | ✓ SATISFIED | STEP A pre-screen short-circuit;spike + `test_option_b_no_op_on_normal_vector_pdf` bytes 不變。 |
| SEC-03 | 07-01, 07-02, 07-03 | page-level only + form XObject 不誤改 + log | ✓ SATISFIED | `log_xobject_intersect` + XObject internal stream untouched test + redact.py:220 wiring。 |
| TEST-03 | 07-01, 07-03 | 單元測試覆蓋(密度梯度 + safe-skip + form-XObject + no-op + 高密度/重複-bbox/genuine-miss) | ✓ SATISFIED | 17 passed,涵蓋全部要求面向。 |

### Phase-Specific Invariants(10 條,直接執行驗證)

| # | Invariant | Status | Evidence |
|---|-----------|--------|----------|
| 1 | AGPL seam:`import fitz` 僅 pdf_engine.py | ✓ | 唯一 import 語句 pdf_engine.py:21。 |
| 2 | Production scope:`git diff b9cf8af..HEAD -- app/` 僅 pdf_engine.py + redact.py | ✓ | diff --stat 確認 2 檔 604 insertions,無其他 app/**/*.py。 |
| 3 | 既有 dispatcher 不刪:redact.py 0 deletions | ✓ | `git diff b9cf8af..HEAD -- redact.py | grep -c '^-[^-]'` = 0。 |
| 4 | SEC-01 gate:3 illustrator_attack PASSED | ✓ | 3 passed(figure / mixed / text)。 |
| 5 | SEC-02 + baseline:321 passed + 3 skipped + 0 xfailed | ✓ | full suite 321/3/0/0。(注:實際 N=321,高於 plan 預估 318;含 07-03 新增 3 Shape 1 unit + 3 flipped attack。) |
| 6 | AGPL guard test 1 passed | ✓ | test_fitz_import_confined_to_engine_seam passed。 |
| 7 | TEST-03 coverage:Option B unit tests passing(含 density + safe-skip + form-XObject + no-op + 高密度 + 重複-bbox + genuine-miss) | ✓ | 17 passed,逐項命名確認。 |
| 8 | mixed-glyph 真刪(SEC-01 core):assert white_pct ≥98 AND zero_area_count == 0(content-stream gate) | ✓ | test body :174-185 對全 3 fixture 無條件雙閘;content-stream gate 委派 production count helper。 |
| 9 | D-A5 fail-safe:genuine parse anomaly → return 0 + warning(不 raise) | ✓ | `test_option_b_shape1_genuine_miss_failsafe`:mixed-item ZAF → deleted=0 + bytes 不變 + option_b_parse_anomaly logged。code :1325-1340 return 0 無 raise。 |
| 10 | SEC-03 log_xobject_intersect:frame intersect form XObject 時 log | ✓ | `test_option_b_form_xobject_intersect_logged` 證明 warning emit + structured extra。 |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (無) | — | — | — | `app/services/pdf_engine.py` 與 `app/services/redact.py` 均無 TBD / FIXME / XXX / HACK / placeholder / not-implemented 等 debt marker 或 stub。 |

### Human Verification Required

(無 — 本 phase 為 service 層 content-stream 改動,所有驗收皆可由 pytest regression + content-stream count + 直接 helper spike 程式化驗證。ROADMAP success criteria 全為可測行為;視覺攻擊驗收已由 `render_region_white_pct` ≥98% 像素閘自動化。)

### Gaps Summary

無 gap。

**關於 07-02-SUMMARY 自標 `Self-Check: FAILED`:** Plan 07-02 整合 Option B wiring 後,SEC-01 acceptance gate(3 regression case)當時 FAIL,根因為 Plan 07-01 helper 在高密度真實 supplier stream(mixed-glyph 3396 ZAF)的 Shape 1 locator perf(765s)+ cardinality 漏抓(14% 命中)。此 gap 已由後續 **Plan 07-03 gap-closure** 完全關閉:(a) Shape 1 locator 重寫為 single-pass `_build_shape1_candidate_index`(perf 765s→1.12s);(b) cardinality 改 bbox-keyed Option (ii)(重複-bbox 全刪);(c) `_NUMBER` leading-dot regex fix(`-.061` / `.06`,14%→100% 命中決定性根因);(d) attack precondition 重設計;(e) figure-glyph 自 B-3012IP 真實零面積 cluster 重新 sanitize。本 verification 對**最終 codebase 狀態**做反推,確認 SEC-01 gate 現已通過(3 PASSED),Phase goal 達成。

**T-06-01 / T-02-07 close evidence:** mixed-glyph(高密度真實 supplier)通過 → Option B 真刪 page-level 零面積 source → Illustrator 拔 image XObject overlay 後 content stream 內無內容可重現(白 100% + count 0)。Phase 6 繼承的 T-06-01 + T-02-07 具備 `CLOSED via Option B` 的客觀證據(07-SECURITY.md 若 gsd-secure-phase 跑可正式記錄)。

---

_Verified: 2026-05-28_
_Verifier: Claude (gsd-verifier)_
