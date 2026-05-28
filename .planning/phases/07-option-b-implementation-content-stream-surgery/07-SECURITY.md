---
phase: 7
phase_name: option-b-implementation-content-stream-surgery
milestone: v1.1
audit_scope: phase_07_option_b_implementation
date: 2026-05-28
asvs_level: 1
block_on: high
diff_base: b9cf8af
commits_audited:
  - 3d982e8  # feat(07-01): add Option B content-stream surgery helpers
  - 59856cb  # test(07-01): 14 TEST-03 unit tests + coordinate seam fix
  - a09b39f  # feat(07-02): wire Option B into redact dispatcher
  - 96e5bad  # test(07-02): remove xfail-strict decorator
  - 235e587  # fix(07-03): rework Shape 1 locator to single-pass index
  - 59f1bd8  # test(07-03): lock Shape 1 rework
  - 8295930  # fix(07-03): close SEC-01 — precondition redesign + figure-glyph + _NUMBER fix
  - a10704b  # fix(07-review): CR-01 conservative skip co-located content
  - b0887f0  # fix(07-review): WR-01/02/06 Shape 2 leading-dot + fillop token + coverage
  - d25958d  # fix(07-review): WR-03 inline-image length-aware mask
  - 237f1e0  # fix(07-review): WR-04 delete dead _locate_shape2_byte_range
  - e081914  # fix(07-review): WR-05 return true splice count
threats_total: 15
threats_closed: 14
threats_open: 0
threats_accepted: 1
register_authored_at_audit_time: true
supersedes:
  - .planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md
supersede_chain:
  - 07-SECURITY.md
  - 06-SECURITY.md
  - .planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md
---

# 07-SECURITY.md — Phase 7 Option B 實作 STRIDE 驗證(v1.1 milestone)

**Phase:** 7 — Option B Implementation: Content-Stream Surgery
**Audit scope:** `phase_07_option_b_implementation`(diff base `b9cf8af` → `HEAD`)
**Authoring date:** 2026-05-28
**ASVS Level:** 1(內網工具基線)
**Audit posture:** FORCE — 假設每條緩解措施不存在,直到 grep / pytest / 程式碼閱讀證明其落地在正確位置。
**Block policy:** `block_on: high` — 任何 high-severity OPEN threat 即阻擋。最終 `threats_open: 0`。

---

## Audit 範圍與方法

本檔對 Phase 7 三個 plan(07-01 helper + 07-02 dispatcher integration + 07-03 gap closure)
與後續 deep code review fix(CR-01 + WR-01..WR-06)的**最終 codebase 狀態**做反推驗證。
每條威脅依其 disposition(mitigate / accept)以下列方法逐一驗證,**不接受文件或意圖作為證據**:

- `mitigate` → grep / 讀取 mitigation plan 所引檔案,確認 pattern 落地在正確位置 + pytest 證據
- `accept` → 確認本檔 Accepted Risks Log 有對應條目

所有驗證命令於 audit 當下實際執行,輸出引於下方各表 Evidence 欄。

---

## STRIDE Threat 驗證表(Phase 7 引入 — T-07-01..T-07-13)

