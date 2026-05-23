"""Upload ingest: validate untrusted bytes, preserve the original, make a work copy.

This is the trust boundary where untrusted file bytes + a client-supplied filename
cross into the system. Every rejection becomes a typed :class:`IngestError(code, message)`
that the API layer maps to a structured 4xx — never a 500 (Pitfall 11).

Validation order is deliberate (cheapest / most-DoS-relevant first):
  1. empty                       -> "empty_file"                  (400)
  2. oversize bytes              -> "file_too_large"              (413)  [T-01-01]
  3. content sniff (4 magics)    -> "unsupported_type"            (415)
  4a. PDF parse                  -> "corrupt_pdf"                 (422)
  4b. Pillow verify / decode     -> "corrupt_image"               (422)
      multi-page TIFF            -> "multi_page_tiff_unsupported" (415)
      decoded format not in set  -> "unsupported_image_format"    (415)
  5. too many pages              -> "too_many_pages"              (413)

Only after all checks pass do we create a session and write three copies:
``originals/`` (the user's raw bytes — SHA-256 invariant, chmod 0o444),
``work/`` (the editable PDF — for PDF uploads this is the same bytes, for image
uploads it is the normalized A4 PDF), and ``pristine/`` (the pipeline reset source —
always a PDF). Phase 4 keeps the AGPL seam intact: fitz lives only behind
``pdf_engine``; this module imports Pillow but never ``fitz``.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

from .. import config, storage
from ..models import SessionInfo
from . import pdf_engine

# PDF magic header. Real PDFs start with "%PDF-" at the very start, though the spec
# tolerates a few junk/BOM bytes before it. We therefore require the header to appear
# at a SMALL leading offset, not merely "somewhere in the first 1 KB" (WR-05) — the
# latter let a non-PDF polyglot whose first kilobyte merely contained the bytes "%PDF-"
# pass the type sniff.
_PDF_MAGIC = b"%PDF-"
# Max bytes of leading junk tolerated before the header (covers a UTF-8/UTF-16 BOM).
_PDF_MAGIC_MAX_OFFSET = 8

# Image magic bytes (D-12). Unlike PDF, the PNG/JPEG/TIFF specs do NOT permit any
# leading junk before the header — we therefore require ``startswith`` offset 0 for
# image magic, NOT the ``find`` + leading-offset window the PDF magic uses. Mixing
# the two would let a polyglot with bytes ``...\x89PNG...`` early in the file falsely
# sniff as a PNG and feed bogus data to Pillow.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_TIFF_LE_MAGIC = b"II*\x00"
_TIFF_BE_MAGIC = b"MM\x00*"

# Pillow formats Phase 4 accepts after decode. Any other decoded format (GIF, WebP,
# BMP, etc.) is rejected as ``unsupported_image_format`` even if the sniff somehow
# passed — defense in depth against magic spoofing where the bytes "happen to look
# like a PNG" but decode as something else entirely (Pillow does its own magic check
# during ``Image.open``).
_ACCEPTED_IMAGE_FORMATS = ("PNG", "JPEG", "TIFF")


class IngestError(Exception):
    """Typed ingest rejection carrying a stable ``code`` and a user-facing ``message``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _looks_like_pdf(data: bytes) -> bool:
    """Content-sniff a PDF header; do NOT trust the filename extension (T-01-06).

    Kept as a thin wrapper around the magic-offset check so callers in earlier phases
    that imported the helper by name keep working; new code should use
    :func:`_sniff_kind` which returns the dispatch kind.
    """
    offset = data[:1024].find(_PDF_MAGIC)
    return 0 <= offset <= _PDF_MAGIC_MAX_OFFSET


