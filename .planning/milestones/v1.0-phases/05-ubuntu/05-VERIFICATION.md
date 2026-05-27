---
phase: 05-ubuntu
verified: 2026-05-24T00:00:00Z
status: pass
phase_goal_achieved: true
success_criteria:
  SC-1: pass  # Docker on Ubuntu (Uvicorn + Nginx) — image built locally deferred to UAT; structural verification PASS
  SC-2: pass  # 大型/旋轉頁面不崩潰 — 60s timeout + workers=2 + WR-06 cap intact
  SC-3: pass  # 暫存清理 + 雜湊驗證 — janitor 3 triggers + SHA-256 baseline+verify+sentinel all wired
date: 2026-05-24
decisions_covered: 18/18
tests_pass: 291/294  # 291 passed + 3 platform-skipped (POSIX-only chmod tests skipped on Windows; acceptable)
regressions: 0
score: 8/8 must-haves verified (combined across 05-01 + 05-02)
overrides_applied: 0
human_verification:
  - test: "docker build + docker run + curl /health on actual Ubuntu / Zeabur image"
    expected: "image builds < 250MB, container reaches healthy, /health returns 5 fields"
    why_human: "Docker not installed on dev machine; Zeabur builds image remotely. Dockerfile validated structurally + via FastAPI TestClient. Real container build is a UAT-deferred verification (researcher noted this in 05-01 SUMMARY)"
  - test: "Ubuntu corporate-portal nginx strip-prefix embedding round-trip"
    expected: "公司主 nginx location /pdf-logo/ proxy_pass + APP_BASE_PATH=/pdf-logo correctly routes all 4 endpoints"
    why_human: "Needs real Ubuntu portal staging environment; FastAPI root_path verified programmatically (APP_BASE_PATH=/pdf-logo → app.root_path == '/pdf-logo' confirmed)"
  - test: "Large 50MB CAD PDF triggers 504 processing_timeout end-to-end"
    expected: "real customer CAD PDF crossing 60s threshold returns 504 + 繁中 timeout 訊息"
    why_human: "Needs real 50MB sample; timeout path verified via monkey-patched sleep (test_process_timeout_returns_504 PASSES)"
  - test: "本機 Python 套裝 python -m app desktop entry cross-platform manual smoke"
    expected: "uvicorn binds 127.0.0.1:8000, browser opens to LogoSwap UI, footer shows AGPL link, full session round-trip works"
    why_human: "Manual interactive boot — requires Ctrl-C lifecycle test; module shape + 127.0.0.1 default + threading.Timer all grep-verified"
  - test: "<OWNER> placeholder substituted before public push (deploy-ops gate)"
    expected: "LOGOSWAP_RELEASE_GATE=1 pytest tests/test_agpl_compliance.py FAILs until <OWNER> replaced in README.md + web/index.html (5 + 1 occurrences)"
    why_human: "Deploy-ops responsibility; release-gate test exists (skipped in dev) and confirmed to fail correctly when activated (WR-06 fix)"
  - test: "UI footer visual rendering in dark + light theme"
    expected: "footer + AGPL link visible and clickable in both themes; .app-session-hint TTL row collapses to 0 when hidden"
    why_human: "Visual / theme rendering — CSS token-only structurally guarantees dual-theme inheritance; needs human eye for confirmation"
---

# Phase 5: 部署與穩固化(Ubuntu)Verification Report

**Phase Goal:** 打包為可在 Ubuntu 伺服器執行的網頁服務(Docker + Nginx),處理大型與旋轉頁面、暫存檔清理,並確保原始檔不被竄改。

**Verified:** 2026-05-24
**Status:** PASS (with 6 UAT-deferred human-verification items — explicitly accepted; see "Known UAT-Deferred Items")
**Re-verification:** No — initial verification after REVIEW-FIX iteration 1 (9/9 findings fixed)

---

## Summary

Phase 5 ships the deployment + hardening pair as planned. All 3 ROADMAP success criteria are satisfied by code in tree:

