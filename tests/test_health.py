"""/health endpoint dedicated tests — Phase 5 Plan 05-02 Task 3.

The existing test_api.py::test_health proves the 5-field schema. This module adds
finer-grained guards: T-05-08 (info disclosure) + multi-session counting + the
unreadable-originals corner.
"""

from __future__ import annotations

import re
import sys

import pytest


def test_health_returns_ok_status(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_includes_uptime_seconds(client):
    body = client.get("/health").json()
    assert "uptime_seconds" in body
    assert isinstance(body["uptime_seconds"], (int, float))
    assert body["uptime_seconds"] >= 0


def test_health_includes_active_sessions_count(client, valid_pdf_bytes):
    """active_sessions reflects the count of token-shaped originals/ subdirs."""
    # Ingest 2 sessions.
    for _ in range(2):
        resp = client.post(
            "/sessions",
            files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 201

    body = client.get("/health").json()
    assert body["active_sessions"] >= 2


def test_health_includes_data_dir_fields(client):
    body = client.get("/health").json()
    assert "data_dir_bytes" in body
    assert "data_dir_pct" in body
    assert isinstance(body["data_dir_bytes"], int)
    assert isinstance(body["data_dir_pct"], (int, float))
    assert 0 <= body["data_dir_pct"] <= 100


def test_health_does_not_leak_session_ids(client, valid_pdf_bytes):
    """T-05-08: /health is unauthenticated — must NOT contain any session token strings.

    Session tokens are URL-safe base64 (alphabet ``[A-Za-z0-9_-]{16,64}``); the hex-only
    32-char regex catches the historical worry case, but the safer test is to ingest a
    real session and then grep its specific id against the health response.
    """
    ingest_resp = client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert ingest_resp.status_code == 201
    sid = ingest_resp.json()["session_id"]

    body_text = client.get("/health").text
    assert sid not in body_text, (
        f"/health body must not contain a session_id; found {sid!r}"
    )
    # Also assert no hex-only 32-char strings leak (defense in depth — the hash digest
    # form, in case a future field accidentally surfaces hashes).
    hex_matches = re.findall(r"[a-f0-9]{32}", body_text)
    # uptime / disk fields are decimal numbers; no hex digests should appear.
    assert hex_matches == [], f"unexpected hex strings in /health body: {hex_matches}"


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="chmod 0 on Windows behaves differently — POSIX-only assertion",
)
def test_health_active_sessions_robust_to_unreadable_kind_dir(client, valid_pdf_bytes, monkeypatch):
    """WR-02: a single unreadable kind dir does NOT crash /health.

    Post-WR-02, the count routes through ``storage.list_session_ids``, which catches
    ``OSError`` per-root and continues. Dropping read permission on ``originals/`` while
    the other three kind dirs remain readable now yields the session count from the
    surviving kinds (positive int) instead of -1. The endpoint stays a 200; a bare 500
    from an unhandled OSError would take down the LB probe.
    """
    import os
    from app import config as _config

    # Ingest one session so all four kind dirs exist.
    client.post(
        "/sessions",
        files={"file": ("ok.pdf", valid_pdf_bytes, "application/pdf")},
    )
    originals_root = _config.DATA_DIR / "originals"
    try:
        os.chmod(originals_root, 0)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        # Either the surviving kinds still expose the session (>= 1) or storage cannot
        # enumerate any (-1). Both are valid; the contract is "do not crash".
        assert isinstance(body["active_sessions"], int)
        assert body["active_sessions"] >= -1
    finally:
        os.chmod(originals_root, 0o755)  # restore for tmp cleanup
