---
phase: 03-logo-placement
reviewed: 2026-05-23T00:00:00Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - app/api/pages.py
  - app/api/process.py
  - app/models.py
  - app/services/logo.py
  - app/services/pdf_engine.py
  - app/services/pipeline.py
  - app/services/render.py
  - logos/manifest.json
  - tests/test_coords.py
  - tests/test_logo.py
  - tests/test_process_api.py
  - web/index.html
  - web/js/api.js
  - web/js/app.js
  - web/js/logos.js
  - web/js/regions.js
  - web/js/viewer.js
  - web/styles/app.css
  - web/styles/tokens.css
findings:
  critical: 0
  warning: 5
  info: 6
  total: 11
status: issues_found
---

# Phase 3: Code Review Report (UAT hotfix)

**Reviewed:** 2026-05-23
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Adversarial review of the UAT-driven hotfix bundle — rotation/upright-logo, per-region
auto-logo by aspect, original-preview render fix, framing lock + 恢復原圖, no-confirm replace,
contrast/zoom defaults, and the side-panel empty-state contradiction fix.

The core security invariants survived intact:

- The fitz import remains confined to `pdf_engine.py` (T-02-03 / AGPL seam) — `place_logo`'s
  new `rotate=` argument was added inside the seam, not at a caller.
- The `logo_id` allowlist (T-03-01) and PNG-only enforcement (WR-04) are unchanged in
  `logo.resolve()`. The new `pick_logo_id_for_rect()` still routes its path resolution through
  `_resolve_path` with the same `is_relative_to(LOGOS_DIR)` containment assert.
- Deferred-mutation (D-05) is intact: `process_job` resets the work copy from the immutable
  original at the start of every run and never touches `originals/`. The user-rotation bake
  saves the OUTPUT with rotation set, then resets pages back to intrinsic BEFORE saving the
  work copy (so the result-render path stays symmetric with `原圖`) — tests
  (`test_process_rotation_does_not_persist_to_work_copy`, the SHA-256 deferred-mutation test)
  prove the invariant survived.
- Rotation math composes correctly across (intrinsic, user) combinations: I traced every
  combination of `intrinsic ∈ {0,90,180,270} × user ∈ {0,90,180,270}` through both
  `page_dimensions` and the pipeline's `set_page_rotation → page_dimensions(rotate=0)` path
  and the displayed-dim math agrees with the client side in every case.
- The frontend stays innerHTML-free (T-02-11 / T-03-04): logos.js's auto cell uses
  `appendChild(<br>)` + `createTextNode`, never an HTML string.

The issues below are correctness/UX defects introduced by the rapid hotfix iteration — none
ship recoverable supplier content, none bypass an allowlist, none mutate the original.

## Warnings

### WR-01: `notifyJobInputChanged` invalidates a fresh result but never repaints `clearAllBtn` visibility

**File:** `web/js/regions.js:455-464`
**Issue:** `renderList()` is the only place that sets `clearAllBtn.hidden = resultFresh`. When
a job-input change (logo selection, rotation) invalidates a fresh result, `notifyJobInputChanged`
flips `resultFresh = false` and (conditionally) calls `setViewMode("original")`, but it never
calls `renderList()`. Result: after the user applies, then changes the logo (which clears
`resultFresh`), the 清除全部 button stays hidden in the side panel even though the user
should now be able to clear framing again. The state is recoverable only by navigating pages
(which triggers `onPageChanged → renderList`).

Reproducer: upload PDF → frame a region → apply (result fresh, 清除全部 hidden) →
change the logo selection → 清除全部 stays hidden (incorrect; the result is now stale and the
user is back in the pre-apply mode).

**Fix:**
```javascript
export function notifyJobInputChanged(message) {
  if (resultFresh) {
    resultFresh = false;
    if (viewMode === "result") {
      setViewMode("original");
    }
    setActionStatus(message || COPY.staleNotice);
    renderList(); // <-- restore clearAllBtn.hidden visibility for the now-stale result
  }
  updateActionGroup();
}
```