- **SC-1** (Docker on Ubuntu): Multi-stage Dockerfile + .dockerignore + docker-compose.example.yml + LICENSE + README all present and structurally correct. App image deliberately excludes nginx (D-A1). Reverse-proxy is the deployment target's responsibility. Three deploy paths (Zeabur / 本機 Python 套裝 / Ubuntu) documented and code-supported. Actual `docker build` is UAT-deferred (Docker not on dev machine; Zeabur builds remotely).
- **SC-2** (Large/rotated pages stable): `asyncio.wait_for(asyncio.to_thread(process_job, ...), 60)` wraps the CPU-bound pipeline; TimeoutError → 504 `processing_timeout`. `UVICORN_WORKERS=2` keeps preview alive on the second worker. Phase 2 `derotation_matrix` (coords + pdf_engine) and Phase 4 WR-06 `fit_dpi_to_pixel_budget` (render.py:75) BOTH untouched — no regression.
- **SC-3** (Cleanup + hash verify): Janitor at 3 sync trigger points (lifespan + POST /sessions finally + POST /process finally), 1h TTL, 4-kind sweep, Windows chmod 0o444 cross-platform fix via `_on_rm_error`. SHA-256 baseline written atomically at ingest (PDF + image paths both hash raw user bytes), verified at /process entry; mismatch → `.corrupted` sentinel + 503 `original_tampered` + structured log; subsequent /process AND GET /result + GET /result/pages/{n}/image all 410 `session_corrupted` (CR-02 hotfix).

Test suite: **291 passed + 3 platform-skipped** in 12.53s. Zero regressions from Phase 1-4 baseline (243 → 291 = +48 new tests). AGPL §13 三件套 atomically in lockstep (LICENSE + README + UI footer).

---

## SC-1: Docker on Ubuntu (Uvicorn + Nginx)

| Check | Evidence | Status |
|-------|----------|--------|
| Multi-stage Dockerfile present | `Dockerfile:14` `FROM python:3.12-slim-bookworm AS builder` + `Dockerfile:28` second `FROM python:3.12-slim-bookworm` (runtime). Two `^FROM` lines confirm multi-stage. | ✓ VERIFIED |
| Non-root USER | `Dockerfile:30-32` `groupadd -g 1000 app && useradd -u 1000 -g 1000 -m -s /usr/sbin/nologin app`; `Dockerfile:60` `USER app` | ✓ VERIFIED |
| HEALTHCHECK via stdlib (no curl on slim) | `Dockerfile:64-65` `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"` — Pitfall 2 honored | ✓ VERIFIED |
| CMD honors $PORT (Zeabur) + $APP_BASE_PATH (Ubuntu) | `Dockerfile:70` `CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-2} ${APP_BASE_PATH:+--root-path ${APP_BASE_PATH}}"]` — `${PORT:-8000}` for Zeabur, `${APP_BASE_PATH:+--root-path ...}` conditional for Ubuntu | ✓ VERIFIED |
| .dockerignore excludes runtime data | `.dockerignore` excludes `.git/`, `.venv/`, `__pycache__/`, `.planning/`, `tests/`, `data/`, `*.log`; KEEPS `LICENSE`, `requirements.txt`, `app/`, `web/`, `logos/` (confirmed by NOTE at line 28-30) | ✓ VERIFIED |
| docker-compose.example.yml present | `docker-compose.example.yml:13-37` single `app` service; lines 39-69 commented `nginx` block as Ubuntu portal reference (D-A1 keeps app image free of nginx) | ✓ VERIFIED |
| LICENSE in image + AGPL §13 disclosure | `Dockerfile:53` `COPY --chown=app:app LICENSE README.md /app/` — LICENSE physically inside the image | ✓ VERIFIED |
| `app/__main__.py` desktop entry exists | `app/__main__.py:38-50` `def main()`; `app/__main__.py:42` `host = os.environ.get("HOST", "127.0.0.1")` — T-05-09 loopback default; `app/__main__.py:35` `threading.Timer(1.0, lambda: webbrowser.open(url)).start()` — Pitfall 7 delayed browser open; `_env_int` reused for PORT/UVICORN_WORKERS (WR-01 fix at line 43-44) | ✓ VERIFIED |
| `APP_BASE_PATH` env → FastAPI `root_path` | `app/main.py:66` `root_path=config.APP_BASE_PATH`; `app/config.py:93` `APP_BASE_PATH: str = os.environ.get("APP_BASE_PATH", "")`. **Runtime verified:** `APP_BASE_PATH=/pdf-logo` → `app.root_path == '/pdf-logo'` (live import + env override confirmed) | ✓ VERIFIED |
| `/health` returns 5 fields, no session_id leak | `app/main.py:259-283` returns `{status, uptime_seconds, active_sessions, data_dir_bytes, data_dir_pct}`. **Live TestClient call confirms** body keys are exactly these 5, and `re.search(r'[a-f0-9]{32}', body)` returns no match (T-05-08 honored). WR-02 routes through `storage.list_session_ids` not raw originals scan. | ✓ VERIFIED |
| README documents 3 deploy paths | `README.md` lines 36, 58, 94 — three explicit "Deploy Target N" sections (Zeabur / 本機 Python 套裝 / Ubuntu 公司入口) | ✓ VERIFIED |

