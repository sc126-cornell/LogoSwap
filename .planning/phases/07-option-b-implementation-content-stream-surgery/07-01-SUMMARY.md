---
phase: 07-option-b-implementation-content-stream-surgery
plan: 01
subsystem: pdf
tags: [pymupdf, content-stream, regex, redaction, security, zero-area-fill, agpl-seam]

# Dependency graph
requires:
  - phase: 06-regression-foundation-threat-model-re-evaluation
    provides: "xfail-strict regression baseline (301+3+3) + PATTERNS S1 multi-stream write-back verbatim source + tests/_illustrator_attack.py + 3 real-supplier fixtures"
provides:
  - "pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect, tolerance) -> int — page-level content-stream surgery helper (STEP A-E pipeline, D-A5 fail-safe)"
  - "pdf_engine.log_xobject_intersect(page, user_rect, logger) -> int — SEC-03 form-XObject transparency log helper"
  - "module-level compiled regex: _SAFE_SKIP_REGIONS_RE / _RE_FILL_RECT_RE / _Q_BLOCK_RE"
  - "internal helpers: _build_safe_skip_mask / _is_unmasked / _splice_out / _locate_shape1_byte_range / _build_shape2_candidate_index / _locate_shape2_byte_range"
  - "tests/test_pdf_engine.py — 14 TEST-03 unit tests"
  - "structured log events: option_b_parse_anomaly / option_b_xobject_intersect"
affects: [07-02-dispatcher-integration, 08-phase8-live-uat, 07-SECURITY]

# Tech tracking
tech-stack:
  added: []  # no new runtime/dev deps — stdlib logging + re only
  patterns:
    - "Hybrid get_drawings() + anchor-regex content-stream surgery (authoritative ZAF detection via fitz + byte-range location via regex over safe-skip mask)"
    - "5-context O(N) bytearray safe-skip mask pre-pass before any operator regex (D-A2)"
    - "Cardinality fail-safe (D-A5): mismatch → logger.warning + return 0, NEVER destructive write-back"
    - "PATTERNS S1 multi-stream write-back: asymmetric write-all-to-[0] + empty-rest, compress=True"
    - "page.transformation_matrix bridges PDF bottom-left content-stream coords to MuPDF top-left get_drawings() coords"

key-files:
  created:
    - "tests/test_pdf_engine.py"
  modified:
    - "app/services/pdf_engine.py"

key-decisions:
  - "Shape 2 (re/f) coordinate alignment requires page.transformation_matrix — fitz get_drawings() reports MuPDF top-left, stream re operands are PDF bottom-left"
  - "_RE_FILL_RECT_RE `between` group widened to absorb safe non-path operators (h closepath + colour ops) because PyMuPDF Shape.draw_rect emits `re h <rgb> rg f`, not adjacent `re f`"
  - "page.get_xobjects() returns bbox as plain 4-tuple on PyMuPDF 1.27.2.3 (not fitz.Rect) — must wrap in fitz.Rect(bbox) before .intersects()"

patterns-established:
  - "Two-shape ZAF dispatch via zaf['items']: all 're' → Shape 2 dict lookup; all m/l → Shape 1 q...Q regex"
  - "繁中 HONEST LIMITATION docstring section on both public helpers (memory feedback_language)"

requirements-completed: [SEC-02, SEC-03, TEST-03]

# Metrics
duration: ~40min
completed: 2026-05-28
---

# Phase 7 Plan 01: Option B Content-Stream Surgery Helpers Summary

**Hybrid get_drawings()+anchor-regex helper that truly deletes page-level zero-area type='f' fills (both PScript5 m/l and Acrobat re shapes) with a 5-context safe-skip mask, cardinality fail-safe, and PATTERNS S1 multi-stream write-back, plus a SEC-03 form-XObject intersect logger — all behind the AGPL seam, covered by 14 TEST-03 unit tests.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 2 (both `tdd="true"`)
- **Files modified:** 1 production (`app/services/pdf_engine.py`) + 1 new test (`tests/test_pdf_engine.py`)
- **Commits:** 2 task commits + 1 metadata commit

## Accomplishments

- **`delete_zero_area_type_f_fills_inside`** (`app/services/pdf_engine.py:1186`) — full STEP A-E pipeline:
  - STEP A: `get_drawings()` 4-gate pre-screen (type='f' + zero-area + fully-inside + non-None) → SEC-02 fast no-op
  - STEP B: `page.read_contents()` + `_build_safe_skip_mask` (5 contexts, O(N) bytearray)
  - STEP C: two-shape anchor byte-range discovery (Shape 1 q...Q regex + Shape 2 dict index) with page-transform coordinate bridging
  - STEP D: cardinality assertion → `logger.warning("option_b_parse_anomaly")` + return 0 (D-A5 fail-safe, never raises, never destructive)
  - STEP E: `_splice_out` + PATTERNS S1 verbatim multi-stream write-back (asymmetric `[0]` write + empty `[1:]`, `compress=True`)
  - 繁中 HONEST LIMITATION docstring section