### WR-02: Auto-logo picker considers manifest entries that fail PNG validation

**File:** `app/services/logo.py:182-204`
**Issue:** `_logo_aspect()` iterates manifest entries via `_load_manifest()` and reads
`Image.open(path).size` without calling `_validate_png()` first. So auto-selection's candidate
set is wider than `list_logos()`'s catalog — a manifest entry that is a JPEG, corrupt PNG, or
oversized file is filtered out of the picker (correct, per `list_logos`) but still considered
in `pick_logo_id_for_rect`'s aspect search. If the closest-aspect winner is one of these
invalid entries, the subsequent `resolve(chosen)` raises `LogoError`, the pipeline catches it,
and the job degrades to pure removal for that region — silently. The user sees "logo skipped"
but does not understand why (the picker showed valid logos; nothing in the UI hints that an
invisible manifest entry is "winning" auto-pick).

This is also a divergence from the catalog filter — the picker is the catalog allowlist;
auto-pick should consult the SAME allowlist.

**Fix:** Use the same validation gate `list_logos` uses, OR cache validated ids and only
consider those. A minimal fix:
```python
def _logo_aspect(entry: dict) -> float | None:
    try:
        path = _resolve_path(entry)
        if not path.is_file():
            return None
        _validate_png(path)   # gate auto-pick on the same allowlist list_logos uses
        key = (str(path), path.stat().st_mtime)
        cached = _aspect_cache.get(key)
        if cached is not None:
            return cached
        with Image.open(path) as img:
            width, height = img.size
    except (LogoError, OSError, UnidentifiedImageError, ValueError):
        return None
    ...
```

### WR-03: `_aspect_cache` grows unbounded across asset replacements

**File:** `app/services/logo.py:179`
**Issue:** The module-level cache is keyed by `(str(path), path.stat().st_mtime)`. Every time
an admin replaces a logo file in place, the mtime changes and a new entry is inserted; the OLD
`(path, old_mtime)` entry stays in the dict forever. In a long-lived uvicorn worker the cache
grows monotonically — one stale entry per asset replacement, per worker. Not exploitable, but
a slow memory leak that violates the "stateless internal tool" deployment assumption.

**Fix:** Either evict same-path entries when a new mtime appears, or scope the cache to
`path` only and re-read on mtime mismatch:
```python
_aspect_cache: dict[str, tuple[float, float]] = {}  # path -> (mtime, aspect)

def _logo_aspect(entry):
    ...
    mtime = path.stat().st_mtime
    cached = _aspect_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    with Image.open(path) as img:
        width, height = img.size
    if not width or not height:
        return None
    aspect = width / height
    _aspect_cache[str(path)] = (mtime, aspect)
    return aspect
```

### WR-04: A failing result-image load breaks the viewer's error state model

**File:** `web/js/viewer.js:217-222` + `web/js/regions.js:543-552` (interaction)
**Issue:** `renderPage()` sets `pageImage.onerror = showPageError` (which hides every state
except `error`). When `regions.js: setViewMode("result")` does `showResultImage(url)` (which
just assigns `pageImage.src = url`), the previous `onerror` from the most recent `renderPage`
remains attached. If the result-image fetch fails (e.g., the server crashed mid-redaction,
caching layer 404), `pageImage.onerror` fires and the WHOLE stage switches to the page-render
error state. The user is stranded — there is no path back to the original view (the apply
button is gone, the regions list is hidden behind the error state, no retry button targets
this case). The only recovery is 更換檔案.

This is a regression specifically introduced by the "after a process the work copy is in a
known-good state" assumption — but a transient fetch failure shouldn't burn the whole UI.

