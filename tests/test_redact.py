"""Redaction + deferred-mutation pipeline tests (Plan 02-02, Task 1).

Proves the core value: a region truly removes text AND vector objects on the WORK copy
(``get_text``/``get_drawings`` over the unpadded user rect empty afterward — REMOVE-01),
the immutable original's SHA-256 is unchanged across a process run (D-05), the export
``*_logoswap.pdf`` keeps ALL pages (D-07), the forbidden ``PDF_REDACT_TEXT_NONE`` constant
never appears in ``redact.py``, and fitz stays confined to ``pdf_engine.py``.

The conftest ``_build_pdf`` page has text "Page i" at point (40, 60) and a line at y=100
from x=20 to x=width-20 on a 200x300pt page — both fall inside the redaction rect computed
below, so a single region must remove BOTH.
"""

from __future__ import annotations

import ast
import glob
import hashlib
import os
from pathlib import Path

import pytest

from app import config, storage
from app.models import JobSpec, RegionMark
from app.services import coords, pdf_engine, pipeline, redact

# The conftest page geometry: 200x300pt, rendered at the default DPI (200) -> scale 200/72.
# Text is drawn near (40,60); the line spans y=100. A rect covering points (10,40)->(190,120)
# in DISPLAYED points covers both. Convert to image pixels (the px_rect contract).
_DPI = config.DEFAULT_DPI  # 200
_SCALE = _DPI / 72.0
# Points -> pixels for a 0-rotation page (top-left origin, no flip).
_REGION_PT = (10.0, 40.0, 190.0, 120.0)
_REGION_PX = tuple(v * _SCALE for v in _REGION_PT)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _open_page0(work_path):
    doc = pdf_engine.open_pdf(work_path)
    return doc, pdf_engine.get_page(doc, 0)


# --------------------------------------------------------------------------------------
# remove_region: true removal of BOTH text and vector over the unpadded user rect
# --------------------------------------------------------------------------------------


def test_remove_region_removes_text_and_vector(ingested_session):
    work = storage.work_path(ingested_session.session_id)
    doc, page = _open_page0(work)
    try:
        rect = coords.pixels_to_pdf_rect(_REGION_PX, _DPI, page)

        # Pre-condition: the region has BOTH text and a drawing to remove.
        assert pdf_engine.get_text_words_in_rect(page, (rect.x0, rect.y0, rect.x1, rect.y1))
        assert pdf_engine.get_drawings_intersecting(page, (rect.x0, rect.y0, rect.x1, rect.y1))

        removed = redact.remove_region_vector(page, rect)
        assert removed is True

        # Post-condition (REMOVE-01): unpadded user rect now empty of text AND drawings.
        words = pdf_engine.get_text_words_in_rect(page, (rect.x0, rect.y0, rect.x1, rect.y1))
        drawings = pdf_engine.get_drawings_intersecting(page, (rect.x0, rect.y0, rect.x1, rect.y1))
        assert words == [], f"residual text after redaction: {words}"
        assert drawings == [], f"residual drawings after redaction: {drawings}"
    finally:
        pdf_engine.close(doc)


def test_remove_region_pads_rect_larger_than_input(ingested_session, monkeypatch):
    # The rect handed to add_redact_annot must be LARGER than the user rect (Pitfall 4 ~5pt
    # pad). Capture the annot rect via the seam.
    work = storage.work_path(ingested_session.session_id)
    doc, page = _open_page0(work)
    captured = {}
    real_add = pdf_engine.add_redact_annot

    def _spy(pg, rect, fill=(1, 1, 1)):
        captured["rect"] = (rect.x0, rect.y0, rect.x1, rect.y1)
        return real_add(pg, rect, fill=fill)

    monkeypatch.setattr(redact.pdf_engine, "add_redact_annot", _spy)
    try:
        rect = coords.pixels_to_pdf_rect(_REGION_PX, _DPI, page)
        redact.remove_region_vector(page, rect)
        padded = captured["rect"]
        # Padded rect strictly contains the user rect on every side (~REDACT_PAD_PT).
        assert padded[0] < rect.x0 and padded[1] < rect.y0
        assert padded[2] > rect.x1 and padded[3] > rect.y1
        assert abs((rect.x0 - padded[0]) - redact.REDACT_PAD_PT) < 1e-6
    finally:
        pdf_engine.close(doc)


def test_remove_region_empty_area_returns_false_not_error(ingested_session):
    # A region over blank space (bottom-right corner, away from text/line) has nothing to
    # remove: success with removed=False, never a RedactError ("沒有可移除的內容").
    work = storage.work_path(ingested_session.session_id)
    doc, page = _open_page0(work)
    try:
        # A tiny rect near the bottom of the 300pt page, below the line (y=100) and text.
        blank_px = (5.0 * _SCALE, 250.0 * _SCALE, 25.0 * _SCALE, 270.0 * _SCALE)
        rect = coords.pixels_to_pdf_rect(blank_px, _DPI, page)
        # Ensure it really is empty first.
        assert not pdf_engine.get_text_words_in_rect(page, (rect.x0, rect.y0, rect.x1, rect.y1))
        assert not pdf_engine.get_drawings_intersecting(page, (rect.x0, rect.y0, rect.x1, rect.y1))
        assert redact.remove_region_vector(page, rect) is False
    finally:
        pdf_engine.close(doc)


def test_remove_region_fully_covered_vector_is_removed(ingested_session):
    # A vector whose bbox lies WHOLLY inside the user rect must be truly removed (the real
    # failure mode the residual assertion guards). The conftest line spans x=20..180 at y=100;
    # a rect covering x=10..190 fully covers it -> removed, no RedactError.
    work = storage.work_path(ingested_session.session_id)
    doc, page = _open_page0(work)
    try:
        full_px = tuple(v * _SCALE for v in (10.0, 90.0, 190.0, 110.0))
        rect = coords.pixels_to_pdf_rect(full_px, _DPI, page)
        rt = (rect.x0, rect.y0, rect.x1, rect.y1)
        # Pre: a drawing lies fully inside the rect.
        assert pdf_engine.get_drawings_fully_inside(page, rt), "fixture line not fully inside"
        assert redact.remove_region_vector(page, rect) is True
        # Post: no drawing remains fully inside the rect (the covered line is gone).
        assert pdf_engine.get_drawings_fully_inside(page, rt) == [], "fully-covered vector survived"
    finally:
        pdf_engine.close(doc)


