# Phase 6: Regression Foundation + Threat Model Re-evaluation — Research

**Researched:** 2026-05-28
**Domain:** PyMuPDF content-stream sanitization + pytest xfail regression harness + STRIDE pre-mortem documentation
**Confidence:** HIGH (核心 API 已 cross-verified;sidecar manifest pattern + xfail strict 為標準 pytest 慣例)

## Summary

Phase 6 是 v1.1 milestone 的「紅燈基線」hardening phase — **無 production code 變更**,純 test / docs 交付。三項交付:(1) `scripts/sanitize_fixture.py` + ≥3 個 sanitized supplier PDF + sidecar JSON manifest in `tests/fixtures/cad-glyph/`、(2) `tests/_illustrator_attack.py` helper + `tests/test_illustrator_attack_regression.py` 紅燈 pytest(parametrize over 3 fixtures,`@pytest.mark.xfail(strict=True)`)、(3) `06-SECURITY.md` pre-mortem(STRIDE 加入 Illustrator-class editor actor + T-02-07 RE-OPENED + T-06-01 新 threat)。

研究結論收斂為三個 HIGH 確信點:

1. **PyMuPDF 已具備所有所需 API** — `Document.set_metadata({})` 清空 metadata(自 1.18.4 起空值不寫入)、`Document.xref_stream(xref)` + `Document.update_stream(xref, bytes)` 對 page content stream 做位元組級 read-modify-write 完全 supported,既有 scratch attack script 已實證可用(`src.update_stream(content_xrefs[0], new_bytes, compress=True)`)。
2. **pytest.mark.xfail(strict=True) 是 Phase 6 → Phase 7 handoff 的正確機制** — XFAIL 不影響 exit code、XPASS(strict) 等同 FAIL → 強迫 Phase 7 implementer 拔掉 marker。`reason` 字串 + `--runxfail` 互動行為已驗證。
3. **`gsd-secure-phase` 既有 frontmatter schema 已存在於 archived `06-HOTFIX-SECURITY.md`** — Phase 6 SECURITY.md 沿用相同 schema,但**以 pre-mortem 變體出現**(no commits to audit、no diff_base、threats_open ≠ 0 by design,因為 Phase 6 的價值就是把 threats 開出來等 Phase 7 close)。

**Primary recommendation:** Phase 6 plan 切兩個 plan — `06-01-sanitization-and-fixtures` (script + 3 fixtures + manifests) 與 `06-02-attack-regression-and-security` (helper + xfail test + 06-SECURITY.md),`scripts/sanitize_fixture.py` 內以 `find_xobject_resource_name → q...Do...Q regex strip → build TESTCO zero-area path → append as new content stream object` 的 pipeline 實作(沿用 scratch script 已 proven 的 regex pattern)。對外人員交付 ≥2 supplier PDF 的時程不確定 → planner 必須在 PLAN.md 列入「synthetic CAD-glyph fallback fixture builder」contingency(用 fitz Shape API 合成 ≥100 zero-area `type='f'` paths,沿用 `test_remove_region_vector_dense_real_zero_area_paths_end_to_end` 的合成 pattern)。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Fixture 來源與 sanitization:**
- **D-A1:** Fixture 來源 = 工程師手中既有真實 supplier CAD PDF;repo root 既有 `3013A-13A-C6-XX-3D02-A01-00040.pdf` 為第 1 個,一週內可交出 ≥2 個另外的 supplier CAD PDF。不採合成 PDF 作 primary source。
- **D-A2:** Sanitization = 脫敏後 commit 進 public repo(`tests/fixtures/cad-glyph/`)。4 件脫敏動作:
  1. Metadata 清空 — `doc.set_metadata({})` 或等效 API(researcher 需驗證 1.27.x 簽名)
  2. Content stream 供應商公司名 → `TESTCO`(find-replace 在 content stream 與 `/Title` 等)
  3. Brand glyph 整塊以新建的 `TESTCO` wordmark zero-area glyph 取代
  4. Bbox / fingerprint cleanup(hyperlink、comment annotation、digital signature、accessibility tags)
- **D-A3:** Brand glyph 複寫策略 — 原 supplier brand glyph(N 個 zero-area `m/l/f/B` 算子序列)整段刪除,以 `TESTCO` wordmark zero-area 算子序列塞回原位置 + 同 CTM。保留同型 attack 面(`count_zero_area_fills_fully_inside` 在框選區內 ≥ 原 count 的 90%)。
- **D-A4:** `scripts/sanitize_fixture.py` 一次性工具 — CLI args `--in raw.pdf --out tests/fixtures/cad-glyph/text-glyph-01.pdf --supplier-name "..." --region-rect "x0,y0,x1,y1"`。raw PDF 不進 git。
- **D-A5:** Coverage 分布:`text-glyph-01.pdf`(文字 glyph 主體)+ `figure-glyph-01.pdf`(圖形 glyph 主體)+ `mixed-glyph-01.pdf`(文字 + 圖形混合)。可選 `…-02.pdf` 第四個。
- **D-A6:** `tests/fixtures/cad-glyph/README.md` 必須寫入 (a) 為什麼是 conftest「no committed binary」convention 的唯一例外、(b) 每個 fixture 對應的原供應商 + sanitization 日期 + commit SHA、(c) 任何 fixture 變更必須走 sanitization script 不可手動編輯。

**Attack-simulation pytest 設計:**
- **D-B1:** 新 test 檔位置 = `tests/test_illustrator_attack_regression.py`(獨立檔)
- **D-B2:** Attack helper 共用模組 = `tests/_illustrator_attack.py`,export 三個函式:
  - `delete_image_xobjects_intersecting(doc, page_index, rect) -> int`
  - `render_region_white_pct(pdf_path, page_index, rect) -> float`
  - `count_zero_area_fills_in_region(pdf_path, page_index, rect) -> int`(包 `app.services.pdf_engine.count_zero_area_fills_fully_inside`)
- **D-B3:** pytest 參數化 — `@pytest.mark.parametrize("fixture_path", [text-glyph-01, figure-glyph-01, mixed-glyph-01])` + `@pytest.mark.xfail(strict=True, reason="Option B pending in Phase 7 …")`
- **D-B4:** Region rect 來源 = 每個 fixture 的 sidecar JSON manifest(`{"region_rect": [x0, y0, x1, y1], "page_index": 0, "expected_zero_area_count_pre_process": N}`)
- **D-B5:** Assertion 雙閘 — (a) `render_region_white_pct >= 98.0` + (b) `count_zero_area_fills_in_region == 0`
- **D-B6:** Test count 影響 — 新增 3 個 xfail tests;baseline 從「301 passed + 3 skipped」變「301 passed + 3 skipped + 3 xfailed」。

**Scratch retirement:**
- **D-C1:** `.planning/debug/scratch/illustrator-attack-2026-05-28/` → `…-archived/`;保留 4 個 PNG/PDF;退役 `_attack_delete_image_xobject.py` + `_check_supplier_removal.py`;新增 `…-archived/README.md`。

**Threat model re-evaluation:**
- **D-D1:** 新建 `06-SECURITY.md`(per-phase),不另建 top-level `.planning/SECURITY.md`。
- **D-D2:** STRIDE 表新增 `Illustrator-class editor attacker` actor + 新 threat `T-06-01: Illustrator pulls image XObject overlay → supplier brand re-rendered`(Spoofing/Info-disclosure 雙重)。Disposition: `OPEN — pending Option B (Phase 7)`。
- **D-D3:** T-02-07 從 `CLOSED with documented residual` → `RE-OPENED 2026-05-28 (v1.1 Phase 6) — pending Option B`,明文不撤銷 v1.0 LIVE mitigation 仍對 CLI-only 威脅模型有效。
- **D-D4:** 06-SECURITY.md format = 沿用 `gsd-secure-phase` 既有 frontmatter + STRIDE 表 + Threat Verification table 風格(對齊 `06-HOTFIX-SECURITY.md`),但**以 pre-mortem 變體**(no audit-time commits to audit)。

**Carrying forward(本階段不重複決定):**
- AGPL seam — `import fitz` 嚴格限制在 `app/services/pdf_engine.py`(Phase 1-4 AST-level guard test 持續綠燈)
- 5330290 教訓 — minimum-change + sufficient-testing
- conftest.py in-memory fixture 哲學 — `tests/fixtures/cad-glyph/` 是唯一 committed-binary 例外
- 既有測試基線 — 301 passed + 3 skipped(v1.0 close + hotfix 06+07)
- commit/push 節奏 — UAT 期間 commit local but never push;Phase 6 沿用,push 留到 Phase 8 LIVE-UAT
- 繁中文案 — SECURITY.md 內文 + xfail reason 字串建議仍繁中

