---
phase: 04-raster-image-support (post-verification hotfix sweep)
reviewed: 2026-05-23T00:00:00Z
depth: standard
diff_base: 137a592
files_reviewed: 7
files_reviewed_list:
  - app/api/pages.py
  - app/services/ingest.py
  - app/services/pdf_engine.py
  - app/services/redact.py
  - web/index.html
  - web/js/logos.js
  - web/styles/app.css
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 4 — Hotfix Sweep: Code Review Report

**Reviewed:** 2026-05-23
**Depth:** standard
**Diff base:** 137a592..HEAD (6 commits: 8c7e90a, a844946, e308f6a, e352b6d, 9b84b83, 6ae755f)
**Files Reviewed:** 7
**Status:** issues_found (3 Warning, 3 Info, 0 Critical)

## Summary

Six post-verification commits landed during DC-1 / DC-2 UAT to harden three distinct
seams: (a) Phase 4-01 RGBA transparency handling in `ingest.py`, (b) Phase 4-01 page
endpoint sourcing for image-upload sessions (`pages.py` now reads `pristine_path`
instead of `original_path` so image uploads, whose `originals/` are raw PNG/JPG/TIFF
bytes rather than a PDF, render correctly), and (c) Phase 2 zero-area drawing
artefacts that PyMuPDF leaves behind after `LINE_ART_REMOVE_IF_COVERED` on supplier
CAD PDFs (filter from residual check + physical white-cover pass).

**No Critical findings.** Every Phase-4 invariant the hotfixes were responsible for
preserving is intact:

- AGPL seam is clean (`import fitz` appears only in `app/services/pdf_engine.py:19`).
- XSS guard holds — the new `<img src="/assets/logo.png">` in `web/index.html` is a
  fully static element with a static `alt`; `logos.js` continues to use
  `createElement` + `textContent` exclusively.
- Path safety on the `pages.py` hotfix is preserved — `pristine_path` resolves via
  the same `subdir("pristine", session_id)` validator the rest of the app uses, and
  `_require_session` still gates the lookup.
- `originals/` (the SHA-256 D-05 invariant target) is no longer read by per-page
  endpoints at all — strict improvement, not regression.
- The zero-area cover routine runs AFTER the residual-content assertion, so a real
  surviving filled drawing still raises `RedactError("residual_content")`. The cover
  only paints over zero-area `type='f'` drawings that PyMuPDF itself renders as zero
  pixels — restoring cross-renderer parity (Adobe Reader / Chrome / Edge render them
  as 1-pixel hairlines), not hiding a real residual.
- The `PDF_REDACT_TEXT_NONE` defence-in-depth guard at `pdf_engine.py:289` is
  unchanged.

The three Warnings are quality / robustness issues (tmp-file pollution, redundant
modulo on an already-normalized angle, missing megapixel cap behind the
DecompressionBomb guard). The three Info items are style/clarity (duplicated magic
number, dead `sessionId` state in `logos.js`, magic-index `[3]` access on
`rgba.split()`).

## Warnings

### WR-01: Orphaned `.tmp` files committed to working tree contain stale source duplicates

**Files:** `app/services/pdf_engine.py.tmp.45532.260407520ef6`,
`web/index.html.tmp.9608.4c01df34b000` (untracked, visible in `git status`)

**Issue:** These editor-atomic-write leftovers contain near-identical but
DIVERGENT copies of `pdf_engine.py` and `index.html`. The `pdf_engine.py.tmp.*`
file also contains `import fitz` at line 19 — so the AGPL-seam invariant grep
(`grep -rn "import fitz" app/`) would either double-count or, worse, mask a real
divergence if the tmp drifts further. The `index.html.tmp.*` already differs in
heading whitespace (`/> 商標` vs `/>商標`), proof that the tmp content is stale.
A future debugger could open the wrong file and chase a phantom bug.

