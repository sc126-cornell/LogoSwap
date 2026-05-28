---
phase: 06
plan: 02
plan_name: attack-regression-and-security
subsystem: test-harness + threat-model-docs
tags: [pytest, xfail-strict, illustrator-attack, stride, threat-model, scratch-retirement, agpl-seam-preserved]
dependency_graph:
  requires:
    - tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.pdf  # Plan 06-01 fixtures
    - tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.json  # Plan 06-01 sidecar manifests
    - app/services/pdf_engine.py::count_zero_area_fills_fully_inside  # production helper (delegate target)
    - app/services/pipeline.py::process_job  # JobSpec consumer
    - app/services/ingest.py::ingest_upload  # entrypoint
    - app/models.py::JobSpec + RegionMark  # request schema (06-PATTERNS Risk Callout #1)
    - tests/conftest.py:298-307  # isolated_data_dir autouse
    - tests/conftest.py:336-354  # logo_library fixture
    - .planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py  # scratch source (NOW DELETED post-port)
  provides:
    - tests/_illustrator_attack.py  # 3 exports (helper module)
    - tests/test_illustrator_attack_regression.py  # parametrized xfail-strict regression
    - .planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md  # pre-mortem STRIDE
    - .planning/debug/scratch/illustrator-attack-2026-05-28-archived/README.md  # retirement note
  affects:
    - .planning/debug/scratch/illustrator-attack-2026-05-28/  # renamed to -archived/
    - .planning/debug/scratch/illustrator-attack-2026-05-28-archived/  # .py scripts deleted, README added
    - samples/3013A-13A-C6-XX-3D02-A01-00040.pdf  # git rm + physical relocate to archived
    - 3013A-13A-C6-XX-3D02-A01-00040.pdf  # repo root copy physically mv'd to archived
    - 不動 app/**/*.py(production code 0 changes verified)
tech_stack:
  added: []  # no new deps;沿用 pinned PyMuPDF 1.27.x + Pillow + numpy + pytest
  patterns_used:
    - "PATTERNS Shared Pattern S1 — fitz import outside AGPL seam(tests/ exception per conftest.py:12)"
    - "PATTERNS Shared Pattern S2 — pipeline entrypoint via JobSpec(NOT raw dict)"
    - "PATTERNS Shared Pattern S3 — isolated_data_dir autouse"
    - "PATTERNS Shared Pattern S4 — 繁中 user-facing strings, English identifiers"
    - "PATTERNS Shared Pattern S5 — gsd-secure-phase frontmatter schema(pre-mortem variant)"
    - "PATTERNS Risk Callout #1 — process_job(session_id, JobSpec instance)正確構造"
    - "PATTERNS Risk Callout #2 — threats_open: 0 + threats_accepted: 2 framing"
    - "PATTERNS Risk Callout #3 — @parametrize ABOVE @xfail(decorator order)"
    - "PATTERNS Risk Callout #4 — multi-stream update_stream write-back verbatim(scratch lines 104-115)"
    - "06-RESEARCH Pitfall 4 — pytest --runxfail 不可用(docstring 註記)"
    - "06-RESEARCH Pitfall 5 — strict_xfail 不設 ini global default"
    - "06-RESEARCH Pitfall 6 — sorted(Path.glob()) 保穩定"
    - "06-RESEARCH Pitfall 8 — fitz 容錯渲染欺騙;雙閘 (a)+(b) 必須兩個都 assert"
key_files:
  created:
    - tests/_illustrator_attack.py  # 219 lines, 3 exports + 2 private helpers
    - tests/test_illustrator_attack_regression.py  # 177 lines, 1 parametrized + xfail-strict test
    - .planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md  # 346 lines, pre-mortem STRIDE
    - .planning/debug/scratch/illustrator-attack-2026-05-28-archived/README.md  # 5 sections, 繁中
    - .planning/phases/06-regression-foundation-threat-model-re-evaluation/06-02-SUMMARY.md
  modified:
    - .planning/debug/scratch/illustrator-attack-2026-05-28/ -> -archived/  # git mv rename
  deleted:
    - .planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_delete_image_xobject.py  # logic ported to tests/
    - .planning/debug/scratch/illustrator-attack-2026-05-28-archived/_check_supplier_removal.py  # logic ported / dropped
    - samples/3013A-13A-C6-XX-3D02-A01-00040.pdf  # raw supplier PDF removed from git index
