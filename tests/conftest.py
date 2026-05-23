"""Shared pytest fixtures.

Fixtures build minimal valid vector PDFs in-memory via the pdf_engine/fitz wrapper
(so we never commit binary fixtures), and redirect ``config.DATA_DIR`` at a tmp_path so
tests never touch the real ``data/`` directory.
"""

from __future__ import annotations

import importlib

import fitz  # only the test harness may use fitz directly to BUILD fixtures
import pytest

from app import config


def _build_pdf(num_pages: int, *, width: float = 200, height: float = 300) -> bytes:
    """Return bytes of a vector PDF with ``num_pages`` pages, each with drawn content.

    Drawn text + a line make these genuine vector pages (not blank), which exercises
    the render path meaningfully.
    """
    doc = fitz.open()
    try:
        for i in range(num_pages):
            page = doc.new_page(width=width, height=height)
            page.insert_text((40, 60), f"Page {i + 1}")
            page.draw_line(fitz.Point(20, 100), fitz.Point(width - 20, 100))
        return doc.tobytes()
    finally:
        doc.close()


# --- Phase 4 in-memory image fixture builders (UPLOAD-03) ----------------------------
#
# Mirrors ``_build_pdf``'s "build bytes in-memory, return bytes, never commit binaries"
# pattern. Every test image is constructed via Pillow at fixture time so the repo stays
# binary-free and the fixtures are deterministic (same seed colours, same byte output
# across machines for the same Pillow version).

def _build_png(
    width: int = 400,
    height: int = 300,
    mode: str = "RGB",
    color: tuple = (200, 100, 50),
) -> bytes:
    """Return bytes of a single-frame PNG image (default 400x300 RGB orange)."""
    from io import BytesIO

    from PIL import Image

    img = Image.new(mode, (width, height), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_jpeg(
    width: int = 400,
    height: int = 300,
    color: tuple = (200, 100, 50),
    quality: int = 90,
) -> bytes:
    """Return bytes of a single-frame JPEG image (RGB, given quality)."""
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _build_tiff(
    width: int = 400,
    height: int = 300,
    mode: str = "RGB",
    color: tuple = (200, 100, 50),
    num_frames: int = 1,
) -> bytes:
    """Return bytes of a TIFF image.

    For ``num_frames > 1`` produces a genuine multi-page TIFF via ``save_all=True`` +
    ``append_images=[…]`` — Pillow's documented multi-page TIFF construction.
    """
    from io import BytesIO

    from PIL import Image

    base = Image.new(mode, (width, height), color)
    buf = BytesIO()
    if num_frames <= 1:
        base.save(buf, format="TIFF")
    else:
        # Build N-1 extra frames with slightly perturbed colour so they are distinct.
        extra = []
        for i in range(1, num_frames):
            shift = (i * 17) % 200
            if mode == "RGB":
                extra_color = (
                    (color[0] + shift) % 256,
                    (color[1] + shift) % 256,
                    (color[2] + shift) % 256,
                )
            else:
                extra_color = color
            extra.append(Image.new(mode, (width, height), extra_color))
        base.save(buf, format="TIFF", save_all=True, append_images=extra)
    return buf.getvalue()


def _build_cmyk_tiff(width: int = 400, height: int = 300) -> bytes:
    """Return bytes of a CMYK TIFF (CMYK PNG is not a Pillow-supported combo)."""
    from io import BytesIO

    from PIL import Image

    img = Image.new("CMYK", (width, height), (100, 100, 100, 50))
    buf = BytesIO()
    img.save(buf, format="TIFF")
    return buf.getvalue()


def _build_rgba_transparent_png(
    width: int = 400,
    height: int = 300,
    fg_color: tuple = (0, 200, 100),
) -> bytes:
    """Return RGBA PNG with a fully-transparent background + an opaque rectangle of ``fg_color``.

    Mirrors the real-world bug case the UAT surfaced (#hotfix-04-01): mind-map export
    PNGs where most pixels are ``(0, 0, 0, 0)`` (transparent black) and only the
    content nodes are opaque. Pillow ``convert("RGB")`` without an explicit white
    composite drops alpha and turns the transparent background BLACK, producing a
    black-background result PDF — Pitfall G.
    """
    from io import BytesIO

    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))  # transparent black
    draw = ImageDraw.Draw(img)
    # Opaque rectangle near the centre — proves opaque content survives the composite.
    pad_w = width // 4
    pad_h = height // 4
    draw.rectangle(
        (pad_w, pad_h, width - pad_w, height - pad_h),
        fill=(*fg_color, 255),
    )
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    """A small single-frame RGB PNG."""
    return _build_png()


@pytest.fixture
def jpeg_bytes() -> bytes:
    """A small single-frame RGB JPEG (default Pillow quality=90)."""
    return _build_jpeg()


@pytest.fixture
def tiff_bytes() -> bytes:
    """A small single-frame RGB TIFF."""
    return _build_tiff()


@pytest.fixture
def multipage_tiff_bytes() -> bytes:
    """A multi-page (3-frame) RGB TIFF — used to assert the multi_page_tiff_unsupported reject path."""
    return _build_tiff(num_frames=3)


@pytest.fixture
def cmyk_tiff_bytes() -> bytes:
    """A CMYK TIFF — used to assert the D-03 CMYK→RGB ingest conversion."""
    return _build_cmyk_tiff()


@pytest.fixture
def fake_png_bytes() -> bytes:
    """A non-image byte payload uploaded with a .png filename — sniff-failure probe."""
    return b"NOT_A_REAL_PNG_AT_ALL_DEFINITELY_BYTES" * 8


