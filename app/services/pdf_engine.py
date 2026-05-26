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
    doc: "fitz.Document", page_no: int, dpi: int, rotate: int = 0
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
    # Apply the user's transient rotation for THIS render only: effective = intrinsic + user.
    # The doc is a freshly-opened transient handle (render opens its own copy and closes it),
    # so this never persists to the immutable original. With the page now at its effective
    # rotation, the pixmap is the rotated image AND page.derotation_matrix carries a rect framed
    # on it back to unrotated content space — the same path that already handles intrinsic
    # /Rotate, so the coordinate seam needs no change.
    if rotate:
        page.set_rotation((int(page.rotation) + int(rotate)) % 360)
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


def page_dimensions(doc: "fitz.Document", page_no: int, rotate: int = 0) -> dict:
    """Return page point dimensions + EFFECTIVE rotation WITHOUT full rasterization.

    Used by the ``/meta`` endpoint so the frontend can size the page stage before the
    image loads. Pixel dimensions are derived from the DPI by the caller.

    ``rotate`` is the user's transient rotation degrees ADDED to the page's intrinsic
    ``/Rotate`` for this measurement only (the doc is a fresh transient handle; the original
    is never touched). ``page_w_pt`` / ``page_h_pt`` are the DISPLAYED dimensions at the
    effective rotation — i.e. width/height SWAP for a net 90°/270° rotation — so the meta the
    overlay measures px against matches the rotated PNG ``render_page_to_png`` produces. The
    pixel-budget fit in ``render.py`` is order-independent (w*h), so it agrees either way.
    """
    page = doc[page_no]
    intrinsic = int(page.rotation)
    effective = (intrinsic + int(rotate)) % 360
    # PyMuPDF's page.rect ALREADY reflects the page's CURRENT /Rotate — for a quarter turn it
    # returns the DISPLAYED rect whose w/h match the rendered pixmap. We must NOT call
    # set_rotation here: render_page calls this AND render_page_to_png on the same open doc, so a
    # mutation would compound (double rotation). Instead we compute the displayed dims for the
    # EFFECTIVE rotation purely: if the net user turn is a quarter turn, swap page.rect's w/h
    # relative to its current orientation. page.rect already reflects the intrinsic /Rotate; a
    # 90/270 USER turn swaps that, a 0/180 turn keeps it.
    rect = page.rect
    swap = int(rotate) % 180 == 90
    w = float(rect.height) if swap else float(rect.width)
    h = float(rect.width) if swap else float(rect.height)
    return {
        "page_w_pt": w,
        "page_h_pt": h,
        "rotation": effective,
    }


def page_intrinsic_rotation(doc: "fitz.Document", page_no: int) -> int:
    """Return the page's intrinsic ``/Rotate`` (0/90/180/270) without rendering.

    Used by the render endpoints to compute an EFFECTIVE rotation = (intrinsic + user)
    transiently for one render, and by the pipeline to bake the user rotation onto the
    download output. The fitz access stays here (AGPL seam / threat T-02-03).
    """
    return int(doc[page_no].rotation)


def set_page_rotation(page: "fitz.Page", rotation: int) -> None:
    """Set a page's absolute ``/Rotate`` to ``rotation`` (a 0/90/180/270 multiple).

    PyMuPDF ``Page.set_rotation`` takes an ABSOLUTE angle, normalized into [0,360). This is
    the single seam the render/pipeline layers use to add the user's transient rotation to a
    page's intrinsic rotation (effective = (intrinsic + user) % 360). It never persists to the
    immutable original — callers only ever set it on a freshly-opened transient/work document.
    """
    page.set_rotation(int(rotation) % 360)


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