decisions:
  - "Phase 6 production code 0 changes invariant 嚴守:每個 task 後 git diff --stat HEAD app/ empty;最終 AGPL guard test 仍綠(tests/test_redact.py::test_fitz_import_confined_to_engine_seam PASSED)"
  - "tests/_illustrator_attack.py 採 VERBATIM-port 策略:scratch lines 40-49 / 70-74 / 84-94 / 96-102 / 104-115 五段邏輯逐字搬入,僅改寫為 typed exports;multi-stream write-back 不對稱 pattern 保留兩個 branch(per Risk Callout #4 — 不整理為單一 loop)"
  - "xfail strict decorator order:@parametrize 在文字位置 line 73(上)+ @xfail 在 line 74(下,緊鄰 function);Python decorator 由下而上 application 確保 parametrize 展開 3 cases 各自帶 xfail marker(per Risk Callout #3)"
  - "process_job 走 JobSpec instance 而非 raw dict — 沿用 app/models.py:77-139 Pydantic schema(dpi + regions[RegionMark(page, px_rect)] + logo_id=None for pure removal D-01 contract per test_process_api.py:270-316)"
  - "06-SECURITY.md frontmatter threats_open: 0 + threats_accepted: 2 framing:兩條 threat 皆 accept (P0, transition-pending until Phase 7),符合 gsd-secure-phase non-block 條件(per RESEARCH § Assumptions A3 + Risk Callout #2)"
  - "Scratch retirement:git mv 為 single atomic 操作(全部 6 entries tracked,不需 fallback);.py 用 git rm -f(因 git mv 已 stage,需 -f 強制處理 staged index);samples/3013A-... 用 git rm(working-tree 同步移除);repo root 副本物理 mv(原本 untracked + .gitignore root-anchored 已屏蔽,直接 mv 安全)"
metrics:
  duration_minutes: 12
  completed_date: 2026-05-28
  task_count: 4
  files_created: 5
  files_modified: 1  # scratch dir rename
  files_deleted: 3  # 2 .py + 1 samples/.pdf
  task_commits: 4  # feat(Task1) + test(Task2) + docs(Task3) + chore(Task4)
---

# Phase 6 Plan 02: Attack Regression + 06-SECURITY.md + Scratch Retirement Summary

Phase 6 紅燈基線「attack-simulation pytest + STRIDE 重評 + scratch 退役」三大交付完整落地:`tests/_illustrator_attack.py` helper(3 exports,VERBATIM-port scratch lines 40-115)+ `tests/test_illustrator_attack_regression.py` parametrize × xfail-strict(3 fixture × 1 case = 3 XFAIL)+ `06-SECURITY.md` pre-mortem STRIDE(Illustrator-class editor actor + T-02-07 RE-OPENED + T-06-01 OPEN,兩條皆 `accept (P0, transition-pending until Phase 7)`)+ scratch dir 重命名 `-archived/` + 退役 2 個 `.py` 攻擊腳本 + 清乾淨 repo 內所有 raw supplier PDF。Production code `app/` 0 動、AGPL seam intact、pytest baseline 從 v1.0 close 的 `301 passed + 3 skipped` 升級為 Phase 6 close 的 `301 passed + 3 skipped + 3 xfailed`(3 xfailed 為 Phase 6 → Phase 7 binding handoff signal)。

## Executive Snapshot

