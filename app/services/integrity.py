"""Phase 5 integrity verification — runtime D-05 enforcement.

Computes and verifies the SHA-256 baseline of ``originals/{sid}/source.pdf`` written at
ingest time (Plan 05-02 D-C1 / D-C2). If the on-disk bytes diverge from the baseline a
session is fail-closed: a structured log line is emitted, a ``work/{sid}/.corrupted``
sentinel is written (so all subsequent operations short-circuit), and a typed
:class:`IntegrityError` is raised. The route layer maps it to 503 ``original_tampered``
(first /process after tamper) or 410 ``session_corrupted`` (later /process on the same sid).

AGPL seam: this module uses **stdlib only** (``hashlib``, ``logging``, ``pathlib``,
``time``) plus :mod:`app.storage`. NO ``import fitz`` — the integrity check must never
require the PDF parser. Enforced by ``tests/test_integrity.py::
test_integrity_module_does_not_import_fitz`` (statement-level grep).

Threat model (Plan 05-02):
  T-05-04 (S — SHA-256 forge): accepted as informational-only. v1 LAN tool; an attacker
  who can rewrite ``originals/source.pdf`` can also rewrite ``meta.json``, so the baseline
  is internal-consistency, not crypto-strength tamper-evidence. Carries Phase 4 T-04 wording.
  Pitfall 4 (legacy session — meta.json missing ``original_sha256``): fail-closed as
  ``session_corrupted`` → 410. The 1-hour TTL janitor reclaims the dir naturally.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from .. import storage

logger = logging.getLogger(__name__)


class IntegrityError(Exception):
    """Typed integrity failure carrying a stable ``code`` (mapped to a structured 4xx/5xx).

    Codes:
      * ``original_tampered`` — the on-disk SHA-256 diverges from the baseline → 503
      * ``session_corrupted`` — meta.json missing / lacks ``original_sha256`` (legacy
        session OR sentinel already set) → 410
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def compute_original_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data`` (the uploaded bytes at ingest time).

    Pure function — same input → same output, no I/O. The ingest layer captures the
    digest BEFORE chmod 0o444 (so the in-memory ``data`` is the source of truth, not the
    chmod-locked file) and writes it into ``meta.json`` in the same transaction
    (:func:`storage.write_session_meta`).
    """
    return hashlib.sha256(data).hexdigest()


def verify_original_hash(session_id: str) -> None:
    """Verify ``originals/{sid}/source.pdf`` matches the baseline in ``meta.json``.

    Side effect order on failure: **write the sentinel BEFORE raising** so a caller that
    catches and converts the exception (pipeline → PipelineError → main handler) does not
    accidentally skip the corruption mark. A subsequent /process on the same sid short-
    circuits to 410 ``session_corrupted`` from the route layer (without even reaching
    this verify call).

    Raises:
      * :class:`IntegrityError`(``original_tampered``) — file bytes diverge from baseline
      * :class:`IntegrityError`(``session_corrupted``) — meta missing or no ``original_sha256``
    """
    meta = storage.read_session_meta(session_id)
    if meta is None or "original_sha256" not in meta:
        # Pitfall 4: legacy session (Phase 1–4 meta.json without the new field) OR a
        # missing meta.json entirely. Fail-closed; the 1-hour TTL reclaims it.
        storage.mark_session_corrupted(session_id)
        raise IntegrityError(
            "session_corrupted",
            "此工作階段為舊版或資料不完整,請重新上傳檔案。",
        )

    expected = str(meta["original_sha256"])
    original = Path(storage.original_path(session_id))
    try:
        actual = hashlib.sha256(original.read_bytes()).hexdigest()
    except OSError as err:
        # Original file missing or unreadable post-ingest — treat as corruption (the
        # session can no longer prove its provenance). The sentinel ensures /process
        # gives up early on retries; the message text is the same as session_corrupted
        # because the user-facing remedy ("重新上傳") is identical.
        storage.mark_session_corrupted(session_id)
        raise IntegrityError(
            "session_corrupted",
            "此工作階段為舊版或資料不完整,請重新上傳檔案。",
        ) from err

    if actual != expected:
        # Structured log for ops audit — sid + both hashes + path + timestamp. The
        # `extra` dict lands in JSON-log adaptors (uvicorn's default formatter ignores
        # it, but a future log-config can serialize it). NOT included in the user-
        # facing message (T-05-08-adjacent — internal forensics, not customer-facing).
        logger.error(
            "original_tampered",
            extra={
                "session_id": session_id,
                "expected_hash": expected,
                "actual_hash": actual,
                "path": str(original),
                "timestamp": time.time(),
            },
        )
        storage.mark_session_corrupted(session_id)
        raise IntegrityError(
            "original_tampered",
            "系統偵測到原始檔異常,此工作階段已停用,請重新上傳檔案。",
        )