### Claude's Discretion

- `scripts/sanitize_fixture.py` 內部實作細節(CLI args 完整設計、CMap decoding 邊界、PDF object stream 編輯走 `doc.update_stream` vs `doc.xref_set_stream` 等)
- xfail reason 字串文案(繁中 + 含 cross-reference 路徑)
- TESTCO wordmark 字型 / 設計選擇(硬編幾組通用幾何路徑即可,不需追求美觀)
- Sidecar JSON manifest schema(核心 3 欄 + 可加 `original_supplier_name_hash`、`sanitization_script_commit_sha`、`created_at_iso` 等元資料)
- 新測試是否需要 isolated `tmp_path`(沿用 conftest 既有 `isolated_data_dir` autouse fixture)
- 既有 attack 腳本中的 `samples/3013A-...pdf` 路徑處置(planner 評估;含原供應商名 — 不安全留 public repo;建議移到 archived 同層或加 `.gitignore`)

### Deferred Ideas (OUT OF SCOPE)

- 對 form XObject 內 zero-area fills 做遞迴 surgery(v1.1 SEC-03 已採 page-level only + log)
- 對 zero-area `type='s'`(stroke)做 surgery
- 新增 `is_raster_fallback_image(page, xref)` getter
- Auto-detect supplier-source heuristic dispatcher(REQUIREMENTS.md Out of Scope)
- CMap decoding helper 通用化(若三個 fixture 都不需要 CMap decode 則不寫)
- xfail → skip 自動切換機制(xfail 本身就是 safe baseline)
- Sanitization script 的 watermark / fingerprint cleanup(實際樣本到手再決定)
- commit raw supplier PDF 進 internal git(用戶 Q2 已否決)
- fitz 在 scripts/sanitize_fixture.py 內的長期治理(scripts/ 目前不在 AGPL guard scope;v1.1 不擴)

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-01 | 收集 ≥3 個工程師手上實際出問題的 CAD-glyph supplier PDF,sanitized 後納入 `tests/fixtures/cad-glyph/` | § 1 (PyMuPDF sanitization API) — `set_metadata({})` + `update_stream` 已驗證可實作 4-step 脫敏;§ 4 (Sidecar JSON manifest) — schema 與 discovery pattern 鎖定;§ 7 (AGPL seam) — `scripts/sanitize_fixture.py` 在 guard 範圍外可自由 import fitz;Open Question Q1 (contingency 樣本) — synthetic fallback fixture builder pattern available via `test_remove_region_vector_dense_real_zero_area_paths_end_to_end` |
| TEST-02 | 攻擊腳本改寫為 pytest regression test,assert 框選區 ≥98% 白 + zero-area fills count == 0(目前紅燈) | § 2 (Content-stream operator semantics) — degenerate `m/l/f` zero-area attack pattern 已驗證;§ 3 (pytest.mark.xfail strict=True) — XPASS(strict) 等同 FAIL 的 handoff 機制驗證;§ 6 (test harness scaffolding) — `tests/_illustrator_attack.py` helper 命名 + `pathlib.Path(__file__).parent` fixture loading pattern;既有 attack regex `r"q\b[^Q]*?/\<Name\>\s+Do\b[^Q]*?Q\b"` 已 proven |
| THREAT-01 | STRIDE 新增 Illustrator-class editor actor,T-02-07 RE-OPENED 至 Option B 落地 | § 5 (per-phase SECURITY.md schema) — `gsd-secure-phase` 既有 frontmatter + Threat Verification table 已對齊 archived `06-HOTFIX-SECURITY.md`;pre-mortem 變體已勾畫(register_authored_at_audit_time + adapted threats_total/closed/open semantics) |

</phase_requirements>

## Architectural Responsibility Map

Phase 6 是測試 / 文件層交付,**沒有 production code tier 動到**。下表將 Phase 6 三項交付映射到既有 architectural tier 為 sanity-check:

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PDF sanitization tool(`scripts/sanitize_fixture.py`) | Dev tooling / scripts | — | 一次性 dev 工具,執行於 maintainer 機器,不參與 runtime。`scripts/` 目錄不在 AGPL guard scope,可直接 `import fitz` |
| Test fixtures(`tests/fixtures/cad-glyph/*.pdf` + `*.json`) | Test data | — | committed binary 例外(README 文件化);sidecar JSON manifest 為 pytest 參數化的 input,非執行 path |
| Test helper(`tests/_illustrator_attack.py`) | Test harness | — | 沿用既有 `tests/` 目錄 + 既有「test harness may use fitz directly」exception(conftest.py line 12) |
| Regression test(`tests/test_illustrator_attack_regression.py`) | Test harness | — | parametrize 跑 ingest → process → attack → assert;**唯一 import production code 的點是** `from app.services import pdf_engine, pipeline, ingest`,跟既有 test 一致 |
| Threat model doc(`06-SECURITY.md`) | Planning artefact | — | per-phase docs,downstream `gsd-secure-phase` agent 在 Phase 7 close 時可接手 cross-reference + supersede chain |

**Key insight:** **App / production tier 0 動**。整個 Phase 6 trace fitz import 增量:`scripts/sanitize_fixture.py` (+1, 不在 guard) + `tests/_illustrator_attack.py` (+1, 不在 guard) + `tests/test_illustrator_attack_regression.py` (+0 or +1,可由 conftest re-export 避免;討論詳 § 6) → `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` 仍綠燈。

## Standard Stack

Phase 6 不引入任何新 dependency。沿用既有 pinned stack:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyMuPDF (`fitz`) | `>=1.27,<1.28`(已 pinned in `requirements.txt`) | Sanitization script content-stream surgery + attack helper image XObject 刪除 + zero-area count assertion | [CITED: requirements.txt] 既有 pin;[VERIFIED: PyPI metadata via STACK.md 既有研究] Python 3.10-3.14 支援、AGPL/Artifex 雙授權;Document.set_metadata({}) + Document.update_stream(xref, bytes) + Page.read_contents() + Document.xref_stream(xref) 全部都是 1.27.x stable API |
| pytest | latest(`pytest` unpinned in `requirements.txt`) | Regression test runner | [CITED: requirements.txt:18] 既有 dependency。`pytest.mark.xfail(strict=True)` 自 pytest 3.x 起 stable,當前 pytest 8.x 完全支援(`strict_xfail` ini option 也可全域設) |
| numpy | `>=1.26`(transitive via Pillow / Pillow-friendly version)— 既有 attack script 已用 | `render_region_white_pct` 算白佔比 | [VERIFIED: existing scratch script `_attack_delete_image_xobject.py:11`] `np.frombuffer(pm.samples, dtype=np.uint8).reshape(...)` 為 既有 attack pattern,沿用 |

### Supporting
無新增。`Pillow`、`FastAPI`、`Uvicorn` 等不在 Phase 6 scope。

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pytest.mark.xfail(strict=True)` | `pytest.mark.skip(reason="…")` | skip 不會在 Phase 7 落地後自動失敗 → 沒有 handoff signal。**xfail strict 顯著更好** — 已被 D-B3 鎖定 |
| `pytest.mark.xfail(strict=True)` | 直接寫一個 inverted assert(`assert NOT clean`)讓 test pass | 倒裝 assert 在 Phase 7 落地後仍會 pass(假設成立),不會 surface bug;且語意混淆(讀 test 的人不知道這是「期望紅燈」)。**xfail strict 顯著更好** — semantically explicit |
| `doc.set_metadata({})` 清空 | 逐欄 `doc.set_metadata({"author": "", "producer": "", ...})` | [VERIFIED: PyMuPDF wiki via WebSearch] 自 1.18.4 起空值不再 write,效果等同;但 `{}` 寫法更簡潔且 covers 所有未來新增欄位 |
| `Document.update_stream(xref, bytes, compress=True)` | `Document.xref_set_stream(xref, bytes)` | [VERIFIED: PyMuPDF docs] `update_stream` is the modern method (xref_set_stream was the old low-level alias and is kept for back-compat);scratch script `_attack_delete_image_xobject.py:110` 已用 `update_stream` 並驗證可行。**用 `update_stream`** |
| TESTCO wordmark 由 `Page.insert_text` 渲染 | 手工拼 `m/l/f` 算子序列 | `insert_text` 會產生 **正常面積** glyph(BT/ET text-show 算子),不是 zero-area `type='f'` fills → 無法保留 attack 面 → 違反 D-A3 「保留同型 attack 面」。**必須手工拼 zero-area path 算子** |

**Installation:** N/A — 沿用 pinned stack。

**Version verification:**
```bash
# 既有 pin 已在 requirements.txt;不需驗證新版本
grep -E "PyMuPDF|pytest|numpy" requirements.txt
```
[VERIFIED: requirements.txt:5,18,19] `PyMuPDF>=1.27,<1.28`、`pytest`(unpinned)、numpy via Pillow 或 既有 dependency 鏈.

## Architecture Patterns

### System Architecture Diagram

```
Phase 6 交付物與既有 codebase 互動

