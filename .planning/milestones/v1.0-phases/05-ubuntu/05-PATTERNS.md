# Phase 5: 部署與穩固化(Ubuntu) — Pattern Map

**Mapped:** 2026-05-23
**Files analyzed:** 22 (10 NEW / 12 MODIFIED)
**Analogs found:** 12 in-repo / 10 NEW (no in-repo analog — patterns sourced from STACK.md + RESEARCH.md)

Most of Phase 5 is **new infrastructure** (Dockerfile, LICENSE, docker-compose example, README, `app/__main__.py`, two new service modules, three new test files). For these, "closest analog" is the **stylistic / structural sibling** in the codebase (e.g. `services/logo.py` for a new `services/integrity.py`) plus the **literal pattern excerpt** from RESEARCH.md. For MODIFIED files, the analog IS the file itself — call out the exact existing line range that establishes the pattern to extend.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `Dockerfile` | NEW infrastructure | build → image | — (none in repo) | RESEARCH.md Pattern 1 |
| `.dockerignore` | NEW infrastructure | build filter | — | RESEARCH.md Pattern 1 |
| `docker-compose.example.yml` | NEW infrastructure | orchestration example | — | RESEARCH.md Standard Stack |
| `LICENSE` | NEW legal | static text | — | FSF AGPL-3.0 verbatim |
| `README.md` | NEW docs | static text | — | RESEARCH.md "Pattern 9" + STACK.md |
| `app/__main__.py` | NEW entry | CLI → uvicorn + browser | `app/main.py` (FastAPI bootstrap) | role-match (different concern) |
| `app/services/janitor.py` | NEW service module | scan-fs → delete | `app/storage.py` (path layout + InvalidSessionId), `app/services/logo.py` (no-fitz service skeleton) | role-match |
| `app/services/integrity.py` | NEW service module | bytes → hash + verify | `app/services/logo.py` (typed Error + lazy config), `app/services/redact.py` (typed Error + pdf_engine seam analog) | role-match |
| `app/config.py` | MODIFY constants | env → constant | `app/config.py` lines 19–73 (`_env_int` helper + named constants) | exact |
| `app/storage.py` | MODIFY storage | atomic write + sweep helpers | `app/storage.py` lines 167–195 (`write_session_meta` / `read_session_meta`), lines 80–101 (`subdir`) | exact |
| `app/services/ingest.py` | MODIFY ingest | bytes → hash + meta write | `app/services/ingest.py` lines 253–267, 296–310 (existing originals + meta write block) | exact |
| `app/services/pipeline.py` | MODIFY pipeline | entry verify | `app/services/pipeline.py` lines 107–137 (existing structural guards at entry) | exact |
| `app/api/process.py` | MODIFY handler | request → timeout-wrapped service | `app/api/process.py` lines 49–67 (existing `process_session` handler) | exact |
| `app/api/sessions.py` | MODIFY handler | request → ingest + sweep | `app/api/sessions.py` lines 43–77 (existing `create_session`) | exact |
| `app/main.py` | MODIFY FastAPI app | startup hook + /health + new exception codes | `app/main.py` lines 92–96 (`_PROCESS_STATUS` dict), lines 166–169 (`/health`), lines 108–114 (PipelineError handler) | exact |
| `web/index.html` | MODIFY HTML | static markup | `web/index.html` lines 39–410 (existing app-shell + toolbar + main) | role-match (new footer block) |
| `web/styles/app.css` | MODIFY CSS | token-aware styles | `web/styles/app.css` lines 1–75 (existing app shell + token usage) | exact |
| `web/js/app.js` | MODIFY frontend | new error codes → 繁中 mapping | `web/js/app.js` lines 18–53 (existing COPY table), lines 115–146 (existing `messageForError`) | exact |
| `tests/test_storage.py` | MODIFY tests | new helpers + atomic write | `tests/test_storage.py` lines 13–143 (existing pattern) | exact |
| `tests/test_process_api.py` | MODIFY tests | new error codes | `tests/test_process_api.py` lines 26–120 (existing `_upload` + happy-path harness) | exact |
| `tests/test_ingest.py` | MODIFY tests | hash baseline asserted | `tests/test_ingest.py` lines 14–56 (existing harness) | exact |
| `tests/test_janitor.py` | NEW test | sweep TTL paths | `tests/test_storage.py` (lifecycle test shape) | role-match |
| `tests/test_integrity.py` | NEW test | hash compute + verify | `tests/test_ingest.py` (hash assertion at line 28–30) | role-match |
| `tests/test_health.py` | NEW test | endpoint fields | `tests/test_api.py` lines 1–95 (existing endpoint test shape) | role-match |
| `requirements.txt` | NO CHANGE | — | — | Phase 5 ships zero new third-party deps (stdlib + Dockerfile + new app code) |

---

## Pattern Assignments

### `Dockerfile` (NEW infrastructure, build → image)

**Analog:** None in repo. Source: RESEARCH.md Pattern 1 (lines ~280–344).

**Pattern to follow:** Two-stage build (`python:3.12-slim-bookworm`). Stage 1 = `pip install --target /install`. Stage 2 = COPY `/install` + `app/` + `web/` + `logos/` + `LICENSE` + `README.md`; non-root `app` UID 1000; `VOLUME /data`; `HEALTHCHECK` using **stdlib `python -c urllib.request`** (NOT curl — slim has no curl, Pitfall 2); `CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-2} ${APP_BASE_PATH:+--root-path ${APP_BASE_PATH}}"]` so Zeabur's injected `$PORT` works AND empty `APP_BASE_PATH` is skipped cleanly.

**Pitfall (RESEARCH.md Pitfall 2):** `python:3.12-slim` has no curl/wget — HEALTHCHECK MUST use `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"`.

**Pitfall (RESEARCH.md Pitfall 10):** COPY `requirements.txt` BEFORE the app code so a code-only change does not bust the pip layer cache.

**Concrete excerpt (RESEARCH.md lines 339–344):**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"

CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-2} ${APP_BASE_PATH:+--root-path ${APP_BASE_PATH}}"]
```

---

### `.dockerignore` (NEW infrastructure, build filter)

**Analog:** None.

**Pattern:** Exclude `.git/`, `.venv*/`, `__pycache__/`, `.pytest_cache/`, `.planning/`, `tests/`, `data/`, `*.log`, `*.tmp.*`, `CLAUDE.md`, `Dockerfile`, `docker-compose.example.yml`, `README.md`, `zeabur.json`. Keep `requirements.txt`, `app/`, `web/`, `logos/`, `LICENSE`.

**Concrete excerpt (RESEARCH.md lines 354–373):** exact list above.

---

### `docker-compose.example.yml` (NEW infrastructure, orchestration example)

**Analog:** None.

**Pattern:** Single `app` service + Ubuntu nginx as reverse-proxy example. `volumes: ./data:/data`; `environment: APP_BASE_PATH=/pdf-logo` (Ubuntu prefix case) or empty (Zeabur/local). MUST be named `.example.yml` (not `.yml`) per D-A1 — repo does not ship a default compose file. Document the strip-prefix nginx pattern as a separate commented block.

---

### `LICENSE` (NEW legal, static text)

**Analog:** None.

**Pattern:** Copy `https://www.gnu.org/licenses/agpl-3.0.txt` **verbatim** into `LICENSE` at repo root. ASCII, ~34KB. **Do not modify** the license text itself (the license forbids that). This is Artifact 1 of the AGPL §13 three-artifact set (memory locked).

