---
phase: 02-region-removal
reviewed: 2026-05-22T00:00:00Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - app/api/process.py
  - app/config.py
  - app/main.py
  - app/models.py
  - app/services/coords.py
  - app/services/pdf_engine.py
  - app/services/pipeline.py
  - app/services/redact.py
  - scripts/smoke_02_03.py
  - tests/test_coords.py
  - tests/test_process_api.py
  - tests/test_redact.py
  - web/index.html
  - web/js/api.js
  - web/js/app.js
  - web/js/regions.js
  - web/js/viewer.js
  - web/styles/app.css
  - web/styles/tokens.css
findings:
  critical: 2
  warning: 6
  info: 5
  total: 13
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-05-22T00:00:00Z
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Phase 2 implements the region-removal slice: a vanilla-JS overlay collects image-pixel
rectangles, the backend maps them to PDF points and truly removes content via PyMuPDF
redaction on a work copy, then exports `原名_logoswap.pdf`. The architecture is sound and
the security posture is generally strong: the Phase-1 session-id allowlist is correctly
re-applied on the new endpoints, the deferred-mutation invariant is structurally guarded,
the AGPL/fitz seam is intact, `PDF_REDACT_TEXT_NONE` is refused, the frontend uses
`textContent`/`createElement` throughout (no `innerHTML`), and `api.js` remains the sole
server seam.

However, the review surfaced **two BLOCKER-class defects that both undermine the core
"所見即所得 / 真正移除" guarantee**:

1. **A client/server DPI disagreement** that silently redacts the wrong area on any page
   large enough to trigger the server's pixel-budget DPI reduction (CR-01). The frontend
   hardcodes `dpi: 200`, but the page may have been rendered (and measured) at a *lower*
   effective DPI.
2. **An over-strict residual-content assertion** that raises a hard 422 for the exact
   primary use case — a CAD vector line that crosses the region boundary (CR-02) — failing
   a legitimate removal rather than succeeding.

The remaining findings concern robustness (orphaned temp/output files on failure, missing
`dpi` echo on the result render, fragile `querySelector` id interpolation) and minor
quality issues.

## Critical Issues

### CR-01: Client hardcodes `dpi: 200` but the server may render/measure at a lower effective DPI — wrong area redacted

**File:** `web/js/regions.js:56`, `web/js/regions.js:550-553`; `app/services/pipeline.py:91-119`; `app/services/render.py:55-71,118-147`

**Issue:** The coordinate contract requires that the `dpi` in the `JobSpec` be *the DPI the
client measured `px_rect` at* (stated explicitly in `app/models.py:79-82` and
`app/services/coords.py:54-56`: "`dpi` MUST be the actual DPI that image was rendered at;
never assume a default"). The frontend violates this:

- `regions.js` defines `const DEFAULT_DPI = 200` (line 56) and posts `dpi: DEFAULT_DPI`
  unconditionally (line 551), regardless of the per-page render DPI.
- But `render.page_meta` / `render.render_page` apply `fit_dpi_to_pixel_budget`
  (`render.py:55-71`), which scales the *effective* DPI **down below 200** for a page whose
  MediaBox is large enough that 200 DPI would exceed `MAX_RENDER_PIXELS` (40 MP). The
  `/meta` response then reports `img_w`/`img_h` computed at that reduced `effective_dpi`
  (`render.py:137-146`), and the overlay measures `px_rect` against exactly those reduced
  dims (`regions.js:131-140`, `imageDimsByPage` from `api.pageMeta`).
- `pipeline.process_job` then maps the rect using the JobSpec's `dpi` (200) via
  `coords.pixels_to_pdf_rect(clamped_px, dpi, page)` (line 119) and computes the clamp box
  as `page_w_pt * (dpi/72)` at 200 as well (lines 112-114).

For any page where `effective_dpi < 200`, the client's pixels (measured at, say, 150 DPI)
are interpreted by the server as 200-DPI pixels. The scale factor `72/dpi` is then wrong by
`effective_dpi/200`, so the redaction rect is shifted and shrunk relative to what the user
framed — **the wrong region is removed, silently, with no error**. This is the highest-risk
coordinate pitfall the phase was explicitly guarding against, and it is undetectable to the
user (the after-image looks plausible because it renders the wrong-but-self-consistent
region). It is realistically reachable within the 50 MB / 30-page envelope via a single
large-MediaBox CAD sheet.

**Fix:** Make the client send the *actual* per-page render DPI, not a constant. Record the
DPI alongside the image dims from `/meta` and use the current page's value (or, since a job
can span pages with differing effective DPIs, send a per-region/per-page DPI). Minimal
change in `regions.js`:

