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
