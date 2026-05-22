"""Nyquist gap-fill tests for Phase 1 (input-preview).

Covers genuine behavioral gaps that the 87-test suite does not reach:

  UPLOAD-01 gap: the POST /sessions 201 response MUST include a `filename` field
    (the contract is {session_id, page_count, filename}). The existing suite asserts
    session_id and page_count but never touches the filename key.

  PREVIEW-02 gap: multi-page navigation requires that EVERY valid page index in
    0..page_count-1 is addressable. The existing suite always fetches page 0. A 2-page
    document's page 1 must return 200 (image endpoint) and a correct page_no (meta
    endpoint) — the second-page path is genuinely untested at the API layer.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# UPLOAD-01: POST /sessions 201 response carries `filename`
# ---------------------------------------------------------------------------


def test_upload_response_includes_filename_field(client, valid_pdf_bytes):
    """POST /sessions must return {session_id, page_count, filename} in the 201 body.

    The filename field is part of the contract (01-01-PLAN.md <interfaces>) but was
    never asserted in the existing test suite.  This test fails if the field is absent
    or empty.
    """
    resp = client.post(
        "/sessions",
        files={"file": ("my_drawing.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 201, f"expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "filename" in body, f"filename field missing from 201 body: {body}"
    assert body["filename"], f"filename field is empty in 201 body: {body}"


def test_upload_response_filename_sanitized(client, valid_pdf_bytes):
    """POST /sessions must sanitize the client filename before echoing it back.

    A path-traversal client filename ('../../evil.pdf') must NOT appear verbatim in
    the response — the returned filename must be safe (no directory separators, no ..).
    """
    resp = client.post(
        "/sessions",
        files={"file": ("../../evil.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 201, f"expected 201, got {resp.status_code}: {resp.text}"
    returned_name = resp.json()["filename"]
    assert "/" not in returned_name, f"unsanitized slash in filename: {returned_name!r}"
    assert "\\" not in returned_name, f"unsanitized backslash in filename: {returned_name!r}"
    assert ".." not in returned_name, f"unsanitized '..' in filename: {returned_name!r}"


# ---------------------------------------------------------------------------
# PREVIEW-02: multi-page navigation — every valid page index must be reachable
# ---------------------------------------------------------------------------


def test_second_page_image_returns_200_png_for_multipage_doc(client, valid_pdf_bytes):
    """GET /sessions/{id}/pages/1/image must succeed (200, image/png) for a 2-page doc.

    The existing suite only fetches page 0.  The multi-page navigation contract
    (PREVIEW-02) requires that EVERY page in 0..page_count-1 is addressable.
    Page 1 is the first page that exercises the non-zero-index path through the render
    service and the API route.
    """
    upload_resp = client.post(
        "/sessions",
        files={"file": ("design.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    sid = upload_resp.json()["session_id"]
    page_count = upload_resp.json()["page_count"]
    assert page_count >= 2, f"fixture must be multi-page, got page_count={page_count}"

    resp = client.get(f"/sessions/{sid}/pages/1/image")
    assert resp.status_code == 200, f"page 1 image expected 200, got {resp.status_code}: {resp.text}"
    assert resp.headers["content-type"] == "image/png", (
        f"expected image/png, got {resp.headers.get('content-type')}"
    )
    assert resp.content[:4] == b"\x89PNG", "response body is not a PNG"


def test_second_page_image_carries_metadata_headers(client, valid_pdf_bytes):
    """Page 1 image must carry all six X-... coordinate-seam headers, same as page 0.

    PREVIEW-01 requires the metadata headers for EVERY rendered page (Phase 2 reads
    them per-page for coordinate mapping). The existing header assertion only covers
    page 0.
    """
    upload_resp = client.post(
        "/sessions",
        files={"file": ("design.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = upload_resp.json()["session_id"]

    resp = client.get(f"/sessions/{sid}/pages/1/image")
    assert resp.status_code == 200

    for header in (
        "X-Page-Width-Pt",
        "X-Page-Height-Pt",
        "X-Page-Rotation",
        "X-Render-Dpi",
        "X-Image-Width-Px",
        "X-Image-Height-Px",
    ):
        assert header in resp.headers, f"page 1 missing header {header}"

    assert resp.headers["X-Render-Dpi"] == "200", (
        f"page 1 default DPI should be 200, got {resp.headers.get('X-Render-Dpi')}"
    )


def test_second_page_meta_returns_correct_page_no(client, valid_pdf_bytes):
    """GET /sessions/{id}/pages/1/meta must return page_no == 1 in the JSON body.

    The /meta endpoint is the pre-load sizing contract for PREVIEW-02 (the viewer
    calls it before the image loads to size the stage correctly for each page).
    Returning the wrong page_no would break the coordinate seam silently.
    """
    upload_resp = client.post(
        "/sessions",
        files={"file": ("design.pdf", valid_pdf_bytes, "application/pdf")},
    )
    sid = upload_resp.json()["session_id"]

    resp = client.get(f"/sessions/{sid}/pages/1/meta")
    assert resp.status_code == 200, f"page 1 meta expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["page_no"] == 1, f"expected page_no=1, got {body.get('page_no')}"
    assert body["dpi"] == 200
    assert body["page_w_pt"] > 0 and body["page_h_pt"] > 0
    assert body["img_w"] > 0 and body["img_h"] > 0


def test_last_page_of_multipage_doc_is_reachable(client, valid_pdf_bytes):
    """The last valid page index (page_count - 1) must be servable, not a 404.

    Boundary condition for PREVIEW-02: a navigator that reaches the last page must
    get a real page, not a spurious 404 from an off-by-one in the range check.
    """
    upload_resp = client.post(
        "/sessions",
        files={"file": ("design.pdf", valid_pdf_bytes, "application/pdf")},
    )
    body = upload_resp.json()
    sid = body["session_id"]
    last_page = body["page_count"] - 1  # 0-based
    assert last_page >= 1, "fixture must be multi-page"

    resp = client.get(f"/sessions/{sid}/pages/{last_page}/image")
    assert resp.status_code == 200, (
        f"last page (index {last_page}) must return 200, got {resp.status_code}"
    )
    assert resp.content[:4] == b"\x89PNG"