---

### `README.md` (NEW docs, static text)

**Analog:** None (no README currently exists per `Glob README*` returning nothing in repo root).

**Pattern (RESEARCH.md Pattern 9 + §"Recommended File Tree"):**
1. Top of file: project name, one-line description (Traditional Chinese + English),  AGPL-3.0 notice + GitHub repo URL (Artifact 2 of AGPL set).
2. Three deploy-target sections, in order: (a) **Zeabur** (push to public GitHub → connect repo → set `APP_BASE_PATH=""`), (b) **本機 Python 套裝** (`git clone` → `pip install -r requirements.txt` → `python -m app` → 瀏覽器自動開啟), (c) **Ubuntu 公司入口網站** (docker-compose.example.yml as starting point, strip-prefix nginx snippet, `APP_BASE_PATH=/pdf-logo`).
3. Environment variable reference table (`DATA_DIR`, `LOGOS_DIR`, `APP_BASE_PATH`, `UVICORN_WORKERS`, `PROCESS_TIMEOUT_SECONDS`, `SESSION_TTL_SECONDS`, `CORS_ALLOW_ORIGINS`, `MAX_UPLOAD_BYTES`, `MAX_PAGES`).
4. Embedding contract section: `window.PDFTOOL_API_BASE` (Phase 1 frontend seam) + `APP_BASE_PATH` env var (Phase 5 backend `root_path`).
5. Known limitations: AGPL §13 internal-deploy guidance, 1h session TTL, /process 60s timeout, large/rotated page DPI fallback.

---

### `app/__main__.py` (NEW entry, CLI → uvicorn + browser)

**Analog:** `app/main.py` (lines 1–34) for the FastAPI module-load pattern; this is a sibling entry point.

**Pattern (RESEARCH.md Pattern 3, lines 417–474):**
```python
"""Desktop entry: `python -m app` boots uvicorn + opens the browser."""
from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn


def _open_browser(url: str) -> None:
    # 1-second delay to avoid racing uvicorn startup (browser hits before server ready)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    workers = int(os.environ.get("UVICORN_WORKERS", "1"))  # desktop default 1
    url = f"http://{host}:{port}"

    if not os.environ.get("UVICORN_NO_BROWSER"):
        _open_browser(url)

    uvicorn.run("app.main:app", host=host, port=port, workers=workers)


if __name__ == "__main__":
    main()
```

**Pitfall (RESEARCH.md Pitfall 7):** uvicorn `--workers > 1` uses `multiprocessing.spawn` (not fork) on Windows. Every imported module must be import-safe under spawn. `app/main.py` already satisfies this — no top-level side effects beyond `FastAPI()` construction. **Phase 5 modification to `app/main.py` MUST keep this property:** the new `_START_TIME = time.time()` global is spawn-safe (each worker captures its own start time, which is the desired semantic per RESEARCH.md line 1234).

**Pitfall (RESEARCH.md line 1106):** A bare `webbrowser.open` before `uvicorn.run` races the server. Use `threading.Timer(1.0, ...)` — NOT `time.sleep(1)` (that would block main thread).

---

### `app/services/janitor.py` (NEW service module, scan-fs → delete)

**Closest analog:** `app/storage.py` (path layout, `_KINDS`, `_SESSION_ID_RE`, `subdir`) + `app/services/logo.py` lines 1–60 (no-fitz service module skeleton with typed Error + lazy config-resolve).

**Pattern to follow (RESEARCH.md Pattern 7, lines 750–908):**

1. **Imports** (mirrors `services/logo.py` style — no fitz):
   ```python
   from __future__ import annotations
   import errno, logging, os, shutil, stat, time
   from pathlib import Path
   from .. import config, storage
   logger = logging.getLogger(__name__)
   ```

