---
phase: 01-input-preview
plan: 01
subsystem: api
tags: [fastapi, pymupdf, fitz, uvicorn, pydantic, pillow, pytest, render, upload, agpl-isolation]

# Dependency graph
requires:
  - phase: (none — first plan of first phase)
    provides: greenfield
provides:
  - "FastAPI backend (uvicorn app.main:app) with /health"
  - "POST /sessions upload endpoint: vector PDF -> session_id + page_count (201), structured 4xx on bad input"
  - "GET /sessions/{id} session lookup (404 session_not_found)"
  - "GET /sessions/{id}/pages/{n}/image: server-rendered PNG at 200 DPI default + six X-... coordinate-seam headers"
  - "GET /sessions/{id}/pages/{n}/meta: PageMeta JSON for pre-load page sizing"
  - "Three-directory storage (originals/work/outputs) with write-once read-only original (UPLOAD-04)"
  - "PyMuPDF isolation seam (app/services/pdf_engine.py) — sole fitz importer (AGPL)"
  - "Render metadata contract (dpi, page_w_pt, page_h_pt, rotation, img_w, img_h) for Phase 2 coordinate mapper"
affects: [01-02 frontend preview viewer, 02-coordinate-mapper, 02-region-removal, 05-deployment]

# Tech tracking
tech-stack:
  added: [PyMuPDF 1.27.2.3, FastAPI 0.136.1, uvicorn 0.47.0, Pillow 12.2.0, python-multipart 0.0.29, pydantic 2.13.4, pytest 9.0.3, httpx 0.28.1]
  patterns:
    - "AGPL isolation seam: all fitz access routed through one swappable engine module"
    - "Server-authoritative render: backend rasterizes; render DPI + page metadata exposed for coordinate seam"
    - "Three-directory write-once preservation: original chmod 0o444, work copy edited, outputs reserved"
    - "Typed service errors (IngestError/RenderError/PdfEngineError) -> structured {detail:{code,message}} 4xx, never bare 500"

key-files:
  created:
    - requirements.txt
    - .gitignore
    - pytest.ini
    - app/config.py
    - app/storage.py
    - app/models.py
    - app/services/pdf_engine.py
    - app/services/ingest.py
    - app/services/render.py
    - app/api/sessions.py
    - app/api/pages.py
    - app/main.py
    - tests/conftest.py
    - tests/test_storage.py
    - tests/test_ingest.py
    - tests/test_render.py
    - tests/test_api.py
  modified: []

key-decisions:
  - "Python 3.14.4 used (env-provided); PyMuPDF installs via cp310-abi3 stable-ABI wheel — no source build, no blocker"
  - "Original filename not persisted as sidecar metadata in Phase 1; GET /sessions reports canonical 'source.pdf' (UI gets real name from POST response)"
  - "Upload size guard enforced by streaming read in the route (reject before fully buffering) AND re-checked in ingest"
  - "X-Render-Dpi reflects the ACTUAL clamped DPI used, not the requested value (D-03)"

patterns-established:
  - "Engine seam: import fitz appears in exactly one file (pdf_engine.py); render.py/ingest.py call wrappers"
  - "Lazy DATA_DIR read in storage so tests monkeypatch config.DATA_DIR to tmp_path (autouse fixture)"
  - "In-memory PDF fixtures built via fitz in conftest (no committed binaries)"

requirements-completed: [UPLOAD-01, UPLOAD-04, PREVIEW-01, PREVIEW-02]

# Metrics
duration: ~30min
completed: 2026-05-22
---

# Phase 1 Plan 01: 後端骨架(FastAPI)Backend Skeleton Summary

**FastAPI service that ingests a vector PDF, preserves the original write-once under a three-directory layout, and serves each page as a PyMuPDF-rendered PNG at 200 DPI with exact render-DPI + page-metadata headers for Phase 2's coordinate seam — fitz isolated to one AGPL-seam module; 35 tests pass.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-22T06:03:00Z (approx)
- **Completed:** 2026-05-22T06:33:00Z
- **Tasks:** 2
- **Files created:** 17 source/test files + requirements.txt/.gitignore/pytest.ini

## Accomplishments

