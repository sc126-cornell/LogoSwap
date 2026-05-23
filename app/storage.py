"""Filesystem storage: three-directory session layout + write-once original.

The originals/work/outputs separation makes accidental mutation of the uploaded source
*structurally* impossible (UPLOAD-04, threat T-01-05, Anti-Pattern 3): the original is
written exactly once and chmod'd read-only; all later processing touches only the
``work/`` copy; generated PDFs land in ``outputs/``.

The client-supplied filename is NEVER used as a filesystem path component (threat
T-01-04 / path traversal): the session directory name is a server-generated
``secrets.token_urlsafe`` token, and the stored filename is sanitized to a bare
basename.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import stat
import tempfile
import time
from pathlib import Path
from typing import Iterator

from . import config

logger = logging.getLogger(__name__)

# Subdirectory kinds under DATA_DIR.
#
# Phase 4: ``pristine`` is the immutable post-ingest PDF snapshot that the pipeline
# reset-from-pristine step copies into ``work/`` at every /process run. For PDF
# uploads it is byte-identical to ``originals/source.pdf``; for image uploads
# (PNG/JPG/TIFF, UPLOAD-03) the user's raw image bytes live in ``originals/`` while
# ``pristine/`` holds the normalized A4 PDF — so the reset step never has to open a
# non-PDF stream as a PDF (which would crash). originals/ stays SHA-256-invariant
# (D-05) because pipeline no longer touches it.
_KINDS = ("originals", "work", "outputs", "pristine")

# A session id is ALWAYS a server-issued ``secrets.token_urlsafe`` token, whose alphabet
# is URL-safe base64: A-Z a-z 0-9 plus ``-`` and ``_`` (no padding). ``token_urlsafe(16)``
# yields 22 chars; we allow a generous 16-64 range so the bound is not brittle. Validating
# against this exact alphabet BEFORE the id becomes a path segment (threat T-01-04 / path
# traversal) is what makes ``subdir`` safe: percent-decoded separators (``%2F``/``%5C``),
# dot segments (``..``), and absolute-style prefixes can never match and so can never reach
# the filesystem. This closes the gap the threat model claimed (but did not) cover: the
# untrusted string that actually builds paths is ``session_id``, not the client filename.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class InvalidSessionId(ValueError):
    """Raised when a caller-supplied session id is not a server-issued token shape.

    Subclasses :class:`ValueError` for backward compatibility (callers that already catch
    ``ValueError`` keep working) but is a distinct type so the API layer can map a crafted
    id to a 404 — indistinguishable from a missing session — rather than a 500.
    """


def validate_session_id(session_id: str) -> str:
    """Return ``session_id`` if it matches the server-token alphabet, else raise.

    The single chokepoint for the path-traversal guard: every path-building helper routes
    through here (via :func:`subdir`), so no untrusted id can become a path segment.
    """
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        raise InvalidSessionId(f"invalid session id: {session_id!r}")
    return session_id

# Fixed on-disk name for the immutable original and the editable work copy. The
# client filename is stored in SessionInfo, not used on disk.
_ORIGINAL_NAME = "source.pdf"
_WORK_NAME = "doc.pdf"
# Phase 4: pristine PDF snapshot used as the pipeline's reset-from-pristine source.
# Same basename as the work copy (doc.pdf) but under a separate ``pristine/`` subdir,
# so the pristine and work paths are structurally distinct (the pipeline asserts this).
_PRISTINE_NAME = "doc.pdf"
# Tiny per-session sidecar holding metadata determined ONCE at ingest (page count,
# original display filename) so the hot GET /sessions/{id} lookup never re-parses the
# PDF and never mislabels a storage/read failure as a client "corrupt_pdf" (WR-03).
_META_NAME = "meta.json"


def _data_dir() -> Path:
    """Resolve DATA_DIR at call time so tests can monkeypatch config.DATA_DIR."""
    return Path(config.DATA_DIR)


def subdir(kind: str, session_id: str) -> Path:
    """Path to ``<DATA_DIR>/<kind>/<session_id>`` (not created).

    ``session_id`` is validated against the server-token alphabet before it becomes a
    path segment (threat T-01-04). As defense-in-depth, the resolved path is asserted to
    stay within ``DATA_DIR`` so even an unforeseen bypass cannot escape the data root.
    """
    if kind not in _KINDS:
        raise ValueError(f"unknown storage kind: {kind!r}")
    validate_session_id(session_id)
    data_dir = _data_dir()
    dest = data_dir / kind / session_id
    # Defense-in-depth containment: the resolved path must remain under DATA_DIR.
    resolved = dest.resolve()
    if not resolved.is_relative_to(data_dir.resolve()):
        raise InvalidSessionId(f"invalid session id: {session_id!r}")
    return dest


def new_session() -> str:
    """Create a new session and its three directories; return the session id.

    The id is a 128-bit unguessable token (threat T-01-07), not a sequential
    counter, so one LAN user cannot enumerate another's session.
    """
    session_id = secrets.token_urlsafe(16)
    for kind in _KINDS:
        subdir(kind, session_id).mkdir(parents=True, exist_ok=True)
    return session_id


def sanitize_filename(name: str | None) -> str:
    """Reduce a client filename to a safe bare basename.

    Strips directory components (handles both ``/`` and ``\\``), rejects ``..``
    traversal, and falls back to ``upload.pdf`` when nothing safe remains. The result
    is only ever used as a *display* value and a stored field — never as a path.
    """
    if not name:
        return "upload.pdf"
    # Normalize Windows separators then take the basename, defeating "a/b\\c.pdf".
    candidate = os.path.basename(name.replace("\\", "/"))
    # Strip any residual traversal tokens / stray separators.
    candidate = candidate.replace("..", "").strip().strip("/\\").strip()
    if not candidate or candidate in {".", ".."}:
        return "upload.pdf"
    return candidate


def original_path(session_id: str) -> Path:
    """Path to the immutable original PDF for a session."""
    return subdir("originals", session_id) / _ORIGINAL_NAME


def work_path(session_id: str) -> Path:
    """Path to the editable work-copy PDF for a session (distinct from the original)."""
    return subdir("work", session_id) / _WORK_NAME


def pristine_path(session_id: str) -> Path:
    """Path to the immutable post-ingest PDF snapshot used as the reset-from-pristine source.

    For a PDF upload, this is byte-identical to :func:`original_path`. For an image
    upload (Phase 4 UPLOAD-03), ``originals/`` stores the user's raw image bytes
    (PNG/JPG/TIFF) — those are NOT a PDF, so the pipeline cannot reset its work copy
    from them directly. We therefore write a normalized A4 PDF here at ingest time
    and the pipeline reads THIS path for the reset, so the D-05 SHA-256 invariant on
    ``originals/`` stays intact (the pipeline no longer touches originals/).
    """
    return subdir("pristine", session_id) / _PRISTINE_NAME


def outputs_dir(session_id: str) -> Path:
    """Directory reserved for generated output PDFs (Phase 2+)."""
    return subdir("outputs", session_id)


def meta_path(session_id: str) -> Path:
    """Path to the per-session metadata sidecar (under ``work/``)."""
    return subdir("work", session_id) / _META_NAME


def write_session_meta(
    session_id: str,
    *,
    page_count: int,
    filename: str,
    original_sha256: str,
) -> Path:
    """Persist ingest-time metadata as ``work/{sid}/meta.json`` atomically.

    Phase 5 (D-C1): ``original_sha256`` is REQUIRED — the SHA-256 baseline for the
    user's uploaded bytes, written in the same transaction as page_count/filename so
    a mid-write crash cannot leave a meta without a baseline. The atomic primitive
    is ``tempfile.mkstemp(dir=dest.parent)`` + ``os.replace``: the tmp file is forced
    onto the same filesystem as the destination (A7 — os.replace is only atomic
    intra-FS), and a partial write never becomes visible at the dest path.

    On failure the tmp file is unlinked; on success ``os.replace`` does the rename.
    The work dir already exists from :func:`new_session`.
    """
    dest = meta_path(session_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "page_count": int(page_count),
        "filename": str(filename),
        "original_sha256": str(original_sha256),
    }
    fd, tmp_path = tempfile.mkstemp(
        prefix=".meta.", suffix=".json.tmp", dir=str(dest.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp_path, dest)
    except BaseException:
        # Clean up the tmp so a failure leaves no .meta.*.tmp orphan behind. The dest
        # is either still its prior content (atomic) or absent (first write).
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return dest


def read_session_meta(session_id: str) -> dict | None:
    """Return the per-session metadata sidecar, or ``None`` if missing/unreadable.

    Callers treat ``None`` as "sidecar unavailable" and may fall back (e.g. a one-time
    re-parse) — but a parse there must NOT be reported as the client-facing ``corrupt_pdf``.
    """
    path = meta_path(session_id)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return None
    if not isinstance(data, dict) or "page_count" not in data:
        return None
    return data


def write_original(session_id: str, filename: str, data: bytes) -> Path:
    """Write the uploaded bytes once under ``originals/`` and set them read-only.

    ``filename`` is sanitized and recorded for reference but does NOT determine the
    on-disk path. After writing, the file mode is set to 0o444 so a later bug cannot
    silently mutate the source of truth (UPLOAD-04 / T-01-05).
    """
    # Sanitize even though we use a fixed on-disk name — defense in depth + record.
    sanitize_filename(filename)
    dest = original_path(session_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(data)
    # Make the original read-only (write-once guarantee).
    os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444
    return dest


def write_work_copy(session_id: str, data: bytes) -> Path:
    """Write the editable work copy under ``work/`` (stays writable)."""
    dest = work_path(session_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest


def write_pristine_copy(session_id: str, data: bytes) -> Path:
    """Write the pristine post-ingest PDF snapshot under ``pristine/`` (Phase 4).

    The pipeline reads this path to reset the work copy at the start of every /process
    run (WR-01 / deferred-mutation D-05). For PDF uploads ``data`` is byte-identical to
    what was written under ``originals/``; for image uploads (UPLOAD-03) ``data`` is
    the normalized A4 PDF produced by :func:`pdf_engine.image_to_a4_pdf`.
    """
    dest = pristine_path(session_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest


def session_exists(session_id: str) -> bool:
    """True when the session's work copy exists (the canonical 'session present' test).

    A session id that fails validation (i.e. is not a server-issued token) can never name
    a real session, so we return ``False`` rather than letting :class:`InvalidSessionId`
    propagate — the route then returns a 404, making a crafted id indistinguishable from a
    missing one (no oracle, no path-traversal sink reached).
    """
    try:
        return work_path(session_id).is_file()
    except InvalidSessionId:
        return False


# ---- Phase 5 (Plan 05-02): janitor + integrity helpers ----------------------------------
#
# All helpers route through :func:`subdir` for the path-traversal allowlist (T-05-07).
# The `_on_rm_error` handler is shared with :mod:`app.services.janitor` (it imports this
# symbol) so the Pitfall 3 cross-platform fix lives in exactly one place.

# Phase 5 sentinel filename — placed under work/{sid}/ when a session is detected as
# corrupted (integrity verify failure). Hyphen-prefix avoids colliding with the JSON
# sidecar's `.meta.*.tmp` namespace.
_CORRUPTED_NAME = ".corrupted"


def _on_rm_error(func, path, exc_info) -> None:
    """``shutil.rmtree`` error handler — re-chmod 0o444 → retry (Pitfall 3, cross-platform).

    On Windows, ``os.unlink`` on a file with mode 0o444 raises ``PermissionError`` because
    the file lacks the "write" attribute. POSIX ``unlink`` is governed by the DIRECTORY
    mode and usually succeeds regardless of the file mode, but defending both keeps a
    single implementation working in CI on either platform. We only treat unlink/rmdir/
    remove failures as recoverable; anything else is logged + swallowed (the janitor /
    delete_session contract is "best-effort cleanup, never raise").
    """
    if exc_info and isinstance(exc_info[1], PermissionError) and func in (
        os.unlink,
        os.remove,
        os.rmdir,
    ):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)
            return
        except OSError as err:
            logger.warning("rmtree retry failed for %s: %s", path, err)
            return
    logger.warning(
        "rmtree error on %s (func=%s): %s",
        path,
        getattr(func, "__name__", func),
        exc_info[1] if exc_info else None,
    )


def list_session_ids() -> Iterator[str]:
    """Yield every well-formed session id present under any of the four kind dirs.

    Used by :mod:`app.services.janitor` (it needs the union across kinds because a job
    can leave artifacts in any subset). Names that fail :data:`_SESSION_ID_RE` are
    skipped — defense in depth against an admin/test creating a stray dir.
    """
    data_dir = _data_dir()
    seen: set[str] = set()
    for kind in _KINDS:
        root = data_dir / kind
        if not root.is_dir():
            continue
        try:
            for entry in root.iterdir():
                name = entry.name
                if name in seen:
                    continue
                if entry.is_dir() and _SESSION_ID_RE.fullmatch(name):
                    seen.add(name)
                    yield name
        except OSError as err:
            logger.warning("list_session_ids: failed under %s: %s", root, err)


def session_age_seconds(session_id: str) -> float | None:
    """Return seconds since the session's MOST-RECENT activity (max mtime across 4 kinds).

    Returns ``None`` if no dir for this session exists in any kind. ``max`` (not min) is
    deliberate: ``outputs/`` may be freshly produced from a /process run while
    ``originals/`` was written an hour ago — protecting the most-recent artifact prevents
    the janitor from deleting a session whose result was just downloaded.

    WR-03 — mtime semantics: this uses each KIND DIR's ``stat().st_mtime``, not the inner
    files'. On POSIX/NTFS the dir mtime updates on file create / unlink / rename but NOT
    on overwrite-in-place. The pipeline lands the result via ``tempfile``-then-``replace``
    (see ``app/services/pipeline.py``'s atomic-replace), which IS a rename → the outputs
    dir mtime bumps on every /process run as required. If a future refactor switches to
    ``open("rb+", ...)``-style overwrite-in-place, this helper would silently stop noticing
    freshly produced results — track that constraint here so the dependency is explicit.
    """
    mtimes: list[float] = []
    for kind in _KINDS:
        try:
            path = subdir(kind, session_id)
        except InvalidSessionId:
            return None
        try:
            mtimes.append(path.stat().st_mtime)
        except FileNotFoundError:
            continue
        except OSError as err:
            logger.warning("session_age_seconds: stat failed on %s: %s", path, err)
            continue
    if not mtimes:
        return None
    return time.time() - max(mtimes)


def delete_session(session_id: str) -> None:
    """Remove the session's directory from all four kinds (best-effort, never raises).

    Each kind is rmtree'd independently so a failure in one kind does NOT skip the others
    (D-B3 "4-kind 一起刪"). :func:`_on_rm_error` re-chmods read-only originals → retry so
    the chmod 0o444 in :func:`write_original` does not block cleanup (Pitfall 3).
    """
    try:
        validate_session_id(session_id)
    except InvalidSessionId:
        return
    for kind in _KINDS:
        try:
            path = subdir(kind, session_id)
        except InvalidSessionId:
            continue
        if not path.exists():
            continue
        try:
            shutil.rmtree(path, onerror=_on_rm_error)
        except OSError as err:
            logger.warning("delete_session: rmtree failed on %s: %s", path, err)


def mark_session_corrupted(session_id: str) -> Path:
    """Write the ``.corrupted`` sentinel under ``work/{sid}/`` (D-C3).

    The sentinel is a zero-byte marker, not a JSON sidecar — its EXISTENCE is the signal.
    Subsequent /process calls short-circuit to 410 ``session_corrupted``; the 1-hour TTL
    sweep eventually reclaims the disk.
    """
    work_dir = subdir("work", session_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    sentinel = work_dir / _CORRUPTED_NAME
    sentinel.touch(exist_ok=True)
    return sentinel


def is_session_corrupted(session_id: str) -> bool:
    """True iff the ``.corrupted`` sentinel exists under ``work/{sid}/``.

    Crafted / non-token ids are swallowed and reported as ``False`` (never a traceback
    that would let an attacker probe the storage layer via error oracles). Mirrors the
    :func:`session_exists` contract.
    """
    try:
        return (subdir("work", session_id) / _CORRUPTED_NAME).is_file()
    except InvalidSessionId:
        return False
    except OSError:
        return False