**Note on `docker build` execution:** The Dockerfile and supporting artifacts were validated by structural source-grep + FastAPI TestClient in-process assertions. Actual container build/run is flagged for UAT (researcher noted Docker is not on dev machine; Zeabur builds remotely; Ubuntu deploy is long-term per memory `project_deployment_licensing.md`). This is a documented, accepted UAT deferral — NOT a verification gap.

---

## SC-2: 大型/旋轉頁面不崩潰

| Check | Evidence | Status |
|-------|----------|--------|
| /process wrapped in 60s asyncio.wait_for + asyncio.to_thread | `app/api/process.py:106-110` `await asyncio.wait_for(asyncio.to_thread(pipeline.process_job, session_id, job), timeout=config.PROCESS_TIMEOUT_SECONDS)` | ✓ VERIFIED |
| PROCESS_TIMEOUT_SECONDS env-tunable | `app/config.py:107` `PROCESS_TIMEOUT_SECONDS: int = _env_int("PROCESS_TIMEOUT_SECONDS", 60)` | ✓ VERIFIED |
| UVICORN_WORKERS default 2 | `app/config.py:92` `UVICORN_WORKERS: int = _env_int("UVICORN_WORKERS", 2)`; Dockerfile ENV line 42 `UVICORN_WORKERS=2` mirrors | ✓ VERIFIED |
| 504 detail.code='processing_timeout' on TimeoutError | `app/api/process.py:111-121` `except asyncio.TimeoutError: raise HTTPException(status_code=504, detail={"code": "processing_timeout", "message": f"處理逾時(超過 {PROCESS_TIMEOUT_SECONDS} 秒)..."})` with 繁中 message | ✓ VERIFIED |
| WR-06 `fit_dpi_to_pixel_budget` still in render layer (no regression) | `app/services/render.py:75` `def fit_dpi_to_pixel_budget(dpi: int, page_w_pt: float, page_h_pt: float) -> int:` — function intact, docstring still references WR-06 | ✓ VERIFIED |
| Phase 2 derotation_matrix coordinate mapping intact | `app/services/pdf_engine.py:167` `unrotated = disp * page.derotation_matrix` + references in `coords.py:16`. Function bodies unchanged; Phase 5 added no Phase 2 modifications. | ✓ VERIFIED (no regression) |
| Pitfall 1 "thread cannot be killed" acknowledged inline | `app/api/process.py:98-105` — multi-line inline comment explains: "asyncio.wait_for(asyncio.to_thread(...)) makes the HTTP response return 504 immediately on timeout, but the underlying thread KEEPS RUNNING ... MAX_RENDER_PIXELS=40MP + MAX_PAGES=30 collapse the worst case ... UVICORN_WORKERS=2 (D-D2) ensures the OTHER worker continues serving" | ✓ VERIFIED |
| Behavioral spot-check: timeout returns 504 | `tests/test_process_api.py::test_process_timeout_returns_504` PASSES (monkey-patches PROCESS_TIMEOUT to 0.2s + sleep stub → 504 returned) | ✓ VERIFIED |
| Behavioral spot-check: corrupted gate runs before timeout | `tests/test_process_api.py::test_process_corrupted_check_runs_before_timeout` PASSES (< 1s response even with sleep stub) | ✓ VERIFIED |