**Fix:** Delete both `.tmp.*` files and add a wildcard to `.gitignore`:

```gitignore
# Editor atomic-write leftovers
*.tmp.*
```

### WR-02: `place_logo` redundant `% 360` masks intent; missing `int()` cast vs. seam convention

**File:** `app/services/pdf_engine.py:329`

**Issue:** `page.rotation` per PyMuPDF docs is already normalized to one of
`{0, 90, 180, 270}`, so `page.rotation % 360` is a no-op. The seam elsewhere
explicitly casts to `int` defensively (`pdf_engine.py:72, 100, 138`); this line
breaks that convention. If a future PyMuPDF release returns a numpy scalar or a
float (it has happened with other PyMuPDF attributes between minor versions),
`insert_image(..., rotate=)` may receive an unexpected type silently.

**Fix:**

```python
return page.insert_image(
    rect,
    stream=stream,
    xref=xref,
    keep_proportion=True,
    overlay=True,
    rotate=int(page.rotation) % 360,  # match the explicit int() cast used elsewhere in the seam
)
```

### WR-03: Image ingest has no megapixel cap behind Pillow's DecompressionBomb guard

**Files:** `app/services/ingest.py:110-197` (`_ingest_image`),
`app/services/pdf_engine.py:574-600` (`image_to_a4_pdf`)

**Issue:** `_ingest_image` catches `Image.DecompressionBombError`, but Pillow's
threshold (`MAX_IMAGE_PIXELS`, ~89 MP default) only RAISES at `MAX_IMAGE_PIXELS *
2`; below that it just emits a warning and proceeds. A 60-megapixel TIFF passes
`verify()` and `load()`, then `image_to_a4_pdf` re-encodes it as PNG inside an A4
page (PyMuPDF does not downscale). The resulting PDF bytes can exceed
`MAX_UPLOAD_BYTES` after re-encode, but the upload-size gate already passed and
is not re-applied to the wrapped PDF. This is a soft DoS path: CPU + memory
spike per worker, not a security hole — but it sits next to a "checked
corrupt_image" branch, misleading future contributors into thinking the bomb
defence is complete.

**Fix:** After `img.load()` in `_ingest_image`, assert a pixel-count cap:

```python
# DoS defence: bound the wall-clock budget of re-encode + A4 wrap.
MAX_IMAGE_PIXELS_HARD = 25_000_000  # tune to match server CPU budget
if img.width * img.height > MAX_IMAGE_PIXELS_HARD:
    raise IngestError(
        "image_too_large_pixels",
        f"影像像素數過多(超過 {MAX_IMAGE_PIXELS_HARD:,} 像素),請先縮圖再上傳。",
    )
```

Or downscale before re-emit. If performance is explicitly out-of-scope for v1,
at minimum document the absence of a megapixel limit in the module docstring so
the next reader does not assume it is covered.

## Info

### IN-01: `_DEGENERATE_EPS = 0.01` duplicated in two functions; drift risk

**File:** `app/services/pdf_engine.py:494, 542`

**Issue:** Both `get_drawings_fully_inside` and `cover_zero_area_artefacts`
re-declare `_DEGENERATE_EPS = 0.01` as a local constant. If the threshold is
ever tuned, two edits are required, and a drift between them silently breaks
the invariant "the residual check and the cover routine see the SAME set of
zero-area drawings" — leading to either (a) Adobe hairlines surviving when the
residual check ignores a wider epsilon, or (b) `residual_content` false
positives when the cover routine ignores a wider one. Same applies to
`_COVER_PAD = 0.5` if a second consumer is ever added.

**Fix:** Promote to a module-level private constant near the redaction enum
re-exports (≈ line 230):

```python
# Zero-area drawing detection (Pitfall A — hotfix #3-5). 0.01 pt ≈ 0.0035 mm,
# below any visible feature, well above float noise. Shared by
# `get_drawings_fully_inside` and `cover_zero_area_artefacts` so they agree on
# what counts as zero-area — a divergence would split residual detection from
# cross-renderer artefact masking.
_DEGENERATE_BBOX_EPS = 0.01
```