- Runnable FastAPI app (`uvicorn app.main:app`) with upload → immutable store → server render → page PNG, plus `/health`.
- **Original preservation is structural (UPLOAD-04):** original written once to `originals/{sid}` and chmod 0o444; all reads use the `work/{sid}` copy; an automated test hashes the original before/after a full ingest+render cycle and asserts equality.
- **PyMuPDF (fitz) AGPL isolation seam:** `import fitz` appears in exactly one file, `app/services/pdf_engine.py`; `render.py` and `ingest.py` are engine-agnostic and call thin wrappers.
- **Render endpoint exposes the coordinate seam (D-03):** PNG at default 200 DPI carrying `X-Page-Width-Pt`, `X-Page-Height-Pt`, `X-Page-Rotation`, `X-Render-Dpi`, `X-Image-Width-Px`, `X-Image-Height-Px`; scale is DPI-derived (verified `img_w == round(page_w_pt * dpi/72)`, e.g. 612pt → 1700px at 200 DPI).
- **DoS guards with limit-bearing messages (D-04 / T-01-01, T-01-02):** >50 MB → 413 `file_too_large` ("...50 MB"), >30 pages → 413 `too_many_pages` ("...30 頁"); render DPI clamped to [72, 300].
- **Parser isolation (Pitfall 11 / T-01-03, T-01-08):** non-PDF/empty/corrupt input returns structured `{detail:{code,message}}` 4xx via global exception handlers — never a bare 500 leaking internals.

## Task Commits

Each task was committed atomically:

1. **Task 1: Project scaffold + three-directory storage + ingest with original preservation** — `c8a4303` (feat)
2. **Task 2: Render service + FastAPI app (upload, session, page-image, meta, health)** — `13c6ba9` (feat)

**Plan metadata:** (this SUMMARY + STATE/ROADMAP) — committed separately as `docs(01-01)`.

_Note: This plan is `type: execute` with `tdd="true"` tasks. Source and behavior-driven tests were authored together and committed once per task (both verified green before commit) rather than as separate RED/GREEN commits._

## Files Created/Modified

- `requirements.txt` — pinned deps (PyMuPDF>=1.27,<1.28; FastAPI; uvicorn[standard]; Pillow>=12,<13; python-multipart; pytest; httpx). Note: never `pip install fitz`.
- `.gitignore` — ignores `data/`, `__pycache__/`, `.venv/`, `*.pyc`, `.pytest_cache/`.
- `pytest.ini` — disables pytest cache (`-p no:cacheprovider`) to avoid a Dropbox file-lock warning on Windows; sets `testpaths = tests`.
- `app/config.py` — DEFAULT_DPI=200, MIN_DPI=72, MAX_DPI=300, MAX_UPLOAD_BYTES=50*1024*1024, MAX_PAGES=30, MAX_UPLOAD_MB (derived), API_TITLE; env-overridable.
- `app/storage.py` — `new_session`, `sanitize_filename`, `write_original` (write-once + chmod 0o444), `write_work_copy`, `original_path`/`work_path`/`outputs_dir`, `session_exists`, `subdir`.
- `app/models.py` — Pydantic v2 `SessionInfo`, `PageMeta`, `ErrorDetail` (exact `<interfaces>` shapes).
- `app/services/pdf_engine.py` — **sole fitz importer**; `open_pdf`, `page_count`, `render_page_to_png`, `page_dimensions`, `close`; `PdfEngineError`.
- `app/services/ingest.py` — `ingest_upload` (empty/oversize/sniff/parse/page-count guards, immutable original + work copy); `IngestError`.
- `app/services/render.py` — `render_page` -> `RenderResult` (PNG + img_w/h, page_w/h_pt, rotation, dpi), `page_meta`, `clamp_dpi`; `RenderError`.
- `app/api/sessions.py` — `POST /sessions` (streaming size guard, code→status map), `GET /sessions/{id}`.
- `app/api/pages.py` — `GET .../image` (six headers, threadpool render), `GET .../meta`.
- `app/main.py` — FastAPI app, router registration, `/health`, typed-error handlers, guarded `web/` StaticFiles mount.
- `tests/conftest.py` — in-memory PDF fixtures, autouse tmp DATA_DIR, `ingested_session`, `client`.
- `tests/test_storage.py`, `tests/test_ingest.py`, `tests/test_render.py`, `tests/test_api.py` — 35 tests total.

## Decisions Made

