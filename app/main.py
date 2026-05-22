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

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import logos, pages, process, sessions
from .services.ingest import IngestError
from .services.logo import LogoError
from .services.pdf_engine import PdfEngineError
from .services.pipeline import PipelineError
from .services.redact import RedactError
from .services.render import RenderError
from .storage import InvalidSessionId

app = FastAPI(title=config.API_TITLE)

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
_PROCESS_STATUS: dict[str, int] = {
    "residual_content": 422,
    "page_out_of_range": 422,
    "work_copy_misconfigured": 500,  # internal invariant breach (should never happen)
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
    """Liveness probe."""
    return {"status": "ok"}


# Mount the static frontend at / when present (created in Plan 01-02). Guard the mount
# so importing app.main never fails if web/ does not exist yet.
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
