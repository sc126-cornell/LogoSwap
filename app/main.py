"""FastAPI application: route registration, /health, error handlers, static mount.

Run locally with::

    uvicorn app.main:app --reload

Global exception handlers convert the service-layer typed errors
(:class:`IngestError`, :class:`RenderError`, :class:`PdfEngineError`) into the
structured ``{"detail": {"code", "message"}}`` JSON with a mapped status, so malformed
or untrusted input never escapes as a bare 500 that leaks internals (Pitfall 11 /
threat T-01-08). The web/ frontend (built in Plan 01-02) is mounted at ``/`` only when
the directory exists, so the app still imports and boots without it.
"""

from __future__ import annotations

import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, storage
from .api import logos, pages, process, sessions
from .services import janitor
from .services.ingest import IngestError
from .services.logo import LogoError
from .services.pdf_engine import PdfEngineError
from .services.pipeline import PipelineError
from .services.redact import RedactError
from .services.render import RenderError
from .storage import InvalidSessionId

# Per-worker process start time. Module-top capture is spawn-safe: every uvicorn
# worker (multiprocessing.spawn on Windows) re-imports app.main and captures its
# own start time, so /health reports per-worker uptime — the desired semantic
# (Pitfall 7).
_START_TIME: float = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # D-B1 trigger (a): app startup runs the janitor once so any session left over from
    # a prior process (crash, manual restart, deploy) gets reclaimed before the first
    # request lands. Wrapped in try/except so a startup janitor failure (broken
    # filesystem, missing DATA_DIR on first boot) cannot prevent the app from coming up
    # — uvicorn would otherwise 503 the entire process.
    try:
        janitor.sweep_expired_sessions()
    except Exception:
        pass
    yield


app = FastAPI(
    title=config.API_TITLE,
    root_path=config.APP_BASE_PATH,
    lifespan=lifespan,
)

