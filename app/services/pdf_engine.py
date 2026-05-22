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


def get_page(doc: "fitz.Document", page_no: int) -> "fitz.Page":
    """Return the open fitz page object for ``page_no``.

    The coordinate mapper (:mod:`app.services.coords`) needs a page handle to derive
    its rotation matrices, but must NOT import fitz itself. It receives this opaque
    page object and reaches the matrices only through the wrappers below, keeping
    ``import fitz`` confined to this seam (AGPL boundary / threat T-02-03).
    """
    return doc[page_no]


def map_rect_to_unrotated(
    page: "fitz.Page", rect_pts: tuple[float, float, float, float]
) -> "fitz.Rect":
    """Map a DISPLAYED-space rect (points, top-left origin) to the UNROTATED page.

    ``rect_pts`` is ``(x0, y0, x1, y1)`` already scaled from pixels to points, expressed
    in the rendered/rotated orientation the user sees. Multiplying by the page's
    ``derotation_matrix`` carries it into the unrotated page space PyMuPDF edits operate
    on (Pitfall 2 / ARCHITECTURE Pattern 2). The returned :class:`fitz.Rect` is
    normalized (``x0<x1``, ``y0<y1``).

    The matrix multiply lives HERE (the fitz seam) so ``coords.py`` stays fitz-free; it
    only orchestrates the pixel<->point scale around this call.
    """
    disp = fitz.Rect(rect_pts[0], rect_pts[1], rect_pts[2], rect_pts[3])
    unrotated = disp * page.derotation_matrix
    unrotated.normalize()
    return unrotated


def map_rect_to_displayed(
    page: "fitz.Page", rect: "fitz.Rect"
) -> tuple[float, float, float, float]:
    """Inverse of :func:`map_rect_to_unrotated`: unrotated page Rect -> displayed points.

    Multiplies an unrotated-page rect by the page's ``rotation_matrix`` to get its
    position in the rendered/rotated orientation, then returns a normalized
    ``(x0, y0, x1, y1)`` tuple (still in points; the caller scales points->pixels).
    Accepts any object with rect-like coordinates (a :class:`fitz.Rect`); coords passes
    back the Rect this seam produced, so it never constructs one itself.
    """
    disp = fitz.Rect(rect) * page.rotation_matrix
    disp.normalize()
    return (disp.x0, disp.y0, disp.x1, disp.y1)


def unrotated_content_box(
    page: "fitz.Page",
    img_w: float,
    img_h: float,
    dpi: int,
) -> tuple[float, float, float, float]:
    """Return the UNROTATED content bounds the mapper/redaction operate within.

    Derived by derotating the full displayed-image rect ``(0,0,img_w,img_h)`` (scaled
    pixels->points) — i.e. exactly the space ``derotation_matrix`` maps into. This is
    MediaBox-quirk-proof: it does not rely on ``page.rect`` (which is the DISPLAYED rect
    and differs from the unrotated content box on rotated pages) nor on ``page.cropbox``
    (which PyMuPDF can derive asymmetrically after ``set_mediabox``). Plan 02-02 reuses
    this to clamp a redaction Rect into the unrotated page (threat T-02-01).
    """
    s = 72.0 / dpi
    disp = fitz.Rect(0.0, 0.0, img_w * s, img_h * s)
    box = disp * page.derotation_matrix
    box.normalize()
    return (box.x0, box.y0, box.x1, box.y1)


def close(doc: "fitz.Document") -> None:
    """Close an open document (no-op safe)."""
    try:
        doc.close()
    except Exception:  # noqa: BLE001 — closing must never raise out of a finally
        pass
