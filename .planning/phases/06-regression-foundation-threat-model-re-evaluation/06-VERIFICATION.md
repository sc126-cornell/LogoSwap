---
phase: 06-regression-foundation-threat-model-re-evaluation
verified: 2026-05-28T03:30:00Z
status: passed
score: 4/4 ROADMAP success criteria + 3/3 requirements + 10/10 phase-6 invariants verified
overrides_applied: 0
---

# Phase 6: Regression Foundation + Threat Model Re-evaluation — Verification Report

**Phase Goal:** 在動 Option B 實作之前先把「紅燈」立起來 — 收集 ≥3 個工程師手上實際出問題的 CAD-glyph supplier PDF 作為 sanitized fixture,把 2026-05-28 forensic 攻擊腳本改寫為 pytest regression test(此階段預期為紅),並同步更新威脅模型把 Illustrator-class editor attacker 列入 actor 清單。完成後 Phase 7 寫的 Option B 才有客觀「綠/紅」可驗。

**Verified:** 2026-05-28T03:30:00Z
**Status:** **PASSED**(含 documented PROVISIONAL exit per Wave 1 fallback)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths(ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | `tests/fixtures/cad-glyph/` 含 ≥3 個 sanitized supplier CAD-glyph PDF,涵蓋文字 glyph 與圖形 glyph representative shapes(metadata 已清,可入 git) | VERIFIED | `tests/fixtures/cad-glyph/` 含 3 個 .pdf(text-glyph-01 / figure-glyph-01 / mixed-glyph-01)+ 3 個 sidecar .json + README.md;每個 PDF 經 fitz.open 驗 author/producer/title/keywords/subject/creator 全為 clean(`metadata bad = clean` × 3);see SC verification block below |
| SC-2 | 對每個 fixture 跑「LogoSwap process → 攻擊腳本拔 image XObject overlay → render 框選區」的 pytest test 存在且**目前紅燈** | VERIFIED | `python -m pytest tests/test_illustrator_attack_regression.py -v` 顯示 3 個 XFAIL(figure-glyph-01 / mixed-glyph-01 / text-glyph-01),exit 0;Option B 未實作 → 攻擊成功 → xfail strict 攔截 |
| SC-3 | `_attack_delete_image_xobject.py` 邏輯已搬入 `tests/` 並以 pytest fixture 化呼叫,scratch 腳本可從 `.planning/debug/scratch/` 退役 | VERIFIED | `.planning/debug/scratch/illustrator-attack-2026-05-28/` 不存在(git mv 到 `…-archived/`);`_attack_delete_image_xobject.py` + `_check_supplier_removal.py` 已刪除;邏輯活於 `tests/_illustrator_attack.py`(3 exports) |
| SC-4 | `.planning/SECURITY.md`(或同等威脅模型文件)STRIDE 表新增 "Illustrator-class editor attacker" actor,T-02-07 從 "CLOSED with documented residual" 改回 "OPEN — Option B 落地後重新關閉" | VERIFIED | `.planning/phases/06-.../06-SECURITY.md` 存在,frontmatter threats_total: 2 / threats_open: 0 / threats_accepted: 2;含 STRIDE Actors 新增 `Illustrator-class editor attacker` actor;含 T-02-07 RE-OPENED narrative + T-06-01 NEW;disposition 文字明示 v1.0 LIVE Option A 對 CLI-only 仍生效,Phase 7 落地 Option B 後 close |

**Score:** 4/4 ROADMAP Success Criteria verified.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `scripts/sanitize_fixture.py` | Sanitization CLI(metadata clear + brand-glyph strip + TESTCO inject + self-assert) | VERIFIED | 存在(27654 bytes);Plan 06-01 acceptance criteria 全達(含 self-assert smoke test exit 2) |
| `tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.pdf` | 3 sanitized PDFs | VERIFIED | 3 個 PDF 全部存在,metadata 全 clean |
| `tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.json` | 3 sidecar manifests with split-coordinate schema | VERIFIED | 3 個 manifest 全部含 5 個 required keys: `region_rect_pdf_points`, `region_rect_px`, `dpi`, `page_index`, `expected_zero_area_count_pre_process` + 4 個 optional metadata(SHA256、commit SHA、ISO date、synthetic flag) |
| `tests/fixtures/cad-glyph/README.md` | Committed-binary exception 5-section 文件 | VERIFIED | 5 個 section 全部就位(why-exception / per-fixture sanitization log / immutability / AGPL §13 / cross-references);PROVISIONAL banner 在 header 標示 |
| `tests/_illustrator_attack.py` | Helper module with 3 exports | VERIFIED | 3 exports callable: `delete_image_xobjects_intersecting`、`render_region_white_pct`、`count_zero_area_fills_in_region`;scratch lines 84-115 verbatim regex + multi-stream write-back 保留 |
| `tests/test_illustrator_attack_regression.py` | Parametrize × xfail-strict regression test | VERIFIED | 3 parametrized cases × xfail-strict;decorator order parametrize@line 73 < xfail@line 74;JobSpec 構造正確(Risk Callout #1);Option B + SEC-01 cross-ref 在 reason string |
| `.planning/phases/06-.../06-SECURITY.md` | Pre-mortem STRIDE doc | VERIFIED | 346 lines,frontmatter threats_open: 0 + threats_accepted: 2 + supersedes [06-HOTFIX-SECURITY.md];STRIDE Actors 新增 Illustrator-class editor;T-02-07 RE-OPENED + T-06-01 OPEN(`accept (P0, transition-pending)`);Pre-mortem vs Audit-time variant section + Accepted Risks Log × 2 |
| `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/README.md` | Retirement note | VERIFIED | 5 sections;cross-ref `tests/_illustrator_attack.py` + `tests/test_illustrator_attack_regression.py` + `06-SECURITY.md` + `tests/fixtures/cad-glyph/` |
| `.gitignore` | Raw-PDF root + samples + archived guards | VERIFIED | 含 `3013A-13A-C6-XX-` (1 hit) + `illustrator-attack-2026-05-28-archived` (1 hit) anchored guards |

All artifacts pass Level 1 (exists), Level 2 (substantive, min_lines met), Level 3 (wired via imports + sidecar cross-references), and Level 4 (data flows — pytest collection + fixture json loads + actual xfail behavior observed).

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tests/test_illustrator_attack_regression.py` | `tests/fixtures/cad-glyph/*.pdf + *.json` | `_load_fixtures()` globs FIXTURES_DIR + json.loads sidecar | WIRED | `_load_fixtures()` 在 line 46-63;`sorted(FIXTURES_DIR.glob("*.pdf"))` + json.loads;pytest collected 3 cases |
| `tests/test_illustrator_attack_regression.py` | `app.services.pipeline.process_job` + `ingest.ingest_upload` + `app.models.JobSpec` | `pipeline.process_job(session_id, JobSpec(dpi, regions=[RegionMark(...)], logo_id=None))` | WIRED | `from app.models import JobSpec, RegionMark` + `from app.services import ingest, pipeline`;JobSpec 構造在 line 131-135 with correct shape per Risk Callout #1 |
| `tests/_illustrator_attack.py` | `app.services.pdf_engine.count_zero_area_fills_fully_inside` | function-internal `from app.services import pdf_engine` then delegate | WIRED | `count_zero_area_fills_in_region` 內 `from app.services import pdf_engine` (line 213) + `pdf_engine.count_zero_area_fills_fully_inside(doc[page_index], rect)` (line 217) |
| `tests/test_illustrator_attack_regression.py` xfail reason | `.planning/REQUIREMENTS.md` SEC-01 | 繁中 reason string 含路徑 cross-ref | WIRED | line 80: `"參 .planning/REQUIREMENTS.md SEC-01。"` |
| `.planning/phases/06-.../06-SECURITY.md` | `archived 06-HOTFIX-SECURITY.md` | frontmatter `supersedes:` list (T-02-07 disposition only) | WIRED | frontmatter line 15-16: `supersedes: - .planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md` |

All 5 key links verified.

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `tests/test_illustrator_attack_regression.py` | `pairs` (parametrize values) | `_load_fixtures()` glob + json.loads of real fixture .json files | YES (3 real param sets collected) | FLOWING |
| `tests/test_illustrator_attack_regression.py` | `session_id` | `ingest.ingest_upload(filename, raw_bytes)` returning SessionInfo | YES (real bytes read from fixture PDFs) | FLOWING |
| `tests/test_illustrator_attack_regression.py` | `output_pdf` | `pipeline.output_path(session_id)` | YES (assert exists; 3 cases all pass through `output_pdf.exists()`) | FLOWING |
| `tests/test_illustrator_attack_regression.py` | `n_deleted` | `delete_image_xobjects_intersecting(doc, ...)` real fitz pipeline | YES (XFAIL evidence shows attack precondition met + double-gate failure → expected red light) | FLOWING |

All data-flow traces confirm dynamic data threads from fixture .pdf+.json → ingest → process_job → attacked output → double-gate assert. The 3 XFAILs are produced by real attack mechanics, not stubs.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Attack regression test produces exactly 3 XFAILs | `python -m pytest tests/test_illustrator_attack_regression.py -v` | `3 xfailed in 2.13s`;each test displayed individually as XFAIL with fixture id | PASS |
| Full suite baseline matches expected | `python -m pytest` | `301 passed, 3 skipped, 3 xfailed in 13.54s` | PASS |
| AGPL guard test still green | `python -m pytest tests/test_redact.py::test_fitz_import_confined_to_engine_seam -v` | `1 passed in 0.29s` | PASS |
| AGPL seam grep | `grep -rn "import fitz" app/` | Only `app/services/pdf_engine.py:19` is a real `import fitz` statement (verified via AST walk); other matches are docstring/comment references | PASS |
| Production code zero changes since milestone v1.1 start | `git diff --stat c27ffea HEAD -- app/` | (empty output) | PASS |
| No raw supplier PDF tracked | `git ls-files \| grep -E '3013A-13A-C6-XX'` | (empty output) | PASS |
| Forensic history preserved | `git log --follow .planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png` | First commit returned: `0f14325 chore(06-02): retire …`; history preserved through git mv | PASS |
| Retired .py scripts absent | `ls .../illustrator-attack-2026-05-28-archived/_attack_delete_image_xobject.py _check_supplier_removal.py` | both "No such file or directory" | PASS |
| Old scratch dir absent | `ls .planning/debug/scratch/illustrator-attack-2026-05-28` | "No such file or directory" | PASS |
| Repo root raw PDF absent | `ls 3013A-13A-C6-XX-3D02-A01-00040.pdf` | "No such file or directory" | PASS |

All behavioral spot-checks pass.

---

### Phase 6 Specific Invariants(10 items)

| # | Invariant | Check | Result |
|---|-----------|-------|--------|
| 1 | AGPL seam preserved — single fitz import in app/ | AST walk across app/**/*.py | PASS (only `app/services/pdf_engine.py:19`) |
| 2 | Production code 0 changes | `git diff --stat HEAD~9 HEAD -- app/` | PASS (empty output) |
| 3 | xfail strict baseline — exactly 3 XFAIL | `python -m pytest tests/test_illustrator_attack_regression.py -v` | PASS (3 XFAIL, no skipped, no XPASS) |
| 4 | Full test suite baseline | `python -m pytest` | PASS (`301 passed, 3 skipped, 3 xfailed`) |
| 5 | AGPL guard test continues to pass | `python -m pytest tests/test_redact.py::test_fitz_import_confined_to_engine_seam` | PASS (1 passed) |
| 6 | No raw supplier PDF tracked anywhere | `git ls-files \| grep -E '3013A-13A-C6-XX'` | PASS (empty) |
| 7 | Forensic evidence history preserved | `git log --follow .../archived/_attack_proof_supplier_revealed.png` | PASS (returns commit 0f14325 — git mv rename detection works) |
| 8a | PATTERNS Risk Callout #1: JobSpec used in regression test | `grep -c "JobSpec" tests/test_illustrator_attack_regression.py` | PASS (≥1: line 34 import + line 131 construction) |
| 8b | PATTERNS Risk Callout #2: SECURITY frontmatter `threats_open: 0` AND `threats_accepted: 2` | Read frontmatter | PASS (lines 12-13 exact match) |
| 8c | PATTERNS Risk Callout #3: parametrize line < xfail line | line-based check | PASS (parametrize@73 < xfail@74) |
| 8d | PATTERNS Risk Callout #4: Asymmetric multi-stream write-back pattern | regex check for `if len==1 ... else ... [1:] update_stream("")` | PASS (verified asymmetric pattern present) |
| 9a | PROVISIONAL: 06-01-SUMMARY has `provisional: true` in frontmatter OR PROVISIONAL banner | Read 06-01-SUMMARY frontmatter | PASS (frontmatter line 7: `provisional: true` + line 8: `provisional_reason: …` + body line 61 banner) |
| 9b | PROVISIONAL: STATE.md has open blocker for engineer fixture replenishment | grep STATE.md | PASS (line 59: `Phase 6 fixture replenishment`) |
| 9c | PROVISIONAL: README notes synthetic fixtures | grep README.md Section 2 | PASS (line 35-36 contain `synthetic` markers; line 4 PROVISIONAL header banner) |
| 10a | Scratch retirement: archived dir exists | `ls archived/` | PASS (contains 4 PNG/PDF + README.md + raw 3013A.pdf untracked) |
| 10b | `_attack_delete_image_xobject.py` no longer tracked | ls check | PASS (absent) |
| 10c | `_check_supplier_removal.py` no longer tracked | ls check | PASS (absent) |
| 10d | Forensic PNGs/PDF still tracked | `ls archived/` | PASS (all 4: `_attack_proof_supplier_revealed.png`, `_attack_target_pre.png`, `_attack_orig_for_comparison.png`, `_attack_image_xobject_deleted.pdf`) |
| 10e | New README.md at archived dir points to tests/ | grep README.md | PASS (Section 2 + Section 4 cross-ref `tests/_illustrator_attack.py` + `tests/test_illustrator_attack_regression.py` + `06-SECURITY.md`) |

**All 10 Phase 6 invariants (incl. sub-points) PASS.**

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TEST-01 | 06-01-PLAN.md | ≥3 sanitized CAD-glyph fixtures in `tests/fixtures/cad-glyph/` | SATISFIED | 3 fixtures + 3 sidecar manifests + README + sanitize script + .gitignore guards — all delivered;PROVISIONAL state explicitly documented (2/3 synthetic) and tracked in STATE.md blocker |
| TEST-02 | 06-02-PLAN.md | Attack-simulation pytest regression test (red-light) | SATISFIED | `tests/test_illustrator_attack_regression.py` with parametrize × xfail-strict;3 XFAIL observed under `python -m pytest`;double-gate assert (white_pct ≥ 98 AND zero_area_count == 0) wired |
| THREAT-01 | 06-02-PLAN.md | STRIDE actor + T-02-07 RE-OPENED | SATISFIED | `06-SECURITY.md` adds Illustrator-class editor attacker actor;T-02-07 RE-OPENED narrative + T-06-01 NEW;frontmatter supersedes archived `06-HOTFIX-SECURITY.md`;both threats classified `accept (P0, transition-pending until Phase 7)` |

REQUIREMENTS.md status table confirms all three marked **Complete** at Phase 6.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|

No anti-patterns found in Phase 6 modified files:

- `tests/_illustrator_attack.py` — no TODO/FIXME/TBD/XXX/HACK
- `tests/test_illustrator_attack_regression.py` — no debt markers
- `scripts/sanitize_fixture.py` — no debt markers
- `.planning/phases/06-.../06-SECURITY.md` — no debt markers
- `.gitignore` — guards documented inline with comments (not debt markers)

The synthesize fallback in `sanitize_fixture.py` and the PROVISIONAL state are documented contingencies (Wave 1 fallback per Warning #6) tracked in STATE.md, not unresolved debt.

---

### Human Verification Required

None. All goal-backward verifications are objectively verifiable through:
- pytest output (3 XFAIL + 301 passed baseline observed)
- git ls-files / git log / git diff (empty / commit-present / empty)
- File existence + metadata cleanliness (fitz.open verified clean)
- AST walk for AGPL seam (single `import fitz` in `pdf_engine.py:19`)
- Frontmatter content checks (`threats_open: 0` + `threats_accepted: 2`)

The "PROVISIONAL exit condition" (2/3 fixtures synthetic, awaiting engineer real-PDF delivery) is a documented Phase 6 exit state per Wave 1 fallback contingency — it is not a verification gap. The blocker is captured in `.planning/STATE.md` for future maintenance.

---

### Gaps Summary

**None.** All ROADMAP Success Criteria, requirements, key links, artifacts, data-flow traces, behavioral spot-checks, and Phase 6 invariants verified. Production code untouched, AGPL seam intact, full test baseline `301 passed + 3 skipped + 3 xfailed` matches the expected Phase 6 close-state.

**PROVISIONAL note (informational, not a gap):** `text-glyph-01.pdf` and `figure-glyph-01.pdf` are synthetic (`--synthesize` fallback) because the engineer delayed delivering 2 additional supplier CAD-glyph PDFs. This is explicitly the Wave 1 fallback contingency (per 06-01-PLAN Fallback C + Warning #6) and is propagated to:
1. `06-01-SUMMARY.md` frontmatter (`provisional: true`)
2. `06-01-SUMMARY.md` body banner (line 61)
3. `tests/fixtures/cad-glyph/README.md` header (line 4) + Section 2 table
4. `.planning/STATE.md` Blockers section (line 59: `Phase 6 fixture replenishment` checkbox)
5. Commit message `a0bdb21` `[fixture PROVISIONAL: 1 real + 2 synthetic]`

The PROVISIONAL state does NOT block Phase 7 execution — the xfail-strict marker is correctly placed whether visual signatures are synthetic or real; Option B in Phase 7 must remove all in-region zero-area type='f' source paths regardless of glyph origin. When engineer delivers the remaining 2 real PDFs, `scripts/sanitize_fixture.py` can be rerun to replace the synthetic fixtures without altering the test logic.

---

### Phase 6 → Phase 7 Handoff Signal

Phase 7 implementer entry points:

1. **Locate the xfail marker:** `grep -rn "xfail.*Option B" tests/` finds the test file (matches the docstring self-reference at line 21; the marker reason string with `Option B` is in lines 77-80 of `tests/test_illustrator_attack_regression.py`).
2. **Expected behavior after Option B landing:** `python -m pytest -k illustrator_attack -v` should report 3 × XPASS(strict) → exit non-zero → implementer must remove the `@pytest.mark.xfail(...)` decorator (lines 74-82).
3. **Final baseline after handoff:** `304 passed, 3 skipped` (the 3 xfailed transition to passed).
4. **`07-SECURITY.md` should:** CLOSE T-02-07 + T-06-01 via Option B; list `06-SECURITY.md` in its `supersedes:` chain.

---

*Verified: 2026-05-28T03:30:00Z*
*Verifier: Claude (gsd-verifier)*

---

## Post-close maintenance addendum(2026-05-28)

**Trigger:** 工程師同日交付了 PROVISIONAL 所欠的 2 個 supplier PDF;原本「documented PROVISIONAL exit」狀態升級為 FINAL。

**Action items 與最終狀態:**

| 原 verification line | 原狀態 | 升級後狀態(commit) |
|---|---|---|
| 9a — 06-01-SUMMARY frontmatter `provisional: true` | PASS(with documented PROVISIONAL exit) | **frontmatter 更新為 `provisional: false`**(commit `f7f34e8`)+ 新增 `provisional_history` 欄位 + 新增 `§ Provisional → Final 升級記錄` section |
| 9b — STATE.md fixture replenishment blocker open | PASS | **blocker 標 RESOLVED**(commit `f7f34e8`)— STATE.md line 59 改為 `[x] ~~Phase 6 fixture replenishment~~ 〔已 RESOLVED 2026-05-28...〕` |
| 9c — README banner notes synthetic | PASS | **README banner 改為「✓ READY」**(commit `f7f34e8`)— Section 2 表格 synthetic 標記更新為 real-supplier raw PDF 來源 |

**Sanitize script 補強(commit `0045c6b`)— 推薦的下次 code-review 範圍:**

- 新增 `_redact_supplier_name_glyph(doc, page, supplier_name) -> int`(Impl note C)— glyph-level redaction 處理 CMap-encoded font
- 新增 `_delete_supplier_annotations(doc, page, supplier_name) -> int`(Impl note D)— 整塊刪除 Form-XObject stamp annotation
- 主流程加 fallback chain:Impl B 後若 supplier name 仍在 → 試 Impl C → 仍在則試 Impl D → 仍在才 exit 1
- 對未來其他 PScript5 / Acrobat 來源的 PDF 通用,降低人工介入需求

**Phase 6 close status 升級為 FINAL** — 3/3 fixture 為 real supplier(同供應商 `宁波登骐 / Ningbo Dengqi` 不同 SKU);PROVISIONAL exit 標記移除;不變式仍全綠(pytest `301 + 3 skipped + 3 xfailed` + AGPL seam + production code 0 changes + no raw supplier PDF tracked)。

*Addendum recorded: 2026-05-28(post-close maintenance round)*