```js
// store dpi with the per-page dims
const meta = await api.pageMeta(sessionId, index);
imageDimsByPage.set(index, { imgW: meta.img_w, imgH: meta.img_h, dpi: meta.dpi });

// when applying, derive dpi from the page the regions were drawn on
// (the JobSpec carries ONE dpi; if effective DPI can differ per page, the contract must
//  move dpi into each region or the pipeline must re-derive scale per page from img dims).
```

The most robust fix is server-side: have `pipeline.process_job` ignore the client `dpi` for
the clamp/scale and instead recompute the scale from the page's own dimensions and the
effective render DPI it would produce (i.e. call the same `fit_dpi_to_pixel_budget` path),
so client and server cannot disagree by construction. At minimum, the JobSpec `dpi` must be
the effective DPI, and the per-page-DPI-divergence case must be handled rather than assumed
uniform.

### CR-02: Residual-content assertion fails legitimate CAD removals — a vector line crossing the region boundary raises 422

**File:** `app/services/redact.py:104-118`; `app/services/pdf_engine.py:246-288`

**Issue:** Redaction uses `graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED`
(`redact.py:107`), which only removes vector paths whose bounding box is **fully covered**
by the redaction rectangle. A CAD line/polyline that passes through the framed region but
extends outside it is *not* covered, so it correctly survives. But the post-redaction
emptiness assertion calls `get_drawings_intersecting(page, user_rect)` (line 113), whose
overlap test is inclusive and degenerate-aware (`pdf_engine.py:246-288`) — it reports *any*
drawing whose bbox merely overlaps or even abuts the unpadded user rect. The surviving
crossing line therefore registers as "residual," and `remove_region` raises
`RedactError("residual_content")` (lines 114-118), which the API maps to a hard 422.

Net effect: framing a region over a logo that sits on top of CAD linework — the project's
primary stated use case ("含 CAD 設計資料... 供應商的商標圖案與文字") — fails the whole job
with "移除後仍偵測到殘留內容" instead of removing the logo and leaving the through-line. The
assertion conflates "a drawing intersects the rect" with "extractable supplier content
survived inside the rect," which are not the same: a line clipped by the rect is expected to
remain partly visible by design.

This is a correctness/usability blocker: legitimate removals on the target document class
will be rejected. (The existing tests pass only because their fixtures place the entire line
*inside* the rect, so it is fully covered and removed — `tests/test_redact.py:34`,
`conftest.py:29` draw the line within the region; the crossing-boundary case is untested.)

**Fix:** The assertion must distinguish "content survived where it should have been removed"
from "content legitimately clipped by the boundary." Options:

```python
# Option A: assert against TEXT only (the recoverable-supplier-content risk), and for
# vectors assert only that no drawing lies WHOLLY inside the user rect (a fully-covered
# survivor is the real failure; a crossing line is expected).
residual_words = pdf_engine.get_text_words_in_rect(page, user_rect)
survivors = [d for d in pdf_engine.get_drawings_intersecting(page, user_rect)
             if _drawing_fully_inside(d, user_rect)]
if residual_words or survivors:
    raise RedactError("residual_content", ...)
```

Add a regression test that frames a region over a line which extends beyond the region on
both sides and asserts `removed is True` (not a `RedactError`). Decide and document the
intended semantics for partially-covered vectors (clip vs. remove-if-touched) explicitly.

## Warnings

### WR-01: Orphaned output + temp files when redaction fails mid-job

**File:** `app/services/pipeline.py:97-142`

