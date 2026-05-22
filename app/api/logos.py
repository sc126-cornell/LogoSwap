"""Logo-library endpoints (Phase 3, LOGO-01): GET /logos + GET /logos/{id}/image.

The library is a fixed, shared, read-only asset — NOT session-scoped — so there is no
``_require_session`` guard here. An untrusted ``logo_id`` is resolved through the manifest
allowlist in ``logo.py`` (T-03-01): a crafted/unknown id is a structured 404 ``logo_not_found``,
never a path read, never a 500.

PNG decode is CPU-bound, so ``resolve`` runs in ``run_in_threadpool`` (mirrors pages.py /
process.py). ``GET /logos`` degrades to ``{"logos": []}`` for an absent/empty library (A2).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.concurrency import run_in_threadpool

from ..services import logo
from ..services.logo import LogoError

router = APIRouter(tags=["logos"])

# logo error code -> HTTP status (the image endpoint maps a crafted/unknown id to 404).
_LOGO_STATUS: dict[str, int] = {
    "logo_not_found": 404,
    "logo_invalid": 422,
    "logo_unreadable": 422,
}


@router.get("/logos")
async def list_logos() -> dict:
    """List the fixed logo library for the picker (LOGO-01).

    Returns ``{"logos": [{id, name, tags}]}`` — never a filesystem path. An absent/empty
    library yields ``{"logos": []}`` (picker empty-state), never a 500.
    """
    return {"logos": logo.list_logos()}


@router.get("/logos/{logo_id}/image")
async def get_logo_image(logo_id: str) -> Response:
    """Serve the full PNG bytes for ``logo_id`` (the picker thumbnail src; CSS-scaled).

    ``logo_id`` is resolved through the manifest allowlist — a crafted/unknown id is a
    structured 404 ``logo_not_found`` (T-03-01), a corrupt asset a 422, never a bare 500.
    """
    try:
        data = await run_in_threadpool(logo.resolve, logo_id)
    except LogoError as err:
        raise HTTPException(
            status_code=_LOGO_STATUS.get(err.code, 422),
            detail={"code": err.code, "message": err.message},
        ) from err
    return Response(content=data, media_type="image/png")
