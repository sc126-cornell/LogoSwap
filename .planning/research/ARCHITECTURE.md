# Architecture Research

**Domain:** Interactive server-side PDF/image editor (web tool), single-file, manual region selection, true content removal + logo replacement
**Researched:** 2026-05-22
**Confidence:** HIGH (coordinate mapping, PyMuPDF redaction mechanics, rendering pipeline verified against official PyMuPDF docs; MEDIUM on framework choice — opinionated but several valid options)

## Standard Architecture

This is a **server-authoritative interactive editor**. The browser is a thin viewer + region-marking surface; all PDF/image truth lives on the server because PyMuPDF (Python) does the actual rendering and editing. The defining problem is **coordinate mapping**: the user draws rectangles on a *scaled raster preview* in the browser, but edits must be applied in *PDF point space on the unrotated page*. Everything in this architecture is shaped to make that mapping correct and centralized.

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         BROWSER (thin client)                          │
│  ┌──────────────┐  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │ Upload Form  │  │ Preview Viewer   │  │ Region Selection UI     │  │
│  │ (file pick)  │  │ (render <img>    │  │ (draw rects on overlay, │  │
│  │              │  │  per page +DPI)  │  │  pick logo, place)      │  │
│  └──────┬───────┘  └────────┬─────────┘  └────────────┬────────────┘  │
│         │                   │ shows server-rendered    │ rects in       │
│         │                   │ page image (known DPI)   │ IMAGE pixels   │
└─────────┼───────────────────┼──────────────────────────┼───────────────┘
          │ multipart upload  │ GET page image           │ POST job spec
          ▼                   ▼ (per page, per zoom)     ▼ (rects+logo+page)
┌──────────────────────────────────────────────────────────────────────┐
│                      HTTP API LAYER (FastAPI)                          │
│  /sessions  /sessions/{id}/pages/{n}/image  /sessions/{id}/process     │
│  /logos     /sessions/{id}/result                                      │
├──────────────────────────────────────────────────────────────────────┤
│                       APPLICATION SERVICES                             │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────┐ │
│  │ Session/   │ │ Render       │ │ COORDINATE   │ │ Processing     │ │
│  │ Upload Mgr │ │ Service      │ │ MAPPER       │ │ Pipeline       │ │
│  │ (ingest,   │ │ (page→pixmap │ │ (px↔point,   │ │ (redact branch │ │
│  │  preserve  │ │  at DPI,     │ │  rotation,   │ │  + logo insert │ │
│  │  original) │ │  page meta)  │ │  origin flip)│ │  + export)     │ │
│  └─────┬──────┘ └──────┬───────┘ └──────┬───────┘ └───────┬────────┘ │
│        │               │                │                 │          │
│        │      ┌────────┴────────────────┴─────────────────┴───────┐  │
│        │      │              PyMuPDF (fitz) core                   │  │
│        │      │  open / get_pixmap / add_redact_annot /            │  │
│        │      │  apply_redactions / insert_image / save            │  │
│        │      └────────────────────────────────────────────────────┘  │
├────────┴───────────────────────────────────────────────────────────────┤
│                            STORAGE (filesystem)                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│  │ originals/   │ │ work/        │ │ outputs/     │ │ logos/       │  │
│  │ (immutable,  │ │ (normalized  │ │ (generated   │ │ (fixed lib,  │  │
│  │  read-only)  │ │  PDF, cache) │ │  PDFs)       │ │  read-only)  │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Upload/Session Manager** | Accept one file (PDF or PNG/JPG/TIFF); validate type/size; assign session id; write the original immutably to `originals/`; **normalize** non-PDF images into a one-page PDF in `work/` so the rest of the pipeline is PDF-only | FastAPI `UploadFile` → save to disk; `fitz.open(stream=..., filetype=...)`; for images, `fitz.open()` a new doc + `page.insert_image(rect, ...)` or `fitz.Pixmap → PDF` |
| **Render Service** | Given (session, page index, DPI/zoom), produce a raster image of that page; also expose **page metadata**: page rect (points), `rotation`, and the exact DPI/scale used to render | `page.get_pixmap(dpi=N)` → PNG bytes; returns `width_pt, height_pt, rotation, dpi` alongside |
| **Coordinate Mapper** | The single source of truth for converting **browser-image pixels ↔ PDF points**, accounting for DPI scale, the bottom-left vs top-left origin, and page rotation (`derotation_matrix`). Used by the pipeline before any edit | Pure Python module, no I/O; functions `pixels_to_pdf_rect()` / `pdf_rect_to_pixels()` taking `(rect, dpi, page)` |
| **Processing Pipeline** | Orchestrate one job: load normalized PDF from `work/`, for each marked region detect content type and **branch** (vector-redaction vs raster-fill), apply redactions, insert chosen logo scaled into the region, save to `outputs/` | A `process_job(session, job_spec)` service calling Coordinate Mapper then PyMuPDF |
| **Logo Library** | Hold a fixed set of company logos as static assets + a manifest (id, name, native px size, transparent-PNG path); serve list to UI and resolve id→file for insertion | `logos/` directory + `logos/manifest.json`; served via `/logos` |
| **Logo Insertion** | Place selected logo PNG into a target PDF rect, preserving aspect ratio (fit/contain), honoring transparency | `page.insert_image(target_rect, filename=..., keep_proportion=True)` after redaction |
| **Output Generator** | Write the new PDF; never touch the original; return a download URL; optionally `garbage`-collect/clean unused objects | `doc.save(out_path, garbage=4, deflate=True)` |
| **Original Preservation** | Guarantee the uploaded source is byte-for-byte intact | Write-once to `originals/`, set read-only perms, **never** open the original with edits — always edit a copy in `work/` |

