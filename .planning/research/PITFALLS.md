# Pitfalls Research

**Domain:** Browser-based PDF logo replacement via manual region selection + PyMuPDF (fitz) "true removal" redaction
**Researched:** 2026-05-22
**Confidence:** HIGH (redaction options, coordinate system, licensing verified against official PyMuPDF docs + GitHub issues); MEDIUM on a few raster-fill details (training + corroborating discussions)

> Two pitfalls dominate everything else and decide whether this product works at all:
> **(A) coordinate mapping** between the browser preview and the PDF page, and
> **(B) redaction that visually covers but does not actually remove** the supplier content.
> A rectangle drawn in the browser that lands 30 pt off, or a logo that still extracts as text/copy-pastes out of the "cleaned" PDF, are both *silent* failures — the export looks fine but is wrong. Treat these as the project's core engineering risk, not afterthoughts.

---

## Critical Pitfalls

### Pitfall 1: Browser-pixel → PDF-point coordinate mismatch (the rectangle lands in the wrong place)

**What goes wrong:**
The user draws a rectangle over the supplier logo in the browser, but the redaction/logo lands offset, scaled wrong, or on the wrong part of the page. Common concrete failures:
- Off by the preview's zoom factor (drew at 1.5x preview scale, sent raw canvas pixels to the backend which treats them as PDF points).
- Off by `window.devicePixelRatio` on HiDPI screens (canvas backing store is 2x CSS pixels).
- Vertically flipped — region appears mirrored top-to-bottom on the page.