┌─────────────────────────────────────────────────────────────────────┐
│                    MAINTAINER MACHINE (one-time)                    │
│                                                                     │
│  raw_supplier.pdf (NOT in git)                                      │
│         │                                                           │
│         ▼                                                           │
│  scripts/sanitize_fixture.py  ──── fitz API ────┐                   │
│    1. doc.set_metadata({})                      │                   │
│    2. content-stream find-replace supplier-name │                   │
│    3. delete brand glyph operator block (regex) │                   │
│    4. inject TESTCO zero-area wordmark @ same   │                   │
│       position + CTM                            │                   │
│    5. assert post-state (zero-area count ≥ 90%) │                   │
│         │                                       │                   │
│         ▼                                       │                   │
│  tests/fixtures/cad-glyph/{text|figure|mixed}-glyph-01.pdf  (COMMITTED)
│  tests/fixtures/cad-glyph/{text|figure|mixed}-glyph-01.json (sidecar) │
│         │                                                           │
└─────────│───────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      pytest RUN (CI / dev)                          │
│                                                                     │
│  tests/test_illustrator_attack_regression.py                        │
│         │                                                           │
│         │ @pytest.mark.parametrize(fixture_path, region_rect)       │
│         │ @pytest.mark.xfail(strict=True, reason="…Option B…")      │
│         │                                                           │
│         ▼                                                           │
│  Step 1: load tests/fixtures/cad-glyph/{N}.pdf + .json              │
│  Step 2: ingest.ingest_upload(filename, bytes) → SessionInfo        │
│  Step 3: pipeline.process_job(session_id, [region], logo_id=None)   │
│         │                                                           │
│         ▼ (LogoSwap output PDF: Option A raster overlay applied)    │
│                                                                     │
│  Step 4: tests/_illustrator_attack.py                               │
│    .delete_image_xobjects_intersecting(doc, page_index, rect)       │
│      (regex `q ... /<Name> Do ... Q` content-stream surgery)        │
│         │                                                           │
│         ▼ (Attacked PDF: image XObject overlay removed)             │
│                                                                     │
│  Step 5: ASSERT (雙閘):                                             │
│    (a) render_region_white_pct(attacked_pdf, ...) >= 98.0           │
│    (b) count_zero_area_fills_in_region(attacked_pdf, ...) == 0      │
│         │                                                           │
│         ▼ (在 Phase 6 預期 FAIL — Option B 未實作 → 紅燈)             │
│                                                                     │
│  pytest 輸出: XFAIL (3 tests)                                        │
└─────────────────────────────────────────────────────────────────────┘

Phase 7 落地 Option B 後同樣的 test 變成 PASS → XPASS(strict)
→ pytest exit code != 0 → 強迫 implementer 拔掉 @pytest.mark.xfail
→ 3 個 PASSED → 新 baseline「304 passed + 3 skipped」
```

### Recommended Project Structure

```
scripts/                                           # 新建(若不存在)
└── sanitize_fixture.py                            # 新檔(一次性 dev 工具)

tests/
├── _illustrator_attack.py                         # 新檔(test helper module)
├── test_illustrator_attack_regression.py          # 新檔(主測試)
├── conftest.py                                    # 不動(可選 加 cad_glyph_session
│                                                  #   parametrized fixture;planner 決定)
└── fixtures/                                      # 新目錄
    └── cad-glyph/
        ├── README.md                              # 新檔(D-A6 文件化例外)
        ├── text-glyph-01.pdf                      # 新檔(sanitized supplier PDF)
        ├── text-glyph-01.json                     # 新檔(sidecar manifest)
        ├── figure-glyph-01.pdf
        ├── figure-glyph-01.json
        ├── mixed-glyph-01.pdf
        └── mixed-glyph-01.json

.planning/
├── phases/
│   └── 06-regression-foundation-threat-model-re-evaluation/
│       └── 06-SECURITY.md                         # 新檔(pre-mortem STRIDE)
└── debug/scratch/
    └── illustrator-attack-2026-05-28-archived/    # 重命名自 …-2026-05-28/
        ├── README.md                              # 新檔(指向新 pytest)
        ├── _attack_proof_supplier_revealed.png    # 保留
        ├── _attack_target_pre.png                 # 保留
        ├── _attack_orig_for_comparison.png        # 保留
        └── _attack_image_xobject_deleted.pdf      # 保留
        # _attack_delete_image_xobject.py — 刪除(邏輯遷移到 tests/_illustrator_attack.py)
        # _check_supplier_removal.py — 刪除(邏輯遷移或捨棄,planner 決定)
```

### Pattern 1: PyMuPDF set_metadata clear

**What:** 清空 PDF 所有 metadata(Author/Producer/CreationDate/ModDate/Title/Keywords/Subject)
**When to use:** sanitize script step 1 — 第一個 4-step 動作
**Example:**
```python
# Source: https://pymupdf.readthedocs.io/en/latest/document.html (set_metadata reference)
# [VERIFIED: PyMuPDF wiki "Using setMetadata() and setToC()" — empty dict {} clears
#  all metadata to "none"; since 1.18.4, empty values are omitted entirely from output PDF]

import fitz

doc = fitz.open(raw_pdf_path)
doc.set_metadata({})  # clears author/producer/creator/title/keywords/subject/creationDate/modDate

# CRITICAL: must save with garbage=4 to physically remove old metadata from file
# (in-place set just marks as unreferenced; garbage collection removes)
doc.save(output_pdf_path, garbage=4, deflate=True, clean=True)
doc.close()
```

### Pattern 2: Content-stream find-replace via update_stream

**What:** Read page content stream bytes → modify → write back
**When to use:** sanitize script step 2 (supplier-name find-replace) + step 3 (brand glyph operator block strip + replace)
**Example:**
```python
# Source: PyMuPDF recipes-low-level-interfaces.html + existing scratch attack script
# (.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py:84-114)
# [VERIFIED via existing 2026-05-28 forensic script that this exact pattern works on the
#  3013A-13A-C6-...pdf supplier file]

import re
import fitz

doc = fitz.open(raw_pdf_path)
page = doc[0]

# Step A: read content stream (may be multiple stream objects per page in CAD PDFs)
stream_bytes = page.read_contents()            # combined bytes view (read-only)
content_xrefs = page.get_contents()            # list of xref(s) backing the stream(s)
print(f"page has {len(content_xrefs)} content stream xref(s); combined size = {len(stream_bytes)} bytes")

# Step B: decode as latin-1 (1-to-1 byte preservation — same encoding scratch script used)
stream_text = stream_bytes.decode("latin-1")

# Step C: find-replace supplier name (literal byte substring match in content stream)
# CAVEAT: this only catches names rendered as ASCII text-show operators (BT … (NAME) Tj … ET).
# If supplier uses ToUnicode + custom font encoding, the literal "NAME" won't appear in the
# stream — see Pitfall 1 below. Mitigation: also walk PDF /Info dict + each Page /Resources
# for embedded /Title / /Author strings via doc.xref_object(xref, compressed=False).
stream_text = stream_text.replace("ACME_SUPPLIER_INC", "TESTCO")

# Step D: strip the supplier brand-glyph operator block.
# CAD-glyph supplier brand = a sequence of zero-area `m/l/f/B` operators wrapped in q…Q.
# Strategy: locate the q…Q block by ANY identifying anchor (typically a Tm matrix near the
# region rect, or the first `m/l/f` after a specific CTM), then `re.subn` the entire block.
# See pattern derivation in § 2.

# Step E: inject TESTCO wordmark zero-area path operator sequence at the same content-stream
# position with same CTM. See § 2 for the construction.
# Build the replacement byte string (latin-1 safe — ASCII subset).

# Step F: re-encode + write back via update_stream
new_bytes = stream_text.encode("latin-1")
if len(content_xrefs) == 1:
    doc.update_stream(content_xrefs[0], new_bytes, compress=True)
