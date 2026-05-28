"""True-removal redaction — the core value (REMOVE-01, threat T-02-07).

Given an open page and the unrotated-page ``Rect`` the coordinate mapper produced, the
two entry points TRULY remove the content inside it (not a cover):

TRUE_REMOVAL_LIMITATION (hotfix #06 / dCt-residue, 2026-05-26)
--------------------------------------------------------------

One narrow case violates the "true removal at the content-stream level" guarantee:
when a supplier mark is rendered as a CAD-glyph decomposition (the supplier ships
each character/stroke as a separate ``type='f'`` filled path with W=0 or H=0
"zero-area" bbox), PyMuPDF's ``apply_redactions`` does NOT remove those zero-area
items in ANY graphics mode — verified for both ``LINE_ART_REMOVE_IF_COVERED``
and ``LINE_ART_REMOVE_IF_TOUCHED``. The sources remain in the content stream.

When :func:`remove_region_vector` detects DENSE zero-area residue
(``pdf_engine.ZERO_AREA_RASTER_THRESHOLD`` or more fully-inside the user rect
after ``apply_redactions``), it overlays a single solid-white image XObject on
the user rect (:func:`pdf_engine.replace_region_with_white_raster`) — the
underlying zero-area BLACK source paths remain in the content stream but are
visually superseded by an opaque image. This is an OVERLAY, not a delete, and
should be understood as a defence-in-depth measure for the cases PyMuPDF's API
cannot reach. The third-party-renderer hairline failure mode that motivated
:func:`pdf_engine.cover_zero_area_artefacts` is also resolved by the overlay
because the image is opaque across the whole rect.

Recovering a supplier mark from a dense-residue output requires BOTH (1)
removing the image XObject (one structural edit in a PDF editor) AND (2)
expanding each zero-area path's bbox to non-zero width/height (per-path
geometry surgery). The prior Phase-4 cover-routine leak only needed
re-colouring 1742 separate white covers — the hotfix #06 dispatcher closes
that step, so the new failure path is strictly harder.

True deletion of zero-area sources requires content-stream surgery (a candidate
hotfix #07 / Option B if higher assurance is required); see
``.planning/phases/05-ubuntu/hotfix-06-dct-residue/`` for the full analysis.


- :func:`remove_region_vector` — Phase 2 path. Used when the framed rect overlaps NO
  image XObject on the page (pure CAD / vector / text content). Marks the rect (grown
  ~5pt to catch stroke-wrapper survivors), applies redactions with
  ``text=TEXT_REMOVE`` + ``graphics=LINE_ART_REMOVE_IF_COVERED`` + ``images=IMAGE_NONE``,
  then asserts the (unpadded) user rect is clean of text AND of drawings WHOLLY inside
  the rect — raising :class:`RedactError` if any content that SHOULD have been removed
  survived. Originally named ``remove_region``; renamed in Phase 4 to make the branch
  explicit.

- :func:`remove_region_raster` — Phase 4 path (D-05 / D-08). Used when the framed rect
  overlaps an image XObject (mock scans / image-only PDFs / OCR'd PDFs). Adds
  ``images=IMAGE_PIXELS`` so the overlapping image pixels are blanked to white (the
  redact annot itself paints nothing — ``fill=None`` — because IMAGE_PIXELS already
  whites the pixels and an annot-fill would survive as a type='fs' drawing that defeats
  the residual-drawings assertion, Pitfall A). Post-redact assertion keeps the TEXT
  residual check (so a dual-layer OCR scan's text layer cannot leak — Pitfall 3 /
  Pitfall E) but DROPS the drawings residual check (a raster region may legitimately
  contain a vector signature or annotation that we are not asked to remove).

Vector semantics (CR-02, decided explicitly): ``LINE_ART_REMOVE_IF_COVERED`` removes only
vector paths whose bbox is FULLY COVERED by the (padded) redaction rect. A CAD line/polyline
that merely CROSSES the region boundary — extending outside it — is *not* covered and is
intentionally KEPT (the project's primary use case is a logo sitting on top of CAD linework;
clipping the through-line would damage wanted geometry). The vector branch's post-redaction
assertion is aligned with that contract: it fails only for a vector that remains WHOLLY
INSIDE the user rect (a genuine survivor of something that should have gone), never for a
boundary-crossing line that legitimately survives. Text is asserted separately (any
extractable word clipped to the user rect is the recoverable-supplier-content risk and must
be gone).

Per-region dispatch (Phase 4 D-05): which branch is invoked is decided by
:mod:`app.services.pipeline` based on ``pdf_engine.rect_overlaps_image(page, rect)``,
not by the redact module — keeping :mod:`pipeline` as the dispatcher and each entry
point single-purpose.

PURITY (threat T-02-03): this module does NOT import the engine library. Every redaction,
extraction, and constant is reached through :mod:`app.services.pdf_engine` wrappers, so the
engine import stays confined to that one seam. The text-keep redaction mode (the one that
preserves text and is therefore forbidden, Pitfall 3) is never named here — only the
true-removal ``TEXT_REMOVE`` is used — so both the AGPL import grep and the forbidden-mode
grep come back clean.
"""

