"""API tests: upload, session lookup, page image + headers, meta, health, immutability."""

from __future__ import annotations

import hashlib

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
