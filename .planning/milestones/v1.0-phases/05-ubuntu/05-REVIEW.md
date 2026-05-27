---
phase: 05-ubuntu
reviewed: 2026-05-24T00:00:00Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - Dockerfile
  - .dockerignore
  - docker-compose.example.yml
  - LICENSE
  - README.md
  - app/__main__.py
  - app/config.py
  - app/main.py
  - app/storage.py
  - app/services/integrity.py
  - app/services/janitor.py
  - app/services/ingest.py
  - app/services/pipeline.py
  - app/api/process.py
  - app/api/sessions.py
  - web/index.html
  - web/js/app.js
  - web/styles/app.css
  - tests/test_api.py
  - tests/test_integrity.py
  - tests/test_janitor.py
  - tests/test_health.py
  - tests/test_storage.py
  - tests/test_ingest.py
  - tests/test_process_api.py
findings:
  critical: 2
  warning: 7
  info: 6
  total: 15
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-24
**Depth:** standard
**Files Reviewed:** 24
**Status:** issues_found

## Summary

Phase 5 (deploy + hardening) is structurally sound. AGPL seam preserved (only `pdf_engine.py` imports `fitz`; both new modules `integrity.py` + `janitor.py` are stdlib-only and enforced by AST grep tests), atomic meta.json writes use the correct `tempfile.mkstemp` + `os.replace` pattern, path-traversal goes through the existing `_SESSION_ID_RE` allowlist, the Pitfall 3 cross-platform chmod 0o444 handler is centralized, the asyncio-thread-cannot-be-killed pitfall is documented inline, frontend writes via `textContent` (no `innerHTML`), and the Dockerfile uses non-root user + stdlib `urllib` HEALTHCHECK.

Two **BLOCKER** issues found:

1. **CR-01 (BLOCKER):** `lifespan` startup janitor silently swallows ALL exceptions with bare `except Exception: pass` — including `KeyboardInterrupt`-adjacent issues like `BaseException` subclasses are excluded, **but** logging is also dropped, so a misconfigured `DATA_DIR` (wrong path, permission denied, full disk) will cause every uvicorn worker to silently start up with a broken data root — the first user upload then fails opaquely. The plan acknowledged "wrap in try/except so startup janitor failure cannot prevent the app from coming up", but a `logger.warning(...)` would cost nothing and give ops the diagnostic.

2. **CR-02 (BLOCKER):** Phase 5 corrupted-session gate is **only enforced on `/process`** (`api/process.py:72`). `GET /sessions/{id}/result/pages/{n}/image` (the "移除結果" after-image) and `GET /sessions/{id}/result` (download) do NOT check `is_session_corrupted` — yet the contract per CONTEXT line 60 says "之後該 session 所有 /process、GET /result、GET /pages 都中止" (Plan D-C3). If a session is marked `.corrupted` (e.g., the user retries after a previous tamper-detect 503), `GET /result` will still happily stream the **stale pre-tamper output PDF** that was produced by an earlier process run. This violates the fail-closed contract.

Five **WARNING** issues touch race conditions, error handling, frontend layout fragility, and a subtle SHA-256-baseline-corner. The remaining items are info-level nits and comment hygiene drift.

All 24 files were read in full. Test files were inspected for TDD compliance, isolation, and adversarial coverage.

## Findings by Severity

### Critical Issues

#### CR-01: Startup janitor swallows ALL exceptions with no diagnostic — silently masks misconfigured DATA_DIR

**File:** `app/main.py:52-55`
**Severity:** BLOCKER
**Issue:**
```python
try:
    janitor.sweep_expired_sessions()
except Exception:
    pass
```
The bare `except Exception: pass` discards every diagnostic. If `DATA_DIR` is unwritable / mistyped / on a missing volume mount (Docker volume not attached, Zeabur env mis-set, Windows drive-letter typo on the local Python package target), the operator gets ZERO signal at boot — the app stays up, returns 200 on `/health` (which itself swallows `OSError` for `data_dir_bytes`), and only the first user upload fails. This is exactly the class of "silent broken deployment" Phase 5's `/health` was supposed to surface.