**Why it happens:**
Three coordinate systems are in play and they disagree:
- **Browser canvas:** origin **top-left**, +Y **down**, units = CSS pixels × devicePixelRatio, scaled by the preview zoom.
- **PDF native (the spec):** origin **bottom-left**, +Y **up**, units = points (1/72").
- **PyMuPDF fitz:** deliberately re-maps PDF coordinates so its `Point`/`Rect` use origin **top-left**, +Y **down** (verified: PyMuPDF docs, app3). This is a frequent surprise — fitz is NOT bottom-left like the raw PDF spec.

So fitz happens to share the *direction* of the browser, but NOT the *scale or zoom*. PDF.js, by contrast, exposes coordinates in bottom-left PDF space via `viewport.convertToPdfPoint()`. If you convert with PDF.js (→ bottom-left points) and then hand those numbers to fitz (→ expects top-left points), you get a vertical flip. If you skip PDF.js's converter and send raw canvas pixels, you get a zoom/DPR scale error.

**How to avoid:**
- Pick ONE canonical contract for the API: **send the rectangle in unscaled PDF points, top-left origin (fitz convention), relative to the unrotated page**, and document it. Convert on the front end.
- Compute the mapping explicitly from the render scale you used to rasterize the preview, do NOT trust the browser's CSS size:
  `pdf_x = (canvas_x / devicePixelRatio) / preview_scale` etc. Derive `preview_scale` from the exact `matrix`/`dpi` you passed to `get_pixmap()` (or PDF.js `getViewport({scale})`).
- If using PDF.js `convertToPdfPoint` (bottom-left), flip Y before sending to fitz: `fitz_y = page_height - pdfjs_y`, and swap y0/y1 so the fitz `Rect` stays normalized (`y0 < y1`).
- Build a visual round-trip test harness early: send a rectangle, have the backend draw that exact `fitz.Rect` as a colored box, render it back, and confirm pixel-for-pixel overlap with the user's selection in the browser. Do this before writing any real redaction code.

**Warning signs:**
- Redaction/logo offset grows when you zoom the preview in/out → scale bug.
- Offset only appears on Retina/4K laptops → devicePixelRatio bug.
- Region appears flipped top↔bottom → origin (bottom-left vs top-left) bug.
- "Works on page 1 but not page 2" where pages have different sizes → you hard-coded a page height/scale.

**Phase to address:**
Foundational. Build the coordinate-contract + round-trip test harness in the **preview & region-selection phase**, before any redaction logic depends on it.

---

### Pitfall 2: Page `.rotation` and non-(0,0) MediaBox break the mapping

**What goes wrong:**
On pages with `/Rotate 90/180/270` (extremely common in CAD/landscape exports) or whose MediaBox does not start at (0,0), the rectangle is correct on a 0°-page but wildly wrong on rotated/offset pages — rotated 90°, mirrored, or shifted by the MediaBox offset.

**Why it happens:**
- PyMuPDF methods operate on the **unrotated** page: "if you insert something you must use unrotated coordinates" (verified: PyMuPDF docs). The browser, however, shows the page **rotated** for display. So the user's on-screen rectangle is in *rotated/display* space while fitz wants *unrotated* space.
- PyMuPDF provides `page.rotation_matrix` and `page.derotation_matrix` exactly for this; skipping them is the bug.
- A MediaBox like `[10 10 600 800]` means page coordinates are offset — assuming the origin is (0,0) shifts everything by the offset.

**How to avoid:**
- Always read `page.rotation` and the page rect (`page.rect`, which already accounts for MediaBox). Map the browser selection to unrotated page space using `selection_rect * page.derotation_matrix` before building the redaction `Rect`.
- For logo insertion on rotated pages, use `insert_image(rect, rotate=...)` consistent with the page rotation, and pass unrotated `rect`.
- Do NOT assume MediaBox origin is (0,0). Use `page.rect`/`page.mediabox` and translate; never construct a `Rect` from absolute numbers that assume a (0,0) origin.
- Add at least one rotated landscape CAD PDF and one non-(0,0)-MediaBox PDF to the test corpus from day one.

**Warning signs:**
- Specific pages are off by exactly 90/180/270° → rotation not de-rotated.
- A consistent constant offset on all regions of one document → MediaBox origin ignored.
- Logos appear sideways/upside-down on some pages only.

**Phase to address:**
Same phase as Pitfall 1 (preview & region selection / coordinate plumbing). Rotation handling is part of the coordinate contract, not a later "polish" item.

---

### Pitfall 3: Redaction visually covers but does NOT remove — content still extractable

**What goes wrong:**
The exported PDF *looks* clean, but the supplier's logo text is still selectable/copy-pasteable, shows up in `page.get_text()` / search, or the logo image is still embedded and recoverable. This is the single most damaging failure: it defeats the entire "真正移除 (truly remove)" core value and can ship branded-wrong/legally-exposed PDFs that look correct.

**Why it happens:**
- Developers reach for the easy path: draw a white rectangle or insert an opaque image *over* the logo (`insert_image`, `draw_rect`, or an annotation) instead of using the redaction pipeline. That only *covers*. **You MUST call `page.apply_redactions()`** after `page.add_redact_annot()` — without `apply_redactions()`, the redact annotation is just a marker and content remains. (verified: PyMuPDF docs / issue #499, #434)
- Even with redaction: **double-layered text** (e.g., OCR text layer under a scanned image, or duplicated text) — one layer gets redacted, the hidden duplicate survives (verified: PyMuPDF discussion #1220).
- Text removal is **character-bbox-overlap based**: a glyph whose bbox only partly overlaps the rect may or may not be removed, and font line-height can cause neighbors to be deleted or kept unexpectedly (verified: PyMuPDF docs).
- Content inside **form XObjects** / nested content streams, and content gated by **optional-content groups (OCG/layers)** that are currently hidden, may not be reached as expected — redaction interacting with OCGs is a known rough edge (verified: discussions #4091, #1220).

**How to avoid:**
- Use the redaction pipeline, never a cover: `page.add_redact_annot(rect)` → `page.apply_redactions(...)`. Make "cover-only" code (a bare `draw_rect`/`insert_image` over content with no `apply_redactions`) forbidden by code review/lint note.
- After applying redactions, **verify** programmatically: run `page.get_text("text")` and `page.get_text("words")` clipped to the redacted rect and assert it is empty; assert no image xref still overlaps the rect. Surface a warning to the user if residual content is detected.
- For scanned/OCR'd PDFs, treat the page as raster (see Pitfall 5) — redact image pixels, and also redact any hidden text layer in the same rect.
- Be aware of `text=PDF_REDACT_TEXT_NONE` — it *keeps* text and explicitly "does NOT comply with data-protection intentions" (verified: docs). Never use it for this product; rely on the default `PDF_REDACT_TEXT_REMOVE`.
- Pad text-redaction rects slightly so partially-overlapping glyphs of the logo wordmark are fully caught; consider `Tools.set_small_glyph_heights(True)` to tighten glyph boxes and avoid clobbering neighbors (verified: docs).

**Warning signs:**
- In the exported PDF you can Ctrl+A / Ctrl+C and paste the supplier name out of a "redacted" area.
- `page.get_text()` over the region still returns the wordmark.
- `page.get_images()` count unchanged after redacting an image logo.
- File still searchable for the supplier name in a normal viewer.

**Phase to address:**
Core **vector redaction phase**. The post-redaction verification assertion should be a hard success criterion for that phase ("redacted region extracts zero text and references zero overlapping image").

---

### Pitfall 4: Vector graphics only partially inside the rect — stroked paths survive or over-delete

**What goes wrong:**
The supplier logo is line-art (vector paths). After redaction, either part of it remains (a stroke that crossed the rect boundary survives), or far MORE than intended disappears (a big path that merely *touches* the rect gets wholly removed, deleting wanted CAD geometry).

**Why it happens:**
- `apply_redactions(graphics=...)` defaults to `PDF_REDACT_LINE_ART_REMOVE_IF_COVERED` (removes vector graphics overlapping the rect). The alternative `REMOVE_IF_TOUCHED` removes graphics *fully contained* — choosing wrong gives either survivors or collateral deletion (verified: PyMuPDF docs).
- **Stroked paths have wrapping rectangles larger than the visible line**: per docs you must add (line width × 1.5) per direction, and with the default miter limit of 10 the redaction rect should be **at least ~5 points larger in every direction** to fully catch a stroke. Drawing the rect exactly on the visible logo edges leaves slivers (verified: PyMuPDF docs).
- CAD drawings are a single huge path soup; an over-eager `REMOVE_IF_TOUCHED` on a tight rect can still nuke a shared path object that extends beyond the logo.

**How to avoid:**
- Default to `graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED` and pad the user's rect by ~5 pt before redaction to catch stroke wrappers.
- Render a before/after preview of the redacted region so the user can SEE survivors or over-deletion and re-draw.
- For CAD files specifically, give the user a visible diff and an undo, because collateral deletion of wanted geometry is a real risk; do not silently apply.
- Test with a known line-art logo and assert the region is visually clean AND that `page.get_drawings()` no longer reports paths intersecting the (unpadded) logo area.

**Warning signs:**
- Thin outline/sliver of the logo remains after redaction.
- Adjacent CAD lines/dimensions vanish unexpectedly → touched-vs-covered mis-set or rect too large.
- `get_drawings()` still lists paths inside the region.

**Phase to address:**
Core **vector redaction phase**, alongside Pitfall 3. The before/after region preview belongs here (it also serves Pitfall 3 verification).

---

### Pitfall 5: Raster "fill" reality — PyMuPDF blanks to WHITE, not "surrounding background color"

**What goes wrong:**
The requirement says image regions should be filled "with white **or surrounding background color**." Teams assume PyMuPDF's image redaction samples the surrounding color — it does not. Default `images=PDF_REDACT_IMAGE_PIXELS` **blanks the overlapping pixels (effectively white/transparent), it does not sample neighbors** (verified: PyMuPDF docs / discussion #1819). On a colored or patterned background this leaves an obvious white box.

**Why it happens:**
- Misreading redaction as "smart fill." PyMuPDF redaction is removal + blank, not inpainting and not background-aware fill (which is exactly why the project already excluded AI inpainting — but "surrounding background color" still implies *sampling*, which is custom work).
- Other raster gotchas stacked on top:
  - **Uncompressed PNG bloat:** `PDF_REDACT_IMAGE_PIXELS` replaces the affected image with a new **uncompressed PNG**, ballooning file size unless you re-save with `deflate=True`/garbage collection (verified: docs, discussion #2644).
  - **Original image not deleted:** the original image object survives if referenced elsewhere — the supplier pixels can still exist in the file/other pages (verified: discussion #1819). A potential *content-leak*, related to Pitfall 3.
  - **Transparent images can segfault** during redaction (verified: issue #1824).
  - **CMYK / image masks / SMask:** cropping/replacing images with alpha or non-RGB colorspaces can return black or wrong colors (verified: discussion #1216).
  - **JPEG recompression artifacts** if you round-trip the page image through JPEG.

**How to avoid:**
- Decide the fill policy explicitly. For a clean white fill, the redaction `fill` color (white default) is fine for white backgrounds. For "surrounding background color," you must **custom-sample**: read a pixmap of a thin border just outside the rect, compute the median/mode color, then `apply_redactions` and `draw_rect(rect, fill=sampled_color, fill_opacity=1)` (or insert a solid filled rect) over the blanked area. PyMuPDF will not do this for you.
- Always re-save with `garbage=4, deflate=True, clean=True` to undo the uncompressed-PNG bloat.
- For full content removal of an image logo, prefer `images=PDF_REDACT_IMAGE_REMOVE` over PIXELS when the whole image is the logo, to avoid leaving the original referenced.
- Guard the transparent-image segfault: wrap redaction in try/except, and on failure fall back to (a) flatten the page to a pixmap, edit pixels, re-insert, or (b) `IMAGE_REMOVE`.
- Convert/normalize CMYK & SMask images to RGB before manipulation to avoid black-box results.

**Warning signs:**
- White rectangle on a colored/patterned background where the user expected blend.
- Output PDF much larger than input after redacting an image.
- Black box instead of fill (CMYK/SMask).
- Crash/segfault on certain logos (transparent PNG-backed images).

**Phase to address:**
**Raster/image-fill phase** (separate from vector). Background-color sampling is its own sub-feature; scope it explicitly or descope to white-only for v1 and say so.

---

### Pitfall 6: Image-based ("scanned") PDFs where the logo is just pixels

**What goes wrong:**
A PDF that *looks* like it has text/vector logos is actually a single full-page scanned image. Vector-style redaction (`get_text`, path removal) finds nothing to remove because there are no text/vector objects — only pixels. The team's vector code path "succeeds" but removes nothing.

**Why it happens:**
- Supplier "PDFs with CAD data" arrive in wildly different forms (the project explicitly lists vector PDF, image-type PDF, and standalone images). Detecting which kind you're holding is non-trivial and often skipped.
- A page can be *mostly* a big background scan with a thin OCR text layer on top (worst of both worlds — see double-layer in Pitfall 3).

**How to avoid:**
- Classify each page on load: inspect `page.get_text()` length, `page.get_images()`, and `page.get_drawings()` counts. Heuristic: little/no text + one page-sized image ⇒ treat as raster; rich text/paths ⇒ vector. Surface the detected mode in the UI.
- Route raster pages to the image-fill path (Pitfall 5) and vector pages to the redaction path (Pitfalls 3–4); for hybrids, run BOTH (redact pixels AND any text layer).
- Standalone PNG/JPG/TIFF uploads: wrap into a single-page PDF (or operate on the pixmap directly) so one pipeline handles all inputs; mind TIFF multi-page and CMYK TIFF.

**Warning signs:**
- "Redaction did nothing" on a file that visibly has a logo.
- `get_text()` returns empty but the page clearly shows words.
- One giant image per page in `get_images()`.

**Phase to address:**
**Input-classification phase** (early, right after upload/preview) so downstream phases know which engine to run.

---

### Pitfall 7: Logo insertion — scale/aspect, transparency, and colorspace

**What goes wrong:**
The company logo is pasted stretched/squashed, with a white box instead of transparency, blurry, or color-shifted; or it gets re-embedded once per placement bloating the file.

**Why it happens:**
- `insert_image(rect)` with `keep_proportion=True` (default) fits within the rect preserving aspect — but if the drawn rect's aspect ≠ logo aspect, the logo is centered and the rest of the rect is empty (looks like misalignment); if someone sets `keep_proportion=False` to "fill," it stretches (verified: docs).
- **PNG alpha:** transparency works only if you pass the alpha correctly — for a base image without an embedded mask you supply the alpha via the `mask` parameter; an opaque-flattened PNG paints a white background over the just-cleaned area (verified: docs).
- **CMYK logos / vector (SVG/PDF) logos:** `insert_image` is raster-oriented; rotation only supports multiples of 90°, and for a vector logo you should convert it to a 1-page PDF and use `show_pdf_page()` for crisp scaling (verified: docs). A raster logo upscaled into a large CAD page looks pixelated.
- Re-embedding the same logo image on every placement bloats the PDF; PyMuPDF can dedupe via the returned `xref`.

**How to avoid:**
- Keep `keep_proportion=True`; if the company brand requires exact fit, letterbox within the rect rather than stretch, and tell the user the logo is centered.
- Store library logos as transparent PNGs with correct alpha (and/or as 1-page PDFs for vector logos). Verify alpha renders over a colored test background, not just white.
- For vector company logos, prefer `show_pdf_page()` (vector→vector) over raster `insert_image` for resolution independence on big CAD pages.
- Reuse the returned image `xref` for repeated placements to avoid re-embedding.
- Normalize CMYK logos to RGB unless the output truly must be CMYK (print). Decide RGB-vs-CMYK output policy explicitly — mixing can shift brand colors.

**Warning signs:**
- White rectangle behind a logo that should be transparent.
- Stretched/distorted logo, or logo floating centered with empty margins.
- Pixelated logo on large/zoomed pages.
- File size grows linearly with number of logo placements.

**Phase to address:**
**Logo-insertion phase** (after redaction works). Transparency + vector-logo handling are the parts most likely to "look done but isn't."

---

### Pitfall 8: CAD-PDF scale — path explosion, OCG layers, embedded fonts, huge page sizes

**What goes wrong:**
A CAD-origin PDF with hundreds of thousands of vector paths makes preview rendering, `get_drawings()`, and redaction slow or memory-heavy; or the supplier logo lives on an optional-content **layer** that's currently hidden, so it's invisible in preview yet present in the file; or huge page sizes (e.g., E-size sheets, thousands of points) blow up rasterization memory.

**Why it happens:**
- CAD exports are pathological for any PDF library: enormous content streams, deeply nested form XObjects, many OCGs.
- Rasterizing a huge page at high DPI for preview is `width_pt × height_pt × (dpi/72)² × 4 bytes` — easily hundreds of MB per page pixmap.
- Redaction must rewrite/repaginate large content streams, which is CPU-bound.

**How to avoid:**
- Render preview pixmaps at a **capped DPI / max pixel budget**, not full resolution; downscale large pages and let the user zoom via re-render of a sub-rect rather than one giant bitmap.
- Detect and surface OCG layers (`doc.layer_ui_configs()` / OCG APIs); warn that hidden layers exist and may contain logos. Decide policy: redact across all layers or only visible ones.
- Set explicit memory/time limits per request; reject or queue files above a size/path-count threshold rather than OOM-killing the server.
- Test with a real large CAD PDF early to get true timing/memory numbers; do not size the server on small samples.

**Warning signs:**
- Preview takes many seconds or the worker OOMs on certain files.
- A logo visible in Acrobat is absent in your preview (it's on a hidden layer).
- `len(page.get_drawings())` in the tens/hundreds of thousands.
- Page dimensions far larger than A4/Letter.

**Phase to address:**
**Performance/robustness phase** for the DPI cap + limits; OCG detection belongs with input-classification (Pitfall 6). Get one real CAD sample into the corpus during the redaction phase to surface this early.

---

### Pitfall 9: Original-file preservation done unsafely

**What goes wrong:**
The "original must be preserved" requirement is violated: `doc.save()` over the same path, or `saveIncr()`/incremental save mutates the uploaded original; or a crash mid-process leaves a half-written file where the original was.

**Why it happens:**
- PyMuPDF `Document.save()` to the same filename, or incremental save, edits in place. Easy to do by habit.
- Working directly on the uploaded file object instead of a copy.

**How to avoid:**
- Treat the uploaded original as **read-only**: copy to a working file (or open from bytes and always `save()` to a NEW path). Never save back onto the upload.
- Save outputs with `garbage=4, deflate=True, clean=True` to a distinct output path; keep the original untouched.
- Add a post-run assertion/checksum that the original file's hash is unchanged.

**Warning signs:**
- Re-downloading the "original" yields the edited version.
- Original file timestamp/size changed after a run.

**Phase to address:**
**Core processing phase** (file I/O contract). Cheap to get right early, expensive to discover late.

---

### Pitfall 10: PyMuPDF AGPL licensing for a tool destined to be embedded in a web service

**What goes wrong:**
PyMuPDF is **AGPL-3.0** (or paid Artifex commercial license). v1 internal CLI/standalone use is generally fine, but the stated future ("掛入同事開發的表單簽核網站" — embed into a form-approval **website**) is exactly the scenario AGPL targets: AGPL's network clause requires offering corresponding source to users who interact with the software over a network. Discovering this after coupling PyMuPDF into a shared web app is an expensive surprise.

**Why it happens:**
- "It's internal, so license doesn't matter" — true-ish for AGPL *internal* use, but AGPL §13 is triggered by *network interaction by users*, and an internal web service still has users interacting over the network. Whether internal-only deployment obligates source disclosure is a genuine legal nuance, not a coding decision (verified: Artifex licensing page + PyMuPDF discussion #971 — internal use is "generally OK" but distribution / SaaS-style interaction is the trigger; this is a legal call, not a code call).

**How to avoid:**
- Flag the license question to whoever owns legal/procurement **now**, before architecture couples tightly to fitz. Document the decision (AGPL-compliant internal deployment vs. buy Artifex commercial license).
- Architecturally isolate PDF processing behind a clean service boundary/API so PyMuPDF could be swapped (e.g., for a commercial license or an alternative engine) without rewriting the app — this also de-risks the future website integration.
- If a closed-source distribution or external-facing service is ever likely, price the Artifex commercial license into the plan early.

**Warning signs:**
- Plans to share/distribute the tool, expose it externally, or bundle it into a product without a license decision on file.
- Legal asks "what's the license?" and nobody knows.

**Phase to address:**
**Phase 0 / planning** (decision + documentation) and the **architecture phase** (isolate fitz behind a boundary). Cheap now, very expensive after deep coupling.

---

### Pitfall 11: Uploaded-file security & temp-file lifecycle (no auth in v1 ≠ no risk)

**What goes wrong:**
v1 is internal and unauthenticated, so security gets skipped — but accepting arbitrary uploaded PDFs/images and running a C-backed parser (MuPDF) on them is an attack surface: malformed/malicious PDFs can crash or exploit the parser; temp files accumulate or leak other users' documents (no auth means anyone on the LAN can hit it); path-traversal via filenames.

**Why it happens:**
- "Internal/no-login" is misread as "no security needed."
- PyMuPDF/MuPDF parses untrusted binary input in C; CVEs and crashes on crafted files are a real category.
- Temp files written for preview/processing are forgotten, never cleaned, or world-readable.

**How to avoid:**
- Run PDF processing in an isolated, resource-limited worker (subprocess/container, CPU+memory+time limits, restricted filesystem) so a crash or exploit can't take down or pivot from the web server.
- Validate inputs: enforce max file size, sniff/verify type (don't trust extension), reject non-PDF/PNG/JPG/TIFF; sanitize/replace filenames (never use the client filename as a path).
- Generate temp paths with `tempfile`/random names in a per-job directory; **delete on completion AND on error** (try/finally), and run a janitor to purge stale jobs. Don't let one user's uploaded design linger where the next can fetch it.
- Keep PyMuPDF updated for security fixes; pin and track CVEs.

**Warning signs:**
- `/tmp` (or upload dir) growing without bound.
- One user can guess/download another's file by predictable URL/path.
- Worker crashes bring down the web process.

**Phase to address:**
**Infrastructure/processing phase.** Even in v1, the isolated-worker + temp-cleanup pattern should be in place; full auth is correctly deferred, but file hygiene and parser isolation are not optional.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Cover logo with a white rect / opaque image instead of `apply_redactions()` | Trivial to code, looks identical | Content NOT removed — defeats core value, ships extractable supplier data | **Never** for this product |
| Send raw canvas pixels to backend, "fix the scale later" | Front end ships faster | Every region is wrong at non-1x zoom/HiDPI; silent until a user notices | Never — the coordinate contract is foundational |
| White-fill only for raster (skip background sampling) | Avoids sampling code | White boxes on colored backgrounds; may not meet "surrounding background color" | OK for v1 **if explicitly descoped & stated**; revisit later |
| Single shared engine, no fitz isolation boundary | Less plumbing | AGPL coupling + can't swap engine for the future website integration | Acceptable only if license decision says AGPL is fine forever |
| Process in the web request thread, no worker isolation | Simplest deploy | One malformed PDF OOMs/crashes the server for everyone | Never beyond a throwaway prototype |
| Skip rotation/MediaBox handling ("our files are all portrait, origin 0,0") | Less math | Breaks the day a landscape/rotated/offset CAD PDF arrives — and it will | Never; CAD exports rotate constantly |
| No post-redaction verification assertion | Less code | Silent partial-removal failures reach users | Never for the core removal feature |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Browser PDF renderer (PDF.js) → fitz | Pass PDF.js bottom-left points straight to fitz (top-left) → vertical flip | Convert + flip Y (`page_h - y`), normalize Rect, send unscaled top-left points per a documented contract |
| Preview rasterization (`get_pixmap` / `getViewport`) → selection scale | Use CSS element size as the scale | Derive scale from the exact `matrix`/`dpi`/`scale` used to render; account for `devicePixelRatio` |
| `apply_redactions()` images param | Leave default and assume original image is gone | Default `IMAGE_PIXELS` leaves uncompressed PNG + original referenced elsewhere; use `IMAGE_REMOVE` for full-image logos; re-save with garbage collection |
| `apply_redactions()` graphics param | Leave default tightly on logo edges | Pad rect ~5pt for stroke wrappers; pick COVERED vs TOUCHED deliberately |
| Future form-approval website + PyMuPDF | Embed fitz directly into the shared web app | Isolate behind a service API; settle AGPL/commercial license first |
| Standalone PNG/JPG/TIFF input | Build a separate code path | Wrap into a 1-page PDF (or operate on pixmap) so one pipeline serves all inputs |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-resolution preview of huge CAD pages | Multi-second renders, worker OOM | Cap DPI / max-pixel budget; zoom by re-rendering sub-rects | Large/E-size sheets or DPI >150 on big pages |
| `get_drawings()` / redaction on path-explosion CAD files | High CPU, slow apply | Time/memory limits per job; queue or reject oversized files | Hundreds of thousands of paths |
| Uncompressed-PNG bloat after image redaction | Output PDF far larger than input | Save with `garbage=4, deflate=True, clean=True` | Any image-overlapping redaction with default `IMAGE_PIXELS` |
| Re-embedding company logo per placement | File grows per logo dropped | Reuse returned image `xref` / store logo once | Many regions across many pages |
| Processing in request thread | Server stalls/crashes under concurrent or malformed uploads | Isolated resource-limited worker, concurrency cap | First big file or malicious upload under load |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| "Internal/no-auth ⇒ no security" | Anyone on LAN uploads/downloads others' designs; crafted PDF exploits parser | Isolated resource-limited worker; input validation; per-job dirs; treat as untrusted even internally |
| Running MuPDF on untrusted PDFs in-process | Parser crash/exploit takes down or pivots from web server | Subprocess/container sandbox with CPU/mem/time/fs limits; keep PyMuPDF patched |
| Trusting client filename as a path | Path traversal / overwrite | Generate random server-side names; never use client filename for filesystem paths |
| Temp files not cleaned / world-readable | Confidential supplier designs linger and leak | `tempfile` random per-job dir; delete on success AND error (try/finally); janitor for stale jobs |
| Leaving original image referenced after redaction | Supplier pixels recoverable from "cleaned" file | `IMAGE_REMOVE` for full-image logos; verify no overlapping image xref remains; re-save with garbage collection |
| Shipping extractable text under a visual cover | Confidential/branding leak; legal exposure | Mandatory `apply_redactions()` + post-redaction text/image extraction assertion |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No before/after preview of the redacted region | User can't see survivors, over-deletion, or white-box fill until after export | Show in-app before/after of the affected region; allow re-draw/undo |
| No indication of detected mode (vector vs raster vs hidden layers) | User expects removal where there's nothing to remove, or misses a hidden-layer logo | Surface detected page type + warn about OCG layers |
| Logo silently centered/letterboxed in a mismatched rect | Looks misaligned/"broken" | Explain proportion behavior; show the placement preview before commit |
| Offset only visible after download | User trusts a wrong export | Real-time on-canvas overlay of where the region maps on the page, validated by round-trip harness |
| One giant zoom bitmap, laggy pan | Frustrating on big CAD pages | Tiled/sub-rect re-render, capped DPI |

## "Looks Done But Isn't" Checklist

- [ ] **Redaction:** Looks covered — verify `page.get_text()` and `get_words()` clipped to the region return EMPTY, and no image xref overlaps the region (true removal, not cover).
- [ ] **Coordinate mapping:** Works at 1x — verify at multiple zoom levels, on a HiDPI display, on rotated (`/Rotate 90/270`) pages, and on a non-(0,0) MediaBox page.
- [ ] **Vector strokes:** Region looks clean — verify no sliver remains (rect padded ~5pt) and that wanted neighboring CAD geometry was NOT deleted.
- [ ] **Raster fill:** Filled — verify the fill policy (white vs sampled background) matches expectation on a COLORED background, not just a white one.
- [ ] **Image redaction:** Pixels blanked — verify output file size didn't balloon (garbage collection applied) and the original image isn't still referenced elsewhere.
- [ ] **Logo transparency:** Looks fine on white — verify alpha over a COLORED background (no white box); verify vector logo stays crisp when scaled up.
- [ ] **Scanned/image PDF:** Vector path "succeeded" — verify it actually removed pixels (not a no-op because there were no text/vector objects).
- [ ] **Hidden layers:** Preview looks clean — verify there are no OCG layers hiding an un-redacted supplier logo.
- [ ] **Original preserved:** Output produced — verify the uploaded original's checksum/size is unchanged.
- [ ] **Temp cleanup:** Job done — verify temp files are deleted on both success and error paths.
- [ ] **License:** v1 ships — verify the AGPL/commercial decision is documented before any website-embedding work begins.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cover-only (no `apply_redactions`) shipped | MEDIUM | Swap to redaction pipeline + add extraction assertion; re-process affected files; notify if any leaked externally |
| Coordinate mapping wrong | LOW–MEDIUM if caught by round-trip harness early; HIGH if discovered in production | Build/repair the round-trip test harness; centralize all conversions in one tested module |
| Rotation/MediaBox ignored | LOW–MEDIUM | Route all selections through `derotation_matrix` and `page.rect`; add rotated + offset test files |
| White-box on colored background | MEDIUM | Add border-sampling fill step after `apply_redactions`; or accept + document white-only for v1 |
| Uncompressed-PNG bloat | LOW | Re-save with `garbage=4, deflate=True, clean=True` |
| AGPL coupling discovered late | HIGH | Buy Artifex commercial license, or refactor fitz behind a swappable service boundary |
| Parser crash from malicious/malformed file took down server | MEDIUM | Move processing to isolated resource-limited worker; add input validation; patch PyMuPDF |
| Transparent-image redaction segfault | LOW–MEDIUM | try/except around redaction; fall back to flatten-page-to-pixmap or `IMAGE_REMOVE` |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Browser↔PDF coordinate mismatch | Preview & region-selection (foundational) | Round-trip harness: backend-drawn rect overlaps user selection pixel-for-pixel at multiple zooms + HiDPI |
| 2. Rotation / non-(0,0) MediaBox | Preview & region-selection | Correct placement on `/Rotate 90/180/270` and offset-MediaBox test PDFs |
| 3. Cover-not-remove (extractable content) | Vector redaction (core) | `get_text`/`get_words` over region empty; no overlapping image xref; file not searchable for supplier name |
| 4. Partial vector / stroke survivors / over-delete | Vector redaction (core) | No visible sliver (rect padded ~5pt); `get_drawings()` clear in region; neighbors intact |
| 5. Raster fill (white vs background; bloat; leaks; segfault) | Raster/image-fill | Fill matches policy on colored bg; size not ballooned; original image not referenced; no crash on transparent images |
| 6. Scanned/image-PDF detection | Input-classification (early) | Detected mode shown; raster page actually has pixels removed (not a no-op) |
| 7. Logo scale/aspect/alpha/colorspace | Logo-insertion | Alpha correct over colored bg; vector logo crisp scaled up; no per-placement bloat |
| 8. CAD scale / OCG / huge pages | Performance/robustness (+ OCG in input-classification) | Capped-DPI preview within memory budget on a real large CAD file; hidden layers surfaced |
| 9. Original-file preservation | Core processing (file I/O) | Original checksum unchanged after a run |
| 10. AGPL licensing | Phase 0 planning + architecture | License decision documented; fitz isolated behind a swappable boundary |
| 11. Upload security & temp lifecycle | Infrastructure/processing | Isolated worker with limits; temp files purged on success+error; random server-side filenames |

## Sources

- PyMuPDF official docs — `Page.apply_redactions()` / `add_redact_annot()` / `insert_image()` parameters, image/graphics/text enum values and defaults, stroke-wrapper ~5pt warning, uncompressed-PNG note: https://pymupdf.readthedocs.io/en/latest/page.html (HIGH)
- PyMuPDF official docs — Appendix 3, coordinate systems: top-left origin, methods use unrotated coordinates, `rotation_matrix`/`derotation_matrix`/`transformation_matrix`: https://pymupdf.readthedocs.io/en/latest/app3.html (HIGH)
- PyMuPDF coordinate-system discussion #1806 / "determine coordinate plane" #3386 / rotated insertion #3366: https://github.com/pymupdf/PyMuPDF/discussions/1806 (MEDIUM–HIGH)
- PyMuPDF redaction issues/discussions — must call `apply_redactions` (#499, #434), redacting outside annotations / partial-rect surprises (#3444, #3376), double-layered text not redacted (#1220), OCG+redaction challenges (#4091): https://github.com/pymupdf/PyMuPDF/discussions/3444 ; https://github.com/pymupdf/PyMuPDF/discussions/1220 (MEDIUM–HIGH)
- PyMuPDF image-redaction details — `IMAGE_PIXELS` creates uncompressed PNG, original not deleted (#1819), file-size increase (#2644), transparent-image segfault (#1824), cropped image returns black / colorspace (#1216): https://github.com/pymupdf/PyMuPDF/discussions/1819 (MEDIUM)
- PyMuPDF Optional Content (OCG/layers) recipes: https://pymupdf.readthedocs.io/en/latest/recipes-optional-content.html (HIGH)
- PyMuPDF licensing — AGPL-3.0 vs Artifex commercial; internal use vs network/distribution trigger: Artifex licensing https://artifex.com/licensing ; PyMuPDF discussion #971 https://github.com/pymupdf/PyMuPDF/discussions/971 ; PyPI https://pypi.org/project/PyMuPDF/ (MEDIUM–HIGH; legal nuance, confirm with counsel)
- PDF.js coordinate conversion — `convertToPdfPoint`/`convertToViewportPoint`/`convertToViewportRectangle`, canvas top-left vs PDF bottom-left, devicePixelRatio for HiDPI: PDF.js `PageViewport` API + issues #6471, #12003: https://github.com/mozilla/pdf.js/issues/6471 (MEDIUM–HIGH)
- General: AGPL §13 network clause (well-established licensing knowledge); MuPDF/PyMuPDF parsing untrusted input as an attack surface (training knowledge / general security practice) (MEDIUM)

---
*Pitfalls research for: browser-based PyMuPDF logo-replacement / true-removal redaction*
*Researched: 2026-05-22*