# Optional CORS middleware (Plan 05-02 D-A1 / Claude discretion):
# CORS_ALLOW_ORIGINS empty (the default) → same-origin / iframe / strip-prefix all work
# without CORS. Future sub-domain embedding (Phase 5 deferred path) sets the env var to
# a comma-separated allowlist; the middleware is added only when the list is non-empty
# to keep the deployment minimal and avoid leaking "Access-Control-*" headers when not
# needed.
if config.CORS_ALLOW_ORIGINS:
    from fastapi.middleware.cors import CORSMiddleware

    _origins = [o.strip() for o in config.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
    if _origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

# Routers (thin handlers; logic in services/).
app.include_router(sessions.router)
app.include_router(pages.router)
app.include_router(process.router)
app.include_router(logos.router)

# Ingest error code -> HTTP status (mirrors api/sessions.py table).
_INGEST_STATUS: dict[str, int] = {
    "unsupported_type": 415,
    "file_too_large": 413,
    "too_many_pages": 413,
    "corrupt_pdf": 422,
    "empty_file": 400,
    # Phase 4 (UPLOAD-03): image ingest failure codes. The mirror dict lives in
    # api/sessions.py; tests/test_ingest.py::test_ingest_status_dicts_in_sync keeps
    # the two in lockstep so a future addition cannot drift silently.
    "unsupported_image_format": 415,
    "multi_page_tiff_unsupported": 415,
    "corrupt_image": 422,
}


@app.exception_handler(IngestError)
async def _handle_ingest_error(_request: Request, exc: IngestError) -> JSONResponse:
    status = _INGEST_STATUS.get(exc.code, 400)
    return JSONResponse(
        status_code=status,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RenderError)
async def _handle_render_error(_request: Request, exc: RenderError) -> JSONResponse:
    # The only RenderError code in Phase 1 is page_not_found -> 404.
    return JSONResponse(
        status_code=404,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(InvalidSessionId)
async def _handle_invalid_session_id(_request: Request, exc: InvalidSessionId) -> JSONResponse:
    # Defense-in-depth: a session id that fails the token-alphabet allowlist (threat
    # T-01-04 / path traversal) can never name a real session. Surface it as a plain 404
    # — indistinguishable from a missing session — so a crafted id is neither an oracle
    # nor a 500 that leaks internals.
    return JSONResponse(
        status_code=404,
        content={"detail": {"code": "session_not_found", "message": "找不到此工作階段。"}},
    )


# Phase-2 pipeline/redact error code -> HTTP status. A residual-content failure means the
# true-removal guarantee could not be met for a region; a bad page index in the JobSpec is a
# client request error. Both are 4xx (input/processing problems), never a bare 500 that would
# leak internals or kill a worker (threat T-02-08).
#
# Phase 5 (Plan 05-02) extends the dict with three integrity / timeout codes:
#   * original_tampered    503 — SHA-256 baseline mismatch (Plan 05-02 D-C3, T-05-04 surface
#                                 acknowledgment); the integrity module has already written
#                                 the .corrupted sentinel, so retries 410.
#   * session_corrupted    410 — meta.json missing original_sha256 OR sentinel already set;
#                                 Gone (not Forbidden / Not Found) is the precise semantic:
#                                 the resource USED to exist but is now intentionally retired.
#                                 process.py also raises this directly via HTTPException for
#                                 the pre-check short-circuit; the mapping here is defense in
#                                 depth for any code path that re-raises through PipelineError.
#   * processing_timeout   504 — /process exceeded PROCESS_TIMEOUT_SECONDS (Plan 05-02 D-D3).
#                                 process.py raises HTTPException directly (asyncio path); the
#                                 mapping is for defense in depth if a future re-raise path
#                                 surfaces the same code through PipelineError.
_PROCESS_STATUS: dict[str, int] = {
    "residual_content": 422,
    "page_out_of_range": 422,
    "work_copy_misconfigured": 500,  # internal invariant breach (should never happen)
    "original_tampered": 503,
    "session_corrupted": 410,
    "processing_timeout": 504,
}


@app.exception_handler(RedactError)
async def _handle_redact_error(_request: Request, exc: RedactError) -> JSONResponse:
    status = _PROCESS_STATUS.get(exc.code, 422)
    return JSONResponse(
        status_code=status,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(PipelineError)
async def _handle_pipeline_error(_request: Request, exc: PipelineError) -> JSONResponse:
    status = _PROCESS_STATUS.get(exc.code, 422)
    return JSONResponse(
        status_code=status,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


# Phase-3 logo error code -> HTTP status. An unknown/crafted logo_id is a 404
# (logo_not_found, no oracle, T-03-01); a corrupt/oversized asset is a 422 — never a bare
# 500, including a LogoError raised inside 03-02's /process path (T-02-08). Mirrors
# _handle_redact_error byte-for-byte in shape.
_LOGO_STATUS: dict[str, int] = {
    "logo_not_found": 404,
    "logo_invalid": 422,
    "logo_unreadable": 422,
}


@app.exception_handler(LogoError)
async def _handle_logo_error(_request: Request, exc: LogoError) -> JSONResponse:
    status = _LOGO_STATUS.get(exc.code, 422)
    return JSONResponse(
        status_code=status,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(PdfEngineError)
async def _handle_engine_error(_request: Request, exc: PdfEngineError) -> JSONResponse:
    # A parser failure that reached the handler means we treat the input as corrupt
    # rather than surfacing a 500 with internal MuPDF text.
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "corrupt_pdf", "message": "PDF 檔案損壞或無法解析。"}},
    )


@app.exception_handler(RequestValidationError)
async def _handle_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    # FastAPI's default 422 body is ``{"detail": [<error list>]}``; reshape it to the
    # project-wide ``{"detail": {"code", "message"}}`` so every error the frontend sees has
    # a stable ``detail.code`` (here ``invalid_request``). The first error's location +
    # message is summarized for the human-readable field; the full list never leaks as a 500.
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    msg = first.get("msg", "請求內容格式不正確。")
    detail_msg = f"{loc}: {msg}" if loc else msg
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "invalid_request", "message": detail_msg}},
    )


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Liveness + lightweight observability probe (Phase 5, D-D4).

    Returns five fields:

    * ``status`` — "ok" (the historical liveness signal).
    * ``uptime_seconds`` — wall-clock seconds since THIS worker imported the
      module. Per-worker, not per-app — that is intentional (Pitfall 7).
    * ``active_sessions`` — count of well-formed session dirs under
      ``originals/``. Sessions are only counted when their directory name
      matches the server-token alphabet (``_SESSION_ID_RE``) so any orphan dir
      a misbehaving admin/test left behind is excluded. Returns -1 if the
      directory cannot be enumerated.
    * ``data_dir_bytes`` / ``data_dir_pct`` — filesystem-level disk usage of the
      mount that backs ``DATA_DIR`` (NOT per-session usage; Pitfall 8).

    Deliberately does NOT include any session_id, filename, or path string
    (T-05-08 — /health is unauthenticated; treat its body as public).
    """
    uptime = max(0.0, time.time() - _START_TIME)
    originals_root = Path(config.DATA_DIR) / "originals"
    active_sessions = 0
    if originals_root.is_dir():
        try:
            active_sessions = sum(
                1
                for entry in originals_root.iterdir()
                if entry.is_dir() and storage._SESSION_ID_RE.fullmatch(entry.name)
            )
        except OSError:
            active_sessions = -1
    data_dir_bytes = 0
    data_dir_pct = 0.0
    try:
        usage = shutil.disk_usage(str(config.DATA_DIR))
        data_dir_bytes = usage.used
        data_dir_pct = round(100.0 * usage.used / usage.total, 2)
    except (OSError, FileNotFoundError):
        pass
    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 2),
        "active_sessions": active_sessions,
        "data_dir_bytes": data_dir_bytes,
        "data_dir_pct": data_dir_pct,
    }


# Mount the static frontend at / when present (created in Plan 01-02). Guard the mount
# so importing app.main never fails if web/ does not exist yet.
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