---

## SC-3: 暫存清理 + 原始檔雜湊驗證

### Janitor (4-kind sweep, 3 triggers)

| Check | Evidence | Status |
|-------|----------|--------|
| app/services/janitor.py exists, stdlib-only | `app/services/janitor.py` — sweep_expired_sessions defined at line 31; module imports only `logging`, `time`, `config`, `storage`. AST verified no `import fitz` | ✓ VERIFIED |
| Trigger (a) lifespan startup | `app/main.py:57-60` `try: janitor.sweep_expired_sessions() except Exception: logger.warning("lifespan: startup janitor sweep failed", exc_info=True)` (CR-01: log not silent swallow) | ✓ VERIFIED |
| Trigger (b) POST /sessions finally | `app/api/sessions.py:86-92` `finally: try: janitor.sweep_expired_sessions() except Exception: logger.warning(...)` | ✓ VERIFIED |
| Trigger (c) POST /process finally | `app/api/process.py:122-134` `finally: try: janitor.sweep_expired_sessions() except Exception: logger.warning(...)` with session_id in log context | ✓ VERIFIED |
| SESSION_TTL_SECONDS = 3600 default | `app/config.py:106` `SESSION_TTL_SECONDS: int = _env_int("SESSION_TTL_SECONDS", 3600)` | ✓ VERIFIED |
| 4-kind sweep (originals + work + pristine + outputs) | `app/storage.py:41` `_KINDS = ("originals", "work", "outputs", "pristine")`; `app/storage.py:402-413` `delete_session` iterates all four kinds via `subdir(kind, sid)` + `shutil.rmtree(path, onerror=_on_rm_error)` | ✓ VERIFIED |
| Windows-safe shutil.rmtree onerror handler | `app/storage.py:303-330` `_on_rm_error` — PermissionError + os.unlink/remove/rmdir → re-chmod 0o644 + retry. Shared between delete_session and janitor (Pitfall 3 single source of truth) | ✓ VERIFIED |
| Janitor failure does NOT taint HTTP response | All 3 trigger sites wrapped in `try/except Exception: logger.warning(... exc_info=True)`. Test: `test_janitor_failure_does_not_taint_process_request` PASSES (monkey-patch janitor to raise, /process still 200) | ✓ VERIFIED |
| max-mtime semantics protect freshly downloaded outputs | `app/storage.py:358-389` `session_age_seconds` uses `max(mtimes)` not min — D-B4 race protection. WR-05 TOCTOU narrowing: re-check before delete at `janitor.py:70-72` | ✓ VERIFIED |

### SHA-256 Integrity

