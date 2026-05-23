"""Ingest unit tests: page_count, original immutability, typed rejections."""

from __future__ import annotations

import hashlib

import pytest

from app import config, storage
from app.services import ingest
from app.services.ingest import IngestError


def test_ingest_valid_pdf_returns_session_and_writes_both_copies(valid_pdf_bytes):
    info = ingest.ingest_upload("design.pdf", valid_pdf_bytes)

    assert info.page_count == 2
    assert info.filename == "design.pdf"
    assert info.session_id

    # Both an immutable original and a separate work copy exist.
    assert storage.original_path(info.session_id).is_file()
    assert storage.work_path(info.session_id).is_file()


def test_ingest_original_is_byte_for_byte_identical(valid_pdf_bytes):
    info = ingest.ingest_upload("design.pdf", valid_pdf_bytes)
    stored = storage.original_path(info.session_id).read_bytes()

    assert hashlib.sha256(stored).hexdigest() == hashlib.sha256(valid_pdf_bytes).hexdigest()


def test_ingest_non_pdf_bytes_rejected_as_typed_error():
    # A ZIP magic ("PK\x03\x04") is not a PDF — must be content-sniffed, not trusted by name.
    with pytest.raises(IngestError) as exc:
        ingest.ingest_upload("totally.pdf", b"PK\x03\x04 not a pdf at all")
    assert exc.value.code in {"unsupported_type", "corrupt_pdf"}


def test_ingest_plain_text_rejected_as_typed_error():
    with pytest.raises(IngestError) as exc:
        ingest.ingest_upload("notes.pdf", b"just some plain text, definitely not a pdf")
    assert exc.value.code in {"unsupported_type", "corrupt_pdf"}


def test_ingest_corrupt_pdf_header_but_unparseable():
    # Has the %PDF- header (passes sniff) but is not a parseable document.
    with pytest.raises(IngestError) as exc:
        ingest.ingest_upload("broken.pdf", b"%PDF-1.7 then garbage \x00\x01\x02 no xref")
    assert exc.value.code == "corrupt_pdf"


def test_ingest_empty_bytes_rejected():
    with pytest.raises(IngestError) as exc:
        ingest.ingest_upload("empty.pdf", b"")
    assert exc.value.code == "empty_file"


def test_ingest_pdf_magic_buried_past_offset_is_unsupported(monkeypatch):
    # WR-05: a non-PDF whose first KB merely CONTAINS "%PDF-" (well past the leading
    # window) must be rejected at the type sniff, not passed to the parser.
    payload = b"X" * 64 + b"%PDF-1.7\n%%EOF"  # %PDF- at offset 64, beyond the 8-byte window
    with pytest.raises(IngestError) as exc:
        ingest.ingest_upload("polyglot.pdf", payload)
    assert exc.value.code == "unsupported_type"


def test_ingest_pdf_magic_after_small_bom_still_sniffs_as_pdf():
    # A 3-byte UTF-8 BOM before the header is within tolerance: sniff must accept it and
    # let the parser decide (here it is unparseable, so corrupt_pdf — proving it got past sniff).
    payload = b"\xef\xbb\xbf%PDF-1.7 then garbage \x00\x01 no xref"
    with pytest.raises(IngestError) as exc:
        ingest.ingest_upload("bom.pdf", payload)
    assert exc.value.code == "corrupt_pdf"  # passed the sniff, failed the real parse


def test_looks_like_pdf_offset_boundaries():
    # Direct unit check on the sniff helper's leading-offset rule.
    assert ingest._looks_like_pdf(b"%PDF-1.7 ...") is True  # offset 0
    assert ingest._looks_like_pdf(b"12345678%PDF-") is True  # offset 8 (inclusive bound)
    assert ingest._looks_like_pdf(b"123456789%PDF-") is False  # offset 9 (just over)
    assert ingest._looks_like_pdf(b"no header here at all") is False


def test_ingest_oversize_rejected_with_limit_in_message(monkeypatch):
    # Shrink the limit so we don't have to build a 50 MB payload.
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 50)  # message still surfaces "50"
    with pytest.raises(IngestError) as exc:
        ingest.ingest_upload("big.pdf", b"%PDF-1.7 this is more than ten bytes")
    assert exc.value.code == "file_too_large"
    assert "50" in exc.value.message


def test_ingest_too_many_pages_rejected_with_limit_in_message(over_page_pdf_bytes):
    with pytest.raises(IngestError) as exc:
        ingest.ingest_upload("many.pdf", over_page_pdf_bytes)
    assert exc.value.code == "too_many_pages"
    assert "30" in exc.value.message


# --- Phase 4 Task 04-01-01: pdf_engine.image_to_a4_pdf + storage pristine ------------


def test_image_to_a4_pdf_produces_single_a4_page(png_bytes):
    """A normalized RGB PNG passes through pdf_engine.image_to_a4_pdf into a 1-page A4 PDF.

    Behavior 1 of Task 04-01-01: page_count == 1, page width/height == 595/842 pt (D-01).
    """
    from app.services import pdf_engine

    pdf_bytes = pdf_engine.image_to_a4_pdf(png_bytes)
    assert isinstance(pdf_bytes, bytes) and pdf_bytes.startswith(b"%PDF-")

    doc = pdf_engine.open_pdf(pdf_bytes)
    try:
        assert pdf_engine.page_count(doc) == 1
        dims = pdf_engine.page_dimensions(doc, 0)
        assert dims["page_w_pt"] == pdf_engine.A4_WIDTH_PT == 595.0
        assert dims["page_h_pt"] == pdf_engine.A4_HEIGHT_PT == 842.0
    finally:
        pdf_engine.close(doc)


def test_image_to_a4_pdf_jpeg_passthrough_is_compact(jpeg_bytes):
    """Behavior 3: a small (~few KB) JPEG round-trips through image_to_a4_pdf to a
    reasonably compact PDF (well under 200KB) — proves garbage/deflate/clean are on
    and JPEG passthrough is not bloating the output.
    """
    from app.services import pdf_engine

    pdf_bytes = pdf_engine.image_to_a4_pdf(jpeg_bytes)
    # The test JPEG is ~few KB; the wrapped PDF must stay well under 200 KB.
    assert len(pdf_bytes) < 200_000, (
        f"image_to_a4_pdf inflated a small JPEG to {len(pdf_bytes)} bytes — "
        "garbage/deflate/clean not enabled?"
    )


def test_storage_pristine_directory_exists_after_new_session():
    """Behavior 4: storage.new_session() must create the pristine/ subdir alongside originals/work/outputs."""
    from app import storage

    sid = storage.new_session()
    assert storage.pristine_path(sid).parent.is_dir()


def test_storage_write_pristine_copy_writes_bytes_and_distinct_path():
    """Behavior 5: write_pristine_copy persists bytes; pristine/work/original paths are all distinct."""
    from app import storage

    sid = storage.new_session()
    payload = b"%PDF-pristine-test-bytes\n"
    written = storage.write_pristine_copy(sid, payload)
    assert written.is_file()
    assert written.read_bytes() == payload

    assert storage.pristine_path(sid) != storage.work_path(sid)
    assert storage.pristine_path(sid) != storage.original_path(sid)
    assert storage.work_path(sid) != storage.original_path(sid)