else:
    # multi-stream page: collapse all rewrites into first stream, empty the rest.
    # Scratch script's empirical pattern (proven on 3013A-...pdf which has 1 stream).
    doc.update_stream(content_xrefs[0], new_bytes, compress=True)
    for xref in content_xrefs[1:]:
        doc.update_stream(xref, b"", compress=True)

doc.save(output_pdf_path, garbage=4, deflate=True, clean=True)
doc.close()
```

### Pattern 3: pytest xfail strict regression test

**What:** Test that **expects** to fail in Phase 6 and **must** be promoted to pass (XPASS error) in Phase 7
**When to use:** `tests/test_illustrator_attack_regression.py` — the 3 parametrized regression cases
**Example:**
```python
# Source: pytest docs https://docs.pytest.org/en/stable/how-to/skipping.html
# [VERIFIED via WebSearch + WebFetch 2026-05-28]
# Pattern: strict=True turns XPASS into a hard test failure.
# This is the explicit Phase 6 → Phase 7 handoff signal — when implementer lands Option B
# and the test starts passing, pytest will FAIL with XPASS(strict) until they remove
# the @pytest.mark.xfail decorator.

import json
import pathlib
import pytest
import fitz

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "cad-glyph"

def _load_fixtures():
    """Discover all (pdf, manifest) pairs in tests/fixtures/cad-glyph/."""
    pairs = []
    for pdf in sorted(FIXTURES_DIR.glob("*.pdf")):
        manifest = pdf.with_suffix(".json")
        if not manifest.exists():
            pytest.fail(f"fixture {pdf.name} is missing sidecar manifest {manifest.name}")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        pairs.append(pytest.param(pdf, data, id=pdf.stem))
    return pairs

@pytest.mark.parametrize("fixture_pdf,manifest", _load_fixtures())
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Option B 尚未實作(Phase 7 SEC-01 待落地)— "
        "Illustrator-class editor 拔 image XObject 後 page content stream 內的零面積 "
        "type='f' 路徑仍會 render 出供應商商標。Phase 7 落地後請拔掉本 marker。"
        "參 .planning/REQUIREMENTS.md SEC-01。"
    ),
)
def test_illustrator_attack_residual_supplier_revealed(
    fixture_pdf, manifest, logo_library, isolated_data_dir
):
    """RED-LIGHT regression test for v1.1 Illustrator-class editor threat model.

    Steps:
      1. Ingest sanitized fixture PDF via app.services.ingest
      2. process_job with the manifest's region_rect, logo_id=None (pure removal)
      3. Apply attack: delete image XObject(s) intersecting region
      4. Assert region rendered ≥98% white AND zero-area type='f' count == 0
    """
    from app.services import ingest, pipeline, storage
    from tests._illustrator_attack import (
        delete_image_xobjects_intersecting,
        render_region_white_pct,
        count_zero_area_fills_in_region,
    )

    region_rect = manifest["region_rect"]    # [x0, y0, x1, y1]
    page_index = manifest["page_index"]      # int

    # 1. ingest
    session = ingest.ingest_upload(fixture_pdf.name, fixture_pdf.read_bytes())

    # 2. process
    pipeline.process_job(
        session.session_id,
        regions=[{"page_index": page_index, "rect": region_rect}],
        logo_id=None,
    )
    output_pdf = storage.work_path(session.session_id)  # whatever the pipeline produces

    # 3. attack
    doc = fitz.open(output_pdf)
    try:
        n_deleted = delete_image_xobjects_intersecting(doc, page_index, region_rect)
        attacked_pdf = output_pdf.with_name(output_pdf.stem + "_attacked.pdf")
        doc.save(attacked_pdf, garbage=4, deflate=True)
    finally:
        doc.close()
    assert n_deleted >= 1, "attack precondition: at least one image XObject must overlap region"

    # 4. assert (雙閘)
    white_pct = render_region_white_pct(attacked_pdf, page_index, region_rect)
    assert white_pct >= 98.0, (
        f"視覺乾淨閘失敗 — 框選區白佔比 {white_pct:.2f}% < 98% 門檻;供應商商標可能重現"
    )
    zero_area_count = count_zero_area_fills_in_region(attacked_pdf, page_index, region_rect)
    assert zero_area_count == 0, (
        f"content stream 乾淨閘失敗 — 框選區內仍有 {zero_area_count} 個 zero-area type='f' 路徑;"
        f"Option B content-stream surgery 未刪除"
    )
