---
phase: 05-ubuntu
plan: 01
subsystem: infra
tags: [docker, fastapi, uvicorn, agpl, dockerfile, healthcheck, root_path]

requires:
  - phase: 01-input-preview
    provides: FastAPI app + window.PDFTOOL_API_BASE seam + /health endpoint
  - phase: 04-raster-image-support
    provides: full Phase 1–4 feature set ready to be shipped
provides:
  - multi-stage Dockerfile (python:3.12-slim-bookworm + non-root user app + VOLUME /data)
  - .dockerignore filtering planning/tests/data/cache out of the image
  - docker-compose.example.yml (D-A1 single-service + commented strip-prefix nginx)
  - LICENSE (AGPL-3.0 verbatim, 34,523 bytes)
  - README.md (three deploy targets + env var table + embedding contract + Known Limitations)
  - app/__main__.py (`python -m app` desktop entry, host=127.0.0.1 default)
  - APP_BASE_PATH env var → FastAPI root_path (D-A2)
  - /health upgraded to 5 fields (status, uptime_seconds, active_sessions, data_dir_bytes, data_dir_pct)
  - lifespan skeleton ready for Plan 05-02 to fill with janitor.sweep_expired_sessions()
  - UI footer with GitHub source anchor + AGPLv3 link (AGPL §13 third artifact)
affects: [05-02-hardening, future-deployment, future-embedding]

tech-stack:
  added:
    - Docker multi-stage build (python:3.12-slim-bookworm)
    - HEALTHCHECK via stdlib urllib (slim has no curl, Pitfall 2)
    - FastAPI lifespan asynccontextmanager pattern
    - shutil.disk_usage for /health observability
  patterns:
    - sh -c CMD form so $PORT (Zeabur) and ${APP_BASE_PATH:+--root-path ...} expand at start
    - per-worker _START_TIME module-top capture (spawn-safe, Pitfall 7)
    - storage._SESSION_ID_RE reused outside storage to filter /health session count
    - <OWNER> placeholder in README + index.html footer for AGPL §13 deploy-time substitution
    - HOST=127.0.0.1 default in desktop entry (T-05-09)

key-files:
  created:
    - Dockerfile
    - .dockerignore
    - docker-compose.example.yml
    - LICENSE
    - README.md
    - app/__main__.py
  modified:
    - app/config.py (added UVICORN_WORKERS + APP_BASE_PATH)
    - app/main.py (root_path + lifespan skeleton + /health 5-field + _START_TIME + shutil/time/storage imports)
    - web/index.html (AGPL footer block inserted into .app-shell)
    - web/styles/app.css (.app-footer block + grid-template-rows third row)
    - tests/test_api.py (test_health updated to 5-field schema)

key-decisions:
  - "AGPL §13 three-artifact set ships in lockstep: LICENSE + README GitHub URL + UI footer — any one missing breaks compliance"
  - "<OWNER> placeholder reserved in README and index.html footer; substitution is a deploy-ops step, not in this plan's scope"
  - "App image deliberately excludes nginx (D-A1) — reverse proxy / TLS belongs to the deployment target (Zeabur LB / Ubuntu portal nginx)"
  - "HEALTHCHECK uses stdlib urllib not curl because python:3.12-slim ships without curl/wget (Pitfall 2)"
  - "CMD uses sh -c form so $PORT (Zeabur injection) and ${APP_BASE_PATH:+--root-path …} (D-A2 conditional flag) expand at container start"
  - "/health is unauthenticated — it must not leak session_ids, filenames, or paths (T-05-08). Tested via 32-char hex grep guard"
  - "Desktop entry (python -m app) defaults host to 127.0.0.1 (T-05-09); only Dockerfile CMD binds 0.0.0.0"
  - "lifespan(app) skeleton is included now (HARD deliverable) so Plan 05-02 only fills in the body, never changes the FastAPI constructor"
  - "_START_TIME is module-top (per-worker capture) — spawn-safe per Pitfall 7; reports per-worker uptime which is the desired semantic"
  - "FastAPI root_path + StaticFiles(html=True) redirect quirk (#12151) documented in README §Known Limitations as 'experimental'; sub-domain mode is the recommended stable alternative"

patterns-established:
  - "Multi-stage Dockerfile: stage 1 builds wheels into /install, stage 2 COPYs wheels-only — runtime layer has no pip / no build toolchain"
  - "ENV declarations preset Phase 5 constants (APP_BASE_PATH, UVICORN_WORKERS, PROCESS_TIMEOUT_SECONDS, SESSION_TTL_SECONDS, DATA_DIR, LOGOS_DIR) in the image to avoid rebuilds for Plan 05-02"
  - "FastAPI app construction: `FastAPI(title=..., root_path=APP_BASE_PATH, lifespan=lifespan)` — root_path + lifespan together at the seam"
  - "Token-only CSS for new components — `.app-footer` uses var(--color-panel|border|text|text-muted|accent) so dual-theme reskin is automatic"
  - "Test schemas evolve safely: test_health asserts shape + types not exact values (uptime/disk are non-deterministic)"

