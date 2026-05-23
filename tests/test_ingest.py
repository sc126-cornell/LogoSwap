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


# --- Phase 4 Task 04-01-02: _sniff_kind dispatch + Pillow chain + pipeline reset ----


def test_sniff_kind_dispatches_four_magics():
    """Behavior 1: _sniff_kind returns the right kind for each of the four magic headers."""
    sk = ingest._sniff_kind
    assert sk(b"%PDF-1.7\nsome PDF content") == "pdf"
    assert sk(b"\x89PNG\r\n\x1a\n" + b"PNG payload") == "png"
    assert sk(b"\xff\xd8\xff\xe0" + b"JPEG body") == "jpeg"
    assert sk(b"II*\x00" + b"TIFF LE body") == "tiff"
    assert sk(b"MM\x00*" + b"TIFF BE body") == "tiff"
    assert sk(b"random_bytes_no_magic_at_all_what_so_ever") is None


def test_sniff_kind_pdf_tolerates_leading_offset_but_images_do_not():
    """Behavior 2: PDF magic permits ≤8 leading offset (BOMs); image magics MUST match at offset 0."""
    sk = ingest._sniff_kind
    # PDF with UTF-8 BOM (3 bytes leading) -> still pdf
    assert sk(b"\xef\xbb\xbf%PDF-1.7") == "pdf"
    # PNG with BOM is rejected (image magic does not tolerate leading offset)
    assert sk(b"\xef\xbb\xbf\x89PNG\r\n\x1a\n") is None
    # PDF too far past the leading window -> rejected
    assert sk(b"X" * 9 + b"%PDF-") is None


def test_extension_not_trusted_fake_png(client, fake_png_bytes):
    """Behavior 3: a file uploaded as evil.png whose bytes are NOT a PNG is rejected as unsupported_type."""
    resp = client.post(
        "/sessions",
        files={"file": ("evil.png", fake_png_bytes, "image/png")},
    )
    assert resp.status_code == 415
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_type"


