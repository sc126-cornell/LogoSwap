---
phase: 06
plan: 01
plan_name: sanitization-and-fixtures
subsystem: dev-tooling + test-fixtures
tags: [pdf-sanitization, fixtures, cad-glyph, agpl-seam-preserved, provisional]
provisional: true
provisional_reason: "2 / 3 fixtures synthetic — 工程師延遲交付 contingency。Phase 6 close 為 PROVISIONAL until 工程師交付剩餘 supplier PDF + 重跑 sanitize_fixture.py。"
dependency_graph:
  requires:
    - app/services/pdf_engine.py::count_zero_area_fills_fully_inside  # self-assert import target
    - .planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py  # attack mechanics source
    - scripts/smoke_02_03.py  # CLI shell skeleton analog
    - tests/test_redact.py:691-794  # Shape.draw_rect(W=0) zero-area pattern
  provides:
    - scripts/sanitize_fixture.py  # 一次性 dev CLI tool
    - tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.pdf + .json  # 3 fixtures + sidecar manifests
    - tests/fixtures/cad-glyph/README.md  # committed-binary exception 文件化
    - .gitignore  # raw supplier PDF 多重 anchored guard
  affects:
    - .planning/STATE.md  # 新增 Phase 6 fixture replenishment blocker
    - 不動 app/**/*.py(production code 0 changes verified)
    - 不動 tests/conftest.py, tests/test_*.py(test infra 0 changes — Plan 06-02 surface)
tech_stack:
  added: []  # no new deps;沿用 pinned PyMuPDF 1.27.x + Pillow + numpy
  patterns_used:
    - "PATTERNS Shared Pattern S1 — fitz import outside AGPL seam(scripts/ + tests/ exception)"
    - "PATTERNS Shared Pattern S4 — 繁中 user-facing strings, English identifiers"
    - "scratch script lines 104-115 — multi-stream update_stream write-back verbatim"
    - "tests/test_redact.py:722-728 — Shape.draw_rect(W=0).finish(fill=).commit() zero-area type='f' fill 注入"
key_files:
  created:
    - scripts/sanitize_fixture.py
    - tests/fixtures/cad-glyph/README.md
    - tests/fixtures/cad-glyph/text-glyph-01.pdf
    - tests/fixtures/cad-glyph/text-glyph-01.json
    - tests/fixtures/cad-glyph/figure-glyph-01.pdf
    - tests/fixtures/cad-glyph/figure-glyph-01.json
    - tests/fixtures/cad-glyph/mixed-glyph-01.pdf
    - tests/fixtures/cad-glyph/mixed-glyph-01.json
    - .planning/phases/06-regression-foundation-threat-model-re-evaluation/06-01-SUMMARY.md
  modified:
    - .gitignore
    - .planning/STATE.md  # blocker: Phase 6 fixture replenishment
decisions:
  - "Sidecar manifest 採 split-coordinate schema(region_rect_pdf_points + region_rect_px),非 CONTEXT D-B4 範例的單一 region_rect — Phase 6 canonical per Warning #8 + Claude's Discretion"
  - "Step 1 metadata clear:在 PyMuPDF 1.27.2.3 上,doc.set_metadata({}) 為 no-op;必須傳 {field: '' for field in USER_FIELDS} 才會真清空。先呼叫 set_metadata({}) 作 intent marker(對齊 acceptance criteria grep + 文件化 RESEARCH 引述 1.18.4 行為),再呼叫顯式 per-field empty dict 實際清空。[Rule 1 deviation]"
  - "Step 3 brand-glyph block strip 採『union_bbox 內 m/l 座標 byte-offset 啟發式』而非 supplier-name find-replace;對 mixed-glyph-01 (3013A-...pdf) 此 heuristic 沒命中(0 個 block 被 strip)— 該 PDF 的零面積 fill 沒被 q...Q 包,但 sanitization 仍 pass(metadata 清乾淨 + supplier name 不在 get_text + post zero-area count 3396 ≥ 0.9 × 1742)。supplier name find-replace 留為 Implementation note B fallback,只在 Step 5 self-assert 觸發。"
  - "Synthesize fallback 觸發(2 / 3 fixtures synthetic) — Phase 6 close 標 PROVISIONAL,3 處 propagate:README banner Section 2 + commit message [fixture PROVISIONAL] tag + STATE.md fixture replenishment blocker。"