Note: `janitor.sweep_expired_sessions()` itself already catches `OSError` + `Exception` per-session (janitor.py:48-53, 74-76) and returns `0`, so the **only** way this outer block fires is for an exception class the janitor itself didn't catch (e.g., a programming error like `AttributeError`, or a `BaseException`-adjacent type the inner handler missed). Both deserve a log line, not silence.

**Fix:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        janitor.sweep_expired_sessions()
    except Exception:
        # Startup must not depend on the sweep — but ops needs the diagnostic.
        import logging
        logging.getLogger(__name__).warning(
            "lifespan: startup janitor sweep failed", exc_info=True
        )
    yield
```

The same defect exists at `app/api/process.py:113-116` and `app/api/sessions.py:82-85` — both `finally: try ... except Exception: pass` blocks silently drop diagnostics. Mitigation is the same: log at WARNING with `exc_info=True`. Worth fixing in the same patch (the test `test_janitor_failure_does_not_taint_process_request` only asserts the 200 response stays clean; a logged warning does not change that test's outcome).

#### CR-02: `.corrupted` sentinel is NOT enforced on `GET /result` or `GET /result/pages/{n}/image` — contract violation

**File:** `app/api/process.py:119-194` (the two GET endpoints) + `05-CONTEXT.md:60` (decision D-C3)
**Severity:** BLOCKER
**Issue:** Decision D-C3 states (verbatim, CONTEXT line 60): "標記 session corrupted(寫一個 work/{sid}/.corrupted sentinel file;**之後該 session 所有 /process、GET /result、GET /pages 都中止**)". The current implementation gates ONLY `POST /process` (process.py:72). After an `original_tampered` event:

1. User retries `POST /process` → 410 `session_corrupted` (correct).
2. User clicks the download button (front-end calls `GET /sessions/{sid}/result`) → 200 streams the **stale pre-tamper output PDF** that the earlier successful process run wrote to `outputs/{sid}/`. The user gets a PDF that does NOT correspond to the current (tampered) source.
3. User clicks "show me the result preview" → `GET /result/pages/0/image` renders from the **work copy** which is also pre-tamper. Same disclosure.

This is a real defect (the work copy and outputs file are NOT cleared when the sentinel is written — see `integrity.verify_original_hash` and `storage.mark_session_corrupted`). The Plan summary (Plan-05-02) may have re-scoped this to "process only" but the CONTEXT lock is the canonical source and the user-facing UX is wrong either way.

**Fix:** Add the same short-circuit to both result endpoints:
```python
# In get_result_page_image and download_result, after _require_session:
if storage.is_session_corrupted(session_id):
    raise HTTPException(
        status_code=410,
        detail={
            "code": "session_corrupted",
            "message": "此工作階段已標記為異常,請重新上傳檔案。",
        },
    )
```

Alternatively (cheaper but more invasive): on `mark_session_corrupted`, also `unlink` the outputs file and the work copy. The sentinel-gate approach is preferred — keeps the storage layer dumb.

Add tests:
- `test_corrupted_session_blocked_from_get_result_download` → 410
- `test_corrupted_session_blocked_from_result_page_image` → 410

### Warning

#### WR-01: `app/__main__.py` ignores empty-string / non-integer `UVICORN_WORKERS` → `int("")` raises ValueError at startup

**File:** `app/__main__.py:39`
**Issue:**
```python
workers = int(os.environ.get("UVICORN_WORKERS", "1"))
```
Compare to `config._env_int` (config.py:19-26), which carefully handles `None`, empty string, and non-integer — falling back to default. `app/__main__.py` does NOT reuse `_env_int`. If a user sets `UVICORN_WORKERS=` (empty, common when a deploy template clears it) or `UVICORN_WORKERS=auto`, `python -m app` crashes with `ValueError: invalid literal for int()`. The same bug applies to `PORT` (line 38).

**Fix:**
```python
from .config import _env_int  # or duplicate the small helper