def _sniff_kind(data: bytes) -> str | None:
    """Return one of ``"pdf"``, ``"png"``, ``"jpeg"``, ``"tiff"`` or ``None`` (D-12).

    PDF magic is matched with the legacy ``find`` + leading-offset window so a BOM-
    prefixed PDF still sniffs as a PDF (Phase 1 WR-05 behaviour, kept for backward
    compatibility with existing tests). Image magics MUST match at offset 0 — there
    is no spec-permitted preamble before PNG/JPEG/TIFF headers, and tolerating one
    would open a polyglot bypass (Pitfall 11).

    The real per-format validation (header sanity, decompression bomb defense,
    multi-page TIFF rejection, CMYK conversion) lives in :func:`_ingest_image` and
    Pillow ``Image.open``. ``_sniff_kind`` is only the FIRST filter.
    """
    head = data[:1024]
    # PDF: tolerate a leading BOM/junk up to 8 bytes (WR-05).
    pdf_offset = head.find(_PDF_MAGIC)
    if 0 <= pdf_offset <= _PDF_MAGIC_MAX_OFFSET:
        return "pdf"
    # Image magics MUST match at offset 0 — no preamble permitted.
    if head.startswith(_PNG_MAGIC):
        return "png"
    if head.startswith(_JPEG_MAGIC):
        return "jpeg"
    if head.startswith(_TIFF_LE_MAGIC) or head.startswith(_TIFF_BE_MAGIC):
        return "tiff"
    return None


