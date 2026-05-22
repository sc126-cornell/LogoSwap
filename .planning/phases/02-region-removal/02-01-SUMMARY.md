---
phase: 02-region-removal
plan: 01
subsystem: coords
tags: [coords, pymupdf, fitz, rotation, derotation-matrix, dpi-scale, mediabox, round-trip-test, pure-module, agpl-isolation]

# Dependency graph
requires:
  - phase: 01-input-preview
    provides: "pdf_engine seam (sole fitz importer) + render.page_meta exposing the exact dpi/page_w_pt/page_h_pt/rotation/img_w/img_h the mapper pairs a pixel rect with"
provides:
  - "app/services/coords.py — the single px<->pt conversion chokepoint (pixels_to_pdf_rect / pdf_rect_to_pixels / clamp_px_rect), fitz-free"
  - "pdf_engine matrix accessors: get_page, map_rect_to_unrotated, map_rect_to_displayed, unrotated_content_box (matrix multiply stays inside the AGPL seam)"
  - "Proven contract: px->pt->px round-trips < 1px (observed ~0.00004px) at rotation 0/90/180/270 AND on a non-(0,0) MediaBox page; 0deg + all-rotation visual-overlap >= 0.95 IoU"
  - "clamp_px_rect bounds/NaN/inverted guard for the HTTP boundary (threat T-02-01) Plan 02-02 reuses"