```

### Anti-Patterns to Avoid

- **手動編輯 sanitized fixture PDF**(直接用 vim / hex editor 改 supplier name):會破壞 PDF object xref table。**用 sanitization script**(D-A6 已鎖定)。
- **把 raw supplier PDF commit 進 repo**(即便短暫):git history 仍可恢復;違反 D-A4 「raw PDF 不進 git」。即使 `git rm` 後也須 `git filter-repo` 才能清除 — 不要犯這個錯。
- **以 `pytest.mark.skip` 取代 `pytest.mark.xfail(strict=True)`**:skip 不會在 Phase 7 自動失敗,失去 handoff signal。
- **不寫 sidecar manifest 直接硬編 region rect 進 test**:D-A1 sanitization 可能微調 region;manifest 才是 single source of truth。
- **在 `app/**/*.py` 任何檔案內 import fitz**:會破壞 AGPL guard test。Phase 6 所有 fitz 操作都在 `tests/` 或 `scripts/`。
- **在 sanitization script 內用 `page.insert_text` 渲染 TESTCO wordmark**:會產生**正常面積** glyph,不保留 zero-area `type='f'` attack 面 → 違反 D-A3 「保留同型 attack 面」。必須手工拼 zero-area path 算子。
- **`Document.update_stream` 對 `xref=0` 或 non-stream xref 呼叫**:會 raise exception。**必須先 `page.get_contents()` 拿到合法 content stream xref(s)**(scratch script 已 proven pattern)。
- **commit binary PDF 不附 README 例外說明**:打破 conftest 「only test harness may use fitz directly to BUILD fixtures」既有 convention。D-A6 已要求 README — planner 必須驗。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 解析 PDF 物件 / xref table | 從零寫 PDF parser | `fitz.open()` + `doc.xref_object(xref, compressed=False)` | PDF 物件圖極複雜(stream filter、indirect ref、cross-ref table、object streams)— PyMuPDF C 後端已處理 |
| 編輯 content stream 算子 | 寫一個 PDF content stream parser | `re.sub` over `latin-1` decoded bytes(scratch script 已 proven 對 CAD-glyph 有效) | content stream 操作只需 byte-substring match;**對 CAD-glyph 不需要 token-level parser**(scratch script 2026-05-28 forensic 已實證) |
| 找 image XObject resource name | 解析 `/Resources /XObject` dict 手寫 | `page.get_images(full=True)` 的第 8 個元素(name) | `_attack_delete_image_xobject.py:72-74` 已 proven 此 API 路徑 |
| 計算 fill area / bbox | 自己算 path operator coverage | `page.get_drawings()` 回傳 `type='f'/'s'`、`rect`、`fill`、`width`、`height` | 既有 `count_zero_area_fills_fully_inside` 已 import 此 helper(`pdf_engine.py:730-743`)|
| Render PDF region to pixels | 自己呼叫 mupdf C API | `page.get_pixmap(matrix=fitz.Matrix(4,4), clip=rect, alpha=False).samples` | scratch script `render_region` 已 proven(`_attack_delete_image_xobject.py:21-30`)|
| 判斷白佔比 | 自己 byte-loop | `np.frombuffer(...).reshape(...) → np.all(arr >= 250, axis=2).sum() / total` | scratch pattern 已 proven |
| 自動偵測 「test 是否該紅 / 該綠」 | 寫 framework-level switch | `pytest.mark.xfail(strict=True)` | strict=True 是設計給「expected fail 等下次 promote」的標準 pattern |
| 統一管理 fixture region_rect | 寫一個 fixture-loading framework | sidecar JSON manifest + `pytest.mark.parametrize` 在 collection time `glob` | python stdlib `pathlib.Path.glob` + `json.loads` 已足夠;不需 pydantic schema validation(planner 可選用 dataclass 增加 type safety,但非必要)|

**Key insight:** Phase 6 的所有「PDF 攻擊面操作」(read/edit content stream、find/delete image XObject、render to pixmap、count zero-area fills)都已在 2026-05-28 forensic scratch script 內 proven 可用。**研究結論:不需要新 library、不需要新 abstraction、不需要新 parser**。Phase 6 工作只是把 scratch 邏輯搬到 `tests/` 並包成 pytest fixture。

## Common Pitfalls

### Pitfall 1: ToUnicode CMap + custom font encoding 規避 text find-replace

**What goes wrong:** 供應商公司名在 PDF 內如果是 Illustrator / CAD 工具用「embedded subset font + custom encoding」渲染的(常見於品牌 wordmark),content stream 內出現的 byte 串不是 ASCII 公司名,而是 glyph index(例如 `\x05\x07\x08`),配 ToUnicode CMap reverse-map 回 Unicode。`str.replace("ACME", "TESTCO")` 完全 miss。
**Why it happens:** Illustrator embed font 為「subset」(只 include 用到的 glyph),encoding 是 ad-hoc CID,真正的 Unicode 對應透過 ToUnicode CMap object 提供。 PyMuPDF `page.get_text()` 會 decode,但 content stream 內的原始 byte 仍是 glyph index。
**How to avoid:** 兩條路:
  (a) **檢查 `page.get_text("words")`** — 若回傳含供應商名 → 公司名是「可 decode 文字」,find-replace 在 content stream 有機會;若回傳不含 → 公司名 likely 是 glyph index,需要走 (b)。
  (b) **走 brand-glyph operator block deletion path (D-A3)**:不嘗試 text-level find-replace,直接砍 brand glyph 的 `q...Q` block,再 inject TESTCO 零面積 wordmark。 D-A3 本來就是這個路線 — Pitfall 1 提醒 sanitize script 內 `replace(supplier_name, "TESTCO")` 是 **best-effort optimization**,主路徑是 brand-glyph deletion。
**Warning signs:** sanitize script 跑完 `page.get_text() 仍包含 supplier name`(assert failure)。

### Pitfall 2: PDF metadata in /Info dict vs XMP stream

**What goes wrong:** `doc.set_metadata({})` 只清 PDF `/Info` dict(老式 metadata)。現代 Illustrator / Acrobat 也會 embed **XMP metadata**(RDF/XML stream),`set_metadata` 不會碰。XMP 可能仍含供應商公司名 + 創作日期 + 軟體版本。
**Why it happens:** XMP 是 ISO 16684-1 標準的 metadata 重複儲存層;PyMuPDF `set_metadata` 是 legacy API。
**How to avoid:** sanitize script 也呼叫 `doc.set_xml_metadata("")`(或 `doc.set_xml_metadata(None)` 視 1.27.x 簽名)清空 XMP stream。`assert doc.get_xml_metadata() == ""` 加進 sanitize 後 self-check。
**Warning signs:** `strings sanitized.pdf | grep -i ACME` 仍命中供應商名。
[CITED: PyMuPDF Document API — set_xml_metadata exists in 1.27 series]

### Pitfall 3: `update_stream` 對 multi-stream page 的處理

**What goes wrong:** 一個 page 在 PDF 物件層可有 **多個 `/Contents` stream**(spec 允許);PyMuPDF `page.read_contents()` 合併讀,但 `page.get_contents()` 回 xref **列表**。若直接 `doc.update_stream(content_xrefs[0], modified_bytes)` 把合併版寫回第一個 stream,**其他 stream 的內容會殘留**,渲染時兩者 concat → 重複算子 → 錯誤渲染。
**Why it happens:** scratch script `_attack_delete_image_xobject.py:107-114` 已遇到並 handle:對第二個及之後的 stream 寫入 `b""` 清空。
**How to avoid:** 沿用 scratch pattern — 「write modified 到 [0],write `b""` 到 [1:]」。Sanitize script 對 multi-stream page 必須採同 pattern。
**Warning signs:** sanitize 後 PDF 在 Adobe Reader / Acrobat 中渲染出現 ghost 算子或重疊文字。

### Pitfall 4: pytest `--runxfail` 在 CI 中誤用會破壞 handoff signal

**What goes wrong:** 若 CI 設 `pytest --runxfail`,所有 xfail marker **被忽略**,test 當普通 test 跑。Phase 6 紅燈 → CI FAIL → 推回 implementer 「修 test」。但 test 是 **設計成紅燈**,implementer 拿不到正確 signal。
**Why it happens:** `--runxfail` 是 debug flag,某些 team 開機式打開。
**How to avoid:** Phase 6 PLAN.md tasks 明確寫「CI 與 local pytest invocation 不可加 `--runxfail`」。`pytest.ini` 不加此 flag(目前已驗證 `pytest.ini` 只有 `-p no:cacheprovider` — clean)。在 `tests/test_illustrator_attack_regression.py` 開頭 module docstring 註記此 invariant。
**Warning signs:** Phase 6 close 後 CI test 顯示 `FAILED` 而非 `XFAIL`。
[CITED: pytest docs — `--runxfail` 強制忽略所有 xfail marker]

### Pitfall 5: `pytest.mark.xfail` 與 parametrize 順序 + `strict_xfail` ini option 衝突

**What goes wrong:** 把 `@pytest.mark.xfail(strict=True)` 寫在 `@pytest.mark.parametrize` **上面**(decorator stack 順序),3 個 parametrized cases 共用一個 xfail decorator → ok。但若 pytest.ini 設 `strict_xfail = true` global default,**所有沒 explicit `strict=False` 的 xfail 會變 strict** — 對 Phase 6 OK(我們本來就要 strict),但對 future test 可能誤傷。
**Why it happens:** pytest 設計 — `strict_xfail` ini option 為 project-wide default。
**How to avoid:** 顯式寫 `strict=True` 在 marker,不依賴 ini default。Phase 6 不動 `pytest.ini`(`strict_xfail` 不加)。每個 xfail call site 自己 explicit。
**Warning signs:** future 不相關的 xfail test 突然 XPASS(strict) 失敗。

### Pitfall 6: `pathlib.Path.glob` 順序非穩定 → parametrize id 漂移

**What goes wrong:** `FIXTURES_DIR.glob("*.pdf")` 在不同 OS / filesystem 順序不一致(Linux ext4 是 inode order,Windows NTFS 是字典序,macOS APFS 取決於 case-sensitivity)。pytest parametrize 的 test id 跟著漂移,reports 比較困難。
**Why it happens:** glob 本身不保證順序(POSIX 規範未強制)。
**How to avoid:** Pattern code 已含 `sorted(FIXTURES_DIR.glob("*.pdf"))` — **必須 sorted**。Pattern 3 已示範。
**Warning signs:** 同一 commit 在 CI vs local 看到不同 parametrize order。

### Pitfall 7: fixture region_rect 與 sanitization brand-glyph deletion 範圍不一致

**What goes wrong:** D-A3 要求 brand glyph 整段刪除以 TESTCO 替換。如果替換的 TESTCO 算子 bbox **不完全 fully inside** sidecar manifest 的 region_rect → `count_zero_area_fills_fully_inside` 會回傳 < 原 count 90% → sanitize script 的 self-check fail(D-A3 驗證點)。
**Why it happens:** TESTCO 字形 bbox 大小手算容易跟 region_rect 不對齊;CTM 變換沒考慮對。
**How to avoid:** sanitization script 先讀「原 brand glyph 的 bounding rect」(`page.get_drawings()` 過濾 supplier-related fills),用該 bbox 作 TESTCO wordmark 的 layout box,再以原 CTM 變換進 content stream。`--region-rect` arg 用作 outer constraint(TESTCO bbox 必須 ⊂ region_rect)。
**Warning signs:** sanitize script self-assert `count_zero_area_fills_fully_inside ≥ 0.9 * original` 失敗。

### Pitfall 8: Phase 6 attack regression test 對 attacked PDF render 時 fitz 可能「自動修復」content stream

**What goes wrong:** PyMuPDF `fitz.open` 對 malformed content stream 會做容錯修復(parse-and-rebuild)。如果 attack 留下不平衡的 q/Q stack(刪除 `q ... Do ... Q` 區塊時偶有殘留),fitz render 可能「智能」補回 — 導致 attack output 在 fitz render 下看起來「乾淨」(白佔比高),但 Adobe Reader render 仍露出供應商商標。**雙閘 (D-B5) 設計就是要抓這個** — `count_zero_area_fills_in_region == 0` 直接看 content stream object,不受 render 容錯影響。
**Why it happens:** mupdf 設計目標是「能 render 大多數 broken PDF」,容錯是 feature。
**How to avoid:** 保留 **雙閘**,不要為了精簡刪掉 zero-area count assertion。D-B5 已鎖定。 Phase 7 implementer 兩個都得過。
**Warning signs:** 視覺白佔比 ≥ 98% 但 zero-area count > 0 → 中間區,Phase 7 implementation 不完整。

## Code Examples

### Common Operation 1: 偵測哪些 image XObject overlap region rect

```python
# Source: existing scratch script .planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py:40-49
# [VERIFIED 2026-05-28 forensic on 3013A-13A-C6-...pdf]