def test_remove_region_boundary_crossing_line_survives_job_succeeds():
    # CR-02: a CAD line that CROSSES the region boundary (extends beyond it on both sides) is
    # only partially covered, so REMOVE_IF_COVERED correctly leaves it. The post-redaction
    # assertion must NOT raise for that legitimate survivor — the job succeeds, removed=True
    # (the text inside was removed), and the crossing line still intersects the rect.
    import fitz  # test harness builds the crossing-line fixture

    from app.services import ingest

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        # A logo wordmark fully inside the framed region...
        page.insert_text((90, 150), "LOGO")
        # ...sitting on a CAD line that runs the full page width, crossing the region on
        # BOTH sides (x=10..190 through a region we will frame at x≈80..120).
        page.draw_line(fitz.Point(10, 160), fitz.Point(190, 160))
        pdf_bytes = doc.tobytes()
    finally:
        doc.close()

    sess = ingest.ingest_upload("cadlogo.pdf", pdf_bytes)
    sid = sess.session_id

    # Frame a narrow region the line crosses: x=80..120pt, y=140..175pt (covers "LOGO" + the
    # line segment, but the line extends well beyond on both sides).
    region_px = [v * _SCALE for v in (80.0, 140.0, 120.0, 175.0)]
    spec = JobSpec(dpi=_DPI, regions=[RegionMark(page=0, px_rect=region_px)])

    # Must NOT raise RedactError("residual_content"); the job succeeds.
    result = pipeline.process_job(sid, spec)
    assert result["regions"][0]["removed"] is True
    assert result["page_count"] == 1

    # The crossing line legitimately survives (it was never fully covered) AND the logo text is
    # gone. Verify on the exported PDF.
    out = storage.outputs_dir(sid) / result["output_filename"]
    doc = pdf_engine.open_pdf(out)
    try:
        page = pdf_engine.get_page(doc, 0)
        rect = coords.pixels_to_pdf_rect(region_px, _DPI, page)
        rt = (rect.x0, rect.y0, rect.x1, rect.y1)
        # Text removed (recoverable-supplier-content risk eliminated).
        assert pdf_engine.get_text_words_in_rect(page, rt) == [], "logo text survived"
        # The through-line still exists on the page (partially covered -> kept by design).
        assert pdf_engine.get_drawings_intersecting(page, rt), (
            "the boundary-crossing line should survive (REMOVE_IF_COVERED)"
        )
        # But nothing remains WHOLLY inside the region (the real removal contract).
        assert pdf_engine.get_drawings_fully_inside(page, rt) == [], (
            "a fully-covered survivor would be a true failure"
        )
    finally:
        pdf_engine.close(doc)


def test_get_white_fill_drawings_intersecting_detects_simulated_residue():
    """Hotfix #05 / dCt-residue diagnostic helper: a simulated whitepaint residue (the
    dCt-residue shape) is detected by ``get_white_fill_drawings_intersecting``, while
    zero-area fills, non-white fills, strokes, and out-of-rect fills are EXCLUDED.

    The helper itself is not (yet) wired into the residual assertion — the dCt-residue
    investigation showed that the 1742 white-fill drawings in the broken live output are
    the ``cover_zero_area_artefacts`` pipeline paint, not recoverable supplier vectors.
    The helper is shipped so the real fix (when chosen) has a precise post-condition
    oracle to assert against.
    """
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        orig = page.get_drawings

        def _with_simulated_residue():
            return list(orig()) + [
                # Genuine residue: non-degenerate type='f' fill ≈ (1,1,1) inside the user rect.
                {
                    "rect": fitz.Rect(60.0, 60.0, 80.0, 80.0),
                    "type": "f",
                    "fill": (1.0, 1.0, 1.0),
                    "color": None,
                    "items": [],
                },
                # Floating-point rounding white (channels at 0.997): still detected.
                {
                    "rect": fitz.Rect(85.0, 60.0, 100.0, 75.0),
                    "type": "f",
                    "fill": (0.997, 0.998, 0.999),
                    "color": None,
                    "items": [],
                },
                # Zero-area white fill — must be EXCLUDED (PyMuPDF's own cover routine paints
                # these as artefact covers; they render zero pixels and carry no content).
                {
                    "rect": fitz.Rect(110.0, 60.0, 110.0, 80.0),
                    "type": "f",
                    "fill": (1.0, 1.0, 1.0),
                    "color": None,
                    "items": [],
                },
                # Black fill inside the user rect — must be EXCLUDED (not white).
                {
                    "rect": fitz.Rect(65.0, 85.0, 75.0, 95.0),
                    "type": "f",
                    "fill": (0.0, 0.0, 0.0),
                    "color": None,
                    "items": [],
                },
                # White stroked (type='s') — must be EXCLUDED (guard is fills-only).
                {
                    "rect": fitz.Rect(60.0, 100.0, 100.0, 105.0),
                    "type": "s",
                    "fill": None,
                    "color": (1.0, 1.0, 1.0),
                    "items": [],
                },
                # White fill OUTSIDE the user rect — must be EXCLUDED.
                {
                    "rect": fitz.Rect(160.0, 200.0, 180.0, 220.0),
                    "type": "f",
                    "fill": (1.0, 1.0, 1.0),
                    "color": None,
                    "items": [],
                },
            ]

        page.get_drawings = _with_simulated_residue
        user_rect = (50.0, 50.0, 130.0, 130.0)
        hits = pdf_engine.get_white_fill_drawings_intersecting(page, user_rect)
        # Exactly the two genuine white residue drawings (60..80 + 85..100), nothing else.
        assert len(hits) == 2, f"expected 2 residue hits, got {len(hits)}: {hits}"
        bboxes = [(d["rect"].x0, d["rect"].x1) for d in hits]
        assert any(60.0 <= b[0] <= 60.5 for b in bboxes), f"first residue missed: {bboxes}"
        assert any(84.5 <= b[0] <= 85.5 for b in bboxes), f"second residue missed: {bboxes}"
    finally:
        doc.close()