**Issue:** `process_job` writes the export to `outputs/原名_logoswap.pdf`
(`save_doc(doc, out_file)`, line 134) and a work temp (`save_doc(doc, work_tmp)`, line 137)
*after* the region loop. If the loop raises `PipelineError`/`RedactError` (out-of-range page
or residual content), no files are written — good. But the per-region loop mutates the
in-memory `doc` cumulatively; once any earlier region succeeds and a *later* region raises,
the partially-redacted state is discarded (correct), yet a subsequent retry re-opens the
*work copy*, which on a prior **successful** run has already been replaced with the redacted
version (line 142). Re-applying the same JobSpec then redacts an already-redacted document —
the second `get_text_words_in_rect` is empty, so the region reports `removed=False`, masking
that the first run's result is what shipped. More concretely: because the work copy is
mutated in place across runs (D-05 says original is immutable, but the *work copy* is not
reset between `/process` calls), a second apply with a *different* region set operates on the
already-redacted substrate, not the pristine page. This is a stale-state hazard for the
"重新套用" flow that `regions.js` exposes (`applyBtn` -> `reapply`, line 443).

**Fix:** Reset the work copy from the immutable original at the start of each `process_job`
run (copy `original_path` -> `work_path` before redacting), so every apply is computed from
the pristine document and "重新套用" is idempotent with respect to the current region set.
Alternatively redact a fresh in-memory copy of the original each run and never persist
cumulative state into `work/`.

### WR-02: Result-render endpoint ignores effective-DPI and has no `dpi` echo path consistent with the overlay

**File:** `app/api/process.py:64-97`

**Issue:** `get_result_page_image` renders the work copy at `config.DEFAULT_DPI` (200) when
no `dpi` query is supplied (line 81) and emits `X-Render-Dpi` from the actual render. That is
fine in isolation, but combined with CR-01 the before-image (`/pages/{n}/image`) and the
after-image (`/result/pages/{n}/image`) can be rendered at *different* effective DPIs if the
page trips the pixel budget, so the before/after toggle (`regions.js:setViewMode`) swaps
between two images of different pixel sizes while the overlay projection assumes a single
`imgW/imgH` per page. The overlay is hidden in result mode (line 251), so rectangles aren't
mis-drawn, but the displayed image can jump size on toggle.

**Fix:** Ensure the result render uses the same effective DPI as the original page render
(both already route through `render` + `fit_dpi_to_pixel_budget`, so this should hold — but
verify and add a test asserting `X-Image-Width-Px` matches between `/pages/{n}/image` and
`/result/pages/{n}/image` for the same page). Resolve jointly with CR-01.

### WR-03: `setActiveRegion` interpolates region id into a CSS selector unsanitized

**File:** `web/js/regions.js:288,295`

**Issue:** `overlay.querySelector(`.region-rect[data-region-id="${id}"]`)` and the matching
`regionListEl.querySelector(...)` interpolate `id` directly into a CSS selector string. Today
`id` is an internal integer (`nextRegionId++`, line 98), so this is safe in practice, but it
is a fragile pattern: any future change that lets ids be non-numeric (e.g. server-issued
string ids, composite keys) would break the selector or, if a value ever contained a quote,
allow selector injection. This is a latent correctness/robustness bug, not an active XSS (the
value is never rendered as HTML).

**Fix:** Look up elements without string interpolation:

```js
const rect = [...overlay.querySelectorAll(".region-rect")]
  .find((el) => el.dataset.regionId === String(id));
```

or store element references in the region model. Same for the `.region-row` lookup.

### WR-04: `getViewerState` and `clampImg` import/usage drift; `pageCount` set but unused

**File:** `web/js/regions.js:25-28,95,649`; `web/js/viewer.js:326-332`

**Issue:** `regions.js` imports `getViewerState` from `viewer.js` (lines 25-28) but never
calls it — dead import. `pageCount` is assigned in `initRegions`/`resetRegions`
(lines 96, 649, 680) but never read. These indicate the module relies on `currentPage`/event
detail rather than the viewer snapshot, so the imported accessor is vestigial. Dead
imports/state obscure the actual data flow and invite the kind of source-of-truth confusion
that CR-01 stems from.