workers = _env_int("UVICORN_WORKERS", 1)
port = _env_int("PORT", 8000)
```

Note also that the docstring (lines 12-15) says default workers is 1, but the README §"Environment Variables" table (line 139) says "2 (Docker) / 1 (`python -m app`)" — confirming there are two intended defaults driven by entry point, not env. This is consistent but the implementation should be robust to bad input.

#### WR-02: `/health` `active_sessions` only counts `originals/` — undercounts during the image-ingest race window

**File:** `app/main.py:253-263`
**Issue:** `active_sessions` is computed by iterating `originals/` only. For image uploads, `new_session()` creates all four kind dirs upfront but `write_original` (which gives `originals/` its non-empty marker) is called AFTER `_ingest_image()` (Pillow chain — up to ~hundreds of ms for a 50MB JPEG). During that window the session exists in `work/` and `pristine/` but `originals/{sid}` is empty — it is `is_dir()` (true, created by `new_session`) but has no `source.pdf`. The current implementation counts it correctly because it checks `entry.is_dir()`, not `(entry / "source.pdf").exists()`. So this is FINE for the count, but the choice to look at `originals/` only is brittle: if a future change ever moves session creation to NOT create the `originals/{sid}` dir until after ingest completes (e.g., to avoid creating empty dirs), `active_sessions` will silently start undercounting. The semantic should be "well-formed sessions" — which storage already exposes via `list_session_ids()`.

**Fix:** Replace the inline directory scan with `list(storage.list_session_ids())` for the count. Same behavior today (because both walk `_KINDS` / one kind), but it's the canonical "well-formed session" surface, won't drift, and is already covered by unit tests. Defense-in-depth: enumeration failure already collapses to `-1`.

#### WR-03: Storage `session_age_seconds` ignores file-level mtimes — janitor protects sessions whose only fresh activity was a recent read

**File:** `app/storage.py:358-381`
**Issue:** `session_age_seconds` uses `subdir(kind, sid).stat().st_mtime` — i.e., the DIRECTORY mtime per kind. Directory mtime updates on file create/delete/rename, but **not** on file content rewrites (POSIX behavior, also Windows NTFS default). So:

- User uploads → `originals/{sid}` mtime updates (file created).
- 30 minutes later, user does `/process` → `outputs/{sid}/result.pdf` is created → `outputs/{sid}` mtime updates. ✔
- 30 minutes later, user does `/process` AGAIN (reset-from-pristine + same region) → `outputs/{sid}/result.pdf` is OVERWRITTEN (atomic swap via `.replace`, which is an unlink+create from the dir's POV — this WILL update mtime on POSIX, but the behavior is FS-dependent). Phase 5 plan says "outputs/ may be freshly produced from a /process run" (storage.py:362-364) which is correct on most FSes, but the comment doesn't acknowledge the per-FS variance.

Worse case: with `pipeline.process_job` using `Path(out_tmp).replace(out_file)` (pipeline.py:379), the outputs dir mtime DOES bump (rename is a dir op). So the user-facing behavior is fine. But this is fragile against future refactors that might overwrite-in-place via `open(..., "wb")`.

**Fix:** Either (a) add a small comment noting the dependency on rename-based atomic replace (the relevant lines in pipeline.py:374-379 already do this — cross-reference it), OR (b) walk one level into each kind dir and take the max file mtime too. (a) is cheaper and the current code is correct; (b) is more future-proof. Recommend (a).

#### WR-04: Janitor `deleted` counter races against partial-success rmtree — count can be misleading on Windows

**File:** `app/services/janitor.py:65-73`
**Issue:**
```python
storage.delete_session(sid)
if not any(
    (config.DATA_DIR / kind / sid).exists()
    for kind in ("originals", "work", "outputs", "pristine")
):
    deleted += 1
