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

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .. import config, storage
from ..models import JobSpec
from ..services import pipeline, render
from ..services.redact import RedactError
from ..services.render import RenderError

router = APIRouter(tags=["process"])


def _require_session(session_id: str) -> None:
    if not storage.session_exists(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "找不到此工作階段。"},
        )


@router.post("/sessions/{session_id}/process")
async def process_session(session_id: str, job: JobSpec) -> dict:
    """Redact the work copy per ``job`` and export the result PDF.

    Returns ``{output_filename, page_count, regions:[{page, removed, clamped}]}``. A missing
    session -> 404; a malformed ``JobSpec`` -> 422 (Pydantic) shaped via the validation
    handler; a residual-content / pipeline failure -> typed 4xx (handled in main.py), never
    a bare 500.
    """
    _require_session(session_id)
    # process_job opens the work copy, maps+clamps, redacts, saves work + outputs. It is
    # CPU-bound (PDF parse + redaction rewrite), so run it off the event loop.
    return await run_in_threadpool(pipeline.process_job, session_id, job)


@router.get("/sessions/{session_id}/result/pages/{page_no}/image")
async def get_result_page_image(
    session_id: str,
    page_no: int,
    dpi: int | None = Query(default=None, ge=1),
) -> Response:
    """Render the REDACTED work copy page as image/png with the six X- coordinate headers.

    This is the "移除結果" after-image the before/after toggle shows (REMOVE-04). The work
    copy IS the redacted substrate after a process run; before one it equals the original,
    so this endpoint is always valid. Out-of-range page -> 404 via the RenderError path.
    """
    _require_session(session_id)
    work = storage.work_path(session_id)

    try:
        result = await run_in_threadpool(
            render.render_page, work, page_no, dpi if dpi is not None else config.DEFAULT_DPI
        )
    except RenderError as err:
        raise HTTPException(
            status_code=404,
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
    """
    _require_session(session_id)

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