**Fix:** Remove the unused `getViewerState` import and the unused `pageCount` field, or wire
them in if they were intended to be the projection source of truth (which would also help
CR-01 by reading the authoritative per-page DPI from the viewer).

### WR-05: `output_filename` re-reads session meta on every call; download path trusts CJK stem with no length/round-trip bound

**File:** `app/services/pipeline.py:51-60,130`; `app/api/process.py:110-123`

**Issue:** `process_job` calls `output_filename` (line 130), which calls
`storage.read_session_meta` (pipeline.py:53), and `download_result` calls it again
(process.py:110) — the filename is derived from the stored display name each time. The on-disk
path is fixed and session-scoped (good, no traversal), but the derived `*_logoswap.pdf` stem
is the unbounded CJK display filename, passed through `quote(out_name, safe="")` into the
`Content-Disposition` `filename*=` header (process.py:122-123). An adversarial display name
(very long, or containing control chars that survive sanitization) would be reflected into a
response header. `storage.sanitize_filename` strips path separators and `..` but does not cap
length or strip control characters, so a 10 KB filename or embedded CR/LF-adjacent bytes could
reach the header. Header injection is mitigated by `quote()` percent-encoding, but the
unbounded length is a minor DoS/robustness gap.

**Fix:** Cap the stem length (e.g. 128 chars) and strip control characters in
`_logoswap_name`/`sanitize_filename` before it is used in the header. Cache the computed
output filename on the session meta at first process so it is not re-derived per request.

### WR-06: `clamp_px_rect` `was_clamped` flag compares the normalized/cleaned rect against the *raw float* tuple — spurious clamp flags

**File:** `app/services/coords.py:96-113`