## Recommended Project Structure

```
pdf-logo-tool/
├── app/
│   ├── main.py                 # FastAPI app, route registration, static mount
│   ├── api/
│   │   ├── sessions.py         # POST /sessions (upload), GET session meta
│   │   ├── pages.py            # GET /sessions/{id}/pages/{n}/image?dpi=
│   │   ├── process.py          # POST /sessions/{id}/process, GET /result
│   │   └── logos.py            # GET /logos  (list fixed library)
│   ├── services/
│   │   ├── ingest.py           # upload validation + image→PDF normalization
│   │   ├── render.py           # page → pixmap at DPI + page metadata
│   │   ├── coords.py           # ★ Coordinate Mapper (pure, unit-tested)
│   │   ├── pipeline.py         # job orchestration + vector/raster branch
│   │   ├── redact.py           # PyMuPDF redaction wrappers (the two branches)
│   │   └── logo.py             # logo resolution + insert_image placement
│   ├── models.py               # Pydantic: JobSpec, RegionMark, PageMeta
│   ├── storage.py              # path layout, session dirs, retention/cleanup
│   └── config.py               # DPI default, size limits, dirs, CORS/embed flags
├── logos/
│   ├── manifest.json           # [{id, name, file, native_w, native_h}]
│   └── *.png                   # transparent company logos
├── data/                       # gitignored runtime storage
│   ├── originals/{session}/    # immutable source
│   ├── work/{session}/         # normalized PDF + render cache
│   └── outputs/{session}/      # generated PDFs
├── web/                        # static frontend (no build step needed v1)
│   ├── index.html
│   ├── viewer.js               # fetch page images, page nav, zoom
│   ├── regions.js              # ★ draw rects, track in IMAGE pixel space
│   └── api.js                  # thin fetch wrappers (the seam — see below)
└── tests/
    └── test_coords.py          # ★ round-trip px→pt→px at every rotation
```

### Structure Rationale

- **`services/coords.py` is isolated and pure (no I/O, no FastAPI, no disk).** This is the load-bearing module; isolating it makes it unit-testable in a tight loop and keeps the mapping logic in exactly one place. Every edit path routes through it.
- **`services/redact.py` separates the two branches** (vector vs raster) so their distinct PyMuPDF parameter sets and gotchas live together and are independently testable.
- **`ingest.py` normalizes everything to PDF early**, so render/coords/pipeline only ever deal with PDF pages — collapsing four input variants (vector PDF, image PDF, PNG/JPG/TIFF) into one internal model.
- **`web/api.js` is the only place that talks to the server** — the integration seam. Swapping standalone↔embedded means changing base URLs/headers in one file.
- **Static frontend, no bundler in v1.** Plain HTML + vanilla JS (or a single small lib like Alpine) keeps deployment to Ubuntu trivial and the iframe-embed story simple.

