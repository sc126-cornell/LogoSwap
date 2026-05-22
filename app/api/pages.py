"""Page endpoints: server-rendered PNG (with metadata headers) and /meta JSON.

Rasterization is CPU-bound, so :func:`render_page` runs in a threadpool
(``run_in_threadpool``) to avoid stalling the event loop (STACK.md process model).

The image response carries the SIX coordinate-seam headers Phase 2 reads. The values
come from the actual render (X-Render-Dpi reflects the ACTUAL clamped DPI used, D-03),
not the requested value.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool

from .. import config, storage
from ..models import PageMeta
from ..services import render
from ..services.render import RenderError

router = APIRouter(tags=["pages"])


def _require_session(session_id: str) -> None:
    if not storage.session_exists(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "找不到此工作階段。"},
        )


def _render_error_status(code: str) -> int:
    """A bad ?rotate= is a 400 (client sent an invalid value); a missing page is a 404."""
    return 400 if code == "invalid_rotation" else 404


@router.get("/sessions/{session_id}/pages/{page_no}/image")
async def get_page_image(
    session_id: str,
    page_no: int,
    dpi: int | None = Query(default=None, ge=1),
    rotate: int | None = Query(default=None),
) -> Response:
    """Return the page as image/png with the six X-... coordinate-seam headers.

    ``dpi`` is optional and defaults to ``config.DEFAULT_DPI`` (200), clamped to
    ``[MIN_DPI, MAX_DPI]``. ``rotate`` (0/90/180/270) is the user's TRANSIENT rotation added to
    the page's intrinsic ``/Rotate`` for this render only — it is NOT persisted. A missing
    session or out-of-range page returns 404; a bad ``rotate`` returns 400.
    """
    _require_session(session_id)
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
            status_code=_render_error_status(err.code),
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


@router.get("/sessions/{session_id}/pages/{page_no}/meta", response_model=PageMeta)
async def get_page_meta(
    session_id: str,
    page_no: int,
    dpi: int | None = Query(default=None, ge=1),
    rotate: int | None = Query(default=None),
) -> PageMeta:
    """Return PageMeta JSON so the frontend can size the page stage before image load.

    ``rotate`` (0/90/180/270) reflects the rotated orientation in the returned dims +
    rotation, so the overlay measures px against the rotated image (symmetric with the image
    endpoint). A bad value returns 400.
    """
    _require_session(session_id)
    work = storage.work_path(session_id)

    try:
        user_rotation = render.validate_rotation(rotate)
        meta = await run_in_threadpool(
            render.page_meta,
            work,
            page_no,
            dpi if dpi is not None else config.DEFAULT_DPI,
            user_rotation,
        )
    except RenderError as err:
        raise HTTPException(
            status_code=_render_error_status(err.code),
            detail={"code": err.code, "message": err.message},
        ) from err

    return PageMeta(**meta)