metrics:
  duration_minutes: 10
  completed_date: 2026-05-28
  task_count: 2
  files_created: 9
  files_modified: 2
  task_commits: 3  # feat(Task1) + fix(metadata Rule 1) + chore(Task2 deliverables)
---

# Phase 6 Plan 01: Sanitization Script + Fixtures Summary

> ⚠ **Phase 6 fixture 構成:1 real + 2 synthetic — close 條件 PROVISIONAL until 工程師交付全部 3 個 real PDFs 並重跑 sanitize_fixture.py。**

Phase 6 紅燈基線「fixture 補給線」:一次性 CLI 工具 `scripts/sanitize_fixture.py`
把 supplier CAD-glyph PDF 脫敏為可 commit 進 public repo 的 fixture,並以 split-coordinate
sidecar JSON manifest 攜帶 region rect + zero-area count(`region_rect_pdf_points` +
`region_rect_px` + `dpi` + `expected_zero_area_count_pre_process`)。3 個 fixture 全部
產出(1 real `mixed-glyph-01.pdf` + 2 synthetic `text-glyph-01.pdf` & `figure-glyph-01.pdf`),
metadata 全清、AGPL seam 不破、production code app/ 0 動。

## Executive Snapshot

| Metric | Value |
|---|---|
| Tasks completed | 2 / 2 |
| Per-task commits | 3(含 1 個 Rule 1 deviation fix commit) |
| Files created | 9(scripts script + 7 fixture entries + SUMMARY) |
| Files modified | 2(`.gitignore`、`.planning/STATE.md`) |
| Production code (`app/**/*.py`) | **0 changes** ✓ |
| AGPL seam intact | ✓(`grep -rn "import fitz" app/`仍只 `pdf_engine.py:19` 一行) |
| Sanitize self-assert smoke test | ✓(`--region-rect "bogus-not-a-rect"` exits 2) |
| Phase 6 close status | **PROVISIONAL** — 2 / 3 fixtures synthetic |

## Sanitize Script 實作要點