### IN-02: `logos.js` accepts and stores `session_id` but never reads it

**File:** `web/js/logos.js:60, 200, 208`

**Issue:** `let sessionId = null;` (module scope) is assigned in `initLogos`
and cleared in `resetLogos` but never read by any function. The picker has no
session-scoped behaviour — `api.logoImageURL(id)` takes only the logo id, and
`api.listLogos()` takes no argument. Dead state misleads readers into believing
the picker is session-scoped.

**Fix:** Drop the parameter, the module variable, and the two assignments:

```js
// Remove:
// let sessionId = null;
// export function initLogos({ session_id } = {}) { sessionId = session_id ?? null; ... }
// export function resetLogos() { sessionId = null; ... }
```

Or, if per-session catalogs are coming, wire it through `api.listLogos(sessionId)`
now so the variable is actually consulted.

### IN-03: Magic index `rgba.split()[3]` and orphaned `Image.open` handle in alpha path

**File:** `app/services/ingest.py:174-178, 197`

**Issue:** Two small issues in the new alpha-composite path:

1. `rgba.split()[3]` works (because the previous line ensured `rgba.mode ==
   "RGBA"`), but the magic index is unobvious. Pillow's `getchannel("A")` is
   the documented idiom.
2. The `finally: img.close()` at line 197 closes the rebound `background` Image,
   not the second `Image.open(io.BytesIO(data))` handle from line 145. Pillow's
   `__del__` will clean it up, but the module's prior care (the docstring at
   137-138 explicitly notes "verify() invalidates the Image object") suggests
   the second open deserves the same explicit lifecycle.

**Fix:**

```python
if has_alpha:
    rgba = img.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    alpha = rgba.getchannel("A")  # named-channel access; same semantics, clearer intent
    background.paste(rgba, mask=alpha)
    img = background
```

And consider a `with Image.open(io.BytesIO(data)) as img2:` block around the
second open so its file handle is closed deterministically.

---

## Invariants Verified (Project Context Section)

| # | Invariant | Evidence | Status |
|---|-----------|----------|--------|
| 1 | AGPL seam — `import fitz` only in `pdf_engine.py` | `grep import fitz app/` → `pdf_engine.py:19` (sole match) | OK |
| 2 | XSS guard — no `innerHTML` in hotfix-touched JS | `logos.js` uses `createElement` + `textContent` only; `<img src="/assets/logo.png">` is static markup | OK |
| 3 | Path safety on `pristine_path` switch | `storage.pristine_path` uses validated `subdir("pristine", session_id)`; `_require_session` gates | OK |
| 4 | `originals/` immutability on read paths | `pages.py` now reads `pristine_path` exclusively; `originals/` touched only by ingest write (chmod 0o444) | OK |
| 5 | RGBA composite onto white before drop-alpha | `ingest.py:174-178` — composite-then-replace pattern, no premultiplied-alpha pitfall | OK |
| 6 | Zero-area filter is `type='f'` only; strokes preserved | `pdf_engine.py:507-508, 551-554` | OK |
| 7 | Physical cover runs AFTER residual assertion | `redact.py:156-171` — assertion (158) precedes `cover_zero_area_artefacts` (171); cover is clamped to user rect (no bleed) | OK |
| 8 | `PDF_REDACT_TEXT_NONE` defence-in-depth guard | `pdf_engine.py:289-292` | OK |
| 9 | `/assets/logo.png` reachable | `web/assets/logo.png` exists; `app/main.py:176` mounts `web/` at `/` via `StaticFiles(html=True)` | OK |

---

_Reviewed: 2026-05-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Scope: post-verification hotfix delta (137a592..HEAD), NOT the original Phase 4 implementation._
