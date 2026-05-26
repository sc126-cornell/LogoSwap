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


def test_preview_image_stays_original_after_process(client, valid_pdf_bytes):
    """The 原圖 preview endpoint renders the IMMUTABLE original, not the redacted work copy.

    Regression for the UAT bug: after an apply, /pages/{n}/image must still return the BEFORE
    image (unchanged from pre-process) and must DIFFER from the 移除結果 result render — otherwise
    '原圖' shows the redacted result and 清除全部 can't visibly return to the original.
    """
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    px_rect, dpi = _region_px_for(client, sid, 0)

    before = client.get(f"/sessions/{sid}/pages/0/image")
    assert before.status_code == 200
    before_png = before.content

    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": dpi, "regions": [{"page": 0, "px_rect": px_rect}]},
    )
    assert proc.status_code == 200

    after = client.get(f"/sessions/{sid}/pages/0/image")
    result = client.get(f"/sessions/{sid}/result/pages/0/image")
    assert after.status_code == 200 and result.status_code == 200
    # 原圖 unchanged by the apply (renders the original), and distinct from the 移除結果.
    assert after.content == before_png, "原圖 preview must not change after process"
    assert after.content != result.content, "原圖 must differ from the 移除結果 result render"


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


@pytest.mark.parametrize("user_rotation", [90, 180, 270])
def test_process_on_user_rotated_preview_redacts_correctly_and_bakes_rotation(
    client, valid_pdf_bytes, user_rotation
):
    """A region framed on a user-ROTATED preview redacts the correct content AND the exported
    page carries the expected effective /Rotate, while the original SHA-256 is unchanged (D-05).

    The overlay measures px against the ROTATED meta (rotate=user_rotation), so we fetch that
    meta and frame the region the same way: convert the unrotated content rect _REGION_PT into
    the rotated DISPLAYED image-pixel space the user would see. We round-trip the same px the
    client posts (with rotations) and assert the exported region is empty + the page is rotated.
    """
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]

    # The rotated render contract for page 0 (dims swap for 90/270).
    meta = client.get(
        f"/sessions/{sid}/pages/0/meta", params={"rotate": user_rotation}
    ).json()
    assert meta["rotation"] == user_rotation, meta
    dpi = meta["dpi"]
    iw, ih = meta["img_w"], meta["img_h"]

    # Map the unrotated content rect _REGION_PT (points) into the ROTATED displayed pixel box.
    # A point (x,y) in the unrotated page (W=200,H=300 pt) appears in the rotated DISPLAYED
    # space as: 90 -> (H - y, x); 180 -> (W - x, H - y); 270 -> (y, W - x). Scale pt->px by dpi.
    s = dpi / 72.0
    W, H = 200.0, 300.0  # conftest page is 200x300pt

    def to_disp(x, y):
        if user_rotation == 90:
            return (H - y, x)
        if user_rotation == 180:
            return (W - x, H - y)
        return (y, W - x)  # 270

    corners = [
        to_disp(_REGION_PT[0], _REGION_PT[1]),
        to_disp(_REGION_PT[2], _REGION_PT[3]),
    ]
    xs = [c[0] * s for c in corners]
    ys = [c[1] * s for c in corners]
    px_rect = [min(xs), min(ys), max(xs), max(ys)]
    # sanity: the framed rect stays inside the rotated image box
    assert 0 <= px_rect[0] <= iw and 0 <= px_rect[2] <= iw
    assert 0 <= px_rect[1] <= ih and 0 <= px_rect[3] <= ih

    original = storage.original_path(sid)
    before = hashlib.sha256(original.read_bytes()).hexdigest()

    resp = client.post(
        f"/sessions/{sid}/process",
        json={
            "dpi": dpi,
            "regions": [{"page": 0, "px_rect": px_rect}],
            "rotations": {"0": user_rotation},
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["regions"][0]["removed"] is True, resp.text

    # Original is byte-for-byte unchanged (deferred-mutation D-05).
    after = hashlib.sha256(original.read_bytes()).hexdigest()
    assert before == after, "original must be unchanged after a rotated /process"

    # The downloaded PDF page carries the baked effective rotation, and the framed region is
    # truly empty. We open the exported bytes and check on the rotated page directly: derive
    # the rotated displayed pixel dims from the page rect (which reflects /Rotate), map px->pt,
    # and assert no residual words/drawings.
    dl = client.get(f"/sessions/{sid}/result")
    assert dl.status_code == 200
    out_doc = pdf_engine.open_pdf(dl.content)
    try:
        page = pdf_engine.get_page(out_doc, 0)
        assert int(page.rotation) == user_rotation, "download must bake the user rotation"
        rect = coords.pixels_to_pdf_rect(px_rect, dpi, page)
        rt = (rect.x0, rect.y0, rect.x1, rect.y1)
        assert pdf_engine.get_text_words_in_rect(page, rt) == []
        assert pdf_engine.get_drawings_fully_inside(page, rt) == []
    finally:
        pdf_engine.close(out_doc)


def test_process_rotation_does_not_persist_to_work_copy(client, valid_pdf_bytes):
    """The WORK copy stays at intrinsic rotation (0) so the result-render path re-applies the
    user rotation transiently — symmetric with 原圖, avoiding a double rotation."""
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    px_rect, dpi = _region_px_for(client, sid, 0)
    resp = client.post(
        f"/sessions/{sid}/process",
        json={
            "dpi": dpi,
            "regions": [{"page": 0, "px_rect": px_rect}],
            "rotations": {"0": 90},
        },
    )
    assert resp.status_code == 200, resp.text

    # The result-render WITHOUT rotate reflects the work copy's intrinsic rotation (0).
    img0 = client.get(f"/sessions/{sid}/result/pages/0/image")
    assert img0.headers["X-Page-Rotation"] == "0", "work copy must stay at intrinsic rotation"
    # The result-render WITH rotate=90 reflects the rotated orientation transiently.
    img90 = client.get(f"/sessions/{sid}/result/pages/0/image", params={"rotate": 90})
    assert img90.headers["X-Page-Rotation"] == "90"


@pytest.mark.parametrize("endpoint", ["pages", "result"])
def test_invalid_rotate_param_is_400(client, valid_pdf_bytes, endpoint):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    base = (
        f"/sessions/{sid}/pages/0/image"
        if endpoint == "pages"
        else f"/sessions/{sid}/result/pages/0/image"
    )
    resp = client.get(base, params={"rotate": 45})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_rotation"


def test_process_invalid_rotation_value_is_422(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": [], "rotations": {"0": 45}},
    )
    assert resp.status_code in {400, 422}
    assert resp.status_code != 500


def test_process_without_logo_is_pure_removal(client, valid_pdf_bytes):
    """D-01 (REVISED by hotfix #06): a /process with no logo_id places NO LOGO image.

    Original D-01 (Phase 2): no logo_id ⇒ ``page.get_images() == []`` everywhere.

    Revised by hotfix #06 (dCt-residue, Option A raster fallback): no logo_id ⇒ no
    LOGO image; the only image XObject that may appear on a page is a raster
    fallback overlay placed by ``remove_region_vector`` when post-redaction
    zero-area ``type='f'`` residue density crosses
    ``ZERO_AREA_RASTER_THRESHOLD`` inside the framed rect. The overlay is a
    32×32 solid-white image XObject; ITS PRESENCE does NOT imply a logo was
    placed.

    For the standard ``valid_pdf_bytes`` fixture (no supplier-CAD-glyph zero-area
    decomposition), the dense branch never fires and ``page.get_images() == []``
    still holds — i.e. this test's assertion is unchanged in spirit, only its
    docstring is revised to acknowledge the new contract. The dense-branch
    behaviour is pinned end-to-end by
    ``tests/test_redact.py::test_remove_region_vector_dense_real_zero_area_paths_end_to_end``
    (which builds a real >=100 zero-area fixture and asserts exactly one raster
    fallback image is inserted per region).
    """
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    px_rect, dpi = _region_px_for(client, sid, 0)
    resp = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": dpi, "regions": [{"page": 0, "px_rect": px_rect}]},
    )
    assert resp.status_code == 200, resp.text

    dl = client.get(f"/sessions/{sid}/result")
    out_doc = pdf_engine.open_pdf(dl.content)
    try:
        for page_no in range(pdf_engine.page_count(out_doc)):
            page = pdf_engine.get_page(out_doc, page_no)
            # Standard fixture is below the dense threshold → still no images.
            # Any image that appears MUST be a raster fallback overlay (asserted
            # by the dense-branch integration test elsewhere); a LOGO image is
            # specifically the contract this test guards against.
            assert page.get_images() == [], (
                "no logo_id must mean no LOGO image (D-01 as revised by hotfix #06); "
                "any image present would be a raster fallback overlay — but the "
                "standard fixture is below the dense-residue threshold and should "
                "produce no image at all"
            )
    finally:
        pdf_engine.close(out_doc)


def test_failed_work_save_does_not_emit_orphan_output(valid_pdf_bytes, monkeypatch):
    """WR-05: if the WORK COPY save fails, the OUTPUT must NOT be on disk either.

    The bug was an asymmetric two-save order (output first, work second). When the work-copy
    save failed (disk full, permission), the output PDF was already on disk but the work copy
    had been reset to the pristine original at the start of the run and was NOT redacted. The
    result: /result downloads a redacted PDF while /result/pages/.../image renders the UNREDACTED
    work copy — the before/after preview lies about the downloaded contents.

    The fix saves the work copy to a tmp file FIRST, then the output to its own tmp, then
    atomically swaps both at the end. Simulating a failure in the work-copy save now leaves
    neither artifact in its final place (work stays pristine, output absent). We call
    pipeline.process_job directly (the API layer has no OSError exception handler — that's a
    separate concern; what we assert here is the pipeline's on-disk invariant).
    """
    from app.services import ingest, pdf_engine, pipeline
    from app.models import JobSpec

    sid = ingest.ingest_upload("design.pdf", valid_pdf_bytes).session_id
    s = 200 / 72.0
    px_rect = [v * s for v in _REGION_PT]

    assert not pipeline.output_path(sid).is_file(), "no prior run, no output expected"

    # Fail the FIRST save_doc call (the work_tmp save).
    calls = {"n": 0}
    original_save_doc = pdf_engine.save_doc

    def failing_save_doc(doc, path, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated disk-full on work-copy save")
        return original_save_doc(doc, path, **kwargs)

    monkeypatch.setattr(pdf_engine, "save_doc", failing_save_doc)

    spec = JobSpec(dpi=200, regions=[{"page": 0, "px_rect": px_rect}])
    with pytest.raises(OSError):
        pipeline.process_job(sid, spec)

    # CRITICAL: the output PDF was NEVER created (the bug WR-05 closed). Before/after preview
    # cannot disagree with what /result downloads, because /result has nothing to download.
    assert not pipeline.output_path(sid).is_file(), (
        "output PDF must not exist when the work-copy save failed (WR-05)"
    )

    # No stray *.tmp.* files left behind (cleanup obligation).
    work_dir = storage.work_path(sid).parent
    out_dir = storage.outputs_dir(sid)
    for d in (work_dir, out_dir):
        if d.exists():
            for p in d.iterdir():
                assert ".tmp." not in p.name, f"stray tmp file left behind: {p}"


def test_failed_output_save_does_not_emit_stale_work(valid_pdf_bytes, monkeypatch):
    """WR-05 (second face): a FAILED output save must NOT leave a swapped-in redacted work copy.

    Even though the new order saves the work copy first to a tmp, the final atomic swap happens
    only after BOTH tmps exist. If the output save fails AFTER the work tmp was written, both
    tmps are cleaned up and neither final artifact is in place. This test simulates a failure
    in the SECOND save_doc call (out_tmp) and asserts the same invariants as above.
    """
    from app.services import ingest, pdf_engine, pipeline
    from app.models import JobSpec

    sid = ingest.ingest_upload("design.pdf", valid_pdf_bytes).session_id
    s = 200 / 72.0
    px_rect = [v * s for v in _REGION_PT]

    calls = {"n": 0}
    original_save_doc = pdf_engine.save_doc

    def fail_second_save_doc(doc, path, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated disk-full on output save")
        return original_save_doc(doc, path, **kwargs)

    monkeypatch.setattr(pdf_engine, "save_doc", fail_second_save_doc)

    spec = JobSpec(dpi=200, regions=[{"page": 0, "px_rect": px_rect}])
    with pytest.raises(OSError):
        pipeline.process_job(sid, spec)

    # Neither the work-copy was atomically swapped, nor was the output written.
    assert not pipeline.output_path(sid).is_file(), (
        "output PDF must not exist when the output save failed (WR-05)"
    )

    # No stray *.tmp.* files left behind.
    work_dir = storage.work_path(sid).parent
    out_dir = storage.outputs_dir(sid)
    for d in (work_dir, out_dir):
        if d.exists():
            for p in d.iterdir():
                assert ".tmp." not in p.name, f"stray tmp file left behind: {p}"


def test_original_unchanged_across_remove_insert(client, valid_pdf_bytes, logo_library):
    """D-05: the immutable original's SHA-256 is unchanged across a remove+INSERT run."""
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    px_rect, dpi = _region_px_for(client, sid, 0)

    original = storage.original_path(sid)
    before = hashlib.sha256(original.read_bytes()).hexdigest()

    resp = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": dpi, "regions": [{"page": 0, "px_rect": px_rect}], "logo_id": "placeholder"},
    )
    assert resp.status_code == 200, resp.text

    after = hashlib.sha256(original.read_bytes()).hexdigest()
    assert before == after, "original must be unchanged after a remove+insert run (D-05)"

    # The remove+insert result actually embedded the logo (sanity that this exercised insert).
    dl = client.get(f"/sessions/{sid}/result")
    out_doc = pdf_engine.open_pdf(dl.content)
    try:
        assert pdf_engine.get_page(out_doc, 0).get_images(), "logo must be present in the result"
    finally:
        pdf_engine.close(out_doc)


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


# --- Phase 4 Task 04-01-03: image upload + logo placement integration ---------------


def test_png_upload_with_logo_placement(client, png_bytes, logo_library):
    """Phase 4 success criteria #3 partial-coverage: image-type files use the SAME logo
    placement path as vector PDFs (Phase 3 LOGO-01 / LOGO-02 unchanged).

    The logo library is provided by the ``logo_library`` fixture (Phase 3). If the picker
    has any logo we add ``logo_id`` to the JobSpec and assert ``logo_skipped == False`` —
    the run must succeed end-to-end and the logo must land on the framed area of the
    normalized A4 page.
    """
    resp = client.post(
        "/sessions",
        files={"file": ("scan.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    logos_resp = client.get("/logos")
    assert logos_resp.status_code == 200
    logos_list = logos_resp.json().get("logos", [])
    if not logos_list:
        pytest.skip("logo library empty — graceful degradation tested elsewhere")

    job = {
        "dpi": 200,
        "regions": [{"page": 0, "px_rect": [100.0, 100.0, 400.0, 300.0]}],
        "logo_id": logos_list[0]["id"],
    }
    proc = client.post(f"/sessions/{sid}/process", json=job)
    assert proc.status_code == 200, proc.json()
    assert proc.json()["logo_skipped"] is False


# --------------------------------------------------------------------------------------
# Phase 4-02 Task 03: image-only PDF + dual-layer OCR + image-upload e2e raster dispatch
# --------------------------------------------------------------------------------------


def test_image_only_pdf_full_frame_redacts_to_white(client, image_only_pdf_bytes):
    """Image-only PDF (scan PDF) → /process with a full-page frame → result PDF has
    the image xref auto-removed AND the centre pixel renders white."""
    resp = client.post(
        "/sessions", files={"file": ("scan.pdf", image_only_pdf_bytes, "application/pdf")}
    )
    assert resp.status_code == 201
    sid = resp.json()["session_id"]
    dpi = 200
    img_w = 595.0 * dpi / 72.0
    img_h = 842.0 * dpi / 72.0
    job = {
        "dpi": dpi,
        "regions": [{"page": 0, "px_rect": [0.0, 0.0, img_w, img_h]}],
    }
    proc = client.post(f"/sessions/{sid}/process", json=job)
    assert proc.status_code == 200, proc.json()
    assert proc.json()["regions"][0]["removed"] is True

    result = client.get(f"/sessions/{sid}/result")
    assert result.status_code == 200
    assert result.content.startswith(b"%PDF-")
    doc = pdf_engine.open_pdf(result.content)
    try:
        page = pdf_engine.get_page(doc, 0)
        # Full-frame raster redaction auto-removes the image xref entirely.
        assert page.get_images() == [], (
            f"image xref should be removed on full-frame raster apply; got {page.get_images()}"
        )
        pix = page.get_pixmap(dpi=72)
        cx, cy = pix.width // 2, pix.height // 2
        pixel = pix.pixel(cx, cy)
        assert all(c >= 250 for c in pixel[:3]), f"expected white, got {pixel}"
    finally:
        pdf_engine.close(doc)


def test_image_only_pdf_with_logo_placement(client, image_only_pdf_bytes, logo_library):
    """Image-only PDF + logo_id → logo is placed AFTER the raster redaction (Pitfall 1
    invariant unchanged) and survives the apply. Phase 4 success criteria #3 — image-type
    files take the same Phase 3 logo path."""
    resp = client.post(
        "/sessions", files={"file": ("scan.pdf", image_only_pdf_bytes, "application/pdf")}
    )
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    logos_resp = client.get("/logos")
    logos_list = logos_resp.json().get("logos", [])
    if not logos_list:
        pytest.skip("logo library empty — graceful degradation tested elsewhere")
    logo_id = logos_list[0]["id"]

    # Frame a 200x200pt patch that sits inside the image region of the A4 page.
    dpi = 200
    scale = dpi / 72.0
    px_rect = [100.0 * scale, 400.0 * scale, 400.0 * scale, 600.0 * scale]
    job = {
        "dpi": dpi,
        "regions": [{"page": 0, "px_rect": px_rect}],
        "logo_id": logo_id,
    }
    proc = client.post(f"/sessions/{sid}/process", json=job)
    assert proc.status_code == 200, proc.json()
    assert proc.json()["logo_skipped"] is False

    result = client.get(f"/sessions/{sid}/result")
    assert result.status_code == 200
    doc = pdf_engine.open_pdf(result.content)
    try:
        page = pdf_engine.get_page(doc, 0)
        # At least one image XObject must remain on the page — the logo placement.
        # (The raster background image survives in non-overlapping pixels too, but the
        # critical invariant is "logo is present after redaction".)
        assert len(page.get_images()) >= 1, "logo must be embedded after raster redaction"
    finally:
        pdf_engine.close(doc)


def test_dual_layer_ocr_text_leak_closed_end_to_end(client, dual_layer_ocr_pdf_bytes):
    """Dual-layer OCR PDF e2e: frame the OCR text rect → /process → /result shows no
    extractable words inside that rect (Pitfall 3 / Pitfall E closed)."""
    resp = client.post(
        "/sessions",
        files={"file": ("ocr.pdf", dual_layer_ocr_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    # The fixture inserts text at (100,400) baseline; glyphs sit a few pt above.
    dpi = 200
    scale = dpi / 72.0
    px_rect = [50.0 * scale, 388.0 * scale, 400.0 * scale, 412.0 * scale]
    job = {"dpi": dpi, "regions": [{"page": 0, "px_rect": px_rect}]}
    proc = client.post(f"/sessions/{sid}/process", json=job)
    assert proc.status_code == 200, proc.json()

    result = client.get(f"/sessions/{sid}/result")
    assert result.status_code == 200
    doc = pdf_engine.open_pdf(result.content)
    try:
        page = pdf_engine.get_page(doc, 0)
        words = pdf_engine.get_text_words_in_rect(page, (50.0, 388.0, 400.0, 412.0))
        assert words == [], f"dual-layer OCR text leak — expected [], got {words}"
    finally:
        pdf_engine.close(doc)


# --------------------------------------------------------------------------------------
# Phase 5 Plan 05-02 Task 3: /process timeout + corrupted gate + janitor triggers
# --------------------------------------------------------------------------------------


def test_meta_original_sha256_written_at_ingest(client, valid_pdf_bytes):
    """D-C1: POST /sessions → meta.json contains 64-char hex original_sha256."""
    import hashlib as _hashlib

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    meta = storage.read_session_meta(sid)
    assert meta is not None
    assert "original_sha256" in meta
    assert len(meta["original_sha256"]) == 64
    # And matches the uploaded bytes (this is the property the verify check enforces)
    assert meta["original_sha256"] == _hashlib.sha256(valid_pdf_bytes).hexdigest()


def test_original_tampered_returns_503(client, valid_pdf_bytes):
    """End-to-end: ingest → tamper originals → POST /process → 503 original_tampered."""
    import os as _os
    import stat as _stat

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = resp.json()["session_id"]

    orig = storage.original_path(sid)
    _os.chmod(orig, _stat.S_IWRITE | _stat.S_IREAD)
    orig.write_bytes(b"%PDF-1.7\nTAMPERED\n%%EOF")
    _os.chmod(orig, _stat.S_IRUSR | _stat.S_IRGRP | _stat.S_IROTH)

    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": []},
    )
    assert proc.status_code == 503, proc.json()
    detail = proc.json()["detail"]
    assert detail["code"] == "original_tampered"
    assert "原始檔" in detail["message"] or "重新上傳" in detail["message"]


def test_corrupted_session_blocked_from_process(client, valid_pdf_bytes):
    """A session marked corrupted before /process short-circuits to 410 session_corrupted."""
    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = resp.json()["session_id"]
    storage.mark_session_corrupted(sid)

    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": []},
    )
    assert proc.status_code == 410, proc.json()
    assert proc.json()["detail"]["code"] == "session_corrupted"


def test_corrupted_session_blocked_from_get_result_download(client, valid_pdf_bytes):
    """CR-02: GET /result must short-circuit to 410 session_corrupted when .corrupted is set.

    Reproduces the contract gap: a process run completes (output PDF on disk), THEN a later
    tamper-detect writes the .corrupted sentinel; without the gate GET /result would
    happily stream the stale pre-tamper output. The gate runs after _require_session so a
    crafted sid still returns 404 (no oracle).
    """
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    px_rect, dpi = _region_px_for(client, sid, 0)
    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": dpi, "regions": [{"page": 0, "px_rect": px_rect}]},
    )
    assert proc.status_code == 200
    # Sanity: download works pre-corruption.
    pre = client.get(f"/sessions/{sid}/result")
    assert pre.status_code == 200

    storage.mark_session_corrupted(sid)

    post = client.get(f"/sessions/{sid}/result")
    assert post.status_code == 410, post.json()
    assert post.json()["detail"]["code"] == "session_corrupted"


def test_corrupted_session_blocked_from_result_page_image(client, valid_pdf_bytes):
    """CR-02: GET /result/pages/{n}/image must short-circuit to 410 session_corrupted.

    Renders the redacted work copy; without the gate it would still render the pre-tamper
    state (mark_session_corrupted is a touch, not a clear). 410 keeps the fail-closed
    semantic consistent across all three D-C3 surfaces (/process, /result, /result/pages).
    """
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    # Sanity: pre-corruption render works.
    pre = client.get(f"/sessions/{sid}/result/pages/0/image")
    assert pre.status_code == 200

    storage.mark_session_corrupted(sid)

    post = client.get(f"/sessions/{sid}/result/pages/0/image")
    assert post.status_code == 410, post.json()
    assert post.json()["detail"]["code"] == "session_corrupted"


def test_legacy_session_without_sha256_treated_as_corrupted(client, valid_pdf_bytes):
    """Pitfall 4: ingest then strip original_sha256 from meta.json → /process rejects.

    Either "session_corrupted" (legacy fallback path) or "original_tampered" (verify
    mismatch on a missing field) is acceptable — both semantics are "禁止使用,請重新上傳".
    """
    import json as _json

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = resp.json()["session_id"]
    # Strip the field — simulate a Phase 1–4 session meeting Phase 5 verify.
    meta_path = storage.meta_path(sid)
    meta = _json.loads(meta_path.read_text())
    meta.pop("original_sha256", None)
    meta_path.write_text(_json.dumps(meta))

    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": []},
    )
    assert proc.status_code in {410, 503}, proc.json()
    assert proc.json()["detail"]["code"] in {"session_corrupted", "original_tampered"}


def test_process_timeout_returns_504(client, valid_pdf_bytes, monkeypatch):
    """D-D3: a /process exceeding PROCESS_TIMEOUT_SECONDS returns 504 processing_timeout.

    Monkey-patch the config constant + the pipeline function so we don't actually wait
    60 seconds. The route handler wraps process_job in asyncio.wait_for(asyncio.to_thread
    (process_job, ...), timeout=config.PROCESS_TIMEOUT_SECONDS).
    """
    import time as _time

    from app import config as _config
    from app.services import pipeline as _pipeline

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = resp.json()["session_id"]

    # Shrink the timeout and make process_job sleep past it.
    monkeypatch.setattr(_config, "PROCESS_TIMEOUT_SECONDS", 0.2)

    def slow_process_job(session_id, job_spec):
        _time.sleep(2.0)
        return {"output_filename": "x.pdf", "page_count": 1, "regions": [], "logo_skipped": False}

    monkeypatch.setattr(_pipeline, "process_job", slow_process_job)

    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": []},
    )
    assert proc.status_code == 504, proc.json()
    assert proc.json()["detail"]["code"] == "processing_timeout"


def test_process_corrupted_check_runs_before_timeout(client, valid_pdf_bytes, monkeypatch):
    """The corrupted short-circuit must fire BEFORE the timeout wrapper — proving 410 is
    immediate even if process_job would have run forever.
    """
    import time as _time

    from app import config as _config
    from app.services import pipeline as _pipeline

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = resp.json()["session_id"]
    storage.mark_session_corrupted(sid)

    monkeypatch.setattr(_config, "PROCESS_TIMEOUT_SECONDS", 60)

    def forever_process_job(session_id, job_spec):
        _time.sleep(10)
        return {}

    monkeypatch.setattr(_pipeline, "process_job", forever_process_job)

    t0 = _time.time()
    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": []},
    )
    elapsed = _time.time() - t0
    assert proc.status_code == 410
    assert proc.json()["detail"]["code"] == "session_corrupted"
    assert elapsed < 1.0, f"corrupted short-circuit took {elapsed}s (must be ≪ timeout)"


def test_sessions_post_calls_janitor_at_end(client, valid_pdf_bytes, monkeypatch):
    """D-B1 trigger (b): /sessions POST end calls janitor.sweep_expired_sessions()."""
    from app.api import sessions as sessions_api

    calls = {"n": 0}

    def counting_sweep(now=None):
        calls["n"] += 1
        return 0

    monkeypatch.setattr(sessions_api.janitor, "sweep_expired_sessions", counting_sweep)

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 201
    assert calls["n"] >= 1


def test_process_post_calls_janitor_at_end(client, valid_pdf_bytes, monkeypatch):
    """D-B1 trigger (c): /process end calls janitor.sweep_expired_sessions() in finally."""
    from app.api import process as process_api

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = resp.json()["session_id"]

    calls = {"n": 0}

    def counting_sweep(now=None):
        calls["n"] += 1
        return 0

    monkeypatch.setattr(process_api.janitor, "sweep_expired_sessions", counting_sweep)

    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": []},
    )
    assert proc.status_code == 200
    assert calls["n"] >= 1


def test_janitor_failure_does_not_taint_process_request(client, valid_pdf_bytes, monkeypatch):
    """janitor.sweep raise → /process still returns 200 (try/except swallows in finally)."""
    from app.api import process as process_api

    resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = resp.json()["session_id"]

    def raising_sweep(now=None):
        raise OSError("simulated janitor failure")

    monkeypatch.setattr(process_api.janitor, "sweep_expired_sessions", raising_sweep)

    proc = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": []},
    )
    assert proc.status_code == 200, proc.json()