def test_get_white_fill_drawings_intersecting_empty_on_normal_redaction():
    """Hotfix #05 invariant: after a normal vector redaction (no zero-area glyphs), the
    helper returns 0. Pins that the helper's BASELINE on the existing pipeline is empty,
    so any future fix can use the helper's count as a regression signal.
    """
    import fitz

    from app.services import ingest

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        # Normal-area supplier-like content (no zero-area CAD glyphs) — the existing
        # pipeline handles this correctly under COVERED + fill=None + cover-routine.
        page.draw_rect(fitz.Rect(60, 60, 140, 80), color=(0, 0, 0), fill=(0, 0, 0))
        page.insert_text((70, 110), "supplier")
        pdf_bytes = doc.tobytes()
    finally:
        doc.close()

    sess = ingest.ingest_upload("supplier.pdf", pdf_bytes)
    sid = sess.session_id

    region_px = [v * _SCALE for v in (50.0, 50.0, 150.0, 120.0)]
    spec = JobSpec(dpi=_DPI, regions=[RegionMark(page=0, px_rect=region_px)])
    result = pipeline.process_job(sid, spec)
    assert result["regions"][0]["removed"] is True

    out = storage.outputs_dir(sid) / result["output_filename"]
    doc = pdf_engine.open_pdf(out)
    try:
        page = pdf_engine.get_page(doc, 0)
        rect = coords.pixels_to_pdf_rect(region_px, _DPI, page)
        rt = (rect.x0, rect.y0, rect.x1, rect.y1)
        residue = pdf_engine.get_white_fill_drawings_intersecting(page, rt)
        assert residue == [], (
            f"baseline guard count must be 0 for normal-area content; got: {residue}"
        )
    finally:
        pdf_engine.close(doc)


def test_get_drawings_fully_inside_skips_zero_area_point_cad_marker():
    """Hotfix #04-03: a degenerate POINT drawing (W=H=0) must be SKIPPED by the residual check.

    CAD exports (AutoCAD, Pillow-ELECTRA, etc.) routinely emit "snap-target" / "moveto-only"
    drawings whose bbox collapses to a single point — they render to nothing visible but show
    up in ``page.get_drawings()``. ``LINE_ART_REMOVE_IF_COVERED`` does NOT remove them
    (PyMuPDF treats zero-area items as non-coverable), so they survive apply_redactions and
    would falsely trip the residual assertion (422 residual_content). Real-world repro:
    PMC.pdf supplier CAD drawing surfaced in UAT Scenario 6.

    Direct unit test on the wrapper because PyMuPDF's high-level draw_* APIs refuse to
    produce zero-radius shapes; CAD tools emit them via raw content streams.
    """
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        # Real drawing inside the query rect to prove the wrapper still finds non-degenerate
        # survivors when the degenerate one is filtered.
        page.draw_rect(fitz.Rect(60, 50, 70, 60), color=(0, 0, 0), fill=(0, 0, 0))

        # Monkey-patch get_drawings to add a degenerate point at (95, 55) — matches the exact
        # shape of the residual artefact observed on PMC.pdf:
        #   rect=(65.34, 744.84, 65.34, 744.84), type='f', fill=(0,0,0), items=1
        orig = page.get_drawings
        def _with_marker():
            drawings = list(orig())
            drawings.append({
                "rect": fitz.Rect(95.0, 55.0, 95.0, 55.0),  # W=0, H=0 — degenerate point
                "type": "f",
                "fill": (0.0, 0.0, 0.0),
                "color": None,
                "items": [("m", fitz.Point(95.0, 55.0))],
            })
            return drawings
        page.get_drawings = _with_marker

        # Query rect covers both the real rect drawing AND the degenerate point.
        query = (50.0, 40.0, 100.0, 70.0)
        hits = pdf_engine.get_drawings_fully_inside(page, query)
        # Real rect drawing must STILL be reported (sanity).
        assert any(
            (d["rect"].width > 0.5 or d["rect"].height > 0.5) for d in hits
        ), f"non-degenerate drawing must still be found; got {hits}"
        # The degenerate point must NOT appear in residuals.
        assert not any(
            d["rect"].width < 0.01 and d["rect"].height < 0.01 for d in hits
        ), f"zero-area point leaked into residual: {hits}"
    finally:
        doc.close()


def test_get_drawings_fully_inside_skips_zero_width_flat_fill_cad_glyph():
    """Hotfix #04-04: a vertical flat-bbox FILL (W=0, H>0) must be SKIPPED — DC.pdf case.

    CAD-rendered PDFs (e.g. AutoCAD exporting Chinese glyphs as filled paths) emit ~1700+
    drawings per title block where each stroke is a filled path with zero width. PyMuPDF's
    ``LINE_ART_REMOVE_IF_COVERED`` will not remove them (zero-area items are not coverable),
    and they render zero pixels (a fill with no area paints nothing). The residual assertion
    must filter them out, otherwise CAD supplier PDFs fail with 422 residual_content even
    though every visible glyph IS gone. Real-world repro: DC.pdf, NINGBO DAN-CHIEF NETWORK
    title block.
    """
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        # Real drawing — proves the wrapper still detects non-degenerate survivors.
        page.draw_rect(fitz.Rect(60, 50, 70, 60), color=(0, 0, 0), fill=(0, 0, 0))

        # Inject CAD glyph-stroke shapes via monkey-patch: vertical W=0 fill + horizontal
        # H=0 fill, both inside the query rect.
        orig = page.get_drawings
        def _with_zero_area_fills():
            drawings = list(orig())
            drawings.append({
                "rect": fitz.Rect(65.0, 52.0, 65.0, 58.0),  # W=0, H=6 (vertical)
                "type": "f", "fill": (0.0, 0.0, 0.0), "color": None,
                "items": [("m", fitz.Point(65.0, 52.0))],
            })
            drawings.append({
                "rect": fitz.Rect(62.0, 55.0, 68.0, 55.0),  # W=6, H=0 (horizontal)
                "type": "f", "fill": (0.0, 0.0, 0.0), "color": None,
                "items": [("m", fitz.Point(62.0, 55.0))],
            })
            return drawings
        page.get_drawings = _with_zero_area_fills

        query = (50.0, 40.0, 100.0, 70.0)
        hits = pdf_engine.get_drawings_fully_inside(page, query)
        # Real rect drawing must STILL be found.
        assert any(
            (d["rect"].width > 0.5 and d["rect"].height > 0.5) for d in hits
        ), f"non-degenerate drawing must still be found; got {hits}"
        # Neither zero-area glyph stroke must appear.
        assert not any(
            d["rect"].width < 0.01 or d["rect"].height < 0.01 for d in hits
        ), f"zero-area glyph strokes leaked into residual: {hits}"
    finally:
        doc.close()


