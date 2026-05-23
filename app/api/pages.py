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

    This is the 原圖 (BEFORE) preview, so it renders the IMMUTABLE pristine PDF — NOT the work
    copy (which the pipeline redacts in place as the 移除結果 substrate). Rendering the work
    copy here made 原圖 show the redacted result after an apply (Phase 1 UAT bug).

    Source is ``pristine_path`` (Phase 4): for PDF uploads pristine bytes equal the user's
    raw PDF (PDF == work == pristine), so this is equivalent to the Phase 1–3 behaviour. For
    IMAGE uploads (PNG/JPG/TIFF), pristine is the normalized A4 PDF — using originals/ here
    would render the raw image bytes at native pixel dimensions (e.g. 3965×9836 pt),
    desynchronizing the frontend's px_rect coordinate space from the /process backend (which
    measures against work, which equals pristine geometry). #hotfix-04-02.
    """
    _require_session(session_id)
    source = storage.pristine_path(session_id)

    try:
        user_rotation = render.validate_rotation(rotate)
        result = await run_in_threadpool(
            render.render_page,
            source,
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
    # Preview metadata comes from the IMMUTABLE pristine PDF (Phase 4): pristine never changes
    # after ingest, so /meta never reflects in-place redactions, and pristine carries the SAME
    # geometry the /process pipeline measures against. For PDF uploads pristine == originals
    # bytes (no behaviour change vs Phase 1–3); for IMAGE uploads pristine is the normalized A4
    # PDF (originals/ is raw PNG/JPG/TIFF bytes — wrong geometry, would desynchronize the
    # frontend px_rect coordinate space from the /process backend). #hotfix-04-02.
    source = storage.pristine_path(session_id)

    try:
        user_rotation = render.validate_rotation(rotate)
        meta = await run_in_threadpool(
            render.page_meta,
            source,
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
