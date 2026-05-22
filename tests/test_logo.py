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

from app import storage
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
