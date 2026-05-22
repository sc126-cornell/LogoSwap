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