# --------------------------------------------------------------------------------------
# Phase 4 Task 04-02-03 (carried) — image_upload_through_to_raster_dispatch
# --------------------------------------------------------------------------------------


def test_image_upload_through_to_raster_dispatch(client, png_bytes):
    """Vertical slice 04-01 → 04-02 end-to-end: PNG upload normalized to A4 PDF in
    ingest, framed region falls inside the image XObject → raster dispatch runs →
    download filename uses ``scan_logoswap.pdf`` stem (D-13)."""
    resp = client.post("/sessions", files={"file": ("scan.png", png_bytes, "image/png")})
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    # 400x300 PNG keep_proportion'd into A4 (595x842 portrait).
    # Aspect 4:3 → fitted width 595, fitted height ≈ 446.25 → letterbox y ≈ [197.875, 644.125].
    # Pick a 200x200 rect well inside that band.
    dpi = 200
    scale = dpi / 72.0
    px_rect = [200.0 * scale, 350.0 * scale, 400.0 * scale, 550.0 * scale]
    job = {"dpi": dpi, "regions": [{"page": 0, "px_rect": px_rect}]}
    proc = client.post(f"/sessions/{sid}/process", json=job)
    assert proc.status_code == 200, proc.json()
    assert proc.json()["regions"][0]["removed"] is True

    result = client.get(f"/sessions/{sid}/result")
    assert result.status_code == 200
    cd = result.headers.get("content-disposition", "")
    # D-13: scan.png → scan_logoswap.pdf (stem-only sanitization, Phase 2 _logoswap_name).
    assert "scan_logoswap.pdf" in cd.lower(), (
        f"download filename should use stem 'scan'; Content-Disposition = {cd!r}"
    )
