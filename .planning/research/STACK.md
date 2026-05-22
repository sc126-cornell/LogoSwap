# Stack Research

**Domain:** Internal web tool for PDF/image logo replacement (manual redaction + logo placement) on Ubuntu
**Researched:** 2026-05-22
**Confidence:** HIGH (core PDF + framework + deployment verified against official docs / PyPI; frontend coordinate API verified against PDF.js docs)

## Executive Recommendation

Build a **single-process FastAPI service** (Python 3.12) that does all PDF/image work with **PyMuPDF (fitz) 1.27.x** plus **Pillow + NumPy** for raster fill/background sampling. Serve a **vanilla JS + PDF.js (pdfjs-dist 5.x)** frontend with a transparent `<canvas>`/`<div>` overlay for rectangle drawing, mapping pixels → PDF points via PDF.js `convertToPdfPoint`. Deploy as a **single Docker container** running **Uvicorn** behind **Nginx** (reverse proxy) on the Ubuntu box.

This is deliberately a "boring", low-moving-parts stack: one language for processing, one container, no database, no auth in v1 — which matches the internal/single-file/manual-selection scope and keeps future embedding easy (it's just an HTTP API + static frontend).

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | **3.12.x** | Runtime for backend + PDF processing | 3.12 is a stable, widely-supported sweet spot. PyMuPDF 1.27 and Pillow 12 both ship prebuilt wheels for 3.10–3.14, so 3.12 has zero compatibility risk. Avoid 3.14 (too new for some transitive deps) and ≤3.9 (Pillow 12 requires ≥3.10). **HIGH** |
| **PyMuPDF (`fitz`)** | **1.27.x** (latest 1.27.2.x; pin `>=1.27,<1.28`) | Core PDF read/render/redact/export; the project-mandated library | Confirmed correct for the core requirement. `Page.add_redact_annot(rect, ...)` + `Page.apply_redactions()` **truly removes** underlying text and vector objects within the rectangle (not a cover-up), and blanks/removes overlapping image pixels. Also renders pages to pixmaps for the preview fallback and reads page dimensions in PDF points. **HIGH** — see "PyMuPDF redaction" section below. |
| **FastAPI** | **0.115.x+** (pin `>=0.115,<1.0`) | Backend web framework: file upload endpoint + processing API | Native, first-class `UploadFile` streaming, Pydantic request validation (region rectangles, page indices, chosen logo id), and auto-generated OpenAPI docs — the OpenAPI schema makes the *future* embedding into the colleague's approval site trivial (well-typed API contract for them to call). ASGI/`async` is a clean fit for "upload → kick off work → return file". **HIGH** |
| **Uvicorn** | **0.34.x+** | ASGI server running the FastAPI app | The reference ASGI server for FastAPI. Modern Uvicorn (0.30+) has a built-in multi-process supervisor (`--workers`), so for an internal low-concurrency tool you do **not** need Gunicorn as a process manager. Run a few workers, restart-on-failure handled by the container/systemd. **HIGH** |
| **PDF.js (`pdfjs-dist`)** | **5.x** (latest 5.7.x, Apr 2025; pin a known 5.x) | In-browser PDF rendering for preview + page navigation | The de-facto standard, dependency-free browser PDF renderer. Critically, its `PageViewport` exposes **`convertToPdfPoint(x, y)`** and **`convertToViewportPoint(x, y)`**, which do the exact pixel↔PDF-point↔rotation↔scale mapping this tool needs, so drawn rectangles round-trip to the backend as correct PDF coordinates regardless of zoom/rotation. **HIGH** |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **Pillow** | **12.x** (latest 12.2.0; requires Python ≥3.10) | Decode/inspect logo PNG/JPG/TIFF; preview standalone image files; light image manipulation | Always. Needed for the **standalone image upload path** (PNG/JPG/TIFF) and to validate/normalize the in-app logo library assets before placing them. **HIGH** |
| **NumPy** | **2.x** (pin `>=1.26` to allow 2.x) | Sample surrounding background color for raster fill; fast pixel-region math | When a raster/image region must be filled with the **surrounding background color** rather than plain white. PyMuPDF pixmaps expose `.samples` as bytes → load into a NumPy array, sample a border ring of pixels, compute the median/mode color, then fill. Plain-white fill alone does not need NumPy. **MEDIUM** (the sampling approach is sound; exact "median border ring" heuristic should be tuned during the raster phase) |
| **python-multipart** | latest (e.g. `>=0.0.9`) | Required dependency for FastAPI `UploadFile` / form uploads | Always (FastAPI requires it for multipart file uploads). **HIGH** |
| **Pydantic** | **2.x** (ships with FastAPI 0.115) | Validate the region payload (page index, x/y/w/h in PDF points, logo id, fill mode) | Always — comes transitively with FastAPI; use it to make the region/job request schema explicit and self-documenting. **HIGH** |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Fast Python dependency & venv management | Recommended over raw pip for reproducible installs and fast Docker builds. Generates a lockfile; use `uv pip install` or `uv sync`. Not mandatory — pip + `requirements.txt` works fine if the team prefers familiarity. |
| **Ruff** | Lint + format (replaces black + flake8 + isort) | Single fast tool, near-zero config. Optional but cheap to adopt. |
| **Docker / Docker Compose** | Containerization for the Ubuntu deploy | Compose to wire app container + Nginx; multi-stage Dockerfile to keep image small. |
| **No frontend build step (v1)** | Keep frontend as plain HTML/JS/CSS + `pdfjs-dist` served statically | Avoids a Node/Vite/Webpack toolchain for what is one interactive page. Add a bundler only if the UI grows. |

## Installation

```bash
# Backend (Python) — core
pip install "PyMuPDF>=1.27,<1.28" "fastapi>=0.115,<1.0" "uvicorn[standard]>=0.34" \
            "Pillow>=12,<13" "numpy>=1.26" "python-multipart>=0.0.9"

# (Pydantic 2.x is pulled in by FastAPI automatically)

# Optional dev tooling
pip install ruff
# or use uv:  uv add "PyMuPDF>=1.27,<1.28" fastapi "uvicorn[standard]" Pillow numpy python-multipart

# Frontend — fetch PDF.js distribution (no npm build needed; vendor the dist files)
npm pack pdfjs-dist        # grab the 5.x tarball, or download the prebuilt build
# then serve build/pdf.mjs + build/pdf.worker.mjs as static assets
```

## PyMuPDF redaction — confirms the core "true removal" requirement (HIGH)

This is the load-bearing capability of the whole project, so it is verified explicitly against the official `Page` docs:

- **Mark a region:** `page.add_redact_annot(rect, fill=(1, 1, 1))` — `fill` defaults to **white `(1,1,1)`**, the color painted into the rectangle *after* redaction. This directly satisfies "raster region filled with white"; pass a sampled color tuple to satisfy "filled with surrounding background color".
- **Apply (this is where true removal happens):** `page.apply_redactions(images=..., graphics=..., text=...)`:
  - `text=PDF_REDACT_TEXT_REMOVE` (default `0`) — **removes the underlying text**, not just covers it. ✔ vector/text requirement
  - `graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED` (default `1`) — removes overlapping **vector graphics**; `PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED` (`2`) removes any vector art touching the rect. ✔ vector logo removal
  - `images=PDF_REDACT_IMAGE_PIXELS` (default `2`) — **blanks the overlapping pixels** of an image; `PDF_REDACT_IMAGE_REMOVE` (`1`) drops the whole overlapping image. ✔ raster/image requirement
- **Then place the company logo:** `page.insert_image(target_rect, filename=logo_path)` (or `stream=`/`pixmap=`) scaled to the region.
- **Preserve original:** never write back to the uploaded path — `doc.save(new_path, ...)` (or `doc.save(..., garbage=4, deflate=True)` for a clean, compacted output) to a fresh file. ✔ "original must be preserved".

**Known gotcha to flag for the build phase (MEDIUM):** there are several reported GitHub issues where `apply_redactions()` can affect text/graphics *outside* the marked rectangle in edge cases (e.g. #2762, #3278), and `REMOVE_IF_COVERED` vs `REMOVE_IF_TOUCHED` behave differently on partially-overlapping vector art. The vector-removal phase should include visual regression checks on real supplier PDFs and deliberate choice of the `graphics` constant. This is a tuning risk, not a feasibility blocker.

## PyMuPDF licensing — addressed (HIGH on facts, MEDIUM on "does it matter here")

- **License:** PyMuPDF is **dual-licensed: GNU AGPL v3.0 OR a commercial license from Artifex.** (PyPI classifier: "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License".)
- **Why AGPL matters more than GPL here:** AGPL's section 13 extends copyleft to **network/SaaS use** — normally, *offering software over a network to users* counts as conveying it, triggering the obligation to offer those users the corresponding source. This is exactly the "it's just an internal web app, we never ship a binary" case people get wrong.
- **Does it matter for THIS project?** **Likely no obligation in v1, but verify before any external exposure:**
  - The tool is **internal-only, on the company LAN, no external users** (per PROJECT.md: 內網免登入). AGPL obligations are triggered by conveying to / interacting with **third parties / outside users**; purely internal use within one organization is generally treated as not "conveying" to outsiders, so the AGPL source-offer obligation typically does not bite. (Multiple community/Artifex discussions state internal use "should be no problem.")
  - **The risk surfaces if scope changes:** if this later gets embedded into a site that **external partners/suppliers can reach**, or is offered to other companies, AGPL's network clause would then require offering source to those users — or buying Artifex's commercial license.
- **Recommendation:**
  1. v1 (internal LAN, no external access): proceed on **AGPL**, no purchase needed. Keep a note in the repo that the PDF engine is AGPL.
  2. Before the *future* "embed into approval website" milestone, **re-confirm who can reach that site.** If anyone outside the company can, get the commercial license (or keep the PDF service on an internal-only network boundary). 
  3. If legal wants zero ambiguity even for internal use, Artifex sells an inexpensive commercial license — cheap insurance, but not required for the stated v1 scope.
  - **Action item for roadmap:** flag a "licensing re-check" gate at the embedding milestone. Do not treat AGPL as a blocker for v1.

## Frontend coordinate mapping — how rectangles round-trip (HIGH)

Recommended approach (the standard PDF.js pattern):

1. Render page to a `<canvas>` at a chosen `scale` using `page.getViewport({ scale })` + `page.render(...)`.
2. Stack a transparent overlay (`<div>` or second `<canvas>`) **exactly over** the page canvas (same CSS box). Capture mouse down/move/up to draw the rubber-band rectangle in *screen/pixel* space — easy for the user.
3. On commit, convert the two corner pixel points to PDF points with **`viewport.convertToPdfPoint(x, y)`** (handles the bottom-left PDF origin vs top-left canvas origin, plus scale and rotation). Send `{ page, x0, y0, x1, y1 }` in **PDF points** to the backend.
4. Backend reconstructs a `fitz.Rect` from those points and feeds it to `add_redact_annot`. Because PDF.js does the math, alignment holds at any zoom — **do not hand-roll the scale/rotation math.**
5. **Standalone images (PNG/JPG/TIFF):** render directly in an `<img>`/`<canvas>` (no PDF.js); the same overlay drawing logic applies, and the backend treats it as a one-"page" raster: coordinates are plain pixels, fill via Pillow/NumPy, then optionally wrap into a PDF on export via PyMuPDF.

## Deployment on Ubuntu — process model & containerization (HIGH)

Recommended topology (single host, internal network):

```
[Browser on LAN]
      │  HTTP(S)
      ▼
   [Nginx]  ── reverse proxy, serves static frontend + /api proxy,
      │         request body size limit, optional TLS termination
      ▼
  [Uvicorn]  ── FastAPI app, 2–4 workers (internal low concurrency)
      │
      ▼
 PyMuPDF / Pillow / NumPy  (in-process)
```

- **Process model:** Run **Uvicorn directly with `--workers N`** (modern Uvicorn 0.30+ has a built-in supervisor). For an internal tool with light, bursty use, `workers = 2–4` is plenty; don't over-engineer with Gunicorn unless you later need its richer worker management. Use `uvicorn[standard]` for the C-accelerated event loop/HTTP.
  - **Caveat (MEDIUM):** PDF redaction on a large scanned PDF is **CPU-bound and can block a worker for seconds.** Run the heavy work in a threadpool (`run_in_threadpool` / `def` endpoint) or as a FastAPI `BackgroundTask` so a single big job doesn't stall the request loop. Full Celery/queue is **overkill for v1** (single user, single file, manual) — defer it to the batch-processing milestone.
- **Containerization:** One **multi-stage Docker image** (build deps → slim runtime), plus a **docker-compose.yml** wiring `app` + `nginx`. Add a `HEALTHCHECK` hitting a `/health` endpoint. Mount a volume for transient uploads/outputs and a separate read-only volume/baked-in dir for the fixed logo library.
  - Use a slim base (`python:3.12-slim`). PyMuPDF and Pillow ship manylinux wheels, so no system build toolchain is needed at runtime — keep the final image lean.
- **Embeddability (future-proofing, per constraints):** Keep the **frontend a static bundle** and the **backend a clean JSON/file HTTP API** with no hard assumptions about being at the site root. Concretely: make the API base path configurable (env var / Nginx prefix like `/pdf-logo/`), avoid server-side sessions, and rely on FastAPI's OpenAPI schema as the integration contract. Then the colleague's approval site can either iframe the static UI or call the API directly with near-zero changes.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastAPI | **Flask** | If the team has deep Flask experience and wants the simplest possible WSGI app. Flask can do file upload fine, but lacks built-in async, typed validation, and auto OpenAPI — and OpenAPI is genuinely useful for the future embedding contract. Choose Flask only on strong team-familiarity grounds. |
| FastAPI | **Django / DRF** | Only if you expect to grow into auth, admin, ORM, and many models. For a single-purpose, no-DB, no-auth tool it's heavy overkill in v1. |
| Uvicorn `--workers` | **Gunicorn + UvicornWorker** | If you later need advanced worker lifecycle management, graceful rolling restarts, or per-worker timeouts under real multi-user load. Fine to adopt at the embedding/scale milestone; unnecessary for internal v1. |
| PyMuPDF | **pikepdf / qpdf** | pikepdf is excellent for low-level PDF structure surgery but does **not** render pages or provide a turnkey redaction-with-fill API. Could be a complementary tool if you hit a structural edge case PyMuPDF can't express — not a replacement. |
| PyMuPDF | **pypdf** | Good for merge/split/metadata, but it does **not truly remove** content under a region or render — wrong tool for the core requirement. |
| Pillow + NumPy white/median fill | **OpenCV inpainting / LaMa AI inpainting** | Explicitly **out of scope** per PROJECT.md (no background reconstruction). Only revisit if users later demand seamless background restoration — adds a heavy dependency and GPU/compute cost. |
| Vanilla JS + PDF.js | **react-pdf / ngx-extended-pdf-viewer** | If the UI grows into a larger SPA with React/Angular already in play. For one interactive page, a framework adds a build pipeline and bundle weight for little gain. |
| Nginx | **Caddy** | If you want automatic HTTPS with near-zero config. Great choice too; pick Nginx if the team already standardizes on it (common on Ubuntu). |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **pypdf / PyPDF2 for the removal step** | They cannot truly delete content within a region (no real redaction); covering ≠ removing — violates the core value. | PyMuPDF `apply_redactions`. |
| **Just drawing a white rectangle over the logo (any lib)** | The supplier text/vector objects remain in the file and are recoverable — exactly the failure mode this tool exists to prevent. | PyMuPDF redaction (`text`/`graphics`/`images` removal). |
| **Hand-rolled pixel↔point math in the frontend** | Easy to get scale/rotation/origin wrong; misaligned rectangles silently redact the wrong area. | PDF.js `viewport.convertToPdfPoint` / `convertToViewportPoint`. |
| **Celery + Redis/RabbitMQ in v1** | A full task queue is operational overhead for a single-user, single-file, manual tool. | FastAPI `BackgroundTasks` / threadpool now; add a queue at the batch milestone. |
| **A database in v1** | No persistent entities are required (stateless: upload → process → download; fixed logo library is just files). Adds ops surface for nothing. | Filesystem for transient files + a folder/JSON manifest for the logo library. |
| **Auth framework in v1** | Out of scope (internal LAN, no login). Adding it now slows delivery. | Network-level access control (internal network / Nginx allowlist) for v1; real auth at the embedding milestone. |
| **`PyMuPDFb` pinned separately / mixing with old `fitz` PyPI package** | The unrelated PyPI package literally named `fitz` is **not** PyMuPDF and will break imports; PyMuPDF installs the `fitz` module itself. | Install only `PyMuPDF`; never `pip install fitz`. |
| **Python ≤3.9** | Pillow 12 requires ≥3.10; you'd be stuck on old Pillow. | Python 3.12. |

## Stack Patterns by Variant

**If the uploaded file is a vector PDF:**
- Redact with `text=PDF_REDACT_TEXT_REMOVE` + `graphics=REMOVE_IF_COVERED` (or `REMOVE_IF_TOUCHED` after testing), then `insert_image` the company logo. No raster fill needed beyond the annot `fill`.

**If the uploaded file is an image/raster PDF (scanned page):**
- The region overlaps an image XObject → `images=PDF_REDACT_IMAGE_PIXELS` blanks those pixels; set annot `fill` to white or a NumPy-sampled background color, then place the logo.

**If the uploaded file is a standalone image (PNG/JPG/TIFF):**
- Skip PDF.js for rendering; do the fill with Pillow/NumPy directly on the raster, paste the logo, then (on export) wrap the result into a PDF via PyMuPDF so the output is consistently a PDF.

**If/when the tool is embedded into the approval website (future):**
- Re-verify the AGPL exposure (external reachability). Make API base path configurable; keep frontend static and stateless so it can be iframed or API-driven.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| PyMuPDF 1.27.x | Python 3.10–3.14 | Prebuilt wheels for all; no MuPDF build needed. **3.12 recommended.** |
| Pillow 12.2.0 | Python ≥3.10 | Drops 3.9 — reinforces Python 3.12 choice. |
| FastAPI 0.115.x | Pydantic 2.x, Uvicorn 0.34+ | Pydantic 2 is bundled; ensure any extra libs are Pydantic-2 compatible. |
| NumPy 2.x | Python ≥3.10, Pillow 12 | NumPy 2 is fine with current Pillow/PyMuPDF; pin `>=1.26` if a transitive dep still wants 1.x. |
| pdfjs-dist 5.x | Modern evergreen browsers (ES modules) | Uses `.mjs` builds + a worker file; serve both `pdf.mjs` and `pdf.worker.mjs`. Internal users on current Chrome/Edge/Firefox = fine. |

## Sources

- https://pypi.org/pypi/PyMuPDF/json — PyMuPDF latest **1.27.2.x**, Python **3.10–3.14**, license classifier "**Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License**" (HIGH)
- https://pymupdf.readthedocs.io/en/latest/page.html — `apply_redactions` params/defaults (`text=PDF_REDACT_TEXT_REMOVE|0`, `graphics=...REMOVE_IF_COVERED|1`, `images=...IMAGE_PIXELS|2`) and `add_redact_annot(fill=(1,1,1))` (HIGH — true removal + white fill confirmed)
- https://artifex.com/licensing and https://github.com/pymupdf/PyMuPDF/discussions/971 — dual AGPL/commercial; AGPL network clause; internal-use guidance (HIGH on facts, MEDIUM on internal-use interpretation — confirm with Artifex before external exposure)
- https://github.com/pymupdf/PyMuPDF/issues/2762 , /issues/3278 — reported redaction edge cases affecting content outside the rect (MEDIUM — tuning risk flag)
- https://pypi.org/pypi/pillow/json — Pillow **12.2.0**, Python **≥3.10** (HIGH)
- https://github.com/mozilla/pdf.js/releases — pdf.js **v5.7.284** (Apr 27, 2025); npm dist package is `pdfjs-dist` (HIGH on version; MEDIUM that the WebFetch didn't echo the package name — `pdfjs-dist` is the well-known npm name)
- https://github.com/mozilla/pdf.js/issues/6471 , /issues/12003 — `PageViewport.convertToPdfPoint` / `convertToViewportPoint` exist and do pixel↔PDF-point mapping incl. rotation/scale (HIGH)
- https://fastapi.tiangolo.com/tutorial/background-tasks/ and FastAPI/Flask 2025/2026 comparisons — `UploadFile`, `BackgroundTasks`, async rationale (HIGH on FastAPI capabilities; MEDIUM on opinionated comparison sources)
- https://uvicorn.dev/deployment/ and FastAPI production-deploy guides (2026) — Uvicorn `--workers` built-in supervisor; Nginx reverse proxy + Docker multi-stage; `(2*cores)+1` heuristic (HIGH)

---
*Stack research for: internal PDF/image logo-replacement web tool (manual redaction)*
*Researched: 2026-05-22*