## Architectural Patterns

### Pattern 1: Server-Side Rasterize, Client-Side Mark (thin client)

**What:** The server renders each page to a raster image at a *known DPI* and ships it as a plain `<img>`. The browser overlays a transparent layer where the user draws rectangles. The browser never parses the PDF.

**When to use:** When the authoritative editing engine is server-side (PyMuPDF here) and you want the preview to *exactly* match what the server will edit. Avoids PDF.js/PyMuPDF rendering discrepancies.

**Trade-offs:** + Preview is pixel-identical to the edit substrate; + no client PDF engine; + uniform handling of vector/image/raster inputs. − A render round-trip per page/zoom (mitigated by caching rendered pages in `work/`); − no client-side text selection (not needed — selection is manual rectangles).

**Example:**
```python
# render.py — one page to PNG at a known DPI, plus the metadata the mapper needs
def render_page(doc, page_no: int, dpi: int = 150):
    page = doc[page_no]
    pix = page.get_pixmap(dpi=dpi)            # raster at known DPI
    r = page.rect                              # UNROTATED page rect, in points
    return {
        "png": pix.tobytes("png"),
        "img_w": pix.width, "img_h": pix.height,
        "page_w_pt": r.width, "page_h_pt": r.height,
        "rotation": page.rotation,             # 0/90/180/270
        "dpi": dpi,
    }
```

### Pattern 2: Centralized Coordinate Mapper (the core of the system)

**What:** A single pure module converts the user's rectangle (in *preview-image pixels*) into a PyMuPDF `Rect` in *unrotated PDF point space*. It handles three concerns at once: **(a) DPI scale**, **(b) origin** — PyMuPDF's `Rect`/`get_pixmap` already use a top-left origin so the displayed image and PyMuPDF share orientation (no manual y-flip needed when you stay inside PyMuPDF), and **(c) rotation** via `page.derotation_matrix`.

**Why each piece matters (verified):**
- **DPI scale:** PDF uses 72 points/inch. A pixmap at `dpi=N` is scaled by `N/72`. So `point = pixel * 72 / dpi`. (PyMuPDF docs: "1 inch = 72 points… multiply by 300/72 to achieve 300 dpi".)
- **Rotation:** PyMuPDF coordinates "always pertain to the *unrotated* page." But the **rendered image is rotated** (`get_pixmap` honors `page.rotation`). So a rect derived directly from displayed-image pixels lives in *rotated/displayed* space and must be mapped back with `page.derotation_matrix` before redaction/insertion. This is the #1 source of "logo lands in the wrong place / removal misses" bugs.
- **Origin:** Within PyMuPDF, `Rect` and `get_pixmap` are top-left origin, matching the browser image. The bottom-left PDF origin is handled internally by PyMuPDF — you do **not** hand-flip y as long as you build a `fitz.Rect` and let derotation handle orientation. (Pitfall to avoid: mixing raw PDF/MediaBox coordinates with PyMuPDF `Rect` coordinates.)

**When to use:** Always, before any redaction or insertion. No edit path bypasses it.

**Trade-offs:** + One tested place to get right; + makes rotation a non-issue downstream. − Requires disciplined round-trip tests at 0/90/180/270.

**Example:**
```python
# coords.py — image pixels (as shown to user) → PyMuPDF Rect on the unrotated page
import fitz

def pixels_to_pdf_rect(px_rect, dpi: int, page: fitz.Page) -> fitz.Rect:
    """px_rect = (x0, y0, x1, y1) in PREVIEW-IMAGE pixel space (top-left origin),
    i.e. coordinates measured on exactly the image render.render_page produced."""
    s = 72.0 / dpi                                  # pixels -> points
    # Rect in the DISPLAYED (rotated) coordinate space, top-left origin:
    disp = fitz.Rect(px_rect[0]*s, px_rect[1]*s, px_rect[2]*s, px_rect[3]*s)
    # Map displayed/rotated space back to the page's unrotated space:
    unrotated = disp * page.derotation_matrix
    return unrotated.normalize()                    # ensure x0<x1, y0<y1

def pdf_rect_to_pixels(rect: fitz.Rect, dpi: int, page: fitz.Page):
    """Inverse — for echoing server rects back onto the preview (e.g. confirm UI)."""
    disp = (rect * page.rotation_matrix)
    z = dpi / 72.0
    return (disp.x0*z, disp.y0*z, disp.x1*z, disp.y1*z)
```

