"""Process + result-render + download endpoints (Plan 02-02, Task 2).

Three endpoints, all session-scoped through :func:`_require_session` (the Phase-1
allowlist; a crafted id is a plain 404, never a path-build or oracle — threat T-02-06):

  - ``POST /sessions/{id}/process``           — run the deferred-mutation removal pipeline
                                                 on the WORK copy; returns the per-region
                                                 result and the export filename.
  - ``GET  /sessions/{id}/result/pages/{n}/image`` — render the REDACTED work copy as the
                                                 "移除結果" after-image, with the same six
                                                 X- coordinate headers as ``pages.py``
                                                 (REMOVE-04). Valid even before a process run
                                                 (the work copy equals the original until
                                                 processed).
  - ``GET  /sessions/{id}/result``            — stream the exported ``原名_logoswap.pdf``
                                                 as an attachment (OUTPUT-01); 404
                                                 ``result_not_ready`` before any process run.

Redaction and rendering are CPU-bound, so they run in ``run_in_threadpool`` (STACK.md
process model / DoS T-02-04). The typed pipeline/redact errors are mapped to structured
``{detail:{code,message}}`` 4xx by the handlers in ``main.py`` — never a bare 500.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .. import config, storage
from ..models import JobSpec
from ..services import janitor, pipeline, render
from ..services.redact import RedactError
from ..services.render import RenderError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["process"])


def _require_session(session_id: str) -> None:
    if not storage.session_exists(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "找不到此工作階段。"},
        )


def _reject_if_corrupted(session_id: str) -> None:
    # D-C3 contract (CR-02): once a session is marked .corrupted, ALL subsequent
    # /process, GET /result, and GET /result/pages/{n}/image MUST short-circuit to 410.
    # The earlier process run's pre-tamper output PDF + work copy are still on disk
    # (mark_session_corrupted is a touch, not a clear); without this gate GET /result
    # would happily stream the stale output that no longer matches the (tampered)
    # source, violating the fail-closed contract.
    if storage.is_session_corrupted(session_id):
        raise HTTPException(
            status_code=410,
            detail={
                "code": "session_corrupted",
                "message": "此工作階段已標記為異常,請重新上傳檔案。",
            },
        )


@router.post("/sessions/{session_id}/process")
async def process_session(session_id: str, job: JobSpec) -> dict:
    """Redact the work copy per ``job`` and export the result PDF.

    Returns ``{output_filename, page_count, regions:[{page, removed, clamped}]}``. A missing
    session -> 404; a malformed ``JobSpec`` -> 422 (Pydantic) shaped via the validation
    handler; a residual-content / pipeline failure -> typed 4xx (handled in main.py), never
    a bare 500.

    ``job`` may carry an optional global ``logo_id`` (Phase 3, D-01): when present the same
    logo is placed into every removed region (resolved via the ``logo.py`` manifest allowlist;
    an unknown id surfaces as a typed ``LogoError`` -> 4xx via the main.py handler); when
    null/absent the job is pure removal (Phase-2 behavior). The handler is otherwise unchanged
    — it passes the whole validated ``JobSpec`` through to ``pipeline.process_job``.
    """
    _require_session(session_id)

    # D-C3 short-circuit: a session previously detected as tampered (work/{sid}/.corrupted
    # sentinel present) returns 410 immediately — no parse, no thread, no timeout. This
    # gate runs BEFORE the timeout wrapper so a poisoned sid cannot tie up a worker
    # waiting for verify (which would itself fail fast, but the short-circuit gives a
    # cleaner 410 with the right code).
    _reject_if_corrupted(session_id)

    # D-D3 timeout: wrap process_job in asyncio.wait_for + asyncio.to_thread. Pipeline is
    # CPU-bound (PDF parse + redaction rewrite + save); to_thread runs it off the event
    # loop, wait_for caps wall-clock time, and finally re-runs the janitor sweep.
    #
    # Pitfall 1 (RESEARCH §"thread cannot be killed"): asyncio.wait_for(asyncio.to_thread
    # (...)) makes the HTTP response return 504 immediately on timeout, but the underlying
    # thread KEEPS RUNNING until process_job naturally exits — Python has no thread.kill().
    # Worst case is ~10–30s after a 60s timeout (MAX_RENDER_PIXELS=40MP +
    # MAX_PAGES=30 collapse the worst case from "minutes" to "tens of seconds"). UVICORN_
    # WORKERS=2 (D-D2) ensures the OTHER worker continues serving /preview / /health /
    # /sessions while one worker's thread drains. Upgrade path (deferred to v1.x if real
    # abuse appears): ProcessPoolExecutor for true process-level kill.
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(pipeline.process_job, session_id, job),
            timeout=config.PROCESS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as err:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "processing_timeout",
                "message": (
                    f"處理逾時(超過 {config.PROCESS_TIMEOUT_SECONDS} 秒),"
                    "請改用較小檔案或減少框選區域數量。"
                ),
            },
        ) from err
    finally:
        # D-B1 trigger (c): /process end calls janitor sweep. try/except guarantees a
        # janitor failure cannot taint the response (T-05-05 mitigation; the sweep itself
        # already swallows OSError, but defense in depth). CR-01: log at WARNING so a
        # janitor regression is observable in ops logs.
        try:
            janitor.sweep_expired_sessions()
        except Exception:
            logger.warning(
                "POST /process: janitor sweep failed (session_id=%s)",
                session_id,
                exc_info=True,
            )


@router.get("/sessions/{session_id}/result/pages/{page_no}/image")
async def get_result_page_image(
    session_id: str,
    page_no: int,
    dpi: int | None = Query(default=None, ge=1),
    rotate: int | None = Query(default=None),
) -> Response:
    """Render the REDACTED work copy page as image/png with the six X- coordinate headers.

    This is the "移除結果" after-image the before/after toggle shows (REMOVE-04). The work
    copy IS the redacted substrate after a process run; before one it equals the original,
    so this endpoint is always valid. Out-of-range page -> 404 via the RenderError path.

    ``rotate`` (0/90/180/270) is applied transiently — symmetric with the 原圖 endpoint — so
    the work copy stays at its intrinsic rotation on disk while the after-image shows the same
    rotated orientation the user framed on. A bad value -> 400. A session marked .corrupted
    after a tamper-detect short-circuits to 410 session_corrupted (D-C3 / CR-02): without this
    the endpoint would render the pre-tamper work copy.
    """
    _require_session(session_id)
    _reject_if_corrupted(session_id)
    work = storage.work_path(session_id)

    try:
        user_rotation = render.validate_rotation(rotate)
        result = await run_in_threadpool(
            render.render_page,
            work,
            page_no,
            dpi if dpi is not None else config.DEFAULT_DPI,
            user_rotation,
        )
    except RenderError as err:
        raise HTTPException(
            status_code=(400 if err.code == "invalid_rotation" else 404),
            detail={"code": err.code, "message": err.message},
        ) from err

    headers = {
        "X-Page-Width-Pt": str(result.page_w_pt),
        "X-Page-Height-Pt": str(result.page_h_pt),
        "X-Page-Rotation": str(result.rotation),
        "X-Render-Dpi": str(result.dpi),
        "X-Image-Width-Px": str(result.img_w),
        "X-Image-Height-Px": str(result.img_h),
    }
    return Response(content=result.png, media_type="image/png", headers=headers)


@router.get("/sessions/{session_id}/result")
async def download_result(session_id: str) -> FileResponse:
    """Stream the exported ``原名_logoswap.pdf`` as an attachment download (OUTPUT-01).

    404 ``result_not_ready`` if no process run has produced an output yet. The on-disk path
    is the FIXED session-scoped output file (threat T-02-06: the CJK display name is used
    only in the Content-Disposition header via RFC-5987 ``filename*=``, never as a path).
    A session marked .corrupted (D-C3 / CR-02) short-circuits to 410 session_corrupted so
    we never stream the pre-tamper output PDF.
    """
    _require_session(session_id)
    _reject_if_corrupted(session_id)

    out_name = pipeline.output_filename(session_id)
    out_file = storage.outputs_dir(session_id) / out_name
    if not out_file.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "result_not_ready",
                "message": "尚未產生結果,請先執行移除處理。",
            },
        )

    # RFC 5987 / UTF-8 filename* for the CJK display name; an ASCII fallback for old clients.
    quoted = quote(out_name, safe="")
    disposition = f"attachment; filename=result.pdf; filename*=UTF-8''{quoted}"
    return FileResponse(
        path=str(out_file),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