```
On Windows, if a file inside `work/{sid}/` is held open by another process (Windows file locks are mandatory), `_on_rm_error` retries with chmod but if the OPEN HANDLE is held, the chmod-retry also fails — `delete_session` logs and returns; `subdir/originals/{sid}` was already gone, but `subdir/work/{sid}` remains with the stuck file. The `if not any(...)` returns False → `deleted` is not incremented → caller sees 0. But the originals/outputs/pristine dirs WERE deleted; the session is in a half-state.

The actual harm is small (next sweep retries, the locked handle eventually releases, the next sweep finishes the job), but `deleted` is the **only** observable signal the function returns to test code, and it can return 0 even when 3/4 dirs were successfully reclaimed — making the test `test_janitor_sweeps_expired_session` (`tests/test_janitor.py:32`: `assert deleted >= 1`) potentially flaky on Windows under load.

**Fix:** Either:
1. Log the half-deleted state explicitly:
   ```python
   if all((config.DATA_DIR / kind / sid).exists() == False for kind in _KINDS):
       deleted += 1
   else:
       logger.warning("janitor: partial delete for %s — some kind dirs remain", sid)
   ```
2. OR count "made progress" (i.e., at least one kind dir was removed) — better for the partial-success case but harder to reason about.

#### WR-05: Janitor calls `delete_session` AFTER reading `session_age_seconds(sid)` — TOCTOU on a session that finished /process between the two calls

**File:** `app/services/janitor.py:56-65`
**Issue:** Sequence:
```python
mtime_age = storage.session_age_seconds(sid)
if mtime_age < ttl:
    continue
storage.delete_session(sid)
```
Between line 58 and line 65, another worker's `/process` (the OTHER worker — `UVICORN_WORKERS=2`) could:
1. Touch `outputs/{sid}` (writing the result PDF) — bumping mtime.
2. Reset the work copy mid-redaction.

The sweep then `rmtree`s `outputs/{sid}/result.pdf` mid-write — the user's `/process` response is 200 but `GET /result` returns 404 `result_not_ready`. The D-B4 race comment (storage.py:14-15, janitor.py:13-15) says "TTL ≫ /process timeout (60s default), so an in-flight job cannot age out mid-run" — TRUE for the in-flight case (the session was actively being processed for at least one timeout interval before the sweep), but FALSE for the "1-hour-old session, user clicks /process at minute 59:59" corner.

In practice, the user would need to start `/process` within the ~milliseconds between the `session_age_seconds` call and the `delete_session` call AFTER the session has already aged past TTL — exceedingly rare. But the mitigation is cheap.

**Fix:** Re-check immediately before deletion:
```python
mtime_age = storage.session_age_seconds(sid)
if mtime_age is None or mtime_age < ttl:
    continue
# Re-check at the last moment (TOCTOU narrowing — not eliminating).
mtime_age_recheck = storage.session_age_seconds(sid)
if mtime_age_recheck is None or mtime_age_recheck < ttl:
    continue
storage.delete_session(sid)
```
Acceptable to defer if a test verifies the in-flight protection — but the current tests do not exercise this exact race.

#### WR-06: AGPL `<OWNER>` placeholder ships in `web/index.html` — first deploy will publish a literal broken link unless replaced

**File:** `web/index.html:419` (plus README.md:15, 39, 65, 77 — and **also** the docker image contains LICENSE + README + index.html with the placeholder, baked into the image at line `COPY --chown=app:app web/ /app/web/` in Dockerfile:51).
**Issue:** The `<OWNER>` placeholder appears in:
- `web/index.html` footer (the AGPL §13 disclosure surface visible to every browser user)
- `README.md` (4 occurrences)

If an operator deploys without replacing them, the AGPL §13 disclosure points to `https://github.com/<OWNER>/LogoSwap` which is a 404 — i.e., the network user is NOT given the source. This is the exact compliance failure §13 exists to prevent. There is no automated guard (no CI check for "<OWNER>" being absent from web/ before tagging a release).

**Fix:** Two practical mitigations:
1. **Build-time substitution.** Dockerfile takes a `GITHUB_OWNER` build arg, runs `sed -i "s/<OWNER>/${GITHUB_OWNER}/g" /app/web/index.html /app/README.md` at the runtime stage — fails the build if `GITHUB_OWNER` is empty.
2. **Test guard.** Add a pytest case `tests/test_agpl_compliance.py::test_no_owner_placeholder_in_web` that greps for `<OWNER>` in `web/` files — fails CI when a release tag is being built (gated by an env var or pytest marker, so dev branches still pass).

The README does flag this in `## License & Source` (line 16-17: "部署前必須將 `<OWNER>` 替換為實際的 public GitHub repo owner"), but a documentation note is not the same as an enforceable gate. Memory says "deployment AGPL-compliance三件套" is a hard requirement.