### Pattern 3: Branch Pipeline (vector-redaction vs raster-fill)

**What:** For each region the pipeline decides whether the underlying content is vector (text + line-art objects) or raster (image), and applies different PyMuPDF redaction parameters. Both branches use the same `add_redact_annot` + `apply_redactions` machinery; only the options differ.

**When to use:** Every region. The branch can be auto-detected (does the rect overlap an image xref? `page.get_image_rects`/`page.get_text` presence) or, simpler and more reliable for v1, **let the user tag the region** as "vector content" vs "image area" in the UI — matching the manual-selection philosophy the project already chose.

**Trade-offs:** + Correct true-removal semantics for each content type; + matches "remove not cover." − Two parameter sets to maintain; − redaction is character-bbox-based so it can over-remove adjacent glyphs (known PyMuPDF behavior — mitigate with `fitz.Tools().set_small_glyph_heights(True)`).

**Example:**
```python
# redact.py — both branches. fill=(1,1,1) gives the white fill the project wants.
import fitz

def remove_vector(page, rect: fitz.Rect):
    """True removal of text + vector objects inside rect."""
    page.add_redact_annot(rect, fill=(1, 1, 1))   # white after removal
    page.apply_redactions(
        text=fitz.PDF_REDACT_TEXT_REMOVE,                    # drop overlapping glyphs
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED, # drop covered line-art
        images=fitz.PDF_REDACT_IMAGE_NONE,                   # leave images alone here
    )

def fill_raster(page, rect: fitz.Rect, color=(1, 1, 1)):
    """Raster/image area: blank the pixels under rect (white or chosen bg color)."""
    page.add_redact_annot(rect, fill=color)
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_PIXELS,   # blank only overlapping pixels
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_NONE,
    )
```
> Note: "surrounding background color" fill is a v1 nicety — sample a pixel just outside the rect from the rendered pixmap and pass it as `color`. Plain white is the safe default and matches the PROJECT decision.

### Pattern 4: API-First Seam for Future Embedding

**What:** Treat the backend as a headless REST API; the v1 standalone UI is just *one consumer* of that API. All UI↔server traffic goes through `web/api.js`. This keeps the "embed into the approval website later" path clean without building it now.

**When to use:** Now, as a design discipline — costs nothing in v1, saves a rewrite later.

**Trade-offs:** + Future iframe/embed needs only config (CORS allow-list, base URL) and an existing UI seam; + the host site could even call the API directly and supply its own UI. − Slightly more discipline than coupling UI to server templates.

**Example:**
```javascript
// api.js — the ONLY module that knows the server URL. The embedding seam.
const API_BASE = window.PDFTOOL_API_BASE || "";   // host page can override
export const createSession = (file) => {
  const fd = new FormData(); fd.append("file", file);
  return fetch(`${API_BASE}/sessions`, {method: "POST", body: fd}).then(r=>r.json());
};
export const pageImageURL = (sid, n, dpi) =>
  `${API_BASE}/sessions/${sid}/pages/${n}/image?dpi=${dpi}`;
export const process = (sid, jobSpec) =>
  fetch(`${API_BASE}/sessions/${sid}/process`,
        {method:"POST", headers:{"Content-Type":"application/json"},
         body: JSON.stringify(jobSpec)}).then(r=>r.json());
```

## Data Flow

### Request Flow