# --- Phase 4-02 raster-redact PDF fixture builders (REMOVE-02 + UPLOAD-02) -----------
#
# These build PDFs whose page content is dominated by RASTER image XObjects (mimicking
# supplier-supplied scan PDFs / OCR'd PDFs) so the raster-dispatch branch in pipeline +
# the IMAGE_PIXELS path in redact have realistic substrates. Like ``_build_pdf`` /
# ``_build_png`` they build in memory and return bytes — no committed binaries.

def _build_image_only_pdf(width: int = 800, height: int = 600) -> bytes:
    """A single-page A4 PDF whose ONLY content is one embedded raster image.

    Mimics "整頁掃描 PDF" — no text, no vectors, just one image XObject covering the
    image area (PyMuPDF's ``insert_image(page.rect, keep_proportion=True)`` letterboxes
    a non-A4-aspect image inside the page). The test harness imports fitz directly
    (sibling of ``_build_pdf``), so this stays independent of production code paths.
    """
    img_bytes = _build_png(width=width, height=height)
    doc = fitz.open()
    try:
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_image(page.rect, stream=img_bytes, keep_proportion=True)
        return doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def _build_dual_layer_ocr_pdf(
    text_words: tuple[str, ...] = ("SUPPLIER", "WORDMARK"),
    img_width: int = 800,
    img_height: int = 600,
) -> bytes:
    """A PDF with BOTH a raster background image AND an overlaid text layer.

    Mimics a scanned PDF that has been OCR'd — Pitfall 3 dual-layer leak target. The
    image is inserted on top of the page via ``insert_image`` (the typical scanned-PDF
    storage), then text is inserted via ``page.insert_text``. A single
    ``apply_redactions`` call with ``images=IMAGE_PIXELS + text=TEXT_REMOVE`` should
    clear BOTH layers (Phase 4 D-06; RESEARCH verified).
    """
    img_bytes = _build_png(width=img_width, height=img_height)
    doc = fitz.open()
    try:
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_image(page.rect, stream=img_bytes, keep_proportion=True)
        # Place text at fixed coords inside the image area for predictable framing.
        x, y = 100.0, 400.0
        for word in text_words:
            page.insert_text((x, y), word)
            x += 100.0
        return doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def _build_mixed_vector_raster_pdf() -> bytes:
    """A PDF whose page has BOTH vector content (text + line) on the lower half AND a
    raster image XObject on the upper half.

    Used to verify per-region dispatch picks the right branch for each rect: an upper
    rect overlaps the image XObject (raster branch); a lower rect does not (vector
    branch). Page is 400x600pt — fits both halves comfortably without overlap.
    """
    img_bytes = _build_png(width=200, height=150)
    doc = fitz.open()
    try:
        page = doc.new_page(width=400.0, height=600.0)
        # Upper half: raster image (200x150 keep-proportion'd into a 400x300 region).
        page.insert_image(fitz.Rect(0, 0, 400, 300), stream=img_bytes, keep_proportion=True)
        # Lower half: vector text + line.
        page.insert_text((40, 400), "VECTOR_BELOW")
        page.draw_line(fitz.Point(20, 500), fitz.Point(380, 500))
        return doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


@pytest.fixture
def image_only_pdf_bytes() -> bytes:
    """An A4 PDF whose only content is one embedded PNG image (no text, no vectors)."""
    return _build_image_only_pdf()


@pytest.fixture
def dual_layer_ocr_pdf_bytes() -> bytes:
    """An A4 PDF with an embedded image AND an overlaid text layer (mock OCR'd scan)."""
    return _build_dual_layer_ocr_pdf()


@pytest.fixture
def mixed_vector_raster_pdf_bytes() -> bytes:
    """A 400x600pt PDF with raster content in the upper half and vector in the lower."""
    return _build_mixed_vector_raster_pdf()


@pytest.fixture
def valid_pdf_bytes() -> bytes:
    """A valid 2-page vector PDF."""
    return _build_pdf(2)


@pytest.fixture
def over_page_pdf_bytes() -> bytes:
    """A valid PDF with MAX_PAGES + 1 pages (for the too_many_pages path)."""
    return _build_pdf(config.MAX_PAGES + 1)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point config.DATA_DIR at a per-test tmp dir so no real data/ is touched.

    autouse so EVERY test is isolated. Reloads modules that captured DATA_DIR at import
    time is unnecessary because storage reads ``config.DATA_DIR`` lazily at call time.
    """
    data_root = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data_root)
    yield data_root


@pytest.fixture
def ingested_session(valid_pdf_bytes):
    """Ingest a valid 2-page PDF and return its SessionInfo (real files on disk)."""
    from app.services import ingest

    return ingest.ingest_upload("design.pdf", valid_pdf_bytes)


@pytest.fixture
def logo_png_bytes() -> bytes:
    """A small transparent RGBA PNG built in-memory (no committed binary, mirrors _build_pdf).

    40x20 with a semi-transparent fill so it carries a real alpha channel (D-03) — the same
    philosophy as the in-memory PDF fixtures.
    """
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGBA", (40, 20), (255, 0, 0, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def logo_library(tmp_path, monkeypatch, logo_png_bytes):
    """Write manifest.json + a transparent PNG into a tmp LOGOS_DIR and monkeypatch config.

    Mirrors the autouse ``isolated_data_dir`` fixture: ``logo.py`` reads ``config.LOGOS_DIR``
    lazily at call time, so monkeypatching the attribute is enough. Returns the dir path.
    """
    import json

    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    (logos_dir / "placeholder.png").write_bytes(logo_png_bytes)
    manifest = [
        {"id": "placeholder", "file": "placeholder.png", "name": "預設商標", "tags": []}
    ]
    (logos_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setattr(config, "LOGOS_DIR", logos_dir)
    return logos_dir


@pytest.fixture
def client():
    """FastAPI TestClient bound to the app (httpx-backed)."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
