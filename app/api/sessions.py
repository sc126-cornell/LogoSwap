"""Session endpoints: upload (POST /sessions) and lookup (GET /sessions/{id}).

Handlers stay thin — validation/storage live in services/. Ingest rejections
(:class:`IngestError`) are mapped to the right HTTP status via a small code->status
table and shaped as ``{"detail": {"code", "message"}}`` so the frontend can read a
stable ``detail.code`` and surface the limit-bearing message.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import config, storage
from ..models import SessionInfo
from ..services import ingest, janitor, pdf_engine
from ..services.ingest import IngestError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])

# Map ingest error codes to HTTP status (per the <interfaces> contract).
_CODE_STATUS: dict[str, int] = {
    "unsupported_type": 415,
    "file_too_large": 413,
    "too_many_pages": 413,
    "corrupt_pdf": 422,
    "empty_file": 400,
    # Phase 4 (UPLOAD-03): image ingest failure codes. Mirrors main._INGEST_STATUS;
    # tests/test_ingest.py::test_ingest_status_dicts_in_sync enforces parity.
    "unsupported_image_format": 415,
    "multi_page_tiff_unsupported": 415,
    "corrupt_image": 422,
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
    # buffering it. Accumulate into a single bytearray (extend in place) rather than a
    # list[bytes] + b"".join(): the old form transiently held ~2x the payload (the chunk
    # list AND the joined bytes) on the heap for an accepted upload (WR-04).
    limit = config.MAX_UPLOAD_BYTES
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB
        if not chunk:
            break
        if len(buf) + len(chunk) > limit:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "file_too_large",
                    "message": f"檔案過大,超過大小上限 {config.MAX_UPLOAD_MB} MB。",
                },
            )
        buf.extend(chunk)

    data = bytes(buf)

    try:
        return ingest.ingest_upload(file.filename or "upload.pdf", data)
    except IngestError as err:
        raise _ingest_http_error(err) from err
    finally:
        # D-B1 trigger (b): POST /sessions end calls janitor sweep. Wrapped in try/except
        # so a janitor failure (concurrent rmtree race, transient I/O error) does not
        # taint the response — the upload either succeeded (201) or already raised the
        # appropriate IngestError. The sweep is best-effort cleanup, not a precondition.
        # CR-01: log at WARNING so an unexpected sweep failure is observable.
        try:
            janitor.sweep_expired_sessions()
        except Exception:
            logger.warning(
                "POST /sessions: janitor sweep failed", exc_info=True
            )


@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str) -> SessionInfo:
    """Return session info; 404 with code "session_not_found" if absent.

    page_count + filename are read from the per-session sidecar written at ingest, so this
    hot path does NOT re-parse the PDF (WR-03). If the sidecar is missing (e.g. a session
    created before sidecars existed), fall back to a one-time re-parse — but a parse failure
    here is an internal/storage problem, surfaced as ``session_unreadable`` (500), never the
    client-facing ``corrupt_pdf`` (which would wrongly blame a file that already passed
    ingest validation).
    """
    if not storage.session_exists(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "找不到此工作階段。"},
        )

    meta = storage.read_session_meta(session_id)
    if meta is not None:
        return SessionInfo(
            session_id=session_id,
            page_count=int(meta["page_count"]),
            filename=meta.get("filename") or "source.pdf",
        )

    # No sidecar — recover page_count by re-parsing once. Map a parse failure to a
    # distinct internal code, NOT corrupt_pdf.
    try:
        doc = pdf_engine.open_pdf(storage.work_path(session_id))
        try:
            n_pages = pdf_engine.page_count(doc)
        finally:
            pdf_engine.close(doc)
    except pdf_engine.PdfEngineError as err:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "session_unreadable",
                "message": "工作階段資料無法讀取,請重新上傳檔案。",
            },
        ) from err

    return SessionInfo(
        session_id=session_id,
        page_count=n_pages,
        filename="source.pdf",
    )