requirements-completed:
  - SC-1
  - D-A1
  - D-A2
  - D-A3
  - D-A4
  - D-D4
  - AGPL-§13

duration: ~25 min
completed: 2026-05-23
---

# Phase 5 Plan 01: 部署 slice (Dockerfile + desktop entry + /health + AGPL §13) Summary

**多階段 Dockerfile + APP_BASE_PATH/root_path 嵌入 seam + /health 五欄位 observability + AGPL §13 三件套(LICENSE + README + UI footer)同時就位 — Phase 1–4 程式可以被 ship。**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-23T15:36Z
- **Completed:** 2026-05-23T16:01Z
- **Tasks:** 3/3
- **Files modified:** 10 (6 created + 4 modified)
- **Tests:** 243/243 pass (zero regression)

## Accomplishments

- **Three deploy targets** share one codebase, one Dockerfile (D-A4):
  Zeabur (PaaS, root mount, `$PORT` injected) / 本機 Python 套裝 (`python -m app`, loopback) / Ubuntu 公司入口 (compose example + strip-prefix nginx pattern).
- **AGPL §13 three-artifact set ships in lockstep** — LICENSE 34,523 bytes verbatim, README with public GitHub URL placeholder, UI footer with both anchors visible on every page.
- **/health is now observable** — five fields (status / uptime_seconds / active_sessions / data_dir_bytes / data_dir_pct), guarded against session_id leak (T-05-08).
- **APP_BASE_PATH → FastAPI root_path** seam plumbed; default `""` preserves Phase 1–4 root mount, prefix mode opt-in for Ubuntu portal.
- **Lifespan skeleton present** — Plan 05-02 fills body only, no FastAPI-constructor edits required.
- **Desktop entry** — `python -m app` defaults host to 127.0.0.1 (T-05-09), opens browser 1 s after uvicorn binds.

## Task Commits

1. **Task 1: Dockerfile + .dockerignore + docker-compose.example.yml** — `c7dec53` (feat)
2. **Task 2: APP_BASE_PATH + lifespan skeleton + /health 5-field + app/__main__.py** — `7213e61` (feat)
3. **Task 3: LICENSE + README + UI footer + .app-footer CSS** — `bb11c0d` (feat)

## Files Created/Modified

**Created (6):**
- `Dockerfile` — Multi-stage `python:3.12-slim-bookworm`. Non-root user `app` UID 1000 (T-05-02). VOLUME `/data`. HEALTHCHECK via stdlib urllib (Pitfall 2). CMD via `sh -c` so `$PORT` (Zeabur) + conditional `--root-path` (D-A2) expand at start. `requirements.txt` COPY'd before app code for layer-cache stability (Pitfall 10).
- `.dockerignore` — Excludes `.git/`, `.venv/`, `__pycache__/`, `.planning/`, `tests/`, `data/`, `*.log`, `Dockerfile`, `CLAUDE.md`. KEEPS `LICENSE`, `requirements.txt`, `app/`, `web/`, `logos/` in the image.
- `docker-compose.example.yml` — Single `app` service (D-A1: no nginx in image) + commented nginx strip-prefix block as Ubuntu portal reference. Named `.example` so deployers explicitly opt in.
- `LICENSE` — AGPL-3.0 verbatim text fetched from `gnu.org/licenses/agpl-3.0.txt` (34,523 bytes; ASCII; "Version 3, 19 November 2007" header present in first 5 lines).
- `README.md` — Three deploy targets with cross-platform commands (Windows PowerShell + macOS + Linux). Env var reference table. Embedding contract (`window.PDFTOOL_API_BASE` frontend seam + `APP_BASE_PATH` backend seam). Known Limitations including Pitfall 5 (root_path + StaticFiles).
- `app/__main__.py` — Desktop entry. `host="127.0.0.1"` default (T-05-09), `workers=1` default (desktop), `threading.Timer(1.0, webbrowser.open)` 1 s delayed browser open (Pitfall 7). `UVICORN_NO_BROWSER=1` suppresses auto-open.

