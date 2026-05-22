# Walking Skeleton — PDF 商標替換工具 (PDF Logo Replacement Tool)

**Phase:** 1
**Generated:** 2026-05-22

## Capability Proven End-to-End

A user uploads a single vector PDF in the browser; the FastAPI backend writes the original immutably to `originals/`, copies it to a `work/` editing copy, opens it with PyMuPDF (fitz), and serves each page rasterized to PNG via `get_pixmap(dpi=...)`. The browser displays the exact server-rendered PNG inside a positioned page stage and lets the user page through every page — the original file is never mutated.

This single slice exercises the entire server-authoritative rendering architecture (HTTP upload → immutable storage → fitz render → browser display) that Phases 2–5 build on.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI 0.115.x + Uvicorn 0.34.x (ASGI), Python 3.12 | Native `UploadFile` streaming, Pydantic 2 validation, auto OpenAPI schema (future embedding contract). Locked by research. |
| PDF engine | PyMuPDF (fitz), pinned `>=1.27,<1.28` | Project-mandated; `get_pixmap` for preview now, `apply_redactions` for true removal in Phase 2. Isolated behind `app/services/pdf_engine.py` so the AGPL engine is swappable. |
| Image library | Pillow `>=12,<13` | Image decode/validation; standalone-image ingest in Phase 4. Imported but minimally used in Phase 1. |
| Rendering model | Server-authoritative — backend rasterizes pages to PNG; browser displays exact `<img>`. NO PDF.js / client-side PDF rendering. | Eliminates the rendering-engine coordinate mismatch that breaks region selection in Phase 2. Overrides the PDF.js mention in STACK.md (SUMMARY.md/ARCHITECTURE.md decision). |
| Data layer | Filesystem only — three-directory separation `data/originals/{sid}`, `data/work/{sid}`, `data/outputs/{sid}`. NO database. | No persistent entities in v1; originals/work/outputs separation makes accidental mutation structurally impossible (UPLOAD-04). |
| Original preservation | Write-once to `originals/` (set read-only), edit only a copy in `work/`, never reopen the original for writes. | Hard UPLOAD-04 guarantee; preservation is structural, not procedural. |
| Auth | None (internal LAN, no login) | Out of scope for v1 per PROJECT.md. Network-level access control later. |
| Session model | Stateless server, `session_id` = random token (`secrets.token_urlsafe`); state keyed by session dir on disk. No server-side session objects, no cookies. | Keeps the API embeddable (iframe / direct API call) without session coupling. |
| Frontend | Vanilla HTML/CSS/JS, NO build step, NO framework. Design tokens as CSS custom properties per UI-SPEC. | Locked by stack; one interactive page does not need a bundler. |
| API seam | All browser↔server traffic flows through `web/api.js`; API base path read from `window.PDFTOOL_API_BASE` (default `""`). | The single embedding seam — host site overrides base URL with zero other changes. |
| Coordinate seam (carry-forward) | Render endpoint returns exact `dpi`, `page_w_pt`, `page_h_pt`, `rotation`, `img_w`, `img_h`. Page image sits in a `position: relative` page stage; image is NOT letterboxed/detached from its true render box. | Phase 2 maps browser pixels ↔ PDF points; the metadata + positioned stage are the prerequisites. Phase 1 builds NO region selection. |
| Deployment target | Local dev run: `uvicorn app.main:app --reload`, static frontend served by FastAPI `StaticFiles` at `/`. Docker/Nginx deferred to Phase 5. | Thinnest working full-stack run for the skeleton; production packaging is a later phase. |
| Directory layout | `app/` (api/ + services/ + models.py + storage.py + config.py), `web/` (static frontend), `data/` (gitignored runtime), `tests/`. | Matches ARCHITECTURE.md recommended structure; service modules added per-phase. |
| Dependency management | `requirements.txt` with pinned ranges (pip-installable). `uv` optional. | Familiar, reproducible; no lockfile complexity required for v1. |

## Stack Touched in Phase 1

- [x] Project scaffold — `app/` package, `requirements.txt`, `.gitignore`, FastAPI app with `StaticFiles` mount, `/health` endpoint, lint config (Ruff, optional)
- [x] Routing — real routes: `POST /sessions`, `GET /sessions/{id}`, `GET /sessions/{id}/pages/{n}/image`
- [x] Data layer — real write (original → `originals/`, copy → `work/`) AND real read (open `work/` PDF, render page to PNG)
- [x] UI — interactive upload control + page navigator wired to the API via `web/api.js`; server-rendered page PNG displayed in a positioned page stage
- [x] Deployment — documented local full-stack run command (`uvicorn app.main:app --reload`) that exercises upload → store → render → display

## Out of Scope (Deferred to Later Slices)

Explicit — this list prevents later phases from re-litigating Phase 1's minimalism:

- Region drawing / rectangle selection / canvas overlay — **Phase 2** (the page stage is built overlay-ready, but NO overlay or drawing logic ships now)
- Coordinate mapping module (`coords.py`) and px↔pt round-trip tests — **Phase 2** (Phase 1 only EXPOSES the render metadata the mapper will consume)
- True removal / redaction (`add_redact_annot`, `apply_redactions`) — **Phase 2**
- Before/after preview, download/export of processed PDF — **Phase 2**
- Logo library, logo selection, logo insertion — **Phase 3**
- Image-type (raster/scanned) PDF handling and standalone image upload (PNG/JPG/TIFF) — **Phase 4** (the upload `accept` list and copy are written to extend, but only vector PDF is the Phase 1 target)
- Raster fill-white removal branch — **Phase 4**
- Docker, Nginx, multi-worker tuning, retention janitor, large-page/rotated-page DPI caps, original-checksum verification job — **Phase 5**
- Background-color sampling fill (NumPy) — v1.x / Phase 5 tuning
- Auth, accounts, batch upload, website embedding — v2 (out of scope)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 2:** User can draw rectangles on the page, the regions truly remove vector/text content (proven by the `coords.py` round-trip harness first), see before/after, and download the new PDF.
- **Phase 3:** User can pick a company logo from a fixed library and place it (aspect-ratio preserved) in the removed region.
- **Phase 4:** User can upload image-type PDFs and standalone images (PNG/JPG/TIFF); raster regions fill white.
- **Phase 5:** Tool is packaged for Ubuntu (Docker + Nginx), handles large/rotated pages, cleans temp files, and verifies originals by checksum.
