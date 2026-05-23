"""LOGO-01 tests: fixed logo-library listing + the logo_id path-traversal defense.

Mirrors the TestClient + structured-4xx assertion style of test_process_api.py and the
in-memory fixture philosophy of conftest.py (no committed binaries — the logo PNG is built
in-memory by the ``logo_png_bytes`` fixture, the library by ``logo_library``).

The load-bearing security property (T-03-01): an untrusted ``logo_id`` is ONLY ever a manifest
dict key — never a path segment — so ``../`` or an unknown id yields a structured 404
``logo_not_found`` and never reads outside LOGOS_DIR, never a 500.
"""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from app import config, storage
from app.models import JobSpec
from app.services import coords, logo, pdf_engine, pipeline

# Conftest page is 200x300pt; the same region constant as test_redact.py / test_process_api.py.
# A logo placed into the pdf_rect derived from this region must land centered + aspect-preserved.
_REGION_PT = (10.0, 40.0, 190.0, 120.0)
# Geometry tolerances: 1pt for containment (rounding) and aspect within a small ratio epsilon.
TOL = 1.0
ASPECT_TOL = 0.05


def _ingest(valid_pdf_bytes):
    """Ingest the standard 2-page vector PDF and return its session id."""
    from app.services import ingest

    return ingest.ingest_upload("design.pdf", valid_pdf_bytes).session_id


def _px_rect(page_no, dpi, page):
    """Image-pixel rect for _REGION_PT at the page's effective render dpi."""
    from app.services import render

    dims = pdf_engine.page_dimensions(page.parent, page_no)
    eff = render.fit_dpi_to_pixel_budget(render.clamp_dpi(dpi), dims["page_w_pt"], dims["page_h_pt"])
    scale = eff / 72.0
    return [v * scale for v in _REGION_PT], eff


def _job_px_rect(dpi):
    """Compute the image-pixel rect for _REGION_PT at the requested dpi (page geometry fixed)."""
    scale = dpi / 72.0
    return [v * scale for v in _REGION_PT]


def test_inserted_logo_bbox_within_rect_and_aspect_preserved(
    valid_pdf_bytes, logo_library, logo_png_bytes
):
    """LOGO-02 / D-02: the placed logo bbox is contained in the target rect, aspect ~= source."""
    from PIL import Image
    from io import BytesIO

    sid = _ingest(valid_pdf_bytes)
    dpi = 200
    px_rect = _job_px_rect(dpi)
    spec = JobSpec(dpi=dpi, regions=[{"page": 0, "px_rect": px_rect}], logo_id="placeholder")
    pipeline.process_job(sid, spec)

    src = Image.open(BytesIO(logo_png_bytes))
    source_aspect = src.width / src.height

    out = pipeline.output_path(sid).read_bytes()
    doc = pdf_engine.open_pdf(out)
    try:
        page = pdf_engine.get_page(doc, 0)
        target = coords.pixels_to_pdf_rect(px_rect, dpi, page)
        images = page.get_images()
        assert images, "logo image must be embedded in the exported PDF"
        xref = images[0][0]
        placed = pdf_engine.get_image_rects(page, xref)
        assert placed, "the embedded logo must have at least one placed rect"
        for r in placed:
            assert target.x0 - TOL <= r.x0 and r.y0 >= target.y0 - TOL
            assert r.x1 <= target.x1 + TOL and r.y1 <= target.y1 + TOL
            assert abs((r.width / r.height) - source_aspect) < ASPECT_TOL
    finally:
        pdf_engine.close(doc)