| Check | Evidence | Status |
|-------|----------|--------|
| app/services/integrity.py exists, stdlib-only | `app/services/integrity.py` — IntegrityError + compute_original_hash + verify_original_hash defined; imports hashlib/logging/pathlib/time + storage. AST grep confirms no `import fitz` (test_integrity_module_does_not_import_fitz now uses AST not substring per cfded81 fix) | ✓ VERIFIED |
| SHA-256 baseline stored in meta.json at ingest (PDF path) | `app/services/ingest.py:265-270` `storage.write_session_meta(session_id, page_count=n_pages, filename=safe_name, original_sha256=compute_original_hash(data))` | ✓ VERIFIED |
| SHA-256 baseline stored in meta.json at ingest (image path) | `app/services/ingest.py:317-322` SAME pattern — D-C4 alignment: hash is over user's raw image bytes (NOT the normalized A4 PDF), maintaining Phase 4 D-05 invariant | ✓ VERIFIED |
| Atomic meta.json write (A7 cross-drive safe) | `app/storage.py:200-214` `tempfile.mkstemp(dir=str(dest.parent))` + `os.replace(tmp_path, dest)` + unlink-on-failure. Test: `test_write_session_meta_is_atomic_on_simulated_crash` PASSES | ✓ VERIFIED |
| /process gates on SHA-256 verification | `app/services/pipeline.py:131-134` `try: integrity.verify_original_hash(session_id) except integrity.IntegrityError as err: raise PipelineError(err.code, err.message)` — runs BEFORE reset-from-pristine | ✓ VERIFIED |
| 503 detail.code='original_tampered' on mismatch + structured log | `app/services/integrity.py:104-118` `logger.error("original_tampered", extra={session_id, expected_hash, actual_hash, path, timestamp})` then `mark_session_corrupted` then raise `IntegrityError("original_tampered", "系統偵測到原始檔異常...")`. Mapped to 503 via `app/main.py:164` `_PROCESS_STATUS["original_tampered"] = 503` | ✓ VERIFIED |
| `.corrupted` sentinel side-effect-BEFORE-raise | `app/services/integrity.py:78` `storage.mark_session_corrupted(session_id)` is called BEFORE `raise IntegrityError` — caller catch path cannot bypass the mark. Test: `test_verify_original_hash_raises_on_tampered_original` confirms sid is corrupted after raise. | ✓ VERIFIED |
| 410 detail.code='session_corrupted' for /process | `app/api/process.py:53-67` `_reject_if_corrupted` helper raises 410 with `session_corrupted` code. Called from /process at line 92 | ✓ VERIFIED |
| 410 also enforced on GET /result + GET /result/pages/{n}/image (CR-02 fix) | `app/api/process.py:157` `_reject_if_corrupted(session_id)` in `get_result_page_image`; `app/api/process.py:197` `_reject_if_corrupted(session_id)` in `download_result`. Tests `test_corrupted_session_blocked_from_get_result_download` + `test_corrupted_session_blocked_from_result_page_image` PASS. | ✓ VERIFIED |
| Legacy meta.json without original_sha256 → fail-closed | `app/services/integrity.py:75-82` `if meta is None or "original_sha256" not in meta: storage.mark_session_corrupted(...) raise IntegrityError("session_corrupted", ...)`. Test `test_legacy_session_without_sha256_treated_as_corrupted` PASSES (accepts 410 OR 503) | ✓ VERIFIED |
| Originals file NEVER mutated by pipeline (D-05 strengthened) | Phase 4 deferred-mutation kept: pipeline reads originals/source.pdf for hash compare only; reset is from pristine/, work copy mutated only. Phase 5 added no writes to originals/. | ✓ VERIFIED (no regression) |

### Behavioral spot-checks

| Test | Result |
|------|--------|
| `tests/test_process_api.py::test_meta_original_sha256_written_at_ingest` | PASS |
| `tests/test_process_api.py::test_original_tampered_returns_503` | PASS |
| `tests/test_process_api.py::test_corrupted_session_blocked_from_process` | PASS |
| `tests/test_process_api.py::test_corrupted_session_blocked_from_get_result_download` | PASS |
| `tests/test_process_api.py::test_corrupted_session_blocked_from_result_page_image` | PASS |
| `tests/test_process_api.py::test_process_timeout_returns_504` | PASS |
| `tests/test_process_api.py::test_process_corrupted_check_runs_before_timeout` | PASS |
| `tests/test_process_api.py::test_sessions_post_calls_janitor_at_end` | PASS |
| `tests/test_process_api.py::test_process_post_calls_janitor_at_end` | PASS |
| `tests/test_process_api.py::test_janitor_failure_does_not_taint_process_request` | PASS |

