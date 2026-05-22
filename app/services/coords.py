"""Centralized coordinate mapper — the single px<->pt conversion chokepoint.

This is the highest-risk component of the tool (research PITFALLS 1-2, ARCHITECTURE
Pattern 2, Build-Order step 3): an off-by-rotation or off-by-DPI mapping silently
redacts the WRONG area. Every edit path (redaction in Plan 02-02, logo placement in
Phase 3) routes through here so the mapping is correct exactly once, by construction
(REMOVE-03 — "所見即所得", correct even on rotated pages).

The three concerns it gets right together:
  (a) DPI scale  — a pixmap rendered at ``dpi`` is scaled ``dpi/72`` from points, so
      ``point = pixel * 72 / dpi`` (PDF uses 72 points/inch).
  (b) Origin     — PyMuPDF ``Rect``/``get_pixmap`` are top-left origin, matching the
      browser image; we do NOT hand-flip Y (Anti-Pattern 4) and never touch raw
      MediaBox numbers — ``page.rect``/derotation handle the offset.
  (c) Rotation   — the rendered image is the ROTATED page, but PyMuPDF edits operate on
      the UNROTATED page, so the rect is carried back via ``page.derotation_matrix``.

PURITY (threat T-02-03): this module does NOT import the engine library (``fitz``),
no FastAPI, and does no file/network I/O. It receives an already-open page object from
its caller and reaches the rotation matrices ONLY through ``pdf_engine`` wrappers, so
the engine import stays confined to that one seam module. The ``Rect`` returned by
:func:`pixels_to_pdf_rect` is the object the seam produced — coords never constructs
one — so it is a usable engine ``Rect`` for the downstream redaction pipeline while this
module stays engine-free. (The acceptance check greps for the literal engine-import
line, which deliberately appears nowhere in this file.)
"""

from __future__ import annotations

from . import pdf_engine


def _normalize_tuple(
    rect: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Return ``(x0, y0, x1, y1)`` with ``x0<=x1`` and ``y0<=y1``.

    Makes a reversed drag (bottom-right -> top-left) map identically to a forward one,
    in plain floats (no fitz dependency).
    """
    x0, y0, x1, y1 = rect
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    return (x0, y0, x1, y1)


def pixels_to_pdf_rect(px_rect, dpi: int, page):
    """Map an image-pixel rect to a PyMuPDF ``Rect`` on the UNROTATED page.

    ``px_rect`` is ``(x0, y0, x1, y1)`` measured on exactly the PNG ``render.render_page``
    produced — preview-image pixel space, top-left origin, in the page's DISPLAYED
    (rotated) orientation. ``dpi`` MUST be the actual DPI that image was rendered at
    (echoed by the render contract; never assume a default). ``page`` is the open page
    handle from :func:`pdf_engine.get_page`.

    Recipe (ARCHITECTURE Pattern 2): scale pixels -> points by ``72/dpi`` (top-left
    origin, NO Y-flip), then map displayed -> unrotated via the page derotation matrix
    (done inside the fitz seam). Returns a normalized ``fitz.Rect``.
    """
    s = 72.0 / dpi
    x0, y0, x1, y1 = _normalize_tuple(
        (px_rect[0] * s, px_rect[1] * s, px_rect[2] * s, px_rect[3] * s)
    )
    # Matrix multiply happens inside the seam (keeps coords fitz-free); the returned
    # Rect is already normalized by the seam.
    return pdf_engine.map_rect_to_unrotated(page, (x0, y0, x1, y1))


def pdf_rect_to_pixels(rect, dpi: int, page):
    """Inverse of :func:`pixels_to_pdf_rect`: unrotated page ``Rect`` -> image pixels.

    Used to echo a server-side rect back onto the preview (e.g. the before/after
    confirmation UI). Maps unrotated -> displayed via the page rotation matrix (in the
    seam), then scales points -> pixels by ``dpi/72``. Returns a normalized
    ``(x0, y0, x1, y1)`` pixel tuple.
    """
    dx0, dy0, dx1, dy1 = pdf_engine.map_rect_to_displayed(page, rect)
    z = dpi / 72.0
    return _normalize_tuple((dx0 * z, dy0 * z, dx1 * z, dy1 * z))


def clamp_px_rect(px_rect, img_w: int, img_h: int):
    """Clamp a pixel rect to ``[0, img_w] x [0, img_h]`` and normalize it.

    Returns ``(clamped_rect, was_clamped)`` where ``clamped_rect`` is a normalized
    ``(x0, y0, x1, y1)`` tuple guaranteed inside the image box, and ``was_clamped`` is
    ``True`` ONLY when an edge actually had to be moved to a page boundary (0/img_w/img_h)
    or a NaN coordinate was seen — i.e. the selection genuinely exceeded the page.

    WR-06: ``was_clamped`` is the BOUNDARY-clamp flag, NOT a "we changed something" flag.
    Correcting a reversed drag (bottom-right -> top-left) is mere normalization and must
    NOT set it, because the frontend surfaces this flag as the user-facing notice
    "框選超出頁面範圍,已自動調整到頁面邊界" — which is wrong for an in-bounds reversed
    drag (nothing exceeded the page). So we compare the NORMALIZED input against the
    clamped output (not the raw, un-normalized tuple): the flag fires only when clamping
    moved an edge, never for a pure direction flip.

    This is the boundary guard for threat T-02-01: the HTTP layer in Plan 02-02 calls it
    on untrusted client rects so an out-of-bounds, inverted, or NaN rect can never
    produce a Rect outside the page (no read/redact outside bounds, no crash). Keeping it
    in this tested module means out-of-bounds handling lives with the mapping it guards.
    """
    raw = tuple(float(v) for v in px_rect)
    # NaN-safe: any NaN coordinate is treated as clamped to the box edge (NaN != NaN).
    cleaned = []
    nan_seen = False
    for v in raw:
        if v != v:  # NaN
            nan_seen = True
            cleaned.append(0.0)
        else:
            cleaned.append(v)
    norm = _normalize_tuple(tuple(cleaned))
    cx0 = min(max(norm[0], 0.0), float(img_w))
    cy0 = min(max(norm[1], 0.0), float(img_h))
    cx1 = min(max(norm[2], 0.0), float(img_w))
    cy1 = min(max(norm[3], 0.0), float(img_h))
    clamped_rect = (cx0, cy0, cx1, cy1)
    # Compare against the NORMALIZED input (WR-06): a reversed-but-in-bounds drag yields
    # clamped_rect == norm and is therefore NOT flagged; only a real boundary move (or NaN)
    # sets was_clamped.
    was_clamped = nan_seen or clamped_rect != norm
    return clamped_rect, was_clamped