def test_logo_survives_redaction(valid_pdf_bytes, logo_library):
    """Pitfall 1: logo inserted AFTER apply_redactions survives; text/vector stay removed."""
    sid = _ingest(valid_pdf_bytes)
    dpi = 200
    px_rect = _job_px_rect(dpi)
    spec = JobSpec(dpi=dpi, regions=[{"page": 0, "px_rect": px_rect}], logo_id="placeholder")
    pipeline.process_job(sid, spec)

    out = pipeline.output_path(sid).read_bytes()
    doc = pdf_engine.open_pdf(out)
    try:
        page = pdf_engine.get_page(doc, 0)
        target = coords.pixels_to_pdf_rect(px_rect, dpi, page)
        rt = (target.x0, target.y0, target.x1, target.y1)
        # Truly removed: no extractable text words inside the user rect (REMOVE-01).
        assert pdf_engine.get_text_words_in_rect(page, rt) == []
        # Logo present: the embedded image survived the apply pass.
        assert page.get_images(), "logo image must survive apply_redactions"
    finally:
        pdf_engine.close(doc)


def test_global_logo_single_xref(valid_pdf_bytes, logo_library):
    """D-01 / Pitfall 4: one global logo across N>=2 regions embeds ONE shared xref."""
    sid = _ingest(valid_pdf_bytes)
    dpi = 200
    px_rect = _job_px_rect(dpi)
    # Two regions across two pages -> the same logo must be embedded only once.
    spec = JobSpec(
        dpi=dpi,
        regions=[
            {"page": 0, "px_rect": px_rect},
            {"page": 1, "px_rect": px_rect},
        ],
        logo_id="placeholder",
    )
    pipeline.process_job(sid, spec)

    out = pipeline.output_path(sid).read_bytes()
    doc = pdf_engine.open_pdf(out)
    try:
        # Collect distinct image xrefs across all pages — the one global logo must dedup to 1.
        xrefs = set()
        for page_no in range(pdf_engine.page_count(doc)):
            page = pdf_engine.get_page(doc, page_no)
            for img in page.get_images():
                xrefs.add(img[0])
        assert len(xrefs) == 1, f"expected one shared logo xref, got {xrefs}"
    finally:
        pdf_engine.close(doc)


def test_list_logos(client, logo_library):
    """GET /logos returns 200 {logos:[...]} with id+name and NO filesystem path leaked."""
    resp = client.get("/logos")
    assert resp.status_code == 200
    body = resp.json()
    assert "logos" in body
    logos = body["logos"]
    assert len(logos) == 1
    entry = logos[0]
    assert entry["id"] == "placeholder"
    assert entry["name"] == "預設商標"
    # No filesystem path / raw file key leaked to the client.
    assert "file" not in entry
    for value in entry.values():
        assert "placeholder.png" != value
        assert "/" not in str(value) and "\\" not in str(value)


def test_list_logos_empty_library_is_not_500(client, tmp_path, monkeypatch):
    """An absent/empty LOGOS_DIR yields 200 {logos: []} (picker empty-state, A2), not a 500."""
    from app import config

    empty_dir = tmp_path / "no-logos-here"  # does not exist
    monkeypatch.setattr(config, "LOGOS_DIR", empty_dir)
    resp = client.get("/logos")
    assert resp.status_code == 200
    assert resp.json() == {"logos": []}


def test_logo_image_happy(client, logo_library):
    """GET /logos/{valid_id}/image returns 200 image/png whose bytes start with the PNG signature."""
    resp = client.get("/logos/placeholder/image")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_logo_id_path_traversal_rejected(client, logo_library):
    """Crafted ids never read outside LOGOS_DIR and never 500 (T-03-01).

    Two crafted shapes are covered:
      - A %2F-encoded multi-segment id (``../../app/config.py``) cannot match the single
        ``{logo_id}`` path segment, so the router returns a plain 404 BEFORE any handler runs
        — it never reaches a path build. (Still a 404, never a 500.)
      - A single-segment crafted id that reaches ``resolve`` (encoded ``%2e%2e`` dot-segment,
        and an unknown id) maps to a structured 404 ``logo_not_found`` (no oracle), because the
        id is only ever a manifest dict key — never joined to LOGOS_DIR.

    Other forms (``../../...`` with %2F-encoded separators, or a bare ``..`` that the URL layer
    normalizes away) are 404'd by routing/normalization before any handler runs — still safe
    (never a path build, never a 500), just without the structured code.
    """
    crafted = quote("../../app/config.py", safe="")
    resp = client.get(f"/logos/{crafted}/image")
    assert resp.status_code == 404
    assert resp.status_code != 500

    # These reach the handler and must be a structured logo_not_found (no oracle).
    for bad_id in ("%2e%2e", "does-not-exist"):
        r = client.get(f"/logos/{bad_id}/image")
        assert r.status_code == 404, bad_id
        assert r.status_code != 500, bad_id
        assert r.json()["detail"]["code"] == "logo_not_found", bad_id


