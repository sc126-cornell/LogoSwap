"""Integrity unit tests: SHA-256 baseline + verify_original_hash + AGPL seam guard."""

from __future__ import annotations

import hashlib
import os
import stat
import sys

import pytest

from app import storage
from app.services import integrity


def _write_ingested(sid: str, data: bytes, *, mark_meta: bool = True) -> None:
    """Write a minimal ingested-style session: original (0o444), pristine, meta with hash."""
    storage.write_original(sid, "x.pdf", data)
    storage.write_pristine_copy(sid, data)
    if mark_meta:
        sha = integrity.compute_original_hash(data)
        storage.write_session_meta(
            sid, page_count=1, filename="x.pdf", original_sha256=sha
        )


def _rewrite_original(sid: str, new_data: bytes) -> None:
    """chmod 0o644 -> overwrite -> chmod 0o444 (cross-platform tamper simulation)."""
    p = storage.original_path(sid)
    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)  # 0o600 on POSIX, RW on Windows
    p.write_bytes(new_data)
    os.chmod(p, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def test_compute_original_hash_matches_hashlib():
    assert integrity.compute_original_hash(b"hello") == hashlib.sha256(b"hello").hexdigest()
    assert integrity.compute_original_hash(b"") == hashlib.sha256(b"").hexdigest()


def test_verify_original_hash_passes_on_unchanged_session():
    sid = storage.new_session()
    _write_ingested(sid, b"%PDF-1.7\nhello\n%%EOF")
    # Must not raise.
    integrity.verify_original_hash(sid)


def test_verify_original_hash_raises_on_tampered_original():
    sid = storage.new_session()
    _write_ingested(sid, b"%PDF-1.7\noriginal\n%%EOF")
    # Tamper the original by rewriting it (chmod-around-write).
    _rewrite_original(sid, b"%PDF-1.7\nTAMPERED\n%%EOF")
    with pytest.raises(integrity.IntegrityError) as exc:
        integrity.verify_original_hash(sid)
    assert exc.value.code == "original_tampered"
    # The .corrupted sentinel must have been written BEFORE the raise (side effect first).
    assert storage.is_session_corrupted(sid) is True


def test_verify_treats_legacy_session_as_corrupted():
    """Pitfall 4: a Phase 1–4 session with no original_sha256 field is fail-closed corrupted."""
    sid = storage.new_session()
    storage.write_original(sid, "x.pdf", b"%PDF-x\n")
    # Write meta WITHOUT original_sha256 by going through old-style helper expectations.
    # We deliberately bypass write_session_meta's signature by writing the file manually
    # to simulate the legacy session (Phase 5 deployment encounters pre-existing meta.json).
    import json as _json
    meta_path = storage.meta_path(sid)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(_json.dumps({"page_count": 1, "filename": "x.pdf"}))

    with pytest.raises(integrity.IntegrityError) as exc:
        integrity.verify_original_hash(sid)
    assert exc.value.code == "session_corrupted"
    assert storage.is_session_corrupted(sid) is True


def test_verify_treats_missing_meta_as_corrupted():
    sid = storage.new_session()
    storage.write_original(sid, "x.pdf", b"%PDF-x\n")
    # No meta.json at all — verify must fail-closed as corrupted.
    assert not storage.meta_path(sid).exists()

    with pytest.raises(integrity.IntegrityError) as exc:
        integrity.verify_original_hash(sid)
    assert exc.value.code == "session_corrupted"


def test_integrity_module_does_not_import_fitz():
    """AGPL seam guard: integrity.py must use stdlib only — no fitz import.

    Statement-level (AST) check mirroring tests/test_redact.py::
    test_fitz_import_confined_to_engine_seam — substring grep would false-positive on
    docstring references like ``no ``import fitz`` ``, so we walk the AST and look at
    actual Import / ImportFrom nodes only. This is the canonical AGPL-seam pattern in
    this codebase.
    """
    import ast
    import inspect

    src = inspect.getsource(integrity)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "fitz" and not alias.name.startswith("fitz."), (
                    f"integrity.py must not import fitz (AGPL seam); got {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module != "fitz" and not module.startswith("fitz."), (
                f"integrity.py must not import from fitz (AGPL seam); got {module}"
            )
