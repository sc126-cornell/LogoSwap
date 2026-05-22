"""True-removal redaction — the core value (REMOVE-01, threat T-02-07).

Given an open page and the unrotated-page ``Rect`` the coordinate mapper produced,
:func:`remove_region` TRULY removes the text and vector objects inside it (not a cover):
it marks the rect (grown ~5pt to catch stroke-wrapper survivors), applies redactions with
``text=PDF_REDACT_TEXT_REMOVE`` + ``graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED``, then
ASSERTS the (unpadded) user rect is clean afterward — raising :class:`RedactError` if any
content that SHOULD have been removed survived.

Vector semantics (CR-02, decided explicitly): ``LINE_ART_REMOVE_IF_COVERED`` removes only
vector paths whose bbox is FULLY COVERED by the (padded) redaction rect. A CAD line/polyline
that merely CROSSES the region boundary — extending outside it — is *not* covered and is
intentionally KEPT (the project's primary use case is a logo sitting on top of CAD linework;
clipping the through-line would damage wanted geometry). The post-redaction assertion is
aligned with that contract: it fails only for a vector that remains WHOLLY INSIDE the user
rect (a genuine survivor of something that should have gone), never for a boundary-crossing
line that legitimately survives. Text is asserted separately (any extractable word clipped to
the user rect is the recoverable-supplier-content risk and must be gone).

PURITY (threat T-02-03): this module does NOT import the engine library. Every redaction,
extraction, and constant is reached through :mod:`app.services.pdf_engine` wrappers, so the
engine import stays confined to that one seam. The text-keep redaction mode (the one that
preserves text and is therefore forbidden, Pitfall 3) is never named here — only the
true-removal ``TEXT_REMOVE`` is used — so both the AGPL import grep and the forbidden-mode
grep come back clean.
"""

from __future__ import annotations

from . import pdf_engine

# Pitfall 4: a stroked path's wrapping rectangle is larger than the visible line (line
# width x 1.5 per direction, default miter limit 10). Growing the redaction rect by ~5pt
# on every side catches those survivors. The emptiness assertion below is checked over the
# ORIGINAL (unpadded) user rect so the padding can never MASK an incomplete removal.
REDACT_PAD_PT = 5.0


class RedactError(Exception):
    """Typed redaction failure carrying a stable ``code`` (e.g. "residual_content").

    The API layer maps this to a structured ``{detail:{code,message}}`` 4xx rather than
    letting it escape as a bare 500 (threat T-02-08).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _pad(rect, pad: float):
    """Return a (x0,y0,x1,y1) tuple grown by ``pad`` on every side.

    Accepts the fitz Rect the mapper produced (read its ``.x0``…``.y1`` coords without
    importing fitz) and returns a plain tuple the seam re-wraps. Growing means x0/y0 move
    out (smaller) and x1/y1 move out (larger).
    """
    return (rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)


def _is_empty(rect_tuple) -> bool:
    """A degenerate (zero/negative-area) rect contains nothing to remove."""
    x0, y0, x1, y1 = rect_tuple
    return x1 <= x0 or y1 <= y0


def remove_region(page, rect) -> bool:
    """Truly remove text + vector objects inside ``rect`` on ``page``.

    ``rect`` is the unrotated-page ``fitz.Rect`` from ``coords.pixels_to_pdf_rect`` (already
    clamped to the page by the caller). Steps:

      1. Read the UNPADDED user rect as a plain tuple (the assertion reference).
      2. If that rect already has no extractable text AND no vector drawing, there is
         nothing to remove — return ``False`` (the UI "沒有可移除的內容" notice). This is
         NOT an error.
      3. Otherwise pad the rect ~5pt, ``add_redact_annot`` (white fill), then
         ``apply_redactions`` with the true-removal flags.
      4. ASSERT the unpadded rect now has no extractable text words AND no vector drawing
         lying WHOLLY INSIDE it; raise :class:`RedactError("residual_content")` only if
         something that should have been removed survived. A line that merely crosses the
         region boundary is *expected* to survive (REMOVE_IF_COVERED) and does NOT raise
         (CR-02).

    Returns ``True`` when content was removed, ``False`` when the region was empty to begin
    with.
    """
    user_rect = (rect.x0, rect.y0, rect.x1, rect.y1)

    # A zero/negative-area rect (e.g. fully clamped away) is a no-op, never a crash.
    if _is_empty(user_rect):
        return False

    had_text = bool(pdf_engine.get_text_words_in_rect(page, user_rect))
    had_drawings = bool(pdf_engine.get_drawings_intersecting(page, user_rect))
    if not had_text and not had_drawings:
        # Nothing removable — success with removed=False (does not raise).
        return False

    # Pad to catch stroke wrappers (Pitfall 4) BEFORE marking the annotation.
    #
    # fill=None (NOT (1,1,1)): a white-fill annotation paints a *new* filled rectangle into
    # the page content stream, which then survives as a drawing whose bbox equals the
    # redaction rect — a false positive that would defeat the post-redaction emptiness
    # assertion (and is itself a "cover", the very thing we forbid). Leaving fill=None
    # truly removes the content and paints nothing, so the region reads as page background
    # and `get_drawings` over it is genuinely empty — the strongest true-removal guarantee
    # (REMOVE-01). White-on-colored raster fill is a Phase-4 concern (images untouched here).
    padded = _pad(rect, REDACT_PAD_PT)
    padded_fitz = pdf_engine.map_tuple_to_rect(padded)
    pdf_engine.add_redact_annot(page, padded_fitz, fill=None)

    # The TRUE-removal step: text=TEXT_REMOVE only — the text-keep mode is forbidden
    # (Pitfall 3 / T-02-07) and never referenced. Raster is left untouched
    # (images=IMAGE_NONE) — that is Phase 4.
    pdf_engine.apply_redactions(
        page,
        text=pdf_engine.TEXT_REMOVE,
        graphics=pdf_engine.LINE_ART_REMOVE_IF_COVERED,
        images=pdf_engine.IMAGE_NONE,
    )

    # Post-redaction assertion over the UNPADDED user rect (REMOVE-01), aligned with the
    # REMOVE_IF_COVERED contract (CR-02):
    #   - TEXT: any extractable word clipped to the user rect is the recoverable-supplier-
    #     content risk and must be gone.
    #   - VECTORS: only a drawing lying WHOLLY INSIDE the user rect is a genuine survivor of
    #     something that should have been removed. A boundary-crossing line is intentionally
    #     kept by REMOVE_IF_COVERED (it was never fully covered) and must NOT raise — that is
    #     the project's primary "logo on CAD linework" case.
    residual_words = pdf_engine.get_text_words_in_rect(page, user_rect)
    residual_covered_drawings = pdf_engine.get_drawings_fully_inside(page, user_rect)
    if residual_words or residual_covered_drawings:
        raise RedactError(
            "residual_content",
            "移除後仍偵測到殘留內容(文字或向量),無法保證真正移除。",
        )

    return True
