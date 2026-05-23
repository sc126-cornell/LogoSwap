"""Storage unit tests: three-dir layout, write-once read-only original, sanitization."""

from __future__ import annotations

import json
import os
import secrets
import time

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
    assert storage.session_exists("aaaaaaaaaaaaaaaa") is False  # valid shape, no such session


# ---- CR-01: session_id path-traversal guard (the string that ACTUALLY builds paths) ----


@pytest.mark.parametrize(
    "evil",
    [
        "../escape",
        "..\\escape",
        "../../etc/passwd",
        "..%2f..%2fwork",  # percent-encoded separators (decoded form would traverse)
        "a/b",
        "a\\b",
        "/abs/path",
        "with space",
        "dotdot..token",  # contains '..' even though no separator
        "tab\tchar",
        "",  # empty
        ".",
        "..",
        "short",  # below the 16-char minimum
        "x" * 65,  # above the 64-char maximum
        "valid_but_has_a_slash/",  # trailing separator
    ],
)
def test_subdir_rejects_non_token_session_id(evil):
    # subdir() is the single sink for the path-build; a non-token id must never reach disk.
    with pytest.raises(storage.InvalidSessionId):
        storage.subdir("work", evil)


def test_subdir_rejects_via_all_path_helpers():
    # Every public path helper routes through subdir(), so each must reject a traversal id.
    for fn in (storage.original_path, storage.work_path, storage.outputs_dir):
        with pytest.raises(storage.InvalidSessionId):
            fn("../../escape")


@pytest.mark.parametrize(
    "good",
    [
        secrets.token_urlsafe(16),
        secrets.token_urlsafe(32),
        "abcdefghij1234567890",  # 20 chars, plain alnum
        "with-dash_and_underscore-0",
        "a" * 16,  # exactly at the lower bound
        "a" * 64,  # exactly at the upper bound
    ],
)
def test_subdir_accepts_server_token_shape(good):
    # A genuine token-shaped id resolves to <DATA_DIR>/work/<id> and is contained.
    path = storage.subdir("work", good)
    assert path == config.DATA_DIR / "work" / good
    assert path.resolve().is_relative_to(config.DATA_DIR.resolve())


def test_session_exists_false_for_traversal_id():
    # The route gate must report a crafted id as "not present" rather than raising.
    assert storage.session_exists("../../etc/passwd") is False
    assert storage.session_exists("..%2f..%2fwork") is False


# ---- Phase 5 Plan 05-02 Task 1: atomic meta + 5 helpers + Pitfall 3 chmod cross-platform ----


def test_write_session_meta_includes_original_sha256():
    sid = storage.new_session()
    sha = "a" * 64  # 64-char hex placeholder
    storage.write_session_meta(
        sid, page_count=3, filename="x.pdf", original_sha256=sha
    )
    meta = storage.read_session_meta(sid)
    assert meta is not None
    assert meta["page_count"] == 3
    assert meta["filename"] == "x.pdf"
    assert meta["original_sha256"] == sha


def test_write_session_meta_is_atomic_on_simulated_crash(monkeypatch):
    """A partial json.dump that raises mid-write must leave NO partial file at dest.

    Verifies the tempfile.mkstemp + os.replace pattern: if the write fails, the original
    dest (none in this case) stays absent and no stray .tmp.* file is left behind.
    """
    sid = storage.new_session()
    dest = storage.meta_path(sid)
    assert not dest.exists()

    real_dump = json.dump

    def failing_dump(obj, fh, *a, **kw):
        fh.write('{"page_count": 1')  # partial
        raise OSError("simulated disk-full")

    monkeypatch.setattr("app.storage.json.dump", failing_dump)
    with pytest.raises(OSError):
        storage.write_session_meta(
            sid, page_count=1, filename="x.pdf", original_sha256="a" * 64
        )
    # dest never created (os.replace was never reached)
    assert not dest.exists()
    # tmp files cleaned up
    leftovers = [p for p in dest.parent.iterdir() if ".meta." in p.name and p.name.endswith(".tmp")]
    assert leftovers == [], f"stray tmp files: {leftovers}"


def test_list_session_ids_unions_across_kinds():
    sid_a = storage.new_session()  # creates all 4 kinds
    sid_b = storage.new_session()
    # Add a stray non-token dir under work — must NOT appear in the iterator.
    # "short" is below the 16-char minimum so _SESSION_ID_RE rejects it.
    (config.DATA_DIR / "work" / "short").mkdir(parents=True, exist_ok=True)
    ids = set(storage.list_session_ids())
    assert sid_a in ids
    assert sid_b in ids
    assert "short" not in ids


def test_session_age_seconds_uses_max_mtime():
    sid = storage.new_session()
    storage.write_original(sid, "x.pdf", b"%PDF-1.7\n%%EOF")
    storage.write_work_copy(sid, b"%PDF-1.7\n%%EOF")
    now = time.time()
    # originals dir set to 9000s ago, outputs dir set to now → max-mtime is now → age ~= 0
    os.utime(config.DATA_DIR / "originals" / sid, (now - 9000, now - 9000))
    os.utime(config.DATA_DIR / "outputs" / sid, (now, now))
    age = storage.session_age_seconds(sid)
    assert age is not None
    assert age < 60, f"expected near-zero age (max mtime is now), got {age}"


def test_session_age_seconds_none_for_unknown_session():
    # A token-shaped id that has no on-disk dirs returns None.
    assert storage.session_age_seconds("aaaaaaaaaaaaaaaa") is None


def test_delete_session_removes_all_four_kinds():
    sid = storage.new_session()
    storage.write_work_copy(sid, b"%PDF-x\n")
    storage.write_pristine_copy(sid, b"%PDF-x\n")
    # outputs dir is created by new_session; originals dir too — write a file to make it non-empty.
    storage.write_original(sid, "x.pdf", b"%PDF-x\n")
    (storage.outputs_dir(sid) / "result.pdf").write_bytes(b"%PDF-out\n")

    # All 4 kinds present before delete
    for kind in ("originals", "work", "outputs", "pristine"):
        assert (config.DATA_DIR / kind / sid).is_dir()

    storage.delete_session(sid)
    for kind in ("originals", "work", "outputs", "pristine"):
        assert not (config.DATA_DIR / kind / sid).exists(), f"{kind}/{sid} still exists"


def test_delete_session_handles_readonly_original():
    """Pitfall 3: write_original chmods 0o444 — delete_session must still rmtree it.

    Cross-platform: on Windows, os.unlink on a 0o444 file raises PermissionError; on POSIX
    the dir mode controls deletion so it usually succeeds, but the _on_rm_error handler
    must keep both platforms green.
    """
    sid = storage.new_session()
    storage.write_original(sid, "x.pdf", b"%PDF-readonly\n")
    # confirm originals is read-only
    p = storage.original_path(sid)
    assert not (os.stat(p).st_mode & 0o200), "test prereq: original must be read-only"

    storage.delete_session(sid)
    assert not (config.DATA_DIR / "originals" / sid).exists()


def test_mark_and_is_session_corrupted_round_trip():
    sid = storage.new_session()
    assert storage.is_session_corrupted(sid) is False
    storage.mark_session_corrupted(sid)
    assert storage.is_session_corrupted(sid) is True


def test_is_session_corrupted_rejects_invalid_session_id():
    # InvalidSessionId must be swallowed and reported as False (no traceback leak).
    assert storage.is_session_corrupted("../../etc") is False
    assert storage.is_session_corrupted("has space") is False
    assert storage.is_session_corrupted("") is False