#### WR-07: `app-session-hint` is inserted as a sibling of `<page-stage>` inside `<main>` — breaks the documented `app-shell` 3-row grid layout

**File:** `web/js/app.js:108-112` + `web/styles/app.css:46-49`
**Issue:** CSS:
```css
.app-shell {
  display: grid;
  grid-template-rows: auto 1fr auto;  /* toolbar | main | footer */
}
```
JS (app.js:108-112):
```js
if (stage && stage.parentElement) {
    stage.parentElement.insertBefore(el, stage.nextSibling);
}
```
`stage.parentElement` is `<main class="main">`, NOT `.app-shell`. So the hint is inserted INSIDE `<main>` (a 2-column grid: stage 1fr + side-panel 0). The hint becomes an unexpected third grid cell at row 1 col 1, which collapses to the stage column and pushes the side-panel layout (Phase 2 region UI) down. Visually, this MIGHT look acceptable when the side-panel is collapsed (Phase 1) but will overlap or mis-align as soon as a doc is loaded (`main--paneled` class is on).

The `.app-session-hint` style block (app.css:60-67) has `text-align: center` + `border-top` and the comment says "Lives inside the page-stage container so it sits alongside the preview flow naturally" — but it actually lives as a sibling of `<page-stage>`, not inside it. Either the implementation or the comment is wrong.

**Fix:** Insert the hint as a sibling of `<main>` inside `<app-shell>`, between `<main>` and `<footer>`:
```js
const shell = document.querySelector(".app-shell");
const footerEl = shell.querySelector(".app-footer");
if (footerEl) {
    shell.insertBefore(el, footerEl);
} else {
    shell.appendChild(el);
}
```
And update `.app-shell { grid-template-rows: auto 1fr auto auto; }` if you want the hint to be its own row (or wrap the hint+footer in a single container).

This needs a UAT visual sanity check post-fix; it was not exercised by any test (`web/` has no automated visual / DOM tests, by design — Phase 1 decision).

### Info

#### IN-01: `data_dir_pct` in `/health` divides by `usage.total` without zero-check — `ZeroDivisionError` on certain pseudo-FS mounts

**File:** `app/main.py:268-269`
**Issue:**
```python
data_dir_pct = round(100.0 * usage.used / usage.total, 2)
```
On certain Docker volume drivers (e.g., a tmpfs of size 0, or an unmounted lazy mount), `shutil.disk_usage` can return `total=0`. The current code catches `OSError, FileNotFoundError` (line 270) but NOT `ZeroDivisionError`. A `total=0` here causes the whole `/health` endpoint to 500, taking down the LB probe.

**Fix:** `data_dir_pct = round(100.0 * usage.used / usage.total, 2) if usage.total > 0 else 0.0`, OR add `ZeroDivisionError` to the except tuple.

#### IN-02: `app/storage.py:316` typo in docstring — "namespace" claim about `.meta.*.tmp` is correct but the sentinel is `.corrupted`, not hyphen-prefix

**File:** `app/storage.py:300`
**Issue:** Comment says "Hyphen-prefix avoids colliding with the JSON sidecar's `.meta.*.tmp` namespace." `.corrupted` and `.meta.` both start with a DOT, not a hyphen. The "hyphen-prefix" phrasing is wrong (no hyphen anywhere); it should say "dot-prefix" or simply "the leading dot puts it in the hidden namespace, distinct from `.meta.*.tmp`". A misleading comment cost nothing to fix and saves the next reader a half-hour. Project CLAUDE.md says "no comments unless WHY non-obvious"; this comment is WHY but the wording is wrong.

#### IN-03: Verbose / WHAT-explaining comments drift from the project "no comments unless WHY non-obvious" rule

