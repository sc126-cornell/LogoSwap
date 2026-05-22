"""PyMuPDF (fitz) isolation seam — the SOLE module that imports ``fitz``.

PyMuPDF is dual-licensed **AGPL-3.0 / Artifex commercial**. v1 is internal-LAN use
(AGPL acceptable), but a future "embed into the approval website" milestone may expose
the tool to external users and re-trigger the AGPL network clause. Confining every
``fitz`` call behind this boundary means the engine can be swapped (for a commercial
license or an alternative library) without touching the rest of the app. Do NOT
``import fitz`` anywhere else — the acceptance check greps for exactly this file.

It also turns untrusted-input parser crashes into typed :class:`PdfEngineError`
(threat T-01-03 / Pitfall 11): malformed PDFs become structured 4xx, never a 500 that
takes down a worker.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF — AGPL; isolated here on purpose. (see module docstring)


class PdfEngineError(Exception):
    """Raised when the underlying engine fails to open/parse a document.

    Callers (ingest, render) catch this and map it to a structured client error
    instead of letting a C-backed parser exception escape as a 500.
    """


def open_pdf(path_or_bytes: str | Path | bytes) -> "fitz.Document":
    """Open a PDF from a filesystem path or raw bytes.

    Wraps ``fitz.open`` so any parse failure on untrusted input becomes a typed
    :class:`PdfEngineError`. The document MUST be closed by the caller (use
    :func:`close`, ideally in a ``finally``).
    """
    try:
        if isinstance(path_or_bytes, (bytes, bytearray)):
            return fitz.open(stream=bytes(path_or_bytes), filetype="pdf")
        return fitz.open(str(path_or_bytes))
    except Exception as exc:  # noqa: BLE001 — deliberately broad: any C-parser failure
        raise PdfEngineError(f"無法解析 PDF: {exc}") from exc


def page_count(doc: "fitz.Document") -> int:
    """Number of pages in an open document."""
    return doc.page_count


def render_page_to_png(
    doc: "fitz.Document", page_no: int, dpi: int
) -> dict:
    """Rasterize one page to PNG bytes at ``dpi`` and return it with page metadata.

    Returns a dict with ``png`` (PNG bytes), ``img_w`` / ``img_h`` (pixel dims),
    ``page_w_pt`` / ``page_h_pt`` (UNROTATED page rect in points — ``page.rect``
    already accounts for a non-(0,0) MediaBox, Anti-Pattern 4), ``rotation``
    (0/90/180/270), and the ``dpi`` actually used.

    Routing this through the engine keeps ``render.py`` engine-agnostic (no ``fitz``
    import there). ``page_no`` is validated by the caller; we raise IndexError-style
    via PyMuPDF if out of range, which the caller maps to a 404.
    """
    page = doc[page_no]
    pix = page.get_pixmap(dpi=dpi)
    rect = page.rect  # unrotated page rect, in points
    return {
        "png": pix.tobytes("png"),
        "img_w": pix.width,
        "img_h": pix.height,
        "page_w_pt": float(rect.width),
        "page_h_pt": float(rect.height),
        "rotation": int(page.rotation),
        "dpi": dpi,
    }


def page_dimensions(doc: "fitz.Document", page_no: int) -> dict:
    """Return page point dimensions + rotation WITHOUT full rasterization.

    Used by the ``/meta`` endpoint so the frontend can size the page stage before the
    image loads. Pixel dimensions are derived from the DPI by the caller.
    """
    page = doc[page_no]
    rect = page.rect
    return {
        "page_w_pt": float(rect.width),
        "page_h_pt": float(rect.height),
        "rotation": int(page.rotation),
    }


def close(doc: "fitz.Document") -> None:
    """Close an open document (no-op safe)."""
    try:
        doc.close()
    except Exception:  # noqa: BLE001 — closing must never raise out of a finally
        pass