def test_cover_zero_area_artefacts_paints_white_over_filtered_residues():
    """Hotfix #04-05: zero-area FILL artefacts inside the user rect must be physically
    covered with opaque white, so third-party PDF renderers (Adobe Reader / Chrome PDF.js
    / Edge Pdfium) don't render them as 1-px hairlines.

    Boundary-crossing CAD STROKES (type='s') and any drawing OUTSIDE the user rect must
    NOT be covered. The cover is a real ``draw_rect(fill=(1,1,1))`` so it WILL appear in
    ``get_drawings()`` AFTER this routine — but the post-redact assertion that gates this
    routine runs BEFORE, so it never trips.
    """
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        # Inject the same shape DC.pdf produces: a zero-WIDTH filled vertical line inside
        # the user rect AT (50, 60)-(50, 70) — well within the rect (40, 50, 90, 80).
        # We use page.draw_line with a stroke type='s'; for type='f' we craft via PDF
        # content stream is overkill — directly use page.add_line_drawing? Easier:
        # write the page contents to inject a degenerate filled path.
        # Practical alternative: monkey-patch get_drawings to inject the shape and verify
        # the cover routine paints over it.
        orig = page.get_drawings
        def _with_zero_area():
            return list(orig()) + [{
                "rect": fitz.Rect(50.0, 60.0, 50.0, 70.0),  # W=0, H=10 (vertical fill)
                "type": "f", "fill": (0.0, 0.0, 0.0), "color": None,
                "items": [("l", fitz.Point(50, 60), fitz.Point(50, 70))],
            }, {
                "rect": fitz.Rect(60.0, 65.0, 70.0, 70.0),  # boundary-crossing real STROKE
                "type": "s", "fill": None, "color": (0.0, 0.0, 0.0),
                "items": [("l", fitz.Point(60, 65), fitz.Point(70, 70))],
            }]
        page.get_drawings = _with_zero_area
        user_rect = (40.0, 50.0, 90.0, 80.0)

        covered = pdf_engine.cover_zero_area_artefacts(page, user_rect)
        assert covered == 1, f"expected exactly 1 zero-area fill covered, got {covered}"

        # Verify a white-filled rect was drawn near the artefact's bbox (paint inside the
        # user rect, near x=50, y=60..70).
        page.get_drawings = orig  # restore real list to see what we actually drew
        actual = page.get_drawings()
        white_covers = [
            d for d in actual
            if d.get("type") == "f"
            and d.get("fill") == (1.0, 1.0, 1.0)
            and 49.0 <= d["rect"].x0 <= 51.0
            and 59.0 <= d["rect"].y0 <= 61.0
        ]
        assert white_covers, f"no white cover painted; got drawings: {[(d.get('type'), d.get('fill'), d['rect']) for d in actual]}"
    finally:
        doc.close()


def test_cover_zero_area_artefacts_skips_strokes_and_out_of_rect_fills():
    """Hotfix #04-05 counter-check: strokes are NOT covered (REMOVE_IF_COVERED handles them
    correctly) and fills OUTSIDE the user rect are also NOT covered.
    """
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        orig = page.get_drawings
        def _with_mixed():
            return list(orig()) + [
                # Zero-area STROKE inside rect — must NOT be covered (strokes excluded).
                {"rect": fitz.Rect(50.0, 60.0, 50.0, 70.0), "type": "s",
                 "fill": None, "color": (0.0, 0.0, 0.0), "items": []},
                # Zero-area FILL outside rect — must NOT be covered.
                {"rect": fitz.Rect(120.0, 100.0, 120.0, 110.0), "type": "f",
                 "fill": (0.0, 0.0, 0.0), "color": None, "items": []},
            ]
        page.get_drawings = _with_mixed
        user_rect = (40.0, 50.0, 90.0, 80.0)

        covered = pdf_engine.cover_zero_area_artefacts(page, user_rect)
        assert covered == 0, f"strokes and out-of-rect fills must be skipped; covered={covered}"
    finally:
        doc.close()


def test_get_drawings_fully_inside_keeps_zero_bbox_stroke_visible_line():
    """Hotfix #04-04 counter-check: a STROKE (``type='s'``) with bbox H=0 is a real visible
    line (pen ink renders even when bbox collapses) and MUST still be reported as a residual.

    ``page.draw_line()`` with default pen produces a stroke whose bbox is collapsed in one
    dim, but the stroke is visibly rendered AND ``LINE_ART_REMOVE_IF_COVERED`` correctly
    removes it. So a surviving zero-bbox stroke is a true failure — we must NOT filter it
    along with the zero-area fills the hotfix is targeting.
    """
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        # Default-width draw_line — produces type='s' with bbox H=0.
        page.draw_line(fitz.Point(60, 50), fitz.Point(80, 50))
        query = (50.0, 40.0, 90.0, 60.0)
        hits = pdf_engine.get_drawings_fully_inside(page, query)
        stroke_hits = [d for d in hits if d.get("type") == "s"]
        assert stroke_hits, (
            f"zero-bbox STROKE (type='s') must still be counted as a residual; got {hits}"
        )
    finally:
        doc.close()


def test_apply_redactions_refuses_text_none():
    # Defence-in-depth: the seam refuses the forbidden PDF_REDACT_TEXT_NONE mode.
    import fitz  # test harness may import fitz directly

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        page.insert_text((40, 60), "x")
        page.add_redact_annot(fitz.Rect(0, 0, 100, 100), fill=(1, 1, 1))
        with pytest.raises(pdf_engine.PdfEngineError):
            pdf_engine.apply_redactions(
                page,
                text=fitz.PDF_REDACT_TEXT_NONE,
                graphics=pdf_engine.LINE_ART_REMOVE_IF_COVERED,
                images=pdf_engine.IMAGE_NONE,
            )
    finally:
        doc.close()


# --------------------------------------------------------------------------------------
# process_job: deferred-mutation, export, page-count preservation
# --------------------------------------------------------------------------------------


