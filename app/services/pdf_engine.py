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


# --- Redaction seam (Plan 02-02) ------------------------------------------------------
#
# The "true removal" pipeline lives behind these wrappers so ``redact.py`` / ``pipeline.py``
# stay fitz-free (AGPL boundary / threat T-02-03). The redaction enum CONSTANTS are
# re-exported by name here so callers can pass them without importing fitz:
#   - TEXT_REMOVE                  = PDF_REDACT_TEXT_REMOVE (the only acceptable text mode;
#                                    PDF_REDACT_TEXT_NONE *keeps* text and is forbidden,
#                                    Pitfall 3)
#   - LINE_ART_REMOVE_IF_COVERED   = PDF_REDACT_LINE_ART_REMOVE_IF_COVERED (vector default,
#                                    Pitfall 4)
#   - IMAGE_NONE                   = PDF_REDACT_IMAGE_NONE (raster untouched — Phase 4)
TEXT_REMOVE = fitz.PDF_REDACT_TEXT_REMOVE
LINE_ART_REMOVE_IF_COVERED = fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED
IMAGE_NONE = fitz.PDF_REDACT_IMAGE_NONE


def map_tuple_to_rect(
    rect_tuple: tuple[float, float, float, float],
) -> "fitz.Rect":
    """Wrap a plain ``(x0, y0, x1, y1)`` tuple into a normalized ``fitz.Rect``.

    ``redact.py`` pads the mapper's Rect in plain floats (staying fitz-free), then hands the
    padded tuple back through this seam to obtain a usable engine Rect for
    :func:`add_redact_annot`. Normalized so a (theoretically) inverted tuple still yields a
    valid Rect.
    """
    r = fitz.Rect(rect_tuple[0], rect_tuple[1], rect_tuple[2], rect_tuple[3])
    r.normalize()
    return r


def add_redact_annot(
    page: "fitz.Page",
    rect: "fitz.Rect",
    fill: tuple[float, float, float] | None = (1.0, 1.0, 1.0),
) -> None:
    """Mark ``rect`` for redaction on ``page``.

    A redact annotation is only a MARKER — content is not removed until
    :func:`apply_redactions` runs (Pitfall 3: covering ≠ removing). ``fill`` is the colour
    painted into the rectangle after removal: a tuple paints that colour, while ``None``
    paints NOTHING (the area reads as page background). The vector pipeline passes
    ``fill=None`` so no cover-rectangle is left behind to survive as a drawing (which would
    both be a "cover" and defeat the emptiness assertion). ``rect`` MUST already be the
    padded, unrotated-page Rect the mapper produced.
    """
    page.add_redact_annot(rect, fill=fill)


def apply_redactions(
    page: "fitz.Page",
    *,
    text: int,
    graphics: int,
    images: int,
) -> None:
    """Apply all pending redaction annotations on ``page`` — the TRUE-removal step.

    Callers pass the re-exported constants by name (e.g. ``text=pdf_engine.TEXT_REMOVE``)
    so they never import fitz. ``text=PDF_REDACT_TEXT_REMOVE`` is mandatory; the wrapper
    refuses ``PDF_REDACT_TEXT_NONE`` (which would KEEP text — Pitfall 3 / threat T-02-07)
    as a defence-in-depth guard so a forbidden mode can never silently ship extractable
    supplier content even if a caller passed it.
    """
    if text == fitz.PDF_REDACT_TEXT_NONE:
        raise PdfEngineError(
            "拒絕使用 PDF_REDACT_TEXT_NONE:該模式會保留文字,違反真正移除要求。"
        )
    page.apply_redactions(text=text, graphics=graphics, images=images)


def place_logo(
    page: "fitz.Page",
    rect: "fitz.Rect",
    *,
    stream: bytes | None = None,
    xref: int = 0,
) -> int:
    """Place a logo into ``rect`` (the SAME unrotated-page Rect the removal used).

    Centered + aspect-preserved (``keep_proportion=True`` → contain + center, D-02 / LOGO-02,
    live-verified default) and painted ON TOP of the cleaned content (``overlay=True``). MUST
    be called AFTER :func:`apply_redactions` (i.e. after ``redact.remove_region`` returns) so
    the logo is not itself redacted away (Pitfall 1).

    First placement: pass ``stream=<png bytes>`` (validated by ``logo.py``); returns the
    embedded image ``xref``. Subsequent placements of the SAME global logo (D-01): pass
    ``xref=<that value>`` and omit ``stream`` so PyMuPDF references the already-embedded object
    instead of re-embedding the PNG per region — avoids file bloat (Pitfall 4 / verified dedup).
    """
    return page.insert_image(
        rect,
        stream=stream,
        xref=xref,
        keep_proportion=True,   # contain + center (LOGO-02) — verified
        overlay=True,           # paint ON TOP of the cleaned content — verified default
    )


def get_image_rects(page: "fitz.Page", xref: int) -> list:
    """Return the placed bbox(es) of the embedded image ``xref`` on ``page``.

    Thin wrapper over ``page.get_image_rects(xref)`` (mirrors :func:`get_text_words_in_rect`)
    so the LOGO-02 placement test can assert the inserted logo's bbox is contained in the
    target rect and aspect-preserved WITHOUT importing fitz (AGPL seam, threat T-02-03).
    """
    return page.get_image_rects(xref)