```
[User picks file]
   │  multipart POST /sessions
   ▼
[Ingest] validate → write originals/{sid}/source.*  (IMMUTABLE)
        → normalize (image→1-page PDF) → work/{sid}/doc.pdf
        → return {session_id, page_count}
   │
   ▼
[User navigates pages / zooms]
   │  GET /sessions/{sid}/pages/{n}/image?dpi=150
   ▼
[Render] doc.pdf → get_pixmap(dpi) → PNG  (+ page meta cached)
        → browser shows <img>; UI records DPI used
   │
   ▼
[User draws rectangles (in IMAGE pixels) + picks logo + sets placement]
   │  POST /sessions/{sid}/process   { regions:[{page,px_rect,kind,logoId,
   │                                            place_px_rect}], dpi }
   ▼
[Pipeline] open COPY of work/doc.pdf  (original untouched)
        for each region:
          ├─ Coordinate Mapper: px_rect --(dpi, rotation)--> fitz.Rect (unrotated)
          ├─ branch: kind==vector → remove_vector ; kind==image → fill_raster
          └─ logo: place_px_rect --mapper--> rect ; insert_image(rect, logo, keep_proportion)
        doc.save(outputs/{sid}/result.pdf, garbage=4, deflate=True)
        → return {result_url}
   │
   ▼
[User downloads]  GET /sessions/{sid}/result  → result.pdf
```

### State Management

```
SERVER holds the canonical state (filesystem-backed, keyed by session_id):
   originals/{sid}/  — immutable source (preservation guarantee)
   work/{sid}/       — normalized PDF + render cache  (editing substrate)
   outputs/{sid}/    — generated result

BROWSER holds ONLY transient UI state (no PDF, no edits persisted client-side):
   - current page index, current zoom/DPI
   - in-progress rectangles, each stored in IMAGE-PIXEL coordinates
   - selected logo id + placement rect (also image pixels)
   The job spec is the single payload that crystallizes browser state → server.
```

The key invariant: **the browser only ever deals in image-pixel coordinates at a stated DPI; the server is the only place that converts to PDF points and the only place that mutates documents.** This keeps the hard math in one tested location and makes the client trivially replaceable (the embedding goal).

### Key Data Flows

