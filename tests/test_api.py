"""API tests: upload, session lookup, page image + headers, meta, health, immutability."""

from __future__ import annotations

import hashlib

import pytest

from app import config, storage


def _upload(client, data: bytes, filename: str = "design.pdf", content_type: str = "application/pdf"):
    return client.post(
        "/sessions",
        files={"file": (filename, data, content_type)},
    )


def test_post_sessions_valid_pdf_returns_201(client, valid_pdf_bytes):
    resp = _upload(client, valid_pdf_bytes)
    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"]
    assert body["page_count"] == 2


def test_post_sessions_txt_payload_is_structured_4xx_not_500(client):
    resp = _upload(client, b"this is just text", filename="notes.txt", content_type="text/plain")
    assert resp.status_code in {415, 422}
    assert resp.status_code != 500
    detail = resp.json()["detail"]
    assert "code" in detail and "message" in detail


def test_post_sessions_oversize_returns_413_with_limit(client, monkeypatch):
    # Shrink the limit so a small payload trips the streaming guard.
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 16)
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 50)
    resp = _upload(client, b"%PDF-1.7 padded out beyond sixteen bytes for sure")
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["code"] == "file_too_large"
    assert "50" in detail["message"]


def test_post_sessions_too_many_pages_returns_413_with_limit(client, over_page_pdf_bytes):
    resp = _upload(client, over_page_pdf_bytes, filename="many.pdf")
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["code"] == "too_many_pages"
    assert "30" in detail["message"]