def test_corrupt_logo_degrades_to_pure_removal(valid_pdf_bytes, logo_library):
    """WR-02: a logo that fails to resolve at process time degrades to pure removal, not abort.

    The picker only surfaces ids that passed list-time validation, but the asset can be
    corrupted/replaced on disk between list and process. The redaction + export must still
    complete (D-04 / A2 philosophy) and the result reports logo_skipped=True so the frontend
    can notify the user the logo was not placed — WITHOUT losing the run.
    """
    sid = _ingest(valid_pdf_bytes)
    dpi = 200
    px_rect = _job_px_rect(dpi)
    # Corrupt the asset on disk AFTER it was (notionally) listed as valid.
    (logo_library / "placeholder.png").write_bytes(b"not a real png")

    spec = JobSpec(dpi=dpi, regions=[{"page": 0, "px_rect": px_rect}], logo_id="placeholder")
    result = pipeline.process_job(sid, spec)

    # The job completed (pure removal) and flagged the skipped logo.
    assert result["logo_skipped"] is True
    out = pipeline.output_path(sid)
    assert out.is_file(), "redaction + export must still produce the output PDF"

    doc = pdf_engine.open_pdf(out.read_bytes())
    try:
        page = pdf_engine.get_page(doc, 0)
        target = coords.pixels_to_pdf_rect(px_rect, dpi, page)
        rt = (target.x0, target.y0, target.x1, target.y1)
        # True removal still happened; no logo embedded (pure removal).
        assert pdf_engine.get_text_words_in_rect(page, rt) == []
        assert page.get_images() == [], "no logo placed when the asset could not be resolved"
    finally:
        pdf_engine.close(doc)


def test_logo_skipped_false_on_clean_placement(valid_pdf_bytes, logo_library):
    """WR-02: a successful placement reports logo_skipped=False (and a no-logo job too)."""
    sid = _ingest(valid_pdf_bytes)
    px_rect = _job_px_rect(200)
    spec = JobSpec(dpi=200, regions=[{"page": 0, "px_rect": px_rect}], logo_id="placeholder")
    assert pipeline.process_job(sid, spec)["logo_skipped"] is False

    sid2 = _ingest(valid_pdf_bytes)
    spec2 = JobSpec(dpi=200, regions=[{"page": 0, "px_rect": px_rect}])
    assert pipeline.process_job(sid2, spec2)["logo_skipped"] is False