import fitz

def find_image_xrefs_intersecting(page: fitz.Page, region: fitz.Rect) -> list[int]:
    xrefs = []
    for img in page.get_images(full=True):
        xref = img[0]
        for bbox in page.get_image_rects(xref):
            if fitz.Rect(bbox).intersects(region):
                xrefs.append(xref)
                break
    return xrefs
```

### Common Operation 2: 找 image XObject resource name (for content-stream surgery)

```python
# Source: existing scratch script :70-74
# [VERIFIED 2026-05-28]

def find_resource_names(page: fitz.Page, target_xrefs: set[int]) -> set[str]:
    names = set()
    for img_info in page.get_images(full=True):
        xref, _, _, _, _, _, _, name = img_info[:8]
        if xref in target_xrefs:
            names.add(name)
    return names
```

### Common Operation 3: Strip `q ... /<Name> Do ... Q` operator block

```python
# Source: existing scratch script :87-102
# [VERIFIED 2026-05-28 forensic — exact regex pattern used in attack proof-of-concept]

import re

def strip_xobject_invocation(stream_text: str, xobject_name: str) -> tuple[str, int]:
    """Return (new_stream_text, count_removed). xobject_name format: '/Im0' or 'Im0'."""
    pattern = re.compile(
        r"q\b[^Q]*?/" + re.escape(xobject_name.lstrip("/")) + r"\s+Do\b[^Q]*?Q\b",
        re.DOTALL,
    )
    new_text, n = pattern.subn("", stream_text)
    # Also strip stray bare `/<Name> Do` not wrapped in q...Q (rare in CAD PDFs):
    bare = re.compile(r"/" + re.escape(xobject_name.lstrip("/")) + r"\s+Do\b")
    new_text, m = bare.subn("", new_text)
    return new_text, n + m
```

### Common Operation 4: Compose TESTCO wordmark as zero-area type='f' operator sequence

```python
# Source: synthesis of PyMuPDF content-stream operator grammar + existing test pattern
# `test_remove_region_vector_dense_real_zero_area_paths_end_to_end` (tests/test_redact.py:722-728)
# which uses Shape.draw_rect(W=0).finish(fill=) to produce real zero-area type='f' fills.
# [VERIFIED via existing test: zero-area type='f' fills surface in page.get_drawings() with
#  type='f' + bbox W=0]

# Approach A — use fitz Shape API (cleaner, no manual operator string composition):
def inject_testco_glyph(page: fitz.Page, anchor: fitz.Rect, n_strokes_per_char: int = 10):
    """Build a TESTCO wordmark of zero-area type='f' fills anchored at `anchor`.

    Each letter is rendered as `n_strokes_per_char` vertical zero-width filled lines
    spread across the letter's bbox. Width=0 → zero-area → attack-surface-equivalent
    to supplier brand glyph decomposition.
    """
    letters = "TESTCO"
    letter_w = anchor.width / len(letters)
    for i, _ch in enumerate(letters):
        x_start = anchor.x0 + i * letter_w
        for j in range(n_strokes_per_char):
            x = x_start + j * (letter_w / n_strokes_per_char)
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(x, anchor.y0, x, anchor.y1))  # W=0 → zero-area
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()

# Approach B — manual content stream operator string (used if A's output is not at
# the exact required position with the supplier's CTM). Append after stripping the
# original brand glyph block via doc.update_stream:
#
#   q
#   <ctm: 6 numbers> cm        % preserve supplier's CTM
#   <x> <y> m                  % moveto
#   <x> <y> l                  % lineto (same point → zero-area)
#   f                          % fill
#   ... (repeat per stroke)
#   Q

# Recommend Approach A first — Shape API handles CTM via page coords directly and the
# resulting drawings.type == 'f' / bbox-W=0 has been independently verified in
# tests/test_redact.py:722-728. Approach B is fallback if A's resulting bbox doesn't
# land where required.
```

### Common Operation 5: 算白佔比

```python
# Source: existing scratch script :21-30
# [VERIFIED 2026-05-28]

import numpy as np

