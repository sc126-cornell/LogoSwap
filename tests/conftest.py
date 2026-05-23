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
