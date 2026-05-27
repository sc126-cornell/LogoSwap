# Phase 6: Regression Foundation + Threat Model Re-evaluation — Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 9 (7 new + 2 rename/cleanup ops)
**Analogs found:** 8 / 9 (one file — `cad-glyph/README.md` — has no analog; first-of-kind docs)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/sanitize_fixture.py` | dev-tooling CLI script | batch (read PDF → mutate → write PDF) | `scripts/smoke_02_03.py` | role-match (CLI shape) + `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py` (PDF surgery mechanics) |
| `tests/_illustrator_attack.py` | test helper module | transform (open → mutate/inspect → bytes/metrics) | `.planning/debug/scratch/.../_attack_delete_image_xobject.py` | exact (source-of-truth attack logic) + `tests/conftest.py:1-12` (license-to-import-fitz precedent) |
| `tests/test_illustrator_attack_regression.py` | pytest regression test (parametrized + xfail) | request-response (build-state → assert) | `tests/test_redact.py::test_remove_region_vector_dense_real_zero_area_paths_end_to_end` (line 691-794) | exact (same end-to-end "build PDF → run pipeline → assert" + xfail-strict is first-of-kind in repo) |
| `tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.pdf` | committed binary fixture | static asset | NONE — first committed-binary exception | NO ANALOG (greenfield) |
| `tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.json` | sidecar JSON manifest | static metadata | `logos/manifest.json` | role-match (same JSON-sidecar-describing-binary-assets pattern) |
| `tests/fixtures/cad-glyph/README.md` | doc explaining committed-binary exception | static docs | NONE — first-of-kind | NO ANALOG (greenfield) |
| `.planning/phases/06-.../06-SECURITY.md` | per-phase STRIDE threat model (pre-mortem variant) | static docs | `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md` | role-match (frontmatter + STRIDE table format identical; pre-mortem semantics differ) |
| **RENAME** `.planning/debug/scratch/illustrator-attack-2026-05-28/` → `…-archived/` + delete `.py` files + add new `README.md` | cleanup op | N/A | NONE (no rename precedent in repo) | NO CODE ANALOG (file-ops only) |

---

## Pattern Assignments

### `scripts/sanitize_fixture.py` (dev-tooling CLI, batch transform)

**Analog A (CLI shell pattern):** `scripts/smoke_02_03.py` lines 1-35, 53-55, 160-162
**Analog B (PDF surgery mechanics):** `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py` lines 40-49, 70-74, 84-115

**CLI-script skeleton pattern** — from `scripts/smoke_02_03.py:1-35`:
```python
"""<繁中 module docstring 描述工具用途>"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repo root (parent of scripts/) is importable when run as `python scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Print CJK cleanly on the Windows console (cosmetic; avoids mojibake in the smoke output).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import fitz  # scripts/ is OUTSIDE the AGPL guard scope (app/**/*.py only) — fitz import is fine

def main() -> int:
    ...
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Image-XObject discovery pattern** — from scratch script lines 40-49 (REUSE VERBATIM in helper functions):
```python
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

**XObject resource-name resolution** — from scratch script lines 70-74:
```python
xobj_names_for_target = set()
for img_info in page.get_images(full=True):
    xref, _, _, _, _, _, _, name = img_info[:8]
    if xref in image_xrefs:
        xobj_names_for_target.add(name)
```

**Content-stream `q ... /<Name> Do ... Q` block strip** — from scratch script lines 84-102 (REUSE VERBATIM):
```python
stream_bytes = page.read_contents()
stream_text = stream_bytes.decode("latin-1")
for name in xobj_names_for_target:
    pattern = re.compile(
        r"q\b[^Q]*?/" + re.escape(name.lstrip("/")) + r"\s+Do\b[^Q]*?Q\b",
        re.DOTALL,
    )
    new_text, n = pattern.subn("", stream_text)
    stream_text = new_text
# Also blank out any stray `<Name> Do` not wrapped in q...Q.
for name in xobj_names_for_target:
    pattern = re.compile(r"/" + re.escape(name.lstrip("/")) + r"\s+Do\b")
    new_text, n = pattern.subn("", stream_text)
    stream_text = new_text
```

**Multi-stream `update_stream` write-back** — from scratch script lines 104-115 (CRITICAL: handles Pitfall 3 multi-stream pages):
```python
new_bytes = stream_text.encode("latin-1")
content_xrefs = page.get_contents()
if len(content_xrefs) == 1:
    doc.update_stream(content_xrefs[0], new_bytes, compress=True)
else:
    # multi-stream page: collapse rewrites into [0], empty the rest
    doc.update_stream(content_xrefs[0], new_bytes, compress=True)
    for xref in content_xrefs[1:]:
        doc.update_stream(xref, b"", compress=True)
doc.save(output_path, garbage=4, deflate=True, clean=True)
```

**TESTCO wordmark zero-area-path injection** — from `tests/test_redact.py:722-728` (use `Shape.draw_rect(W=0)` to produce real zero-area `type='f'` fills):
```python
n = pdf_engine.ZERO_AREA_RASTER_THRESHOLD + 20  # ensure ≥ threshold after replacement
for i in range(n):
    x = 55.0 + i * 2.0
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(x, 110.0, x, 190.0))  # W=0 → zero-area type='f'
    shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
    shape.commit()
```

**Differences from analog:**
- Smoke script drives FastAPI TestClient; sanitize script does NOT touch HTTP — pure local file mutation.
- Scratch script is a fire-and-forget proof-of-concept with hardcoded paths (`ORIG`, `TARGET`, `REGION`); sanitize script must accept CLI args (`--in`, `--out`, `--supplier-name`, `--region-rect`) per D-A4. Parse `--region-rect "x0,y0,x1,y1"` with explicit `int(x)` / `float(x)` + `ValueError` handling (V5 ASVS input validation, RESEARCH § Security Domain).
- Sanitize script adds 4 ordered steps (metadata clear → content-stream find-replace → brand-glyph deletion → bbox/fingerprint cleanup) that the scratch script does NOT do (scratch only deletes image XObjects).
- Sanitize script must self-assert before saving: `len(doc.get_metadata()) == 0`, supplier name not in `page.get_text()`, `count_zero_area_fills_fully_inside(page, REGION) >= 0.9 * original_count` (per D-A3). On any assert failure → exit non-zero, do NOT write output (T-06 mitigation per RESEARCH "Known Threat Patterns").
- Add `doc.set_xml_metadata("")` after `doc.set_metadata({})` to cover XMP stream too (Pitfall 2 in RESEARCH).
- 繁中 CLI messages (`print("步驟 1: 清空 metadata...")`) per memory `feedback_language` + CONTEXT carrying-forward.

---

### `tests/_illustrator_attack.py` (test helper module, transform)

**Analog:** `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py` (entire file) + `tests/conftest.py:1-12` (fitz license precedent)

**Module-docstring + fitz-license note** — from `tests/conftest.py:1-13` (mirror the same justification):
```python
"""<繁中 module docstring: 「Illustrator 拔 image XObject 攻擊邏輯,從 .planning/debug/scratch/illustrator-attack-2026-05-28/ 搬入,改寫為可重用 helper」>

