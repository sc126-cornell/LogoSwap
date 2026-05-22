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
    """A crafted ``../`` id AND an unknown id BOTH map to 404 logo_not_found, never 500."""
    crafted = quote("../../app/config.py", safe="")
    resp = client.get(f"/logos/{crafted}/image")
    assert resp.status_code == 404
    assert resp.status_code != 500
    assert resp.json()["detail"]["code"] == "logo_not_found"

    resp2 = client.get("/logos/does-not-exist/image")
    assert resp2.status_code == 404
    assert resp2.status_code != 500
    assert resp2.json()["detail"]["code"] == "logo_not_found"


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