def _region_jobspec() -> JobSpec:
    return JobSpec(dpi=_DPI, regions=[RegionMark(page=0, px_rect=list(_REGION_PX))])


def test_process_job_leaves_original_unchanged(ingested_session):
    sid = ingested_session.session_id
    original = storage.original_path(sid)
    before = _sha256(original)

    result = pipeline.process_job(sid, _region_jobspec())

    after = _sha256(original)
    assert before == after, "original PDF must be byte-for-byte unchanged (D-05)"
    assert result["page_count"] == 2  # all pages kept (D-07)


def test_process_job_exports_logoswap_pdf_keeping_all_pages(ingested_session):
    sid = ingested_session.session_id
    result = pipeline.process_job(sid, _region_jobspec())

    assert result["output_filename"].endswith("_logoswap.pdf")
    out = storage.outputs_dir(sid) / result["output_filename"]
    assert out.is_file(), "exported PDF must exist in outputs/"

    # Re-open the EXPORTED PDF and assert it keeps all pages and the region is truly empty.
    doc = pdf_engine.open_pdf(out)
    try:
        assert pdf_engine.page_count(doc) == 2  # D-07
        page = pdf_engine.get_page(doc, 0)
        rect = coords.pixels_to_pdf_rect(_REGION_PX, _DPI, page)
        words = pdf_engine.get_text_words_in_rect(page, (rect.x0, rect.y0, rect.x1, rect.y1))
        drawings = pdf_engine.get_drawings_intersecting(page, (rect.x0, rect.y0, rect.x1, rect.y1))
        assert words == [], f"exported PDF still has extractable text: {words}"
        assert drawings == [], f"exported PDF still has vector survivors: {drawings}"
    finally:
        pdf_engine.close(doc)


def test_process_job_redacts_work_copy_in_place(ingested_session):
    # The work copy itself is the result-render substrate: after processing it must show the
    # removed result (the region is empty when re-opened from the work path).
    sid = ingested_session.session_id
    pipeline.process_job(sid, _region_jobspec())

    work = storage.work_path(sid)
    doc = pdf_engine.open_pdf(work)
    try:
        page = pdf_engine.get_page(doc, 0)
        rect = coords.pixels_to_pdf_rect(_REGION_PX, _DPI, page)
        assert pdf_engine.get_text_words_in_rect(page, (rect.x0, rect.y0, rect.x1, rect.y1)) == []
        assert pdf_engine.get_drawings_intersecting(page, (rect.x0, rect.y0, rect.x1, rect.y1)) == []
    finally:
        pdf_engine.close(doc)


def test_process_job_filename_uses_original_stem(ingested_session):
    # ingested_session uses "design.pdf" -> "design_logoswap.pdf".
    result = pipeline.process_job(ingested_session.session_id, _region_jobspec())
    assert result["output_filename"] == "design_logoswap.pdf"


def test_logoswap_name_handles_cjk():
    # D-06 with a CJK display name (圖紙.pdf -> 圖紙_logoswap.pdf).
    assert pipeline._logoswap_name("圖紙.pdf") == "圖紙_logoswap.pdf"
    assert pipeline._logoswap_name("drawing.PDF") == "drawing_logoswap.pdf"
    assert pipeline._logoswap_name(None) == "source_logoswap.pdf"


def test_logoswap_name_caps_length_and_strips_control_chars():
    # WR-05: the stem is the (CJK) display name and ends up in a Content-Disposition header.
    # Cap its length and strip control characters so a 10 KB name or embedded CR/LF-adjacent
    # bytes cannot reach the response header.
    # Control chars (incl. CR/LF/TAB/NUL) are stripped from the stem.
    name = pipeline._logoswap_name("a\r\nb\tc\x00.pdf")
    assert name == "abc_logoswap.pdf"
    assert "\r" not in name and "\n" not in name and "\t" not in name and "\x00" not in name

    # An over-long stem is capped to MAX_STEM_LEN before the suffix.
    long_stem = "圖" * 5000
    capped = pipeline._logoswap_name(long_stem + ".pdf")
    assert capped.endswith("_logoswap.pdf")
    stem_part = capped[: -len("_logoswap.pdf")]
    assert len(stem_part) == pipeline.MAX_STEM_LEN
    assert len(stem_part) <= 128

    # A name that is ALL control chars collapses to the safe fallback stem (never empty).
    assert pipeline._logoswap_name("\x00\x01\x02.pdf") == "source_logoswap.pdf"


def test_process_job_out_of_bounds_region_is_clamped_not_crash(ingested_session):
    # A rect far beyond the page must be clamped (flagged) and not crash / not redact outside.
    sid = ingested_session.session_id
    huge_px = [10_000.0, 10_000.0, 20_000.0, 20_000.0]
    spec = JobSpec(dpi=_DPI, regions=[RegionMark(page=0, px_rect=huge_px)])
    result = pipeline.process_job(sid, spec)
    region = result["regions"][0]
    assert region["clamped"] is True
    # Fully out-of-bounds collapses to a zero-area rect at the page edge -> nothing removed,
    # no crash, original still intact.
    assert region["removed"] is False
    assert result["page_count"] == 2


def test_process_job_reapply_is_idempotent_from_pristine_original(ingested_session):
    # WR-01: a second apply (重新套用) must compute from the PRISTINE original, not the
    # already-redacted work copy. Apply region A, then apply a DIFFERENT region B; B's result
    # must contain region A's content again (because the work copy was reset), and B must be
    # truly removed. Region A is the line band; region B is the text near (40,60).
    sid = ingested_session.session_id

    region_a_px = [v * _SCALE for v in (5.0, 95.0, 195.0, 115.0)]  # the line at y=100
    region_b_px = [v * _SCALE for v in (30.0, 45.0, 120.0, 75.0)]  # the "Page 1" text

    # First apply: remove the line.
    r1 = pipeline.process_job(sid, JobSpec(dpi=_DPI, regions=[RegionMark(page=0, px_rect=region_a_px)]))
    assert r1["regions"][0]["removed"] is True

    # Second apply with ONLY region B. If the work copy were NOT reset, region A (the line)
    # would already be gone; we assert it is BACK (work copy reset to pristine) by checking the
    # exported PDF still has the line, while region B's text is removed.
    r2 = pipeline.process_job(sid, JobSpec(dpi=_DPI, regions=[RegionMark(page=0, px_rect=region_b_px)]))
    assert r2["regions"][0]["removed"] is True

    out = storage.outputs_dir(sid) / r2["output_filename"]
    doc = pdf_engine.open_pdf(out)
    try:
        page = pdf_engine.get_page(doc, 0)
        # Region B (text) removed in this run.
        rect_b = coords.pixels_to_pdf_rect(region_b_px, _DPI, page)
        rt_b = (rect_b.x0, rect_b.y0, rect_b.x1, rect_b.y1)
        assert pdf_engine.get_text_words_in_rect(page, rt_b) == [], "region B text not removed"
        # Region A (the line) is BACK — the second run started from the pristine original, so the
        # first run's removal did not persist into this apply (idempotent re-apply).
        rect_a = coords.pixels_to_pdf_rect(region_a_px, _DPI, page)
        rt_a = (rect_a.x0, rect_a.y0, rect_a.x1, rect_a.y1)
        assert pdf_engine.get_drawings_intersecting(page, rt_a), (
            "re-apply must reset the work copy from the immutable original (WR-01): "
            "region A's line should reappear when only region B is applied"
        )
    finally:
        pdf_engine.close(doc)


