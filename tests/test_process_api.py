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
    """D-01: a /process with no logo_id produces NO embedded image — Phase-2 behavior unchanged."""
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
            assert page.get_images() == [], "no logo_id must mean no embedded image (D-01)"
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
