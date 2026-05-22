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
