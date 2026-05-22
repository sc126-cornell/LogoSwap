"""Storage unit tests: three-dir layout, write-once read-only original, sanitization."""

from __future__ import annotations

import os

import pytest

from app import config, storage


def test_new_session_creates_exactly_three_dirs():
    sid = storage.new_session()
    assert isinstance(sid, str) and sid

    originals = config.DATA_DIR / "originals" / sid
    work = config.DATA_DIR / "work" / sid
    outputs = config.DATA_DIR / "outputs" / sid

    assert originals.is_dir()
    assert work.is_dir()
    assert outputs.is_dir()


def test_write_original_round_trips_bytes():
    sid = storage.new_session()
    data = b"%PDF-1.7\nhello world bytes\n%%EOF"
    path = storage.write_original(sid, "x.pdf", data)

    assert path == storage.original_path(sid)
    assert path.read_bytes() == data
    # Stored under originals/{sid}.
    assert path.parent == config.DATA_DIR / "originals" / sid


def test_write_original_is_read_only_after_write():
    sid = storage.new_session()
    path = storage.write_original(sid, "x.pdf", b"%PDF-1.7\n%%EOF")

    mode = os.stat(path).st_mode
    # Owner write bit must be off (0o444 write-once guarantee).
    assert not (mode & 0o200), f"original should not be writable, mode={oct(mode)}"


@pytest.mark.parametrize(
    "evil",
    [
        "../../etc/passwd",
        "a/b\\c.pdf",
        "..\\..\\windows\\system32\\evil.dll",
        "/abs/path/secret.pdf",
    ],
)
def test_sanitize_filename_strips_separators_and_dotdot(evil):
    safe = storage.sanitize_filename(evil)
    assert "/" not in safe
    assert "\\" not in safe
    assert ".." not in safe


def test_sanitize_filename_falls_back_when_empty():
    assert storage.sanitize_filename("") == "upload.pdf"
    assert storage.sanitize_filename(None) == "upload.pdf"
    assert storage.sanitize_filename("..") == "upload.pdf"


def test_work_path_differs_from_original_and_lives_under_work():
    sid = storage.new_session()
    work = storage.work_path(sid)
    original = storage.original_path(sid)

    assert work != original
    assert work.parent == config.DATA_DIR / "work" / sid


def test_session_exists_reflects_work_copy():
    sid = storage.new_session()
    assert storage.session_exists(sid) is False
    storage.write_work_copy(sid, b"%PDF-1.7\n%%EOF")
    assert storage.session_exists(sid) is True
    assert storage.session_exists("does-not-exist") is False
