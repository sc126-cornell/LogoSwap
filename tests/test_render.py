"""Render service tests: PNG output, DPI-derived scale, default + clamp behavior."""

from __future__ import annotations

import pytest

from app import config, storage
from app.services import render
from app.services.render import RenderError


def test_render_page_returns_png_and_metadata(ingested_session):
    work = storage.work_path(ingested_session.session_id)
    result = render.render_page(work, page_no=0, dpi=200)

    assert result.png[:4] == b"\x89PNG"
    assert result.img_w > 0 and result.img_h > 0
    assert result.page_w_pt > 0 and result.page_h_pt > 0
    assert result.rotation in {0, 90, 180, 270}
    assert result.dpi == 200


def test_render_scale_is_derived_from_dpi(ingested_session):
    work = storage.work_path(ingested_session.session_id)
    result = render.render_page(work, page_no=0, dpi=200)

    expected = result.page_w_pt * 200 / 72
    assert abs(result.img_w - expected) <= 2


def test_render_default_dpi_is_200(ingested_session):
    work = storage.work_path(ingested_session.session_id)
    result = render.render_page(work, page_no=0)  # no explicit dpi
    assert result.dpi == config.DEFAULT_DPI == 200


def test_render_dpi_clamped_to_bounds(ingested_session):
    work = storage.work_path(ingested_session.session_id)

    high = render.render_page(work, page_no=0, dpi=10_000)
    assert high.dpi == config.MAX_DPI

    low = render.render_page(work, page_no=0, dpi=1)
    assert low.dpi == config.MIN_DPI


def test_render_out_of_range_page_raises(ingested_session):
    work = storage.work_path(ingested_session.session_id)
    with pytest.raises(RenderError) as exc:
        render.render_page(work, page_no=999, dpi=200)
    assert exc.value.code == "page_not_found"


def test_page_meta_matches_render(ingested_session):
    work = storage.work_path(ingested_session.session_id)
    meta = render.page_meta(work, page_no=0)
    rendered = render.render_page(work, page_no=0)

    assert meta["dpi"] == 200
    assert meta["rotation"] == rendered.rotation
    # Pixel dims derived from DPI should match the actual render within rounding.
    assert abs(meta["img_w"] - rendered.img_w) <= 2
    assert abs(meta["img_h"] - rendered.img_h) <= 2


# ---- WR-06: per-render pixel-budget ceiling (oversized single page) ---------------------


def test_fit_dpi_to_pixel_budget_passes_normal_page():
    # A normal page at its DPI is well under budget — DPI unchanged.
    assert render.fit_dpi_to_pixel_budget(200, 200.0, 300.0) == 200


def test_fit_dpi_to_pixel_budget_scales_down_oversized_page(monkeypatch):
    # A huge MediaBox would project far over the budget; DPI must scale down so the
    # resulting pixel count fits, and pixels grow with DPI² so the fit uses sqrt.
    monkeypatch.setattr(config, "MAX_RENDER_PIXELS", 40 * 1_000_000)
    big_pt = 20_000.0  # 20000 x 20000 pt page
    fitted = render.fit_dpi_to_pixel_budget(config.MAX_DPI, big_pt, big_pt)
    assert fitted < config.MAX_DPI
    scale = fitted / 72.0
    assert round(big_pt * scale) * round(big_pt * scale) <= config.MAX_RENDER_PIXELS


def _build_oversized_pdf(width_pt: float, height_pt: float) -> bytes:
    import fitz  # test harness may build fixtures with fitz directly

    doc = fitz.open()
    try:
        page = doc.new_page(width=width_pt, height=height_pt)
        page.insert_text((40, 60), "huge page")
        return doc.tobytes()
    finally:
        doc.close()


def test_render_oversized_page_stays_within_pixel_budget(monkeypatch):
    # End-to-end: rendering a pathologically large page must reduce the effective DPI
    # (WR-06) and produce a pixmap whose pixel count is within the budget.
    from app.services import ingest

    monkeypatch.setattr(config, "MAX_RENDER_PIXELS", 8 * 1_000_000)  # tighten so it triggers
    pdf = _build_oversized_pdf(8_000.0, 8_000.0)
    info = ingest.ingest_upload("huge.pdf", pdf)
    work = storage.work_path(info.session_id)

    result = render.render_page(work, page_no=0, dpi=config.MAX_DPI)
    assert result.dpi < config.MAX_DPI  # scaled down to fit the budget
    assert result.img_w * result.img_h <= config.MAX_RENDER_PIXELS
    assert result.png[:4] == b"\x89PNG"

    # meta must report the SAME reduced dpi and matching pixel dims as the render (D-03).
    meta = render.page_meta(work, page_no=0, dpi=config.MAX_DPI)
    assert meta["dpi"] == result.dpi
    assert abs(meta["img_w"] - result.img_w) <= 2
    assert abs(meta["img_h"] - result.img_h) <= 2
