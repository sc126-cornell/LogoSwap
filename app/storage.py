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

import os
import secrets
import stat
from pathlib import Path

from . import config

# Subdirectory kinds under DATA_DIR.
_KINDS = ("originals", "work", "outputs")

# Fixed on-disk name for the immutable original and the editable work copy. The
# client filename is stored in SessionInfo, not used on disk.
_ORIGINAL_NAME = "source.pdf"
_WORK_NAME = "doc.pdf"


def _data_dir() -> Path:
    """Resolve DATA_DIR at call time so tests can monkeypatch config.DATA_DIR."""
    return Path(config.DATA_DIR)


def subdir(kind: str, session_id: str) -> Path:
    """Path to ``<DATA_DIR>/<kind>/<session_id>`` (not created)."""
    if kind not in _KINDS:
        raise ValueError(f"unknown storage kind: {kind!r}")
    return _data_dir() / kind / session_id


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


def outputs_dir(session_id: str) -> Path:
    """Directory reserved for generated output PDFs (Phase 2+)."""
    return subdir("outputs", session_id)


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


def session_exists(session_id: str) -> bool:
    """True when the session's work copy exists (the canonical 'session present' test)."""
    return work_path(session_id).is_file()