def test_empty_file_message_mentions_image(client):
    """Behavior 4: empty file upload returns 400 with message that mentions PDF or 影像."""
    resp = client.post(
        "/sessions",
        files={"file": ("empty.pdf", b"", "application/octet-stream")},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "empty_file"
    # New copy mentions both PDF and 影像 (Phase 4 dropzone now accepts both).
    assert "影像" in detail["message"]


def test_corrupt_image_truncated_png(client):
    """Behavior 5: PNG magic header + garbage payload passes sniff but fails Pillow verify → 422 corrupt_image."""
    payload = b"\x89PNG\r\n\x1a\n" + b"garbage" * 200
    resp = client.post(
        "/sessions",
        files={"file": ("broken.png", payload, "image/png")},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "corrupt_image"


def test_multi_page_tiff_rejected(client, multipage_tiff_bytes):
    """Behavior 6: a 3-page TIFF is rejected with multi_page_tiff_unsupported 415."""
    resp = client.post(
        "/sessions",
        files={"file": ("multi.tiff", multipage_tiff_bytes, "image/tiff")},
    )
    assert resp.status_code == 415
    detail = resp.json()["detail"]
    assert detail["code"] == "multi_page_tiff_unsupported"
    assert "多頁 TIFF" in detail["message"]


def test_ingest_status_dicts_in_sync():
    """Behavior 8: main._INGEST_STATUS and api.sessions._CODE_STATUS must have identical contents."""
    from app.api.sessions import _CODE_STATUS as api_dict
    from app.main import _INGEST_STATUS as main_dict

    assert set(main_dict.keys()) == set(api_dict.keys())
    for k in main_dict:
        assert main_dict[k] == api_dict[k]
    # And every Phase-4 new code must exist with the right status
    for k, expected in (
        ("unsupported_image_format", 415),
        ("multi_page_tiff_unsupported", 415),
        ("corrupt_image", 422),
    ):
        assert main_dict[k] == expected
        assert api_dict[k] == expected


# --- Phase 4 Task 04-01-03: image end-to-end integration -----------------------------


def test_png_upload_normalizes_to_a4_pdf(client, png_bytes):
    """End-to-end: PNG upload becomes a 1-page A4 PDF; /pages/0/image renders a PNG."""
    from app import storage as _storage

    resp = client.post(
        "/sessions",
        files={"file": ("scan.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["page_count"] == 1
    assert body["filename"] == "scan.png"

    sid = body["session_id"]
    # work copy is a PDF; originals/ holds the raw PNG bytes.
    assert _storage.work_path(sid).read_bytes().startswith(b"%PDF-")
    assert _storage.original_path(sid).read_bytes() == png_bytes

    # /pages/0/image must return a PNG (the server-rendered preview of the A4 page).
    img_resp = client.get(f"/sessions/{sid}/pages/0/image")
    assert img_resp.status_code == 200
    assert img_resp.content.startswith(b"\x89PNG")


def test_jpeg_upload_normalizes_to_a4_pdf(client, jpeg_bytes):
    """End-to-end: JPEG upload becomes a 1-page A4 PDF."""
    from app import storage as _storage

    resp = client.post(
        "/sessions",
        files={"file": ("drawing.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["page_count"] == 1
    assert body["filename"] == "drawing.jpg"

    sid = body["session_id"]
    assert _storage.work_path(sid).read_bytes().startswith(b"%PDF-")


def test_tiff_upload_normalizes_to_a4_pdf(client, tiff_bytes):
    """End-to-end: single-page TIFF upload becomes a 1-page A4 PDF."""
    from app import storage as _storage

    resp = client.post(
        "/sessions",
        files={"file": ("scan.tiff", tiff_bytes, "image/tiff")},
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["page_count"] == 1
    assert body["filename"] == "scan.tiff"

    sid = body["session_id"]
    assert _storage.work_path(sid).read_bytes().startswith(b"%PDF-")


def test_cmyk_tiff_normalized_to_rgb(client, cmyk_tiff_bytes):
    """D-03: a CMYK TIFF upload must be ingested without crash and produce a valid PDF.

    Deeper colorspace inspection (RGB / ICCBased) is deferred to 04-02 — the Phase 4-01
    sanity bar is 'no crash + valid 1-page PDF'.
    """
    from app import storage as _storage
    from app.services import pdf_engine

    resp = client.post(
        "/sessions",
        files={"file": ("cmyk.tiff", cmyk_tiff_bytes, "image/tiff")},
    )
    assert resp.status_code == 201, resp.json()
    sid = resp.json()["session_id"]

    pdf_bytes = _storage.work_path(sid).read_bytes()
    doc = pdf_engine.open_pdf(pdf_bytes)
    try:
        assert pdf_engine.page_count(doc) == 1
    finally:
        pdf_engine.close(doc)


def test_originals_sha256_unchanged_after_image_run(client, png_bytes):
    """D-05: originals/ bytes (= the user's raw PNG) survive a /process run untouched.

    After Phase 4 the pipeline resets from pristine/, NOT originals/, so this invariant
    actually gets stronger for image uploads (pipeline never touches originals/ at all).
    """
    import hashlib as _hashlib

    from app import storage as _storage

    expected_sha = _hashlib.sha256(png_bytes).hexdigest()

    resp = client.post(
        "/sessions",
        files={"file": ("scan.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    # Trivial vector-branch process job. For image-only PDFs (no embedded vector content
    # in the framed area) Phase 4-01 keeps IMAGE_NONE — the raster branch is added in 04-02.
    job = {"dpi": 200, "regions": [{"page": 0, "px_rect": [50.0, 50.0, 250.0, 200.0]}]}
    proc = client.post(f"/sessions/{sid}/process", json=job)
    assert proc.status_code == 200, proc.json()

    actual_sha = _hashlib.sha256(
        _storage.original_path(sid).read_bytes()
    ).hexdigest()
    assert actual_sha == expected_sha


def test_image_upload_download_filename_uses_stem(client, png_bytes):
    """D-13: scan.png upload → download Content-Disposition carries scan_logoswap.pdf."""
    resp = client.post(
        "/sessions",
        files={"file": ("scan.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    job = {"dpi": 200, "regions": [{"page": 0, "px_rect": [50.0, 50.0, 250.0, 200.0]}]}
    proc = client.post(f"/sessions/{sid}/process", json=job)
    assert proc.status_code == 200, proc.json()

    result = client.get(f"/sessions/{sid}/result")
    assert result.status_code == 200
    cd = result.headers.get("content-disposition", "")
    # Either literal scan_logoswap.pdf or a percent-encoded variant (Phase 2 _logoswap_name).
    assert "scan_logoswap.pdf" in cd or "scan_logoswap" in cd, cd


def test_pipeline_resets_work_from_pristine_not_originals(valid_pdf_bytes, client):
    """Reset source must be pristine/, not originals/ (T-04-01-02 Step 5).

    Upload a PDF, then delete originals/source.pdf manually after ingest. A subsequent
    /process call must still succeed because the pipeline reads pristine/ — never
    originals/ — for the reset. Without this change pipeline would 5xx on a missing
    original even though work was viable.
    """
    from app import storage

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    # Make originals/ inaccessible by removing the file (chmod 0o444 → must remove
    # write bit before unlink on Windows; on POSIX unlink works regardless of file mode
    # as long as the directory is writable).
    import os
    import stat
    orig = storage.original_path(sid)
    os.chmod(orig, stat.S_IWRITE | stat.S_IREAD)
    orig.unlink()
    assert not orig.exists()

    # A /process call should still succeed because pipeline resets from pristine/.
    job = {"dpi": 200, "regions": [{"page": 0, "px_rect": [50.0, 50.0, 200.0, 150.0]}]}
    proc = client.post(f"/sessions/{sid}/process", json=job)
    assert proc.status_code == 200, proc.json()


# --------------------------------------------------------------------------------------
# Phase 4-02 Task 03: PNG upload + raster dispatch — consecutive processes are idempotent
# (reset-from-pristine on the image path, completing the 04-01 invariant under raster apply).
# --------------------------------------------------------------------------------------


def test_image_upload_consecutive_processes_idempotent(client, png_bytes):
    """A PNG upload + two consecutive /process runs (same region) produce results of
    near-identical size — the second apply resets work from pristine BEFORE running the
    raster dispatch, so the IMAGE_PIXELS blank cannot accumulate.
    """
    resp = client.post("/sessions", files={"file": ("scan.png", png_bytes, "image/png")})
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    job = {"dpi": 200, "regions": [{"page": 0, "px_rect": [200.0, 200.0, 600.0, 500.0]}]}

    proc1 = client.post(f"/sessions/{sid}/process", json=job)
    assert proc1.status_code == 200, proc1.json()
    result1 = client.get(f"/sessions/{sid}/result").content
    assert result1.startswith(b"%PDF-")

    proc2 = client.post(f"/sessions/{sid}/process", json=job)
    assert proc2.status_code == 200, proc2.json()
    result2 = client.get(f"/sessions/{sid}/result").content
    assert result2.startswith(b"%PDF-")

    # Sizes match within ~1 KiB (PDFs carry creation-time metadata so byte-exact compare
    # is impossible; a >1 KiB drift would signal IMAGE_PIXELS accumulating between runs).
    assert abs(len(result1) - len(result2)) < 1024, (
        f"size drift between consecutive raster applies: {len(result1)} vs {len(result2)} "
        "— pipeline reset-from-pristine may not be in effect on the image path"
    )