def test_non_png_asset_rejected(client, logo_library):
    """WR-04: a Pillow-decodable non-PNG (JPEG) is rejected as logo_invalid, not served as PNG.

    The endpoint hardcodes media_type=image/png and place_logo embeds the bytes as PNG, so
    validation must enforce PNG (D-03) rather than accepting any decodable format. A JPEG that
    decodes fine must NOT pass: it is skipped from list_logos and a direct /image fetch is 422.
    """
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (40, 20), (0, 128, 0)).save(buf, format="JPEG")
    (logo_library / "shot.jpg").write_bytes(buf.getvalue())
    manifest = [
        {"id": "placeholder", "file": "placeholder.png", "name": "預設商標", "tags": []},
        {"id": "jpeg", "file": "shot.jpg", "name": "JPEG", "tags": []},
    ]
    (logo_library / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Skipped from the catalog: only the genuine PNG survives.
    ids = [e["id"] for e in client.get("/logos").json()["logos"]]
    assert ids == ["placeholder"]

    # Direct resolve of the non-PNG id is a structured 422 logo_invalid (not served as PNG).
    r = client.get("/logos/jpeg/image")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "logo_invalid"


def test_bad_asset_skipped_from_list(client, logo_library, logo_png_bytes):
    """A manifest entry whose file is missing/corrupt is SKIPPED from list_logos, not fatal."""
    # Append a second entry pointing at a missing file + a corrupt file.
    (logo_library / "broken.png").write_bytes(b"not a real png")
    manifest = [
        {"id": "placeholder", "file": "placeholder.png", "name": "預設商標", "tags": []},
        {"id": "missing", "file": "absent.png", "name": "缺檔", "tags": []},
        {"id": "broken", "file": "broken.png", "name": "壞檔", "tags": []},
    ]
    (logo_library / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    resp = client.get("/logos")
    assert resp.status_code == 200
    ids = [e["id"] for e in resp.json()["logos"]]
    assert ids == ["placeholder"]  # bad entries skipped, good one survives


# ---- Auto-selection by region shape (auto_logo) ------------------------------------
def _make_png(w: int, h: int, color=(0, 0, 255, 255)) -> bytes:
    """Build an in-memory RGBA PNG of a given size (no committed binary)."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGBA", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def two_logo_library(tmp_path, monkeypatch):
    """A library with a WIDE (10:1) and a BLOCK (2:1) logo for auto-selection tests."""
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    (logos_dir / "wide.png").write_bytes(_make_png(1000, 100))   # native aspect 10.0
    (logos_dir / "block.png").write_bytes(_make_png(200, 100))   # native aspect 2.0
    manifest = [
        {"id": "wide", "file": "wide.png", "name": "寬", "tags": []},
        {"id": "block", "file": "block.png", "name": "方", "tags": []},
    ]
    (logos_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(config, "LOGOS_DIR", logos_dir)
    return logos_dir


def test_pick_logo_id_for_rect_by_aspect(two_logo_library):
    """A very wide region picks the wide logo; a square-ish region picks the block logo."""
    assert logo.pick_logo_id_for_rect(800, 100) == "wide"   # 8:1 closest to 10:1
    assert logo.pick_logo_id_for_rect(150, 100) == "block"  # 1.5:1 closest to 2:1
    assert logo.pick_logo_id_for_rect(0, 100) is None        # degenerate -> None


def test_pick_logo_id_for_rect_empty_library(tmp_path, monkeypatch):
    """No library -> None (auto degrades to pure removal, WR-02 / D-04)."""
    monkeypatch.setattr(config, "LOGOS_DIR", tmp_path / "does-not-exist")
    assert logo.pick_logo_id_for_rect(800, 100) is None


def test_auto_logo_picks_per_region_by_shape(valid_pdf_bytes, two_logo_library):
    """auto_logo=True embeds the wide logo in a wide region and the block logo in a block region."""
    sid = _ingest(valid_pdf_bytes)
    dpi = 200
    s = dpi / 72.0
    wide_px = [v * s for v in (10.0, 20.0, 190.0, 40.0)]    # 180x20 = 9:1 framed box
    block_px = [v * s for v in (10.0, 60.0, 170.0, 140.0)]  # 160x80 = 2:1 framed box
    spec = JobSpec(
        dpi=dpi,
        auto_logo=True,
        regions=[
            {"page": 0, "px_rect": wide_px},
            {"page": 0, "px_rect": block_px},
        ],
    )
    result = pipeline.process_job(sid, spec)
    assert result["logo_skipped"] is False

    out = pipeline.output_path(sid).read_bytes()
    doc = pdf_engine.open_pdf(out)
    try:
        page = pdf_engine.get_page(doc, 0)
        images = page.get_images()
        assert len(images) == 2, f"expected two distinct logos embedded, got {len(images)}"
        aspects = [
            r.width / r.height
            for img in images
            for r in pdf_engine.get_image_rects(page, img[0])
        ]
        # Placed-logo aspect == native logo aspect (keep_proportion): ~10:1 and ~2:1.
        assert any(a > 5 for a in aspects), f"expected a wide placement, got {aspects}"
        assert any(1.5 < a < 3 for a in aspects), f"expected a block placement, got {aspects}"
    finally:
        pdf_engine.close(doc)


def _red_top_blue_bottom_png(w: int = 80, h: int = 160) -> bytes:
    """An unambiguously oriented logo: top half RED, bottom half BLUE."""
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (255, 0, 0, 255) if y < h // 2 else (0, 0, 255, 255)
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_place_logo_is_upright_in_displayed_rotated_page(rot):
    """The placed logo stays UPRIGHT in the displayed (baked /Rotate) page for every rotation.

    Regression for the UAT finding: without rotation compensation the logo rotated WITH the page
    and landed sideways. place_logo rotates the image by page.rotation so it reads upright in the
    orientation the user framed on. We render the page (which applies /Rotate) and assert the
    red half sits ABOVE the blue half with a dominant vertical split.
    """
    import fitz
    from PIL import Image

    doc = fitz.open()
    page = doc.new_page(width=300, height=200)  # landscape, intrinsic /Rotate = 0
    pdf_engine.set_page_rotation(page, rot)
    pdf_engine.place_logo(page, fitz.Rect(60, 40, 240, 160), stream=_red_top_blue_bottom_png())
    pix = page.get_pixmap(dpi=100)  # applies /Rotate -> displayed orientation
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    load = img.load()
    reds, blues = [], []
    for y in range(0, img.height, 2):
        for x in range(0, img.width, 2):
            r, g, b = load[x, y]
            if r > 150 and g < 100 and b < 100:
                reds.append((x, y))
            elif b > 150 and r < 100 and g < 100:
                blues.append((x, y))
    assert reds and blues, "logo colors must be present in the rendered output"
    rx = sum(p[0] for p in reds) / len(reds)
    ry = sum(p[1] for p in reds) / len(reds)
    bx = sum(p[0] for p in blues) / len(blues)
    by = sum(p[1] for p in blues) / len(blues)
    # Upright: red centroid is ABOVE blue (smaller y) and the split is vertical, not sideways.
    assert (by - ry) > abs(bx - rx), f"logo not upright at /Rotate={rot}: dx={bx-rx:.0f} dy={by-ry:.0f}"
    doc.close()


def test_auto_logo_empty_library_degrades_to_pure_removal(valid_pdf_bytes, tmp_path, monkeypatch):
    """auto_logo=True with no library: logo_skipped, redaction still completes, no image embedded."""
    monkeypatch.setattr(config, "LOGOS_DIR", tmp_path / "empty")
    sid = _ingest(valid_pdf_bytes)
    dpi = 200
    spec = JobSpec(dpi=dpi, auto_logo=True, regions=[{"page": 0, "px_rect": _job_px_rect(dpi)}])
    result = pipeline.process_job(sid, spec)
    assert result["logo_skipped"] is True

    out = pipeline.output_path(sid).read_bytes()
    doc = pdf_engine.open_pdf(out)
    try:
        assert pdf_engine.get_page(doc, 0).get_images() == []
    finally:
        pdf_engine.close(doc)


def test_pick_logo_id_for_rect_skips_non_png_entries(tmp_path, monkeypatch):
    """WR-02: the picker's candidate set MUST be the same allowlist list_logos uses.

    A JPEG manifest entry that list_logos filters out (PNG-only / D-03) must NOT be considered
    by pick_logo_id_for_rect either, even if its native aspect is the closest match. Without the
    fix the JPEG won the aspect search; resolve(chosen) then raised logo_invalid and the region
    silently degraded to pure removal even though a valid wide PNG was in the library. With the
    fix the JPEG is skipped from the picker and the genuine PNG wins.
    """
    from io import BytesIO

    from PIL import Image

    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    # A VALID PNG with a block (2:1) aspect.
    (logos_dir / "block.png").write_bytes(_make_png(200, 100))
    # A wider JPEG (10:1) — Pillow-decodable so a naive aspect read would prefer it for a wide
    # region — but list_logos rejects it as logo_invalid (D-03 PNG-only).
    buf = BytesIO()
    Image.new("RGB", (1000, 100), (0, 128, 0)).save(buf, format="JPEG")
    (logos_dir / "wide.jpg").write_bytes(buf.getvalue())
    manifest = [
        {"id": "block", "file": "block.png", "name": "方", "tags": []},
        {"id": "wide_jpeg", "file": "wide.jpg", "name": "寬 JPEG", "tags": []},
    ]
    (logos_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(config, "LOGOS_DIR", logos_dir)

    # Even for a very wide region (8:1, closer to the JPEG's 10:1 than the PNG's 2:1), the picker
    # MUST return the valid PNG — the JPEG is filtered out by the same gate list_logos uses.
    assert logo.pick_logo_id_for_rect(800, 100) == "block"
    # Sanity: list_logos confirms the JPEG is excluded from the catalog allowlist.
    assert [e["id"] for e in logo.list_logos()] == ["block"]


def test_aspect_cache_bounded_across_asset_replacements(tmp_path, monkeypatch, logo_png_bytes):
    """WR-03: replacing a logo file in place must NOT leak a new cache entry per replacement.

    The aspect cache is keyed by str(path); the value carries (mtime, aspect) so an mtime change
    overwrites the entry rather than appending a sibling. Without the fix the (path, mtime) key
    caused one stale entry per replacement to accumulate in a long-lived uvicorn worker.
    """
    import time

    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    (logos_dir / "logo.png").write_bytes(_make_png(100, 100))   # 1:1
    manifest = [{"id": "x", "file": "logo.png", "name": "x", "tags": []}]
    (logos_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(config, "LOGOS_DIR", logos_dir)

    # Clear the module cache so this test's measurements are independent of prior tests.
    logo._aspect_cache.clear()
    baseline = len(logo._aspect_cache)

    # Prime the cache with the initial asset.
    assert logo.pick_logo_id_for_rect(100, 100) == "x"
    assert len(logo._aspect_cache) == baseline + 1

    # Replace the asset in place a few times, forcing a different mtime each time.
    target = logos_dir / "logo.png"
    aspects = [(200, 100), (300, 100), (400, 100)]
    for i, (w, h) in enumerate(aspects):
        target.write_bytes(_make_png(w, h))
        # Some filesystems quantize mtime — nudge it forward to ensure a real change.
        new_mtime = target.stat().st_mtime + (i + 1) * 1.0
        import os
        os.utime(target, (new_mtime, new_mtime))
        # Trigger another picker call (which goes through _logo_aspect for this entry).
        assert logo.pick_logo_id_for_rect(w, h) == "x"

    # Cache holds AT MOST one entry per asset path — never one-per-replacement.
    assert len(logo._aspect_cache) == baseline + 1, (
        f"aspect cache leaked entries across replacements: {logo._aspect_cache}"
    )
    # Sanity: the cached value reflects the LATEST mtime + aspect (not a stale 1:1 from before).
    key = str(target.resolve())
    cached_mtime, cached_aspect = logo._aspect_cache[key]
    assert cached_mtime == target.stat().st_mtime
    final_w, final_h = aspects[-1]
    assert abs(cached_aspect - final_w / final_h) < 1e-9


def test_pick_logo_id_for_rect_skips_corrupt_entries(tmp_path, monkeypatch, logo_png_bytes):
    """WR-02 (second face): a manifest entry whose file is corrupt is skipped from the picker.

    Mirrors the JPEG case: a corrupt PNG that list_logos filters out (logo_unreadable) must NOT
    be considered for the aspect search either. Otherwise the corrupt entry would silently win
    auto-pick and the region would degrade to pure removal even when a valid logo was available.
    """
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    (logos_dir / "good.png").write_bytes(logo_png_bytes)
    (logos_dir / "broken.png").write_bytes(b"not a real png")
    manifest = [
        {"id": "good", "file": "good.png", "name": "好", "tags": []},
        {"id": "broken", "file": "broken.png", "name": "壞", "tags": []},
    ]
    (logos_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(config, "LOGOS_DIR", logos_dir)

    # The corrupt entry is invisible to the picker; the only visible candidate is the valid PNG.
    chosen = logo.pick_logo_id_for_rect(200, 100)
    assert chosen == "good"
    assert chosen != "broken"
