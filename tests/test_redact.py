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

        removed = redact.remove_region(page, rect)
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
        redact.remove_region(page, rect)
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
        assert redact.remove_region(page, rect) is False
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
        assert redact.remove_region(page, rect) is True
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