1. **Original preservation:** Upload writes once to `originals/` and is never opened for editing. The pipeline always opens a copy in `work/`. Output goes to `outputs/`. Three separate directories make accidental mutation structurally impossible.
2. **Coordinate crystallization:** Rectangles live as image pixels in the browser through the whole interaction; they become PDF `Rect`s exactly once, server-side, at process time — using the same DPI the image was rendered at (the DPI is echoed in the job spec so client and server can't disagree).
3. **Input normalization:** Vector PDF, image-only PDF, and standalone PNG/JPG/TIFF all converge to a single normalized PDF in `work/` at ingest, so render/mapper/pipeline have exactly one code path.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Internal team (1–20 concurrent) — v1 reality | Single FastAPI process (uvicorn + a few workers) on the Ubuntu box. Filesystem storage. Synchronous processing is fine; PyMuPDF is fast for single files. No queue, no DB. |
| Heavier internal use (occasional large/many-page PDFs) | Move processing to a `BackgroundTask` or a small worker so HTTP requests don't block; add a render cache eviction policy; cap DPI and page size. |
| Embedded into approval site / batch (future, out of scope) | Introduce a job queue (RQ/Celery) and a real session store (Redis); make the API stateless behind it; this is exactly what the API-first seam buys you. |

### Scaling Priorities

1. **First bottleneck: synchronous render/process blocking the request thread** on large multi-page CAD PDFs. Fix: render cache in `work/` (already designed) + offload `process` to a background task returning a job id. Cheap to add when needed.
2. **Second bottleneck: disk growth from sessions.** Fix: a retention/cleanup job (`storage.py`) that deletes session dirs older than N hours — important even in v1 so the box doesn't fill.

## Anti-Patterns

### Anti-Pattern 1: Rendering preview with PDF.js while editing with PyMuPDF

**What people do:** Use PDF.js (or pdf.js-based viewers) in the browser to render the page and capture rectangles against *that* render, then send to a PyMuPDF backend.
**Why it's wrong:** The two engines can lay out/rasterize subtly differently (fonts, rotation handling, cropbox vs mediabox), so the rectangle the user drew on the PDF.js canvas does not align with PyMuPDF's coordinate space — removal misses and logos drift. It also forces you to reconcile *two* coordinate systems.
**Do this instead:** Render the preview *with the same PyMuPDF* that does the editing (Pattern 1). The image the user marks is literally the substrate the server edits.

### Anti-Pattern 2: Ignoring page rotation in the coordinate mapping

**What people do:** Convert pixels→points using only the DPI scale and feed the rect straight to `add_redact_annot`.
**Why it's wrong:** PyMuPDF coordinates pertain to the *unrotated* page, but `get_pixmap` renders the *rotated* page. On 90/180/270° pages the rect is in the wrong orientation; redaction and logo land in the wrong region. This passes silently on the common 0° pages and fails only on rotated ones — a nasty latent bug.
**Do this instead:** Always pass the rect through `page.derotation_matrix` (Pattern 2) and test round-trips at all four rotations.

### Anti-Pattern 3: Editing the uploaded original in place

**What people do:** Open the uploaded file, redact, and `save()` (or `saveIncr`) over it, then serve it.
**Why it's wrong:** Violates the hard requirement that the original is preserved; one bug or one re-run corrupts the source of truth.
**Do this instead:** Original is write-once and read-only; always edit a copy in `work/`, write results to `outputs/`.

### Anti-Pattern 4: Hand-flipping Y / mixing raw PDF coordinates with PyMuPDF Rect

**What people do:** Manually compute `y = page_height - y` to "fix" the bottom-left PDF origin while also using PyMuPDF `Rect`s.
**Why it's wrong:** PyMuPDF `Rect` and `get_pixmap` already use a top-left origin; manual flipping double-corrects and inverts placement. Mixing MediaBox-space numbers with PyMuPDF-space numbers is the classic origin bug.
**Do this instead:** Stay entirely in PyMuPDF coordinate space (build `fitz.Rect`, use derotation). Don't reach for raw PDF MediaBox math.

### Anti-Pattern 5: Coupling the UI directly to server-rendered templates

**What people do:** Render the editor with Jinja templates and embed server URLs throughout the JS.
**Why it's wrong:** Kills the future embedding story — the approval site can't reuse the API cleanly, and CORS/iframe concerns get tangled in the UI.
**Do this instead:** API-first (Pattern 4); a static frontend whose only server contact is `api.js`.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| (none in v1) | — | Fully self-contained; no external APIs, no AI/inpainting, no auth provider. This is a deliberate v1 simplification. |
| Future: approval-form website | Iframe embed + REST API, or direct API consumption | API-first design means the host either drops the standalone UI in an `<iframe>` (set `API_BASE`, allow CORS, send iframe-resize via `postMessage`) or calls the REST endpoints with its own UI. No backend rearchitecture required. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Browser ↔ API | REST/JSON + multipart upload + `<img>` GETs | Only `web/api.js` crosses it. Image-pixel coords on the wire; never PDF points. |
| API ↔ Services | Direct in-process Python calls | FastAPI handlers stay thin; logic lives in `services/`. |
| Pipeline ↔ Coordinate Mapper | Direct call, *mandatory* before every edit | The one chokepoint that guarantees correct mapping. |
| Services ↔ PyMuPDF | Direct `fitz` calls, wrapped in `render.py`/`redact.py`/`logo.py` | Wrapping isolates PyMuPDF quirks (redaction options, glyph-height flag) from orchestration. |
| Services ↔ Storage | Path layout via `storage.py` | Enforces originals/work/outputs separation. |

## Build Order (dependency-ordered — what must exist before what)

This ordering is the primary signal for roadmap phasing. Each step is independently demonstrable.

```
1. STORAGE + INGEST + PRESERVATION  ── foundation
   - session dirs; write original immutably; normalize image→PDF.
   - Demo: upload any of the 4 input types → a normalized PDF exists in work/,
     original untouched in originals/. Nothing else can be built without this.

2. RENDER SERVICE + PREVIEW VIEWER  ── you must SEE before you can MARK
   - get_pixmap(dpi) endpoint + page metadata; browser shows pages, page nav, zoom.
   - Demo: flip through pages of an uploaded file in the browser.
   - Depends on: (1).

3. COORDINATE MAPPER + ROUND-TRIP TESTS  ── ★ the spine; build & prove EARLY
   - pure px↔pt module with derotation; unit tests at 0/90/180/270.
   - Demo: a test rect drawn in pixels maps to the correct PDF Rect (verify by
     rendering the mapped rect back onto the image — it overlaps the input).
   - Depends on: (2) for page metadata. MUST be solid before any editing.

4. REGION SELECTION UI  ── capture rectangles in image-pixel space
   - overlay drawing, multiple rects, per-page, region kind tag (vector/image).
   - Demo: draw rects on the preview; job spec (pixels) is assembled.
   - Depends on: (2). Pairs with (3) — UI produces what mapper consumes.

5. PROCESSING PIPELINE: REMOVAL BRANCHES  ── the core value
   - vector redaction + raster fill via add_redact_annot/apply_redactions on a COPY.
   - Demo: marked supplier logo/text is truly GONE in the output PDF; original intact.
   - Depends on: (3) mapper + (4) job spec + (1) work copy.

6. LOGO LIBRARY + INSERTION  ── replacement half of the core value
   - manifest + static logos; /logos endpoint; insert_image with keep_proportion.
   - Demo: company logo appears, correctly scaled/placed, in the removed region.
   - Depends on: (5) (insert after redaction) + (3) (placement rect mapping).

7. OUTPUT + DOWNLOAD  ── close the loop
   - save(garbage=4); /result download; retention cleanup.
   - Demo: download a finished, brand-correct PDF; originals/ still pristine.
   - Depends on: (5)+(6).

(Cross-cutting from step 1: API-first seam — every endpoint above is REST/JSON via
 api.js, so the embedding path stays open with zero extra work later.)
```

**Critical ordering insight:** Steps **3 (Coordinate Mapper)** and **5 (Removal)** are the highest-risk, highest-value items. The mapper must be proven *before* removal, because incorrect mapping makes removal look broken in ways that are hard to debug. Recommend a dedicated, test-heavy phase for the mapper rather than folding it into UI or pipeline work. Render (2) is a hard prerequisite for both the UI and the mapper (it supplies page metadata and the very image users mark).

## Sources

- [PyMuPDF — Page (add_redact_annot, apply_redactions, rotation_matrix/derotation_matrix)](https://pymupdf.readthedocs.io/en/latest/page.html) — HIGH (authoritative; verified parameter signatures and rotation semantics)
- [PyMuPDF — Images / get_pixmap DPI & zoom](https://pymupdf.readthedocs.io/en/latest/recipes-images.html) — HIGH (DPI=72pt baseline, N/72 zoom relationship)
- [PyMuPDF — Pixmap (width/height/stride)](https://pymupdf.readthedocs.io/en/latest/pixmap.html) — HIGH
- [PyMuPDF — Matrix & coordinate system](https://pymupdf.readthedocs.io/en/latest/matrix.html) — HIGH
- [PyMuPDF Discussion #1806 — coordinate system(s)](https://github.com/pymupdf/PyMuPDF/discussions/1806) — MEDIUM (community, consistent with docs)
- [PyMuPDF Issue #3433 — apply_redactions removes more text than expected](https://github.com/pymupdf/PyMuPDF/issues/3433) — MEDIUM (documents the character-bbox over-removal pitfall)
- [PyMuPDF Issue #3770 — redaction removing images](https://github.com/pymupdf/PyMuPDF/issues/3770) — MEDIUM (motivates explicit image/graphics options per branch)
- [PyMuPDF Discussion #2471 — unwanted white rectangles from redaction](https://github.com/pymupdf/PyMuPDF/discussions/2471) — MEDIUM
- [PyMuPDF Issue #4657 — redaction fill color white](https://github.com/pymupdf/pymupdf/issues/4657) — MEDIUM (confirms fill=(1,1,1) behavior)
- [Mozilla PDF.js examples & viewport notes](https://mozilla.github.io/pdf.js/examples/) — MEDIUM (confirms origin-flip concern; used to argue AGAINST PDF.js for editing here)
- [FastAPI — Request Files / UploadFile](https://fastapi.tiangolo.com/tutorial/request-files/) — HIGH (upload handling, in-memory vs disk spill)
- [Inter-Application Communication Using Iframes and postMessage](https://medium.com/@rishinamansingh/inter-application-communication-using-iframes-and-the-postmessage-api-3ddf26dac9af) — LOW/MEDIUM (embedding pattern background)

---
*Architecture research for: interactive server-side PDF logo replacement tool (PyMuPDF)*
*Researched: 2026-05-22*