# --- Redaction seam (Plan 02-02 + Phase 4-02 raster branch) ---------------------------
#
# The "true removal" pipeline lives behind these wrappers so ``redact.py`` / ``pipeline.py``
# stay fitz-free (AGPL boundary / threat T-02-03). The redaction enum CONSTANTS are
# re-exported by name here so callers can pass them without importing fitz:
#   - TEXT_REMOVE                  = PDF_REDACT_TEXT_REMOVE (the only acceptable text mode;
#                                    PDF_REDACT_TEXT_NONE *keeps* text and is forbidden,
#                                    Pitfall 3)
#   - LINE_ART_REMOVE_IF_COVERED   = PDF_REDACT_LINE_ART_REMOVE_IF_COVERED (vector default,
#                                    Pitfall 4)
#   - LINE_ART_REMOVE_IF_TOUCHED   = PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED (re-exported for
#                                    callers/tests that need to reference the constant
#                                    without importing fitz; not currently used by the
#                                    pipeline. Hotfix #05 / dCt-residue investigation
#                                    empirically verified that TOUCHED does NOT remove
#                                    ZERO-AREA drawings either — both COVERED and TOUCHED
#                                    treat zero-area items as non-coverable — so switching
#                                    to TOUCHED does not address the CAD-glyph-as-zero-area
#                                    failure mode. See debug session
#                                    .planning/debug/redact-whitepaint-residue.md.)
#   - IMAGE_NONE                   = PDF_REDACT_IMAGE_NONE (raster untouched — vector
#                                    branch; Phase 2 default)
#   - IMAGE_PIXELS                 = PDF_REDACT_IMAGE_PIXELS (raster overlap: blank the
#                                    pixels of every image XObject overlapping the
#                                    redact rect; integer xref of fully-covered images
#                                    is auto-removed by PyMuPDF — Phase 4 D-08, raster
#                                    branch)
TEXT_REMOVE = fitz.PDF_REDACT_TEXT_REMOVE
LINE_ART_REMOVE_IF_COVERED = fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED
LINE_ART_REMOVE_IF_TOUCHED = fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED
IMAGE_NONE = fitz.PDF_REDACT_IMAGE_NONE
IMAGE_PIXELS = fitz.PDF_REDACT_IMAGE_PIXELS

# A4 page dimensions in PDF points (1 pt = 1/72"). D-01 of Phase 4:
# all standalone image uploads (PNG/JPG/TIFF) normalize to a single-page portrait A4
# PDF with the image fit-in-page + centered + keep_proportion=True. Constants are
# exported by name so callers in ingest.py do NOT import fitz and the AGPL seam stays
# confined to this module.
A4_WIDTH_PT = 595.0
A4_HEIGHT_PT = 842.0

# Zero-area drawing detection (Phase 4 hotfixes #04-03 — PMC.pdf — and #04-04/#04-05
# — DC.pdf). 0.01 pt ≈ 0.0035 mm — far below any humanly-visible feature, but
# large enough to absorb floating-point noise from PDF coordinate parsing.
#
# Shared by ``get_drawings_fully_inside`` (the residual-content REMOVAL assertion)
# and ``cover_zero_area_artefacts`` (the cross-renderer hairline-mask) so they
# agree on what counts as zero-area. A drift between the two would split residual
# detection from artefact masking — either (a) Adobe-rendered hairlines survive
# when the residual check ignores a wider epsilon, or (b) ``residual_content``
# false positives when the cover routine ignores a wider one. IN-01.
_DEGENERATE_BBOX_EPS = 0.01

# White-fill detection tolerance for the post-redaction "whitepaint residue" guard
# (hotfix #05 / dCt-residue). PyMuPDF returns fill colours as floats in [0, 1]; a
# numerically-exact (1.0, 1.0, 1.0) is the common case, but some content streams
# produce 0.999... due to RGB rounding. Treat any channel within 0.5 % of 1.0 as
# white. The guard itself is not wired into ``remove_region_vector``'s assertion
# yet — the dCt-residue investigation showed the residue mechanism is
# cover_zero_area_artefacts paint (not a recoverable supplier vector), so a guard
# that trips on those covers would false-positive the existing pipeline. The
# helper is shipped so the real fix (when chosen) can wire it in at the
# appropriate boundary.
_WHITE_FILL_EPS = 0.005