- **Python 3.14.4 (env-provided) instead of the research-recommended 3.12.** The env note flagged 3.14 as new and a possible blocker. Result: **no blocker** — `pip install` pulled prebuilt wheels for everything: PyMuPDF 1.27.2.3 via a `cp310-abi3` stable-ABI wheel (forward-compatible with 3.14), Pillow 12.2.0 via a `cp314` wheel. `import fitz` + `get_pixmap(dpi=...)` + `tobytes("png")` all verified working on 3.14.4. No source build occurred.
- **Resolved dep versions** (within the pinned ranges): FastAPI 0.136.1, uvicorn 0.47.0, pydantic 2.13.4, python-multipart 0.0.29, starlette 1.0.1, httpx 0.28.1, pytest 9.0.3.
- **GET /sessions filename:** Phase 1 does not persist a per-session metadata sidecar, so `GET /sessions/{id}` returns the canonical on-disk name `source.pdf`. The real client filename is returned by `POST /sessions` (which the frontend captures), so this does not block 01-02. A sidecar can carry the original name in a later phase if the UI needs it on reload.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reworded a docstring so the AGPL-seam grep stays unambiguous**
- **Found during:** Task 2 (render.py)
- **Issue:** `render.py`'s module docstring contained the literal phrase ``import fitz`` (in prose explaining the seam). The acceptance check `grep -rl "import fitz" app/` would have falsely flagged `render.py` as a second fitz importer, breaking the "exactly one file" guarantee the verifier checks.
- **Fix:** Reworded the docstring to "it never imports the engine library directly … the only module that imports fitz is `pdf_engine`" — no literal `import fitz` string.
- **Files modified:** `app/services/render.py`
- **Verification:** `grep -rl "import fitz" app/` now returns only `app/services/pdf_engine.py`; full suite still 35 passed.
- **Committed in:** `13c6ba9` (Task 2 commit)

**2. [Rule 3 - Blocking] Added pytest.ini to disable the pytest cache**
- **Found during:** Task 1 (first pytest run)
- **Issue:** pytest emitted a `PytestCacheWarning` because the repo lives in a Dropbox-synced folder and Dropbox transiently locks `.pytest_cache` on Windows (`WinError 32`). Tests passed but the warning was noise and could intermittently fail cache writes.
- **Fix:** Added `pytest.ini` with `addopts = -p no:cacheprovider` and `testpaths = tests`.
- **Files modified:** `pytest.ini` (new)
- **Verification:** Re-ran suite — warning gone, 35 passed.
- **Committed in:** `c8a4303` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking).
**Impact on plan:** Both are minor and necessary to keep the acceptance checks accurate and the test run clean. No scope creep; no behavior change to shipped endpoints.

## Issues Encountered

- **Bash tool uses POSIX bash, not PowerShell, on this Windows host.** Backslash venv paths (`.venv\Scripts\python.exe`) failed; switched to forward-slash paths (`./.venv/Scripts/python.exe`) which work. (The env banner says PowerShell, but the Bash tool shell is bash.)
- **Git line-ending warnings** (`LF will be replaced by CRLF`) on every staged file — benign Windows normalization, no action needed.

## Threat surface scan

No new security surface beyond the plan's `<threat_model>`. Mitigations implemented as specified: T-01-01 (upload size, streaming guard + ingest re-check), T-01-02 (page count + DPI clamp), T-01-03 (parser try/except → typed error), T-01-04 (filename sanitize + token session dirs), T-01-05 (write-once read-only original, hash-unchanged test), T-01-06 (content sniff not extension), T-01-07 (token_urlsafe session id), T-01-08 (handlers return only {code,message}). T-01-09 (audit log) and T-01-10 (retention janitor) remain `accept`/Phase 5 as planned.

## Known Stubs

None. All endpoints return real, data-backed responses (no hardcoded/placeholder data). The only guarded-absent feature is the `web/` static mount, which is intentionally created in Plan 01-02 and is guarded so the app boots without it.

## Next Phase Readiness

- **01-02 (frontend preview) is unblocked:** the exact API contract from `<interfaces>` is implemented and verified — `POST /sessions`, `GET /sessions/{id}`, `GET /sessions/{id}/pages/{n}/image?dpi=`, `GET /sessions/{id}/pages/{n}/meta`, `/health`. The frontend's `web/api.js` can target these directly; the static mount auto-activates once `web/` exists.
- **Phase 2 (coordinate mapper) carry-forward is in place:** every render response exposes the actual DPI + `page_w_pt`/`page_h_pt`/`rotation`/`img_w`/`img_h` (headers and `/meta`), which the px↔pt mapper consumes. No region/redaction/coords logic was built (correctly deferred).
- **To run locally:** `python -m venv .venv` → `./.venv/Scripts/python -m pip install -r requirements.txt` → `./.venv/Scripts/python -m uvicorn app.main:app --reload`.

## Self-Check: PASSED

- All 16 claimed created files verified present on disk (config, storage, models, pdf_engine, ingest, render, sessions, pages, main, 4 test files, requirements.txt, .gitignore, SUMMARY).
- Both task commits verified in git log: `c8a4303` (Task 1), `13c6ba9` (Task 2).
- Full test suite: 35 passed. `import fitz` in exactly one file. End-to-end smoke test (Letter PDF → 201 → 200-DPI PNG with six headers, img_w 1700 == 612*200/72) confirmed.

---
*Phase: 01-input-preview*
*Completed: 2026-05-22*