This module imports fitz directly. The AGPL fitz seam (app/**/*.py AST guard,
tests/test_redact.py::test_fitz_import_confined_to_engine_seam) restricts
`import fitz` to app/services/pdf_engine.py inside the production tier. tests/
is OUTSIDE that scope — same exception as conftest.py:12 ("only the test
harness may use fitz directly to BUILD fixtures"). See PATTERNS.md.
"""

from __future__ import annotations

import fitz  # license: test harness exception (mirror conftest.py:12)
import numpy as np
```

**Required exports** (per CONTEXT D-B2):
1. `delete_image_xobjects_intersecting(doc: fitz.Document, page_index: int, rect: tuple) -> int` — wraps scratch lines 40-115 (image XObject discovery + content-stream surgery + multi-stream write-back). Returns count of deleted xrefs.
2. `render_region_white_pct(pdf_path: Path | str, page_index: int, rect: tuple) -> float` — wraps scratch lines 21-30:
   ```python
   def render_region_white_pct(pdf_path, page_index, rect):
       doc = fitz.open(pdf_path)
       try:
           page = doc[page_index]
           pm = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(*rect), alpha=False)
           arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
           return round(100 * np.all(arr >= 250, axis=2).sum() / arr[..., 0].size, 2)
       finally:
           doc.close()
   ```
3. `count_zero_area_fills_in_region(pdf_path: Path | str, page_index: int, rect: tuple) -> int` — opens doc and delegates to production helper:
   ```python
   def count_zero_area_fills_in_region(pdf_path, page_index, rect):
       from app.services import pdf_engine  # production helper; safe — pdf_engine is the fitz seam
       doc = fitz.open(pdf_path)
       try:
           return pdf_engine.count_zero_area_fills_fully_inside(doc[page_index], rect)
       finally:
           doc.close()
   ```

**Differences from analog:**
- Scratch script is a `main()` entrypoint with hardcoded `ORIG`/`TARGET`/`REGION` constants (lines 12-18) and `print()` statements; helper module exports pure functions returning typed values — no I/O side effects beyond opening/closing docs.
- `delete_image_xobjects_intersecting` must accept a `fitz.Document` (already-opened by caller) rather than a path string — the regression test wants to inspect the doc post-attack before saving (per RESEARCH Pattern 3 / Step 3-4 of the 4-step pytest flow).
- Drop the diagnostic `print()` calls (scratch lines 34, 39, 49, 56, 60-61, 74, 94, 101, 106, 115, 120-134) — helpers must be silent for pytest collection cleanliness.
- Add explicit `name.lstrip("/")` handling in the regex pattern (already in scratch line 90) — keep verbatim, do not "tidy" it away.
- Type hints required per repo convention (look at any `app/services/*.py` for signature style — `from __future__ import annotations` + PEP 604 unions).

---

### `tests/test_illustrator_attack_regression.py` (pytest regression test, parametrized + xfail strict)

**Analog A (end-to-end test shape):** `tests/test_redact.py::test_remove_region_vector_dense_real_zero_area_paths_end_to_end` (line 691-794)
**Analog B (fitz-in-test-file precedent):** `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` (line 1190-1207) — proves `app/**/*.py` is the scope, not `tests/**/*.py`

**Test-file docstring pattern** — from `test_redact.py:692-708`:
```python
def test_illustrator_attack_residual_supplier_revealed(...):
    """RED-LIGHT regression test for v1.1 Illustrator-class editor threat model.

    Steps:
      1. Ingest sanitized fixture PDF via app.services.ingest
      2. process_job with the manifest's region_rect, logo_id=None (pure removal)
      3. Apply attack: delete image XObject(s) intersecting region
      4. Assert region rendered ≥98% white AND zero-area type='f' count == 0

    EXPECTED-FAIL (Phase 6) — Option B pending in Phase 7 SEC-01. When Phase 7
    lands the content-stream surgery, this test will start passing → XPASS(strict)
    → pytest exits non-zero → implementer MUST remove the @pytest.mark.xfail
    decorator. That removal is the Phase 6 → Phase 7 handoff signal.

    INVARIANT: never invoke pytest with --runxfail (Pitfall 4 in 06-RESEARCH.md).
    """
```

**Fixture-discovery + parametrize pattern** — from RESEARCH § Pattern 3:
```python
import json
import pathlib
import pytest

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "cad-glyph"

def _load_fixtures():
    """Discover all (pdf, manifest) pairs in tests/fixtures/cad-glyph/.

    sorted() is REQUIRED — Path.glob order is filesystem-dependent (Pitfall 6).
    """
    pairs = []
    for pdf in sorted(FIXTURES_DIR.glob("*.pdf")):
        manifest = pdf.with_suffix(".json")
        if not manifest.exists():
            pytest.fail(f"fixture {pdf.name} missing sidecar manifest {manifest.name}")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        pairs.append(pytest.param(pdf, data, id=pdf.stem))
    return pairs

@pytest.mark.parametrize("fixture_pdf,manifest", _load_fixtures())
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Option B 尚未實作(Phase 7 SEC-01 待落地)— Illustrator-class editor "
        "拔 image XObject 後 page content stream 內的零面積 type='f' 路徑仍會 "
        "render 出供應商商標。Phase 7 落地後請拔掉本 marker。"
        "參 .planning/REQUIREMENTS.md SEC-01。"
    ),
)
def test_illustrator_attack_residual_supplier_revealed(fixture_pdf, manifest, ...):
    ...
```

**End-to-end body pattern** — adapt from `test_redact.py:711-794`. Key step adapter table:

| `test_redact.py:691-794` step | Phase 6 test step |
|---|---|
| `doc = fitz.open()` + synthetic page build (lines 711-728) | Read sanitized fixture PDF bytes from `fixture_pdf.read_bytes()` + `ingest.ingest_upload(fixture_pdf.name, bytes)` |
| `redact.remove_region_vector(page, user_rect)` (line 745) | `pipeline.process_job(session.session_id, JobSpec(dpi=..., regions=[Region(page=manifest["page_index"], px_rect=...)]))` — note `process_job` takes a `JobSpec` not raw dict (verified `app/services/pipeline.py:90`) |
| `assert page.get_images(full=True) == 1` POST-condition (line 749) | NEW Phase 6 step: call `delete_image_xobjects_intersecting(doc, page_index, rect)` between process and assert |
| 5-pixel-sample white check (lines 776-792) | Use `render_region_white_pct(attacked_pdf, page_index, rect) >= 98.0` from helper (D-B5 雙閘 (a)) |
| (none in analog) | NEW Phase 6 雙閘 (b): `count_zero_area_fills_in_region(attacked_pdf, page_index, rect) == 0` |

**Differences from analog:**
- Analog builds synthetic PDF in-memory; Phase 6 test reads committed binary fixture from `tests/fixtures/cad-glyph/*.pdf`. This is the **only test in the suite that reads a committed binary** — README.md must document this exception (D-A6).
- Analog uses synthetic `user_rect = fitz.Rect(50, 100, 350, 200)` hardcoded; Phase 6 test reads `region_rect` from sidecar JSON manifest (D-B4) — single source of truth, no drift if sanitize script re-tunes region.
- Analog runs `redact.remove_region_vector` directly; Phase 6 test runs full `pipeline.process_job` (per CONTEXT canonical refs `app/services/pipeline.py:107-150`) — exercises ingest + storage paths too.
- **NEW STEP inserted between process and assert:** `delete_image_xobjects_intersecting` — this is the Illustrator-attack simulation step that does not exist in any other test.
- **`@pytest.mark.xfail(strict=True)` is first-of-kind in the repo** (RESEARCH § Anti-Patterns / Common Pitfalls confirms). The reason string MUST be 繁中 + include `.planning/REQUIREMENTS.md SEC-01` cross-reference so Phase 7 implementer can `grep` for it.
- Test count delta: analog adds passing tests; Phase 6 adds 3 `XFAIL` (3 fixtures × 1 test = 3 cases, not counted as passed). Baseline becomes "301 passed + 3 skipped + 3 xfailed" (D-B6).
- Use `isolated_data_dir` and `logo_library` autouse/explicit fixtures from `tests/conftest.py:298-354` — no new conftest changes required (CONTEXT D-C-style note: "沿用 conftest 既有 fixture, planner 決定要不要單獨檔放新 conftest").

---

### `tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.pdf` (committed binary fixtures, static asset)

**Analog:** NONE — repo has zero committed binary PDF fixtures (verified: `tests/fixtures/` does not exist before Phase 6; conftest builds all PDFs in-memory via `_build_pdf` / `_build_*_pdf`).

**Pattern (from CONTEXT D-A5 + RESEARCH § Pre-mortem Schema):**
- File names locked: `text-glyph-01.pdf` (text wordmark主體), `figure-glyph-01.pdf` (icon/monogram), `mixed-glyph-01.pdf` (combined).
- Each must be produced by running `scripts/sanitize_fixture.py` on a real supplier PDF (raw PDF stays out of git per D-A4).
- Each must self-validate via the sanitize script's `--out` enforcement (target path MUST be `tests/fixtures/cad-glyph/` — script rejects writes elsewhere per RESEARCH § Known Threat Patterns "Raw supplier PDF accidentally committed").

**Contingency** (per RESEARCH Open Question 1): if engineer can't deliver ≥2 additional supplier PDFs in time, use synthetic CAD-glyph fixture via `Shape.draw_rect(W=0)` pattern (`test_redact.py:722-728`) — track in STATE.md as "Phase 6 fixture 構成:N real + M synthetic". Sanitize script gains an optional `--synthesize` mode in that case.

**Differences from analog:** This is the **first committed-binary exception** in the repo. The exception is scoped strictly to `tests/fixtures/cad-glyph/` and must be documented in the sibling `README.md`.

---

### `tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.json` (sidecar JSON manifest, static metadata)

**Analog:** `logos/manifest.json`

**Existing analog format** — from `logos/manifest.json:1-5`:
```json
[
  { "id": "logo-1line", "file": "1.png", "name": "商標(單行)", "tags": ["wide"] },
  { "id": "logo-2line", "file": "2.png", "name": "商標(雙行)", "tags": ["block"] }
]
```

**Phase 6 schema (per CONTEXT D-B4 + Claude's Discretion):**
```json
{
  "region_rect": [602.0, 481.0, 827.0, 511.0],
  "page_index": 0,
  "expected_zero_area_count_pre_process": 1742,
  "original_supplier_name_hash": "<sha256-of-original-name-for-audit>",
  "sanitization_script_commit_sha": "<short-sha>",
  "created_at_iso": "2026-05-28T..."
}
```

**Differences from analog:**
- `logos/manifest.json` is a flat array (multiple records); cad-glyph manifest is one object per fixture (one-to-one with sibling `.pdf` file).
- `logos/manifest.json` is read at runtime by `app.services.logo` (production); cad-glyph manifests are read only by `tests/test_illustrator_attack_regression.py::_load_fixtures` (test-time only).
- Field semantics differ — `region_rect` is in **PDF points** (output of sanitization script's `--region-rect` arg), `page_index` is 0-based, `expected_zero_area_count_pre_process` is the sanity-check baseline the sanitize script wrote (allows future drift detection).
- Per-fixture isolation: each `.pdf` has its own `.json` (no shared list) so future fixture additions don't risk merge conflicts.

---

### `tests/fixtures/cad-glyph/README.md` (docs, static)

**Analog:** NONE — `samples/` directory has no README; this is greenfield documentation for the committed-binary exception.

**Required content (per CONTEXT D-A6):**
1. **WHY this directory is the only `tests/fixtures/` committed-binary exception** — cross-reference `tests/conftest.py:1-6` philosophy ("never commit binary fixtures") and explain that Illustrator-attack regression requires real supplier CAD content stream operator sequences that synthetic builders cannot faithfully reproduce.
2. **One row per fixture** — original supplier (initial only, OK to redact), sanitization date, sanitization script commit SHA, mapping to which slot (text/figure/mixed).
3. **Immutability rule** — any fixture mutation MUST go through `scripts/sanitize_fixture.py` re-run (never hex-edit, never `git rebase` to change bytes); cross-reference RESEARCH § Anti-Patterns "手動編輯 sanitized fixture PDF".
4. **AGPL §13 statement** — "all fixtures sanitized via scripts/sanitize_fixture.py, no original supplier IP retained" (per CONTEXT § specifics).
5. 繁中文案 per memory `feedback_language`.

---

### `.planning/phases/06-.../06-SECURITY.md` (threat model doc, pre-mortem variant)

**Analog:** `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md`

**Frontmatter pattern** — from analog lines 1-21 (adapt fields per RESEARCH § Pre-mortem Schema):
```yaml
---
phase: 6
phase_name: regression-foundation-threat-model-re-evaluation
milestone: v1.1
audit_scope: phase_06_pre_mortem        # CHANGED: not "hotfix_..." — explicitly pre-mortem
date: 2026-05-28
asvs_level: 1
diff_base: N/A                          # CHANGED: phase has no production-code commits
commits_audited: []                     # CHANGED: empty list
threats_total: 2                        # T-02-07 RE-OPENED + T-06-01
threats_closed: 0                       # by design — closes in Phase 7
threats_open: 0                         # MUST be 0 to not block gsd-secure-phase (A3 in RESEARCH)
threats_accepted: 2                     # both threats listed as `accept (P0, transition-pending until Phase 7)`
register_authored_at_audit_time: true
supersedes:
  - .planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md  # T-02-07 disposition only
---
```

**STRIDE table pattern** — from analog lines 48-54 (one row per threat, exact column schema):
```markdown
| Threat ID | Category | Disposition | Status | Evidence (file:line) |
|-----------|----------|-------------|--------|----------------------|
| T-02-07 | I — TRUE REMOVAL vs cover | mitigate(已 archive)+ **RE-OPENED 2026-05-28** pending Option B (Phase 7) — **accept (P0, transition-pending)** | **RE-OPENED** | `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png` + `tests/test_illustrator_attack_regression.py` xfail; closing condition: Phase 7 `07-SECURITY.md` 重新 CLOSED |
| T-06-01 | S + I — Illustrator pulls image XObject overlay → supplier brand re-rendered from zero-area type='f' source | mitigate (pending Option B Phase 7) — **accept (P0, transition-pending)** | OPEN | 同上 evidence;closing condition 同上 |
```

**Accepted Risks Log pattern** — from analog lines 72-90 (replicate sectioning, swap content):
```markdown
## Accepted Risks Log

### T-06-01-r1 — Illustrator-class editor attack surface
- **Disposition:** accept (P0, transition-pending until Phase 7 closes)
- **Risk description:** <繁中 description>
- **Why accepted now:** Phase 6 is a red-light-baseline phase by design — production-code mitigation lands in Phase 7 Option B (SEC-01). The regression test xfail markers are the binding contract for that handoff.
- **Upgrade trigger / when revisited:** Phase 7 落地 Option B → `07-SECURITY.md` 將此條 CLOSED via Option B(content-stream surgery)
- **Documented at:** `tests/test_illustrator_attack_regression.py` xfail reason, this file, `.planning/REQUIREMENTS.md SEC-01`
```

**Pre-mortem vs audit-time variant table** — copy from RESEARCH § STRIDE Pre-mortem (lines 712-725) verbatim into 06-SECURITY.md prose to explain why this file has `commits_audited: []` and `threats_open: 0` (with both threats listed as `accept`).

**Differences from analog:**
- Analog is **audit-time** (4 commits audited, post-hoc verification of mitigations); Phase 6 is **pre-mortem** (no commits to audit, threats are intentionally OPEN and accepted as transition-pending).
- Analog has `live_uat_verified_at: 2026-05-27` field; Phase 6 omits it (no LIVE deployment to verify).
- Analog `threats_open: 0` because all 5 are CLOSED (4 mitigate + 1 accept); Phase 6 `threats_open: 0` because both threats are listed under `threats_accepted: 2` (the `accept (P0, transition-pending)` framing is the key — A3 in RESEARCH explains this satisfies `gsd-secure-phase` agent's non-block contract).
- Analog `supersedes` is empty; Phase 6 `supersedes` points at the archived `06-HOTFIX-SECURITY.md` (T-02-07 disposition only — not the whole audit).
- Analog has a "Threshold Boundary Verification" section about the 50–99 zero-area range; Phase 6 has no equivalent — replace with a "Pre-mortem vs audit-time variant" section (per pattern above).
- Analog's "Open Threats: None." line becomes Phase 6's "Open Threats: 0 (T-02-07 and T-06-01 both classified as `accept (P0, transition-pending)` — see Accepted Risks Log)."
- 繁中 prose throughout (memory `feedback_language`); English for identifiers / file paths / quoted code (mirrors analog's bilingual convention).

---

### Rename + cleanup: `.planning/debug/scratch/illustrator-attack-2026-05-28/` → `…-archived/`

**Analog:** None — no rename precedent in repo. Pattern is straightforward file-ops:
1. Rename directory (preserve git history via `git mv`).
2. Delete `_attack_delete_image_xobject.py` and `_check_supplier_removal.py` (logic migrated to `tests/_illustrator_attack.py`).
3. Keep 4 PNG/PDF forensic artefacts: `_attack_proof_supplier_revealed.png`, `_attack_target_pre.png`, `_attack_orig_for_comparison.png`, `_attack_image_xobject_deleted.pdf` (per CONTEXT D-C1).
4. Add new `README.md` in the archived dir — 繁中 note pointing forward:
   ```markdown
   # Illustrator attack — 2026-05-28 forensic evidence (archived)

   攻擊腳本邏輯已搬入 `tests/_illustrator_attack.py` +
   `tests/test_illustrator_attack_regression.py`(v1.1 Phase 6 hardening)。
   此目錄保留 PNG/PDF 證據以利後續審計 cite,例如
   `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`
   對 T-06-01 / T-02-07 RE-OPENED 的 evidence cite。

   .py 腳本已退役 — git history 仍可查回 commit b9aa005 之前的版本。
   ```

**Open follow-up** (per RESEARCH Open Question 3): planner decides whether to also move `samples/3013A-13A-C6-XX-3D02-A01-00040.pdf` and the repo-root duplicate into the archived dir + add `.gitignore` entry — they contain the original supplier name and are unsafe to retain in public repo.

---

## Shared Patterns

### Pattern S1: fitz import outside the AGPL seam — license-to-import note
**Source:** `tests/conftest.py:1-12`
**Apply to:** `tests/_illustrator_attack.py` (mandatory header note), `scripts/sanitize_fixture.py` (optional but recommended inline note)
**Verbatim license precedent** (conftest.py:12):
```python
import fitz  # only the test harness may use fitz directly to BUILD fixtures
```
**Why this works:** `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` (line 1190-1207) scopes its AST walk to `glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True)` — `app_dir` is derived from `redact.__file__` which is `app/services/redact.py`. So `tests/` and `scripts/` are **outside the scope by construction**. Phase 6 must NOT modify this guard test (CONTEXT carrying-forward: "Phase 1–4 AST-level guard test 持續綠燈").

### Pattern S2: Pipeline-entrypoint for end-to-end tests
**Source:** `app/services/pipeline.py:90-100` (function signature) + `app/services/ingest.py:331-338` (ingest entrypoint)
**Apply to:** `tests/test_illustrator_attack_regression.py` step 1-2
**Pattern (caller side):**
```python
from app.services import ingest, pipeline
session = ingest.ingest_upload(fixture_pdf.name, fixture_pdf.read_bytes())
# Build JobSpec — see app/models for the pydantic shape (logo_id=None for pure removal)
result = pipeline.process_job(session.session_id, job_spec)
# Output path — see app/services/pipeline.py:85-87 output_path() OR storage.work_path()
```
**Caveat:** `process_job` signature is `(session_id: str, job_spec: JobSpec) -> dict` per `pipeline.py:90` — NOT the `(session_id, regions=[...], logo_id=None)` shape sketched in CONTEXT D-B3 pseudocode. Test must build a proper `JobSpec` (see `app/models.py` for the Pydantic class). RESEARCH § Pattern 3 example also takes liberties here — planner must verify the exact `JobSpec` schema before writing the test.

### Pattern S3: Isolated tmp_path via autouse fixture
**Source:** `tests/conftest.py:298-307`
**Apply to:** `tests/test_illustrust_attack_regression.py` (free — autouse already covers it)
**Pattern (no caller action required — it just works):**
```python
@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data_root)
    yield data_root
```
**Why this matters:** Every Phase 6 test gets a per-test `data/` dir for free — no need to special-case fixture I/O.

### Pattern S4: 繁中 user-facing strings, English identifiers
**Source:** memory `feedback_language` + every existing user-facing string in `app/services/pipeline.py:43-50` / `ingest.py:341-344`
**Apply to:** `scripts/sanitize_fixture.py` CLI messages, `tests/test_illustrator_attack_regression.py` xfail reason + assert messages, `06-SECURITY.md` prose, `cad-glyph/README.md`, `…-archived/README.md`
**Pattern:**
```python
raise PipelineError(
    "work_copy_misconfigured",
    "內部錯誤:工作副本路徑與初始 PDF 副本相同,已中止以保護工作流程。",  # 繁中 user-facing
)
```

### Pattern S5: SECURITY.md frontmatter schema (gsd-secure-phase consumer contract)
**Source:** `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md:1-21`
**Apply to:** `06-SECURITY.md` (see Pattern Assignments section above for the adapted pre-mortem variant)
**Critical fields downstream `gsd-secure-phase` reads:** `phase`, `audit_scope`, `threats_total`, `threats_closed`, `threats_open`, `threats_accepted`, `register_authored_at_audit_time`, `supersedes`. The pre-mortem variant must set `threats_open: 0` and `threats_accepted: 2` (NOT `threats_open: 2`) per RESEARCH § Assumptions A3 — otherwise the secure-phase agent blocks Phase 6 closure.

---

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| `tests/fixtures/cad-glyph/*.pdf` | committed binary fixture | First committed-binary exception in repo; previously all PDFs built in-memory via `conftest._build_pdf` |
| `tests/fixtures/cad-glyph/README.md` | greenfield exception docs | No prior `tests/fixtures/` README; `samples/` has no README either |
| Rename/cleanup of scratch dir | file-ops | No rename precedent in repo |

For these, RESEARCH.md and CONTEXT.md decisions are the authoritative source.

---

## Metadata

**Analog search scope:**
- `scripts/` (1 file found: `smoke_02_03.py`)
- `tests/` (conftest.py, test_redact.py:691-794 + :1190-1207, test_process_api.py:270-316)
- `app/services/` (pipeline.py, ingest.py, pdf_engine.py:699-743 — read-only references for caller-side patterns)
- `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md` (full)
- `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py` (full)
- `logos/manifest.json` (full)

**Files scanned:** 8 source files + 2 docs

**Pattern extraction date:** 2026-05-28

**Confidence:** HIGH — every excerpt cited has a verified file:line reference; the scratch attack script lines 40-115 are the source-of-truth for the attack mechanics (already proven on `3013A-13A-C6-...pdf` 2026-05-28); the `test_redact.py:691-794` end-to-end shape is in the current passing baseline (301 passed).

**Risk callouts for planner:**
1. **`process_job` signature** — RESEARCH § Pattern 3 sketch uses `pipeline.process_job(session_id, regions=[...], logo_id=None)` but actual signature is `process_job(session_id, job_spec: JobSpec) -> dict` per `pipeline.py:90`. Planner must verify `JobSpec` shape against `app/models.py` and adjust the test body accordingly. (Shared Pattern S2 flags this.)
2. **`gsd-secure-phase` non-block contract** — `threats_open: 0` + `threats_accepted: 2` framing is load-bearing; if planner writes `threats_open: 2` instead, the agent will block Phase 6 closure (RESEARCH § Assumptions A3 = MEDIUM risk).
3. **xfail strict + parametrize decorator order** — `@pytest.mark.parametrize` must be **above** `@pytest.mark.xfail` (closer to the function) so xfail applies to each parametrized case; reversing them is a Pitfall 5 trap.
4. **Multi-stream content stream handling** — the scratch script's "write to [0], empty [1:]" pattern (lines 109-114) is empirical (proven on 3013A-...pdf which is single-stream); other supplier PDFs may have legitimately multi-stream pages — sanitize script must preserve this pattern verbatim (Pitfall 3 in RESEARCH).