def test_process_job_empty_regions_still_exports(ingested_session):
    # An empty regions list is a valid no-op export (all pages kept, original untouched).
    sid = ingested_session.session_id
    before = _sha256(storage.original_path(sid))
    result = pipeline.process_job(sid, JobSpec(dpi=_DPI, regions=[]))
    assert result["page_count"] == 2
    assert (storage.outputs_dir(sid) / result["output_filename"]).is_file()
    assert _sha256(storage.original_path(sid)) == before


def test_process_job_rejects_page_out_of_range(ingested_session):
    sid = ingested_session.session_id
    spec = JobSpec(dpi=_DPI, regions=[RegionMark(page=99, px_rect=list(_REGION_PX))])
    with pytest.raises(pipeline.PipelineError) as exc:
        pipeline.process_job(sid, spec)
    assert exc.value.code == "page_out_of_range"


# --------------------------------------------------------------------------------------
# CR-01 regression: a large-MediaBox page whose effective render DPI < the requested 200.
# The client measures px_rect against the REDUCED-DPI image dims /meta reports; the server
# must re-derive that same effective DPI per page so the region maps to the CORRECT PDF
# rect. Before the fix the server scaled by the requested 200 -> the framed content was NOT
# removed (the rect landed shifted/shrunk), which this test would catch.
# --------------------------------------------------------------------------------------

# An E-size-class CAD sheet: large enough that 200 DPI exceeds MAX_RENDER_PIXELS (40 MP),
# forcing fit_dpi_to_pixel_budget to scale the effective DPI below 200.
_BIG_W_PT = 2600.0
_BIG_H_PT = 3400.0
# Where the supplier mark sits in UNROTATED page points (top-left origin) — comfortably
# inside the page, away from edges so padding/clamping never interferes.
_BIG_MARK_PT = (400.0, 500.0, 1200.0, 900.0)


def _ingest_big_page(filename: str = "bigcad.pdf"):
    """Ingest a single large-MediaBox page carrying text + a line inside _BIG_MARK_PT."""
    import fitz  # test harness may import fitz directly to BUILD fixtures

    from app.services import ingest

    doc = fitz.open()
    try:
        page = doc.new_page(width=_BIG_W_PT, height=_BIG_H_PT)
        # Content placed firmly inside the framed mark rect.
        page.insert_text((450, 560), "SUPPLIER MARK")
        page.draw_line(fitz.Point(420, 700), fitz.Point(1180, 700))
        pdf_bytes = doc.tobytes()
    finally:
        doc.close()
    return ingest.ingest_upload(filename, pdf_bytes)


def test_process_job_uses_effective_dpi_on_reduced_dpi_page(monkeypatch):
    # Force the effective DPI strictly below the requested 200 for this page.
    from app import config as cfg
    from app.services import render

    sess = _ingest_big_page()
    sid = sess.session_id

    # The page must actually trip the pixel budget, else the test proves nothing.
    effective = render.fit_dpi_to_pixel_budget(_DPI, _BIG_W_PT, _BIG_H_PT)
    assert effective < _DPI, (
        f"fixture not large enough: effective_dpi {effective} not < {_DPI} "
        f"(MAX_RENDER_PIXELS={cfg.MAX_RENDER_PIXELS})"
    )

    # The client reads /meta (effective DPI + reduced dims) and measures px_rect against
    # THOSE dims. Reproduce that: px = pt * effective_dpi / 72.
    eff_scale = effective / 72.0
    px_rect = [v * eff_scale for v in _BIG_MARK_PT]

    # The JobSpec carries the REQUESTED dpi (200) — exactly the value a client that measures
    # at the reduced DPI but posts the request ceiling would send. The server must re-derive
    # the effective DPI per page and map correctly regardless.
    spec = JobSpec(dpi=_DPI, regions=[RegionMark(page=0, px_rect=px_rect)])
    result = pipeline.process_job(sid, spec)
    assert result["regions"][0]["removed"] is True, (
        "framed content must be removed when the server uses the effective per-page DPI"
    )

    # Prove the framed content is gone in the EXPORTED PDF, mapping the same px_rect at the
    # effective DPI (the contract the client/server now share).
    out = storage.outputs_dir(sid) / result["output_filename"]
    doc = pdf_engine.open_pdf(out)
    try:
        page = pdf_engine.get_page(doc, 0)
        rect = coords.pixels_to_pdf_rect(px_rect, effective, page)
        rt = (rect.x0, rect.y0, rect.x1, rect.y1)
        assert pdf_engine.get_text_words_in_rect(page, rt) == [], "text survived"
        assert pdf_engine.get_drawings_intersecting(page, rt) == [], "vector survived"
    finally:
        pdf_engine.close(doc)


