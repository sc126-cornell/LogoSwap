# Phase 7: Option B Implementation — Content-Stream Surgery - Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 4 (2 production modify + 1 test new + 1 test modify)
**Analogs found:** 4 / 4 (every file has a concrete codebase analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/pdf_engine.py` (modify — add 2 helpers) | fitz seam helper | transform (read content stream → mutate → write back) | `tests/_illustrator_attack.py::delete_image_xobjects_intersecting` (verbatim multi-stream write-back) + `app/services/pdf_engine.py::cover_zero_area_artefacts` (line 635) + `count_zero_area_fills_fully_inside` (line 699) | exact (S1 verbatim port) + role-match (naming, signature, docstring style) |
| `app/services/redact.py` (modify — insert ≤10 LOC dispatcher block) | dispatcher (non-fitz) | request-response (call helper → log → fall through to existing dispatcher) | `app/services/redact.py:232-256` (existing zero_area_count dispatcher block — STYLE only; do NOT rewrite) + `app/services/integrity.py:26-32` (logging import pattern) | exact (insertion adjacent to analog) |
| `tests/test_pdf_engine.py` (new) — or `tests/test_redact.py::TestOptionB` | unit test suite | request-response (build PDF → run helper → assert) | `tests/test_redact.py::test_remove_region_vector_dense_real_zero_area_paths_end_to_end` (line 691-794) + `tests/conftest.py::_build_pdf` (line 18-32) | exact (Shape.draw_rect(W=0) zero-area injection at lines 722-728 + density gradient builder) |
| `tests/test_illustrator_attack_regression.py` (modify — delete 8 lines) | regression test (xfail decorator removal) | N/A (single-decorator removal) | self (Phase 6 produced; lines 74-82 are the only acceptable mutation point) | exact (this single-line decorator removal IS the entire Phase 6→7 handoff signal) |

---

## Pattern Assignments

### `app/services/pdf_engine.py` — add `delete_zero_area_type_f_fills_inside` + `log_xobject_intersect`

**Analog A (Shared Pattern S1 — multi-stream write-back, VERBATIM):** `tests/_illustrator_attack.py:180-189`
**Analog B (helper naming + signature style):** `app/services/pdf_engine.py::count_zero_area_fills_fully_inside` (line 699-743)
**Analog C (docstring HONEST LIMITATION style):** `app/services/pdf_engine.py::replace_region_with_white_raster` (line 746-792, especially line 776-791)
**Analog D (zero-area + fully-inside + type='f' iteration loop):** `app/services/pdf_engine.py::cover_zero_area_artefacts` (line 635-696)

---

#### Pattern A1 — Module-level imports + logger setup

**Source:** `app/services/integrity.py:23-32` (the project's standard `logging` import idiom; sibling service file in the same package)

```python
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from .. import storage

logger = logging.getLogger(__name__)
```

**Apply to `pdf_engine.py`:** Plan 07-01 must add `import logging` + `import re` to the existing import block (currently line 15-19: `from __future__ import annotations`, `from pathlib import Path`, `import fitz`). Place `logging` alphabetically between `__future__` and `pathlib`, add `re` after `logging`. Add `logger = logging.getLogger(__name__)` after the `import fitz` line (similar position to `integrity.py:32`).

---

#### Pattern A2 — Existing helper signature & contract style (from `count_zero_area_fills_fully_inside` line 699-743)

```python
def count_zero_area_fills_fully_inside(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> int:
    """Count ``type='f'`` drawings with ZERO-area bbox that are fully inside ``rect``.

    Dispatcher input for the dCt-residue fix (hotfix #06): :func:`remove_region_vector`
    calls this after ``apply_redactions`` to decide whether the zero-area residue
    cleanup should use the per-artefact cover strategy (...).

    Contract — counts ONLY drawings that are:

    - ``type='f'`` (filled path; ...).
    - Zero-area (bbox width OR height below :data:`_DEGENERATE_BBOX_EPS`, ...).
    - Fully inside ``rect`` (matches the cover routine's containment filter, ...).
    """
    q = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    q.normalize()
    query = (q.x0, q.y0, q.x1, q.y1)
    count = 0
    for drawing in page.get_drawings():
        d_rect = drawing.get("rect")
        if d_rect is None:
            continue
        if drawing.get("type") != "f":
            continue
        dr = fitz.Rect(d_rect)
        dr.normalize()
        if not (dr.width < _DEGENERATE_BBOX_EPS or dr.height < _DEGENERATE_BBOX_EPS):
            continue
        if not _rect_contains(query, (dr.x0, dr.y0, dr.x1, dr.y1)):
            continue
        count += 1
    return count
```

**Apply to:** Plan 07-01's STEP A (pre-screen via `get_drawings()`) — same 4-gate filter (`type='f'`, zero-area, fully-inside, drop None). Plan 07-01 helper reuses module-level `_DEGENERATE_BBOX_EPS` (line 261) and existing `_rect_contains` (line 508) — IN-01 alignment is mandatory (D-A3 in CONTEXT).

**Key reuse points:**
- `_DEGENERATE_BBOX_EPS = 0.01` (pdf_engine.py:261) — DO NOT redefine, DO NOT shadow with a local default
- `_rect_contains(query, candidate)` (pdf_engine.py:508) — already-existing fully-inside test
- `fitz.Rect(...).normalize()` — required idiom for safety against inverted rects

---

#### Pattern A3 — HONEST LIMITATION docstring section (from `replace_region_with_white_raster` line 776-791)

```python
def replace_region_with_white_raster(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> None:
    """Insert a single solid-white image XObject covering ``rect`` (dCt-residue fix).

    [...]

    LIMITATION (be honest)
    ----------------------

    The zero-area BLACK source paths remain in the content stream. They are not
    deleted — only visually superseded by the image overlay. Recovering the
    original supplier mark requires:

      1. Removing this image XObject (one structural edit in a PDF editor), AND
      2. Expanding the zero-area path bboxes to non-zero width/height
         (per-path geometry surgery).

    This is strictly harder than the failure mode it replaces — the prior
    ``cover_zero_area_artefacts`` leak recovers the mark by simply re-colouring
    the per-artefact covers, no geometry surgery needed. True deletion of
    zero-area sources requires content-stream surgery (a candidate hotfix for a
    future iteration if higher assurance is required).
    """
```

**Apply to `delete_zero_area_type_f_fills_inside`:** Plan 07-01 helper docstring MUST include an equivalent `HONEST LIMITATION` section, but reframed for what Option B *cannot* do (fail-safe surface) — example from 07-RESEARCH.md Example 1 (verbatim):

```
HONEST LIMITATION
-----------------
本 helper 採 regex anchor matching;PDF 內容流的 byte-level 表達細節(operator
間任意 whitespace、CTM nested q/Q stack、PScript5 vs Acrobat 寫法差異)可能讓
某些 zero-area path 的 byte 範圍 regex 漏抓。漏抓時 cardinality assertion 失敗
→ return 0 + logger.warning("option_b_parse_anomaly") → 既有 dispatcher
(Phase 4-6 Option A overlay + cover_zero_area_artefacts) 接 last-mile defense。
詳見 06-PATTERNS Risk Callout #4 + 07-RESEARCH § Common Pitfalls Pitfall 1。
```

繁中 docstring 段 is mandatory (memory `feedback_language` + Pattern S4 in 06-PATTERNS).

---

#### Pattern A4 — Multi-stream content stream write-back (Shared Pattern S1, VERBATIM PORT)

**Source:** `tests/_illustrator_attack.py:180-189` — Phase 6 already verbatim-ported this from `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_delete_image_xobject.py` lines 104-115. **Phase 7 ports it ONCE MORE, same asymmetric structure, into `pdf_engine.py`.**

```python
    # Multi-stream write-back — VERBATIM scratch lines 104-115(不對稱 pattern,
    # 保留兩個 branch 結構而非「整理」為單一 loop,per 06-PATTERNS Risk Callout #4)
    new_bytes = stream_text.encode("latin-1")
    content_xrefs = page.get_contents()
    if len(content_xrefs) == 1:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
    else:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
        for xref in content_xrefs[1:]:
            doc.update_stream(xref, b"", compress=True)
```

**Apply to Plan 07-01 STEP E (after `_splice_out`):** Use `doc = page.parent` to access the Document handle (Pitfall 7 in RESEARCH); the helper signature stays `(page, user_rect, tolerance)` — DO NOT add `doc` as an arg.

**LOAD-BEARING — DO NOT "tidy":**
- The single-stream and multi-stream branches MUST stay as TWO branches. Do not collapse them into one `for xref in content_xrefs` loop.
- The asymmetric "write to [0] + empty [1:]" pattern is empirically verified (Phase 6 attack helper proved on `3013A-13A-C6-…pdf`); refactoring it risks silent multi-stream corruption.
- `compress=True` is mandatory (Pitfall 6 in RESEARCH — uncompressed write-back inflates output PDF size by 30-50%).
- Per Anti-Pattern in RESEARCH § Architecture Patterns line 533: **"Writing back to all multi-stream xrefs as concatenated blobs … the [0] + empty [1:] pattern is the verified-correct write-back."**

---

#### Pattern A5 — `log_xobject_intersect` helper (SEC-03 side-effect-only)

**Source:** 07-RESEARCH.md § Pattern 2 (lines 489-518) + verified `page.get_xobjects()` tuple shape `(xref, name, invoker, bbox)` where `bbox` is `fitz.Rect` in page user-space (no CTM math).

```python
def log_xobject_intersect(page: "fitz.Page", user_rect: "fitz.Rect", logger=None) -> int:
    """Log form-XObject intersects with user_rect; return count. SEC-03 transparency helper.

    page.get_xobjects() returns Form XObjects only (not image XObjects). For each
    xobject, bbox is already in page user-space (no CTM math required).
    Returns the count of intersecting xobjects.

    The page-level Option B does NOT touch Form XObject internal streams; this helper
    transparently surfaces to logs that page-level deletion may not have been
    exhaustive for an XObject-residue scenario. The existing dispatcher's dense/sparse
    branches act as last-mile defence.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    n = 0
    for xref, name, invoker, bbox in page.get_xobjects():
        # bbox is already a fitz.Rect in page user-space (verified)
        if bbox.intersects(user_rect):
            n += 1
    if n > 0:
        logger.warning(
            "option_b_xobject_intersect",
            extra={
                "page_index": page.number,
                "user_rect": [user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1],
                "xobject_count": n,
            },
        )
    return n
```

**Apply to Plan 07-01:** Add as the second new helper in `pdf_engine.py`, adjacent to `delete_zero_area_type_f_fills_inside`. **Accept `logger` as injected arg** (avoid hardcoding `pdf_engine`'s logger — let the caller's `redact.py` logger surface the event in its namespace).

---

#### Pattern A6 — `_DEGENERATE_BBOX_EPS` constant reuse (IN-01 alignment)

**Source:** `app/services/pdf_engine.py:255-261`

```python
# Shared by ``get_drawings_fully_inside`` (the residual-content REMOVAL assertion)
# and ``cover_zero_area_artefacts`` (the cross-renderer hairline-mask) so they
# agree on what counts as zero-area. A drift between the two would split residual
# detection from artefact masking — either (a) Adobe-rendered hairlines survive
# when the residual check ignores a wider epsilon, or (b) ``residual_content``
# false positives when the cover routine ignores a wider one. IN-01.
_DEGENERATE_BBOX_EPS = 0.01
```

**Apply to:** Plan 07-01 helper's `tolerance: float = _DEGENERATE_BBOX_EPS` default arg. **IN-01 mandate:** if a future maintenance sprint changes this constant, all THREE helpers (`get_drawings_fully_inside`, `cover_zero_area_artefacts`, `delete_zero_area_type_f_fills_inside`) flip together. Plan 07-01 MUST NOT introduce a separate epsilon constant; reuse this one.

---

### `app/services/redact.py` — insert Option B call at line 195 boundary

**Analog A (insertion-site style):** `app/services/redact.py:197-256` — existing zero_area_count dispatcher block. Plan 07-02's insertion sits IMMEDIATELY BEFORE this block (line 232) and IMMEDIATELY AFTER the residual_content assertion (line 195). DO NOT modify the existing dispatcher; only insert.
**Analog B (logging idiom):** `app/services/integrity.py:26-32` — `import logging` + `logger = logging.getLogger(__name__)`

---

#### Pattern B1 — Existing dispatcher block (STYLE reference; DO NOT REWRITE)

**Source:** `app/services/redact.py:197-258` (verbatim — the block Plan 07-02 inserts BEFORE).

```python
    # Zero-area artefact cleanup — dispatched on residue DENSITY (hotfix #06,
    # dCt-residue).
    #
    # Background: ``LINE_ART_REMOVE_IF_COVERED`` leaves zero-area filled paths
    # (``type='f'`` with W=0 or H=0) in the content stream because PyMuPDF treats
    # them as non-coverable (...).
    # [...long verbatim comment block...]
    # Done AFTER the residual assertion so neither code path can trip
    # ``get_drawings_fully_inside`` (zero-area fills are already excluded from that
    # assertion via the same _DEGENERATE_BBOX_EPS, IN-01).
    zero_area_count = pdf_engine.count_zero_area_fills_fully_inside(page, user_rect)
    if zero_area_count >= pdf_engine.ZERO_AREA_RASTER_THRESHOLD:
        # Dense-residue path: single white image XObject covers the whole rect.
        pdf_engine.replace_region_with_white_raster(page, user_rect)
        # Post-condition: the safe-landing diagnostic helper from the same hotfix.
        whitepaint = pdf_engine.get_white_fill_drawings_intersecting(page, user_rect)
        if whitepaint:
            raise RedactError(
                "residual_whitepaint",
                "raster fallback 後仍偵測到 white-paint 殘留,raster overlay 未生效。",
            )
    else:
        # Sparse-residue path: per-artefact hairline cover (the Phase 4 #5
        # behaviour). [...]
        pdf_engine.cover_zero_area_artefacts(page, user_rect)

    return True
```

**Apply to Plan 07-02:** Plan 07-02 inserts BEFORE this block. The existing dispatcher is **untouched** — its dense/sparse branch becomes last-mile defense when Option B leaves residual zero-area count > 0 (form-XObject internal residue). DO NOT delete the existing comment header; DO NOT change `if zero_area_count >= pdf_engine.ZERO_AREA_RASTER_THRESHOLD:` — both are load-bearing for the IN-01 invariant.

---

#### Pattern B2 — Insertion block (07-RESEARCH § Code Examples Example 8 + CONTEXT D-C1, VERBATIM)

**Source:** 07-RESEARCH.md lines 1117-1127 + CONTEXT D-C1 (lines 114-124).

```python
# At top of file (after `from . import pdf_engine` line 84), ADD:
import logging
logger = logging.getLogger(__name__)
```

```python
# At line 195 insertion point (immediately after the residual_content RedactError
# raise, immediately before the existing zero_area_count dispatcher block),
# INSERT this block (~6 lines + 4 lines comments):
    # Phase 7 Option B — page-level content-stream surgery (SEC-01).
    # 真正刪除 fully-inside-rect 零面積 type='f' fills,upstream defense before
    # 既有 Phase 5 Hotfix 06 dispatcher(form-XObject 內巢狀殘留時才會走
    # dense/sparse last-mile defense)。
    deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
    if deleted > 0:
        logger.info(
            "option_b_deleted",
            extra={"page_index": page.number, "count": deleted},
        )
    pdf_engine.log_xobject_intersect(page, user_rect, logger=logger)
```

**Apply to Plan 07-02:** ≤ 10 LOC dispatcher block (excluding the `import logging` + `logger = ...` two-line top-of-file addition). Total redact.py diff ≤ 12 LOC.

**Critical AGPL guard contract:** `import logging` is stdlib, NOT `fitz`. `redact.py` after Plan 07-02 must still pass `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` (line 1190-1207). Plan 07-02 implementer MUST NOT add `import fitz` to redact.py — `user_rect` arrives as `fitz.Rect` already (passed from `pipeline.py` via `pdf_engine.map_tuple_to_rect`), and `pdf_engine` helpers consume it.

---

### `tests/test_pdf_engine.py` (NEW) — TEST-03 unit tests

**Analog A (end-to-end build PDF → run → assert structure):** `tests/test_redact.py::test_remove_region_vector_dense_real_zero_area_paths_end_to_end` (line 691-794) — especially the `Shape.draw_rect(W=0)` zero-area injection at lines 722-728.
**Analog B (in-memory PDF builder):** `tests/conftest.py::_build_pdf` (line 18-32) — `_build_pdf` + variants are the project's standard "build bytes in-memory, return bytes, never commit binaries" pattern.
**Analog C (AGPL guard must continue to pass):** `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` (line 1190-1207) — scope is `app/**/*.py`; `tests/test_pdf_engine.py` is OUTSIDE scope by construction (Pattern S1 in 06-PATTERNS + Pitfall 9 in 07-RESEARCH).

---

#### Pattern T1 — In-memory PDF construction with `Shape.draw_rect(W=0)` (zero-area injection)

**Source:** `tests/test_redact.py:711-732` (verbatim — the only existing pattern in the suite for synthesizing zero-area `type='f'` fills).

```python
def test_remove_region_vector_dense_real_zero_area_paths_end_to_end():
    """Hotfix #06 — end-to-end integration (NO monkey-patch).
    [...]
    """
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)

        # User rect we will frame: 50..350 x 100..200 (300pt wide, 100pt tall).
        user_rect = fitz.Rect(50.0, 100.0, 350.0, 200.0)

        # Synthesize >= ZERO_AREA_RASTER_THRESHOLD real zero-area type='f' paths
        # FULLY INSIDE user_rect. Use draw_rect(W=0) — each one is a vertical
        # zero-width filled line at x=55+i*2, y from 110 to 190. Verified to
        # produce {'type':'f','fill':(0,0,0)} with bbox W=0 in get_drawings().
        n = pdf_engine.ZERO_AREA_RASTER_THRESHOLD + 20  # 120, well above threshold
        for i in range(n):
            x = 55.0 + i * 2.0
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(x, 110.0, x, 190.0))  # W=0 → zero-area
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()

        # Also add a text word to remove [...]
        page.insert_text((100, 150), "SUPPLIER", fontsize=10)
        [...]
    finally:
        doc.close()
```

**Apply to Plan 07-01:** Density gradient parametrized test (per 07-RESEARCH.md Example 6 lines 1015-1051):

```python
@pytest.mark.parametrize("n_zaf", [0, 1, 100, 1742])
def test_option_b_density_gradient(n_zaf):
    """TEST-03 density gradient: 0 / 1 / 100 / 1742 zero-area type='f' fills inside rect.

    Sourced from tests/test_redact.py:722-728 Shape.draw_rect(W=0) injection pattern.
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        user_rect = fitz.Rect(50.0, 100.0, 350.0, 200.0)

        for i in range(n_zaf):
            x = 55.0 + (i % 290) * 1.0  # spread across rect width
            y_off = (i // 290) * 1.0
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(x, 110.0 + y_off, x, 190.0 + y_off))  # W=0
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()

        count_before = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_before == n_zaf

        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == n_zaf

        count_after = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_after == 0
    finally:
        doc.close()
```

**Key reuse:** `Shape.draw_rect(fitz.Rect(x, y0, x, y1))` with W=0 (x0 == x1) + `shape.finish(fill=...)` + `shape.commit()` — verified by existing `test_remove_region_vector_dense_real_zero_area_paths_end_to_end` to produce real `get_drawings()` entries with `type='f'` and W=0.

---

#### Pattern T2 — Test file fitz license header (06-PATTERNS Shared Pattern S1)

**Source:** `tests/conftest.py:12` (verbatim license precedent) + `tests/_illustrator_attack.py:60` (Phase 6 mirror).

```python
import fitz  # only the test harness may use fitz directly to BUILD fixtures
```

**Apply to `tests/test_pdf_engine.py`:** Top-of-file fitz import MUST carry this comment. The AGPL guard at `tests/test_redact.py:1190-1207` scopes to `app/**/*.py` (line 1195: `glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True)` where `app_dir` is `os.path.dirname(os.path.dirname(os.path.abspath(redact.__file__)))`). Therefore `tests/` is outside the scope BY CONSTRUCTION — but the license comment is project convention.

---

#### Pattern T3 — `caplog` structured log assertion (07-RESEARCH § Example 5)

**Source:** 07-RESEARCH.md lines 968-1010 (Example 5) + Assumption A5 (`caplog` exposes `extra={}` kwargs as LogRecord attributes).

```python
def test_option_b_form_xobject_intersect_logged(caplog):
    """SEC-03: when user_rect intersects a Form XObject bbox, log_xobject_intersect
    emits warning event with structured extra fields, and page-level surgery does NOT
    descend into XObject internal stream.
    """
    import logging

    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        nested_doc = fitz.open()
        try:
            nested_page = nested_doc.new_page(width=200, height=150)
            shape = nested_page.new_shape()
            shape.draw_rect(fitz.Rect(50, 60, 50, 100))  # zero-area W=0
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()
            # show_pdf_page wraps nested page in a Form XObject on the host page
            page.show_pdf_page(fitz.Rect(50, 100, 250, 250), nested_doc, 0)
        finally:
            nested_doc.close()

        assert len(page.get_xobjects()) >= 1

        with caplog.at_level(logging.WARNING, logger="app.services.pdf_engine"):
            n = pdf_engine.log_xobject_intersect(
                page, fitz.Rect(40, 90, 260, 260), logger=None
            )

        assert n >= 1
        matching = [r for r in caplog.records if "option_b_xobject_intersect" in r.message]
        assert matching
        rec = matching[0]
        assert rec.xobject_count >= 1  # extra={"xobject_count": ...} surfaces as attr
        assert rec.page_index == 0
    finally:
        doc.close()
```

**Apply to Plan 07-01 SEC-03 test:** Use `page.show_pdf_page(host_rect, nested_doc, page_no)` (verified PyMuPDF API) to synthesize a Form XObject wrapping a zero-area path. `caplog.at_level(logging.WARNING, logger="app.services.pdf_engine")` scopes capture to the helper's logger namespace.

---

#### Pattern T4 — Coverage map (14 cases per CONTEXT D-D3 + 07-RESEARCH § Validation Architecture table)

| Category | Test | Builds |
|----------|------|--------|
| **Density gradient (4 cases, parametrized)** | `test_option_b_density_gradient[0,1,100,1742]` | Pattern T1 |
| **SEC-02 no-op (2 cases)** | `test_option_b_no_op_on_normal_vector_pdf` | 07-RESEARCH Example 4 |
| | `test_option_b_reentrant` (call twice; 2nd call returns 0) | 07-RESEARCH Open Q3 |
| **Safe-skip 5 contexts (5 cases)** | `test_safe_skip_bt_et` (text block contains `m l f` chars) | 07-RESEARCH Example 7 |
| | `test_safe_skip_paren_string` (`(Quality m l f)` literal) | 07-RESEARCH Example 7 |
| | `test_safe_skip_hex_string` (`<6d6c66>` hex data) | 07-RESEARCH Example 7 |
| | `test_safe_skip_comment` (`% m l f\n` comment) | 07-RESEARCH Example 7 |
| | `test_safe_skip_inline_image` (BI/ID/EI binary bytes) | 07-RESEARCH Example 7 |
| **SEC-03 form-XObject (3 cases)** | `test_option_b_form_xobject_intersect_logged` | Pattern T3 |
| | `test_option_b_form_xobject_internal_stream_untouched` (page-level only) | Pattern T3 + assert nested xref stream unchanged |
| | `test_option_b_no_xobject_no_log` (no intersect → no log) | inverse of Pattern T3 |

**Total: 14 cases** (4 parametrized density + 2 SEC-02 + 5 safe-skip + 3 SEC-03). Final baseline expectation: `(304 + ~14) passed + 3 skipped` after Plan 07-02 close.

---

### `tests/test_illustrator_attack_regression.py` — DELETE 8 lines (xfail decorator removal)

**Analog:** Self — this is the Phase 6 produced file. The xfail decorator at lines 74-82 is the **only** sanctioned mutation point (Phase 6 → Phase 7 handoff signal).

**Source — BEFORE (current state, lines 73-82 verbatim):**

```python
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
```

**Source — AFTER (Plan 07-02 final state):**

```python
@pytest.mark.parametrize("fixture_pdf,manifest", _load_fixtures())
def test_illustrator_attack_residual_supplier_revealed(
```

**Diff:** delete lines 74-82 inclusive (9 lines if counting the closing `)`; 8 functional lines per 07-RESEARCH Example 9). Keep `@pytest.mark.parametrize` decorator above the function.

**Verification command sequence** (CONTEXT D-D4 + 07-RESEARCH Example 9):
```bash
grep -rn "xfail.*Option B" tests/                          # locate marker (sanity check)
# [edit lines 74-82 — delete xfail decorator only]
python -m pytest -k illustrator_attack -v                  # expect 3 PASSED (was 3 XFAIL)
python -m pytest 2>&1 | tail -3                            # expect (304+N) passed, 3 skipped
```

**DO NOT modify:**
- Lines 1-72 (docstring + parametrize + `_load_fixtures` helper)
- Lines 83+ (test body)
- Comment at lines 66-72 (Decorator order explanation — still load-bearing for the remaining `@pytest.mark.parametrize`)

---

## Shared Patterns

### Pattern S1 — Multi-stream content-stream write-back (VERBATIM PORT from Phase 6)

**Source:** `tests/_illustrator_attack.py:180-189` (Phase 6 already verbatim-ported from `_attack_delete_image_xobject.py` lines 104-115)
**Apply to:** Plan 07-01 `delete_zero_area_type_f_fills_inside` helper STEP E
**Verbatim excerpt:** see Pattern A4 above.

**Why load-bearing (Risk Callout #4):** PDF spec § 7.8.2 allows a page's content to be split across multiple `/Contents` array entries, equivalent to one concatenated stream. The asymmetric "write to [0] + empty [1:]" pattern collapses all content into the first stream while emptying the rest — verified-correct on `3013A-13A-C6-XX-3D02-A01-00040.pdf` (Phase 6 forensic evidence). DO NOT refactor into a single loop; DO NOT distribute slices across all xrefs; DO NOT skip `compress=True` (Pitfall 6).

### Pattern S2 — In-memory test PDF construction (no committed binary)

**Source:** `tests/conftest.py:18-32` `_build_pdf` + `tests/test_redact.py:722-728` `Shape.draw_rect(W=0)` zero-area injection
**Apply to:** All Plan 07-01 TEST-03 unit tests
**Project rule:** zero new committed binary fixtures (the Phase 6 `tests/fixtures/cad-glyph/` exception is NOT extended in Phase 7). Every TEST-03 fixture is synthesized in-memory via `fitz.open() + new_page() + Shape.draw_rect(W=0).finish(fill=).commit()`.

### Pattern S3 — Cardinality fail-safe error handling (D-A5 mandate)

**Source:** CONTEXT D-A5 + 07-RESEARCH § Architecture Patterns STEP D + § Security Domain Known Threat Patterns row "Cardinality drift"
**Apply to:** Plan 07-01 `delete_zero_area_type_f_fills_inside` STEP D

```python
# STEP D: Cardinality assertion (D-A5 fail-safe)
if len(ranges_to_delete) != len(zafs):
    logger.warning(
        "option_b_parse_anomaly",
        extra={
            "page_index": page.number,
            "user_rect": list(user_rect_tuple),
            "expected": len(zafs),
            "matched": len(ranges_to_delete),
        },
    )
    return 0
```

**Why fail-safe (NOT raise):**
1. 5330290 minimum-change discipline — Option B failure must NOT break v1.0 baseline pipeline
2. Existing dispatcher (Option A overlay + cover_zero_area_artefacts) still catches residue as last-mile defense
3. Phase 6 regression test surfaces failure naturally (Option B miss → count > 0 → dispatcher branch → XFAIL not XPASS → implementer sees and debugs)
4. NEVER call `doc.update_stream` if cardinality mismatch — destructive write on bad byte ranges = corrupted PDF (worst outcome). RETURN 0 + WARN + LEAVE STREAM UNTOUCHED.

### Pattern S4 — AGPL fitz seam respect (Pattern S1 in 06-PATTERNS + 07-PITFALLS Pitfall 9)

**Source:** `app/services/pdf_engine.py:19` (the sole `import fitz` line in production code) + `tests/test_redact.py:1190-1207` (AST guard)
**Apply to:**
- Plan 07-01: ALL new fitz operations stay in `pdf_engine.py`. The two new helpers (`delete_zero_area_type_f_fills_inside`, `log_xobject_intersect`) sit inside this file.
- Plan 07-02: `redact.py` adds `import logging` (stdlib) only. DO NOT add `import fitz` to redact.py. `user_rect` is already `fitz.Rect` (created by `pdf_engine.map_tuple_to_rect` upstream); pdf_engine helpers consume it.
- Verification command: `grep -rn "import fitz" app/` after Plan 07-02 close — must show exactly one line: `app/services/pdf_engine.py:19`.

### Pattern S5 — Structured logging with `extra={}` kwarg

**Source:** `app/services/integrity.py:26-32` (logger pattern) + 07-RESEARCH § Architecture Patterns Anti-Pattern "Logging without `extra={...}` structured dict"
**Apply to:** All three Phase 7 log events (`option_b_deleted`, `option_b_parse_anomaly`, `option_b_xobject_intersect`)

```python
logger.warning(
    "option_b_xobject_intersect",                              # event name (machine-parseable)
    extra={                                                    # structured fields
        "page_index": page.number,
        "user_rect": [user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1],
        "xobject_count": n,
    },
)
```

**Apply to ALL Option B log events** — downstream log aggregation (future colleague approval-site integration per CONTEXT canonical refs) needs JSON-parseable events, not free-form strings.

### Pattern S6 — 繁中 docstring + log messages, English identifiers (Pattern S4 in 06-PATTERNS)

**Source:** memory `feedback_language` + every existing user-facing string in `app/services/pipeline.py:43-50` / `ingest.py:341-344` / `redact.py:193-194`
**Apply to:** Plan 07-01 helper `HONEST LIMITATION` docstring section + Plan 07-02 dispatcher block 繁中 inline comments

Identifiers (`delete_zero_area_type_f_fills_inside`, `option_b_deleted`, etc.) stay English. Prose, docstrings, log-event semantic descriptions, error messages stay 繁中.

---

## Risk Callouts (Phase 7 specific)

### Risk Callout #1 — Two operator shapes MUST both be handled

**Source:** 07-RESEARCH § Common Pitfalls Pitfall 3 + live spike on `mixed-glyph-01.pdf` (1742 PScript5 `l`-based + 1654 Acrobat/TESTCO `re`-based)

| Shape | Operator pattern | Source |
|-------|------------------|--------|
| **Shape 1 (PScript5 supplier)** | `q ... cm <args> m <x> <y> l <x2> <y2> [l ...]* f|f*|B|b|B*|b* Q` | real supplier PDFs |
| **Shape 2 (Acrobat / TESTCO sanitize)** | `<x> <y> <w> <h> re <ops>* f|f*|B|b|B*|b*` | sanitize injection + Acrobat output |

Plan 07-01 helper MUST implement BOTH shape locators (`_locate_shape1_byte_range` + `_locate_shape2_byte_range`). Dispatch by inspecting `zaf.get("items", [])` — if all items are `('re', ...)` → Shape 2; if items are `('m', ...)` / `('l', ...)` → Shape 1. **Missing one shape → mixed-glyph regression test still fails XFAIL.**

Phase 7 RESEARCH § Code Examples Example 2 (Shape 1) and Example 3 (Shape 2) provide the concrete implementations.

### Risk Callout #2 — Cardinality fail-safe (D-A5) — NEVER destructive write on mismatch

**Source:** CONTEXT D-A5 + Pattern S3 above
**Critical:** if `len(ranges_to_delete) != len(zafs)`:
- Emit `logger.warning("option_b_parse_anomaly", extra={"expected":…, "matched":…})`
- `return 0` IMMEDIATELY
- DO NOT call `doc.update_stream`
- DO NOT call `_splice_out`
- DO NOT raise `RedactError`

The destructive path (update_stream with mismatched byte ranges) corrupts the PDF; the dispatcher's last-mile defense (Option A overlay) silently covers what Option B missed. Returning 0 is the only safe failure.

### Risk Callout #3 — Multi-stream write-back PATTERN S1 verbatim

**Source:** 06-PATTERNS Risk Callout #4 + Pattern S1 above + Pattern A4

**LOAD-BEARING — Plan 07-01 implementer must resist 4 "tidiness" temptations:**
1. Collapsing the if/else into one loop ❌ — keep TWO branches
2. Distributing slices across xrefs (`for i, xref in enumerate(content_xrefs): update_stream(xref, slice[i])`) ❌ — write all-to-[0], empty rest
3. Skipping `compress=True` (or using `compress=False`) ❌ — inflates output PDF 30-50% (Pitfall 6)
4. Saving the doc inside the helper (`doc.save(...)`) ❌ — caller owns save lifecycle (Pitfall 9 RESEARCH § Architecture Anti-Patterns)

### Risk Callout #4 — Safe-skip 5-context mask via bytearray O(N) pre-pass

**Source:** CONTEXT D-A2 + 07-RESEARCH § Architecture Patterns Pattern 1 STEP B + Pitfall 1
**Pre-pass MUST run BEFORE any operator-locating regex.** Two-pass approach is mandatory:

```python
def _build_safe_skip_mask(stream: bytes) -> bytearray:
    """O(N) one-time bytearray mask. mask[i]=0 means 'inside safe-skip region', 1 means 'searchable'."""
    mask = bytearray(b"\x01" * len(stream))
    for m in _SAFE_SKIP_REGIONS_RE.finditer(stream):
        for i in range(m.start(), m.end()):
            mask[i] = 0
    return mask
```

5 contexts the mask MUST cover (D-A2):
1. `BT ... ET` text blocks (m/l/f chars inside text-show hex strings)
2. `BI ... ID ... EI` inline images (binary bytes may contain m/l/f bytes)
3. `(...)` literal strings with nested `\(` `\)` escape (PostScript-style)
4. `<...>` hex strings (may contain `<6d6c66>` hex of `m`/`l`/`f`)
5. `% ... \n` comments

**Why mask-then-regex (not regex-with-lookaround):** PDF content stream is BYTES; `re` engine doesn't know about PDF syntax. A naive `q\b[^Q]*?Q\b` regex terminates prematurely on `Q` inside a `(Quality)` literal string (the WR-02 caveat in `tests/_illustrator_attack.py:19-37`). The bytearray mask is the only safe way to teach the regex "skip these byte ranges."

### Risk Callout #5 — AGPL seam: ALL new fitz ops in `pdf_engine.py`; `redact.py` change must NOT add `import fitz`

**Source:** Pattern S4 above + `tests/test_redact.py:1190-1207` AST guard

**Verification commands** (Plan 07-01 + Plan 07-02 close gates):
```bash
grep -rn "import fitz" app/
# Expected: app/services/pdf_engine.py:19  (ONLY line)

python -m pytest tests/test_redact.py::test_fitz_import_confined_to_engine_seam -v
# Expected: PASSED
```

Adding `import fitz` to `redact.py` (even at module level for type hints) FAILS the AST guard immediately. Use `"fitz.Page"` / `"fitz.Rect"` as STRING type annotations (PEP 604 forward-ref style); pdf_engine helpers signatures already use this pattern (see line 312 `page: "fitz.Page"`).

### Risk Callout #6 — Production code scope: ONLY `pdf_engine.py` + `redact.py` modified

**Source:** CONTEXT § canonical_refs lines 217-220 + 5330290 minimum-change lesson

**Phase 7 production-code change boundary:**
- `app/services/pdf_engine.py` — add 2 helpers + module-level `import logging`, `import re`, `logger = ...`
- `app/services/redact.py` — add 1 dispatcher block (~10 LOC) + `import logging`, `logger = ...`
- **NO OTHER `app/**/*.py` FILE TOUCHED**

Verification gate (Plan 07-02 close):
```bash
git diff --stat <plan-07-01-base>^..HEAD -- 'app/'
# Expected: exactly two files: app/services/pdf_engine.py | app/services/redact.py
```

Files Phase 7 MUST NOT touch (CONTEXT § code_context "What Phase 7 does NOT touch"):
- `app/services/pipeline.py`, `coords.py`, `ingest.py`, `integrity.py`, `janitor.py`
- `app/api/*.py`, `app/main.py`, `app/config.py`, `app/models.py`
- `web/**`
- `tests/_illustrator_attack.py` (Phase 6 attack helper — DO NOT modify)
- `tests/fixtures/cad-glyph/` (Phase 6 produced ground truth)
- `scripts/sanitize_fixture.py` (Phase 6 produced)

### Risk Callout #7 — `page.parent` for Document access (Pitfall 7)

**Source:** 07-RESEARCH § Pitfall 7

Plan 07-01 helper signature is `(page, user_rect, tolerance)` — NO `doc` arg. Inside the helper:
```python
doc = page.parent  # fitz.Page.parent → fitz.Document
content_xrefs = page.get_contents()
doc.update_stream(content_xrefs[0], new_bytes, compress=True)
```

**DO NOT change the helper signature to `(doc, page, user_rect, tolerance)`** — Plan 07-02 dispatcher call site already uses the 3-arg form. Adding `doc` breaks the call site and triggers a needless cross-plan coordination.

### Risk Callout #8 — Re-entrancy (Open Question 3)

**Source:** 07-RESEARCH § Open Questions Q3

The helper MUST be safe to call twice in a row on the same page. After first call deletes N ZAFs:
- Second call: `get_drawings()` returns 0 ZAFs (all removed) → STEP A pre-screen short-circuits → return 0
- `page.read_contents()` bytes unchanged on second call

Plan 07-01 SHOULD include `test_option_b_reentrant` (one of the 14 cases per Pattern T4 coverage map).

---

## No Analog Found

**None.** All 4 Phase 7 files have concrete codebase analogs. Greenfield aspects (Option B regex strategy, safe-skip 5-context mask, hybrid get_drawings + anchor approach) are NOT covered by direct analogs — but the **mechanical patterns** (multi-stream write-back, helper signature style, docstring style, test fixture builder, logging idiom) ALL have analogs in the existing codebase per the table above.

For the greenfield aspects, 07-RESEARCH.md is the authoritative source (Pattern 1 hybrid strategy + Pattern 2 SEC-03 helper + Code Examples 1-9).

---

## Metadata

**Analog search scope:**
- `app/services/pdf_engine.py` (1378 lines — read targeted: 1-80, 255-340, 630-800 covering imports, constants, dispatcher dependencies, IN-01 epsilon, existing helpers, replace_region_with_white_raster docstring)
- `app/services/redact.py` (~258 lines — read lines 1-100 + 175-275 covering module docstring, residual_content assertion at line 195, existing dispatcher block at lines 197-258)
- `app/services/integrity.py` (lines 20-35 only — logging idiom precedent)
- `app/services/janitor.py` (line 23-28 — second logging idiom datapoint)
- `tests/conftest.py` (lines 1-80 — `_build_pdf` + fitz license header precedent)
- `tests/_illustrator_attack.py` (FULL — Phase 6 multi-stream write-back verbatim source)
- `tests/test_illustrator_attack_regression.py` (FULL — xfail decorator removal target)
- `tests/test_redact.py` (lines 685-800 + 1180-1215 — Shape.draw_rect(W=0) injection + AGPL guard)
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-PATTERNS.md` (FULL — Pattern S1 + Risk Callouts to mirror)
- `.planning/phases/07-option-b-implementation-content-stream-surgery/07-CONTEXT.md` (FULL — file inventory + D-A1..D-D4 decisions)
- `.planning/phases/07-option-b-implementation-content-stream-surgery/07-RESEARCH.md` (FULL — Pattern 1-3 + Code Examples 1-9 + 9 Pitfalls)

**Files scanned:** 11 production / test / planning files

**Pattern extraction date:** 2026-05-28

**Confidence:** HIGH — every excerpt has a verified file:line citation. Phase 6 PATTERNS S1 multi-stream write-back is empirically verified (`mixed-glyph-01.pdf` end-to-end attack proof, Phase 6 forensic evidence). All four Plan 07-01 / 07-02 target files have direct in-repo analogs. The only `[ASSUMED]` claims are deferred to A1-A6 in 07-RESEARCH's Assumptions Log (all flagged for spike-time verification by Plan 07-01 implementer).

---

*Phase 7 pattern map complete — planner can now produce Plan 07-01 (helper + TEST-03) and Plan 07-02 (dispatcher + xfail flip) with concrete code excerpts to copy into `<read_first>` and `<action>` blocks.*
