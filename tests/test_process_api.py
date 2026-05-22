"""End-to-end API tests for the process + result-render + download endpoints (Task 2).

Drives the full slice through the TestClient: ingest -> POST /process a region computed
from the page_meta DPI -> 200 with per-region flags -> GET the result-render after-image
(six X- headers) -> assert (by opening the EXPORTED PDF with fitz) the region is truly
empty -> GET /result downloads a PDF attachment named ``*_logoswap.pdf`` keeping all pages
(D-07). Malformed bodies are structured 4xx (never 500); /result before a process run is a
404 ``result_not_ready``; the original is never mutated.
"""

from __future__ import annotations

import hashlib

import pytest

from app import storage
from app.services import coords, pdf_engine

# Conftest page is 200x300pt with text near (40,60) and a line at y=100. A rect covering
# points (10,40)->(190,120) covers both; convert to image pixels at the render DPI returned
# by /meta so the client/server agree on scale (the px_rect contract).
_REGION_PT = (10.0, 40.0, 190.0, 120.0)


def _upload(client, data: bytes, filename: str = "design.pdf"):
    return client.post(
        "/sessions", files={"file": (filename, data, "application/pdf")}
    )


def _region_px_for(client, sid: str, page_no: int = 0):
    """Compute the image-pixel rect for _REGION_PT from the page's actual render DPI."""
    meta = client.get(f"/sessions/{sid}/pages/{page_no}/meta").json()
    scale = meta["dpi"] / 72.0
    return [v * scale for v in _REGION_PT], meta["dpi"]


def _exported_region_empty(out_bytes: bytes, px_rect, dpi: int, page_no: int = 0) -> bool:
    """Open exported PDF bytes and report whether the region has NO text and NO drawings."""
    doc = pdf_engine.open_pdf(out_bytes)
    try:
        page = pdf_engine.get_page(doc, page_no)
        rect = coords.pixels_to_pdf_rect(px_rect, dpi, page)
        rt = (rect.x0, rect.y0, rect.x1, rect.y1)
        words = pdf_engine.get_text_words_in_rect(page, rt)
        drawings = pdf_engine.get_drawings_intersecting(page, rt)
        return words == [] and drawings == []
    finally:
        pdf_engine.close(doc)


# --------------------------------------------------------------------------------------
# Happy path: process -> after-image -> download, with true-removal verified on the export
# --------------------------------------------------------------------------------------


def test_process_then_render_then_download_full_slice(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    px_rect, dpi = _region_px_for(client, sid, 0)

    # Original hash before processing (deferred-mutation check).
    original = storage.original_path(sid)
    before = hashlib.sha256(original.read_bytes()).hexdigest()

    # POST /process -> 200 with per-region flags.
    resp = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": dpi, "regions": [{"page": 0, "px_rect": px_rect}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_count"] == 2  # all pages kept (D-07)
    assert body["output_filename"] == "design_logoswap.pdf"
    assert body["regions"][0] == {"page": 0, "removed": True, "clamped": False}

    # The original is byte-for-byte unchanged (D-05).
    after = hashlib.sha256(original.read_bytes()).hexdigest()
    assert before == after, "original must be unchanged after /process"

    # GET the result-render after-image for page 0 -> image/png with the six X- headers.
    img = client.get(f"/sessions/{sid}/result/pages/0/image")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content[:4] == b"\x89PNG"
    for header in (
        "X-Page-Width-Pt",
        "X-Page-Height-Pt",
        "X-Page-Rotation",
        "X-Render-Dpi",
        "X-Image-Width-Px",
        "X-Image-Height-Px",
    ):
        assert header in img.headers, f"missing {header}"

    # GET /result -> a PDF attachment named *_logoswap.pdf, keeping all pages, region empty.
    dl = client.get(f"/sessions/{sid}/result")
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"
    cd = dl.headers["content-disposition"]
    assert "attachment" in cd
    assert "design_logoswap.pdf" in cd  # RFC-5987 filename* carries the CJK-safe name

    out_doc = pdf_engine.open_pdf(dl.content)
    try:
        assert pdf_engine.page_count(out_doc) == 2  # D-07
    finally:
        pdf_engine.close(out_doc)

    # The exported region truly extracts NOTHING (REMOVE-01) — open the downloaded bytes.
    assert _exported_region_empty(dl.content, px_rect, dpi, 0)


def test_result_render_valid_before_processing(client, valid_pdf_bytes):
    # Before any process run the work copy equals the original, so the after-image endpoint
    # still renders (it just shows the unmodified page).
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    img = client.get(f"/sessions/{sid}/result/pages/0/image")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.headers["X-Render-Dpi"] == "200"