- **`log_xobject_intersect`** (`app/services/pdf_engine.py:1321`) — SEC-03 transparency: walks `page.get_xobjects()`, emits structured `option_b_xobject_intersect` warning when ≥1 form-XObject bbox intersects user_rect; logger injection; page-level only (no XObject descent); 繁中 HONEST LIMITATION docstring
- **`tests/test_pdf_engine.py`** — 14 TEST-03 cases all green (4 density gradient + 2 SEC-02 + 5 safe-skip + 3 SEC-03)

## Task Commits

1. **Task 1: Add helpers to pdf_engine.py** — `3d982e8` (feat)
2. **Task 2: Author 14 TEST-03 cases + coordinate-seam auto-fixes** — `59856cb` (test)

**Plan metadata:** (this commit) (docs)

_Note: Task 1 + Task 2 are a TDD unit; the coordinate-seam bug fixes surfaced by Task 2's tests were committed with the test file (Rule 1 auto-fixes scoped to the same helper code)._

## Files Created/Modified

- `app/services/pdf_engine.py` — +2 public helpers + 6 internal helpers + 3 module-level compiled regex + `_SAFE_BETWEEN_TOKEN` + `import logging`/`import re` + `logger = logging.getLogger(__name__)`
- `tests/test_pdf_engine.py` (new) — 14 TEST-03 unit tests, fitz license header, in-memory fixtures only

## Decisions Made

- **Hybrid strategy as planned** — `get_drawings()` is the authoritative zero-area detector (CTM-resolved user-space rects); regex only locates byte ranges. Cardinality assertion bridges the two.
- **Coordinate-space bridging via `page.transformation_matrix`** (not in original plan code examples) — see Deviations.
- **Shape dispatch by `zaf['items']`** — all `('re', ...)` → Shape 2 dict lookup; all `('m'|'l', ...)` → Shape 1 q...Q regex; mixed → None → cardinality fail-safe.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Shape 1/2 byte-range bboxes need page.transformation_matrix**
- **Found during:** Task 2 (density gradient `[1742]` spike → `option_b_parse_anomaly`)
- **Issue:** The plan's code examples (07-RESEARCH Example 3) built the Shape 2 dict key directly from raw `re` operands (PDF bottom-left coords), but `get_drawings()` reports `zaf['rect']` in MuPDF top-left user-space (Y-flipped via `Matrix(1,0,0,-1,0,page_height)`). Keys never matched for any ZAF whose `y_off > 0`, so 1452/1742 ZAFs failed lookup → cardinality mismatch → fail-safe → deleted=0. The single-row density `[1]`/`[100]` cases passed only because their Y range happened to map onto itself.
- **Fix:** Apply `page.transformation_matrix` to both Shape 1 (`local_rect * ctm * page_transform`) and Shape 2 (`pdf_rect * page_transform`) candidate bboxes before comparing to/keying on `zaf['rect']`. Added `page_transform` param to `_locate_shape1_byte_range` + `_build_shape2_candidate_index`.
- **Files modified:** `app/services/pdf_engine.py`
- **Verification:** Density gradient 0/1/100/1742 all pass; 1742 completes in ~0.08s.
- **Committed in:** `59856cb`

**2. [Rule 1 - Bug] `_RE_FILL_RECT_RE` between-group too narrow for PyMuPDF-synthesised `re`**
- **Found during:** Task 2 (initial synthetic-fixture spike → `_RE_FILL_RECT_RE` match None)
- **Issue:** The final 07-RESEARCH regex used `(?P<between>\s+)` (whitespace only) between `re` and the fill operator. Real supplier PScript5 emits adjacent `re f`, but PyMuPDF's own `Shape.draw_rect(W=0)` — the exact TEST-03 fixture builder — emits `re\nh\n0 0 0 rg f` (closepath + set-fill-colour). The whitespace-only `between` never matched the fixture, so the helper deleted nothing on synthetic test data.
- **Fix:** Introduced `_SAFE_BETWEEN_TOKEN` allowing zero-or-more safe non-path tokens (numeric/name operands + `h W W* g G rg RG k K cs CS sc SC scn SCN`) bounded `{0,16}`. Path-construction operators (`m l c v y re`) are EXCLUDED to prevent skipping across into another path's fill (anti-mis-attribution).
- **Files modified:** `app/services/pdf_engine.py`
- **Verification:** Synthetic fixtures match `100 110 0 80 re\nh\n0 0 0 rg f`; real-supplier adjacent `re f` still matches.
- **Committed in:** `59856cb`