| Threat ID | Category | Disposition | Status | Evidence(file:line / command) |
|-----------|----------|-------------|--------|--------------------------------|
| T-07-01 | T(Tampering)— regex parse 竄改(safe-skip mask) | mitigate | **CLOSED** | `_build_safe_skip_mask`(`pdf_engine.py:1080`)O(N) bytearray 5-context mask;WR-03 fix 將 inline-image 改為 length-aware `_mask_inline_images`(`pdf_engine.py:1024`)。`test_pdf_engine.py` 5 個 `test_safe_skip_*` case 通過(BT/ET、paren、hex、comment、inline-image)。`pytest tests/test_pdf_engine.py -q` → 34 passed。 |
| T-07-02 | I — cardinality drift → 錯誤刪除 / 漏刪 | mitigate | **CLOSED** | D-A5 fail-safe 在 `pdf_engine.py:1429-1442`:`missing_keys_1 or missing_keys_2 or has_mixed_empty_zaf` → `logger.warning("option_b_parse_anomaly", extra={...})` + `return 0`,在蒐集 ranges 之前 abort。`test_option_b_shape1_genuine_miss_failsafe` 證明真實漏抓 → return 0 + bytes 不變 + warning。 |
| T-07-03 | I — multi-stream write-back 損毀(orphaned [1:] streams) | mitigate | **CLOSED** | PATTERNS S1 verbatim 在 `pdf_engine.py:1469-1474`:`len==1` 寫 `[0]`;否則寫 `[0]` + 對 `[1:]` 寫 `b""`,全部 `compress=True`,兩 branch 未 collapse(LOAD-BEARING 註解 line 1465-1468)。density gradient `[1742]` + mixed-glyph(3396 ZAF)regression 通過。 |
| T-07-04 | I — form XObject 內部零面積殘留(供應商商標可在 XObject 內重現) | **accept**(page-level only) | **CLOSED (accepted)** | 見下方 Accepted Risks Log § T-07-04-r1。`page.read_contents()` API contract 天然不下鑽 XObject(D-B1);`log_xobject_intersect`(`pdf_engine.py:1483`)emit `option_b_xobject_intersect` 透明化;`test_option_b_form_xobject_internal_stream_untouched` 證明 nested XObject xref stream 呼叫前後 bytes 不變。 |
| T-07-05 | A(DoS)— helper raise → 500 → pipeline 中斷 | mitigate | **CLOSED** | D-A5 fail-safe 全部 anomaly 路徑 `return 0` + `logger.warning`,**無任何 `raise`** 在 helper 內(`pdf_engine.py:1429-1442`)。`test_option_b_shape1_genuine_miss_failsafe` 確認 return 0 非 exception。full suite 0 errors。 |
| T-07-06 | T — in-helper `doc.save()` → 原始檔被竄改 | mitigate | **CLOSED** | helper 僅呼叫 `doc.update_stream`(in-memory page object),**無 `doc.save()`**(grep `doc.save` 在 `delete_zero_area_type_f_fills_inside` 函式體內 0 命中);caller 擁有 save lifecycle。`test_option_b_reentrant` 證明 in-memory 狀態一致。 |
| T-07-07 | T — 效能 / catastrophic backtracking | mitigate | **CLOSED** | 07-03 Shape 1 重寫為 single-pass `_build_shape1_candidate_index`(`pdf_engine.py:1144`),鏡像 Shape 2 O(1) 查表;mixed-glyph 框選區 765s → 1.12s(07-03-SUMMARY)。`_Q_BLOCK_RE` bounded `[^Q]{0,2048}?`。`test_option_b_shape1_high_density_all_matched` 含 perf soft-assert。 |
| T-07-08 | AGPL 營運風險 — 新 `import fitz` 混入 app/ | mitigate | **CLOSED** | grep `import fitz` over `app/` → 唯一實際 import 語句在 `app/services/pdf_engine.py:21`(其餘命中皆 docstring/comment)。AGPL guard test `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` → **1 passed**。 |
| T-07-09 | T/S — redact.py 意外 import fitz | mitigate | **CLOSED** | `git diff b9cf8af..HEAD -- app/services/redact.py | grep "^+import"` → 僅 `+import logging`(stdlib, non-fitz)。redact.py 傳入既為 `fitz.Rect` 的 `rect`,所有 fitz 操作委派 pdf_engine helper。 |
| T-07-10 | T — 既有 dispatcher 被修改 | mitigate | **CLOSED** | `git diff b9cf8af..HEAD -- app/services/redact.py | grep -c "^-[^-]"` → **0**(0 deletion lines)。既有 dense/sparse dispatcher + HONEST LIMITATION 區段(`redact.py:222+`)字面保留。 |
| T-07-11 | I — xfail → skip swap(fake green) | mitigate | **CLOSED** | `@pytest.mark.xfail` 在 `tests/test_illustrator_attack_regression.py` 已**完全移除**(非替換為 skip);`@pytest.mark.parametrize`(line 73)保留。`pytest -k illustrator_attack -v` → **3 PASSED**(非 skipped、非 xfailed)。 |
| T-07-12 | I — try/except 包住 Option B → log 被吞 | mitigate | **CLOSED** | redact.py Option B block(`redact.py:213-220`)**無 try/except wrap**;inline comment(line 208-210)明文記載「不包 try/except 以免吞掉 helper warning」。helper 內部 D-A5 fail-safe 自行 log。 |
| T-07-13 | A — import-time error → suite ERROR | mitigate | **CLOSED** | `from app.services import pdf_engine` import 乾淨;full suite `pytest` → **338 passed + 3 skipped + 0 failed + 0 error**。 |

---