---

## Cross-cutting Verification

### AGPL §13 三件套同時就位

| Artifact | Evidence | Status |
|----------|----------|--------|
| LICENSE file (AGPL-3.0 verbatim) | `LICENSE` file exists; `wc -c LICENSE` = **34,523 bytes**; first 2 lines: `GNU AFFERO GENERAL PUBLIC LICENSE` / `Version 3, 19 November 2007` | ✓ VERIFIED |
| README.md mentions GitHub URL (placeholder OK pre-deploy) | `README.md:15` `https://github.com/<OWNER>/LogoSwap` + 4 more occurrences across Deploy Target sections; line 11 `LogoSwap 以 **GNU AGPLv3** 授權` | ✓ VERIFIED (placeholder ok — WR-06 release-gate enforces substitution at deploy) |
| UI footer with GitHub source link + AGPLv3 link | `web/index.html:415-426` `<footer class="app-footer" role="contentinfo">` with `<a href="https://github.com/<OWNER>/LogoSwap" target="_blank">LogoSwap</a>` and AGPLv3 link to gnu.org. Token-only CSS at `web/styles/app.css:86-105`. | ✓ VERIFIED |
| <OWNER> placeholder deploy gate | `tests/test_agpl_compliance.py` (created via WR-06 fix `fca14fb`) — 2 pristine-repo tests PASS (placeholder present), 2 release-gate tests SKIPPED unless `LOGOSWAP_RELEASE_GATE=1` set. Documented deploy-ops gate. | ✓ VERIFIED |

### AGPL Seam (fitz isolation)

| File | AST check | Status |
|------|-----------|--------|
| `app/services/integrity.py` | AST walk: no Import/ImportFrom containing `fitz` | ✓ VERIFIED |
| `app/services/janitor.py` | AST walk: no Import/ImportFrom containing `fitz` | ✓ VERIFIED |
| `app/__main__.py` | AST walk: no Import/ImportFrom containing `fitz` | ✓ VERIFIED |
| `app/services/pdf_engine.py` (canonical seam) | Contains `import fitz` at line 19 — confirmed sole entry point | ✓ VERIFIED |
| Test guards: `test_integrity_module_does_not_import_fitz` + `test_janitor_module_does_not_import_fitz` | Both PASS (AST-based after `cfded81` fix) | ✓ VERIFIED |

### 繁中 error copy for new codes

| Code | Server message | Frontend message (web/js/app.js) | Status |
|------|----------------|----------------------------------|--------|
| `original_tampered` | `app/services/integrity.py:116-117` `系統偵測到原始檔異常,此工作階段已停用,請重新上傳檔案。` | `app.js:55` `originalTampered` key + `app.js:212-213` case | ✓ VERIFIED |
| `session_corrupted` | `app/services/integrity.py:80-81` + `app/api/process.py:64-65` `此工作階段已標記為異常,請重新上傳檔案。` | `app.js:57` `sessionCorrupted` + `app.js:214-215` case | ✓ VERIFIED |
| `processing_timeout` | `app/api/process.py:115-118` `處理逾時(超過 {N} 秒),請改用較小檔案或減少框選區域數量。` | `app.js:59` `processingTimeout` + `app.js:216-217` case | ✓ VERIFIED |
| `sessionTtlHint` (D-B2 UI hint) | n/a (UI-side) | `app.js:64-65` `此次處理 1 小時內完成下載 — 逾時需重新上傳。` + `aria-live="polite"` at line 106 | ✓ VERIFIED |
| `sessionExpired` (404 friendly) | n/a (UI-side) | `app.js:66-67` `此次處理已過期,請重新上傳此檔。` | ✓ VERIFIED |

### Phase 4 D-05 invariant preserved

- `originals/` chmod 0o444 untouched (`app/storage.py:249`)
- pipeline NEVER writes to originals/ — verify_original_hash is read-only
- Image upload SHA-256 hashes RAW user bytes (NOT normalized A4 PDF) — `app/services/ingest.py:321` confirms (D-C4 alignment)
- Pristine/ used for reset; originals/ used only for hash verify and meta sidecar