# Dispatch threshold for the dCt-residue fix (hotfix #06). When
# ``remove_region_vector`` finds at least this many ZERO-AREA ``type='f'`` filled
# paths fully inside the user rect AFTER apply_redactions, it switches the
# zero-area cleanup strategy from per-artefact white covers
# (:func:`cover_zero_area_artefacts`) to a single solid-white image XObject
# overlay (:func:`replace_region_with_white_raster`).
#
# Why the dispatch exists: the cover routine paints one ±0.5 pt white rectangle
# PER zero-area path. When the underlying source paths form a recognizable shape
# (e.g. a supplier logo decomposed into CAD glyph strokes — the 3013A-13A-C6-...
# reproduction file has 1742 such paths tracing a "dCt" logo), the UNION of the
# per-artefact covers reproduces that shape, and re-colouring the covers any
# non-white colour recovers the original mark — a leak this dispatcher closes
# for the high-density case.
#
# Chosen as 100 from empirical separation: legitimate DC.pdf-class CAD artefacts
# at line corners surface as a handful (single-digit to low-tens) of zero-area
# fills; supplier-logo decomposition produces hundreds to thousands. The gap is
# wide enough that the threshold is robust to a 5–10x shift in either direction.
ZERO_AREA_RASTER_THRESHOLD = 100


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

    ROTATION COMPENSATION: ``rect`` is in UNROTATED page space, but the page is displayed (and the
    download baked) with its ``/Rotate``. Without compensation the logo — drawn upright in
    unrotated space — rotates WITH the page and lands sideways in the orientation the user framed
    on. So rotate the image by ``page.rotation`` (the effective /Rotate, intrinsic + any user
    rotation the pipeline set before placement): live-verified that ``rotate == page /Rotate``
    lands the logo UPRIGHT in the displayed output for 90/180/270 (no-op at 0). This also fixes
    pages with an INTRINSIC /Rotate, where the logo was previously placed sideways.
    """
    return page.insert_image(
        rect,
        stream=stream,
        xref=xref,
        keep_proportion=True,   # contain + center (LOGO-02) — verified
        overlay=True,           # paint ON TOP of the cleaned content — verified default
        # `page.rotation` is already normalized by PyMuPDF to {0, 90, 180, 270}, so a `% 360`
        # is a no-op. Explicit `int()` matches the seam convention (see `set_page_rotation`,
        # `page_intrinsic_rotation`) so a future PyMuPDF release returning a float / numpy
        # scalar cannot silently hand `insert_image` an unexpected numeric type.
        rotate=int(page.rotation),  # keep the logo upright in the displayed (rotated) page
    )


def get_image_rects(page: "fitz.Page", xref: int) -> list:
    """Return the placed bbox(es) of the embedded image ``xref`` on ``page``.

    Thin wrapper over ``page.get_image_rects(xref)`` (mirrors :func:`get_text_words_in_rect`)
    so the LOGO-02 placement test can assert the inserted logo's bbox is contained in the
    target rect and aspect-preserved WITHOUT importing fitz (AGPL seam, threat T-02-03).
    """
    return page.get_image_rects(xref)


def rect_overlaps_image(page: "fitz.Page", rect: "fitz.Rect") -> bool:
    """True iff ``rect`` (unrotated-page points) overlaps any image XObject on ``page``.

    Used by ``pipeline.process_job`` per-region dispatch (Phase 4 D-05): given a
    user-framed rect already mapped to unrotated-page points (via
    ``coords.pixels_to_pdf_rect`` and Phase 2's derotation matrix), test whether the
    rect overlaps any image XObject placed on the page. If yes, the pipeline routes
    to ``redact.remove_region_raster`` (which sets ``images=IMAGE_PIXELS``); if no,
    it routes to ``redact.remove_region_vector`` (the original Phase 2 path,
    ``images=IMAGE_NONE``).

    Implementation: enumerate every image xref via ``page.get_images()``, then for
    each xref enumerate its placed bbox(es) via ``page.get_image_rects(xref)`` (the
    same image may appear at multiple positions). Any inclusive AABB overlap →
    True; no overlaps → False. The Rect returned by ``get_image_rects`` lives in
    UNROTATED-page space (same space as ``rect``), so no derotation matrix is needed
    here.

    Lives in pdf_engine.py because ``page.get_images`` / ``page.get_image_rects`` are
    fitz APIs — the AGPL seam invariant (threat T-02-03) requires every fitz access
    route through this module. ``redact.py`` and ``pipeline.py`` stay fitz-free.

    [VERIFIED: Phase 4 RESEARCH Pattern 4 — PyMuPDF 1.27.2.3 returns
        get_image_rects = [Rect(0.0, 197.875, 595.0, 644.125)] for a single image
        keep_proportion'd into A4 (letterboxed top/bottom).]
    """
    q = fitz.Rect(rect)
    q.normalize()
    for entry in page.get_images():
        xref = entry[0]
        for img_rect in page.get_image_rects(xref):
            ir = fitz.Rect(img_rect)
            ir.normalize()
            # AABB inclusive overlap (mirrors the degenerate-bbox-aware test in
            # ``_rects_overlap`` but kept inline here for a tight type contract:
            # this helper takes ``fitz.Rect``, ``_rects_overlap`` takes tuples).
            if ir.x0 <= q.x1 and q.x0 <= ir.x1 and ir.y0 <= q.y1 and q.y0 <= ir.y1:
                return True
    return False


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
    must NOT trip the assertion.

    EXCLUDED: **zero-area FILL drawings only** (``type == 'f'`` with width OR height ≤ ε).
    Two real-world cases surfaced these as false positives:

    - **PMC.pdf (#hotfix-04-03):** snap-target / moveto-only POINT fills (W=H=0).
    - **DC.pdf (#hotfix-04-04):** CAD glyph stroke fragments rendered as filled paths with
      W=0 (vertical flat-bbox fills, ~1700 of them in a single page's title block).

    Empirically verified: ``LINE_ART_REMOVE_IF_COVERED`` correctly removes zero-bbox-area
    STROKES (``type='s'`` from e.g. ``page.draw_line()`` with default pen — bbox H=0 but the
    stroke pen still renders a visible line, and PyMuPDF removes it). However the same mode
    does NOT remove zero-area FILLS (``type='f'``) — a fill with no extent paints nothing
    and PyMuPDF treats it as non-coverable. So a surviving zero-area fill carries no
    recoverable supplier content (zero pixels), but a surviving stroke could still be a
    visible line and must remain in the residual check. Filtering is therefore restricted
    to ``type == 'f'``.
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
        # Skip zero-area FILL drawings only (type='f'). Covers PMC.pdf POINT fills and
        # DC.pdf flat-bbox glyph fills. STROKES (type='s' / 'fs') stay in the check even
        # when bbox is flat — PyMuPDF removes coverable strokes correctly, so a residual
        # stroke is a real visible-line failure. Threshold is the module-level
        # _DEGENERATE_BBOX_EPS so the cover routine sees the same set (IN-01).
        is_zero_area = (dr.width < _DEGENERATE_BBOX_EPS or dr.height < _DEGENERATE_BBOX_EPS)
        if is_zero_area and drawing.get("type") == "f":
            continue
        if _rect_contains(query, (dr.x0, dr.y0, dr.x1, dr.y1)):
            hits.append(drawing)
    return hits


def get_white_fill_drawings_intersecting(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> list:
    """Return non-degenerate WHITE-FILL drawings whose bbox intersects ``rect``.

    Diagnostic helper introduced during the hotfix #05 / dCt-residue investigation. The
    dCt-residue failure mode shows up as a cluster of ``type='f'`` drawings with fill ≈
    (1, 1, 1) intersecting the user rect whose union of bboxes reproduces the supplier
    mark when re-coloured. This helper enumerates exactly that population.

    IMPORTANT CONTEXT: empirical analysis of the LIVE broken output
    (``3013A-13A-C6-XX-3D02-A01-00040_logoswap.pdf``) confirmed that the 1742 white-fill
    drawings inside the framed rect are NOT recoverable supplier vectors painted white —
    they are the ``cover_zero_area_artefacts`` paint covering 1742 zero-area BLACK glyph
    fills the supplier rendered as a CAD glyph stroke decomposition (each stroke has a
    bbox with W or H = 0). PyMuPDF's ``apply_redactions`` cannot remove zero-area items
    in any mode (verified for both ``LINE_ART_REMOVE_IF_COVERED`` and
    ``LINE_ART_REMOVE_IF_TOUCHED``). The covers form the visible-yet-recoverable
    "whitepaint" shape; the underlying zero-area black fills are also still in the
    content stream.

    Because the white covers are intentional pipeline output (defensive paint over CAD
    artefacts to suppress third-party-renderer hairlines), this helper is NOT wired into
    ``remove_region_vector``'s residual assertion — doing so would false-positive every
    DC.pdf-class CAD redaction the pipeline currently handles correctly. It is shipped
    so the real fix (when chosen — e.g. routing dense zero-area regions through a raster
    fallback, or content-stream surgery to delete the zero-area sources before painting)
    can use it as the post-condition oracle.

    EXCLUDED:

    - Drawings whose ``type`` is not ``'f'`` (pure fills only).
    - Zero-area FILLS (``W < ε`` or ``H < ε``) — same rationale as
      :func:`get_drawings_fully_inside`: they render zero pixels.

    Fill colour comparison: PyMuPDF returns ``fill`` as a 3-tuple of floats in [0, 1] or
    ``None``. Any non-None tuple where every channel is within :data:`_WHITE_FILL_EPS`
    of 1.0 counts as white (some content streams emit ``0.999...`` due to rounding).
    """
    q = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    q.normalize()
    query = (q.x0, q.y0, q.x1, q.y1)
    hits = []
    for drawing in page.get_drawings():
        d_rect = drawing.get("rect")
        if d_rect is None:
            continue
        if drawing.get("type") != "f":
            continue
        fill = drawing.get("fill")
        if fill is None or len(fill) < 3:
            continue
        if not all(abs(c - 1.0) <= _WHITE_FILL_EPS for c in fill[:3]):
            continue
        dr = fitz.Rect(d_rect)
        dr.normalize()
        if dr.width < _DEGENERATE_BBOX_EPS or dr.height < _DEGENERATE_BBOX_EPS:
            continue
        if _rects_overlap(query, (dr.x0, dr.y0, dr.x1, dr.y1)):
            hits.append(drawing)
    return hits


def cover_zero_area_artefacts(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> int:
    """Paint opaque white over each zero-area fill drawing fully inside ``rect``. Return count.

    Phase 4 hotfix #5 — surfaced by DC.pdf supplier CAD PDF. ``LINE_ART_REMOVE_IF_COVERED``
    leaves zero-area filled paths (``type='f'`` with W=0 or H=0) in the content stream
    because PyMuPDF treats them as non-coverable. PyMuPDF itself renders nothing for them
    (zero pixels), so ``get_drawings_fully_inside`` correctly filters them out of the
    residual assertion — BUT third-party PDF renderers (Adobe Reader / Chrome PDF.js /
    Edge Pdfium) render zero-width fills as 1-pixel HAIRLINES, surfacing as "weird marks"
    over the placed logo.

    Surgical fix: cover each zero-area artefact with a thin opaque white rectangle. Only
    drawings that are (a) ``type='f'`` AND (b) zero-area AND (c) fully inside ``rect`` are
    covered — boundary-crossing CAD construction lines (which CR-02 explicitly preserves)
    are NOT touched.

    Must be called AFTER the residual assertion so the white covers don't trip
    ``get_drawings_fully_inside``.

    The cover rect is the artefact's bbox padded by ±0.5 pt (well below any visible
    feature, large enough to mask anti-aliasing of the underlying zero-area stroke), and
    clamped to ``rect`` so we never paint outside the user's framed area.
    """
    q = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    q.normalize()
    query = (q.x0, q.y0, q.x1, q.y1)
    # ±0.5 pt halo: well below any visible feature, large enough to mask anti-aliasing
    # of the underlying zero-area stroke. Single-consumer constant — kept local because
    # ``get_drawings_fully_inside`` doesn't need a halo (it isn't painting anything).
    # The shared zero-area threshold lives at module scope as ``_DEGENERATE_BBOX_EPS``
    # (IN-01) so the two routines see the SAME set of zero-area drawings.
    _COVER_PAD = 0.5
    covered = 0
    for drawing in page.get_drawings():
        d_rect = drawing.get("rect")
        if d_rect is None:
            continue
        dr = fitz.Rect(d_rect)
        dr.normalize()
        if drawing.get("type") != "f":
            continue
        if not (dr.width < _DEGENERATE_BBOX_EPS or dr.height < _DEGENERATE_BBOX_EPS):
            continue
        if not _rect_contains(query, (dr.x0, dr.y0, dr.x1, dr.y1)):
            continue
        # Cover artefact's bbox + halo, clamped to the user rect so we never bleed outside.
        cover = fitz.Rect(
            max(dr.x0 - _COVER_PAD, query[0]),
            max(dr.y0 - _COVER_PAD, query[1]),
            min(dr.x1 + _COVER_PAD, query[2]),
            min(dr.y1 + _COVER_PAD, query[3]),
        )
        if cover.width <= 0 or cover.height <= 0:
            # Degenerate cover (user rect collapsed) — skip; the artefact is by definition
            # outside the visible page area too.
            continue
        # fill = pure white, color=None means no stroke (we don't want a 1px border).
        page.draw_rect(cover, fill=(1, 1, 1), color=None, width=0)
        covered += 1
    return covered


def count_zero_area_fills_fully_inside(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> int:
    """Count ``type='f'`` drawings with ZERO-area bbox that are fully inside ``rect``.

    Dispatcher input for the dCt-residue fix (hotfix #06): :func:`remove_region_vector`
    calls this after ``apply_redactions`` to decide whether the zero-area residue
    cleanup should use the per-artefact cover strategy (:func:`cover_zero_area_artefacts`,
    sparse case) or the single-image-overlay strategy
    (:func:`replace_region_with_white_raster`, dense case crossing
    :data:`ZERO_AREA_RASTER_THRESHOLD`).

    Contract — counts ONLY drawings that are:

    - ``type='f'`` (filled path; strokes are not the leak source — the existing cover
      routine already filters them out for the same reason).
    - Zero-area (bbox width OR height below :data:`_DEGENERATE_BBOX_EPS`, the shared
      threshold the cover routine also reads — IN-01 keeps the two functions
      aligned on what counts as zero-area).
    - Fully inside ``rect`` (matches the cover routine's containment filter, so the
      count here equals the count of covers the cover routine WOULD paint).

    Boundary-crossing CAD construction lines are intentionally NOT counted: they
    are the CR-02 case (kept by ``LINE_ART_REMOVE_IF_COVERED`` and never covered
    by the cover routine), and including them here would skew the dispatch toward
    raster fallback for any framed rect that grazes a CAD through-line.
    """
    q = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    q.normalize()
    query = (q.x0, q.y0, q.x1, q.y1)
    count = 0
    for drawing in page.get_drawings():
        d_rect = drawing.get("rect")
        if d_rect is None:
            continue
        if drawing.get("type") != "f":
            continue
        dr = fitz.Rect(d_rect)
        dr.normalize()
        if not (dr.width < _DEGENERATE_BBOX_EPS or dr.height < _DEGENERATE_BBOX_EPS):
            continue
        if not _rect_contains(query, (dr.x0, dr.y0, dr.x1, dr.y1)):
            continue
        count += 1
    return count


def replace_region_with_white_raster(
    page: "fitz.Page", rect: tuple[float, float, float, float]
) -> None:
    """Insert a single solid-white image XObject covering ``rect`` (dCt-residue fix).

    The dense-case zero-area cleanup path (hotfix #06): when the residual zero-area
    ``type='f'`` count crosses :data:`ZERO_AREA_RASTER_THRESHOLD`, the per-artefact
    cover routine (:func:`cover_zero_area_artefacts`) would paint hundreds of small
    ±0.5 pt white rectangles whose UNION reproduces the underlying supplier-logo
    shape — a recoverable leak (re-colour the covers and the original mark
    returns). This routine paints a single solid-white image XObject covering the
    entire rect instead: no per-stroke geometry, no per-rect granularity, nothing
    to re-colour back into a shape.

    Implementation notes
    --------------------

    The pixmap is generated at a small fixed resolution (32×32 RGB white). PDF
    readers scale it to fit ``rect`` using bilinear interpolation, which is
    visually indistinguishable from a per-pixel render for a solid colour. After
    ``deflate=True`` save compression the on-disk resource is well under 100
    bytes — the compressed stream of a constant-byte pixmap is essentially a
    deflate header plus a tiny run-length.

    The image is inserted with ``overlay=True`` (default), placing it ABOVE the
    existing content stream — including the zero-area source paths PyMuPDF
    cannot remove. Render order is therefore:
    ``[zero-area sources] → [residual covers, if any] → [this white image]``,
    and the image is the topmost layer.

    LIMITATION (be honest)
    ----------------------

    The zero-area BLACK source paths remain in the content stream. They are not
    deleted — only visually superseded by the image overlay. Recovering the
    original supplier mark requires:

      1. Removing this image XObject (one structural edit in a PDF editor), AND
      2. Expanding the zero-area path bboxes to non-zero width/height
         (per-path geometry surgery).

    This is strictly harder than the failure mode it replaces — the prior
    ``cover_zero_area_artefacts`` leak recovers the mark by simply re-colouring
    the per-artefact covers, no geometry surgery needed. True deletion of
    zero-area sources requires content-stream surgery (a candidate hotfix for a
    future iteration if higher assurance is required).
    """
    q = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    q.normalize()
    if q.width <= 0 or q.height <= 0:
        # Degenerate rect — caller already short-circuited on empty rects in
        # remove_region_vector via _is_empty(). Defence in depth here.
        return
    # 32×32 white pixmap. fitz.Pixmap(colorspace, bbox, alpha) created without
    # samples=... contains uninitialised bytes; clear_with(255) sets every byte
    # to 0xff, producing pure white in RGB. alpha=False keeps the resource
    # small and avoids alpha-channel handling in third-party renderers.
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32), False)
    try:
        pix.clear_with(255)
        page.insert_image(q, pixmap=pix, overlay=True)
    finally:
        # Pixmap holds a C-allocated buffer; drop the reference promptly so the
        # garbage collector can reclaim it without waiting for the next gc cycle.
        del pix


def image_to_a4_pdf(image_bytes: bytes) -> bytes:
    """Wrap an already-normalized RGB image (PNG/JPEG bytes) into a single-page A4 PDF.

    Phase 4 D-01 (standalone image normalization, UPLOAD-03): standalone PNG/JPG/TIFF
    uploads become portrait A4 (595×842 pt) single-page PDFs with the image fit-in-page,
    keep_proportion=True (contain + center), and white page background as the fill.

    The caller (``ingest._ingest_image_to_pdf``) must hand bytes that Pillow has already
    decoded, CMYK→RGB-converted (D-03 / Pitfall D black-box defence), and re-encoded as
    PNG or JPEG. JPEG bytes pass through PyMuPDF as a JPEG XObject byte-exact, so a small
    input stays small (RESEARCH Pattern 3 verified). The wrapping PDF uses
    ``garbage=4, deflate=True, clean=True`` so the output never bloats over the input
    image size (Pitfall 9).

    This helper lives in pdf_engine.py because it must call ``fitz.open() + new_page +
    insert_image`` — those touch fitz, and the AGPL seam (threat T-02-03) requires every
    fitz call to be inside this module. ``insert_image`` with ``keep_proportion=True``
    is the same parameter already verified by ``place_logo`` (LOGO-02), so the
    fit/center semantics are not re-verified here.
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
        page.insert_image(page.rect, stream=image_bytes, keep_proportion=True)
        return doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


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