**Modified (4):**
- `app/config.py` — Appended `UVICORN_WORKERS: int = _env_int("UVICORN_WORKERS", 2)` (D-D2) and `APP_BASE_PATH: str = os.environ.get("APP_BASE_PATH", "")` (D-A2) below `API_TITLE`. Following Phase 1–4 `_env_int` + module-top constant pattern. (SESSION_TTL_SECONDS / PROCESS_TIMEOUT_SECONDS / CORS_ALLOW_ORIGINS deferred to Plan 05-02 to avoid unused-import churn.)
- `app/main.py` — Added `shutil`, `time`, `Path`, `asynccontextmanager` + `storage` import. Added module-top `_START_TIME = time.time()` (per-worker, spawn-safe, Pitfall 7). Added empty `lifespan(app)` skeleton (HARD deliverable). FastAPI now constructed with `root_path=config.APP_BASE_PATH, lifespan=lifespan`. `/health` enhanced to 5 fields — `active_sessions` filtered by `storage._SESSION_ID_RE` (defense in depth — no session_id leak in body).
- `web/index.html` — `<footer class="app-footer" role="contentinfo">` inserted INSIDE `.app-shell` AFTER `</main>` and BEFORE the clear-confirm modal. Contains GitHub source anchor (`<OWNER>` placeholder) + AGPLv3 link, both `target="_blank" rel="noopener"`. Static literals only — no server-message reflection (XSS posture preserved).
- `web/styles/app.css` — `.app-shell` grid-template-rows updated to `auto 1fr auto` (3 rows). New `.app-footer` block uses only token vars (`--color-panel`, `--color-border`, `--color-text`, `--color-text-muted`, `--color-accent`, `--space-sm`, `--space-lg`, `--font-size-small`). Link uses `--color-text` + underline; only hover reaches `--color-accent` (Phase 1 rule: accent reserved for primary CTA).
- `tests/test_api.py` — `test_health` updated from `assert resp.json() == {"status": "ok"}` to shape + types assertion against the 5-field schema. Uptime/disk values are non-deterministic so exact-value comparison is replaced with `>= 0`, `isinstance(int|float)`.

## Decisions Made

See `key-decisions` in frontmatter (10 items). Highlights:

- **AGPL §13 three-artifact set is atomic** — any single artifact missing breaks compliance. All three shipped in Task 3 (single commit `bb11c0d`).
- **`<OWNER>` placeholder convention** — README and footer both carry the placeholder. Replacement is a deploy-ops gate (must happen before pushing to public GitHub). Plan-level scope explicitly excludes the substitution.
- **Image does NOT contain nginx (D-A1)** — Reverse proxy / TLS is the deployment target's concern. App image stays a clean uvicorn-only ASGI server. The commented nginx block in `docker-compose.example.yml` documents the strip-prefix pattern without forcing it.

## Deviations from Plan

**None — plan executed exactly as written.**

The plan was unusually thorough (PATTERNS.md gave line-precise analogs for every file; RESEARCH.md gave verbatim code excerpts; CONTEXT.md locked all decisions D-A1..D-A4 + D-D4). No bugs found, no missing-critical to add inline, no blocking issues, no architectural surprises. All three tasks landed first-try and 243/243 tests stayed green.

## Issues Encountered

**None blocking.** Two minor environment quirks observed but not deviations:

1. **MSYS bash POSIX-path-mangling for `APP_BASE_PATH=/pdf-logo`** — Running env-var override via Git Bash on Windows would silently rewrite `/pdf-logo` to `C:/Program Files/Git/pdf-logo`. This is a shell artefact, not a code bug. Verified the fix with `MSYS_NO_PATHCONV=1 APP_BASE_PATH=/pdf-logo python -c …` which correctly yielded `app.root_path == '/pdf-logo'`. Documented here for future executors on Windows.
2. **`active_sessions` in dev /health probe returned 142** — Because the dev `./data/` carried real session dirs from Phase 1–4 UAT runs. Expected behaviour; on a fresh Docker volume or Zeabur deploy this would be 0.

## Plan-level Verification Results

| # | Check | Result |
|---|-------|--------|
| 1 | `docker build -t logoswap .` exit 0; image size | **Deferred to UAT** — Docker not installed on dev machine (per memory `project_deployment_licensing.md`, Zeabur builds the image remotely; Ubuntu is long-term). Dockerfile validated by source-grep + structural assertions instead. |
| 2 | `docker run … && curl /health` 200 + 5 fields | **Deferred to UAT** — see above. /health 5-field schema verified via FastAPI `TestClient` against the in-process app (passes). |
| 3 | `python -m app` boots uvicorn + browser opens | **Module import + shape verified** — `app.__main__.main` callable, `threading.Timer(1.0, ...)`, `127.0.0.1` default, `uvicorn.run("app.main:app", ...)` all grep-present. Manual interactive boot left to UAT (would require Ctrl-C handling here). |
| 4 | `APP_BASE_PATH=/pdf-logo` → `app.root_path == '/pdf-logo'` | **PASS** — `MSYS_NO_PATHCONV=1 APP_BASE_PATH=/pdf-logo python -c "from app.main import app; assert app.root_path == '/pdf-logo'"` exit 0. |
| 5 | `pytest tests/` zero regression | **PASS — 243/243 passed in 8.10s.** |
| 6 | LICENSE + README + footer AGPL §13 set | **PASS** — `test -f LICENSE && grep "Version 3" && grep "AGPLv3" web/index.html && grep "AGPL" README.md` exit 0. |
| 7 | /health 5 fields | **PASS** — `TestClient(app).get('/health')` returns `{"status":"ok","uptime_seconds":0.16,"active_sessions":N,"data_dir_bytes":N,"data_dir_pct":N}`. |
| 8 | /health no session_id leak | **PASS** — `re.search(r'[a-f0-9]{32}', r.text)` returned None. |
| 9 | UI footer dark+light theme visual | **Deferred to phase-level UAT** — Plan does not require manual visual check per its own success_criteria. Token-only CSS guarantees dual-theme inheritance structurally. |