affects: [02-02 removal pipeline, 02-03 region selection UI, 03-logo-insertion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Centralized coordinate mapper (ARCHITECTURE Pattern 2): one tested place gets DPI scale + top-left origin + rotation right; every edit path routes through it"
    - "Matrix-multiply-in-seam: coords stays fitz-free; page.derotation_matrix/rotation_matrix multiplies live in pdf_engine so import fitz remains in exactly one file"
    - "Unrotated content box derived by derotating the rendered image rect (MediaBox-quirk-proof bound for redaction clamp), not page.rect/cropbox"

key-files:
  created:
    - app/services/coords.py
    - tests/test_coords.py
  modified:
    - app/services/pdf_engine.py

key-decisions:
  - "derotation_matrix maps DISPLAYED space into UNROTATED CONTENT space (mediabox), NOT page.rect — on rotated pages page.rect is the displayed rect; the containment bound is the derotated full-image box"
  - "set_mediabox produces an asymmetric/clipped cropbox in PyMuPDF; the round-trip (matrix inverse) is the real gate and holds regardless, so containment is asserted against the derotated image box not cropbox"
  - "coords returns the fitz.Rect the seam produced (never constructs one) so it is a usable Rect for 02-02 redaction while importing no fitz"
  - "clamp_px_rect is NaN-safe and normalizes drag direction; flags any correction for the API layer"

patterns-established:
  - "Pure mapper module: no fitz/FastAPI/IO; receives an open page handle + the actual render dpi"
  - "Statement-level (AST) fitz-purity test instead of naive substring, mirroring the repo-wide grep acceptance check"

requirements-completed: [REMOVE-03]

# Metrics
duration: ~35min
completed: 2026-05-22
---

# Phase 2 Plan 01: 座標對應骨幹 (Coordinate Mapper Spine) Summary

**A pure, fitz-free px<->pt coordinate mapper (`coords.py`) that converts browser-image pixel rects to PyMuPDF Rects on the unrotated page and back — round-tripping at ~0.00004px error across 0/90/180/270 rotations and an offset MediaBox, with the matrix multiply confined to the engine seam and a 17-test gate harness that must stay green before any removal code lands.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-05-22 (approx)
- **Completed:** 2026-05-22
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- **`app/services/coords.py` — the single px<->pt chokepoint (REMOVE-03):** `pixels_to_pdf_rect(px_rect, dpi, page)` scales pixels by `72/dpi` (top-left origin, NO Y-flip per Anti-Pattern 4), maps displayed->unrotated via the page derotation matrix, and returns a normalized Rect; `pdf_rect_to_pixels` is the exact inverse; `clamp_px_rect` is the bounds/NaN/inverted guard.
- **AGPL seam preserved (T-02-03):** `coords.py` imports no `fitz`. The derotation/rotation matrix multiply lives in three new `pdf_engine` wrappers (`map_rect_to_unrotated`, `map_rect_to_displayed`, plus `get_page` and `unrotated_content_box`), so `grep -rl "import fitz" app/` still returns ONLY `app/services/pdf_engine.py`.
- **Round-trip GATE proven (Pitfalls 1-2):** parametrized px->pt->px at rotation 0/90/180/270 AND a non-(0,0) MediaBox page, asserting `< 1px` per edge — **observed max error ~0.00004px**. Plus a visual-overlap sanity (draw the mapped Rect, re-render, IoU vs the original selection) `>= 0.95` at 0deg and all four rotations.
- **Full suite green:** `pytest -q` = **110 passed** (Phase 1 tests + 17 new coords tests), zero regression.
- **No removal code written** — correctly deferred to Plan 02-02; this plan is mapping + tests only.

## Task Commits

Each task was committed atomically:

1. **Task 1: engine matrix accessors + pure coords module** — `b15620e` (feat)
2. **Task 2: round-trip + visual-overlap test harness** — `3ad0a0b` (test)

**Plan metadata:** (this SUMMARY + STATE + ROADMAP) — committed separately as `docs(02-01)`.

_Note: Task 1 is `tdd="true"`. Following the Phase 1 precedent (TDD source + behaviour tests authored together, verified green before commit), the implementation (engine seam + coords) and the proving harness were committed along their natural file boundary: Task 1 = the spine implementation (`pdf_engine.py` + `coords.py`), Task 2 = the full `tests/test_coords.py` gate that proves it. The harness was run green (`pytest tests/test_coords.py` = 17 passed) before each commit._

## Files Created/Modified

- `app/services/coords.py` (created) — pure coordinate mapper: `pixels_to_pdf_rect`, `pdf_rect_to_pixels`, `clamp_px_rect`, `_normalize_tuple`. No fitz / FastAPI / IO.
- `app/services/pdf_engine.py` (modified) — added `get_page`, `map_rect_to_unrotated`, `map_rect_to_displayed`, `unrotated_content_box`; existing `open_pdf/page_count/page_dimensions/render_page_to_png/close` wrappers unchanged.
- `tests/test_coords.py` (created) — 17 tests: round-trip per rotation, offset-MediaBox round-trip + inside-content-box, zero-rotation identity scale, drag-direction independence, `clamp_px_rect` (bounds/inverted/NaN), AST-based fitz-purity, and 0deg + all-rotation visual-overlap IoU.

## Function Signatures (the proven contract for Plan 02-02)

```
# app/services/coords.py  (pure; page is an opaque handle from pdf_engine.get_page)
pixels_to_pdf_rect(px_rect, dpi: int, page) -> fitz.Rect   # normalized, unrotated page space
pdf_rect_to_pixels(rect, dpi: int, page) -> (x0, y0, x1, y1)  # normalized image pixels
clamp_px_rect(px_rect, img_w, img_h) -> ((x0,y0,x1,y1), was_clamped: bool)

# app/services/pdf_engine.py  (the ONLY fitz importer)
get_page(doc, page_no) -> fitz.Page
map_rect_to_unrotated(page, rect_pts) -> fitz.Rect          # disp * derotation_matrix, normalized
map_rect_to_displayed(page, rect) -> (x0,y0,x1,y1)          # unrot * rotation_matrix, normalized
unrotated_content_box(page, img_w, img_h, dpi) -> (x0,y0,x1,y1)  # redaction clamp bound
```

## Round-Trip Evidence (max |Δ| per edge, 200 DPI fixtures, 400x600pt page)

| Case | Rendered img | Max round-trip error | Gate (<1px) |
|------|--------------|----------------------|-------------|
| rotation 0 | 1111x1667 | 0.000042 px | PASS |
| rotation 90 | 1667x1111 | 0.000041 px | PASS |
| rotation 180 | 1111x1667 | 0.000042 px | PASS |
| rotation 270 | 1667x1111 | 0.000041 px | PASS |
| offset MediaBox [10 10 410 610], 0deg | 1111x1667 | 0.000042 px | PASS |
| offset MediaBox [10 10 410 610], 90deg | 1667x1111 | 0.000041 px | PASS |

Visual-overlap (draw mapped Rect -> re-render -> IoU vs selection): `>= 0.95` at 0/90/180/270.

## Decisions Made

- **The derotated rect's containment bound is the UNROTATED CONTENT box, not `page.rect`.** Empirically `page.derotation_matrix` maps displayed space into the *mediabox/unrotated* space (e.g. on a 90deg 400x600 page a displayed-corner rect derotates to y up to 600, which is correctly inside the unrotated 400x600 content box but *outside* the displayed `page.rect` of 600x400). The mapper is correct; the right reference rect is the derotation of the full rendered image, exposed as `pdf_engine.unrotated_content_box` (also the natural redaction-clamp bound for 02-02).
- **`set_mediabox` cropbox quirk:** after `set_mediabox((10,10,410,610))`, PyMuPDF reports `page.rect=(0,0,400,600)` and an asymmetric `cropbox=(10,0,410,600)`. Rather than depend on that derived box, containment is asserted against the derotated image rect; the round-trip (a pure matrix inverse) is the hard gate and holds regardless of the MediaBox offset — exactly the "no constant offset appears" property the plan requires.
- **coords returns the seam's Rect, never constructs one** — keeps it engine-free while still handing 02-02 a usable `fitz.Rect` for `add_redact_annot`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Containment assertion used the wrong reference rect (test bug, not mapper bug)**
- **Found during:** Task 2 (round-trip harness, first run)
- **Issue:** The initial test asserted the derotated Rect lies inside `page.rect`. On rotated pages `page.rect` is the *displayed* rect, so a correctly-derotated coordinate legitimately falls outside it — the assertion failed at rotation 90 (`y1=596.4 > page.rect.y1=400`) even though the round-trip itself was exact. The mapping was right; the bound was wrong.
- **Fix:** Added `pdf_engine.unrotated_content_box(page, img_w, img_h, dpi)` (derotates the full rendered image rect = the true unrotated content bound) and asserted containment against it. This also gives Plan 02-02 the correct redaction-clamp bound.
- **Files modified:** `app/services/pdf_engine.py`, `tests/test_coords.py`
- **Verification:** All 17 coords tests pass at 0/90/180/270 + offset MediaBox; round-trip max error ~0.00004px.
- **Committed in:** `b15620e` (accessor) + `3ad0a0b` (test)

**2. [Rule 1 - Bug] coords docstring contained the literal `import fitz`, false-tripping the AGPL grep**
- **Found during:** Task 2 (purity test)
- **Issue:** `coords.py`'s module docstring used the literal phrase ``import fitz`` in prose. The repo-wide acceptance check `grep -rl "import fitz" app/` (and the purity test) would have falsely flagged `coords.py` as a second fitz importer — the identical trap Phase 1 documented for `render.py`.
- **Fix:** Reworded the docstring to avoid the literal substring ("does NOT import the engine library", "the engine import stays confined to that one seam"). Also hardened the purity test to parse imports via AST (statement-level) rather than substring matching.
- **Files modified:** `app/services/coords.py`, `tests/test_coords.py`
- **Verification:** `grep -rl "import fitz" app/` returns only `app/services/pdf_engine.py`; purity test passes.
- **Committed in:** `b15620e` (coords) + `3ad0a0b` (test)

---

**Total deviations:** 2 auto-fixed (2 bugs — one in the test harness, one a docstring/grep hazard).
**Impact on plan:** Both necessary to make the gate accurate and the AGPL acceptance check correct. No scope creep, no behaviour change to the mapper recipe (which followed ARCHITECTURE Pattern 2 verbatim). The `unrotated_content_box` accessor is a small, justified addition (Rule 2-adjacent) that 02-02 will reuse for redaction bounds.

## Issues Encountered

- **PyMuPDF coordinate-space subtlety (resolved):** confirmed empirically (via a throwaway probe) that `derotation_matrix` targets the unrotated mediabox space and that `set_mediabox` yields an asymmetric cropbox — both informed the containment-bound decision above rather than blocking work.
- **Git CRLF warnings** on staged files — benign Windows normalization, no action (same as Phase 1).
- **Pre-existing unstaged `.planning/config.json` change** (the `_auto_chain_active` flag) is NOT part of this plan and was deliberately left unstaged / uncommitted (out of scope).

## Threat surface scan

No new security surface beyond the plan's `<threat_model>`. Mitigations implemented as specified: T-02-01 (`clamp_px_rect` bounds + NaN + normalize, unit-tested; `unrotated_content_box` gives 02-02 the clamp bound), T-02-02 (round-trip + visual-overlap gate at all rotations + offset MediaBox — the structural REMOVE-03 guarantee), T-02-03 (coords imports no fitz; matrix multiply in the seam; grep returns only `pdf_engine.py`).

## Known Stubs

None. `coords.py` is real, runnable code with exact round-trip behaviour; no placeholder/hardcoded values. No redaction/removal code was written (correctly deferred to Plan 02-02).

## Next Phase Readiness

- **Plan 02-02 (removal pipeline) is unblocked:** the spine is proven. 02-02 can call `pdf_engine.get_page` + `coords.pixels_to_pdf_rect(px_rect, dpi, page)` to obtain the exact unrotated `fitz.Rect` to feed `add_redact_annot` + `apply_redactions`, clamp untrusted client rects with `coords.clamp_px_rect`, and bound the result with `pdf_engine.unrotated_content_box`. The contract (signatures + tolerances) is documented above.
- **Gate discipline:** `pytest tests/test_coords.py -q` (17 tests) must remain green; it is the regression gate for any change touching the mapper.
- **Carry-forward:** the render contract (`render.page_meta` exact dpi/img dims) pairs 1:1 with the mapper, so client and server cannot disagree on DPI.

## Self-Check: PASSED

- Created files verified present: `app/services/coords.py`, `tests/test_coords.py`. Modified: `app/services/pdf_engine.py`.
- Both task commits verified in git log: `b15620e` (Task 1, feat), `3ad0a0b` (Task 2, test).
- `pytest tests/test_coords.py -q` = 17 passed; full `pytest -q` = 110 passed. `grep -rl "import fitz" app/` = only `app/services/pdf_engine.py`. Round-trip max error ~0.00004px at all four rotations + offset MediaBox (< 1px gate).

---
*Phase: 02-region-removal*
*Completed: 2026-05-22*
</content>
</invoke>
