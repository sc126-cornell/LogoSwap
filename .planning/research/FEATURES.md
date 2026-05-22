# Feature Research

**Domain:** Internal web tool for PDF/image re-branding — "true removal" of supplier logo/text + placement of own logo (PyMuPDF backend)
**Researched:** 2026-05-22
**Confidence:** HIGH (core PyMuPDF removal/fill/insert capabilities verified against official docs and issue tracker; frontend rectangle-selection patterns verified via PDF.js/react-pdf sources)

## Feature Landscape

This is a niche tool, not a general PDF editor. The "competitive" reference points are: PDF redaction tools (Adobe Acrobat Redact, PDF24, pdf-redact-tools), PDF annotation/markup tools (PDF.js Express, Bluebeam), and re-branding/watermark scripts. The feature bar is set by what makes a *manual, single-file, true-removal* workflow usable end-to-end. Categorization below is tuned to **this tool's stated v1 scope**, not to general PDF editors.

### Table Stakes (Users Expect These)

Features the tool is *unusable* without. Each maps to an Active requirement in PROJECT.md.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Multi-format upload (vector PDF, raster PDF, standalone PNG/JPG/TIFF)** | Source files are heterogeneous (CAD vector PDFs, scanned/raster PDFs, loose images). Tool is useless if it rejects a common input. | MEDIUM | PyMuPDF opens all listed image formats as Pixmap and PDFs natively. Standalone images must be normalized to a 1-page PDF on ingest (`fitz.open()` → new page sized to image → `insert_image`, or `Pixmap`-based convert). Validate type + size server-side. |
| **Browser preview with multi-page navigation** | Users must see the document and find the logo before acting. Without preview there is nothing to draw on. | MEDIUM | Render pages to images server-side (PyMuPDF `get_pixmap`, ~150 DPI) and display, OR render client-side with PDF.js/react-pdf. Server-render is simpler and avoids shipping the raw vector PDF to the browser. Need page thumbnails or prev/next + page count. |
| **Draw one or more rectangular regions per page (multi-region, cross-page)** | This is the core interaction — manual selection replaces auto-detection (a deliberate Key Decision). Must support several logos per page and across pages. | HIGH | No turnkey "draw rectangle" exists in core PDF.js; it is a known DIY overlay pattern (mouse-down/move/up → SVG/canvas rect over the page layer). Must track regions per page, allow add/move/resize/delete, and **map screen pixel coords → PDF point coords** (the highest-bug-risk piece — zoom/DPI/rotation must be handled). |
| **True vector/text removal inside region (not cover-up)** | The Core Value. Covering with a white box still leaves the supplier text/vector underneath (extractable, visible in other viewers). | MEDIUM | Verified: `page.add_redact_annot(rect)` + `page.apply_redactions(text=PDF_REDACT_TEXT_REMOVE, graphics=PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)` truly removes overlapping text glyphs and line-art objects. This is exactly the mechanism PROJECT.md banks on. |
| **Raster fill of region (white or background color)** | For raster/image content there are no vector objects to delete; the region must be painted over. Explicitly chosen over inpainting. | LOW–MEDIUM | Verified: redaction supports `fill=(1,1,1)` (white) on the annotation; `apply_redactions(images=PDF_REDACT_IMAGE_PIXELS)` whitens the covered image area in place. White is trivial; "surrounding background color" requires sampling (see differentiators). |
| **Managed company-logo library: list + select** | Logo set is fixed and company-owned; PROJECT.md specifies a pre-stored library so users just pick. Selecting a logo is required before placement. | LOW | v1 can be a server folder of approved logos + a metadata list (name, file, optional transparent PNG). UI = thumbnail picker. "Add/remove logos" is a softer requirement (see differentiators / admin). |
| **Place selected logo into region with scaling + aspect-ratio preservation** | The other half of Core Value: put *our* mark where theirs was, without distortion. | MEDIUM | Verified: `page.insert_image(rect, ...)` scales the image into the rect, **preserves aspect ratio**, and centers it (covers at least one dimension fully). Use transparent PNG so logo doesn't paint an opaque box over kept content. Positioning = the user's drawn rect by default. |
| **Export/download result PDF; original preserved** | Output is the whole point; and the source-of-truth supplier file must never be mutated. | LOW | Work on a copy: load original → operate in memory → `doc.save(new_path)` (or `save(..., garbage=4, deflate=True)`). Never overwrite the uploaded file. Offer download of the new PDF. |