**3. [Rule 1 - Bug] `page.get_xobjects()` bbox is a tuple, not fitz.Rect (PyMuPDF 1.27.2.3)**
- **Found during:** Task 2 (`test_option_b_form_xobject_intersect_logged` → n=0)
- **Issue:** 07-RESEARCH/PATTERNS (Assumption, "verified via WebFetch") stated the 4th tuple element is a `fitz.Rect`. On the actual 1.27.2.3 dev install, `page.get_xobjects()` returns `(xref, name, invoker, bbox)` where `bbox` is a plain `(x0,y0,x1,y1)` **tuple**. My helper called `bbox.intersects(...)`, which raised `AttributeError`, silently swallowed by a defensive `except` → n=0 → no log emitted.
- **Fix:** Wrap `bbox` in `fitz.Rect(bbox)` (+`.normalize()`) before `.intersects()`; tightened the except to `(ValueError, TypeError)` for coercion failures only.
- **Files modified:** `app/services/pdf_engine.py`
- **Verification:** `test_option_b_form_xobject_intersect_logged` + `test_option_b_no_xobject_no_log` both pass.
- **Committed in:** `59856cb`

---

**Total deviations:** 3 auto-fixed (3 bugs, all Rule 1). **Impact:** All three were necessary for the helper to function correctly on real fitz data and for the 14 TEST-03 cases to pass. No scope creep — all fixes stayed inside the two planned helpers + their regex/coordinate handling. The deviations stem from the plan's research examples being validated against a real *supplier* PDF (`re f` adjacent, inside `cm` blocks already in device space) rather than PyMuPDF's own `Shape.draw_rect` fixture builder used by TEST-03.

## Issues Encountered

- **Real-fixture full-page spike on `mixed-glyph-01.pdf` (3396 ZAFs) is slow at full-page scope** (a background spike did not complete quickly). The synthetic 1742-ZAF case completes in ~0.08s, but the real fixture at full-page rect appears slower — likely the per-ZAF Shape 1 q...Q regex over a 1.3MB stream combined with `count_zero_area_fills_fully_inside` re-scans. This is a **07-02 integration concern** (the dispatcher passes framed sub-rects, not full-page), not a 07-01 blocker. Recorded as an Open Question observation for 07-02 / Phase 8 (cross-ref 07-RESEARCH Assumption A6 + Open Q on performance). The fail-safe correctly returns 0 (no corruption) when cardinality drifts on the real fixture at full-page scope.

## Open Question Observations (spike findings for 07-02 / Phase 8 cross-reference)

- **Q3 (re-entrancy) — RESOLVED:** `test_option_b_reentrant` confirms 2nd call returns 0 + bytes unchanged. STEP A pre-screen short-circuit is the mechanism.
- **Q4 (`page.parent`) — VERIFIED:** `page.parent` returns the `fitz.Document` on 1.27.2.3; no signature change needed.
- **A5 (caplog `extra` as LogRecord attrs) — VERIFIED:** `rec.xobject_count` / `rec.page_index` surface directly as attributes; no `rec.extra[...]` needed.
- **A (get_xobjects bbox type) — CORRECTED:** bbox is a tuple, not fitz.Rect (see Deviation 3). 07-02 dispatcher does not need to care (it calls the helper, which handles coercion internally).
- **NEW for 07-02:** Shape 2 coordinate alignment depends on `page.transformation_matrix`. Real supplier PDFs whose `re` lives inside a `cm` device-space block may need the `cm` applied (Shape 1 path) rather than the top-level `re` path — 07-02 should verify the 3 real fixtures XPASS when the dispatcher feeds framed rects, and rely on D-A5 fail-safe + Option A overlay last-mile defense where Option B misses.

## Next Phase Readiness (Plan 07-02 handoff signals)

Helper contract for the redact.py dispatcher integration (Plan 07-02 inserts at line 195 boundary):

- **Signature:** `pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)` → `int` (count deleted; 0 on no-op or fail-safe). Do NOT pass `doc` (uses `page.parent`).
- **Signature:** `pdf_engine.log_xobject_intersect(page, user_rect, logger=logger)` → `int` (count intersecting; logger injection accepted).
- **Log events:** `option_b_deleted` (emit in redact.py when deleted>0), `option_b_parse_anomaly` (emitted internally on fail-safe), `option_b_xobject_intersect` (emitted internally when n>0).
- **Phase 6 regression still 3 XFAIL** — 07-02 wires the helper into `remove_region_vector` then removes the `@pytest.mark.xfail(strict=True)` decorator at `tests/test_illustrator_attack_regression.py:74-82` to flip to 3 PASSED.
- **Baseline after 07-01:** `315 passed + 3 skipped + 3 xfailed`. After 07-02 xfail flip: `318 passed + 3 skipped`.

## Self-Check: PASSED

- FOUND: `tests/test_pdf_engine.py`
- FOUND: `.planning/phases/07-option-b-implementation-content-stream-surgery/07-01-SUMMARY.md`
- FOUND: commit `3d982e8` (Task 1)
- FOUND: commit `59856cb` (Task 2)
- 2 public helpers present in `app/services/pdf_engine.py`
- AGPL guard PASSED; `git diff --stat HEAD -- app/` only `app/services/pdf_engine.py`
- 14 TEST-03 PASSED; baseline `315 passed + 3 skipped + 3 xfailed`; Phase 6 regression 3 XFAIL

---
*Phase: 07-option-b-implementation-content-stream-surgery*
*Completed: 2026-05-28*
