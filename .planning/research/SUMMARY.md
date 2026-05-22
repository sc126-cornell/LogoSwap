# Project Research Summary

**Project:** PDF 商標替換工具 (PDF Logo Replacement Tool)
**Domain:** Browser-based, server-authoritative PDF/image redaction and logo replacement tool (internal LAN, no auth, PyMuPDF-backed)
**Researched:** 2026-05-22
**Confidence:** HIGH

## Executive Summary

This is a focused, single-file, interactive re-branding tool: a user uploads a supplier product-design PDF (vector, raster, or standalone image), manually draws rectangles over supplier logos and text, and exports a new PDF with those regions truly removed and replaced by the company's own logo. The emphasis on "true removal" — not a white-box cover-up — is the entire core value, and it is fully achievable via PyMuPDF's `add_redact_annot` + `apply_redactions` API, which genuinely deletes text glyphs, vector line-art objects, and image pixels from the underlying PDF content stream rather than overlaying an opaque shape. The recommended architecture is a single-process FastAPI service (Python 3.12, PyMuPDF 1.27.x, Pillow 12, NumPy 2.x) serving a vanilla JS + server-rendered-preview frontend, deployed as a Docker container behind Nginx on the internal Ubuntu box, with no database and no auth in v1.

The highest-risk engineering component is **coordinate mapping**: the user draws rectangles on a raster preview image rendered at a specific DPI, but PyMuPDF operates in PDF point space on an unrotated page. Three coordinate-system concerns must be handled simultaneously — DPI scale (`px * 72 / dpi = points`), page rotation (PyMuPDF coordinates are always in unrotated space; the displayed image is rotated; `page.derotation_matrix` bridges the gap), and origin convention (PyMuPDF `Rect` uses top-left, matching the browser image, but differs from the raw PDF spec's bottom-left; do not hand-flip Y). A misaligned mapping produces wrong redaction placement silently — the export looks clean but the removal or logo lands in the wrong area. This module must be built early, isolated, and proven with round-trip tests at all four page rotations before any redaction code is written.

The recommended approach is a **server-authoritative rendering model**: the server (PyMuPDF) renders each page to a PNG at a known DPI, the browser displays that exact image, and the user draws rectangles measured in those image pixels. The browser transmits pixel coordinates plus the DPI value; the server does the single, centralized pixel-to-point conversion and applies edits. This eliminates the rendering-engine mismatch that occurs when PDF.js renders the preview but PyMuPDF does the editing. A **deferred-mutation model** — keeping regions and logo assignments as editable data on the client until the user explicitly exports — makes undo/redo cheap and enables a before/after preview of the redacted page (strongly recommended as v1 table stakes, not a v1.x nicety). PyMuPDF is AGPL-licensed; internal LAN use in v1 is fine, but the library must be isolated behind a clean service boundary so the engine can be swapped if the future website-embedding milestone exposes the tool to external users.

---

## Key Findings

### Recommended Stack

A deliberately low-moving-parts stack is correct for this problem. One Python process handles upload, rendering, coordinate conversion, redaction, and logo insertion — there is no reason for a separate worker service or a database in v1. The frontend is plain HTML + vanilla JS with server-rendered page images as `<img>` elements and a transparent canvas overlay for rectangle drawing; no Node build toolchain is needed.

**Core technologies:**

- **Python 3.12** — stable sweet spot; required by Pillow 12 (drops 3.9); prebuilt wheels for all core dependencies
- **PyMuPDF (fitz) 1.27.x, pin `>=1.27,<1.28`** — the load-bearing library; `page.add_redact_annot(rect, fill=(1,1,1))` + `page.apply_redactions(text=PDF_REDACT_TEXT_REMOVE, graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED, images=PDF_REDACT_IMAGE_PIXELS)` truly removes content (verified against official docs); `fill` defaults to white `(1,1,1)`; dual-licensed AGPL / Artifex commercial
- **FastAPI 0.115.x** — native `UploadFile`, Pydantic 2 validation of region payloads, auto OpenAPI schema (the future embedding contract)
- **Uvicorn 0.34.x with `--workers`** — modern built-in multi-process supervisor; no Gunicorn needed for internal low-concurrency use
- **Pillow 12.x** — standalone image decoding and normalization; logo pre-validation
- **NumPy 2.x** — border-pixel sampling for "surrounding background color" fill; not required for plain white fill
- **Vanilla JS (no build step) + server-rendered PNG pages** — preferred over PDF.js for preview to eliminate rendering-engine coordinate discrepancies

**Do not use:** pypdf/PyPDF2 (cannot truly remove content), PDF.js as the editable preview renderer (rendering discrepancy risk), Celery in v1, any database, AI inpainting.

### Expected Features

**Must have — v1 table stakes:**
- Multi-format upload (vector PDF, raster/image PDF, standalone PNG/JPG/TIFF) — standalone images normalized to 1-page PDF at ingest
- Browser preview + multi-page navigation — server renders pages with `get_pixmap`; client displays as `<img>`
- Draw rectangular regions per page, cross-page — canvas overlay; regions stored in image-pixel space
- Correct screen-pixel to PDF-point coordinate mapping — load-bearing sub-feature; must account for DPI, `derotation_matrix`, and origin convention
- True vector/text removal — `add_redact_annot` + `apply_redactions` with `PDF_REDACT_TEXT_REMOVE` and `PDF_REDACT_LINE_ART_REMOVE_IF_COVERED`
- Raster fill (white minimum) — `PDF_REDACT_IMAGE_PIXELS` with `fill=(1,1,1)`
- Company logo library: list + select — static `logos/` + `manifest.json`
- Logo placement, aspect-ratio preserved — `page.insert_image(..., keep_proportion=True)` after redaction
- Export/download; original never mutated — three-directory separation (`originals/`, `work/`, `outputs/`)
- **Before/after preview of redacted region** — promoted to table stakes; redaction silently over- or under-removes on CAD-derived PDFs

**Should have — v1.x:** Background-color sampling for fill; per-region removal-mode control; undo/redo; logo placement fine-tuning; lightweight admin for logo library; manage-and-apply-all panel.

**Defer — v2+:** Batch processing; auth; website embedding.

**Do not build:** AI inpainting; automatic logo/text detection.

### Architecture Approach

Server-authoritative thin-client editor. The browser deals exclusively in image-pixel coordinates at a stated DPI; the server is the single place that converts those pixels to PDF points and mutates documents. Deferred-mutation model: regions live as editable data on the client; the PDF is mutated exactly once at export time on a copy of the working file.

**Major components:** Upload/Session Manager (ingest.py), Render Service (render.py), Coordinate Mapper (coords.py — pure, no I/O, unit-tested), Processing Pipeline (pipeline.py), Logo Library (logos/ + manifest.json), Storage (storage.py — enforces three-directory separation), API Layer (thin FastAPI handlers), Frontend (viewer.js + regions.js + api.js as the embedding seam).

### Critical Pitfalls (top 5 of 11)

1. **Browser-pixel to PDF-point coordinate mismatch** — derive scale from exact render DPI, never CSS element size; account for `window.devicePixelRatio`; build a visual round-trip test harness before any redaction code
2. **Page rotation and non-(0,0) MediaBox** — always apply `page.derotation_matrix`; use `page.rect` for page bounds; include rotated CAD PDFs in the test corpus from day one
3. **Redaction covers but does not remove** — `apply_redactions()` is mandatory; post-redaction `get_text()` assertion over the region must return empty; `PDF_REDACT_TEXT_NONE` is forbidden in this product
4. **Vector stroke survivors and CAD over-deletion** — pad drawn rect ~5pt; default to `REMOVE_IF_COVERED`; before/after preview is the primary defense against silent over-deletion
5. **AGPL licensing coupling** — isolate `fitz` behind a clean service-API boundary now; document the license decision; re-check before the website-embedding milestone

---

## Implications for Roadmap

### Suggested Phase Structure (7 phases, dependency-ordered)

1. **Storage, Ingest, and Preservation** — foundation; upload endpoint, type validation, image-to-PDF normalization, three-directory isolation, content-type classification, Docker skeleton. Nothing else can be built without this.

2. **Render Service and Preview Viewer** — `get_pixmap(dpi)` endpoint plus page metadata; browser page viewer with navigation and zoom. Hard prerequisite for the Coordinate Mapper (supplies page dimensions and rotation).

3. **Coordinate Mapper (test-heavy — the spine)** — pure `coords.py` module with `pixels_to_pdf_rect` and inverse; handles DPI scale, `derotation_matrix`, `page.rect` for MediaBox offset; visual round-trip test harness at 0/90/180/270 degrees. Do not write any redaction code until this phase's tests pass.

4. **Region Selection UI** — canvas overlay in `regions.js`; per-page region list in image-pixel space; region kind tag (vector vs image); logo picker; job-spec assembly; deferred-mutation model in browser.

5. **Removal Pipeline + Before/After Preview** — `remove_vector` and `fill_raster` branches in `redact.py`; ~5pt rect padding; post-redaction extraction assertion; transparent-image segfault guard; before/after preview endpoint; export with garbage collection. This is the core value; preview belongs here, not later.

6. **Logo Library and Insertion** — `logo.py` with `insert_image(..., keep_proportion=True)`, alpha-channel handling, `xref` reuse, vector logo via `show_pdf_page()`.

7. **Output, Download, and Cleanup** — download endpoint, retention janitor, original-checksum assertion, Nginx configuration.

### Phase Ordering Rationale

Storage → Render (render needs files) → Coordinate Mapper (mapper needs page metadata from render) → Region UI (UI produces what mapper consumes; mapper must be proven first) → Removal + Preview (depends on mapper and region spec) → Logo Insertion (insert after removal) → Output/Cleanup (depends on full pipeline).

### Research Flags

All seven phases follow well-documented patterns — no additional phase-research calls are needed. What is needed instead:
- **Phase 3:** Assemble a test corpus (PDFs at 0/90/180/270 degrees, offset MediaBox, vector and raster) before writing any code.
- **Phase 5:** Obtain a real large CAD supplier PDF to surface performance issues and OCG layer behavior during development.
- **Licensing checkpoint (before website-embedding):** Re-verify external reachability. If external users interact over the network, acquire the Artifex commercial license or keep the PDF service on an internal-only boundary.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core capabilities verified against official PyMuPDF docs and PyPI; apply_redactions flags and defaults confirmed; version compatibility matrix confirmed |
| Features | HIGH | True-removal behavior confirmed; insert_image aspect-preservation confirmed; deferred-mutation model backed by issue tracker evidence |
| Architecture | HIGH | Coordinate mapping formulas verified against PyMuPDF docs; build order is dependency-derived; anti-patterns documented with evidence |
| Pitfalls | HIGH (mechanics) / MEDIUM (AGPL legal) | Redaction mechanics, coordinate edge cases, and image gotchas verified; AGPL section 13 interpretation is a legal call, not a code call |

**Overall confidence:** HIGH

### Gaps to Address During Implementation

- **Background-color sampling parameters:** median-border-ring approach is sound; ring width and method need tuning against real supplier files during Phase 5. Descope to white-only for v1 if sampling adds unacceptable complexity.
- **`apply_redactions` edge cases on CAD files:** `REMOVE_IF_COVERED` vs `REMOVE_IF_TOUCHED` choice and ~5pt padding may need per-file tuning. Build a visual regression suite against real supplier PDFs during Phase 5.
- **OCG / hidden-layer policy:** decide whether to redact across all layers, only visible layers, or warn the user. Determine during Phase 5 testing.
- **CMYK colorspace policy:** decide RGB vs CMYK output before Phase 6. RGB normalization is safe for screen use; print output may require CMYK preservation.
- **Large CAD file performance bounds:** calibrate DPI cap and max-pixel-budget against the target Ubuntu hardware during Phase 2.

---

## Sources

**Primary (HIGH):** PyMuPDF official docs (page.html, app3.html — redaction flags, derotation_matrix, 72pt baseline, top-left origin); PyMuPDF PyPI (1.27.2.x, AGPL/Artifex); Pillow PyPI (12.x, Python >=3.10); FastAPI docs; Uvicorn deploy guide; Artifex licensing page + PyMuPDF discussion #971; PyMuPDF OCG recipes.

**Secondary (MEDIUM):** PyMuPDF GitHub issues #2762, #3278, #3433, #1819, #2644, #1824, #1216, #4091, #1220, #3439, #3440, #4657; PDF.js issues #6471 (PageViewport API, evaluated and rejected for preview); PyMuPDF discussion #1806 (coordinate system); Artifex blog (insert_image aspect-preservation).

**Tertiary (LOW–MEDIUM):** PDF.js issue #20146 (confirms no built-in rectangle annotation); general security practice for C-backed parser isolation.

---

*Research completed: 2026-05-22*
*Ready for roadmap: yes*
