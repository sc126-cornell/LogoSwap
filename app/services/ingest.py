"""Upload ingest: validate untrusted bytes, preserve the original, make a work copy.

This is the trust boundary where untrusted file bytes + a client-supplied filename
cross into the system. Every rejection becomes a typed :class:`IngestError(code, message)`
that the API layer maps to a structured 4xx — never a 500 (Pitfall 11).

Validation order is deliberate (cheapest / most-DoS-relevant first):
  1. empty            -> "empty_file"            (400)
  2. oversize bytes   -> "file_too_large"        (413)  [T-01-01; message carries 50 MB]
  3. PDF content sniff-> "unsupported_type"      (415)  [content-sniffed, not extension]
  4. parse            -> "corrupt_pdf"           (422)  [T-01-03]
  5. too many pages   -> "too_many_pages"        (413)  [T-01-02; message carries 30]

Only after all checks pass do we create a session, write the immutable original, and
copy the bytes to the work path (the editing substrate — the original is never reopened
for writes, Anti-Pattern 3).
"""

from __future__ import annotations

from .. import config, storage
from ..models import SessionInfo
from . import pdf_engine

# PDF magic header. Real PDFs start with "%PDF-" (optionally after a few junk bytes,
# but we accept it appearing within the first small window to be lenient about BOMs).
_PDF_MAGIC = b"%PDF-"


class IngestError(Exception):
    """Typed ingest rejection carrying a stable ``code`` and a user-facing ``message``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _looks_like_pdf(data: bytes) -> bool:
    """Content-sniff a PDF header; do NOT trust the filename extension (T-01-06)."""
    head = data[:1024]
    return _PDF_MAGIC in head


def ingest_upload(filename: str, data: bytes) -> SessionInfo:
    """Validate + store an uploaded PDF, returning its :class:`SessionInfo`.

    Raises :class:`IngestError` for every rejection path with a stable code.
    """
    # 1. Empty.
    if not data:
        raise IngestError("empty_file", "檔案是空的,請選擇有內容的 PDF。")

    # 2. Oversize — reject before doing any parsing work (DoS mitigation T-01-01).
    #    Message carries the limit value (e.g. "50") for the frontend "檔案過大" copy.
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise IngestError(
            "file_too_large",
            f"檔案過大,超過大小上限 {config.MAX_UPLOAD_MB} MB。",
        )

    # 3. Type sniff (content, not extension).
    if not _looks_like_pdf(data):
        raise IngestError(
            "unsupported_type",
            "不支援的檔案類型,本階段僅接受向量 PDF。",
        )

    # 4. Parse — a malformed PDF that sniffed as PDF still must not crash the worker.
    doc = None
    try:
        try:
            doc = pdf_engine.open_pdf(data)
        except pdf_engine.PdfEngineError as exc:
            raise IngestError("corrupt_pdf", "PDF 檔案損壞或無法解析。") from exc

        n_pages = pdf_engine.page_count(doc)

        # A structurally-valid file with zero pages is unusable.
        if n_pages < 1:
            raise IngestError("corrupt_pdf", "PDF 沒有任何頁面。")

        # 5. Too many pages (DoS mitigation T-01-02). Message carries the limit ("30").
        if n_pages > config.MAX_PAGES:
            raise IngestError(
                "too_many_pages",
                f"頁數過多,超過頁數上限 {config.MAX_PAGES} 頁。",
            )
    finally:
        if doc is not None:
            pdf_engine.close(doc)

    # All checks passed — persist. Create the session, write the immutable original,
    # then a separate writable work copy. The original is never reopened for writes.
    session_id = storage.new_session()
    safe_name = storage.sanitize_filename(filename)
    storage.write_original(session_id, safe_name, data)
    storage.write_work_copy(session_id, data)

    return SessionInfo(
        session_id=session_id,
        page_count=n_pages,
        filename=safe_name,
    )