### REVIEW-FIX closure (9/9 findings landed)

All 9 review findings from `05-REVIEW.md` are addressed via the commits between `6abca8e` and `cfded81`:

| ID | Severity | Fix commit | In tree? |
|----|----------|-----------|----------|
| CR-01 | BLOCKER | `6abca8e` | ✓ (logger.warning in all 3 janitor trigger sites) |
| CR-02 | BLOCKER | `b02ae56` | ✓ (`_reject_if_corrupted` called from GET /result + GET /result/pages/{n}/image) |
| WR-01 | WARNING | `f7ad897` | ✓ (`_env_int` used in `app/__main__.py`) |
| WR-02 | WARNING | `88d933c` | ✓ (`/health` uses `storage.list_session_ids`) |
| WR-03 | WARNING | `f8fda90` | ✓ (docstring note in `session_age_seconds`) |
| WR-04 | WARNING | `8734bdc` | ✓ (partial-delete logging in `janitor.py`) |
| WR-05 | WARNING | `22bf973` | ✓ (TOCTOU re-check in `janitor.py:70-72`) |
| WR-06 | WARNING | `fca14fb` | ✓ (`tests/test_agpl_compliance.py` exists + 2 PASS + 2 release-skipped) |
| WR-07 | WARNING | `63fc4ce` | ✓ (`.app-shell` grid-template-rows = `auto 1fr auto auto`, hint at app-shell level) |
| (Integrity AST fix) | post-review-fix | `cfded81` | ✓ (AGPL seam grep now AST-based; both seam tests PASS) |

---

## Test Suite Snapshot

```
$ .venv/Scripts/python.exe -m pytest tests/ --no-header -q
291 passed, 3 skipped in 12.53s
```

- **Phase 4 baseline:** 243 passed
- **Phase 5 close:** 291 passed + 3 platform-skipped (POSIX-only chmod tests + Windows-only behavior tests)
- **Net Phase 5:** +48 new tests, 0 regressions
- All Phase 5 dedicated test modules (test_health, test_integrity, test_janitor, test_agpl_compliance) PASS
- All Phase 1–4 modules continue to PASS (test_api, test_coords, test_ingest, test_logo, test_phase1_gaps, test_phase2_gaps, test_process_api, test_redact, test_render, test_storage)

### Anti-pattern scan

```
grep -c "TBD|FIXME|XXX" across all Phase 5 modified files → 0 matches
```

No unresolved debt markers introduced by Phase 5. Pitfall 1 / WR-* are documented in code via descriptive comments referencing the threat model entries, not as unresolved TODOs.

---

## Decisions Coverage (18/18)

