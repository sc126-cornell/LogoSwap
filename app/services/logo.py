"""Fixed read-only logo-library service (Phase 3, LOGO-01) — fitz-free.

This module loads/validates ``logos/manifest.json`` and resolves an untrusted ``logo_id``
to validated PNG bytes. It imports ONLY ``json``/``re``/``pathlib``/``PIL`` and ``config`` —
NEVER ``fitz`` — so the AGPL isolation seam stays in ``pdf_engine.py`` (threat T-02-03,
enforced by ``test_fitz_import_confined_to_engine_seam``).

The load-bearing security property (T-03-01, mirrors ``storage.validate_session_id``/``subdir``):
an untrusted ``logo_id`` is ONLY ever a key into the parsed manifest dict — never a path
segment. The manifest entry's admin-controlled bare ``file`` basename is what joins to
``LOGOS_DIR``, guarded by an ``is_relative_to(LOGOS_DIR)`` containment assert. An unknown id
yields a 404 ``logo_not_found`` (no oracle), exactly like ``session_not_found``. We NEVER build
``LOGOS_DIR / logo_id`` (Pitfall 3 / Anti-Pattern).

A bad/oversized/corrupt asset is SKIPPED from ``list_logos`` (per-asset try/except) rather than
crashing the catalog (T-03-02 / T-03-03 / Pitfall 6); an absent/empty/unparseable manifest
yields ``{}`` so the picker degrades to an empty state, never a 500 (A2).
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .. import config


class LogoError(Exception):
    """Typed logo failure carrying a stable ``code`` (mirrors ``RenderError``).

    Codes: ``logo_not_found`` (unknown/crafted id -> 404, no oracle); ``logo_unreadable`` /
    ``logo_invalid`` (corrupt/undecodable asset -> 422). Mapped to a structured 4xx in
    ``main.py`` so a bad id/asset never escapes as a bare 500 (T-02-08 / T-03-03).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _logos_dir() -> Path:
    """Resolve LOGOS_DIR at call time so tests can monkeypatch config.LOGOS_DIR."""
    return Path(config.LOGOS_DIR)


def _load_manifest() -> dict:
    """Parse ``<LOGOS_DIR>/manifest.json`` into a dict keyed by ``id``.

    An absent/empty/unparseable manifest (or a non-list / malformed shape) yields ``{}`` —
    the picker shows an empty state, never a 500 (A2; mirrors ``read_session_meta``).
    """
    path = _logos_dir() / "manifest.json"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return {}
    if not isinstance(data, list):
        return {}
    by_id: dict = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        logo_id = entry.get("id")
        file_name = entry.get("file")
        if not isinstance(logo_id, str) or not isinstance(file_name, str):
            continue
        by_id[logo_id] = entry
    return by_id


def _resolve_path(entry: dict) -> Path:
    """Join the admin-controlled ``entry["file"]`` to LOGOS_DIR with a containment assert.

    Defense-in-depth (T-03-01): even though ``file`` is admin-controlled, the resolved path
    must remain under LOGOS_DIR; otherwise raise ``logo_not_found`` (no oracle). This mirrors
    ``storage.subdir``'s ``is_relative_to`` guard.
    """
    logos_dir = _logos_dir()
    path = (logos_dir / entry["file"]).resolve()
    if not path.is_relative_to(logos_dir.resolve()):
        raise LogoError("logo_not_found", "找不到所選商標。")
    return path


def _validate_png(path: Path) -> None:
    """Confirm ``path`` is a decodable PNG within the size cap; else raise LogoError.

    File-size cap (T-03-02) is checked BEFORE decode. The decoded format MUST be PNG (WR-04 /
    D-03 "PNG 去背 with alpha"): the image endpoint serves the bytes with a hardcoded
    ``media_type="image/png"`` and ``place_logo`` embeds them as PNG, so a JPEG/GIF/TIFF that
    merely happens to decode would make the served Content-Type a lie and feed the wrong
    assumptions into placement. We therefore reject any non-PNG with ``logo_invalid``. Pillow
    ``verify()`` rejects a corrupt file and (via ``Image.MAX_IMAGE_PIXELS``) a decompression
    bomb. Raises ``logo_unreadable`` on any decode failure so the caller can skip (list) or
    surface a 422 (resolve).

    Note: ``verify()`` invalidates the image object, so we read ``.format`` BEFORE calling it.
    """
    try:
        size = path.stat().st_size
    except OSError as err:
        raise LogoError("logo_unreadable", "商標檔案無法讀取。") from err
    if size > config.MAX_LOGO_BYTES:
        raise LogoError("logo_invalid", "商標檔案過大。")
    try:
        with Image.open(path) as img:
            fmt = img.format
            if fmt != "PNG":
                raise LogoError("logo_invalid", "商標檔案必須為 PNG 格式。")
            img.verify()
    except LogoError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as err:
        raise LogoError("logo_unreadable", "商標檔案無法讀取。") from err


def _public_entry(entry: dict) -> dict:
    """Project a manifest entry into the client-facing shape — NEVER the path/file key.

    Returns ``{id, name, tags}`` only; the ``file`` basename and any filesystem path stay
    server-side (no path leak to the picker).
    """
    return {
        "id": entry["id"],
        "name": entry.get("name", entry["id"]),
        "tags": list(entry.get("tags", [])) if isinstance(entry.get("tags"), list) else [],
    }


def list_logos() -> list[dict]:
    """List valid library entries as ``[{id, name, tags}]`` (LOGO-01).

    An entry whose file is missing, oversized, or fails Pillow validation is SKIPPED (per-asset
    try/except) rather than failing the whole list (T-03-02/03 / Pitfall 6). Never returns a
    filesystem path or the raw ``file`` key.
    """
    out: list[dict] = []
    for entry in _load_manifest().values():
        try:
            path = _resolve_path(entry)
            if not path.is_file():
                continue
            _validate_png(path)
        except LogoError:
            continue
        out.append(_public_entry(entry))
    return out


def resolve(logo_id: str) -> bytes:
    """Resolve ``logo_id`` (a manifest dict key) to validated PNG bytes.

    1. ``manifest.get(logo_id)`` -> ``None`` raises ``logo_not_found`` (404, no oracle).
    2. Join the admin-controlled ``file`` basename to LOGOS_DIR with an ``is_relative_to``
       containment assert (T-03-01). NEVER ``LOGOS_DIR / logo_id``.
    3. Validate the bytes via Pillow; a decode failure raises ``logo_unreadable`` (422).
    """
    entry = _load_manifest().get(logo_id)
    if entry is None:
        raise LogoError("logo_not_found", "找不到所選商標。")
    path = _resolve_path(entry)
    if not path.is_file():
        raise LogoError("logo_not_found", "找不到所選商標。")
    _validate_png(path)
    try:
        return path.read_bytes()
    except OSError as err:
        raise LogoError("logo_unreadable", "商標檔案無法讀取。") from err
