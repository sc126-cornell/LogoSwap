"""Render service: a work-copy page -> PNG at a known DPI + page metadata.

All ``fitz`` access is routed through :mod:`app.services.pdf_engine`, so this module
stays engine-agnostic (it never imports the engine library directly — the AGPL seam
stays intact; the only module that imports fitz is ``pdf_engine``).

The default 200 DPI (D-02) suits CAD line clarity; the ``[MIN_DPI, MAX_DPI]`` clamp is
the per-render pixel-budget guard (Pitfall 8 / threat T-01-02) so a caller cannot
request a multi-gigabyte pixmap. The render reads the ``work/`` copy ONLY — never the
immutable original (Anti-Pattern 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import config
from . import pdf_engine


class RenderError(Exception):
    """Typed render failure carrying a stable ``code`` (e.g. "page_not_found")."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RenderResult:
    """One rendered page: PNG bytes + the metadata Phase 2's coordinate mapper needs."""

    png: bytes
    img_w: int
    img_h: int
    page_w_pt: float
    page_h_pt: float
    rotation: int
    dpi: int


def clamp_dpi(dpi: int | None) -> int:
    """Clamp a requested DPI into ``[MIN_DPI, MAX_DPI]``; ``None`` -> DEFAULT_DPI."""
    if dpi is None:
        return config.DEFAULT_DPI
    return max(config.MIN_DPI, min(config.MAX_DPI, dpi))


def _validate_page_no(doc, page_no: int) -> None:
    n = pdf_engine.page_count(doc)
    if page_no < 0 or page_no >= n:
        raise RenderError(
            "page_not_found",
            f"找不到第 {page_no} 頁(共 {n} 頁)。",
        )


def render_page(
    work_pdf_path: str | Path,
    page_no: int,
    dpi: int | None = None,
) -> RenderResult:
    """Render ``page_no`` of the work-copy PDF at ``dpi`` (default 200, clamped).

    Raises :class:`RenderError("page_not_found")` for an out-of-range page. The
    document is always closed.
    """
    effective_dpi = clamp_dpi(dpi if dpi is not None else config.DEFAULT_DPI)
    doc = pdf_engine.open_pdf(work_pdf_path)
    try:
        _validate_page_no(doc, page_no)
        data = pdf_engine.render_page_to_png(doc, page_no, effective_dpi)
    finally:
        pdf_engine.close(doc)

    return RenderResult(
        png=data["png"],
        img_w=data["img_w"],
        img_h=data["img_h"],
        page_w_pt=data["page_w_pt"],
        page_h_pt=data["page_h_pt"],
        rotation=data["rotation"],
        dpi=data["dpi"],
    )


def page_meta(
    work_pdf_path: str | Path,
    page_no: int,
    dpi: int | None = None,
) -> dict:
    """Return PageMeta-shaped data for ``page_no`` without shipping the PNG.

    Pixel dims are derived from the exact (clamped) DPI so they match what
    :func:`render_page` would produce: ``img = round(pt * dpi / 72)``.
    """
    effective_dpi = clamp_dpi(dpi if dpi is not None else config.DEFAULT_DPI)
    doc = pdf_engine.open_pdf(work_pdf_path)
    try:
        _validate_page_no(doc, page_no)
        dims = pdf_engine.page_dimensions(doc, page_no)
    finally:
        pdf_engine.close(doc)

    scale = effective_dpi / 72.0
    return {
        "page_no": page_no,
        "page_w_pt": dims["page_w_pt"],
        "page_h_pt": dims["page_h_pt"],
        "rotation": dims["rotation"],
        "dpi": effective_dpi,
        "img_w": round(dims["page_w_pt"] * scale),
        "img_h": round(dims["page_h_pt"] * scale),
    }
