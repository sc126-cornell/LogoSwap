"""Phase 5 temp file janitor — 4-kind TTL sweep.

Runs synchronously at three trigger points (Plan 05-02 D-B1):
  (a) app startup            — :mod:`app.main` lifespan hook
  (b) end of POST /sessions  — :mod:`app.api.sessions`
  (c) end of POST /sessions/{sid}/process — :mod:`app.api.process`

Stdlib only (``time`` + :mod:`app.storage`). No fitz, no asyncio, no APScheduler —
the synchronous design is deliberate (D-B1 explicitly rejects background scheduler /
cron for a single-process internal tool).

Race protection (D-B4): TTL (3600s default) ≫ /process timeout (60s default), so an
in-flight job cannot age out mid-run; :func:`storage.delete_session` is itself wrapped
in try/except (it never raises) so a concurrent rmtree race only loses one cleanup
round, never crashes the sweep.

AGPL seam: tests/test_janitor.py::test_janitor_module_does_not_import_fitz enforces
this — never add a fitz import.
"""

from __future__ import annotations

import logging
import time

from .. import config, storage

logger = logging.getLogger(__name__)


def sweep_expired_sessions(now: float | None = None) -> int:
    """Delete every session whose max-mtime is older than :data:`config.SESSION_TTL_SECONDS`.

    Returns the count of sessions successfully deleted. Never raises — per-session errors
    are caught and logged so a single bad directory cannot stall the sweep, and so the
    three trigger sites can call this in a ``try / except Exception: pass`` finally block
    without polluting the HTTP response.

    The TTL is read at call time (not import time) so monkeypatching :data:`config.
    SESSION_TTL_SECONDS` in tests works without re-importing the module.
    """
    if now is None:
        now = time.time()
    ttl = config.SESSION_TTL_SECONDS

    try:
        sids = list(storage.list_session_ids())
    except OSError as err:
        logger.warning("janitor: enumerate_session_ids failed: %s", err)
        return 0
    except Exception as err:  # noqa: BLE001 — defensive top-level
        logger.warning("janitor: enumerate failed unexpectedly: %s", err)
        return 0

    deleted = 0
    for sid in sids:
        try:
            mtime_age = storage.session_age_seconds(sid)
            if mtime_age is None:
                continue
            if mtime_age < ttl:
                continue
            # delete_session is best-effort and itself swallows OSError, but we still
            # wrap in try/except for any unforeseen failure (test monkeypatch coverage).
            storage.delete_session(sid)
            # Count only confirmed full deletes (all 4 kind dirs gone). WR-04: on Windows,
            # an open file handle inside work/{sid}/ can defeat _on_rm_error's chmod retry,
            # leaving the session in a partial state (e.g. originals/outputs/pristine
            # reclaimed but work survives with the stuck file). Log that case explicitly
            # so ops sees the half-state instead of the sweep silently returning 0.
            remaining = [
                kind
                for kind in ("originals", "work", "outputs", "pristine")
                if (config.DATA_DIR / kind / sid).exists()
            ]
            if not remaining:
                deleted += 1
            else:
                logger.warning(
                    "janitor: partial delete for %s — kinds still present: %s",
                    sid,
                    ",".join(remaining),
                )
        except Exception as err:  # noqa: BLE001 — never raise out of the sweep
            logger.warning("janitor: failed on %s: %s", sid, err)
    return deleted
