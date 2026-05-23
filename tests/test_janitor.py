"""Janitor unit tests: TTL sweep + max-mtime + cross-platform chmod + race + non-token-dir."""

from __future__ import annotations

import os
import stat
import sys
import time

import pytest

from app import config, storage
from app.services import janitor


def _backdate_all_kinds(sid: str, age_seconds: float) -> None:
    """Set mtime/atime on every kind dir for ``sid`` to now - age_seconds."""
    target = time.time() - age_seconds
    for kind in ("originals", "work", "outputs", "pristine"):
        path = config.DATA_DIR / kind / sid
        if path.exists():
            os.utime(path, (target, target))


def test_janitor_sweeps_expired_session():
    """A session whose max-mtime is older than TTL is deleted from all four kinds."""
    sid = storage.new_session()
    storage.write_original(sid, "x.pdf", b"%PDF-1.7\n%%EOF")
    storage.write_work_copy(sid, b"%PDF-1.7\n%%EOF")
    _backdate_all_kinds(sid, 3700)  # > 3600s TTL

    deleted = janitor.sweep_expired_sessions()
    assert deleted >= 1
    for kind in ("originals", "work", "outputs", "pristine"):
        assert not (config.DATA_DIR / kind / sid).exists(), (
            f"{kind}/{sid} should be gone after sweep"
        )


def test_janitor_keeps_active_session_under_ttl():
    """A fresh session (mtime ~= now) survives a sweep untouched."""
    sid = storage.new_session()
    storage.write_original(sid, "x.pdf", b"%PDF-1.7\n%%EOF")
    deleted = janitor.sweep_expired_sessions()
    assert deleted == 0
    for kind in ("originals", "work", "outputs", "pristine"):
        assert (config.DATA_DIR / kind / sid).is_dir(), (
            f"{kind}/{sid} must survive sweep for an active session"
        )


def test_janitor_max_mtime_protects_recent_outputs():
    """An old originals/ dir + a NEW outputs/ dir → max-mtime wins → not deleted.

    Repro of the "outputs just downloaded but originals is hours old" race-avoidance
    rule: session_age_seconds uses MAX mtime so a fresh output protects the session.
    """
    sid = storage.new_session()
    storage.write_original(sid, "x.pdf", b"%PDF-1.7\n%%EOF")

    now = time.time()
    # originals backdated to 9000s ago, outputs touched to 100s ago
    os.utime(config.DATA_DIR / "originals" / sid, (now - 9000, now - 9000))
    os.utime(config.DATA_DIR / "outputs" / sid, (now - 100, now - 100))

    deleted = janitor.sweep_expired_sessions()
    assert deleted == 0
    assert (config.DATA_DIR / "originals" / sid).is_dir()
    assert (config.DATA_DIR / "outputs" / sid).is_dir()


def test_janitor_handles_chmod_0o444_originals_cross_platform():
    """write_original chmods 0o444 — sweep must still rmtree it (Pitfall 3).

    On Windows os.unlink against a 0o444 file raises PermissionError; the shared
    _on_rm_error in storage.py re-chmods to 0o644 and retries. POSIX usually succeeds
    regardless of file mode. Either way the dir must be gone after sweep.
    """
    sid = storage.new_session()
    storage.write_original(sid, "x.pdf", b"%PDF-1.7\n%%EOF")
    p = storage.original_path(sid)
    assert not (os.stat(p).st_mode & 0o200), "test prereq: original must be 0o444"
    _backdate_all_kinds(sid, 3700)

    deleted = janitor.sweep_expired_sessions()
    assert deleted >= 1
    assert not (config.DATA_DIR / "originals" / sid).exists()


def test_janitor_returns_zero_on_no_sessions():
    """Empty data dir → sweep returns 0, never raises."""
    # No new_session calls in this test — the data dir is empty (autouse fixture).
    assert janitor.sweep_expired_sessions() == 0


def test_janitor_skips_non_token_dir_names():
    """A dir whose name fails _SESSION_ID_RE is ignored (defense in depth, T-05-07)."""
    # Manually create a stray dir under work/ with a non-token name
    (config.DATA_DIR / "work").mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "work" / "not_a_token").mkdir(parents=True, exist_ok=True)
    # Backdate it so age > TTL — if janitor wrongly picked it up, it would try to delete
    now = time.time()
    os.utime(config.DATA_DIR / "work" / "not_a_token", (now - 9000, now - 9000))

    deleted = janitor.sweep_expired_sessions()
    assert deleted == 0
    # The stray dir is still present — janitor did NOT touch it
    assert (config.DATA_DIR / "work" / "not_a_token").is_dir()


def test_janitor_failure_does_not_raise(monkeypatch):
    """If an internal rmtree fails for one session, sweep logs and continues — never raises."""
    sid = storage.new_session()
    _backdate_all_kinds(sid, 3700)

    # Force delete_session to raise the first time it's called
    real_delete = storage.delete_session
    calls = {"n": 0}

    def maybe_raise(s):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated rmtree failure")
        real_delete(s)

    monkeypatch.setattr("app.services.janitor.storage.delete_session", maybe_raise)
    # Must not raise
    result = janitor.sweep_expired_sessions()
    assert isinstance(result, int)
    assert result >= 0


def test_janitor_module_does_not_import_fitz():
    """AGPL seam: janitor.py must use stdlib + storage only — no fitz."""
    import ast
    import inspect

    src = inspect.getsource(janitor)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "fitz" and not alias.name.startswith("fitz."), (
                    f"janitor.py must not import fitz; got {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module != "fitz" and not module.startswith("fitz."), (
                f"janitor.py must not import from fitz; got {module}"
            )