2. **Constants** (re-use storage's `_KINDS` rather than redeclare — DRY with `storage._KINDS`):
   ```python
   _KINDS = ("originals", "work", "outputs", "pristine")  # mirrors storage.py:34
   ```

3. **`_on_rm_error` handler** — RESEARCH.md lines 784–804. CRITICAL for cross-platform (Pitfall 3 — `originals/source.pdf` is chmod 0o444; Windows `DeleteFile` fails on read-only). 3-arg `onerror` form works on 3.10–3.14; pick that over `onexc` for broadest compatibility.

4. **Main entry `sweep_expired_sessions(now: float | None = None) -> int`** — RESEARCH.md lines 878–908. NEVER raises (returns 0 on enumeration failure). Compares `_session_max_mtime(sid)` (latest mtime across 4 kinds) against `config.SESSION_TTL_SECONDS`. Calls `_delete_session(sid)` for expired sessions.

5. **`_session_max_mtime`** (lines 856–875): uses **max** not **min** mtime — a session that just produced an output 5 min ago must not be deleted because its originals/ is 55 min old.

6. **`_enumerate_session_ids`** (lines 838–853): union of well-formed session names across all four kind dirs — covers orphaned remnants from crash-between-writes.

7. **Race protection (D-B4):** TTL (3600s default) is 60x process timeout (60s default), so a session being actively /process'd cannot age out mid-job. Defensive `try/except` on `_safe_rmtree` catches `ENOTEMPTY` from concurrent rmtree.

**Concrete excerpt (RESEARCH.md lines 784–822, `_on_rm_error` + `_safe_rmtree`):**
```python
def _on_rm_error(func, path, exc_info) -> None:
    """rmtree error handler — re-chmod a read-only file then retry."""
    excvalue = exc_info[1] if exc_info else None
    if isinstance(excvalue, PermissionError) and func in (os.unlink, os.rmdir, os.remove):
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            func(path)
            return
        except OSError:
            pass
    logger.warning("janitor: rmtree failed on %s: %s", path, excvalue)


def _safe_rmtree(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        shutil.rmtree(path, onerror=_on_rm_error)
        return not path.exists()
    except OSError as err:
        if err.errno == errno.ENOTEMPTY:
            return not path.exists()
        logger.warning("janitor: rmtree raised on %s: %s", path, err)
        return False
```

**Pitfall (RESEARCH.md Pitfall 3):** `shutil.rmtree` on chmod 0o444 file on Windows raises `PermissionError`. Solution: `onerror=_on_rm_error` that re-chmod's then retries. **MUST be tested on Windows path** (dev venv is Windows per memory; CI Ubuntu masks this).

---

### `app/services/integrity.py` (NEW service module, bytes → hash + verify)

**Closest analog:** `app/services/logo.py` lines 1–60 (typed `LogoError(code, message)` + module docstring with security property statement + no-fitz seam) AND `app/services/redact.py` lines 1–50 (purity / AGPL seam statement at module top).

**Pattern to follow (RESEARCH.md Pattern 6, lines 620–711):**

1. **Module docstring** mirrors `services/logo.py` style — name the security property (D-05 runtime enforcement of originals/ invariant) + the AGPL seam guarantee (no fitz import; uses `hashlib` stdlib).

2. **Typed `IntegrityError(code, message)`** — mirrors `LogoError` shape at `logo.py:31–42`. Codes: `original_tampered` (503), `session_corrupted` (410).
   ```python
   class IntegrityError(Exception):
       def __init__(self, code: str, message: str) -> None:
           super().__init__(message)
           self.code = code
           self.message = message
   ```

3. **`compute_original_hash(data: bytes) -> str`** — thin `hashlib.sha256(data).hexdigest()` wrapper. Called by `ingest.py` after the upload bytes are in scope but before `write_session_meta`.

4. **`verify_original_hash(session_id: str) -> None`** — RESEARCH.md lines 656–695. Raises `IntegrityError("original_tampered" | "session_corrupted")`. Side effect on mismatch: calls `storage.mark_session_corrupted(session_id)` BEFORE raising, so subsequent /process calls short-circuit at the API layer (D-C3).

5. **Structured logging** — use `logger.error("original_tampered", extra={...})` with `session_id`, `expected_hash`, `actual_hash`, `path`, `timestamp`. No CRLF injection risk (server controls all fields). Uvicorn's stdout passes the line through.

6. **Pipeline integration:** `pipeline.process_job` catches `IntegrityError` and re-raises as `PipelineError(err.code, err.message)` — so the existing `_PROCESS_STATUS` dict in `main.py:92` routes the code to the right status with no new exception-handler boilerplate.

**Concrete excerpt (RESEARCH.md lines 656–695):**
```python
def verify_original_hash(session_id: str) -> None:
    """Compare originals/source.pdf against the baseline in meta.json."""
    meta = storage.read_session_meta(session_id)
    if meta is None or "original_sha256" not in meta:
        # Legacy session (Phase 1–4) or sidecar lost. Treat as corrupted — user re-uploads.
        storage.mark_session_corrupted(session_id)
        raise IntegrityError(
            "session_corrupted",
            "此工作階段為舊版或資料不完整,請重新上傳檔案。",
        )

    expected = meta["original_sha256"]
    original = storage.original_path(session_id)
    actual = hashlib.sha256(Path(original).read_bytes()).hexdigest()

    if actual != expected:
        logger.error(
            "original_tampered",
            extra={"session_id": session_id, "expected_hash": expected,
                   "actual_hash": actual, "path": str(original), "timestamp": time.time()},
        )
        storage.mark_session_corrupted(session_id)
        raise IntegrityError(
            "original_tampered",
            "系統偵測到原始檔異常,此工作階段已停用,請重新上傳檔案。",
        )
```

**Pitfall (RESEARCH.md Pitfall 4):** Meta.json schema migration — Phase 1–4 sessions lack `original_sha256`. **Decision (RESEARCH.md line 615):** reject as `session_corrupted` (require re-upload). 1h TTL ensures legacy sessions auto-expire within 1h of Phase 5 deployment, so this is non-disruptive.

---

### `app/config.py` (MODIFY — add 5 constants)

**Analog (THIS file):** `app/config.py` lines 19–73 (`_env_int` helper + named constants with docstrings).

**Pattern to follow:** Append five new constants AFTER the existing block (after line 84 `API_TITLE`). Use `_env_int` for integer-valued vars; use `os.environ.get(name, default)` for string vars.

**Concrete excerpt (existing pattern at `app/config.py:19–48`):**
```python
def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default

# ...

MAX_UPLOAD_BYTES: int = _env_int("MAX_UPLOAD_BYTES", 50 * 1024 * 1024)
MAX_PAGES: int = _env_int("MAX_PAGES", 30)
```

**Phase 5 additions (per CONTEXT.md "Carrying forward" + RESEARCH.md):**
```python
# Phase 5: session lifecycle / deployment / stabilization
SESSION_TTL_SECONDS: int = _env_int("SESSION_TTL_SECONDS", 3600)          # 1h hard TTL (D-B2)
PROCESS_TIMEOUT_SECONDS: int = _env_int("PROCESS_TIMEOUT_SECONDS", 60)    # /process timeout (D-D3)
UVICORN_WORKERS: int = _env_int("UVICORN_WORKERS", 2)                     # workers default (D-D2)
APP_BASE_PATH: str = os.environ.get("APP_BASE_PATH", "")                  # FastAPI root_path (D-A2)
CORS_ALLOW_ORIGINS: str = os.environ.get("CORS_ALLOW_ORIGINS", "")        # comma-separated, default off (Claude discretion)
```

**Note:** Naming convention follows existing constants — `MAX_X_Y` / `MIN_X` / `DEFAULT_X` / unit suffix (`_BYTES`, `_SECONDS`, `_PIXELS`).

---

### `app/storage.py` (MODIFY — atomic meta write + 5 helpers)

**Analog (THIS file):** `app/storage.py` lines 167–195 (`write_session_meta` + `read_session_meta`), lines 80–101 (`subdir` + path-traversal guard), lines 240–251 (`session_exists` pattern for the "is_session_corrupted" mirror).

**Modifications:**

1. **Upgrade `write_session_meta` to atomic + new field** — RESEARCH.md Pattern 5 (lines 557–599). Add required keyword arg `original_sha256: str`. Use `tempfile.mkstemp(dir=str(dest.parent))` + `os.replace(tmp, dest)`.

   **Concrete excerpt (RESEARCH.md lines 564–599):**
   ```python
   def write_session_meta(
       session_id: str,
       *,
       page_count: int,
       filename: str,
       original_sha256: str,  # Phase 5: NEW required field
   ) -> Path:
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
           os.replace(tmp_path, dest)  # atomic on Linux + Windows
       except Exception:
           try:
               os.unlink(tmp_path)
           except OSError:
               pass
           raise
       return dest
   ```

   **Pitfall (RESEARCH.md A7, line 1397):** `tempfile.mkstemp(dir=str(dest.parent))` is REQUIRED — without explicit `dir=`, Windows may put tmp on a different drive making `os.replace` cross-FS = non-atomic.

2. **`list_session_ids() -> Iterator[str]`** — RESEARCH.md lines 936–947. Yield well-formed session ids across all 4 kinds, deduplicated via a `seen: set[str]`.

3. **`session_age_seconds(session_id: str) -> float | None`** — RESEARCH.md lines 950–957. Max mtime across kind-dirs (parallels janitor's `_session_max_mtime`).

4. **`delete_session(session_id: str) -> None`** — RESEARCH.md lines 960–966. Removes session dir in all 4 kinds using `shutil.rmtree` + `_on_rm_error` handler (share helper with janitor, or duplicate).

5. **`mark_session_corrupted(session_id: str) -> Path`** — RESEARCH.md lines 915–925:
   ```python
   def mark_session_corrupted(session_id: str) -> Path:
       work_dir = subdir("work", session_id)
       work_dir.mkdir(parents=True, exist_ok=True)
       sentinel = work_dir / ".corrupted"
       sentinel.touch(exist_ok=True)
       return sentinel
   ```

6. **`is_session_corrupted(session_id: str) -> bool`** — RESEARCH.md lines 928–933 (mirrors `session_exists` shape at `storage.py:240–251`):
   ```python
   def is_session_corrupted(session_id: str) -> bool:
       try:
           return (subdir("work", session_id) / ".corrupted").is_file()
       except InvalidSessionId:
           return False
   ```

**Reuse the path-traversal guard:** every new helper MUST route through `subdir(kind, session_id)` so `validate_session_id` rejects crafted ids before disk I/O (existing storage.py:62–64 pattern).

---

### `app/services/ingest.py` (MODIFY — compute + persist hash at upload)

**Analog (THIS file):** `app/services/ingest.py` lines 253–267 (`_ingest_pdf` write block) and lines 296–310 (`_ingest_image_to_pdf` write block).

**Modification:** In both `_ingest_pdf` AND `_ingest_image_to_pdf`, after `storage.write_original(session_id, safe_name, data)` and before `storage.write_session_meta(...)`, compute `original_sha256` from the **upload bytes `data`** (NOT re-read from disk — bytes already in scope and chmod 0o444 was already applied). Pass it as the new kwarg.

**Concrete excerpt (existing pattern at `ingest.py:256–261`):**
```python
session_id = storage.new_session()
safe_name = storage.sanitize_filename(filename)
storage.write_original(session_id, safe_name, data)
storage.write_work_copy(session_id, data)
storage.write_pristine_copy(session_id, data)
storage.write_session_meta(session_id, page_count=n_pages, filename=safe_name)
```

**Phase 5 modification (insert `from .integrity import compute_original_hash` at top, then):**
```python
session_id = storage.new_session()
safe_name = storage.sanitize_filename(filename)
storage.write_original(session_id, safe_name, data)
storage.write_work_copy(session_id, data)
storage.write_pristine_copy(session_id, data)
storage.write_session_meta(
    session_id,
    page_count=n_pages,
    filename=safe_name,
    original_sha256=compute_original_hash(data),  # Phase 5: D-C1 baseline
)
```

**Important:** For image uploads (`_ingest_image_to_pdf`), the hash is over the user's **original image bytes** (`data`), not the normalized A4 PDF — because `originals/` stores the user's raw bytes (image), and the hash baseline must match what `verify_original_hash` will re-read from `originals/source.pdf`. RESEARCH.md confirms this is the correct semantic (D-C4 — verify only originals/).

---

### `app/services/pipeline.py` (MODIFY — verify at entry)

**Analog (THIS file):** `app/services/pipeline.py` lines 107–137 (existing `process_job` entry: pristine path resolution + `work_copy_misconfigured` structural guard).

**Modification:** Inject `integrity.verify_original_hash(session_id)` BEFORE the existing `shutil.copyfile(pristine, work)` reset (line 136). Catch `IntegrityError` and re-raise as `PipelineError(err.code, err.message)` so the existing `main.py:108–114` exception handler routes via `_PROCESS_STATUS`.

**Concrete excerpt (RESEARCH.md lines 716–729):**
```python
def process_job(session_id: str, job_spec) -> dict:
    work = storage.work_path(session_id)
    pristine = storage.pristine_path(session_id)

    # Phase 5: verify originals/ hash BEFORE reset-from-pristine (D-C2).
    try:
        integrity.verify_original_hash(session_id)
    except integrity.IntegrityError as err:
        raise PipelineError(err.code, err.message) from err

    # (existing structural guards + reset + redact + save logic continues unchanged)
    if Path(work).resolve() == Path(pristine).resolve():
        raise PipelineError("work_copy_misconfigured", ...)
    # ...
```

**No new error-handler code needed in `main.py` for this** — `PipelineError` is already handled at `main.py:108–114`. Only the `_PROCESS_STATUS` dict at `main.py:92–96` needs the new code mappings (see below).

---

### `app/api/process.py` (MODIFY — corrupted check + timeout + janitor)

**Analog (THIS file):** `app/api/process.py` lines 49–67 (existing `process_session` handler using `run_in_threadpool`).

**Three modifications, in this order:**

1. **PRE-check `is_session_corrupted`** (before timeout wrapper) — short-circuit with 410.
2. **Replace `run_in_threadpool(pipeline.process_job, ...)` with `asyncio.wait_for(asyncio.to_thread(pipeline.process_job, ...), timeout=config.PROCESS_TIMEOUT_SECONDS)`** — D-D3 60s bound.
3. **Add `finally: janitor.sweep_expired_sessions()`** with bare `except Exception: pass` so janitor failure never taints the response.

**Concrete excerpt (RESEARCH.md lines 502–542):**
```python
@router.post("/sessions/{session_id}/process")
async def process_session(session_id: str, job: JobSpec) -> dict:
    _require_session(session_id)

    # Phase 5: corrupted-session sentinel check FIRST (D-C3).
    if storage.is_session_corrupted(session_id):
        raise HTTPException(
            status_code=410,  # Gone — session no longer usable
            detail={"code": "session_corrupted",
                    "message": "此工作階段已標記為異常,請重新上傳檔案。"},
        )

    # Phase 5: bound the sync CPU-bound work in 60s (D-D3).
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(pipeline.process_job, session_id, job),
            timeout=config.PROCESS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as err:
        raise HTTPException(
            status_code=504,
            detail={"code": "processing_timeout",
                    "message": f"處理逾時(超過 {config.PROCESS_TIMEOUT_SECONDS} 秒),"
                               "請改用較小檔案或減少框選區域數量。"},
        ) from err
    finally:
        # D-B1 trigger point (c): /process end → sweep expired sessions.
        try:
            janitor.sweep_expired_sessions()
        except Exception:
            pass
```

**Pitfall (RESEARCH.md Pitfall 1):** `asyncio.wait_for(asyncio.to_thread(...))` does NOT kill the thread on timeout — Python cannot kill threads. HTTP returns 504 promptly but the worker thread keeps running until the sync work completes naturally. **This is acceptable for v1** because workers default to 2 (the other worker still serves /pages preview / /health) and MAX_RENDER_PIXELS=40MP + MAX_PAGES=30 keep worst-case real work in 10–30s. Plan-writer MUST document this fact in code comments + README known-limitations.

**Also:** `_require_session` (process.py:41–46) returns 404 for unknown session — the **`is_session_corrupted` check must run AFTER `_require_session`** so a missing-session vs. corrupted-session distinction stays clean.

---

### `app/api/sessions.py` (MODIFY — janitor sweep at end of POST)

**Analog (THIS file):** `app/api/sessions.py` lines 43–77 (existing `create_session`).

**Modification:** Add `finally: janitor.sweep_expired_sessions()` (try/except wrapped) at the end of `create_session` — D-B1 trigger point (b). Same pattern as `api/process.py`.

**No timeout wrapper needed here** — ingest is bounded by `MAX_UPLOAD_BYTES` + the streaming size guard already in place at lines 56–69.

---

### `app/main.py` (MODIFY — startup hook + /health + new exception codes)

**Analog (THIS file):**
- `app/main.py` lines 92–96 (existing `_PROCESS_STATUS` dict — extend it).
- `app/main.py` lines 108–114 (existing `_handle_pipeline_error` — NO change needed; new codes route through it via dict lookup).
- `app/main.py` lines 166–169 (existing `/health` — replace).
- `app/main.py` lines 34, 37–40 (`app = FastAPI(...)` + router registration — add `root_path` + lifespan).

**Three modifications:**

1. **Extend `_PROCESS_STATUS`** (line 92–96) with three new codes:
   ```python
   _PROCESS_STATUS: dict[str, int] = {
       "residual_content": 422,
       "page_out_of_range": 422,
       "work_copy_misconfigured": 500,
       # Phase 5: NEW
       "original_tampered": 503,
       "session_corrupted": 410,
       "processing_timeout": 504,  # also emitted directly by api/process.py
   }
   ```

2. **Enhance `/health`** (replace lines 166–169) — RESEARCH.md Pattern 8 (lines 973–1023):
   ```python
   _START_TIME = time.time()  # captured per worker (spawn-safe per Pitfall 7)

   @app.get("/health", tags=["health"])
   async def health() -> dict:
       uptime = max(0.0, time.time() - _START_TIME)
       originals_root = Path(config.DATA_DIR) / "originals"
       active_sessions = 0
       if originals_root.is_dir():
           try:
               active_sessions = sum(
                   1 for entry in originals_root.iterdir()
                   if entry.is_dir() and storage._SESSION_ID_RE.fullmatch(entry.name)
               )
           except OSError:
               active_sessions = -1
       data_dir_bytes = 0
       data_dir_pct = 0.0
       try:
           usage = shutil.disk_usage(str(config.DATA_DIR))
           data_dir_bytes = usage.used
           data_dir_pct = round(100.0 * usage.used / usage.total, 2)
       except (OSError, FileNotFoundError):
           pass
       return {
           "status": "ok",
           "uptime_seconds": round(uptime, 2),
           "active_sessions": active_sessions,
           "data_dir_bytes": data_dir_bytes,
           "data_dir_pct": data_dir_pct,
       }
   ```

   **Pitfall (RESEARCH.md Pitfall 8):** `shutil.disk_usage` reports **filesystem-level** usage (the bind-mount or volume's underlying FS), NOT per-session usage. Document this in the `/health` JSON schema docstring. Acceptable for v1 alerting.

   **Spawn-safety (RESEARCH.md Pitfall 7):** `_START_TIME` at module top level is captured per worker process — each worker reports its own uptime, which is the desired semantic.

3. **Add startup lifespan hook for janitor** + (optional) FastAPI `root_path` constructor arg:
   ```python
   _APP_BASE_PATH = os.environ.get("APP_BASE_PATH", "")

   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # D-B1 trigger point (a): app startup sweep.
       try:
           janitor.sweep_expired_sessions()
       except Exception:
           pass
       yield

   app = FastAPI(title=config.API_TITLE, root_path=_APP_BASE_PATH, lifespan=lifespan)
   ```

   **Pitfall (RESEARCH.md Pitfall 5):** `FastAPI(root_path=...)` + `app.mount("/", StaticFiles(html=True))` has known redirect quirks (#12151). Default `APP_BASE_PATH=""` is safe; document `APP_BASE_PATH=/pdf-logo` as "experimental — test with your proxy before relying on it" (RESEARCH.md line 410).

**Optional Phase 5 — CORS middleware (Claude's discretion):**
```python
if config.CORS_ALLOW_ORIGINS:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in config.CORS_ALLOW_ORIGINS.split(",") if o.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
```

---

### `web/index.html` (MODIFY — AGPL footer + session TTL hint)

**Analog (THIS file):** `web/index.html` — no existing `<footer>` element (verified via `Grep app-footer`). Closest structural sibling: lines 39–410 (`<div class="app-shell">` + `<header class="toolbar">` + `<main class="main">` + `<aside class="side-panel">`).

**Pattern:** Add a `<footer class="app-footer" role="contentinfo">` element INSIDE `<div class="app-shell">` after `</main>` (before line 410 `</div>`) but BEFORE the modal block at line 414. This keeps the footer inside the shell grid; CSS will fix it to the bottom.

**Concrete excerpt (RESEARCH.md Pattern 9, lines 1042–1050):**
```html
<!-- AGPL §13 source disclosure — required for network deployment of AGPL software.
     Link visible to every browser session; no login wall, no JS-conditional rendering. -->
<footer class="app-footer" role="contentinfo">
  <p class="app-footer__text">
    本工具為 <a class="app-footer__link"
                href="https://github.com/<OWNER>/LogoSwap"
                target="_blank" rel="noopener">LogoSwap</a> — 依
    <a class="app-footer__link"
       href="https://www.gnu.org/licenses/agpl-3.0.html"
       target="_blank" rel="noopener">AGPLv3</a> 授權。
  </p>
  <p class="app-footer__hint">此次處理 1 小時內完成下載 — 逾時需重新上傳。</p>
</footer>
```

**Important:** The `<OWNER>` placeholder must be replaced by the actual public GitHub repo URL before deploy (Artifact 2 — memory locked). Planner should make this an explicit task: "user confirms GitHub URL → substitute into index.html before any deploy."

---

### `web/styles/app.css` (MODIFY — footer styles)

**Analog (THIS file):** `web/styles/app.css` lines 1–80 (existing token-only styling + `.app-shell` grid + `.toolbar` flex pattern).

**Pattern to follow:** Hard rule from `app.css:1–8` — **every color is `var(--color-*)` from `tokens.css`; no raw theme hexes**. Accent is reserved for primary CTA + active page indicator only (`app.css:6–8`); the AGPL footer link is NOT the accent — use `var(--color-text)` or `var(--color-link)` if it exists in tokens.

**Phase 5 additions (terse, token-only):**
```css
.app-footer {
  padding: var(--space-sm) var(--space-lg);
  background: var(--color-panel);
  border-top: 1px solid var(--color-border);
  font-size: var(--font-size-small);
  color: var(--color-text-muted);
  text-align: center;
}

.app-footer__text { margin: 0; }
.app-footer__hint { margin: var(--space-xs) 0 0 0; color: var(--color-text-muted); }
.app-footer__link { color: var(--color-text); text-decoration: underline; }
.app-footer__link:hover { color: var(--color-accent); }
```

**Note:** Update `.app-shell { grid-template-rows: auto 1fr auto; }` (currently `auto 1fr` at `app.css:46–48`) so the footer has a row in the shell grid.

---

### `web/js/app.js` (MODIFY — three new error codes → 繁中 messages)

**Analog (THIS file):** `web/js/app.js` lines 18–53 (existing `COPY` table with 繁中 strings) and lines 115–146 (existing `messageForError(err)` switch).

**Modification:** Add three new `COPY` entries + three new switch cases mirroring the existing family-grouping pattern (lines 121–138):

**Concrete excerpt (existing pattern at `app.js:116–146`):**
```javascript
function messageForError(err) {
  const code = err && err.code ? err.code : "unknown";
  switch (code) {
    case "unsupported_type":
      return COPY.unsupportedType;
    case "corrupt_pdf":
      return COPY.corruptPdf;
    // ... (Phase 4 image codes)
    case "file_too_large":
    case "too_many_pages":
      return COPY.fileTooLarge(extractLimit(err && err.serverMessage));
    case "empty_file":
      return COPY.unsupportedType;
    default:
      return COPY.networkFailure;
  }
}
```

**Phase 5 additions** (extend `COPY` table):
```javascript
// Phase 5 — three new server error codes (UI-SPEC Phase 5).
// Family: 系統發現異常 / 工作階段問題 / 逾時 — different remedy for each.
originalTampered:
  "系統偵測到原始檔異常,此工作階段已停用,請重新上傳此檔。",
sessionCorrupted:
  "此工作階段已過期或無法使用,請重新上傳檔案。",
processingTimeout:
  "處理逾時,請改用較小檔案或減少框選區域數量後再試一次。",
```

And new switch cases in `messageForError` (before `default`):
```javascript
case "original_tampered":
  return COPY.originalTampered;
case "session_corrupted":
  return COPY.sessionCorrupted;
case "processing_timeout":
  return COPY.processingTimeout;
```

**Important — security pattern preserved (`app.js:11`):** all dynamic strings via `textContent` (never `innerHTML`). The COPY strings are static literals, no server-message reflection — same posture as existing Phase 1–4 error codes.

**Where errors surface:** the `processJob` call site in `regions.js` / `app.js` already catches `ApiError` and routes through the existing inline notice block — no new UI scaffolding required, only the message mapping. (The 410/503/504 codes flow from server `ApiError.code` exactly like the existing 422/415/413 codes do.)

---

### `tests/test_storage.py` (MODIFY — atomic meta write + new helpers)

**Analog (THIS file):** `tests/test_storage.py` lines 13–143 (existing layout: `test_new_session_creates_exactly_three_dirs`, `test_write_original_round_trips_bytes`, `test_sanitize_filename_*`, `test_subdir_rejects_non_token_session_id`).

**Pattern to follow:** Each new helper gets a dedicated test mirroring the existing one-test-per-property style. Reuse the autouse `isolated_data_dir` fixture (conftest.py:298–307) for tmp DATA_DIR isolation — already auto-applied to every test.

**New tests to add:**

| Test name | Asserts |
|-----------|---------|
| `test_write_session_meta_includes_original_sha256` | written meta.json has all three fields |
| `test_write_session_meta_is_atomic_on_crash` | simulate write failure → no half-written meta.json (only old or new content) |
| `test_list_session_ids_unions_across_kinds` | session ids appear in any of 4 kinds → all enumerated, deduplicated |
| `test_session_age_seconds_uses_max_mtime` | bump mtime in outputs/ → age reflects newest, not oldest |
| `test_delete_session_removes_all_four_kinds` | after delete, none of 4 kind-dirs contain {sid}/ |
| `test_delete_session_handles_readonly_original_on_windows` | originals/source.pdf chmod 0o444 still deletable (Pitfall 3) |
| `test_mark_and_is_session_corrupted_round_trip` | mark → is_corrupted True; not marked → False |
| `test_is_session_corrupted_rejects_invalid_id` | crafted id returns False, never raises |

**Concrete pattern excerpt (existing `tests/test_storage.py:37–43` — read-only assertion):**
```python
def test_write_original_is_read_only_after_write():
    sid = storage.new_session()
    path = storage.write_original(sid, "x.pdf", b"%PDF-1.7\n%%EOF")
    mode = os.stat(path).st_mode
    assert not (mode & 0o200), f"original should not be writable, mode={oct(mode)}"
```

---

### `tests/test_process_api.py` (MODIFY — new error codes + corrupted gate)

**Analog (THIS file):** `tests/test_process_api.py` lines 26–120 (existing `_upload` + `_region_px_for` helpers + full happy-path slice).

**New tests to add:**

| Test name | Asserts |
|-----------|---------|
| `test_original_tampered_returns_503` | tamper with originals/source.pdf between ingest and /process → 503 `original_tampered` + structured detail.code |
| `test_corrupted_session_blocked_from_process` | mark .corrupted then call /process → 410 `session_corrupted` |
| `test_legacy_session_without_sha256_treated_as_corrupted` | strip `original_sha256` from meta.json → /process → 503 or 410 with friendly message |
| `test_process_timeout_returns_504` | monkeypatch `config.PROCESS_TIMEOUT_SECONDS=0.1` + monkeypatch `pipeline.process_job` to `time.sleep(2)` → /process → 504 `processing_timeout` |
| `test_meta_original_sha256_written_at_ingest` | after `/sessions` POST → `read_session_meta(sid)["original_sha256"]` is 64-char hex |

**Concrete pattern excerpt (existing `tests/test_process_api.py:90–107` — hash invariant):**
```python
# Original hash before processing (deferred-mutation check).
original = storage.original_path(sid)
before = hashlib.sha256(original.read_bytes()).hexdigest()
# ... /process ...
after = hashlib.sha256(original.read_bytes()).hexdigest()
assert before == after, "original must be unchanged after /process"
```

**Tampering test pattern (Phase 5 NEW — adapts the above):** the test must temporarily `chmod 0o644` originals/source.pdf to mutate it (chmod 0o444 from `write_original` prevents writes), then re-chmod 0o444, then call /process to verify the tamper-detection.

---

### `tests/test_ingest.py` (MODIFY — assert hash baseline written)

**Analog (THIS file):** `tests/test_ingest.py` lines 14–56 (existing happy-path + rejection tests; line 28–30 already computes SHA-256 for the immutability assertion).

**New test to add:**
```python
def test_ingest_writes_original_sha256_into_meta(valid_pdf_bytes):
    info = ingest.ingest_upload("design.pdf", valid_pdf_bytes)
    meta = storage.read_session_meta(info.session_id)
    assert meta is not None
    assert "original_sha256" in meta
    # Must match the bytes hash, NOT a re-read from disk (defense: ingest computes before chmod).
    assert meta["original_sha256"] == hashlib.sha256(valid_pdf_bytes).hexdigest()


def test_ingest_image_hash_is_over_raw_image_bytes(png_bytes):
    # For image uploads, hash is over the user's image bytes (in originals/), NOT the normalized A4 PDF.
    info = ingest.ingest_upload("logo.png", png_bytes)
    meta = storage.read_session_meta(info.session_id)
    assert meta["original_sha256"] == hashlib.sha256(png_bytes).hexdigest()
```

---

### `tests/test_janitor.py` (NEW test file)

**Closest analog:** `tests/test_storage.py` (lifecycle test shape using `isolated_data_dir` fixture).

**Pattern to follow:** Test the `sweep_expired_sessions` function directly + integration with the three trigger points. Use `os.utime(path, (epoch, epoch))` to fake-age a session's dir mtime past TTL.

**Tests to include:**

| Test name | Asserts |
|-----------|---------|
| `test_janitor_sweeps_expired_session` | create session, `os.utime` it to mtime-3700s, call `sweep_expired_sessions()` → returns 1, all 4 kind dirs gone |
| `test_janitor_keeps_active_session_under_ttl` | create session, leave mtime fresh, sweep → returns 0, dirs intact |
| `test_janitor_max_mtime_protects_recent_outputs` | originals/ ancient but outputs/ recent → not deleted |
| `test_janitor_handles_chmod_0o444_originals_on_windows` | the 0o444 source.pdf must be deletable via `_on_rm_error` handler (Pitfall 3) |
| `test_janitor_skips_concurrent_rmtree_race` | mock `shutil.rmtree` to raise `ENOTEMPTY` mid-sweep → no exception, returns count of those that succeeded |
| `test_janitor_skips_non_token_dir_names` | manually create `data/work/not-a-token/` → janitor skips (defense-in-depth, doesn't rm) |
| `test_janitor_called_from_app_startup_lifespan` | TestClient lifespan kick → janitor.sweep_expired_sessions ran (use monkeypatch counter) |
| `test_janitor_called_at_end_of_process_request` | call /process → janitor was called (monkeypatch counter) |
| `test_janitor_failure_does_not_taint_request` | monkeypatch janitor.sweep_expired_sessions to raise → /process still returns 200 |

**Fixture pattern (mirror conftest.py):** can reuse `client` + `valid_pdf_bytes` + `ingested_session`. For mtime manipulation: `os.utime(path, (time.time() - 3700, time.time() - 3700))`.

---

### `tests/test_integrity.py` (NEW test file)

**Closest analog:** `tests/test_ingest.py:26–30` (existing hashlib + storage.original_path pattern).

**Tests to include:**

| Test name | Asserts |
|-----------|---------|
| `test_compute_original_hash_matches_hashlib` | `compute_original_hash(b"x")` == `hashlib.sha256(b"x").hexdigest()` |
| `test_verify_original_hash_passes_on_unchanged_session` | ingest → verify_original_hash → no raise |
| `test_verify_original_hash_raises_on_tampered_original` | ingest → chmod 0o644 → mutate → chmod 0o444 → verify → raises IntegrityError("original_tampered") |
| `test_verify_marks_session_corrupted_on_tamper` | after tamper detection → `is_session_corrupted(sid)` is True |
| `test_verify_treats_legacy_session_as_corrupted` | strip `original_sha256` from meta.json → verify → raises IntegrityError("session_corrupted") |
| `test_verify_treats_missing_meta_as_corrupted` | delete meta.json → verify → raises IntegrityError("session_corrupted") |
| `test_integrity_module_does_not_import_fitz` | `import app.services.integrity` → `fitz` not in module imports (AGPL seam preservation) |

---

### `tests/test_health.py` (NEW test file)

**Closest analog:** `tests/test_api.py` lines 1–95 (existing TestClient pattern for endpoint tests).

**Tests to include:**

| Test name | Asserts |
|-----------|---------|
| `test_health_returns_ok_status` | GET /health → 200, JSON `status == "ok"` |
| `test_health_includes_uptime_seconds` | uptime_seconds is a float >= 0 |
| `test_health_includes_active_sessions_count` | after 2 uploads → active_sessions == 2 |
| `test_health_includes_data_dir_fields` | data_dir_bytes is int, data_dir_pct is float in 0..100 |
| `test_health_active_sessions_minus_one_on_unreadable` | chmod 0 on originals/ → active_sessions == -1 |
| `test_health_does_not_leak_session_ids` | response body must NOT contain any session_id (info disclosure guard) |

---

## Shared Patterns

### Typed `*Error(code, message)` + `main.py` `_PROCESS_STATUS` dict routing

**Source:** Established pattern across `services/ingest.py:62–68` (IngestError), `services/logo.py:31–42` (LogoError), `services/pipeline.py:43–49` (PipelineError), `services/redact.py:60` (RedactError), `services/render.py` (RenderError), `services/pdf_engine.py` (PdfEngineError), `storage.py:47–53` (InvalidSessionId).

**Apply to:** All Phase 5 new error pathways. The new codes (`original_tampered`, `session_corrupted`, `processing_timeout`) flow through the existing `PipelineError` channel — no new exception handler class needed. Only the `_PROCESS_STATUS` dict at `main.py:92–96` extends with three entries.

**Concrete shape (every service error follows this):**
```python
class FooError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
```

---

### Lazy `config` resolution + `subdir`-routed path-traversal guard

**Source:** `storage.py:80–101` (`subdir` validates session_id via `_SESSION_ID_RE` + asserts containment under `DATA_DIR` before returning a path).

**Apply to:** Every new helper that touches the filesystem with a session_id arg (`mark_session_corrupted`, `is_session_corrupted`, `delete_session`, janitor's `_delete_session`, `_session_max_mtime`). Each MUST route through `storage.subdir(kind, sid)` so an untrusted id can never become a path segment without first passing `validate_session_id`.

**Concrete excerpt (`storage.py:85–101`):**
```python
def subdir(kind: str, session_id: str) -> Path:
    if kind not in _KINDS:
        raise ValueError(f"unknown storage kind: {kind!r}")
    validate_session_id(session_id)
    data_dir = _data_dir()
    dest = data_dir / kind / session_id
    resolved = dest.resolve()
    if not resolved.is_relative_to(data_dir.resolve()):
        raise InvalidSessionId(f"invalid session id: {session_id!r}")
    return dest
```

---

### Env-var configuration via `_env_int` + module-top constant

**Source:** `config.py:19–73`.

**Apply to:** All 5 Phase 5 constants. `_env_int(name, default)` for integers; `os.environ.get(name, default)` for strings.

---

### `from __future__ import annotations` + module docstring naming the security property

**Source:** Every existing `app/services/*.py` and `app/api/*.py`. See `storage.py:1–14`, `services/ingest.py:1–24`, `services/logo.py:1–18`, `services/pipeline.py:1–25`.

**Apply to:** `app/services/integrity.py` and `app/services/janitor.py`. Module docstring must name the security/correctness property being enforced (D-05 runtime enforcement for integrity; 4-kind TTL sweep + Pitfall 3 cross-platform for janitor) AND explicitly state the AGPL seam (no fitz import; stdlib only).

---

### 繁中 (Traditional Chinese) error messages

**Source:** Every typed error message across `services/ingest.py:139–141, 246–248`, `services/pipeline.py:118–121, 131–134, 168–170`, `services/logo.py`, `api/sessions.py:64–67`. All user-facing messages are Traditional Chinese; English appears only in code identifiers + logs.

**Apply to:** All Phase 5 new error messages:
- `"系統偵測到原始檔異常,此工作階段已停用,請重新上傳檔案。"` (original_tampered)
- `"此工作階段為舊版或資料不完整,請重新上傳檔案。"` (session_corrupted, legacy)
- `"此工作階段已標記為異常,請重新上傳檔案。"` (session_corrupted, runtime)
- `"處理逾時(超過 X 秒),請改用較小檔案或減少框選區域數量。"` (processing_timeout)

---

### `try/except: pass` around janitor calls (best-effort, never tainting requests)

**Source:** Phase 5 NEW pattern (RESEARCH.md lines 538–541, 535).

**Apply to:** Every janitor call site (`api/sessions.py` POST end, `api/process.py` POST end, `main.py` lifespan startup). Janitor failures are logged inside the function (`logger.warning(...)`); the caller never sees the exception. This is non-negotiable — a sweep failure must not 500 the user's upload/process.

```python
finally:
    try:
        janitor.sweep_expired_sessions()
    except Exception:
        pass  # janitor logs internally; never taint the response
```

---

### AGPL seam: no `import fitz` outside `pdf_engine.py`

**Source:** Phase 1–4 lock + `services/logo.py:1–18` module docstring statement + Phase 1–4 enforced by test (`test_fitz_import_confined_to_engine_seam`).

**Apply to:** `services/integrity.py` (uses `hashlib` stdlib only), `services/janitor.py` (uses `shutil`/`os` stdlib only), `app/__main__.py` (uses `uvicorn`/`webbrowser`/`threading` only). Confirm with the existing enforcement test — Phase 5 modifications MUST keep it passing.

---

## No Analog Found

Files for which no in-repo analog exists — planner should source patterns from RESEARCH.md / STACK.md as cited:

| File | Role | Source |
|------|------|--------|
| `Dockerfile` | NEW infrastructure | RESEARCH.md Pattern 1 (lines 280–344) — multi-stage `python:3.12-slim-bookworm` |
| `.dockerignore` | NEW infrastructure | RESEARCH.md Pattern 1 (lines 354–373) |
| `docker-compose.example.yml` | NEW infrastructure | RESEARCH.md Standard Stack + D-A1 (single-container example + commented nginx) |
| `LICENSE` | NEW legal | FSF canonical AGPL-3.0 text (https://www.gnu.org/licenses/agpl-3.0.txt) — copy verbatim |
| `README.md` | NEW docs | RESEARCH.md Pattern 9 + §"Recommended File Tree" — three deploy targets + env var table |
| `zeabur.json` (optional) | NEW infrastructure | RESEARCH.md line 84 (PORT env var convention) — Zeabur auto-detects Dockerfile, so this file is usually unnecessary; create only if a specific Zeabur build-trigger config is needed |
| `tests/test_health.py` | NEW test | shape mirrors `tests/test_api.py` (TestClient endpoint test) |
| `tests/test_janitor.py` | NEW test | shape mirrors `tests/test_storage.py` (lifecycle + isolated_data_dir) |
| `tests/test_integrity.py` | NEW test | shape mirrors `tests/test_ingest.py` (hash assertions + IngestError-style raises) |
| `app/__main__.py` | NEW entry | RESEARCH.md Pattern 3 (lines 417–474) — `uvicorn.run` + `threading.Timer(1.0, webbrowser.open)` |

---

## Cross-cutting Pitfall Index (for planner `<read_first>` lists)

| # | Pitfall | Affected files | Source |
|---|---------|----------------|--------|
| 1 | `asyncio.wait_for(asyncio.to_thread(...))` cannot kill the thread | `app/api/process.py` | RESEARCH.md Pitfall 1 (line 1144) |
| 2 | `python:3.12-slim` has no curl/wget | `Dockerfile` | RESEARCH.md Pitfall 2 (line 1158) |
| 3 | `shutil.rmtree` on chmod 0o444 originals/source.pdf on Windows | `app/services/janitor.py`, `app/storage.py` (delete_session) | RESEARCH.md Pitfall 3 (line 1175) |
| 4 | meta.json schema migration (legacy sessions lack `original_sha256`) | `app/services/integrity.py` | RESEARCH.md Pitfall 4 (line 1187) |
| 5 | `FastAPI(root_path=...)` + StaticFiles `html=True` redirect bug | `app/main.py`, `README.md` | RESEARCH.md Pitfall 5 (line 1197) |
| 6 | AGPL §13 internal != exempt | `LICENSE`, `README.md`, `web/index.html` | RESEARCH.md Pitfall 6 (line 1211) |
| 7 | uvicorn `--workers > 1` on Windows requires spawn-safe modules | `app/__main__.py`, `app/main.py` (_START_TIME) | RESEARCH.md Pitfall 7 (line 1221) |
| 8 | `shutil.disk_usage` reports filesystem-level (not session-level) usage | `app/main.py` (/health) | RESEARCH.md Pitfall 8 (line 1241) |
| 9 | Zeabur free-tier resource limits (vague vendor docs) | deploy planning | RESEARCH.md Pitfall 9 (line 1251) |
| 10 | Multi-stage build cache invalidation by `requirements.txt` order | `Dockerfile` | RESEARCH.md Pitfall 10 (line 1264) |
| A7 | `tempfile.mkstemp(dir=...)` cross-drive on Windows = non-atomic | `app/storage.py` (write_session_meta) | RESEARCH.md A7 (line 1397) |

---

## Metadata

**Analog search scope:**
- `app/` (config, main, storage, services/*, api/*) — read in full
- `web/` (index.html, js/api.js, js/app.js, styles/app.css) — read targeted sections
- `tests/` (conftest, test_storage, test_process_api, test_api, test_ingest) — read targeted sections
- `requirements.txt`, repo root for Dockerfile / README (none found — confirms "no analog" classification)
- `.planning/phases/05-ubuntu/05-CONTEXT.md` — full read (decisions + canonical refs)
- `.planning/phases/05-ubuntu/05-RESEARCH.md` — targeted reads (Pattern 1–9, Pitfall 1–10, Architecture Map)

**Files scanned:** 18 Python files + 3 JS + 1 HTML + 1 CSS + 2 planning artifacts = 25
**Pattern extraction date:** 2026-05-23