def _ingest_image(data: bytes, sniff_kind: str) -> bytes:
    """Validate + normalize an uploaded image to RGB PNG/JPEG bytes ready for A4 wrapping.

    The chain mirrors ``logo._validate_png`` (Phase 3) — read ``img.format`` BEFORE
    calling ``img.verify()`` because verify() invalidates the Image object — but
    extends it for Phase 4's multi-page-TIFF / CMYK / alpha / format-allowlist
    requirements. Steps:

    a. ``Image.open(BytesIO(data))`` -> read ``fmt`` -> ``verify()``. Any
       :class:`Image.DecompressionBombError` / :class:`UnidentifiedImageError` / OS-
       error / ValueError raises :class:`IngestError("corrupt_image", …)` — never
       escapes as a 500.
    b. Re-open (verify() leaves the object unusable). Reject multi-page TIFFs via
       ``getattr(img, "n_frames", 1) > 1`` with ``multi_page_tiff_unsupported`` (D-02).
    c. Reject any decoded format that is not PNG/JPEG/TIFF with
       ``unsupported_image_format`` — covers the "PNG magic but Pillow decoded it as
       GIF" polyglot case (D-12 defense in depth).
    d. Force RGB: ``img.convert("RGB")`` if mode != "RGB". This drops alpha (PNG RGBA
       gets composited onto white, Pitfall G transparent-PNG defense) and converts
       CMYK to RGB (D-03, Pitfall D black-box defense).
    e. ``img.load()`` to force pixel decode — verify() is only header sanity, a
       truncated payload only trips here. Same except chain → corrupt_image.
    f. Re-encode: JPEG sniffed inputs round-trip back to JPEG (small, byte-near-exact
       passthrough by PyMuPDF later); PNG / TIFF inputs are re-emitted as PNG
       (lossless after the convert("RGB") drop-alpha step).
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format  # MUST be read before verify(); verify() invalidates the obj.
            img.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as err:
        raise IngestError("corrupt_image", "影像檔案損壞或無法解析。") from err

    # Re-open after verify(). IN-03: use ``with Image.open(...) as src:`` so the source
    # file handle / underlying BytesIO is released deterministically the moment we have a
    # detached copy in ``img``. The ``finally: img.close()`` below then only needs to clean
    # up the SINGLE working handle (either the copy, or the alpha-composited ``background``
    # that replaced it), not two parallel handles relying on Pillow's __del__ to mop up the
    # source. Frame-count + pixel-cap checks happen INSIDE the ``with`` so they see the
    # source's metadata (n_frames lives on the source image, not the copy).
    try:
        with Image.open(io.BytesIO(data)) as src:
            n_frames = getattr(src, "n_frames", 1)
            if n_frames > 1:
                raise IngestError(
                    "multi_page_tiff_unsupported",
                    "暫不支援多頁 TIFF,請先拆成單頁 TIFF 再上傳。",
                )

            if fmt not in _ACCEPTED_IMAGE_FORMATS:
                raise IngestError(
                    "unsupported_image_format",
                    f"不支援的影像格式:{fmt}。",
                )

            # DoS hard cap on pixel count (WR-03). Pillow's ``Image.DecompressionBombError``
            # only RAISES at ``MAX_IMAGE_PIXELS * 2``; below that it merely emits a warning
            # and proceeds. So a 60-megapixel TIFF passes ``verify()`` + ``load()``,
            # ``image_to_a4_pdf`` then re-encodes it as PNG inside an A4 page, and the
            # resulting CPU/memory spike (PyMuPDF does not downscale on insert_image)
            # exceeds the wall-clock budget per worker. ``MAX_UPLOAD_BYTES`` is already
            # checked upstream but a small heavily-compressed source (e.g. a uniform
            # gradient PNG) can sit well under 50 MB and still decompress to ≥100 MP.
            # Re-use the existing ``config.MAX_INGEST_IMAGE_PIXELS`` constant — its docstring
            # already states it is the ingest-side pixel ceiling — and enforce it as a HARD
            # cap (raise an IngestError, not just a warning). Pillow's own threshold
            # remains in place as a backstop.
            if src.width * src.height > config.MAX_INGEST_IMAGE_PIXELS:
                raise IngestError(
                    "image_too_large_pixels",
                    f"影像像素數過多(超過 {config.MAX_INGEST_IMAGE_PIXELS:,} 像素),請先縮圖再上傳。",
                )

            # Detach a working copy so we can keep mutating after ``src`` is closed.
            img = src.copy()
    except IngestError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as err:
        raise IngestError("corrupt_image", "影像檔案損壞或無法解析。") from err

    try:
        # D-03 CMYK→RGB, RGBA→RGB (Pitfall D, Pitfall G).
        # Pillow's plain ``convert("RGB")`` on an alpha-bearing image DROPS the alpha
        # channel without compositing — so RGBA pixel (0,0,0,0) becomes RGB (0,0,0)
        # BLACK, turning a fully transparent background into a fully black one. The
        # user perceives transparent PNGs as "white background" in the browser, so
        # we must composite onto white explicitly BEFORE dropping alpha. Covers
        # RGBA, LA, and palette PNGs that carry transparency via ``info["transparency"]``.
        has_alpha = (
            img.mode in ("RGBA", "LA")
            or (img.mode == "P" and "transparency" in img.info)
        )
        if has_alpha:
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            # IN-03: named-channel access. Documented Pillow idiom; semantics identical to
            # ``rgba.split()[3]`` but the intent is obvious to a future reader.
            background.paste(rgba, mask=rgba.getchannel("A"))
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Force pixel decode — catch truncated-payload corruption that survives verify().
        try:
            img.load()
        except (OSError, ValueError) as err:
            raise IngestError("corrupt_image", "影像檔案損壞或無法解析。") from err

        # Re-emit. JPEG-sniffed input → JPEG (byte-near-exact passthrough by PyMuPDF);
        # PNG / TIFF → PNG (lossless after the drop-alpha convert above).
        buf = io.BytesIO()
        if sniff_kind == "jpeg":
            img.save(buf, format="JPEG", quality=config.JPEG_REENCODE_QUALITY)
        else:
            img.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        img.close()


def _ingest_pdf(filename: str, data: bytes) -> SessionInfo:
    """The Phase 1 PDF ingest path, refactored out of ``ingest_upload`` for dispatch."""
    doc = None
    try:
        try:
            doc = pdf_engine.open_pdf(data)
        except pdf_engine.PdfEngineError as exc:
            raise IngestError("corrupt_pdf", "PDF 檔案損壞或無法解析。") from exc

        n_pages = pdf_engine.page_count(doc)

        if n_pages < 1:
            raise IngestError("corrupt_pdf", "PDF 沒有任何頁面。")

        if n_pages > config.MAX_PAGES:
            raise IngestError(
                "too_many_pages",
                f"頁數過多,超過頁數上限 {config.MAX_PAGES} 頁。",
            )
    finally:
        if doc is not None:
            pdf_engine.close(doc)

    # Persist: originals (immutable, 0o444), work (editable PDF), pristine (reset source PDF).
    # For PDF uploads originals == work == pristine bytes; the structural separation matters
    # for the image upload path (T-04-01-02 below) where originals != work/pristine.
    session_id = storage.new_session()
    safe_name = storage.sanitize_filename(filename)
    storage.write_original(session_id, safe_name, data)
    storage.write_work_copy(session_id, data)
    storage.write_pristine_copy(session_id, data)
    storage.write_session_meta(session_id, page_count=n_pages, filename=safe_name)

    return SessionInfo(
        session_id=session_id,
        page_count=n_pages,
        filename=safe_name,
    )


def _ingest_image_to_pdf(filename: str, data: bytes, kind: str) -> SessionInfo:
    """Normalize an image upload (PNG/JPG/TIFF) into a single-page A4 PDF session.

    Phase 4 D-01 / UPLOAD-03: the user's raw image bytes stay in ``originals/`` (so the
    SHA-256 invariant D-05 keeps proving the upload was preserved), while ``work/`` and
    ``pristine/`` hold the normalized A4 PDF. The pipeline will reset its work copy from
    pristine/ (T-04-01-02 Step 5), so it never opens the raw image bytes as a PDF.
    """
    # Pillow chain: verify -> n_frames check -> format allowlist -> CMYK/alpha convert -> load -> re-emit.
    normalized_bytes = _ingest_image(data, kind)

    # Wrap into a single-page A4 PDF via the fitz seam.
    pdf_bytes = pdf_engine.image_to_a4_pdf(normalized_bytes)

    # Defensive: open + count to ensure the wrapper produced a valid PDF.
    doc = pdf_engine.open_pdf(pdf_bytes)
    try:
        n_pages = pdf_engine.page_count(doc)
        if n_pages != 1:
            raise IngestError(
                "corrupt_pdf",
                "正規化失敗,影像無法產出有效 PDF。",
            )
    finally:
        pdf_engine.close(doc)

    session_id = storage.new_session()
    safe_name = storage.sanitize_filename(filename)
    # originals/ keeps the user's raw image bytes (SHA-256 invariant, D-05).
    storage.write_original(session_id, safe_name, data)
    # work/ and pristine/ hold the normalized A4 PDF — work is the editing substrate,
    # pristine is the pipeline reset source.
    storage.write_work_copy(session_id, pdf_bytes)
    storage.write_pristine_copy(session_id, pdf_bytes)
    storage.write_session_meta(session_id, page_count=1, filename=safe_name)

    return SessionInfo(
        session_id=session_id,
        page_count=1,
        filename=safe_name,
    )


def ingest_upload(filename: str, data: bytes) -> SessionInfo:
    """Validate + store an uploaded PDF or image, returning its :class:`SessionInfo`.

    Phase 4 dispatch: PDF goes to :func:`_ingest_pdf` (Phase 1 path), images
    (PNG / JPG / TIFF) go to :func:`_ingest_image_to_pdf` (UPLOAD-03 / D-01). Every
    rejection path raises :class:`IngestError` with a stable code mapped to a 4xx by
    the API layer — never a 500.
    """
    # 1. Empty.
    if not data:
        raise IngestError(
            "empty_file",
            "檔案是空的,請選擇有內容的 PDF 或影像。",
        )

    # 2. Oversize — reject before doing any parsing work (DoS mitigation T-01-01).
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise IngestError(
            "file_too_large",
            f"檔案過大,超過大小上限 {config.MAX_UPLOAD_MB} MB。",
        )

    # 3. Content sniff (extension not trusted, D-12 / T-01-06).
    kind = _sniff_kind(data)
    if kind is None:
        raise IngestError(
            "unsupported_type",
            "不支援的檔案類型,僅接受 PDF、PNG、JPG、TIFF。",
        )

    if kind == "pdf":
        return _ingest_pdf(filename, data)
    return _ingest_image_to_pdf(filename, data, kind)