def render_region_white_pct(pdf_path, page_index: int, rect: tuple[float, float, float, float]) -> float:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        pm = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(*rect), alpha=False)
        arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
        return round(100 * np.all(arr >= 250, axis=2).sum() / arr[..., 0].size, 2)
    finally:
        doc.close()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pypdf` / `PyPDF2` content-stream edit | PyMuPDF `Document.update_stream` | PyMuPDF 1.18+(2021) | pypdf 沒有等效的 stream rewrite API;PyMuPDF 才是正解 |
| `doc.setMetadata({})`(camelCase) | `doc.set_metadata({})`(snake_case) | PyMuPDF 1.17(2020) PEP-8 rename | 兩者都還 work;新 code 用 snake_case |
| `doc.xref_set_stream(xref, bytes)` (low-level) | `doc.update_stream(xref, bytes)` (modern wrapper) | PyMuPDF 1.18(2021) | 兩者都還 work,但 `update_stream` 自動 compress + 處理 non-stream xref 例外較友善 |
| pytest `@pytest.xfail`(bare decorator) | `@pytest.mark.xfail(strict=...)`(marker) | pytest 3.0(2016) | 新 code 必須用 marker 形式 |

**Deprecated/outdated:**
- 任何 `import fitz; fitz.open(...).setMetadata(...)` camelCase 形式 — PEP-8 alias 仍 work 但 docs 已不再展示
- `doc.xrefSetStream(...)` — 1.18 前的 camelCase 名 — 不該用於新 code

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sanitization script 的 latin-1 round-trip(`stream_bytes.decode("latin-1") → modify → encode("latin-1")`)對所有 supplier PDF 都安全 | Pattern 2, § 1 | LOW — scratch script 2026-05-28 已在 3013A-13A-C6-...pdf 上 proven。但若工程師交付的另外 ≥2 個 supplier PDF 內含「真正的 UTF-8 byte sequence in /Title」(rare),latin-1 round-trip 仍 OK(latin-1 是 byte-transparent),但理論可能踩到 PDF stream encoder edge case。**Mitigation:** sanitize script self-check `assert page.get_text()` 不含 supplier name 後才 save |
| A2 | Approach A(`Shape.draw_rect(W=0).finish(fill=...)`)產生的 zero-area `type='f'` glyph 真的會在 `count_zero_area_fills_fully_inside` 中被 count | Pattern 4 / Common Op 4 | LOW — `tests/test_redact.py:722-728` 既有 test 已 verify 此確切 pattern produces `type='f'` with bbox W=0,且 `count_zero_area_fills_fully_inside` 會 count(integration test passing in v1.0 close baseline) |
| A3 | `gsd-secure-phase` agent 對 「pre-mortem 變體」(no commits to audit、threats_open ≠ 0 by design)能正確 dispatch | § 5 / Pre-mortem Schema | MEDIUM — `gsd-secure-phase` workflow.md 的 `register_authored_at_plan_time` 邏輯設計是「PLAN.md 有 `<threat_model>` block → verify mode;沒有 → retroactive STRIDE」,Phase 6 走「PLAN.md 內列出 06-SECURITY.md 將 author 的 threats → register_authored_at_plan_time: true」。**Risk:** secure-phase agent 在 Phase 6 close 時可能 BLOCK advancement(threats_open > 0);Phase 6 design 故意 leave threats open。**Mitigation:** Phase 6 PLAN.md 必須明確將 T-02-07 + T-06-01 都列為 `accept (until Phase 7 closes)` 或寫進 Accepted Risks Log,讓 secure-phase agent 看到 `threats_open: 0` |
| A4 | 工程師會在一週內交付 ≥2 個額外 supplier PDF(D-A1) | Open Question Q1 | MEDIUM — 取決於工程師排程。**Contingency** 詳 Open Question Q1 |
| A5 | `page.get_text("words")` 對所有 supplier PDF 都能回傳 decoded supplier name(若名字是 ASCII text-show 渲染) | Pitfall 1 | MEDIUM — Illustrator subset font 是 corner case;若 3 個 fixture 都遇到,sanitize script 需特別寫 CMap decode helper(已在 Deferred 列為 corner-case helper 不通用化)|
| A6 | `pytest.ini` 沒被任何 dev / CI invocation 覆寫 `--runxfail` | Pitfall 4 | LOW — verified `pytest.ini` clean;但若 Zeabur CI 設此 flag 會破壞 handoff signal,**Mitigation:** Phase 6 PLAN.md 內 task 明文寫「驗證 CI 不加 `--runxfail`」 |
| A7 | `samples/3013A-...pdf` 與 repo root 同檔的處置(留 vs 移到 archived 同層)由 planner 自主決定,沒有遺漏 issue | Claude's Discretion (CONTEXT.md) | LOW — CONTEXT.md 已標為 planner discretion;但提醒 planner:既有 `_attack_delete_image_xobject.py:12-13` hard-code 此路徑,若移動,scratch archived README 內須註記新位置 |

## Open Questions(全部 RESOLVED 2026-05-28)

1. **〔RESOLVED 2026-05-28〕工程師交付 ≥2 個 supplier PDF 的時程不確定** — D-A1 假設「一週內」可交;若 Phase 6 plan 跑到實作階段仍未交付,需 fallback。
   - 我們知道的: repo root 既有 `3013A-13A-C6-XX-3D02-A01-00040.pdf` 為第 1 個,夠合 1 個 fixture(planner 決定 map 到 text-glyph / figure-glyph / mixed 的哪個 slot)
   - 不明處: 其他 2 個 fixture 是否會準時到位
   - 建議: planner 在 PLAN.md tasks 列入 **contingency** — 若工程師未準時,用 synthetic CAD-glyph fallback(沿用 `test_remove_region_vector_dense_real_zero_area_paths_end_to_end` 的 fitz Shape API pattern,在 sanitization script 增加 `--synthesize` mode 或寫獨立 `tests/conftest.py::synthetic_cad_glyph_pdf_bytes` fixture builder)。記入 STATE.md「Phase 6 fixture 構成:N 個 real + M 個 synthetic」以便追蹤
   - **Resolution:** Phase 6 plan 走 contingency(1 real + 2 synthetic) close 為 PROVISIONAL。同日 post-close maintenance round 內,工程師交付 2 個額外 supplier PDF(`3013A-36A-C6-W4.pdf` + `B-3012IP-WM02-T430.pdf`,同為 `宁波登骐 / Ningbo Dengqi` 不同 SKU),補強 sanitize_fixture.py Impl notes C + D(commit `0045c6b`)後重跑成功,3/3 fixture 升級為 real(commit `f7f34e8`)。PROVISIONAL banner 移除。

2. **〔RESOLVED 2026-05-28〕`scripts/sanitize_fixture.py` 處理 CMap-encoded supplier name 的深度** — Pitfall 1 列為 corner case。
   - 我們知道的: scratch script 對 3013A-13A-C6-...pdf 的 supplier-name find-replace 是否有效尚未 forensic 驗證(2026-05-28 attack proof 只證明 image XObject delete 攻擊成立,沒測 text replace)
   - 不明處: 3 個 fixture 各自的供應商 wordmark 是「ASCII text-show」還是「subset font + CMap」
   - 建議: sanitize script 第一版 **不寫 CMap decoder**;遇到 CMap-encoded name 時 fall back to D-A3 brand-glyph deletion path(本來就是主路徑)+ `page.get_text("words")` self-check。若三個 fixture 都遇到 CMap 名 → 此 Open Question 升為 Phase 6 closing 的「實踐記錄」記入 STATE.md;若一個都沒遇到 → 此問題自動解決
   - **Resolution:** Plan 06-01 原始 close 時 mixed-glyph-01 沒觸發 CMap fallback(supplier name 不在 get_text)。Post-close 2026-05-28 — text-glyph-01(`3013A-36A-C6-W4.pdf`)觸發 CMap fallback(B 不夠),補強為 Impl note C(glyph-level `add_redact_annot + apply_redactions`)後仍不足(supplier 在 Form-XObject stamp annotation appearance 內);再補強為 Impl note D(`page.delete_annot()` 整塊刪 stamp annotation)才解決。fallback chain 為 A → B → C → D,對未來 PScript5 + Acrobat 出口 PDF 通用(commit `0045c6b`)。

3. **〔RESOLVED 2026-05-28〕`samples/3013A-...pdf` 與 repo root 同檔的最終處置** — CONTEXT.md 列為 Claude's Discretion,但研究結論偏好:**移到 `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/`** 同層,加 `.gitignore` 護欄。
   - 我們知道的: 該檔含原供應商名 — 不安全留 public repo
   - 不明處: 重命名後 `_attack_delete_image_xobject.py` 既有 path 引用是否仍需可 resolve(該 .py 即將 archived 也不執行,故 path 引用不會被執行)
   - 建議: planner 在 06-02 plan 內加一個 task 「移動 raw supplier PDF 到 archived 同層 + 更新 .gitignore + scratch archived README 註記原路徑」
   - **Resolution:** Plan 06-02 Task 4 已執行 `git rm samples/3013A-...pdf` + 物理 mv 至 archived 路徑 + `.gitignore` archived-anchored guard 加入。Post-close 2026-05-28 — 額外的 2 個 supplier PDF(`3013A-36A-...` + `B-3012IP-...`)也走同樣處置(物理 mv 至 archived,gitignore patterns 擴充為 `/3013A-36A-*.pdf` + `/B-3012IP-*.pdf` + archived-dir 對應 patterns)。`git ls-files | grep -E '3013A\|B-3012IP'` empty,phase-level invariant 達成。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PyMuPDF (`fitz`) | sanitize script + attack helper + regression test | ✓ (pinned `>=1.27,<1.28`) | 既有 pin verified in requirements.txt:5 | — |
| pytest | regression test runner | ✓ (in requirements.txt:18) | unpinned;CI 用最新 stable(8.x 在 2026-05 為 current) | — |
| numpy | render_region_white_pct in attack helper | ✓ (transitive — 既有 scratch script 已用) | 沿用既有版本 | — |
| Python 3.10+ | runtime | ✓ (per STACK.md Python 3.12 recommendation) | 既有 | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 6 無 auth flow |
| V3 Session Management | no | Phase 6 不改 session |
| V4 Access Control | no | Phase 6 不改 access |
| V5 Input Validation | partial | sanitize script 接受 user-supplied `--supplier-name` arg + `--region-rect` parsed coord — 信任 dev maintainer input,但 region_rect 字串應 `int(x)` parse with explicit `ValueError` handling |
| V6 Cryptography | no | Phase 6 不引入新 crypto |
| V14 Configuration | no | 不改 config |

### Known Threat Patterns for Phase 6 stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sanitized fixture 仍含 supplier metadata 殘留 | I (Information disclosure) | sanitize script 內 self-assert(`get_metadata == {}`、`get_text` 不含 supplier name、`xml_metadata == ""`)+ 任何 fail → script exit non-zero 不寫 output |
| Raw supplier PDF 意外 commit | I (Information disclosure) | .gitignore 加 `*supplier*.pdf` pattern + sanitize script `--out` arg 強制路徑必須 in `tests/fixtures/cad-glyph/`(reject outside)+ Phase 6 PLAN.md 列入 task 「git status 跑完 sanitize 後驗證無 supplier PDF 在 staging」|
| Brand glyph 殘留(D-A3 替換不完整) | I (Information disclosure) | sanitize script self-check `count_zero_area_fills_fully_inside ≥ 0.9 * original` + post-render visual diff(可加但非 hard requirement) |
| pytest xfail marker 被誤拔(false handoff signal) | T (Tampering — process tampering) | Phase 6 → 7 handoff 設計就是「strict=True 自動 catch」;Phase 7 implementer 必須在 commit message 明文寫「removed @pytest.mark.xfail per Option B landing」+ code review 驗 |

### STRIDE Pre-mortem (供 06-SECURITY.md 撰寫參考)

Phase 6 06-SECURITY.md 內須包含的 STRIDE 表(由 planner 在 06-SECURITY.md 內成稿):

| Threat ID | Category | Actor | Disposition | Status | Evidence / Closing condition |
|-----------|----------|-------|-------------|--------|------------------------------|
| T-02-07 | I — TRUE REMOVAL vs cover(supersede archived `06-HOTFIX-SECURITY.md` 中相同 ID) | Illustrator-class editor attacker | mitigate(已 archive)+ **RE-OPENED 2026-05-28** pending Option B | **RE-OPENED** | RE-OPENED 證據:`.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png`、`tests/test_illustrator_attack_regression.py` 紅燈;closing condition:Phase 7 落地 Option B → `07-SECURITY.md` 中重新 CLOSED |
| T-06-01 | S + I — Illustrator pulls image XObject overlay → supplier brand re-rendered from zero-area type='f' source | Illustrator-class editor attacker | mitigate(pending Option B in Phase 7) | OPEN | Evidence:`_attack_proof_supplier_revealed.png` + 新 pytest 紅燈;closing condition:同 T-02-07 |
| T-06-02(可選 by planner) | T — pytest xfail marker tampering(implementer 在沒落地 Option B 的情況下手動拔掉 marker) | Phase 7 implementer | mitigate via process | accept(P3,UAT 期間 review pass 攔截) | code review + strict=True 機制本身(只要 marker 在,test 失敗的話不影響 exit code;沒落地 Option B 拔了 marker,test 會 FAIL,CI 攔截) |

**Pre-mortem 與 audit-time SECURITY.md 差異(planner 在 06-SECURITY.md 內須明說):**

| 屬性 | Phase 6 (Pre-mortem) | v1.0 hotfix-06 (Audit-time) |
|------|-----------------------|------------------------------|
| audit_scope | `phase_06_pre_mortem`(非真實 audit) | `hotfix_06_dct_residue` |
| diff_base | N/A — phase 內無 production code commits | `f911139..HEAD` |
| commits_audited | empty list | 4 commits 列舉 |
| threats_total | 2 (T-02-07 RE-OPENED + T-06-01 OPEN) | 5 |
| threats_closed | 0(by design — close 在 Phase 7) | 4 mitigate + 1 accept = 5 |
| threats_open | 2(by design)— **planner 必須在 Accepted Risks Log 將 T-02-07 + T-06-01 標為 `accept (P0, transition-pending until Phase 7)`** 以讓 `gsd-secure-phase` agent 不 BLOCK(見 A3) | 0 |
| register_authored_at_audit_time | true | true |
| live_uat_verified_at | N/A | 2026-05-27 |
| supersedes | `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md`(T-02-07 disposition) | — |
| superseded_by(forward link)| N/A(到 Phase 7 才補) | `06-SECURITY.md` 內的 T-02-07 RE-OPENED 條目 |

## Sources

### Primary (HIGH confidence)
- `requirements.txt:5-19` - PyMuPDF / pytest / numpy 既有 pin(verified by Read tool)
- `pytest.ini` - 既有 pytest 配置 clean,無 `--runxfail`(verified by Read tool)
- `tests/conftest.py:12` - 「only the test harness may use fitz directly to BUILD fixtures」既有 exception(verified)
- `tests/test_redact.py:691-794` - `test_remove_region_vector_dense_real_zero_area_paths_end_to_end` 既有 dense-branch end-to-end test pattern,zero-area `m/l/f` 用 `Shape.draw_rect(W=0).finish(fill=)` 已驗證(verified by Read tool)
- `tests/test_redact.py:1190-1207` - `test_fitz_import_confined_to_engine_seam` AST guard,scope = `app/**/*.py`(verified)
- `app/services/pdf_engine.py:699-743` - `count_zero_area_fills_fully_inside` API,使用 `_DEGENERATE_BBOX_EPS = 0.01` tolerance(verified)
- `app/services/pdf_engine.py:294` - `ZERO_AREA_RASTER_THRESHOLD = 100`(verified)
- `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py` - 完整 attack pattern proven 2026-05-28 on 3013A-...pdf(verified)
- `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md` - SECURITY.md frontmatter schema reference + T-02-07 superseded source(verified)
- `https://pymupdf.readthedocs.io/en/latest/recipes-low-level-interfaces.html` - `xref_stream` + `update_stream` recipe(WebFetch 2026-05-28)
- `https://docs.pytest.org/en/stable/how-to/skipping.html` - xfail strict=True 行為 + `--runxfail` 互動(WebFetch + WebSearch 2026-05-28)