| Metric | Value |
|---|---|
| Tasks completed | 4 / 4 |
| Per-task commits | 4(feat + test + docs + chore) |
| Files created | 5(2 test code + 1 SECURITY doc + 1 archived README + 1 SUMMARY) |
| Files renamed | 1 dir + 4 entries(scratch → archived) |
| Files deleted | 3(2 retired .py + 1 raw supplier PDF from index) |
| Production code (`app/**/*.py`) | **0 changes** ✓ |
| AGPL seam intact | ✓(`grep -rn "import fitz" app/` only `pdf_engine.py:19`) |
| pytest baseline | `301 passed, 3 skipped, 3 xfailed` ✓ |
| xfail strict 3-case 紅燈基線 | ✓(text-glyph-01 + figure-glyph-01 + mixed-glyph-01 各 XFAIL) |
| AGPL guard test 仍綠 | ✓(`tests/test_redact.py::test_fitz_import_confined_to_engine_seam` PASSED) |
| `gsd-secure-phase` non-block invariant | ✓(`threats_open: 0` + `threats_accepted: 2`) |
| `git ls-files \| grep 3013A-13A-C6-XX` | empty ✓(無 raw supplier PDF tracked) |
| `git log --follow` archived PNG | ✓ 2 commits(0f14325 + b9aa005;history preserved through git mv) |

## Tasks 1 & 2 — Attack Helper + Regression Test

### `tests/_illustrator_attack.py` (Task 1 — commit `cdf6c26`)

**3 exports + 2 private helpers,全部 type-hinted、無 module-level side effect、無 main()**:

```python
def _find_image_xrefs_intersecting(page, rect) -> list[int]    # VERBATIM scratch lines 40-49
def _resolve_resource_names(page, xrefs) -> set[str]           # VERBATIM scratch lines 70-74
def delete_image_xobjects_intersecting(doc, page_index, rect) -> int    # 包 lines 84-115
def render_region_white_pct(pdf_path, page_index, rect) -> float        # VERBATIM scratch lines 21-30
def count_zero_area_fills_in_region(pdf_path, page_index, rect) -> int  # delegate to production helper
```

**Verbatim preservation 範圍**:scratch 主 regex `r"q\b[^Q]*?/" + re.escape(name.lstrip("/")) + r"\s+Do\b[^Q]*?Q\b"`(line 89) + bare fallback `r"/" + re.escape(name.lstrip("/")) + r"\s+Do\b"`(line 98)+ multi-stream `update_stream` 不對稱 write-back(`[0]` modified + `[1:]` empty,scratch lines 104-115)三段邏輯**逐字搬入** — Risk Callout #4 嚴守。

**Adapter 範圍**(非 verbatim,改寫為 test-friendly):
- 簽名加 type hints(scratch 為 untyped Path / fitz 物件)
- 私有 helpers(`_find_image_xrefs_intersecting` / `_resolve_resource_names`)拆出以對齊 D-B2
- `count_zero_area_fills_in_region` 採 **function-internal import** `from app.services import pdf_engine`(避免 module-load-time 把 production module 拉進 tests namespace)
- 全部 `doc = fitz.open(...) try ... finally doc.close()` 包裝(scratch 為 fire-and-forget script,沒 close)
- `delete_image_xobjects_intersecting` 接受 已-open 的 `fitz.Document`(scratch 自己 open)— 允許呼叫者保留 doc 後 `doc.save(*_attacked.pdf)`,for regression test
- **NO** `main()` / `print(...)` / `if __name__ == "__main__"` — module 必須 silent for pytest collection cleanliness(per PATTERNS Differences from analog)

**AGPL guard**:`tests/_illustrator_attack.py:37` `import fitz  # license: test harness exception (mirror tests/conftest.py:12)` — `tests/` 不在 AGPL guard scope 內(`tests/test_redact.py::test_fitz_import_confined_to_engine_seam` AST walk 只掃 `app/**/*.py`,per Shared Pattern S1)。每個 task 後 grep 驗 seam 仍只 `app/services/pdf_engine.py:19` 一行真實 `import fitz` statement。

### `tests/test_illustrator_attack_regression.py` (Task 2 — commit `165f737`)

**Decorator stack**(line 73-74,**順序載荷**):

```python
@pytest.mark.parametrize("fixture_pdf,manifest", _load_fixtures())   # line 73
@pytest.mark.xfail(strict=True, reason="Option B 尚未實作(Phase 7 SEC-01 待落地)...")  # line 74
def test_illustrator_attack_residual_supplier_revealed(...):
```