def get_text_words_in_rect(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> list:
    """Return the text WORDS whose bbox intersects ``rect`` (unrotated-page points).

    Used by the post-redaction emptiness assertion (Pitfall 3): after applying redactions
    the words clipped to the user's UNPADDED rect must be empty. ``get_text("words", clip=)``
    returns a list of ``(x0, y0, x1, y1, word, block, line, word_no)`` tuples.
    """
    clip = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    return page.get_text("words", clip=clip)


def _rects_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    """Inclusive AABB overlap test that treats DEGENERATE (flat) rects as real.

    ``fitz.Rect.intersects`` returns ``False`` for an empty (zero-area) rect, but a
    horizontal/vertical stroke (a logo outline, a CAD line) has a zero-HEIGHT or
    zero-WIDTH bounding box — exactly the survivor the post-redaction assertion must catch
    (Pitfall 4). So we test interval overlap on each axis inclusively: the drawing counts
    as intersecting the query if their x-ranges overlap AND their y-ranges overlap. ``a``/``b``
    are normalized ``(x0, y0, x1, y1)`` with ``x0<=x1``, ``y0<=y1``.
    """
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    x_overlap = ax0 <= bx1 and bx0 <= ax1
    y_overlap = ay0 <= by1 and by0 <= ay1
    return x_overlap and y_overlap


def get_drawings_intersecting(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> list:
    """Return vector drawings whose bounding rect intersects ``rect`` (unrotated points).

    A stroked path that survived redaction would still report a drawing intersecting the
    (unpadded) user rect. Each drawing dict carries a ``rect`` key (its bbox); we keep only
    those that overlap the query rect (``get_drawings`` returns ALL paths on the page). The
    overlap test is inclusive and degenerate-aware so a flat-bbox stroke survivor is NOT
    missed.

    NOTE (CR-02): "intersects" is the wrong test for the post-redaction REMOVAL assertion
    because ``LINE_ART_REMOVE_IF_COVERED`` intentionally KEEPS a path that merely crosses the
    rect boundary (it is not fully covered). Use :func:`get_drawings_fully_inside` for that
    assertion; this inclusive-overlap query remains the right tool for "does any drawing touch
    the region" UI/diagnostic checks and for the test suite's survivor probes.
    """
    q = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    q.normalize()
    query = (q.x0, q.y0, q.x1, q.y1)
    hits = []
    for drawing in page.get_drawings():
        d_rect = drawing.get("rect")
        if d_rect is None:
            continue
        dr = fitz.Rect(d_rect)
        dr.normalize()
        if _rects_overlap(query, (dr.x0, dr.y0, dr.x1, dr.y1)):
            hits.append(drawing)
    return hits


def _rect_contains(
    outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]
) -> bool:
    """True when ``inner``'s bbox lies WHOLLY within ``outer`` (inclusive edges).

    Degenerate-aware: a flat (zero-width/height) stroke bbox still counts as contained when
    its single line/point falls inside ``outer``. Both are normalized ``(x0,y0,x1,y1)``.
    """
    ox0, oy0, ox1, oy1 = outer
    ix0, iy0, ix1, iy1 = inner
    return ox0 <= ix0 and oy0 <= iy0 and ix1 <= ox1 and iy1 <= oy1


def get_drawings_fully_inside(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> list:
    """Return vector drawings whose bounding rect lies WHOLLY inside ``rect`` (unrotated pts).

    This is the correct post-redaction REMOVAL assertion for vectors (CR-02): redaction with
    ``LINE_ART_REMOVE_IF_COVERED`` removes exactly the paths fully covered by the (padded)
    redaction rect, and intentionally leaves a path that only crosses the boundary. So a path
    that is still fully inside the user rect AFTER apply_redactions is a genuine survivor (a
    real failure), whereas a boundary-crossing line is an expected, legitimate survivor and
    must NOT trip the assertion. The check is degenerate-aware so a flat-bbox stroke fully
    within the rect is still counted.
    """
    q = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    q.normalize()
    query = (q.x0, q.y0, q.x1, q.y1)
    hits = []
    for drawing in page.get_drawings():
        d_rect = drawing.get("rect")
        if d_rect is None:
            continue
        dr = fitz.Rect(d_rect)
        dr.normalize()
        if _rect_contains(query, (dr.x0, dr.y0, dr.x1, dr.y1)):
            hits.append(drawing)
    return hits


def save_doc(
    doc: "fitz.Document",
    path: str | Path,
    *,
    garbage: int = 4,
    deflate: bool = True,
    clean: bool = True,
) -> None:
    """Save ``doc`` to a NEW ``path`` with garbage collection + compression (Pitfall 9).

    ``garbage=4, deflate=True, clean=True`` undoes redaction bloat and compacts the file.
    The caller MUST pass a path distinct from the immutable original (the pipeline asserts
    this) — never save back onto the upload.
    """
    doc.save(str(path), garbage=garbage, deflate=deflate, clean=clean)


def close(doc: "fitz.Document") -> None:
    """Close an open document (no-op safe)."""
    try:
        doc.close()
    except Exception:  # noqa: BLE001 — closing must never raise out of a finally
        pass