def test_get_session_returns_page_count(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.get(f"/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["page_count"] == 2


def test_get_unknown_session_returns_404(client):
    resp = client.get("/sessions/THIS-DOES-NOT-EXIST")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "session_not_found"


def test_get_page_image_returns_png_with_all_headers(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.get(f"/sessions/{sid}/pages/0/image")  # no dpi query
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"

    assert resp.headers["X-Render-Dpi"] == "200"
    for header in (
        "X-Page-Width-Pt",
        "X-Page-Height-Pt",
        "X-Page-Rotation",
        "X-Image-Width-Px",
        "X-Image-Height-Px",
    ):
        assert header in resp.headers, f"missing {header}"


def test_get_page_image_out_of_range_returns_404(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.get(f"/sessions/{sid}/pages/999/image")
    assert resp.status_code == 404


def test_get_page_meta_returns_pagemeta_with_default_dpi(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    resp = client.get(f"/sessions/{sid}/pages/0/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_no"] == 0
    assert body["dpi"] == 200
    assert body["page_w_pt"] > 0 and body["page_h_pt"] > 0
    assert body["img_w"] > 0 and body["img_h"] > 0
    assert body["rotation"] in {0, 90, 180, 270}


# ---- CR-01 / WR-07: path traversal on the ROUTE param that actually builds paths -------
#
# Two complementary layers:
#   (1) Single-segment crafted ids that REACH the /sessions/{session_id} handler — these
#       are the genuine attack surface for the path-build sink; the allowlist must 404 them.
#   (2) A request-handler-level probe (TestClient) that bypasses httpx URL normalization,
#       proving a raw traversal payload that arrives as one path segment is rejected.
#
# NOTE on encoded-separator forms like "..%2f..%2fwork": httpx/Starlette apply RFC-3986
# dot-segment removal to the request target BEFORE it becomes a route param, so such a URL
# never arrives at the handler AS a session_id — it either resolves to the static SPA mount
# or to no route. We assert the security property that actually matters for those: the
# response never leaks a real session payload and is never a 500. The allowlist itself is
# proven exhaustively at the storage layer (test_storage.py) and via the single-segment
# cases below, which DO reach the path-building sink.


@pytest.mark.parametrize(
    "evil_id",
    [
        "..%5c..%5cwork",  # percent-encoded backslash separators (Windows blast radius)
        "with..dots",  # contains '..' though no separator — reaches the handler
        "x" * 65,  # over the length bound
        "short",  # under the length bound
        "has space",  # alphabet violation
        "weird*chars",  # alphabet violation
    ],
)
def test_get_session_rejects_single_segment_traversal_id_as_404(client, evil_id):
    # A crafted session_id that reaches the route is rejected as a plain 404
    # (indistinguishable from a missing session) — never a 500, never a path-build.
    resp = client.get(f"/sessions/{evil_id}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "session_not_found"


@pytest.mark.parametrize(
    "evil_id",
    [
        "..%2f..%2fwork",  # percent-encoded forward-slash separators
        "%2e%2e%2f%2e%2e",  # fully percent-encoded ../..
        "..",  # bare dot-dot
        "..%5c..%5cwork",
    ],
)
def test_encoded_separator_id_is_safe_never_leaks_or_500s(client, valid_pdf_bytes, evil_id):
    # These collapse via URL normalization before reaching the handler. The security
    # property: they must NEVER return a real session JSON payload and never 500. A benign
    # static-mount 200 (serving index.html) or a 404 are both acceptable; a DATA_DIR read
    # is not.
    _upload(client, valid_pdf_bytes)  # ensure a real session exists to (not) leak
    resp = client.get(f"/sessions/{evil_id}")
    assert resp.status_code != 500, resp.text
    ctype = resp.headers.get("content-type", "")
    if resp.status_code == 200:
        # The only legitimate 200 here is the static SPA shell, not a session payload.
        assert "application/json" not in ctype, resp.text
        assert "session_id" not in resp.text
    else:
        assert resp.status_code == 404, resp.text


@pytest.mark.parametrize(
    "evil_id",
    [
        "..%5c..%5csource",
        "with..dots",
        "has space",
        "x" * 65,
    ],
)
def test_get_page_image_rejects_single_segment_traversal_id_as_404(client, evil_id):
    resp = client.get(f"/sessions/{evil_id}/pages/0/image")
    assert resp.status_code == 404, resp.text
    assert resp.status_code != 500


@pytest.mark.parametrize(
    "evil_id",
    [
        "..%5c..%5csource",
        "with..dots",
        "has space",
    ],
)
def test_get_page_meta_rejects_single_segment_traversal_id_as_404(client, evil_id):
    resp = client.get(f"/sessions/{evil_id}/pages/0/meta")
    assert resp.status_code == 404, resp.text
    assert resp.status_code != 500


def test_handler_rejects_raw_traversal_session_id(client, valid_pdf_bytes):
    # Bypass URL-path normalization: hand the route handler a raw traversal payload AS the
    # session_id (the exact untrusted-string-to-filesystem-path flow CR-01 closes). Even an
    # id with literal separators / dot-segments must be a 404, never a path-build or 500.
    import asyncio

    from fastapi import HTTPException

    from app import storage
    from app.api import sessions as sessions_api
    from app.storage import InvalidSessionId

    _upload(client, valid_pdf_bytes)  # a real session exists; the crafted id must not reach it

    for raw in ("../../originals", "..\\..\\originals", "../etc/passwd", ".."):
        # The storage sink itself rejects the crafted id...
        with pytest.raises(InvalidSessionId):
            storage.subdir("work", raw)
        # ...and the route handler turns it into a 404 (session_exists swallows the
        # InvalidSessionId -> False -> the handler's own 404), never a 500.
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(sessions_api.get_session(raw))
        assert excinfo.value.status_code == 404


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_original_unchanged_after_rendering(client, valid_pdf_bytes):
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    original = storage.original_path(sid)
    before = hashlib.sha256(original.read_bytes()).hexdigest()

    # Render every page a couple of times.
    for _ in range(2):
        for n in range(2):
            assert client.get(f"/sessions/{sid}/pages/{n}/image").status_code == 200

    after = hashlib.sha256(original.read_bytes()).hexdigest()
    assert before == after, "original must be byte-for-byte unchanged after rendering"