def test_process_job_wrong_dpi_maps_to_wrong_rect_proving_cr01(monkeypatch):
    # Lock the failure mode: if the server had used the REQUESTED 200 (the old behaviour),
    # the px_rect the client measured at the effective DPI maps to a SHIFTED/SHRUNK PDF rect.
    # Because effective < 200, the wrong scale (72/200) shrinks the rect toward the origin, so
    # it neither matches the correctly-mapped rect nor fully covers what the user framed. This
    # proves the two mappings genuinely diverge on this page, so the fix is load-bearing.
    from app.services import render

    sess = _ingest_big_page()
    sid = sess.session_id
    effective = render.fit_dpi_to_pixel_budget(_DPI, _BIG_W_PT, _BIG_H_PT)
    eff_scale = effective / 72.0
    px_rect = [v * eff_scale for v in _BIG_MARK_PT]

    work = storage.work_path(sid)
    doc = pdf_engine.open_pdf(work)
    try:
        page = pdf_engine.get_page(doc, 0)
        correct = coords.pixels_to_pdf_rect(px_rect, effective, page)
        wrong = coords.pixels_to_pdf_rect(px_rect, _DPI, page)

        # The correct mapping reproduces the framed mark rect (within a sub-pt rounding tol).
        for got, exp in zip((correct.x0, correct.y0, correct.x1, correct.y1), _BIG_MARK_PT):
            assert abs(got - exp) < 1.0, f"correct mapping off: {got} vs {exp}"

        # The wrong mapping is materially different — every edge is pulled toward the origin
        # by the ratio (effective/200), a >> 1pt error on a sheet this large.
        ratio = effective / _DPI
        for w_edge, exp in zip((wrong.x0, wrong.y0, wrong.x1, wrong.y1), _BIG_MARK_PT):
            assert abs(w_edge - exp) > 10.0, (
                f"wrong mapping unexpectedly close to correct: {w_edge} vs {exp}"
            )
            assert abs(w_edge - exp * ratio) < 1.0, "wrong rect = framed rect * (eff/200)"

        # Concretely: the wrong rect fails to fully cover the framed mark — its bottom/right
        # edges fall short of the mark's extent, so it would leave residual or clear the wrong
        # area. (correct.x1 covers the mark to 1200pt; wrong.x1 stops near 1200*ratio.)
        assert wrong.x1 < correct.x1 - 10.0
        assert wrong.y1 < correct.y1 - 10.0
    finally:
        pdf_engine.close(doc)


# --------------------------------------------------------------------------------------
# Structural acceptance: forbidden constant absent, fitz confined to the seam
# --------------------------------------------------------------------------------------


def _app_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(redact.__file__)))


def test_redact_py_never_uses_text_none():
    src = Path(redact.__file__).read_text(encoding="utf-8")
    assert "PDF_REDACT_TEXT_NONE" not in src, (
        "PDF_REDACT_TEXT_NONE must NEVER appear in redact.py (it keeps text — Pitfall 3)"
    )


def test_fitz_import_confined_to_engine_seam():
    # Statement-level (AST) check, mirroring the 02-01 purity test: only pdf_engine.py may
    # `import fitz`. redact.py and pipeline.py must be fitz-free.
    app_dir = _app_dir()
    offenders = []
    for path in glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True):
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=path)
        imports_fitz = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name == "fitz" or alias.name.startswith("fitz.") for alias in node.names):
                    imports_fitz = True
            elif isinstance(node, ast.ImportFrom):
                if node.module == "fitz" or (node.module or "").startswith("fitz."):
                    imports_fitz = True
        if imports_fitz:
            offenders.append(os.path.basename(path))
    assert offenders == ["pdf_engine.py"], f"fitz imported outside the seam: {offenders}"


# --------------------------------------------------------------------------------------
# Phase 4-02 Task 01: IMAGE_PIXELS constant + rect_overlaps_image helper
# --------------------------------------------------------------------------------------


def test_image_pixels_constant_exported():
    """IMAGE_PIXELS is re-exported by pdf_engine so callers stay fitz-free (Phase 4 D-08)."""
    import fitz

    assert pdf_engine.IMAGE_PIXELS == fitz.PDF_REDACT_IMAGE_PIXELS == 2


def test_line_art_remove_if_touched_constant_exported():
    """Hotfix #05 investigation: PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED is re-exported so
    callers/tests can name it without importing fitz (AGPL seam, T-02-03).

    NOT currently used by the pipeline — the dCt-residue investigation empirically verified
    that TOUCHED does not remove zero-area drawings either, so switching the vector branch
    to TOUCHED does NOT fix the dCt-residue failure mode. The constant is shipped as
    infrastructure for the eventual real fix.
    """
    import fitz

    assert pdf_engine.LINE_ART_REMOVE_IF_TOUCHED == fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED == 2


def test_rect_overlaps_image_positive(image_only_pdf_bytes):
    """A rect landing inside the embedded image area returns True (Pattern 4)."""
    import fitz

    doc = pdf_engine.open_pdf(image_only_pdf_bytes)
    try:
        page = pdf_engine.get_page(doc, 0)
        # The image is keep_proportion'd into A4 (595x842) from 800x600 ratio
        # — letterboxed up/down; centre rect lands firmly inside the image XObject.
        center_rect = fitz.Rect(200, 300, 400, 500)
        assert pdf_engine.rect_overlaps_image(page, center_rect) is True
    finally:
        pdf_engine.close(doc)


def test_rect_overlaps_image_negative_vector_pdf(valid_pdf_bytes):
    """A vector-only PDF has no image XObjects, so the probe always returns False."""
    import fitz

    doc = pdf_engine.open_pdf(valid_pdf_bytes)
    try:
        page = pdf_engine.get_page(doc, 0)
        any_rect = fitz.Rect(10, 10, 100, 100)
        assert pdf_engine.rect_overlaps_image(page, any_rect) is False
    finally:
        pdf_engine.close(doc)


def test_rect_overlaps_image_mixed_dispatch(mixed_vector_raster_pdf_bytes):
    """Mixed PDF: upper-half rect overlaps the image (True), lower-half rect does not (False)."""
    import fitz

    doc = pdf_engine.open_pdf(mixed_vector_raster_pdf_bytes)
    try:
        page = pdf_engine.get_page(doc, 0)
        upper_rect = fitz.Rect(50, 50, 350, 250)  # in raster region
        lower_rect = fitz.Rect(30, 350, 380, 550)  # in vector region
        assert pdf_engine.rect_overlaps_image(page, upper_rect) is True
        assert pdf_engine.rect_overlaps_image(page, lower_rect) is False
    finally:
        pdf_engine.close(doc)


# --------------------------------------------------------------------------------------
# Phase 4-02 Task 02: remove_region_raster — true raster removal + dual-layer OCR
# --------------------------------------------------------------------------------------