Python decorator 由下而上 application:
1. `@xfail` 先套用到 base function(每個未來 parametrize case 各自 inherit xfail marker)
2. `@parametrize` 在外層展開 3 個 cases(text/figure/mixed-glyph-01),每個都帶獨立 xfail

**反置會出問題** — `parametrize` 拿到已-xfail-wrapped 物件 → 展開行為不可預期 → Phase 6 → Phase 7 handoff signal 失靈(Risk Callout #3 嚴守)。

**JobSpec 構造精確 shape**(Risk Callout #1 嚴守):

```python
job_spec = JobSpec(
    dpi=manifest["dpi"],                                          # int, 144 in all 3 manifests
    regions=[RegionMark(
        page=manifest["page_index"],                              # int, 0 in all 3
        px_rect=list(manifest["region_rect_px"]),                 # 4 floats, image-pixel space at dpi
    )],
    logo_id=None,                                                 # pure removal, D-01 contract per test_process_api.py:270-316
)
pipeline.process_job(session_id, job_spec)                        # (str, JobSpec) -> dict per pipeline.py:90
output_pdf = pipeline.output_path(session_id)                     # Path per pipeline.py:85
```

**process_job 回傳 dict 欄位**:`{"output_filename": str, "page_count": int, "regions": [{"page": int, "removed": bool, "clamped": bool}, ...], "logo_skipped": bool}`(per pipeline.py:90 docstring)— 本 test 不檢查 return dict 欄位,只透過 `pipeline.output_path(session_id).exists()` 確認 output PDF 落地;若 Phase 7 implementer 改 process_job 增加 unexpected key 不影響本 test。

**雙閘 assert**(D-B5):
- (a) `render_region_white_pct(attacked_pdf, page_index, region_pdf_pts) >= 98.0` — 視覺乾淨閘
- (b) `count_zero_area_fills_in_region(attacked_pdf, page_index, region_pdf_pts) == 0` — content-stream 乾淨閘
- 加 `n_deleted >= 1` precondition assert(若 region 內無 image XObject 可拔,attack 不成立 — xfail strict 仍會攔截但 Phase 7 落地後會以 XFAIL 而非 PASSED 出現,作為 fixture 不適配的 signal)

**Sidecar manifest schema 消費**(Plan 06-01 canonical split-coordinate per Warning #8):
- `manifest["region_rect_pdf_points"]` → 給 fitz operations(`fitz.Rect(*pts)` clip + `count_zero_area_fills_fully_inside`)
- `manifest["region_rect_px"]` → 給 `RegionMark.px_rect`(IMAGE pixels at the job dpi)
- 一處 Plan 06-01 sanitize 寫,雙處 Plan 06-02 test 讀

**Fixture-discovery**:`_load_fixtures()` 用 `sorted(FIXTURES_DIR.glob("*.pdf"))`(per Pitfall 6 — Path.glob 順序不穩定);缺對應 `.json` sidecar → `pytest.fail` 中止 collection。

**xfail reason 字串**(繁中 + cross-ref):
```
Option B 尚未實作(Phase 7 SEC-01 待落地)— Illustrator-class editor 拔 image
XObject 後 page content stream 內的零面積 type='f' 路徑仍會 render 出供應商商標。
Phase 7 落地後請拔掉本 marker。參 .planning/REQUIREMENTS.md SEC-01。
```

Phase 7 implementer `grep -rn "xfail.*Option B" tests/` 可一鍵定位本 marker;落地 Option B 後 `python -m pytest -k illustrator_attack -v` 預期變 XPASS(strict) → exit non-zero → 強迫拔 marker = handoff completion 動作。

### pytest baseline 確認

```
$ python -m pytest 2>&1 | tail -3
================= 301 passed, 3 skipped, 3 xfailed in 13.68s ==================
```

- 301 passed:v1.0 close + hotfix 06+07 既有基線(無回退)
- 3 skipped:POSIX-only chmod tests on Windows(既有,無新增)
- 3 xfailed:本 Plan 06-02 新增,對應 3 個 fixture × 1 parametrized × xfail-strict
- `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` 仍綠 ✓

## Task 3 — 06-SECURITY.md Pre-mortem STRIDE

### Frontmatter 確切值(commit `bafcbdc`)

```yaml
phase: 6
phase_name: regression-foundation-threat-model-re-evaluation
milestone: v1.1
audit_scope: phase_06_pre_mortem
date: 2026-05-28
asvs_level: 1
diff_base: N/A
commits_audited: []
threats_total: 2
threats_closed: 0
threats_open: 0          # ← gsd-secure-phase non-block invariant
threats_accepted: 2      # ← transition-pending framing
register_authored_at_audit_time: true
supersedes:
  - .planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md
```

`threats_open: 0` + `threats_accepted: 2` framing 經 RESEARCH § Assumptions A3 確認為 `gsd-secure-phase` agent non-block 條件;不採 `threats_open: 2`(會阻塞 Phase 6 close)。

### STRIDE Threat Register final disposition 文字

| Threat | Disposition |
|---|---|
| **T-02-07** | `mitigate(已 archive,沿用 v1.0 LIVE Option A 對 CLI-only 威脅模型仍有效)+ RE-OPENED 2026-05-28 pending Option B (Phase 7) — accept (P0, transition-pending until Phase 7)` |
| **T-06-01** | `mitigate(pending Option B Phase 7)— accept (P0, transition-pending until Phase 7)` |

兩條 threat 共享同一 closing path:Phase 7 落地 Option B(SEC-01)後 `07-SECURITY.md` 將 **同時** CLOSED via Option B(同一 production fix close 兩條 — root cause 同為 page content stream 內零面積 type='f' source 未被刪除)。

### Content 統計

- 11 個 sections(Pre-mortem Context / STRIDE Actors / STRIDE Threat Register / T-02-07 RE-OPENED narrative / T-06-01 narrative / Accepted Risks Log × 2 entries / Pre-mortem vs Audit-time variant / Open Threats / Cross-references / Supersession Chain matrix)
- 346 lines prose
- Cross-references:11 條 traceability matrix(REQUIREMENTS.md SEC-01/02/03 + TEST-02/03 + THREAT-01/02 + DEPLOY-01 + 本 Plan 交付物)

### Archived 原檔未被本檔編輯

`git diff --stat HEAD .planning/milestones/` 顯示 0 changed files(commit history confirmed)— 追溯 chain 透過 frontmatter `supersedes:` 鎖定,archived `06-HOTFIX-SECURITY.md` 原檔保留 v1.0 close 時的 `CLOSED with documented residual` 文字不被改動。

## Task 4 — Scratch Retirement + Repo Cleanup

### Archived dir final 內容(commit `0f14325`)

```
.planning/debug/scratch/illustrator-attack-2026-05-28-archived/
├── README.md                           # NEW(5 sections,繁中)
├── _attack_image_xobject_deleted.pdf   # 保留(forensic evidence)
├── _attack_orig_for_comparison.png     # 保留(原 supplier PDF render reference)
├── _attack_proof_supplier_revealed.png # 保留(攻擊後重現證據)
├── _attack_target_pre.png              # 保留(攻擊前 LogoSwap 輸出 render)
└── 3013A-13A-C6-XX-3D02-A01-00040.pdf  # 物理 mv 自 repo root,untracked
                                        # (.gitignore archived-anchored 屏蔽)
```

### 退役的 .py 確認 deleted

```
$ ls .planning/debug/scratch/illustrator-attack-2026-05-28-archived/*.py 2>&1
ls: cannot access '...*.py': No such file or directory
```

`_attack_delete_image_xobject.py` + `_check_supplier_removal.py` 已 `git rm -f`(因 git mv 先 stage 了 rename,後續 git rm 需 `-f` 處理 staged index);git history 仍可 `git log --all --diff-filter=D --follow -- .../[name].py` 查回歷史版本。

### README.md 章節結構

5 個 section,全 繁中:
1. **為何 archived**(v1.1 milestone 啟動 ground-truth)
2. **`.py` 退役說明 + 邏輯落點**(指向 `tests/_illustrator_attack.py` + `tests/test_illustrator_attack_regression.py`)
3. **保留的 4 個 PNG/PDF 證據用途**(逐個 cite + AGPL §13 考量)
4. **Cross-references**(新 pytest + 新 fixtures + 06-SECURITY.md + `scripts/sanitize_fixture.py` + REQUIREMENTS.md SEC-01)
5. **原始 raw supplier PDF 處置**(samples/ git rm + repo root 物理 mv + .gitignore archived-anchored 屏蔽)

### `git log --follow` archived PNG output(Blocker #3 達成)

```
$ git log --follow --oneline .planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png | head -3
0f14325 chore(06-02): retire 2026-05-28 illustrator-attack scratch + clean raw supplier PDFs
b9aa005 chore: archive v1.0 phase dirs + 2026-05-28 illustrator-attack evidence
```

2 commits in history chain — git mv 保住 rename detection,downstream `gsd-secure-phase` agent 或未來 audit 可追溯到 v1.1 啟動之前的 forensic 取證 commit。

### Repo phase-level invariant 確認(Blocker #2 + Warning #9)

```
$ git ls-files | grep -E '3013A-13A-C6-XX'
(empty)
```

三個 state 同步達成:
1. **`samples/3013A-13A-C6-XX-3D02-A01-00040.pdf`** — `git rm` 已從 git index 移除(working tree bytes 也同步刪除,因 git rm 預設行為)。`samples/` 目錄空後也消失。
2. **Repo root `3013A-13A-C6-XX-3D02-A01-00040.pdf`** — 物理 `mv` 到 archived dir(原本 untracked + Plan 06-01 `.gitignore` root-anchored `/3013A-13A-C6-XX-*.pdf` 已屏蔽)。
3. **Archived dir 內 raw `3013A-...pdf` 副本** — Plan 06-01 `.gitignore` archived-anchored `/.planning/debug/scratch/illustrator-attack-2026-05-28-archived/3013A-*.pdf` 屏蔽,不會被 git track。

附註:repo root 仍保留 4 個 `3013A-13A-C6-XX-3D02-A01-00040_logoswap (N).pdf` — 這些是 **LogoSwap 處理後的 output PDF**(不是 raw supplier),不在 raw supplier PDF 屏蔽範圍內;不影響 `git ls-files` invariant(它們皆 untracked + 名稱不含 `XX-3D02` raw pattern)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `git rm` 對 git-mv-staged files 需要 `-f`**
- **Found during:** Task 4 Step B
- **Issue:** `git mv` 已將 `.py` scripts staged 為 `R`(rename),後續 `git rm` 預設拒絕 staged-changes-bearing files(`error: the following files have changes staged in the index`)。
- **Fix:** 改用 `git rm -f`(force)。語意上仍為 intentional deletion(scratch script 已 archive 路徑後,Plan 06-02 Task 4 明文 spec 要刪),`-f` 只是 git 對 staged-state 的安全 prompt 繞過。
- **Files modified:** N/A(只是 command flag 改變,結果一致)
- **Commit:** `0f14325`(Task 4 commit)

**2. [Rule 1 - Bug] Acceptance check 的 `t.index('@pytest.mark.xfail')` 對 docstring 內 mention 命中**
- **Found during:** Task 2 verify 階段
- **Issue:** Plan acceptance criteria 包含 `python -c "... idx_p=t.index('@pytest.mark.parametrize'); idx_x=t.index('@pytest.mark.xfail'); assert idx_p < idx_x"` — 但 module docstring 內 prose 提到 `@pytest.mark.xfail(strict=True)` 字串(在 invariant 解釋段)+ 提到 `@pytest.mark.parametrize`(在 decorator order 解釋段),`.index()` 拿到的是 **docstring 內第一個 mention**(line 8 xfail,line 17 parametrize),導致 acceptance check 邏輯誤判 decorator order 錯位。
- **Fix:** 真實 decorator 順序正確 —— line 73 `@pytest.mark.parametrize` 在 line 74 `@pytest.mark.xfail` **之上**(Risk Callout #3 嚴守)。改用 line-based check(`for line in source.splitlines(): startswith('@pytest.mark.parametrize'/xfail')`)驗證,結果 `decorator order ok: parametrize@line 73 < xfail@line 74`。Acceptance check 邏輯是字面 `.index()` 的問題,實作正確 — 不修 plan 的 check 本身(out-of-scope),只在本 SUMMARY 註記 known false positive。
- **Files modified:** N/A
- **Commit:** N/A

### Authentication Gates

None — Phase 6 為純測試 + 文件層交付,無外部服務 / API key / login。

## Known Issues / Carry-forward to Phase 7

### ~~Phase 6 fixture replenishment~~ **〔已 RESOLVED 2026-05-28〕**

**Original carry-forward**(已在當日內 close):`text-glyph-01.pdf` + `figure-glyph-01.pdf` 為 synthetic(`--synthesize` fallback);只有 `mixed-glyph-01.pdf` 是 real supplier PDF。

**Resolution(2026-05-28 post-close maintenance):** 工程師交付剩餘 2 個 supplier PDF(`3013A-36A-C6-W4.pdf` + `B-3012IP-WM02-T430.pdf`,同為 `宁波登骐 / Ningbo Dengqi` 不同 SKU),sanitize_fixture.py 補強 Impl notes C + D(commit `0045c6b`)處理 PScript5 + Acrobat 出口的 CMap font + Form-XObject stamp annotation 場景,3/3 fixture 升級為 real(commit `f7f34e8`)。Phase 6 PROVISIONAL banner 已移除。詳見 `06-01-SUMMARY.md § Provisional → Final 升級記錄`。

**對紅燈基線無影響**:3 個 XFAIL 仍維持(real fixtures attack 同樣成功 — 雙閘斷言基於 page-level zero-area `type='f'` source path 是否被刪,與 supplier 身份無關)。Phase 7 implementer 接手不變。

### `mixed-glyph-01.pdf` 的 brand-glyph strip 沒命中(Plan 06-01 corner case #1)

Plan 06-01 執行時發現:`mixed-glyph-01.pdf` 的零面積 fill 散落在 content stream 內(非 `q...Q` group 包裝),Plan 06-01 brand-glyph block strip heuristic 0 命中 — 但 sanitize 仍 pass(metadata 清乾淨 + supplier name 不在 `get_text()` + post zero-area count 3396 ≥ 0.9 × 1742)。

**對 Plan 06-02 紅燈基線的影響**:Phase 6 regression test 對此 fixture 的 XFAIL 行為**與其他 2 個 fixture 一致**(都 XFAIL)。`mixed-glyph-01.pdf` 內留有 1742 個原 supplier zero-area fill + 1654 個 TESTCO 縱線 = 3396 個 total post zero-area;attack 拔 image XObject 後 attacked PDF 在框選區內仍有大量 zero-area type='f' source path,雙閘 (b)(`count_zero_area_fills_in_region == 0`)必定 fail → XFAIL。**Phase 7 落地 Option B 後預期同樣會 close**(Option B 應移除 page-level 所有 fully-inside-rect 的 zero-area fills,不管其 glyph shape 是 synthetic 還是 real supplier)。

### Phase 7 implementer 接手要點

1. **一鍵定位 marker**:`grep -rn "xfail.*Option B" tests/` → `tests/test_illustrator_attack_regression.py:75-83`
2. **落地 Option B 後驗證**:`python -m pytest -k illustrator_attack -v` 預期顯示 3 個 **`XPASS(strict)`** → exit non-zero
3. **Handoff completion 動作**:拔掉 `tests/test_illustrator_attack_regression.py` 的 `@pytest.mark.xfail(...)` decorator(line 74-82)→ 3 個 cases 變 PASSED → pytest baseline 變 `304 passed, 3 skipped`
4. **`07-SECURITY.md` 更新**:把 T-02-07 + T-06-01 兩條 STRIDE row 改為 `mitigate | CLOSED via Option B`,evidence 指向 Phase 7 production code commit + Plan 07-XX 新增 helper 單元測試(TEST-03)
5. **追溯 chain**:`07-SECURITY.md` frontmatter `supersedes:` 列出本檔(`06-SECURITY.md`),延續 chain `07-SECURITY.md → 06-SECURITY.md → archived 06-HOTFIX-SECURITY.md`
6. **追溯 cross-ref**:`grep -rn "T-02-07\|T-06-01" tests/ docs/ .planning/` 確認所有 reference 已 follow Option B close 後的新狀態(本 Plan 06-02 deliverable 全部 inline cite 都已對齊 transition-pending framing,Phase 7 implementer 只需把 06-SECURITY.md 等價的兩條從 `transition-pending` → `mitigate | CLOSED via Option B`)

## Self-Check: PASSED

Files verified (all FOUND):
- `tests/_illustrator_attack.py`
- `tests/test_illustrator_attack_regression.py`
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`
- `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/README.md`
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-02-SUMMARY.md`

Files verified DELETED (all confirmed gone):
- `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_delete_image_xobject.py`
- `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_check_supplier_removal.py`
- `samples/3013A-13A-C6-XX-3D02-A01-00040.pdf`
- `.planning/debug/scratch/illustrator-attack-2026-05-28/`(整個 dir,rename 到 `-archived`)

Commits verified (all FOUND in git log):
- `cdf6c26` — feat(06-02): add tests/_illustrator_attack.py helper module
- `165f737` — test(06-02): add tests/test_illustrator_attack_regression.py xfail-strict baseline
- `bafcbdc` — docs(06-02): add 06-SECURITY.md pre-mortem STRIDE for v1.1 milestone
- `0f14325` — chore(06-02): retire 2026-05-28 illustrator-attack scratch + clean raw supplier PDFs

Phase invariants:
- `grep -rn "import fitz" app/` → only `app/services/pdf_engine.py:19`(seam intact) ✓
- `git diff --stat HEAD~4 app/`(本 plan 4 commits)→ 0 changed files ✓
- `git ls-files | grep -E '3013A-13A-C6-XX'` → empty ✓
- `python -m pytest -k illustrator_attack -v` → 3 XFAIL ✓
- `python -m pytest 2>&1 | tail -3` → `301 passed, 3 skipped, 3 xfailed` ✓
- `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` → PASSED ✓
- `git log --follow .../...archived/_attack_proof_supplier_revealed.png | head -3` → 2 commits ✓

## Threat Flags

無新 threat surface introduced。本 plan 0 動 production code、0 新 runtime attack surface。
- `tests/_illustrator_attack.py` 在 maintainer 機器上跑(屬 test harness,non-production)
- `tests/test_illustrator_attack_regression.py` 屬 test code,non-production
- `06-SECURITY.md` 為 docs,non-runtime
- Scratch retirement 為 file-ops cleanup,non-runtime
- AGPL seam intact(per Plan 06-02 verification 1)
- 06-SECURITY.md 既有的 T-02-07 + T-06-01 已 register;非 unregistered flag

## Cross-references

- Plan: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-02-PLAN.md`
- Context: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-CONTEXT.md`(D-B1..D-B6, D-C1, D-D1..D-D4)
- Research: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-RESEARCH.md`(Pattern 1/2/3,Pitfall 3/4/5/6/8,Assumptions A3)
- Patterns: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-PATTERNS.md`(Pattern Assignments × 7 + Shared Patterns S1-S5 + Risk Callouts 1-4)
- Previous plan: `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-01-SUMMARY.md`(fixtures + sanitize script + .gitignore guards)
- Project: `.planning/PROJECT.md`(milestone v1.1 Active)
- Requirements: `.planning/REQUIREMENTS.md` TEST-02 + THREAT-01(Phase 6)+ SEC-01 / SEC-02 / SEC-03 / TEST-03 / THREAT-02 / DOC-01 / DOC-02 / DEPLOY-01(Phase 7 / 8)
- Threat model:`.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`(本 plan 交付)
- Next plan / Phase 7 entrypoint:`.planning/phases/07-*/`(待 Phase 7 啟動時建立);Phase 7 implementer 用 `grep -rn "xfail.*Option B" tests/` 一鍵定位 handoff marker