**Fix:** Result-image loads should surface a region-panel notice with retry, not the global
page-render error. Either give regions.js's `showResultImage` its own onerror handler that
calls `showNotice(COPY.resultRenderFailed, true, () => setViewMode("result"))`, or scope
`showPageError` to renderPage's own onerror only:
```javascript
// in viewer.js, expose a setter and let regions.js install its own handler
export function showResultImage(url, onError) {
  if (state.sessionId === null || !url) return;
  pageImage.onerror = onError || pageImage.onerror;
  pageImage.src = url;
}
```

### WR-05: Pipeline emits both an output PDF and a stale work copy if work-copy save fails after output save

**File:** `app/services/pipeline.py:285-300`
**Issue:** Inside the `try` block we (1) save the OUTPUT pdf with rotations baked, then (2)
reset rotations, then (3) save the work copy to a tmp path, then (outside the try) (4)
atomically replace the work copy with the tmp. If step (3) fails (e.g., out-of-disk), control
exits the `try/finally` (closing doc) and the function raises — but step (1)'s output file is
already on disk. The work copy then remains the FRESHLY-COPIED ORIGINAL from line 129's
`shutil.copyfile(original, work)` reset — i.e., NOT redacted.

After this failure, a subsequent `GET /sessions/{id}/result` downloads a redacted PDF, but
`GET /sessions/{id}/result/pages/{n}/image` (which renders the work copy) shows the
UNREDACTED page. Before/after preview lies about the downloaded contents.

A simpler fix is to save to a temp output file first, then atomically rename; OR save work
copy first, then output. The asymmetry exists because the work copy must be reset to
intrinsic rotation while the output must keep rotation baked. A clean reorder:

**Fix:**
```python
# Save work copy first (the substrate for /result/pages render). If THIS fails, we
# bail with no half-state on disk.
for page_idx, intrinsic in intrinsic_by_page.items():
    pdf_engine.set_page_rotation(pdf_engine.get_page(doc, page_idx), intrinsic)
work_tmp = Path(work).with_suffix(".redacted.tmp.pdf")
pdf_engine.save_doc(doc, work_tmp)

# Re-apply user rotation for the download bake.
for page_idx, user_deg in rotations.items():
    if user_deg % 360 == 0:
        continue
    pdf_engine.set_page_rotation(
        pdf_engine.get_page(doc, page_idx),
        (intrinsic_by_page[page_idx] + user_deg) % 360,
    )

out_file = out_dir / out_name
out_tmp = out_file.with_suffix(".tmp.pdf")
pdf_engine.save_doc(doc, out_tmp)
# After both saves succeed, swap both into place.
Path(work_tmp).replace(work)
Path(out_tmp).replace(out_file)
```

This costs two extra set_rotation calls but guarantees the work copy and output are either
both-updated or both-untouched.

## Info

### IN-01: `notifyJobInputChanged()` from rotation shows the "framing changed" stale copy

**File:** `web/js/regions.js:724`
**Issue:** `onPageRotated` calls `notifyJobInputChanged()` with no message argument, so the
action status reads "框選已變更,請重新套用以更新結果" — but the user rotated, they did not
edit framing. Slightly misleading UX copy.

**Fix:** Pass a rotation-specific stale message, e.g. `notifyJobInputChanged("頁面方向已變更,請重新套用以更新結果")`.

### IN-02: Manifest's vestigial `1.jpg` / `2.jpg` source files left in `logos/`

**File:** `logos/` (filesystem layout) — manifest at `logos/manifest.json:1-4`
**Issue:** The directory contains `1.jpg`, `1.png`, `2.jpg`, `2.png` but the manifest only
references the two `.png` entries. The JPGs are the pre-transparent-PNG conversion source
files. They are NOT served (manifest filter is the gate) but they DO inflate the deploy
artifact and could confuse a future admin replacing logos. Cosmetic cleanup.

**Fix:** Move source JPGs outside `logos/` (e.g., to a `logos/.source/` ignored by the
manifest), or remove from the deployed image.

### IN-03: `auto_logo=true` AND `logo_id` set by the same JobSpec — silent priority