### Differentiators (Competitive Advantage / UX Wins)

Not strictly required for a barely-working tool, but they make *this* tool reliable and pleasant given its tricky "true removal on CAD vector + raster" problem. Several are cheap and high-leverage.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Before/after preview of each processed region (re-render after redaction)** | Redaction is lossy and can over-remove (catches overlapping images/icons) or under-remove (logo defined via clipping mask / embedded image survives). Showing the result *before* download catches both failure modes — turns a "trust me" tool into a verifiable one. | MEDIUM | Re-render the affected page region with `get_pixmap` after apply and show old-vs-new. Directly mitigates the #1 verified pitfall. Strong recommendation to include in v1. |
| **Background-color sampling for raster fill (match surrounding color, not just white)** | White boxes on a colored/patterned background look like obvious censorship. Sampling the adjacent pixels and filling with that color produces a cleaner, more "outward-usable" result — aligns with PROJECT.md's "可對外使用" goal. | MEDIUM | Sample a ring of pixels just outside the rect (PyMuPDF pixmap pixel access), take median/mode, fill the redaction with that color. Not full inpainting (correctly out of scope) — just a flat matched color. Offer "white / sampled / pick color" choice. |
| **Per-region removal mode control (text-only / vector / image / all)** | CAD vector PDFs mix text, line-art, hatches, and embedded raster in one region. A single global mode over-removes (deletes the whole drawing) or leaves residue. Letting the user say "remove text here, fill image there" is the difference between a clean result and a ruined CAD drawing. | MEDIUM | Expose the `apply_redactions` flags per region: `PDF_REDACT_LINE_ART_NONE / REMOVE_IF_TOUCHED / REMOVE_IF_COVERED`, `PDF_REDACT_TEXT_REMOVE/NONE`, `PDF_REDACT_IMAGE_NONE/PIXELS/REMOVE`. Default to a sensible "remove text + line-art-if-covered" and let advanced users override. High value for the stated CAD use case. |
| **Undo/redo of region + edit actions** | Manual drawing is error-prone (mis-drawn boxes, wrong logo). Undo/redo makes the manual workflow forgiving and fast, raising trust in a destructive operation. | MEDIUM | Implement as a client-side action stack *before* the irreversible export step (regions are just data until "Process"). Cheap if regions/logo-assignments are kept as an editable model and PDF mutation happens only at export. Note: PyMuPDF redaction itself is not undoable mid-document — hence keep edits in the model, apply once. |
| **Logo placement fine-tuning (manual scale %, alignment, padding/margin within region)** | Auto-fit-to-rect centers and preserves ratio, but users often want the logo slightly smaller with margin, or aligned to a corner. Small control = professional-looking output. | LOW–MEDIUM | Built on top of the table-stakes placement. Compute a sub-rect of the drawn region from scale% + alignment, pass to `insert_image`. Optional opacity/rotation are further nice-to-haves. |
| **Snap-to-detected-object / show text & vector boxes as guides** | Showing the bounding boxes of text spans and drawings (from `get_text("dict")` / `get_drawings()`) helps users draw tight, accurate rectangles around the logo without guessing — reduces over/under-removal at the source. | MEDIUM–HIGH | Overlay detected boxes from PyMuPDF as visual guides (not auto-selection — that's an anti-feature). Useful but heavier; reasonable to defer to v1.x. |
| **Add/remove logos in the library (lightweight admin)** | PROJECT.md lists "add" loosely; an upload form for new approved logos avoids a developer redeploy each time branding changes. | LOW | A simple authenticated-by-network upload page or even a watched folder. Keep minimal; full admin/permissions is out of scope. |
| **Multi-region batch within a single file ("apply all", page list of pending regions)** | Re-branding a multi-page CAD set means many regions; a manage-and-apply-all panel beats one-at-a-time. Note: this is single-file multi-region, NOT cross-file batch (which is out of scope). | LOW–MEDIUM | Just UX over the region model; collect all regions, apply per page in one pass. Clarify naming so it isn't confused with the out-of-scope multi-file batch. |

### Anti-Features (Deliberately NOT in v1)

Each is either an explicit Out-of-Scope item in PROJECT.md or a tempting addition that contradicts the project's chosen tradeoffs.

| Feature | Why Requested | Why Problematic (for v1) | Alternative |
|---------|---------------|--------------------------|-------------|
| **AI inpainting / background reconstruction of raster regions** | Looks "magic"; perfectly hides removal on textured backgrounds. | Heavy deps (model weights / GPU on an internal Ubuntu box), unpredictable artifacts, latency, and explicitly excluded in PROJECT.md ("移除後填白/底色即可,不還原被蓋住的內容"). | White fill or **sampled flat background color** (differentiator). Good-enough and deterministic. |
| **Automatic logo/text detection (image matching / OCR to find the supplier mark)** | Saves the user from drawing boxes. | Supplier logos vary wildly; detection is unreliable, and a wrong auto-removal silently damages the file. PROJECT.md Key Decision explicitly chooses manual selection as more reliable. | Manual rectangle drawing + optional **object-box guides** (differentiator) to assist, not decide. |
| **Multi-file / folder batch processing** | Re-branding many supplier files at once. | v1 is an interactive single-file workflow; batch needs job queue, async, progress, and a non-interactive removal strategy — large surface, and explicitly deferred. | Single-file now; design the processing core as a pure function so v2 batch can reuse it. |
| **User accounts / login / permissions / audit** | Governance, "who changed what". | Internal-network-only, v1 explicitly免登入 to cut complexity. Adding auth now front-loads cost with no v1 value. | Network-level access control; design so auth can wrap the app later (future "嵌入簽核網站"). |
| **Embedding into the existing form-approval website** | Eventual integration goal. | Coupling v1 to another team's app blocks standalone delivery. PROJECT.md keeps v1 standalone, integration deferred. | Build standalone but keep the core as a callable service/API surface for later embedding. |
| **General-purpose PDF editing (reflow text, edit fonts, rearrange pages, fill forms, e-sign)** | "While we're in here, let me also…" scope creep toward a full editor. | Massive surface, distracts from the single Core Value, and PyMuPDF text *editing* (vs removal) is fiddly. | Stay a focused redaction+rebrand tool. Out-of-band edits happen in real PDF editors. |
| **Full annotation suite (highlights, comments, freehand, stamps beyond the company logo)** | Looks like expected "PDF tool" features. | Not aligned to Core Value; adds UI and persistence complexity. | Only the rectangle-region primitive needed for removal/placement. |
| **Live raster repaint / pixel-level brush eraser** | Fine manual cleanup of stubborn raster marks. | Turns the tool into an image editor; redaction-rect fill covers the stated need. | Region fill (white/sampled). If a region is too coarse, draw multiple smaller regions. |

## Feature Dependencies

```
Multi-format upload (incl. image→1-page PDF normalize)
    └──requires──> (nothing; entry point)
            │
            ▼
Browser preview + multi-page navigation
    └──requires──> Upload + server/client page render
            │
            ▼
Draw rectangular region(s) per page  ◄── coordinate mapping (screen px ↔ PDF pt) is the load-bearing sub-feature
    └──requires──> Preview (must see page to draw on it)
            │
            ├─────────────────────────────┐
            ▼                             ▼
True vector/text removal          Raster fill of region
(apply_redactions: text+line-art) (apply_redactions: fill color)
    └──requires──> Region(s)          └──requires──> Region(s)
            │                             │
            │                             └──enhanced by──> Background-color sampling
            │                             └──enhanced by──> Per-region removal-mode control
            │
            ▼
Logo placement (insert_image into region, aspect-preserved)
    └──requires──> Region(s) + Logo library (list+select)
    └──enhanced by──> Placement fine-tuning (scale/align/margin)
            │
            ▼
Export / download new PDF (original preserved)
    └──requires──> all edits applied to an in-memory copy

Before/after preview ──enhances──> removal + fill + placement (re-render after apply)
Undo/redo ──enhances──> region drawing + logo assignment (operates on the pre-export edit model)
Snap-to-object guides ──enhances──> region drawing (uses get_text/get_drawings boxes)
Add/remove logos (admin) ──enhances──> Logo library

AI inpainting ──conflicts──> Raster fill (chosen approach); do not build
Auto-detection ──conflicts──> Manual region drawing (chosen approach); do not build
```

### Dependency Notes

- **Region drawing requires preview:** users can only draw where they can see; preview is the prerequisite UI surface.
- **Removal AND fill both require regions:** nothing can be removed/filled until at least one rectangle exists — region selection is the universal upstream feature. Roadmap must sequence region selection before any removal/placement work.
- **Coordinate mapping is a hidden hard dependency of everything downstream:** the screen-pixel → PDF-point transform (accounting for render DPI, zoom, and page rotation) must be correct, or every removal/placement lands in the wrong spot. Treat it as its own deliverable, not an afterthought of "draw rectangle."
- **Logo placement requires the logo library:** you cannot place what you cannot select; library list+select must land with or before placement.
- **Export depends on edits being applied to a copy:** original-preservation is a constraint on *how* every mutating feature is implemented (operate on a loaded copy, save to a new path), not a standalone late feature.
- **Undo/redo and before/after preview hinge on a deferred-mutation model:** if regions/logo-assignments are kept as editable data and the PDF is only mutated once at "Process/Export," undo/redo is cheap and before/after is natural. If you mutate eagerly, both become hard (PyMuPDF redaction is not reversible mid-document). This architectural choice should be made early.
- **AI inpainting conflicts with raster fill; auto-detection conflicts with manual drawing:** these are not just "later" — they replace chosen approaches and would undermine the project's reliability rationale. Keep out.

## MVP Definition

### Launch With (v1) — maps 1:1 to PROJECT.md Active requirements

- [ ] **Multi-format upload** (vector PDF, raster PDF, PNG/JPG/TIFF) — entry point; images normalized to a 1-page PDF.
- [ ] **Browser preview + multi-page navigation** — required to locate logos and draw.
- [ ] **Draw one or more rectangular regions per page (cross-page)** + correct **screen↔PDF coordinate mapping** — the core interaction.
- [ ] **True vector/text removal in region** (`apply_redactions`) — the Core Value.
- [ ] **Raster fill in region** (white at minimum) — required for image/raster content.
- [ ] **Logo library: list + select** — required before placement.
- [ ] **Logo placement into region, aspect-preserved** — second half of Core Value.
- [ ] **Export/download new PDF; original preserved** — the deliverable + a hard constraint.
- [ ] **(Strongly recommended) Before/after preview** — cheap insurance against the verified over/under-removal pitfall; arguably promote to table stakes for trust.

### Add After Validation (v1.x)

- [ ] **Background-color sampling for fill** — trigger: users complain white boxes look bad / "可對外使用" quality bar not met with white.
- [ ] **Per-region removal-mode control** — trigger: CAD files where the default removal over-/under-removes; let users tune flags.
- [ ] **Undo/redo** — trigger: users report frequent mis-draws slowing them down (low cost if deferred-mutation model adopted at v1).
- [ ] **Logo placement fine-tuning (scale %, align, margin)** — trigger: requests for non-centered or smaller logos.
- [ ] **Add/remove logos (lightweight admin)** — trigger: branding changes shouldn't need a redeploy.
- [ ] **Manage-and-apply-all region panel** — trigger: multi-page jobs feel tedious one region at a time.

### Future Consideration (v2+) — aligns with PROJECT.md Out of Scope

- [ ] **Multi-file / folder batch** — defer: needs job queue + non-interactive strategy; explicitly out of scope for v1.
- [ ] **Embed into form-approval website** — defer: keep v1 standalone; expose core as a service later.
- [ ] **Auth / accounts / permissions / audit log** — defer: internal network only for v1.
- [ ] **Snap-to-object selection guides** — defer: useful but heavier than the manual primitive needs.
- [ ] **AI inpainting / auto-detection** — do not build (anti-features); listed only to keep them explicitly closed.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Multi-format upload (+ image→PDF) | HIGH | MEDIUM | P1 |
| Browser preview + page nav | HIGH | MEDIUM | P1 |
| Draw rectangular region(s) + coord mapping | HIGH | HIGH | P1 |
| True vector/text removal | HIGH | MEDIUM | P1 |
| Raster fill (white) | HIGH | LOW | P1 |
| Logo library list + select | HIGH | LOW | P1 |
| Logo placement (aspect-preserved) | HIGH | MEDIUM | P1 |
| Export / download, original preserved | HIGH | LOW | P1 |
| Before/after preview | HIGH | MEDIUM | P1–P2 (recommend P1) |
| Background-color sampling fill | MEDIUM | MEDIUM | P2 |
| Per-region removal-mode control | MEDIUM–HIGH | MEDIUM | P2 |
| Undo/redo | MEDIUM | MEDIUM | P2 |
| Logo placement fine-tuning | MEDIUM | LOW–MEDIUM | P2 |
| Add/remove logos (admin) | MEDIUM | LOW | P2 |
| Apply-all region panel | MEDIUM | LOW–MEDIUM | P2 |
| Snap-to-object guides | MEDIUM | MEDIUM–HIGH | P3 |
| Multi-file batch | HIGH (future) | HIGH | P3 (out of v1 scope) |
| Embed in approval site | HIGH (future) | MEDIUM–HIGH | P3 (out of v1 scope) |
| Auth / permissions | LOW (v1) | MEDIUM | P3 (out of v1 scope) |
| AI inpainting | — | HIGH | Do not build |
| Auto logo detection | — | HIGH | Do not build |

**Priority key:**
- P1: Must have for launch (≈ the 8 PROJECT.md Active requirements + recommended before/after preview)
- P2: Should have, add when possible (v1.x quality/UX)
- P3: Nice to have / future / out of declared scope

## Competitor Feature Analysis

| Feature | Adobe Acrobat (Redact) | PDF.js / react-pdf annotators | Our Approach |
|---------|------------------------|-------------------------------|--------------|
| True content removal | Yes — true redaction removes underlying content; defaults to white/black fill box | No — annotations are overlays, original content remains underneath | Yes — PyMuPDF `apply_redactions` (text + line-art) truly removes; the whole point vs annotation tools |
| Region drawing | Mark-for-redaction rectangles, multi-page | DIY rectangle overlay (no built-in rect in core PDF.js) | DIY rectangle overlay (canvas/SVG) + strict screen↔PDF coordinate mapping |
| Raster fill | Solid fill color over redacted area | N/A (no removal) | White or **sampled background color**, flat (no inpainting) |
| Logo / replacement content | Manual stamp/image after redaction (general, not a fixed library) | Image annotation overlay (not removal) | **Fixed company-logo library**, auto-scaled aspect-preserved placement into the region |
| Vector/CAD nuance | Removes overlapping vector art; can over-remove | N/A | Per-region removal-mode flags + before/after preview to control CAD over/under-removal |
| Batch / automation | Action wizard / batch redaction available | N/A | Out of scope for v1 (single-file interactive); core kept reusable for later batch |
| Auth / governance | Enterprise auth, audit | App-dependent | None in v1 (internal network); deferred |

**Net positioning:** general editors *can* redact and *can* stamp an image, but none is a single, focused, fixed-logo *re-branding* workflow for mixed CAD-vector + raster supplier files. The differentiation is the tight removal-then-place loop plus CAD-aware controls (per-region modes, before/after verify, sampled fill) — not breadth.

## Key Verified Technical Facts (informing the above)

- `page.add_redact_annot(rect, fill=(r,g,b))` + `page.apply_redactions(...)` truly removes overlapping **text** (`PDF_REDACT_TEXT_REMOVE`, default) and **vector/line-art** (`PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED` / `_IF_COVERED`), and can whiten/fill **image** pixels (`PDF_REDACT_IMAGE_PIXELS`) or skip images (`PDF_REDACT_IMAGE_NONE`). This is exactly the "remove not cover" + "fill raster" requirement. (HIGH)
- `page.insert_image(rect, ...)` scales an image into a rect, **preserves aspect ratio**, and centers it. Use transparent-PNG logos to avoid an opaque box. (HIGH)
- PyMuPDF opens PNG/JPG/TIFF/BMP/GIF (and more) as `Pixmap`; standalone images are easily wrapped into a 1-page PDF for a uniform pipeline. (HIGH)
- **Pitfall (verified, drives before/after preview + per-region modes):** redaction can remove *more* than intended — images/icons merely overlapping a redaction rect get deleted/whitened; and content defined via clipping masks or embedded raster (common in CAD-derived PDFs) may not be a discrete object to "remove." Mode control + visual verification are the mitigations. (HIGH — confirmed in PyMuPDF issues/discussions #3439/#3440/#901 and CAD clipping-mask sources)
- Core PDF.js has **no** built-in rectangle-annotation/drawing primitive; rectangle selection is an established DIY canvas/SVG-overlay pattern, and **coordinate mapping** (DPI/zoom/rotation) is the main correctness risk. (HIGH)

## Sources

- [PyMuPDF — Page (apply_redactions / add_redact_annot, redaction flags)](https://pymupdf.readthedocs.io/en/latest/page.html) — HIGH
- [PyMuPDF docs source — page.rst (redaction parameter semantics)](https://github.com/pymupdf/PyMuPDF/blob/main/docs/page.rst) — HIGH
- [PyMuPDF — The Basics (redaction two-step, insert_image scaling/aspect)](https://pymupdf.readthedocs.io/en/latest/the-basics.html) — HIGH
- [PyMuPDF — Image handling / Pixmap (supported input formats, image→PDF)](https://pymupdf.readthedocs.io/en/latest/recipes-images.html) — HIGH
- [Artifex — Adding Watermarks/Logos with PyMuPDF (insert_image, scale to %, aspect-preserved placement)](https://artifex.com/blog/adding-watermarks-to-pdfs-with-pymupdf-a-complete-guide) — MEDIUM
- [PyMuPDF Issue #3439 / Discussion #3440 — redaction deletes overlapping images/icons (over-removal pitfall)](https://github.com/pymupdf/PyMuPDF/issues/3439) — HIGH
- [PyMuPDF Issue #901 — redaction breaks transparent images (raster pitfall)](https://github.com/pymupdf/PyMuPDF/issues/901) — HIGH
- [PyMuPDF Issue #4657 — redaction fill defaults to white; Acrobat parity](https://github.com/pymupdf/pymupdf/issues/4657) — MEDIUM
- [Understanding PDF.js Layers in React (canvas/text/annotation layers, overlays)](https://blog.react-pdf.dev/understanding-pdfjs-layers-and-how-to-use-them-in-reactjs) — MEDIUM
- [mozilla/pdf.js Issue #20146 — request for built-in rectangle annotation (i.e., not built-in)](https://github.com/mozilla/pdf.js/issues/20146) — HIGH
- [mozilla/pdf.js Issue #11285 — drawing a rectangle on PDF canvas (DIY pattern)](https://github.com/mozilla/pdf.js/issues/11285) — MEDIUM
- [Bluebeam — Issues with raster-based PDFs (raster vs vector handling)](https://support.bluebeam.com/revu/troubleshooting/issues-with-raster-based-pdfs.html) — MEDIUM
- [Adobe — PDF imports & clipping masks (CAD/vector clipping nuance)](https://community.adobe.com/t5/illustrator-discussions/why-do-pdf-imports-have-a-clipping-mask/td-p/10644921) — MEDIUM

---
*Feature research for: internal PDF/image logo-replacement (true-removal) tool — PyMuPDF backend*
*Researched: 2026-05-22*