def test_before_and_after_images_share_effective_dpi_and_dims(client, valid_pdf_bytes):
    # WR-02: the before-image (/pages/{n}/image) and the after-image
    # (/result/pages/{n}/image) must render at the SAME effective DPI and pixel size for a
    # page, so the before/after toggle never swaps between two differently-sized images while
    # the overlay assumes one img_w/img_h. Both route through render.fit_dpi_to_pixel_budget;
    # redaction does not change page geometry, so the dims hold after processing too.
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    px_rect, dpi = _region_px_for(client, sid, 0)
    client.post(
        f"/sessions/{sid}/process",
        json={"dpi": dpi, "regions": [{"page": 0, "px_rect": px_rect}]},
    )
    for page_no in range(2):
        before = client.get(f"/sessions/{sid}/pages/{page_no}/image")
        after = client.get(f"/sessions/{sid}/result/pages/{page_no}/image")
        assert before.status_code == 200 and after.status_code == 200
        for header in ("X-Render-Dpi", "X-Image-Width-Px", "X-Image-Height-Px"):
            assert before.headers[header] == after.headers[header], (
                f"page {page_no} header {header} differs: "
                f"before={before.headers[header]} after={after.headers[header]}"
            )


def test_result_render_out_of_range_page_404(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.get(f"/sessions/{sid}/result/pages/999/image")
    assert resp.status_code == 404


# --------------------------------------------------------------------------------------
# Error cases: not-ready download, missing session, malformed bodies -> structured 4xx
# --------------------------------------------------------------------------------------


def test_download_before_process_is_result_not_ready_404(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.get(f"/sessions/{sid}/result")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "result_not_ready"


def test_process_unknown_session_404(client):
    resp = client.post(
        "/sessions/THIS-DOES-NOT-EXIST/process",
        json={"dpi": 200, "regions": []},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "session_not_found"


def test_result_render_unknown_session_404(client):
    resp = client.get("/sessions/THIS-DOES-NOT-EXIST/result/pages/0/image")
    assert resp.status_code == 404


def test_download_unknown_session_404(client):
    resp = client.get("/sessions/THIS-DOES-NOT-EXIST/result")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "bad_body",
    [
        {"regions": []},  # missing dpi
        {"dpi": 200, "regions": [{"page": 0, "px_rect": [1, 2, 3]}]},  # px_rect len 3
        {"dpi": 200, "regions": [{"page": -1, "px_rect": [1, 2, 3, 4]}]},  # page < 0
        {"dpi": 999999, "regions": []},  # dpi over MAX_DPI
        {"dpi": 1, "regions": []},  # dpi under MIN_DPI
    ],
)
def test_process_malformed_body_is_structured_4xx_not_500(client, valid_pdf_bytes, bad_body):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.post(f"/sessions/{sid}/process", json=bad_body)
    assert resp.status_code in {400, 422}, resp.text
    assert resp.status_code != 500
    detail = resp.json()["detail"]
    assert "code" in detail and "message" in detail


def test_process_too_many_regions_is_4xx(client, valid_pdf_bytes, monkeypatch):
    # DoS T-02-04: a regions list over MAX_REGIONS is rejected (422), never processed.
    from app import config as cfg

    monkeypatch.setattr(cfg, "MAX_REGIONS", 3)
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    regions = [{"page": 0, "px_rect": [0, 0, 1, 1]} for _ in range(4)]
    resp = client.post(f"/sessions/{sid}/process", json={"dpi": 200, "regions": regions})
    assert resp.status_code in {400, 422}
    assert resp.status_code != 500
    assert "code" in resp.json()["detail"]


def test_process_page_out_of_range_is_structured_4xx(client, valid_pdf_bytes):
    # A syntactically valid JobSpec whose page index exceeds the doc -> typed 422, not 500.
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": [{"page": 50, "px_rect": [1, 2, 30, 40]}]},
    )
    assert resp.status_code == 422
    assert resp.status_code != 500
    assert resp.json()["detail"]["code"] == "page_out_of_range"


def test_process_empty_regions_exports_noop(client, valid_pdf_bytes):
    # An empty regions list is a valid no-op export; /result then downloads the full PDF.
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.post(f"/sessions/{sid}/process", json={"dpi": 200, "regions": []})
    assert resp.status_code == 200
    assert resp.json()["page_count"] == 2
    dl = client.get(f"/sessions/{sid}/result")
    assert dl.status_code == 200
    out_doc = pdf_engine.open_pdf(dl.content)
    try:
        assert pdf_engine.page_count(out_doc) == 2
    finally:
        pdf_engine.close(out_doc)


def test_process_crafted_session_id_is_404(client):
    # The Phase-1 allowlist must not regress: a crafted id is a plain 404 on /process.
    resp = client.post("/sessions/has space/process", json={"dpi": 200, "regions": []})
    assert resp.status_code == 404
    assert resp.status_code != 500