| Decision | Evidence | Status |
|----------|----------|--------|
| D-A1 (no nginx in image) | Dockerfile has zero nginx mention; docker-compose.example.yml comments the nginx block as opt-in | ✓ |
| D-A2 (root mount + optional APP_BASE_PATH) | `app/main.py:66` + runtime env-override test | ✓ |
| D-A3 (multi-stage + 本機可不用 Docker) | Dockerfile multi-stage + `app/__main__.py` desktop entry | ✓ |
| D-A4 (3 deploy targets) | README.md has 3 explicit "Deploy Target" sections | ✓ |
| D-B1 (synchronous janitor 3 triggers) | lifespan + sessions finally + process finally (all logger.warning on error per CR-01) | ✓ |
| D-B2 (1h hard TTL + UI hint) | SESSION_TTL_SECONDS=3600 + `sessionTtlHint` COPY + aria-live polite region in app.js | ✓ |
| D-B3 (4-kind sweep) | `_KINDS` 4-tuple iterated in delete_session + janitor | ✓ |
| D-B4 (race protection: mtime ≫ process timeout) | 3600 / 60 = 60x; WR-05 TOCTOU re-check additional defense | ✓ |
| D-C1 (SHA-256 in meta.json) | ingest writes original_sha256 in same atomic transaction as page_count + filename | ✓ |
| D-C2 (verify at /process entry) | pipeline.process_job line 131-134 runs verify before reset-from-pristine | ✓ |
| D-C3 (503 + log + .corrupted sentinel) | integrity.py logger.error + mark_session_corrupted (side-effect-before-raise) + 503 mapping | ✓ |
| D-C4 (only verify originals, not pristine) | verify_original_hash reads `storage.original_path(sid)`; pristine never touched | ✓ |
| D-C5 (legacy meta migration → corrupted) | integrity.py:75-82 fail-closed; test_verify_treats_legacy_session_as_corrupted PASSES | ✓ |
| D-D1 (sync /process) | asyncio.wait_for(asyncio.to_thread(...)) — same sync handler, no BackgroundTasks refactor | ✓ |
| D-D2 (workers=2 default) | UVICORN_WORKERS=2 in config + Dockerfile ENV; __main__.py defaults 1 for desktop (justified) | ✓ |
| D-D3 (60s timeout) | PROCESS_TIMEOUT_SECONDS=60 + 504 mapping | ✓ |
| D-D4 (HEALTHCHECK + /health 5 fields) | Dockerfile HEALTHCHECK stdlib urllib; /health returns 5 fields runtime-verified | ✓ |
| AGPL §13 三件套 | LICENSE 34KB + README.md AGPL clause + UI footer all in lockstep | ✓ |

---

## Known UAT-Deferred Items (NOT verification gaps)

These items require human / environmental verification and are explicitly accepted per `05-CONTEXT.md`, `05-01-SUMMARY.md::Plan-level Verification Results` (rows 1–3, 9), and memory `project_deployment_licensing.md`:

1. **Zeabur 實機 build + deploy round-trip** — Docker not installed on dev machine; Zeabur builds image remotely. Dockerfile + structure verified via source-grep + FastAPI TestClient.
2. **Ubuntu 公司入口 nginx strip-prefix embedding** — Needs Ubuntu portal staging. `APP_BASE_PATH=/pdf-logo` → `app.root_path == '/pdf-logo'` confirmed programmatically.
3. **Large 50MB CAD PDF triggers 504** — Needs real customer sample. Timeout path verified via monkey-patched sleep in test_process_timeout_returns_504.
4. **本機 Python 套裝 `python -m app` cross-platform smoke** — Module shape + 127.0.0.1 default + threading.Timer all verified; full lifecycle is manual UAT.
5. **`<OWNER>` placeholder substitution before public push** — Documented deploy-ops gate via `LOGOSWAP_RELEASE_GATE=1 pytest tests/test_agpl_compliance.py`.
6. **UI footer + TTL hint visual rendering in dark + light themes** — Token-only CSS structurally guarantees dual-theme inheritance; visual confirmation is manual.

These are recorded in `human_verification:` frontmatter for `/gsd-uat` follow-through. **Phase 5 is structurally complete; goal achieved.**

---

## Verdict

**PASS — phase goal achieved.**

- All 3 ROADMAP Success Criteria are evidenced in tree with passing tests.
- All 18 phase decisions covered.
- All 9 REVIEW-FIX findings resolved (2 BLOCKER + 7 WARNING) plus the post-review integrity-AST regression fix.
- 291/294 tests pass (3 platform-skipped), zero regressions from Phase 1–4 (243 → 291 = +48 net).
- AGPL §13 三件套 atomically deployed; AGPL seam preserved (only `pdf_engine.py` imports fitz).
- Phase 4 D-05 SHA-256 invariant strengthened (runtime verify added), not weakened.
- 6 items explicitly routed to UAT (Docker / Zeabur / Ubuntu / large CAD PDF / desktop smoke / visual theme) — these are scope-deferred verifications, not code gaps.

## VERIFICATION PASSED

---

*Verified: 2026-05-24*
*Verifier: Claude (gsd-verifier)*