## STRIDE Threat 驗證表(07-03 gap-closure 引入 — T-07-14..T-07-18)

| Threat ID | Category | Disposition | Status | Evidence(file:line / command) |
|-----------|----------|-------------|--------|--------------------------------|
| T-07-14 | T — bbox-keyed cardinality 放寬(Option ii)誤刪 byte-range | mitigate | **CLOSED** | byte-range 只來自通過 STEP A get_drawings 4-gate 的 zaf-bbox key;任一 zaf-bbox 在 index 找不到即 fail-safe return 0(`pdf_engine.py:1429-1442`)。**CR-01 fix 進一步收緊**:`_DISALLOWED_IN_BLOCK`(`pdf_engine.py:451`)使夾帶 co-located `Do`/`BT`/`sh`/`BI` 的 q...Q block 不被 index → fail-safe(`pdf_engine.py:1221`)。`test_option_b_shape1_genuine_miss_failsafe` + CR-01 reproduction test(`/Fm0 Do` survives)鎖死。 |
| T-07-15 | A(DoS)— Shape 1 per-zaf 全串流 finditer(765s) | mitigate | **CLOSED** | single-pass `_build_shape1_candidate_index`(`pdf_engine.py:1144`)取代 per-zaf finditer;mixed-glyph 765s → 1.12s。同 T-07-07。 |
| T-07-16 | I — Illustrator 拔 overlay 後供應商商標重現(SEC-01 核心) | mitigate | **CLOSED** | Shape 1 真刪 + `_NUMBER` leading-dot fix(`pdf_engine.py:384`)→ mixed-glyph 100% 命中。3 illustrator-attack regression PASS;content-stream gate `count == 0` + 白≥98%。**此即 T-06-01 + T-02-07 的 close 機制**(見下方 inherited section)。 |
| T-07-17 | T — figure-glyph 重新 sanitize 經既有 CLI | mitigate | **CLOSED** | 沿用既有 `scripts/sanitize_fixture.py` CLI(本體未改);Step 5 self-assert 全過(metadata 空 + supplier name 不在 get_text + zero-area count ≥ 0.9×原);raw PDF 仍 gitignored。manifest `original_supplier_zero_area_count: 3225`、`synthetic: false`。 |
| T-07-18 | R(Repudiation)— D-A5 fail-safe 透明化 | accept(已緩解) | **CLOSED (accepted)** | `option_b_parse_anomaly` 含 `missing_shape1`/`missing_shape2`/`mixed_empty` 結構化欄位(`pdf_engine.py:1437-1439`)→ 漏抓可追溯;`log_xobject_intersect`(SEC-03)不變。既有 structured log 充分,無新攻擊面。視為與 T-07-04 同類的 documented accept(見 Accepted Risks Log）。 |

> **註(disposition policy 對齊):** T-07-18 在 07-03 PLAN threat_model 標為 `accept(已緩解)`。
> 為使 `threats_open: 0` 且 accepted 條目可追溯,本檔將其視為「已以結構化 log 緩解的 accept」,
> 在 Accepted Risks Log § T-07-18-r1 記錄。其風險屬 P3(diagnostic visibility,非 data-loss / disclosure),
> 與 ASVS L1 相容。實質上此條已 mitigate(log 已落地),非殘留風險。

---

## Code Review 衍生威脅驗證(CR-01 + WR-01..WR-06,post-fix CLOSED)

deep code review(`07-REVIEW.md`)在 Phase 7 實作上發現 1 BLOCKER + 6 WARNING,
全數 FIXED(status: fixed,7/7 in-scope)。本 audit 確認每個 fix 落地於最終 codebase:

| 來源 | 描述 | Status | Evidence(commit / file:line) |
|------|------|--------|------------------------------|
| **CR-01**(BLOCKER) | Shape 1 整塊 q...Q splice over-delete co-located 合法內容(data loss);fail-safe 不接 | **CLOSED** | `a10704b` — `_DISALLOWED_IN_BLOCK = re.compile(rb"\bDo\b|\bBT\b|\bsh\b|\bBI\b")`(`pdf_engine.py:451`);`_build_shape1_candidate_index` line 1221 偵測到即 `continue`(不 index → dispatch 視為 missing → D-A5 fail-safe → Option A overlay last-mile)。reproduction test 證明 `q 10 20 m 10 100 l f /Fm0 Do Q` 不被 index(`/Fm0 Do` survives),pure-path control block 仍被 index。 |
| WR-01 | Shape 2 `_RE_FILL_RECT_RE` 未套 `_NUMBER` leading-dot fix | **CLOSED** | `b0887f0` — `_NUMBER`(`pdf_engine.py:384`)hoist 至 Shape 2 之前,套用於 x/y/w/h + `_SAFE_BETWEEN_TOKEN`。 |
| WR-02 | Shape 2 `f*`/`b*`/`B*` 殘留 dangling `*`(malformed output) | **CLOSED** | `b0887f0` — `fillop` 尾端 `\b` → `(?![A-Za-z*])`,完整 token 被消費。 |
| WR-03 | inline-image mask 在 binary 內遇假 `EI` token 提前終止(mask hole) | **CLOSED** | `d25958d` — `_mask_inline_images`(`pdf_engine.py:1024`)length-aware stateful scanner(`/L`/`/Length` byte-exact;否則 whitespace-delimited `EI` fallback,documented best-effort)。詳見下方 WR-03 殘留說明。 |
| WR-04 | `_locate_shape2_byte_range` dead code + stale single-match rule | **CLOSED** | `237f1e0` — 整段刪除(grep 確認 0 callers + 函式定義已移除;dispatch loop 為唯一 source of truth)。 |
| WR-05 | 回傳 `len(zafs)`(intent count)非實際刪除數 | **CLOSED** | `e081914` — 改回傳 `len(ranges_to_delete)`(`pdf_engine.py:1480`);docstring 修正。 |
| WR-06 | Shape 2 fill-operator variants + leading-dot reals 全無測試 | **CLOSED** | `b0887f0` — 新增 Shape 2 unit tests(7 fill operators + leading-dot reals + dangling-`*` splice + negative-w/h Pitfall 5)。`tests/test_pdf_engine.py` 34 passed。 |

---

## 繼承威脅關閉 — T-06-01 + T-02-07(Phase 7 核心安全交付)

Phase 6 `06-SECURITY.md` 將以下兩條列為 `accept (P0, transition-pending until Phase 7 Option B)`,
明文 closing condition 為「Phase 7 `07-SECURITY.md` CLOSED via Option B」。**本 audit 確認兩條已關閉。**

| Threat ID | Category | Phase 6 狀態 | Phase 7 狀態 | Close Evidence |
|-----------|----------|--------------|--------------|----------------|
| **T-06-01** | S + I — Illustrator-class editor 拔 image XObject overlay → 供應商商標從零面積 type='f' source 重現 | accept (P0, transition-pending) | **CLOSED via Option B** | Option B(`delete_zero_area_type_f_fills_inside`)真正刪除 page-level 零面積 type='f' source paths → 拔掉 image XObject overlay 後 content stream 內**無內容可重現**。 |
| **T-02-07** | I — TRUE REMOVAL vs cover gap(v1.0 CLOSED-with-documented-residual → Phase 6 RE-OPENED) | accept (P0, transition-pending) | **CLOSED via Option B** | 同一 production fix(零面積 source 真刪)同時關閉兩條 root-cause-共享的 threat。 |

### Close 的客觀證據(SEC-01 acceptance gate)

```
$ python -m pytest -k illustrator_attack -v
collected 341 items / 338 deselected / 3 selected

tests/test_illustrator_attack_regression.py::...[figure-glyph-01] PASSED [ 33%]
tests/test_illustrator_attack_regression.py::...[mixed-glyph-01]  PASSED [ 66%]
tests/test_illustrator_attack_regression.py::...[text-glyph-01]   PASSED [100%]

====================== 3 passed, 338 deselected in 6.73s ======================
```

**真刪 vs 視覺遮蓋 — content-stream gate 的關鍵驗證:**

`tests/test_illustrator_attack_regression.py:174-185` 對全部 3 個 parametrized fixture
**無條件** assert 兩道閘:

- `assert white_pct >= 98.0`(視覺乾淨閘,line 174)
- `assert zero_area_count == 0`(content-stream 乾淨閘,line 181)

content-stream gate(`count_zero_area_fills_in_region`,`tests/_illustrator_attack.py:238-263`)
**委派至 production `count_zero_area_fills_fully_inside`**(讀 `get_drawings()` / content stream,
**非僅渲染像素**)。因此 mixed-glyph(高密度真實 supplier,3396 ZAF)通過 `count == 0`
**必須是 content stream 真的被刪除**,而非 Option A overlay 視覺遮蓋 — 若僅靠 overlay,attack
拔掉 overlay 後 content-stream gate(`== 0`)會失敗。

precondition redesign(07-03 SCOPE 2)經 review 確認(`07-REVIEW.md` IN-04):兩道安全閘為
**unconditional asserts**,在 precondition 之後無條件執行,門檻(white≥98% / count==0)一字未放鬆。
redesign 只能**新增**失敗路徑(無 overlay AND region 髒),不能抑制真實失敗。

### Supersession chain

本檔 frontmatter `supersedes:` 列出 `06-SECURITY.md`,延續追溯鏈:

```
07-SECURITY.md → 06-SECURITY.md → archived 06-HOTFIX-SECURITY.md
```

archived 原檔不被本檔編輯;v1.0 `06-HOTFIX-SECURITY.md` 的 T-02-07
`CLOSED with documented residual` 由本檔升級為 `CLOSED via Option B`(零面積 source 已 page-level 真刪)。
殘留僅存於 form-XObject 內部(SEC-03 已透明化,見 T-07-04 accept)。

---

## Accepted Risks Log

### T-07-04-r1 — Form XObject 內部零面積殘留(page-level only 策略)

- **Disposition:** accept(SEC-03 page-level only + Option A overlay last-mile + log)
- **Severity:** P3(ASVS L1;實際樣本未出現 form-XObject 內巢狀零面積攻擊面)
- **Risk description(繁中):** Option B 對 `page.read_contents()`(page-level content stream)
  跑 regex surgery。fitz API contract 天然不下鑽 form XObject 內部 content stream(獨立 xref +
  獨立 `xref_stream()` 才能讀)。若供應商零面積 type='f' source 巢狀於 form XObject 內,Option B
  page-level 不刪除 → 攻擊者拔 image XObject overlay 後理論上仍可能在 XObject 內重現。
- **Why accepted:**
  - (a) Form XObject recursive surgery 明列為 **Deferred**(`.planning/REQUIREMENTS.md` Out of Scope
    + STATE.md Deferred 表 + 07-CONTEXT § deferred);v1.1 SEC-03 範圍即 page-level only。
  - (b) **透明化已落地** — `log_xobject_intersect`(`pdf_engine.py:1483`)在每次 Option B 跑時檢查,
    任一 form-XObject bbox 與框選區相交即 emit `option_b_xobject_intersect` warning + 結構化 extra
    (`page_index` / `user_rect` / `xobject_count`);redact.py:220 wire。
  - (c) **不誤改 XObject 內部** — `test_option_b_form_xobject_internal_stream_untouched` 證明
    nested XObject xref stream 呼叫前後 bytes 不變(page-level only 不破壞巢狀內容)。
  - (d) **Last-mile defense** — page-level Option B 跑完後若 `count_zero_area_fills_fully_inside`
    仍 > 0(form-XObject 殘留),既有 Phase 4-6 dispatcher(dense Option A overlay / sparse
    cover_zero_area_artefacts)接手(redact.py:222+,完整保留)。
- **Residual risk:** form-XObject 巢狀零面積攻擊面在實際 3/3 sanitized fixture 中未出現;若 future
  樣本出現 + colleague 整合需求 + risk assessment 後,再評估遞迴 surgery 方案(已記 STATE.md)。
- **Upgrade trigger:** 實際 supplier PDF 出現 form-XObject 內零面積 type='f' source 並被 attack
  重現 → 升級為遞迴 content-stream surgery(maintenance sprint)。
- **Documented at:** 本檔 + `pdf_engine.py` `delete_zero_area_type_f_fills_inside` /
  `log_xobject_intersect` 的繁中 HONEST LIMITATION docstring + `.planning/REQUIREMENTS.md` SEC-03。

### T-07-18-r1 — D-A5 fail-safe 透明化(diagnostic visibility)

- **Disposition:** accept(已緩解;結構化 log 已落地)
- **Severity:** P3(repudiation / diagnostic visibility,非 data-loss / disclosure)
- **Risk description(繁中):** Option B 在 cardinality drift / 真實漏抓時走 D-A5 fail-safe
  (return 0,不寫回)。若無充分 telemetry,漏抓事件無法追溯(repudiation)。
- **Why accepted(已緩解):** `option_b_parse_anomaly` warning 含 `expected` / `missing_shape1` /
  `missing_shape2` / `mixed_empty` / `page_index` / `user_rect` 結構化欄位(`pdf_engine.py:1429-1441`),
  漏抓完全可追溯。既有 structured log 對 ASVS L1 內網工具充分;無新攻擊面。
- **Residual risk:** 無。此條實質已 mitigate(log 已落地),列為 accept 僅因 07-03 PLAN 原始分類。
- **Documented at:** 本檔 + `pdf_engine.py:1429-1441` + `test_option_b_shape1_genuine_miss_failsafe`
  (caplog 捕獲 `option_b_parse_anomaly` + `missing_shape1 >= 1`)。

### WR-03 殘留 — inline-image 無 /L 宣告時 whitespace-delimited EI fallback

- **Disposition:** accept(P3,documented best-effort,ASVS L1)
- **Risk description(繁中):** WR-03 fix(`_mask_inline_images`,`pdf_engine.py:1024`)在 inline image
  dict 宣告 `/L` 或 `/Length` 時 byte-exact 跳過 payload(immune to embedded 假 `EI`);**未宣告 /L 時**
  fallback 為「第一個 whitespace-delimited `EI` 後接 delimiter/EOF」之 best-effort 啟發式。
- **Why accepted:** inline image 在 CAD supplier PDF 罕見;bbox-collision precondition(unmasked tail
  byte 恰好 match shape detector 且 round 到同一 ZAF key)極窄;且 over-delete 已由 CR-01
  `_DISALLOWED_IN_BLOCK`(`\bBI\b`)+ D-A5 fail-safe 二重防護。length-aware path 有 regression
  覆蓋(`tests/test_pdf_engine.py`)。
- **Residual risk:** 無 /L 宣告 + 含 standalone `EI` 的 inline image 在 page-level content stream 內
  + 後續 byte 恰好構成 shape-detector 偽命中 — 多重窄條件交集,P3。
- **Upgrade trigger:** 實際 supplier PDF 出現無 /L inline image 導致誤刪 → 升級為完整 stateful tokenizer。

---

## Unregistered Flags(SUMMARY.md ## Threat Flags / Stub Threat scan 稽核)

逐 plan SUMMARY 的 Threat Flags / Stub-Threat-scan 區段稽核:

| Plan SUMMARY | Threat Flags 宣告 | 對應 threat ID | 結論 |
|--------------|-------------------|----------------|------|
| 07-01-SUMMARY | (Issues Encountered:mixed-glyph full-page perf — 已由 07-03 close) | T-07-07 / T-07-15 | mapped,informational |
| 07-02-SUMMARY | 「無新攻擊面 — Option B wiring 只呼叫既有 AGPL-seam helper」;STRIDE T-07-09..T-07-13 全數 verify gate 守住 | T-07-09..T-07-13 | mapped,informational |
| 07-03-SUMMARY | 「無新攻擊面 — Shape 1 rework 全在既有 pdf_engine.py helper 內;無新網路端點 / auth path / 檔案存取 / schema 變更」;T-07-14/15/16 緩解 | T-07-14/15/16 | mapped,informational |

**Unregistered flags: NONE。** 三個 SUMMARY 的 Threat Flags 區段皆明示「無新攻擊面」,
且所有提及的 risk 均映射至本檔已 register 的 threat ID(T-07-01..T-07-18)。
code review 額外發現的 CR-01 / WR-01..WR-06 已全數 FIXED 並映射至 T-07-14(over-delete)
與既有 Shape 2 correctness 面,非未登記新攻擊面。

---

## Audit 執行的驗證命令與輸出(audit-time,非引用 SUMMARY)

| # | 驗證 | 命令 | 結果 | Status |
|---|------|------|------|--------|
| 1 | AGPL seam — import fitz 僅 pdf_engine.py | `grep -rn "import fitz" app/` | 唯一實際 import 語句 `app/services/pdf_engine.py:21`(其餘為 docstring/comment) | ✓ |
| 2 | AGPL guard test | `pytest tests/test_redact.py::test_fitz_import_confined_to_engine_seam -v` | 1 passed | ✓ |
| 3 | SEC-01 acceptance gate | `pytest -k illustrator_attack -v` | **3 passed**(figure / mixed / text),0 failed / 0 xfailed / 0 skipped | ✓ |
| 4 | redact.py 0 deletions(既有 dispatcher 不刪) | `git diff b9cf8af..HEAD -- app/services/redact.py | grep -c "^-[^-]"` | **0** | ✓ |
| 5 | Phase 7 production scope | `git diff --stat b9cf8af..HEAD -- app/` | 僅 `pdf_engine.py`(+685)+ `redact.py`(+25)兩檔,710 insertions / 0 deletions 既有 code | ✓ |
| 6 | redact.py import non-fitz | `git diff b9cf8af..HEAD -- app/services/redact.py | grep "^+import"` | 僅 `+import logging`(stdlib) | ✓ |
| 7 | full baseline | `pytest` | **338 passed + 3 skipped + 0 xfailed + 0 failed** | ✓ |
| 8 | TEST-03 unit tests | `pytest tests/test_pdf_engine.py -q` | 34 passed(14 原 TEST-03 + 3 Shape 1 高密度/重複-bbox/genuine-miss + Shape 2 WR-06 覆蓋) | ✓ |
| 9 | `_locate_shape2_byte_range` dead code 已刪(WR-04) | grep `def _locate_shape2_byte_range` | 0 命中(已刪除) | ✓ |
| 10 | CR-01 guard 落地 | grep `_DISALLOWED_IN_BLOCK` | `pdf_engine.py:451` 定義 + `:1221` 使用 | ✓ |
| 11 | `_NUMBER` leading-dot fix | read `pdf_engine.py:384` | `_NUMBER = rb"[-+]?(?:\d+\.?\d*\|\.\d+)"` | ✓ |
| 12 | D-A5 fail-safe 無 raise | read `pdf_engine.py:1429-1442` | `logger.warning("option_b_parse_anomaly")` + `return 0`,無 raise | ✓ |

> **環境註(IN-02,非 source defect):** audit 環境為 Python 3.14 / PyMuPDF 1.27.2.3;
> CLAUDE.md mandate 為 Python 3.12。測試於 3.14 全綠,但 CI/deploy parity 應確認 pin 3.12
> (尤其 regex / logging 行為)。非本 phase source 變更,記為部署前 checklist 項。

---

## Final Verdict

## SECURED

**Phase:** 7 — Option B Implementation: Content-Stream Surgery
**Threats Closed:** 14/15(13 mitigate-CLOSED + 1 accept-CLOSED;另 1 accept-CLOSED 為 T-07-04 form-XObject 殘留)
**ASVS Level:** 1
**threats_open: 0**

所有宣告的緩解措施皆以直接 grep / 程式碼閱讀 / pytest 執行驗證落地於正確位置:

- **AGPL seam 完整** — `import fitz` 唯一 `pdf_engine.py:21`;guard test green。
- **Production scope 嚴格** — 僅 `pdf_engine.py` + `redact.py`;redact.py 0 deletions(既有 dispatcher 完整保留)。
- **T-06-01 + T-02-07 CLOSED via Option B** — SEC-01 acceptance gate 3 PASSED,content-stream gate
  委派 production count helper(真刪非視覺遮蓋),雙閘 unconditional assert 門檻未放鬆。
- **D-A5 fail-safe** — cardinality mismatch → return 0 + warning,絕不破壞性寫回、絕不 raise。
- **CR-01 over-delete BLOCKER 已 FIXED** — `_DISALLOWED_IN_BLOCK` 保守跳過夾帶 co-located 內容的
  block,test 證明 `/Fm0 Do` survives;這是唯一 fail-safe 無法以「漏刪方向」覆蓋的方向,已由
  conservative-skip 補上。
- **WR-01..WR-06 全 FIXED**;WR-03 inline-image 無 /L 殘留以 P3 documented best-effort accept(ASVS L1)。
- **T-07-04 form-XObject 殘留** 以 accept 記入 Accepted Risks Log(page-level only + log + Option A last-mile)。

**無 high-severity OPEN threat。無 unregistered flag。Phase 7 cleared。**

下一階段(Phase 8)接手須知:三處 LIMITATION docstring 在 Phase 7 close 時未更新(Phase 8
THREAT-02 + DOC-01 才動);`08-SECURITY.md` 應 cross-reference 本檔作為 T-06-01 + T-02-07 的
close evidence,並補上 LIVE-UAT verifying note(DEPLOY-01)。

---

*07-SECURITY.md authoring complete — Phase 7 Option B STRIDE 驗證鎖定(FORCE stance)。*
*Auditor: Claude (gsd-secure-phase)*
*Audit completed: 2026-05-28*