### Secondary (MEDIUM confidence)
- PyMuPDF Wiki "Using setMetadata() and setToC()" - `set_metadata({})` 清空語意(WebSearch 2026-05-28,1.18.4 起空值不寫入)
- Paul Ganssle blog "How and why I use pytest's xfail" - strict=True 為 「accidental fix detection」標準慣例(WebSearch 2026-05-28)
- Medium / Pragmatic Programmers "Disallowing XPASS" - `strict_xfail` ini option 用法(WebSearch 2026-05-28)

### Tertiary (LOW confidence)
None — all critical claims verified against either official docs, existing repo code, or proven scratch script.

## Project Constraints (from CLAUDE.md)

- **GSD Workflow Enforcement** — Phase 6 必須走 `/gsd-plan-phase 6` → `/gsd-execute-phase 6`,不可直接 Edit/Write 進 repo 外的 GSD 流程
- **核心 stack 鎖定** — PyMuPDF (核心 PDF 處理) + FastAPI + PDF.js + Pillow + numpy。Phase 6 不引入新 dep
- **AGPL §13 三件套** — 既有就位(public GitHub + LICENSE + UI source link);Phase 6 不動部署文件
- **fitz seam** — `import fitz` 嚴格限 `app/services/pdf_engine.py`;scripts/ 與 tests/ 為既有例外
- **Python 3.10+**(STACK.md 推薦 3.12);PyMuPDF 1.27.x cp310-abi3 wheel covers 3.10-3.14
- **No PyPDF2 / pypdf for removal step**(per STACK.md What NOT to Use):Phase 6 內所有 PDF 操作走 PyMuPDF;sanitize script 不引入 pypdf 即便其 metadata API 看似簡單
- **No Celery / no DB / no auth in v1**(per STACK.md):Phase 6 是純 test/docs,不會誤碰
- **繁中 user-facing 文案**(memory feedback_language):xfail reason 字串、SECURITY.md 內文、sanitize script CLI 訊息採繁中。Python identifiers 與 pytest marker 維持英文
- **Per-phase quality gates**(memory feedback_quality_gates):review/fix + validate + secure 在每個 phase 邊界都跑,Phase 6 close 前須跑 `gsd-secure-phase` 對 06-SECURITY.md 做 verification — A3 已分析此 agent 對 pre-mortem 變體的處理需在 plan 內 explicit handle
- **Commit/push cadence**(memory feedback_commit_push_cadence):Phase 6 沿用 — UAT 期間 commit local but never push;hotfix inline;push 留到 Phase 8 LIVE-UAT
- **5330290 minimum-change 教訓**:Phase 6 不夾帶 polish / nice-to-have(任何超出 phase boundary 的優化推到 maintenance sprint)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - 沿用既有 pinned stack,無新增 dep
- PyMuPDF sanitization API: HIGH - `set_metadata({})` + `update_stream` 雙雙 verified via PyMuPDF docs + existing scratch script proven 對 3013A-...pdf 有效
- Content-stream operator semantics: HIGH - 既有 `tests/test_redact.py:722-728` 已實證 `Shape.draw_rect(W=0).finish(fill=)` 產 zero-area `type='f'`
- pytest.xfail(strict=True): HIGH - 官方 docs + 多重 secondary source 一致
- Sidecar JSON manifest pattern: HIGH - `pathlib.Path.glob` + `json.loads` + `pytest.mark.parametrize` 都是 stdlib / pytest 標準
- Per-phase SECURITY.md schema: MEDIUM - 既有 archived `06-HOTFIX-SECURITY.md` 提供完整 reference,但 pre-mortem 變體對 `gsd-secure-phase` agent 的 dispatch 行為有 A3 列出的 MEDIUM risk
- AGPL seam considerations: HIGH - AST guard test `test_fitz_import_confined_to_engine_seam` scope 已驗證為 `app/**/*.py` only
- Test harness scaffolding: HIGH - tests/ 既有 `__init__.py` 顯示 tests/ 是 package,`tests/_illustrator_attack.py` 可直接 `from tests._illustrator_attack import ...`;`pathlib.Path(__file__).parent / "fixtures"` 為標準慣例
- Pitfalls: MEDIUM-HIGH - 8 個 Pitfall 中 6 個有具體 evidence(既有 scratch / test code);2 個(Pitfall 1 CMap + Pitfall 7 region misalignment)為 logical inference

**Research date:** 2026-05-28
**Valid until:** 2026-06-28(30 天,stack 為 stable pinned;若 PyMuPDF 1.28.x 上市則 invalidates xref_stream / update_stream 部分)
