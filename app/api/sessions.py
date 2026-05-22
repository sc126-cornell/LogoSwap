"""Session endpoints: upload (POST /sessions) and lookup (GET /sessions/{id}).

Handlers stay thin — validation/storage live in services/. Ingest rejections
(:class:`IngestError`) are mapped to the right HTTP status via a small code->status
table and shaped as ``{"detail": {"code", "message"}}`` so the frontend can read a
stable ``detail.code`` and surface the limit-bearing message.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import config, storage
from ..models import SessionInfo
from ..services import ingest, pdf_engine
from ..services.ingest import IngestError

router = APIRouter(tags=["sessions"])

# Map ingest error codes to HTTP status (per the <interfaces> contract).
_CODE_STATUS: dict[str, int] = {
    "unsupported_type": 415,
    "file_too_large": 413,
    "too_many_pages": 413,
    "corrupt_pdf": 422,
    "empty_file": 400,
}


def _ingest_http_error(err: IngestError) -> HTTPException:
    status = _CODE_STATUS.get(err.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": err.code, "message": err.message},
    )


@router.post("/sessions", status_code=201, response_model=SessionInfo)
async def create_session(file: UploadFile = File(...)) -> SessionInfo:
    """Upload a single vector PDF; returns session_id + page_count (201).

    The upload is read with an early size guard (T-01-01): we stop reading and reject
    as ``file_too_large`` as soon as the stream exceeds ``MAX_UPLOAD_BYTES`` rather than
    buffering the whole oversize file.
    """
    # Stream-read with an early cap so an oversize upload is rejected before fully
    # buffering it. We read one extra byte past the limit to detect "over".
    limit = config.MAX_UPLOAD_BYTES
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "file_too_large",
                    "message": f"檔案過大,超過大小上限 {config.MAX_UPLOAD_MB} MB。",
                },
            )
        chunks.append(chunk)

    data = b"".join(chunks)

    try:
        return ingest.ingest_upload(file.filename or "upload.pdf", data)
    except IngestError as err:
        raise _ingest_http_error(err) from err


@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str) -> SessionInfo:
    """Return session info; 404 with code "session_not_found" if absent.

    page_count is recovered by opening the work copy through the engine seam.
    """
    if not storage.session_exists(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "找不到此工作階段。"},
        )

    doc = pdf_engine.open_pdf(storage.work_path(session_id))
    try:
        n_pages = pdf_engine.page_count(doc)
    finally:
        pdf_engine.close(doc)

    # The original filename is not persisted as metadata in Phase 1; report the
    # canonical work filename. (A session-meta sidecar can carry the original name
    # in a later phase if the UI needs it.)
    return SessionInfo(
        session_id=session_id,
        page_count=n_pages,
        filename="source.pdf",
    )