## Pitfall 5 (root_path + StaticFiles) Observation

With default `APP_BASE_PATH=""`, `TestClient(app).get('/')` returned 200 + full index.html with footer + AGPLv3 + github.com all present. Phase 1–4 behaviour is byte-for-byte preserved at root mount. Prefix mode (`APP_BASE_PATH=/pdf-logo`) verified to flip `app.root_path` correctly but the StaticFiles redirect behaviour under a real strip-prefix proxy must be tested at deploy-time on the actual nginx config — README §Known Limitations marks this as experimental per the Pitfall 5 disposition (accept + document).

## Known Stubs

None. Every Phase 5 Plan 01 deliverable is implemented; lifespan body is deferred to Plan 05-02 (planned, scheduled, signature stable) — that is a forward seam, not a stub.

## Threat Flags

None. All Phase 5 Plan 01 threats (T-05-01 multi-stage, T-05-02 non-root, T-05-03 AGPL §13, T-05-08 /health minimization, T-05-09 desktop loopback bind, Pitfalls 2/5/7/10) are addressed within this plan; the threat surface introduced by Plan 05-02 (SHA-256 baseline, janitor, /process timeout, .corrupted sentinel) is out-of-scope for this plan and registered for 05-02.

## Items Carried to Plan 05-02

- `app/main.py` lifespan body — fill in `janitor.sweep_expired_sessions()`
- `app/config.py` — append `SESSION_TTL_SECONDS`, `PROCESS_TIMEOUT_SECONDS`, `CORS_ALLOW_ORIGINS`
- `app/services/janitor.py` — new module (sweep_expired_sessions + _on_rm_error + cross-platform chmod 0o444 unlink)
- `app/services/integrity.py` — new module (compute_original_hash + verify_original_hash + IntegrityError)
- `app/storage.py` — `write_session_meta` atomic + `original_sha256` required field + `list_session_ids` / `session_age_seconds` / `delete_session` / `mark_session_corrupted` / `is_session_corrupted` helpers
- `app/api/process.py` — corrupted gate + `asyncio.wait_for(asyncio.to_thread(...))` 60s timeout + finally-block janitor sweep
- `app/api/sessions.py` — finally-block janitor sweep
- `app/services/ingest.py` + `app/services/pipeline.py` — wire SHA-256 baseline at ingest + verify at /process entry
- `web/js/app.js` — three new error codes (`original_tampered` / `session_corrupted` / `processing_timeout`) → 繁中 messages
- New test files: `tests/test_janitor.py`, `tests/test_integrity.py`, `tests/test_health.py` (extended)

## OWNER Placeholder Substitution

`<OWNER>` placeholder lives in TWO places (must be replaced together before any deploy):
1. `README.md` — 5 occurrences (License & Source section + each Deploy Target git URL)
2. `web/index.html` — 1 occurrence (footer GitHub anchor)

Substitution is a **deploy-ops gate** (memory-locked `project_deployment_licensing.md`): public GitHub repo created → LICENSE pushed → `<OWNER>` replaced → push → Zeabur connects. This is out-of-scope for the plan itself; documented here so the deployer cannot miss either location.

## Self-Check: PASSED

- File `Dockerfile`: **FOUND**
- File `.dockerignore`: **FOUND**
- File `docker-compose.example.yml`: **FOUND**
- File `LICENSE`: **FOUND** (34,523 bytes)
- File `README.md`: **FOUND**
- File `app/__main__.py`: **FOUND**
- File `app/config.py`: **MODIFIED** (UVICORN_WORKERS + APP_BASE_PATH appended)
- File `app/main.py`: **MODIFIED** (root_path + lifespan + /health 5-field + _START_TIME)
- File `web/index.html`: **MODIFIED** (app-footer block added)
- File `web/styles/app.css`: **MODIFIED** (.app-footer block + grid third row)
- Commit `c7dec53`: **FOUND** (Task 1)
- Commit `7213e61`: **FOUND** (Task 2)
- Commit `bb11c0d`: **FOUND** (Task 3)

---
*Phase: 05-ubuntu*
*Completed: 2026-05-23*
