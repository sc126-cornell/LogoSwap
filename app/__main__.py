"""Desktop entry: ``python -m app`` boots uvicorn and opens the browser.

The HOST default is ``127.0.0.1`` (loopback) — desktop mode must NEVER listen on
0.0.0.0 (T-05-09). The Dockerfile / Zeabur path overrides this with ``--host
0.0.0.0`` via uvicorn's own CLI; this entry point is for the local-Python-package
deploy target (D-A4 target 2).

The browser is opened from a background ``threading.Timer`` with a 1-second
delay so uvicorn's bind happens before the browser hits the URL (Pitfall 7).
Set ``UVICORN_NO_BROWSER=1`` to suppress the auto-open (CI / headless).

Workers default to 1 on desktop (rather than the 2 used in Docker / Zeabur)
because (a) one local user does not benefit from a parallel worker and (b)
multi-worker spawn on Windows is slower to boot. Override via
``UVICORN_WORKERS``.

All imports here MUST stay spawn-safe — ``uvicorn.run("app.main:app", ...)``
with workers > 1 spawns child processes that re-import ``app.main``. The module
has no top-level side effects beyond ``FastAPI()`` construction and a
``time.time()`` capture, both of which are safe under spawn.
"""

from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

from .config import _env_int


def _open_browser(url: str) -> None:
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()


def main() -> None:
    # WR-01: reuse the config._env_int helper so an empty / non-integer PORT or
    # UVICORN_WORKERS (common when deploy templates clear an env var) falls back to the
    # default instead of crashing the desktop entry point with ValueError.
    host = os.environ.get("HOST", "127.0.0.1")
    port = _env_int("PORT", 8000)
    workers = _env_int("UVICORN_WORKERS", 1)
    url = f"http://{host}:{port}"

    if not os.environ.get("UVICORN_NO_BROWSER"):
        _open_browser(url)

    uvicorn.run("app.main:app", host=host, port=port, workers=workers)


if __name__ == "__main__":
    main()