**File:** `app/services/pipeline.py:192-198`
**Issue:** When both `auto_logo=True` and a non-null `logo_id` are POSTed, the pipeline
silently ignores `logo_id` (auto_logo wins). The frontend never sends this combination
(getSelectedLogoId returns null when isAutoLogo is true), so this is purely a defensive
concern, but a future client refactor could easily ship both. The current behavior is
reasonable but undocumented at the model layer.

**Fix:** Either add a Pydantic validator that rejects the combination, or document the
priority order in the JobSpec docstring. Cheap defense-in-depth:
```python
@model_validator(mode="after")
def _exclusive_logo_modes(self):
    if self.auto_logo and self.logo_id:
        raise ValueError("auto_logo and logo_id are mutually exclusive")
    return self
```

### IN-04: Projection denominator can fall back to CSS-pixel space during a narrow load race

**File:** `web/js/regions.js:153-168`
**Issue:** `projection()` falls back to `pageImage.naturalWidth || frameW` when
`imageDimsByPage[currentPage]` is unset. The `frameW` fallback only kicks in when BOTH the
image and the `/meta` fetch are still in flight — but once the frame has a non-zero size
(applyZoom ran, which depends on /meta), dims are usually set. The narrow race is when /meta
fetched by `initRegions` lags /meta fetched by `initViewer` AND the user clicks before the
image loads. On a HiDPI display, the fallback would mis-scale by `devicePixelRatio` (image
pixels = CSS pixels × dpr, but the fallback divides by `frameW` which equals image-pixel
width naturalWidth on dpr=1 but cssW on dpr=2). In practice the sub-threshold filter
(`DRAG_THRESHOLD=4`) catches almost all cases and the window is sub-100ms.

**Fix:** Either await the /meta result before enabling pointer interactions, OR drop the
final `frameW` fallback (the dims and naturalWidth fallbacks are sufficient):
```javascript
const imgW = (dims && dims.imgW) || pageImage.naturalWidth || 0;
const imgH = (dims && dims.imgH) || pageImage.naturalHeight || 0;
if (imgW === 0 || imgH === 0) {
  return { toImageX: () => 0, toImageY: () => 0, /* ... */, imgW: 0, imgH: 0 };
}
```
Then the onPointerUp clamp + sub-threshold check naturally drop the zero-area region.

### IN-05: Rotating mid-drag leaves the rubber-band positioned against a stale frame size

**File:** `web/js/regions.js:316-389` + `web/js/viewer.js:272-289`
**Issue:** If a user is mid-drag on the overlay and simultaneously triggers rotation (two-
handed mouse on rotate buttons, or via a future keyboard shortcut), `rotateBy` reflows the
frame while `dragStart` and `drawEl` are non-null. The `drawEl`'s CSS coordinates were
captured before the reflow and the eventual `onPointerUp` projection uses the NEW frame
dimensions — yielding a pxRect that does not match what the user dragged. Currently impossible
via single-pointer mouse, but trivially reachable on touch / a future keyboard binding.

**Fix:** Cancel any in-progress drag at the start of `onPageRotated`:
```javascript
function onPageRotated(detail) {
  if (dragStart) cleanupDrag({});
  ...
}
```

### IN-06: No focus trap inside the clear-all confirm modal

**File:** `web/index.html:412-429` + `web/js/regions.js:664-672`
**Issue:** The clear-confirm modal opens with `clearConfirmBtn.focus()` but Tab can move focus
out of the dialog (onto the toolbar, region rows, etc.). Standard accessibility practice for
`role="dialog" aria-modal="true"` is to trap focus inside the dialog while open.

**Fix:** On the modal's keydown listener, intercept Tab/Shift-Tab and loop focus between
the two buttons (cancel ↔ confirm). Lower priority because the modal is short-lived and
keyboard-savvy users can also use Escape (already wired).

---

_Reviewed: 2026-05-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