**Files:** Multiple — examples:
- `app/main.py:42-44` (3-line `_START_TIME` comment is mostly WHAT; the WHY ("per-worker uptime is the desired semantic") is in the function's docstring already)
- `app/services/integrity.py:64-68` (4-line "Side effect order on failure" comment in `verify_original_hash` — useful WHY, but could be tighter)
- `app/services/janitor.py:60-72` (15-line "best-effort cleanup" prose is helpful but borders on overcommenting)
- `app/main.py:140-154` (15-line block-comment over `_PROCESS_STATUS` enumerating 3 codes — adds value once but should not be repeated; the second + third entries in the dict already self-document via the code string)

**Fix:** Cut WHAT-explaining lines; keep the WHY one-liners. Not a blocker — but watch for comment drift in future phases.

#### IN-04: Image-upload `originals/source.pdf` is a misleading on-disk name for raw PNG/JPG/TIFF bytes

**File:** `app/storage.py:75` (`_ORIGINAL_NAME = "source.pdf"`)
**Issue:** For an image upload, `write_original(sid, "scan.png", raw_png_bytes)` writes the raw PNG bytes to `originals/{sid}/source.pdf`. The `.pdf` suffix is misleading — a developer who SSH's into the data volume to debug will reasonably assume that file is a PDF and feed it to `pdfinfo` or similar, getting a confusing "not a PDF" error. The bytes are stored correctly and the verify path round-trips correctly (it reads back the bytes; the suffix is decorative); this is a developer-ergonomics nit.

**Fix:** Either rename the constant to `_ORIGINAL_BASENAME = "source"` (no suffix) and let the on-disk name be just `source`, OR keep the constant but use the sanitized filename's extension (`source.png`, `source.jpg`, etc.). The latter requires changing `verify_original_hash` to discover the file via `glob("source.*")` — more code for small gain. Defer.

#### IN-05: Lifespan `bare except Exception` is paired with `KeyboardInterrupt` / `SystemExit` propagating correctly, but `BaseException` like `MemoryError` propagates through — verify intent

**File:** `app/main.py:54-55` + `app/api/process.py:113-116` + `app/api/sessions.py:82-85`
**Issue:** All three sites use `except Exception:` (not `except BaseException:`). Correct semantics: `KeyboardInterrupt` and `SystemExit` propagate (good — uvicorn restart works). But `MemoryError` is a subclass of `Exception` — it WILL be swallowed. In the janitor case under low memory, that's fine. In the process/sessions cases, the response will return 200 even though the worker is in trouble. Likely acceptable for a v1 LAN tool.

**Fix:** No code change; add a comment acknowledging the choice if intent is intentional. Recommend deferring.

#### IN-06: README §"Embedding Contract" mentions `js/api.js` import; verify spelling consistency

**File:** `README.md:157`
**Issue:** Reads "在 host 頁面注入此 global 前載入 `js/api.js`" — the actual file is `web/js/api.js`. Most readers will get it from context but the `web/` prefix is missing once. Not load-bearing.

**Fix:** Change `js/api.js` → `web/js/api.js` once in the README. Trivial.

## What Was Reviewed

**Source (15 files):**
- Backend: `app/__main__.py`, `app/config.py`, `app/main.py`, `app/storage.py`, `app/services/integrity.py`, `app/services/janitor.py`, `app/services/ingest.py`, `app/services/pipeline.py`, `app/api/process.py`, `app/api/sessions.py`
- Frontend: `web/index.html`, `web/js/app.js`, `web/styles/app.css`
- Deploy: `Dockerfile`, `.dockerignore`, `docker-compose.example.yml`, `LICENSE` (first 50 lines + preamble), `README.md`

**Tests (6 files):**
- `tests/test_integrity.py`, `tests/test_janitor.py`, `tests/test_health.py`, `tests/test_storage.py`, `tests/test_ingest.py`, `tests/test_process_api.py`, `tests/test_api.py`

**Verified properties (passed):**
- AGPL seam intact: `import fitz` appears ONLY in `app/services/pdf_engine.py` (Grep confirmed across `app/`); both new modules `integrity.py` + `janitor.py` carry AST-level grep tests against `fitz` imports.
- Atomic `write_session_meta`: uses `tempfile.mkstemp(dir=dest.parent)` + `os.replace` (Pitfall A7 cross-drive — same-FS guarantee preserved); tmp cleanup on failure exercised by `test_write_session_meta_is_atomic_on_simulated_crash`.
- Path traversal: `list_session_ids`, `session_age_seconds`, `delete_session`, `mark_session_corrupted`, `is_session_corrupted` all route through `subdir(kind, sid)` which validates against `_SESSION_ID_RE` AND asserts `is_relative_to(DATA_DIR)`. Direct `Path.iterdir` in `list_session_ids` filters by `_SESSION_ID_RE` before yielding.
- Pitfall 3 (chmod 0o444 → rmtree on Windows): `_on_rm_error` handler re-chmods on `PermissionError` for `unlink/remove/rmdir`, retries, logs on retry failure. Both `test_delete_session_handles_readonly_original` and `test_janitor_handles_chmod_0o444_originals_cross_platform` exercise the path.
- SHA-256 baseline: `compute_original_hash(data)` hashes the in-memory `data` (NOT a re-read of the on-disk file), then is written into meta.json in the same atomic transaction. Image-upload path correctly hashes raw image bytes (NOT the normalized A4 PDF) → aligns with verify path which reads `originals/` (which holds raw image bytes for image uploads).
- `asyncio.wait_for` + `asyncio.to_thread` timeout: thread-cannot-be-killed pitfall acknowledged inline (process.py:84-92). 504 response is correct.
- Frontend XSS: All new code uses `textContent`; no `innerHTML` introduced. Verified via Grep — only `innerHTML` mentions in `web/js/` are negative assertions in comments.
- Dockerfile: non-root `USER app`, stdlib `urllib.request` HEALTHCHECK (no curl dependency), multi-stage to drop builder layer, `${PORT:-8000}` for Zeabur, optional `--root-path` flag.
- `/health` 5 fields cost-bounded: `active_sessions` uses `iterdir()` on ONE kind dir (O(sessions)), `data_dir_bytes` uses `shutil.disk_usage` (FS metadata, O(1)).
- TDD: RED commit history not directly verified (out of scope of file content), but tests cover failure modes — tamper simulation, legacy meta, timeout via monkeypatch slow function, corrupted gate vs timeout ordering, janitor TTL + race + chmod + non-token dir.

**Tests adequately cover (good):**
- Tamper detection happy + sad path including sentinel side-effect ordering.
- Legacy meta.json (missing `original_sha256`) fail-closed as `session_corrupted`.
- Janitor TTL boundary (3700s > 3600s), max-mtime semantics, chmod 0o444 cross-platform, non-token dir skip, failure-non-raising.
- Timeout via `monkeypatch.setattr(_pipeline, "process_job", slow_process_job)`.
- Corrupted sentinel SHORT-CIRCUITS the timeout (latency assertion `< 1.0s` even with 60s timeout configured).
- `/health` info-disclosure guard (sid not leaked in body) + POSIX `chmod 0` corner for `active_sessions=-1`.

**Tests missing (referenced in BLOCKER findings):**
- `.corrupted` enforcement on `GET /result` and `GET /result/pages/{n}/image` — CR-02.
- `<OWNER>` placeholder absent from `web/` before release — WR-06.

## Verdict

**Status: issues_found — DO NOT merge to a public-deploy tag without addressing CR-02 and WR-06.**

Phase 5 is well-engineered overall — the structural decisions (AGPL seam, atomic meta, sentinel, asyncio timeout, non-root container, stdlib healthcheck, three deploy targets sharing one image) are correct and well-tested for their happy paths. The **two BLOCKER findings are both contract / compliance gaps** that would manifest only when the system is actually deployed to AGPL-applicable public hosting:

- **CR-02 (corrupted-session result/preview gate):** Quick fix (4 lines per endpoint + 2 tests) — must be done before declaring D-C3 met.
- **WR-06 (`<OWNER>` placeholder):** Either build-time substitution or a CI grep. AGPL §13 compliance is the gating condition for Zeabur push (memory-locked). The current state ships a literal broken link.

The other findings are quality / robustness items that do not block the deploy slice closing, but **CR-01 (silent startup failure)** would seriously hurt operability the first time a `DATA_DIR` volume is misconfigured — and the fix is one log line. Worth shipping with the BLOCKER patches.

Recommend: open hotfixes for CR-01 + CR-02 + WR-06 immediately. Bundle WR-01..05 + IN-01 (the divide-by-zero one in particular — that one IS a `/health` 500) into a follow-up hardening pass before the Zeabur push tag.

---

_Reviewed: 2026-05-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