from __future__ import annotations

import logging

from . import pdf_engine

# Phase 7 Option B(SEC-01)— 模組層級 logger,沿用 app/services/integrity.py:26-32 同包
# sibling 慣例(stdlib logging,non-fitz,不破 AGPL seam,per Risk Callout #5)。
# 供 remove_region_vector 內 Option B dispatcher block 發 structured log event:
#   option_b_deleted(本檔 emit)/ option_b_xobject_intersect(pdf_engine 內 emit)。
logger = logging.getLogger(__name__)

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


def remove_region_vector(page, rect) -> bool:
    """Truly remove text + vector objects inside ``rect`` on ``page`` (VECTOR branch).

    Phase 4 — renamed from ``remove_region`` to make explicit it is the VECTOR branch;
    sibling :func:`remove_region_raster` handles the raster-overlap case (Pitfall 3
    dual-layer leak + Pitfall A fill survivor). ``rect`` is the unrotated-page
    ``fitz.Rect`` from ``coords.pixels_to_pdf_rect`` (already clamped to the page by
    the caller). Steps:

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

    # Phase 7 Option B — page-level content-stream surgery (SEC-01)。
    # 真正刪除 fully-inside-rect 零面積 type='f' fills(CAD-glyph 供應商商標分解),
    # upstream defense before 既有 Phase 5 Hotfix 06 dispatcher(form-XObject 內巢狀
    # 殘留時才會走下方 dense/sparse last-mile defense)。helper 採 D-A5 fail-safe:
    # regex 漏抓時 return 0 + 內部 logger.warning,絕不 raise、絕不破壞性寫回,故此處
    # 不包 try/except(包了反而吞掉 helper 的 warning,失去 SEC-03 透明化)。
    # NOTE: 傳入的是 fitz.Rect 物件 ``rect``(非上方的 user_rect tuple)— Plan 07-01
    # helper 簽名收 fitz.Rect 並於內部自行轉 tuple。
    deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, rect)
    if deleted > 0:
        logger.info(
            "option_b_deleted", extra={"page_index": page.number, "count": deleted}
        )
    # SEC-03 透明化:page-level only 策略下,form-XObject 內巢狀零面積殘留不下鑽刪除,
    # 但若有 form-XObject bbox 與框選區相交則 structured-log(emit 在 pdf_engine 內)。
    pdf_engine.log_xobject_intersect(page, rect, logger=logger)

    # Zero-area artefact cleanup — dispatched on residue DENSITY (hotfix #06,
    # dCt-residue).
    #
    # Background: ``LINE_ART_REMOVE_IF_COVERED`` leaves zero-area filled paths
    # (``type='f'`` with W=0 or H=0) in the content stream because PyMuPDF treats
    # them as non-coverable (verified for both COVERED and TOUCHED graphics modes).
    # The Phase 4 hotfix #5 routine ``cover_zero_area_artefacts`` paints a ±0.5 pt
    # white rectangle PER artefact to suppress the 1-px hairline third-party
    # readers render. That works fine for SPARSE residue (a few isolated CAD
    # corners, no shape leak).
    #
    # Failure mode this dispatcher closes: when the residue is DENSE and the
    # underlying paths trace a recognizable shape (a supplier-logo CAD glyph
    # decomposition, 1742 paths in the 3013A-13A-C6-... reproduction), the UNION
    # of the per-artefact covers reproduces that shape, and re-colouring the
    # covers any non-white colour recovers the original supplier mark.
    #
    # Dispatch: count residual zero-area FILLS fully inside the user rect (the same
    # population the cover routine would paint over). If that count crosses
    # ``ZERO_AREA_RASTER_THRESHOLD``, swap the per-artefact cover strategy for a
    # single solid-white image XObject overlay (``replace_region_with_white_raster``)
    # — no per-stroke COVER geometry to re-colour as an attack.
    #
    # HONEST LIMITATION (mirrors replace_region_with_white_raster's docstring and
    # the module-level TRUE_REMOVAL_LIMITATION note): the dense branch removes the
    # COVERS' attack surface but does NOT delete the zero-area BLACK source paths
    # from the content stream — they remain, visually superseded by the opaque
    # image XObject. Recovery now requires removing the image AND per-path bbox
    # surgery (strictly harder than re-colouring vector covers, but not impossible).
    # True content-stream deletion of zero-area sources is deferred to a future
    # content-stream-surgery hotfix (Option B / #07).
    #
    # Done AFTER the residual assertion so neither code path can trip
    # ``get_drawings_fully_inside`` (zero-area fills are already excluded from that
    # assertion via the same _DEGENERATE_BBOX_EPS, IN-01).
    zero_area_count = pdf_engine.count_zero_area_fills_fully_inside(page, user_rect)
    if zero_area_count >= pdf_engine.ZERO_AREA_RASTER_THRESHOLD:
        # Dense-residue path: single white image XObject covers the whole rect.
        pdf_engine.replace_region_with_white_raster(page, user_rect)
        # Post-condition: the safe-landing diagnostic helper from the same hotfix.
        # After the raster overlay, no non-degenerate white-fill DRAWINGS should
        # intersect the rect — the dense path deliberately does NOT call
        # ``cover_zero_area_artefacts`` (the source of the legacy per-artefact
        # cover drawings the helper detects). The image XObject is not a drawing
        # and is not counted by this helper. If the assertion ever fails, it
        # means a future change re-introduced cover-style paint into the dense
        # path; failing closed is correct (T-02-07: never silently leave
        # recoverable supplier content).
        whitepaint = pdf_engine.get_white_fill_drawings_intersecting(page, user_rect)
        if whitepaint:
            raise RedactError(
                "residual_whitepaint",
                "raster fallback 後仍偵測到 white-paint 殘留,raster overlay 未生效。",
            )
    else:
        # Sparse-residue path: per-artefact hairline cover (the Phase 4 #5
        # behaviour). Strokes (type='s') are preserved — REMOVE_IF_COVERED
        # already handles them and any boundary-crossing CAD line stays
        # untouched by this routine.
        pdf_engine.cover_zero_area_artefacts(page, user_rect)

    return True


def remove_region_raster(page, rect) -> bool:
    """Truly remove raster image pixels + any overlaid text inside ``rect`` (RASTER branch).

    Phase 4 D-05 / D-08 sibling of :func:`remove_region_vector`. The pipeline routes here
    when ``pdf_engine.rect_overlaps_image(page, rect)`` returned True — i.e. the framed
    rect overlaps at least one image XObject on the page (mock scans, image-only PDFs,
    OCR'd dual-layer PDFs).

    Three deltas vs :func:`remove_region_vector` (Phase 4 D-09 + RESEARCH Pattern 5):

      1. ``images=pdf_engine.IMAGE_PIXELS`` (not IMAGE_NONE) — PyMuPDF blanks the
         overlapping image pixels to white. Full-frame overlap auto-removes the image
         xref; partial overlap preserves the non-overlapping pixels (RESEARCH verified).
      2. Skip the ``(not had_text and not had_drawings)`` short-circuit — a raster region
         may consist of ONLY image content (no extractable text, no vector drawings); we
         still must run apply_redactions to blank the pixels. The pipeline only routes
         here when ``rect_overlaps_image`` returned True, so there IS image content to
         blank by construction.
      3. Skip the ``residual_covered_drawings`` post-redact assertion — a raster region
         is ALLOWED to contain legitimate drawings (e.g. a CAD vector signature on a
         scan, an annotation overlay). The raster branch's true-removal guarantee is the
         IMAGE_PIXELS pixel-blank, NOT the drawing graph.

    Text-residual assertion IS retained — Pitfall 3 / Pitfall E dual-layer OCR leak
    (a scan PDF with an OCR'd text layer): the OCR text is NOT a raster pixel, it
    lives in the page object stream. ``text=TEXT_REMOVE`` in the single apply_redactions
    call clears it, and ``get_text_words_in_rect`` over the unpadded rect afterward is
    the last-line check that nothing extractable survived (RESEARCH verified on the
    dual_layer_ocr fixture: ``['SUPPLIER', 'WORDMARK']`` → ``[]``).

    fill=None (not (1,1,1)): RESEARCH Pitfall A — ``fill=(1,1,1)`` leaves a ``type='fs'``
    drawing with rect == redact_rect, which (a) IS a cover (the forbidden pattern),
    (b) IS itself a survivor of ``get_drawings_fully_inside`` if any test ever runs
    the vector assertion against a raster-redacted region. IMAGE_PIXELS itself blanks
    the pixels to white — annot fill is redundant AND harmful.
    """
    user_rect = (rect.x0, rect.y0, rect.x1, rect.y1)

    if _is_empty(user_rect):
        return False

    # Pad to catch stroke wrappers (Pitfall 4) BEFORE marking the annotation. The raster
    # branch keeps the same ~5pt pad because OCR text glyph bboxes (the Pitfall 3 leak
    # target) often have stroke wrappers extending past the visible glyph.
    padded = _pad(rect, REDACT_PAD_PT)
    padded_fitz = pdf_engine.map_tuple_to_rect(padded)
    # fill=None: see docstring (Pitfall A defence). IMAGE_PIXELS will white the pixels.
    pdf_engine.add_redact_annot(page, padded_fitz, fill=None)

    pdf_engine.apply_redactions(
        page,
        text=pdf_engine.TEXT_REMOVE,                    # D-06 dual-layer OCR clean
        graphics=pdf_engine.LINE_ART_REMOVE_IF_COVERED, # raster 區允許未覆蓋的 drawing 殘留
        images=pdf_engine.IMAGE_PIXELS,                 # D-08 raster blank to white
    )

    # Raster post-redact assertion: TEXT ONLY (Pitfall 3 / Pitfall E).
    # Drawings residual is intentionally NOT asserted (see docstring deltas #3).
    residual_words = pdf_engine.get_text_words_in_rect(page, user_rect)
    if residual_words:
        raise RedactError(
            "residual_content",
            "移除後仍偵測到殘留文字,無法保證真正移除。",
        )

    return True