def test_raster_full_page_blank_to_white(image_only_pdf_bytes, tmp_path):
    """Full-page frame on image-only PDF: IMAGE_PIXELS auto-removes the image xref AND
    the rendered centre pixel reads white (RESEARCH verified D-08)."""
    import fitz

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(image_only_pdf_bytes)
    doc = pdf_engine.open_pdf(pdf_path)
    try:
        page = pdf_engine.get_page(doc, 0)
        full_rect = fitz.Rect(0, 0, 595.0, 842.0)
        removed = redact.remove_region_raster(page, full_rect)
        assert removed is True
        # Full-page overlap auto-removes the image xref (RESEARCH verified).
        assert page.get_images() == [], (
            f"image xref should be auto-removed on full-frame; got {page.get_images()}"
        )
        # Centre pixel renders white.
        pix = page.get_pixmap(dpi=72)
        center_x, center_y = pix.width // 2, pix.height // 2
        pixel = pix.pixel(center_x, center_y)
        assert all(c >= 250 for c in pixel[:3]), f"expected white, got {pixel}"
    finally:
        pdf_engine.close(doc)


def test_raster_partial_redact_inside_white_outside_keep(image_only_pdf_bytes, tmp_path):
    """Partial frame: inside-rect pixels turn white; outside-rect (still in image area)
    pixels keep the original colour. The conftest PNG is (200, 100, 50) orange so
    'not white' is easy to assert."""
    import fitz

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(image_only_pdf_bytes)
    doc = pdf_engine.open_pdf(pdf_path)
    try:
        page = pdf_engine.get_page(doc, 0)
        # The image is letterboxed inside A4: 800x600 keep-proportion'd into 595x842
        # → image area ≈ y∈[197.875, 644.125]. Frame a 200x200 box well inside it.
        inside_rect = fitz.Rect(200, 280, 400, 480)
        removed = redact.remove_region_raster(page, inside_rect)
        assert removed is True
        pix = page.get_pixmap(dpi=72)
        # dpi=72 → 1pt == 1px
        cx, cy = int((200 + 400) / 2), int((280 + 480) / 2)
        inside_px = pix.pixel(cx, cy)
        assert all(c >= 250 for c in inside_px[:3]), f"inside not white: {inside_px}"
        # Pick a point still inside the image letterbox but outside the redact rect.
        # Image y-band ~[198,644]; redact rect y∈[280,480]; take (100,550) — left of redact,
        # below redact rect, inside image band.
        ox, oy = 100, 550
        outside_px = pix.pixel(ox, oy)
        assert not all(c >= 250 for c in outside_px[:3]), (
            f"outside-redact pixel unexpectedly white (image not preserved): {outside_px}"
        )
    finally:
        pdf_engine.close(doc)


def test_raster_dual_layer_ocr_text_residual_empty(dual_layer_ocr_pdf_bytes, tmp_path):
    """Dual-layer OCR PDF: a single apply_redactions call clears BOTH the image pixels
    AND the OCR text layer in the frame (Pitfall 3 / Pitfall E closed)."""
    import fitz

    pdf_path = tmp_path / "ocr.pdf"
    pdf_path.write_bytes(dual_layer_ocr_pdf_bytes)
    doc = pdf_engine.open_pdf(pdf_path)
    try:
        page = pdf_engine.get_page(doc, 0)
        # The fixture inserts "SUPPLIER" at (100,400) and "WORDMARK" at (200,400) but the
        # PDF text origin is the BASELINE, so the rendered glyph bboxes sit ABOVE y=400.
        # PyMuPDF default insert_text fontsize is 11pt — frame a band ~y∈[388, 410]
        # to safely include both word boxes.
        text_rect = fitz.Rect(50, 388, 400, 412)
        rt = (text_rect.x0, text_rect.y0, text_rect.x1, text_rect.y1)
        # Pre: both layers exist in the framed region.
        assert pdf_engine.get_text_words_in_rect(page, rt), (
            "fixture invariant: OCR words must exist inside the framed rect"
        )
        assert pdf_engine.rect_overlaps_image(page, text_rect), (
            "fixture invariant: raster image must overlap the framed rect"
        )
        removed = redact.remove_region_raster(page, text_rect)
        assert removed is True
        # Dual-layer leak closed: no text words remain (the OCR layer is gone).
        residual = pdf_engine.get_text_words_in_rect(page, rt)
        assert residual == [], f"dual-layer OCR text leak: {residual}"
    finally:
        pdf_engine.close(doc)


def test_raster_fill_none_no_drawing_residual(image_only_pdf_bytes, tmp_path):
    """Pitfall A defence: raster branch passes fill=None so no type='fs' rect==redact_rect
    drawing survives the apply (which would defeat get_drawings_fully_inside)."""
    import fitz

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(image_only_pdf_bytes)
    doc = pdf_engine.open_pdf(pdf_path)
    try:
        page = pdf_engine.get_page(doc, 0)
        rect = fitz.Rect(100, 200, 300, 400)
        redact.remove_region_raster(page, rect)
        # Walk every drawing; refuse the survivor signature
        # (type='fs', fill≈(1,1,1), rect overlapping the redact rect).
        for d in page.get_drawings():
            d_rect = d.get("rect")
            if d_rect is None:
                continue
            if d.get("type") == "fs" and d.get("fill") == (1.0, 1.0, 1.0):
                overlap = (
                    rect.x0 <= d_rect.x1 and d_rect.x0 <= rect.x1
                    and rect.y0 <= d_rect.y1 and d_rect.y0 <= rect.y1
                )
                assert not overlap, (
                    f"raster fill=None should NOT leave an fs-fill survivor inside the rect, got {d}"
                )
    finally:
        pdf_engine.close(doc)


def test_raster_empty_rect_no_op(image_only_pdf_bytes, tmp_path):
    """Degenerate rect returns False without raising (mirrors vector branch _is_empty)."""
    import fitz

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(image_only_pdf_bytes)
    doc = pdf_engine.open_pdf(pdf_path)
    try:
        page = pdf_engine.get_page(doc, 0)
        empty_rect = fitz.Rect(100, 100, 100, 100)
        assert redact.remove_region_raster(page, empty_rect) is False
    finally:
        pdf_engine.close(doc)