**Issue:** `was_clamped` is computed as `nan_seen or clamped_rect != raw` (line 112), where
`raw = tuple(float(v) for v in px_rect)` (line 96) is the *un-normalized* input, but
`clamped_rect` is built from the *normalized* (`_normalize_tuple`) and clamped values. For an
in-bounds but reversed-drag rect (e.g. `(300,400,100,200)`), `clamped_rect` is the normalized
`(100,200,300,400)` which `!= raw`, so `was_clamped` is `True` even though nothing was clamped
to a boundary — only drag direction was corrected. The frontend surfaces this as the
"框選超出頁面範圍,已自動調整到頁面邊界" notice (`regions.js:564`, `COPY.clamped`), which is the
*wrong* message for a mere reversed drag (it claims the box exceeded the page when it didn't).
The test `tests/test_coords.py:249-252` actually encodes this conflation as intended behavior,
so it's a spec ambiguity, but the user-facing copy is misleading.

**Fix:** Distinguish "normalized (drag direction corrected)" from "clamped to boundary".
Compare the *normalized* input against the *clamped* output for the boundary flag:

```python
norm = _normalize_tuple(tuple(cleaned))
clamped_rect = (...)  # as today
was_clamped = nan_seen or clamped_rect != norm   # boundary clamp only
```

and only show `COPY.clamped` when an edge was actually moved to 0/img_w/img_h.

## Info

### IN-01: `quote` import and RFC-5987 disposition duplicated between modules

**File:** `app/api/process.py:26,122-123`

**Issue:** The `Content-Disposition` `filename*=UTF-8''` construction is hand-built inline.
If Phase 3 adds more download endpoints, this will be copy-pasted. Consider a small helper
(`storage` or a `responses` util) so the RFC-5987 encoding lives in one place.

### IN-02: Magic numbers in frontend projection / drag handling

**File:** `web/js/regions.js:56-57`; `web/js/viewer.js:23,99`

**Issue:** `DRAG_THRESHOLD = 4`, `DEFAULT_DPI = 200`, the `- 64` stage-padding subtraction in
`currentZoomFactor` (viewer.js:99), and `ZOOM_STEPS` are inline constants. The `- 64` in
particular hard-codes an assumption about `--space-xl` padding that will silently break if the
token changes. Prefer reading the padding from computed style or a shared constant.

### IN-03: Broad `except Exception` blocks rely on comments rather than narrow catches

**File:** `app/services/pdf_engine.py:41,310-313`; `scripts/smoke_02_03.py:28`

**Issue:** Several `except Exception`/bare-pass blocks are intentional (parser isolation, safe
close), and are annotated, which is acceptable. Noted only for completeness: the `close()`
swallow (pdf_engine.py:310-313) could log at debug level so a genuinely failing close isn't
invisible during diagnosis.

### IN-04: `getTotalRegionCount` exported but unused; `currentZoomFactor()` recomputed on every page change

**File:** `web/js/regions.js:705-708`; `web/js/viewer.js:195`

**Issue:** `getTotalRegionCount` is exported from `regions.js` but has no importer (app.js does
not call it). Minor dead surface. Remove if not part of a planned Phase-3 contract.

### IN-05: Smoke harness committed under `scripts/` despite being described as throwaway

**File:** `scripts/smoke_02_03.py:12`

**Issue:** The module docstring states "This is a throwaway harness (NOT a committed pytest)",
yet it is committed. Either fold its unique assertions (rotated-page placement end-to-end) into
a real pytest under `tests/` or remove it to avoid bit-rot. As-is it duplicates
`tests/test_process_api.py` coverage without being run by CI.

---

_Reviewed: 2026-05-22T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---

## Resolution (2026-05-22)

All BLOCKER and WARNING findings fixed; Info findings (IN-01..05) intentionally deferred
(out of the requested fix scope). Each fix is an atomic commit with a regression test that
fails before the fix and passes after. Full pytest suite (147 passed) + the smoke harness
(`scripts/smoke_02_03.py`) are green. Invariants verified intact: fitz confined to
`pdf_engine.py` (AST test), the Phase-1 `session_id` allowlist, and original-file
immutability (SHA-256 test).

- **CR-01** (`0e741fc`) — `pipeline.process_job` re-derives the EFFECTIVE per-page DPI via
  `render.fit_dpi_to_pixel_budget` (instead of trusting the JobSpec `dpi`) for clamp + mapping,
  so a page whose effective DPI was reduced below the requested 200 redacts the correct area by
  construction. `regions.js` records `meta.dpi` per page and documents the JobSpec `dpi` as the
  requested ceiling (no hardcoded 200 for measurement). Regression: large-MediaBox page
  (effective DPI < 200) — content removed; the old 200-based mapping proven divergent.
- **CR-02** (`68d319b`) — added `pdf_engine.get_drawings_fully_inside`; the post-redaction
  vector assertion now fails only for a drawing WHOLLY inside the user rect, aligning with
  `LINE_ART_REMOVE_IF_COVERED`. A logo-on-CAD-linework job (line crossing the boundary) now
  succeeds (text removed, through-line kept); a fully-covered vector is still removed. Semantics
  documented in `redact.py`.
- **WR-01** (`249fecf`) — `process_job` resets the work copy from the immutable original at the
  start of every run, so "重新套用" is idempotent and never accumulates stale redactions.
- **WR-02** (`29b7a9e`) — verified (and locked with a test) that the before/after images render
  at the same effective DPI + pixel dims per page; resolved jointly with CR-01.
- **WR-03 / WR-04** (`725ced5`) — `setActiveRegion` looks up by `dataset.regionId` instead of
  interpolating the id into a CSS selector; removed the dead `getViewerState` import and the
  write-only `pageCount` field.
- **WR-05** (`e1a107a`) — `_logoswap_name` strips control characters and caps the stem to 128
  before it reaches the Content-Disposition header. (The per-request caching sub-suggestion was
  not adopted: re-derivation is a single cached-on-disk JSON read plus a bounded string op, and a
  cache field would add staleness risk for negligible gain; the security-relevant bounding is the
  substantive fix.)
- **WR-06** (`7e64bb5`) — `coords.clamp_px_rect` compares the NORMALIZED input against the
  clamped output, so the `clamped` flag (and the "超出頁面範圍" notice) fires only on a real
  boundary move, never on a reversed-but-in-bounds drag.

_Fixed: 2026-05-22 — Claude (gsd-code-fixer)_