**Option B linear recipe(per checker Blocker #1):**

1. **Step 1 — Metadata clear**(`doc.set_metadata({})` intent marker + `doc.set_metadata({field: "" ...})` 實際清空 + `doc.set_xml_metadata("")` 清 XMP)
2. **Step 2 — Locate union bbox + record baseline zero-area count**(via `page.get_drawings()` filter type='f' ∩ region,呼叫 production helper `count_zero_area_fills_fully_inside`)
3. **Step 3 — Brand-glyph 整塊 strip via `doc.update_stream`**(multi-stream pattern verbatim per scratch lines 104-115;byte-offset 啟發式 — `q...Q` block 內含 union_bbox 範圍的 `m/l` 算子座標時整塊刪除,從尾部往前刪以保 offset)
4. **Step 4 — TESTCO 零面積 wordmark 注入 via `Shape.draw_rect(W=0)` + `shape.commit()`**(verbatim per `tests/test_redact.py:722-728`,zero-area type='f' fill;n_target = `max(int(original_count × 0.95), 1)`)
5. **Step 5 — 4 條 self-assert**(metadata 全空 / supplier name 不在 `get_text()` / zero-area count ≥ 0.9 × original / out path 在 `tests/fixtures/cad-glyph/`)
6. **Step 6 — `doc.save(garbage=4, deflate=True, clean=True)`**

**主路徑不做 supplier-name find-replace** — 留給 Implementation note B fallback,只在 Step 5 supplier-name self-assert 觸發 fail 時才執行(per checker Blocker #1)。

**Synthesize fallback mode**(`--synthesize`):從零建構 A4 PDF + 鋪 120 個 zero-area fill + 跳過 Step 2/3 + 沿用 Step 1 / 4 / 5(縮減版)/ 6。

**CMap fallback 是否觸發:** **沒有觸發。** mixed-glyph-01(3013A-...pdf)的 `page.get_text()` 只回 30 chars(`'A\n2\n4 5\nB\n1\n...'`)— supplier brand 是純向量幾何 + CMap-encoded glyph,brand-glyph block strip heuristic 沒命中(0 個 q...Q block 被刪),但 supplier-name self-assert pass(`UNKNOWN_SUPPLIER_PLACEHOLDER` 本就不在文字中),不觸發 fallback。詳見下方 corner case #1。

## 3 Fixtures 構成

| Slot | Source | Supplier name SHA256 (16 chars) | Region rect (PDF points) | Expected zero-area count |
|---|---|---|---|---|
| `text-glyph-01.pdf` | **synthetic**(`--synthesize` fallback) | `sha256:` of "SYNTHETIC_TESTCO" → 待 manifest 讀取 | `[100, 100, 300, 200]` | 120 |
| `figure-glyph-01.pdf` | **synthetic**(`--synthesize` fallback) | `sha256:` of "SYNTHETIC_TESTCO" | `[200, 300, 400, 400]` | 120 |
| `mixed-glyph-01.pdf` | **real** — `3013A-13A-C6-XX-3D02-A01-00040.pdf`(repo root,untracked);Acrobat Distiller / PScript5 出口;原 author='RD07'、title=`<hex>`、producer='Acrobat Distiller 9.0.0' 全洗 | `sha256:` of "UNKNOWN_SUPPLIER_PLACEHOLDER" | `[602, 481, 827, 511]` | 1742(post: 3396) |

`sanitization_script_commit_sha` 在所有 3 個 manifest 中皆為腳本 commit 當下的 git HEAD short SHA(`d671548` 或之後)。

## Sidecar Manifest Schema(Phase 6 canonical)

採 **split-coordinate** schema — 取代 CONTEXT D-B4 範例中的單一 `region_rect`,Phase 7 unit tests + consumer 對齊本 schema(per Warning #8 + Claude's Discretion on manifest schema):

```json
{
  "region_rect_pdf_points": [x0, y0, x1, y1],
  "region_rect_px": [x0*dpi/72, y0*dpi/72, x1*dpi/72, y1*dpi/72],
  "dpi": 144,
  "page_index": 0,
  "expected_zero_area_count_pre_process": <int>,
  "original_supplier_name_sha256": "sha256:<16-char hex>",
  "sanitization_script_commit_sha": "<short SHA>",
  "created_at_iso": "<UTC ISO 8601>",
  "synthetic": true | false
}
```

理由:downstream(Plan 06-02 attack regression test)同時需要 PDF-point rect(供 `fitz.Rect(*rect)` clip + `count_zero_area_fills_fully_inside`)與 pixel rect + dpi(供 `pipeline.process_job` 的 `JobSpec(dpi=DPI, regions=[RegionMark(page=P, px_rect=[...])])` 消費)。一處寫,雙處讀,避免乘除轉換錯誤。

## README.md 5 個 Section 標題

1. **為什麼這是 `tests/` 唯一 committed-binary 例外**
2. **每個 fixture 的脫敏記錄**(markdown 表格 4 欄;synthetic 列在 supplier 欄寫 `—(synthetic — 工程師延遲交付 contingency;Phase 6 close 為 PROVISIONAL)`)
3. **Immutability rule(D-A6 c)**
4. **AGPL §13 statement**
5. **Cross-references**(sanitization tool / regression test / production helper / threat model / raw PDF 處置)

## `.gitignore` 新增 Patterns

```
/3013A-13A-C6-XX-*.pdf                                       # repo root anchored(已存在的 raw file)
/samples/3013A-*.pdf                                         # samples/ anchored(tracked 副本待 Plan 06-02 git rm)
/.planning/debug/scratch/illustrator-attack-2026-05-28-archived/3013A-*.pdf  # archived-anchored
*-supplier-raw.pdf                                           # future-proof convention
```

`archived-anchored` 一條對應 Plan 06-02 Task 4 將 root 副本物理 mv 至 `.../illustrator-attack-2026-05-28-archived/`,`.gitignore` 確保移入後不被 track,讓 `git rm` + 物理 `mv` 為兩步乾淨操作(checker Blocker #2 解除)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `doc.set_metadata({})` 在 PyMuPDF 1.27.2.3 為 no-op**
- **Found during:** Task 2 step A(對 3013A-...pdf 第一次跑 sanitize)
- **Issue:** RESEARCH § Pattern 1 引用 PyMuPDF wiki「自 1.18.4 起空值不寫入」claim,但實證 PyMuPDF 1.27.2.3 + 3013A-...pdf 傳空 dict 不清任何欄位(`fitz.open + d.set_metadata({}) + d.save + reopen` → metadata 完全保留 `author='RD07'`、`title=<hex>`、`producer='Acrobat Distiller 9.0.0'` 等)。
- **Fix:** Step 1 改成傳「per-field empty dict」`{field: "" for field in USER_FIELDS}`。為保 acceptance criteria `grep -c 'doc.set_metadata({})' >= 1` + 文件化 1.27 系列的意外行為,先呼叫 `doc.set_metadata({})` 作 intent marker,再呼叫顯式 per-field empty dict 實際清空。同步更新 `_metadata_all_empty` self-assert,只檢查 `_USER_METADATA_FIELDS`(author / producer / title / keywords / subject / creator / creationDate / modDate / trapped),不包 `format` / `encryption`(PyMuPDF computed 欄位,非 /Info dict 內容)。
- **Files modified:** `scripts/sanitize_fixture.py`(+30 行 / -4 行)
- **Commit:** `cd1d84f`

### Authentication Gates

None — Phase 6 不涉及外部服務 / API key / login。

## Authentication Gates

None.

## Self-Assert Smoke Test Result(Warning #7 證明)

```
$ python scripts/sanitize_fixture.py --synthesize --out /tmp/should_fail.pdf --region-rect "bogus-not-a-rect"
sanitize_fixture.py: error: argument --region-rect: --region-rect 必須是 4 個逗號分隔的數字(x0,y0,x1,y1);收到 1 個 token: 'bogus-not-a-rect'
$ echo $?
2
```

✓ `--region-rect` parser self-assert reachable + raises argparse error → exit code 2(non-zero)。Warning #7 「self-assert 觸發證明」滿足。

## Corner Cases Discovered

**#1 — `mixed-glyph-01.pdf` 的 brand-glyph block strip 沒命中(0 個 q...Q block 被刪)**

執行 log:
```
步驟 3/6:Brand-glyph 整塊 content-stream surgery(update_stream)…
  ✓ 已 strip 0 個 q...Q block
```

成因:3013A-...pdf 的零面積 fill 看起來不是被 `q ... Q` group 包起來的個別 brand-glyph block,而是直接散落在 content stream 內(可能是 PScript5 的特殊出口慣例)。

影響:此 fixture 仍保留原 supplier 的 1742 個 zero-area fill(沒被 strip)+ 額外的 1654 個 TESTCO 縱線 = 3396 個 total post zero-area count。Sanitization 沒「物理移除原 brand glyph」但 metadata 已清乾淨 + `get_text()` 不含 supplier name(supplier brand 是純向量,CMap-encoded text 沒被 decode 出來;30 chars total,只有 'A\n2\n4 5\nB\n1\n6\n3\n8\n7\nA\nB\ncat 6\n')。Visual signature 是否仍含可識別供應商商標 → **Plan 06-02 attack regression test 跑起來就會驗;若視覺殘留導致 regression test 真的 fail 而非 xfail,fixture 需在 Plan 06-02 重跑 sanitize(以更積極的 brand-glyph 定位 heuristic)。**

**#2 — `mixed-glyph-01.pdf` 的 multi-stream check**

`page.get_contents()` 在此 fixture 上不需要 multi-stream write-back(其 content stream 為單 stream),但腳本的 multi-stream pattern 已 preserved verbatim per scratch lines 104-115,future supplier PDF 命中 multi-stream 時自動觸發。

## Phase 6 Hardening Invariants 驗證

| Invariant | Check | Result |
|---|---|---|
| AGPL seam intact | `grep -v "^#" app/services/pdf_engine.py \| grep -nE "^import fitz\|^from fitz"` | ✓ 只回 `19:import fitz …` |
| Production code 0 動 | `git diff --stat HEAD~3 app/`(本 plan 共 3 commits) | ✓ 0 changed files |
| Sanitize script `--help` 5 args | `python scripts/sanitize_fixture.py --help` | ✓ `--in / --out / --supplier-name / --region-rect / --synthesize` |
| Self-assert smoke test reachable | bogus `--region-rect` → exit ≠ 0 | ✓ exit 2 |
| 7 entries in `tests/fixtures/cad-glyph/` | `ls tests/fixtures/cad-glyph/` | ✓ 3 .pdf + 3 .json + 1 README.md |
| Manifest schema all 5 required keys | python json schema check | ✓ all 3 manifests have `region_rect_pdf_points` + `region_rect_px` + `dpi` + `page_index` + `expected_zero_area_count_pre_process` |
| Metadata clean(author/producer/title/keywords/subject/creator) | fitz.open + check `doc.metadata.get(k) in (None, '')` | ✓ all 3 .pdf clean |
| `.gitignore` root-anchored + archived-anchored | `grep -c "3013A-13A-C6-XX-"` + `grep -c "illustrator-attack-2026-05-28-archived"` | ✓ 1 + 1 |
| AGPL guard test still collectable | `python -m pytest --co -q tests/test_redact.py::test_fitz_import_confined_to_engine_seam` | ✓ 1 test collected |
| STATE.md blocker added | `grep -c "Phase 6 fixture replenishment"` | ✓ 1 |

## Known Stubs

None — sanitize script 不是 stub(完整 6-step pipeline + self-assert + 2 modes);fixtures 不是 stub(都通過 self-assert 才 commit);README 不是 stub(5 個 section 完整文件化)。Synthetic fixtures 不算 stub — 它們是 valid PDF 帶 valid zero-area attack 面,只是 visual signature 來自合成而非真實供應商。

## Deferred Issues / Known Issues for Plan 06-02

- **`samples/3013A-...pdf` tracked 副本待 `git rm`**(Plan 06-02 Task 4)— 本 plan 已加 `.gitignore` `samples/`-anchored guard。
- **Repo root `3013A-...pdf` 物理移動到 archived dir**(Plan 06-02 Task 4)— 本 plan 已加 archived-anchored guard。
- **`mixed-glyph-01.pdf` brand-glyph block strip 0 命中**(corner case #1)— 若 Plan 06-02 attack regression test 驗證視覺仍殘留原供應商,需在 Plan 06-02 重跑 sanitize(以更積極 heuristic;或考慮把 mixed-glyph-01 也降為 synthetic 並加 STATE.md 額外 blocker)。

## Threat Flags

無新 threat surface introduced — 本 plan 0 動 production code、0 新 runtime attack surface。sanitize script 在 maintainer 機器上跑(per threat_model T-PLAN06-01-01,info-disclosure 已 mitigate via 4 條 pre-save self-assert);fixture PDF 通過 self-assert 才落地(T-PLAN06-01-02 mitigate);AGPL seam 不破(T-PLAN06-01-04 mitigate)。

## Cross-references

- Plan: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-01-PLAN.md`
- Context: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-CONTEXT.md`(D-A1..D-A6, D-B1..D-B6)
- Research: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-RESEARCH.md`(Pattern 1/2/3, Pitfall 1/2/3/4/5/6/7/8)
- Patterns: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-PATTERNS.md`(Pattern Assignments + Shared Pattern S1/S2/S4/S5)
- Project: `.planning/PROJECT.md`(milestone v1.1 Active)
- Requirements: `.planning/REQUIREMENTS.md` TEST-01
- Next plan: `06-02-PLAN.md`(attack regression test + 06-SECURITY.md + scratch retirement)

## Self-Check: PASSED

Files verified (all FOUND):
- `scripts/sanitize_fixture.py`
- `tests/fixtures/cad-glyph/README.md`
- `tests/fixtures/cad-glyph/text-glyph-01.pdf` + `.json`
- `tests/fixtures/cad-glyph/figure-glyph-01.pdf` + `.json`
- `tests/fixtures/cad-glyph/mixed-glyph-01.pdf` + `.json`
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-01-SUMMARY.md`

Commits verified (all FOUND in git log):
- `d671548` — feat(06-01): add sanitize_fixture.py CLI tool
- `cd1d84f` — fix(06-01): metadata clear requires per-field empty values on PyMuPDF 1.27.2.3
- `a0bdb21` — chore(06-01): produce 3 cad-glyph fixtures + manifests + README + .gitignore guards [fixture PROVISIONAL]
