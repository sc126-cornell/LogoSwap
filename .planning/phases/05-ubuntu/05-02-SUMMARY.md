---
phase: 05-ubuntu
plan: 02
subsystem: hardening
tags: [sha256, janitor, ttl, timeout, integrity, asyncio, corrupted-sentinel, agpl-seam, threat-mitigation, tdd]

requires:
  - phase: 04-raster-image-support
    provides: SHA-256 D-05 invariant + pristine reset source + IngestError/PipelineError handlers
  - phase: 05-ubuntu
    plan: 01
    provides: lifespan(app) skeleton + UVICORN_WORKERS + APP_BASE_PATH + /health 5-field
provides:
  - app/services/integrity.py (NEW): compute_original_hash + verify_original_hash + IntegrityError
  - app/services/janitor.py (NEW): sweep_expired_sessions(now?) → int (stdlib only)
  - storage atomic write_session_meta (tempfile.mkstemp + os.replace, A7 cross-drive safe)
  - storage helpers: list_session_ids, session_age_seconds (max-mtime), delete_session, mark_session_corrupted, is_session_corrupted
  - _on_rm_error shared rmtree handler (Pitfall 3 Windows chmod 0o444 cross-platform)
  - /process timeout (asyncio.wait_for + asyncio.to_thread, 60s default, 504 processing_timeout)
  - corrupted gate (is_session_corrupted short-circuit → 410 session_corrupted)
  - janitor triggers: lifespan startup + POST /sessions + POST /process (try/except in finally)
  - _PROCESS_STATUS dict extended (original_tampered:503 / session_corrupted:410 / processing_timeout:504)
  - Frontend繁中 error messages: originalTampered / sessionCorrupted / processingTimeout
  - D-B2 session TTL hint UI (此次處理 1 小時內完成下載) + 404 expired message (此次處理已過期)
  - Optional CORS middleware (config.CORS_ALLOW_ORIGINS, off by default)
affects: [future-deployment-uat, future-large-pdf-handling, future-embedded-portal]

tech-stack:
  added:
    - asyncio.wait_for + asyncio.to_thread for timeout-bounded CPU-bound work
    - tempfile.mkstemp(dir=dest.parent) + os.replace atomic write pattern (A7)
    - hashlib.sha256 SHA-256 baseline verify on every /process
    - shutil.rmtree onerror handler for cross-platform readonly cleanup
  patterns:
    - "AST-based AGPL seam grep (tests/test_integrity.py + tests/test_janitor.py): mirrors test_redact.py's test_fitz_import_confined_to_engine_seam"
    - "side-effect-before-raise in IntegrityError (sentinel written BEFORE raise — caller's catch path cannot skip the mark)"
    - "max-mtime not min-mtime for session_age_seconds (outputs/ freshness protects from premature sweep)"
    - "janitor synchronous trigger × 3, all try/except wrapped — never taint HTTP response (T-05-05)"

key-files:
  created:
    - app/services/integrity.py
    - app/services/janitor.py
    - tests/test_integrity.py
    - tests/test_janitor.py
    - tests/test_health.py
  modified:
    - app/config.py (added SESSION_TTL_SECONDS + PROCESS_TIMEOUT_SECONDS + CORS_ALLOW_ORIGINS)
    - app/storage.py (atomic write_session_meta + 5 new helpers + _on_rm_error shared handler)
    - app/services/ingest.py (compute_original_hash baseline write for PDF + image paths)
    - app/services/pipeline.py (verify_original_hash gate at process_job entry)
    - app/api/process.py (corrupted short-circuit + asyncio.wait_for timeout + janitor finally)
    - app/api/sessions.py (janitor finally trigger b)
    - app/main.py (lifespan startup sweep + _PROCESS_STATUS 3-entry extension + optional CORS)
    - web/js/app.js (5 new COPY keys + 3 messageForError cases + TTL hint live-region)
    - web/styles/app.css (.app-session-hint token-only block)
    - tests/test_storage.py (8 new tests for atomic meta + helpers)
    - tests/test_ingest.py (5 new tests + 1 updated test for D-C2 semantics)
    - tests/test_process_api.py (9 new tests for timeout + corrupted + janitor triggers)

key-decisions:
  - "Side-effect order in verify_original_hash: write .corrupted sentinel BEFORE raising IntegrityError — a caller's catch path (pipeline → PipelineError) cannot skip the mark, so subsequent /process on the same sid short-circuits at the route layer instead of re-verifying"
  - "Atomic meta.json write uses tempfile.mkstemp(dir=dest.parent) — A7 forces the tmp file onto the same filesystem as the destination so os.replace is genuinely atomic. Without dir=, Windows defaults the tmp to a separate volume and os.replace falls back to copy-then-delete (non-atomic)"
  - "session_age_seconds uses MAX (not min) mtime across the 4-kind dirs — protects a freshly-downloaded outputs/ even when originals/ is hours old (D-B4 race protection alternative to a .lock file)"
  - "Corrupted short-circuit lives in app/api/process.py BEFORE the asyncio.wait_for wrapper — a poisoned sid returns 410 in <1s without spending a thread; the timeout would still catch it via verify_original_hash but adds latency"
  - "asyncio.wait_for(asyncio.to_thread(...)) is the official-supported FastAPI pattern for CPU-bound timeout; Python cannot kill the underlying thread, but UVICORN_WORKERS=2 (D-D2) keeps preview/ingest responsive on the other worker. ProcessPoolExecutor upgrade path documented (deferred to v1.x if real abuse appears)"
  - "Janitor failure is logged AND swallowed at every trigger point (try/except: pass) — D-B1 contract is best-effort cleanup, not a precondition for the HTTP response"
  - "Image upload SHA-256 hashes the user's RAW image bytes (NOT the normalized A4 PDF) — D-C4 alignment with the verify path (which reads originals/, the raw bytes); the Phase 4 D-05 strengthened invariant carries forward into Phase 5"
  - "Legacy session (Phase 1–4 meta.json without original_sha256) is fail-closed → session_corrupted → 410. 1h TTL janitor reclaims the dir naturally; no migration script required"
  - "Pitfall 3 (Windows chmod 0o444 + rmtree): the _on_rm_error handler lives in app/storage.py (used by both delete_session and janitor.delete_session) — single source of truth, no duplication"
  - "_PROCESS_STATUS mapping for original_tampered/session_corrupted/processing_timeout serves as DEFENSE IN DEPTH — api/process.py raises HTTPException directly with the matching status code; the dict catches any future code path that re-raises through PipelineError"

patterns-established:
  - "TDD cycle per task: tests/test_*.py RED commit (test only) → app/* GREEN commit (impl + test passes). Three tasks = three (RED, GREEN) commit pairs"
  - "Atomic write via tempfile.mkstemp(dir=dest.parent) + os.fdopen + os.replace + unlink-on-failure — usable for any future single-file sidecar write"
  - "Side-effect-before-raise in typed errors with cleanup actions (sentinel, log) — caller catch paths cannot bypass cleanup"
  - "Synchronous janitor at three trigger points with try/except finally — no background scheduler / no APScheduler / no asyncio.task, just stdlib"
  - "AST-based AGPL seam grep for new fitz-free modules (integrity, janitor) — substring grep would false-positive on docstrings; ast.walk + isinstance(Import|ImportFrom) is the canonical pattern (mirrors tests/test_redact.py)"

requirements-completed:
  - SC-2
  - SC-3
  - D-B1
  - D-B2
  - D-B3
  - D-B4
  - D-C1
  - D-C2
  - D-C3
  - D-C4
  - D-C5
  - D-D1
  - D-D3

duration: ~70 min
completed: 2026-05-24
---

# Phase 5 Plan 02: 穩固化 slice (SHA-256 verify + janitor + /process timeout + 前端 UX) Summary

**原始檔 SHA-256 baseline + verify_original_hash + .corrupted sentinel + 1h TTL janitor 三點同步 + /process 60s timeout + 前端三個錯誤碼 + D-B2 session TTL UI 提示 — Phase 5 success criteria #2 + #3 雙雙落地。**

## Performance

- **Duration:** ~70 min
- **Started:** 2026-05-23T16:01Z (immediately after Plan 05-01 closure)
- **Completed:** 2026-05-24T (Asia/Taipei)
- **Tasks:** 3/3
- **Files modified:** 13 (2 created module files + 3 created test files + 8 modified)
- **Tests:** 288 collected (287 passed + 1 platform-skipped) — 243 Phase 4 baseline → +45 Phase 5 = 288 total

## Accomplishments

- **Runtime SHA-256 D-05 verify** — every /process re-hashes originals/source.pdf against the meta.json baseline before any reset-from-pristine work. Mismatch → 503 `original_tampered` + structured log + `.corrupted` sentinel; subsequent /process on same sid → 410 `session_corrupted` (no parse, no thread, <1s).
- **Atomic meta.json writes** — `tempfile.mkstemp(dir=dest.parent)` + `os.replace` + unlink-on-failure. A7 cross-drive guarantee: tmp file forced onto destination's filesystem so os.replace is genuinely atomic on Windows.
- **1-hour TTL janitor with 3 synchronous trigger points** — lifespan startup, POST /sessions finally, POST /process finally. All three wrapped in try/except so janitor failure cannot taint the HTTP response. `_on_rm_error` re-chmods 0o444 → retry for Pitfall 3 (Windows readonly originals).
- **/process 60s timeout** — `asyncio.wait_for(asyncio.to_thread(pipeline.process_job, ...), timeout=PROCESS_TIMEOUT_SECONDS)`. TimeoutError → 504 `processing_timeout` with繁中 message including the limit. Pitfall 1 inline-noted: thread cannot be killed; UVICORN_WORKERS=2 keeps preview alive on the other worker.
- **Corrupted gate at the route layer** — `is_session_corrupted` short-circuit runs BEFORE the timeout wrapper, so a poisoned sid never even allocates a thread.
- **Frontend繁中 error mapping** — `originalTampered`, `sessionCorrupted`, `processingTimeout` in COPY + 3 new switch cases in `messageForError`. XSS-safe path (textContent only — no server message reflection).
- **D-B2 session TTL UI hint** — polite live-region (`aria-live="polite" role="status"`) inserted into the page-stage on successful upload showing「此次處理 1 小時內完成下載 — 逾時需重新上傳。」. Swaps to「此次處理已過期,請重新上傳此檔。」on a 404 from `GET /sessions/{id}` (caught in `showError` via `err.status === 404 && err.code === "session_not_found"`).
- **AGPL seam preserved** — integrity.py + janitor.py both stdlib-only; AST-grep guards in `tests/test_integrity.py` + `tests/test_janitor.py` mirror the canonical `test_fitz_import_confined_to_engine_seam` pattern.
- **Phase 4 D-05 invariant strengthened, not weakened** — pipeline still NEVER writes to originals/ (the new verify call is read-only); pristine/ untouched on verify failure; T-05-04..07 + T-05-10 + Pitfall 1/3/4/A7 all mapped per plan threat_model.

## Task Commits

1. **Task 1 RED — failing tests for atomic meta + storage helpers + integrity module** — `732bcde` (test)
2. **Task 1 GREEN — atomic meta + 5 storage helpers + integrity module** — `ad72796` (feat)
3. **Task 2 RED — failing tests for janitor module + pipeline verify integration** — `4958cbc` (test)
4. **Task 2 GREEN — janitor module + pipeline verify_original_hash integration** — `c2c1f0f` (feat)
5. **Task 3 RED — failing tests for /process timeout + corrupted gate + janitor triggers** — `fc43fa4` (test)
6. **Task 3 GREEN — /process timeout + corrupted gate + janitor 3 triggers + frontend mapping** — `852b75f` (feat)

## Files Created/Modified

**Created (5):**

- `app/services/integrity.py` — IntegrityError + compute_original_hash + verify_original_hash. Stdlib only (hashlib/logging/pathlib/time + storage). Side-effect-before-raise: `storage.mark_session_corrupted(sid)` runs BEFORE the IntegrityError raise so a caller's catch path (pipeline → PipelineError) cannot bypass the sentinel write. Structured log on tamper (`logger.error("original_tampered", extra={session_id, expected_hash, actual_hash, path, timestamp})`) lands in JSON-log adaptors if a future log-config wires one.
- `app/services/janitor.py` — `sweep_expired_sessions(now?) → int`. Reads TTL from `config.SESSION_TTL_SECONDS` at call time (test-friendly). Iterates `storage.list_session_ids()`, drops every sid whose `session_age_seconds(sid) >= TTL` via `storage.delete_session`. Counts a delete a success only if all 4-kind dirs are gone afterwards. Per-session and top-level try/except prevent any single failure from stalling the sweep. AGPL seam preserved (AST grep test).
- `tests/test_integrity.py` — 6 tests: hashlib parity, pass/tampered/legacy-meta/missing-meta paths, AST-based AGPL seam grep.
- `tests/test_janitor.py` — 8 tests: TTL sweep, active-session-keep, max-mtime protection (the freshly-downloaded outputs/ case), Windows chmod 0o444 cross-platform, no-sessions zero, non-token-dir skip (T-05-07), per-session failure isolation, AGPL seam.
- `tests/test_health.py` — 6 tests: status, uptime float ≥ 0, active_sessions count after multi-ingest, data_dir fields shape, T-05-08 no-session-id-leak grep, POSIX-only unreadable-originals → -1.

**Modified (8):**

- `app/config.py` — Appended three Phase 5 constants below APP_BASE_PATH: `SESSION_TTL_SECONDS=3600` (D-B2 1h TTL), `PROCESS_TIMEOUT_SECONDS=60` (D-D3), `CORS_ALLOW_ORIGINS=""` (off by default — D-A1 same-origin / iframe / strip-prefix all work without it). All env-overridable via `_env_int` / `os.environ.get` per Phase 1-4 pattern.
- `app/storage.py` — Added `tempfile`, `shutil`, `time`, `logging`, `Iterator` imports. `write_session_meta` now requires `original_sha256: str` kwarg and writes atomically (tempfile.mkstemp + os.replace + unlink-on-fail). Added `_on_rm_error` shared rmtree handler (Pitfall 3, used by `delete_session` and janitor). Added `_CORRUPTED_NAME = ".corrupted"`. Added 5 new functions: `list_session_ids() → Iterator[str]` (union across 4 kinds, _SESSION_ID_RE filtered), `session_age_seconds(sid) → float | None` (max mtime), `delete_session(sid)` (4-kind rmtree, best-effort, never raises), `mark_session_corrupted(sid) → Path` (writes sentinel), `is_session_corrupted(sid) → bool` (swallows InvalidSessionId).
- `app/services/ingest.py` — Imported `from .integrity import compute_original_hash`. Both `_ingest_pdf` and `_ingest_image_to_pdf` now compute the SHA-256 over the user's raw uploaded bytes (`data`) and pass `original_sha256=compute_original_hash(data)` into `write_session_meta`. Same transaction — atomic baseline.
- `app/services/pipeline.py` — Imported `integrity` alongside the existing services. `process_job` runs `integrity.verify_original_hash(session_id)` immediately after the `work_copy_misconfigured` structural guard and BEFORE the reset-from-pristine `shutil.copyfile`. IntegrityError → re-raise as `PipelineError(err.code, err.message)` so the existing main.py PipelineError handler picks up the new `_PROCESS_STATUS` entries.
- `app/api/process.py` — Imported `asyncio`, `janitor`, `storage`. `process_session` adds (a) D-C3 short-circuit (`storage.is_session_corrupted` → 410), (b) `asyncio.wait_for(asyncio.to_thread(pipeline.process_job, session_id, job), timeout=config.PROCESS_TIMEOUT_SECONDS)` wrapper; TimeoutError → 504 `processing_timeout`, (c) finally `janitor.sweep_expired_sessions()` with try/except. Pitfall 1 inline note documents the "thread cannot be killed; UVICORN_WORKERS=2 mitigates" rationale.
- `app/api/sessions.py` — Imported `janitor`. `create_session` adds `finally: try: janitor.sweep_expired_sessions() except Exception: pass` so the upload either succeeded (201) / raised the appropriate IngestError, and then the cleanup runs without ever masking the result.
- `app/main.py` — Imported `janitor`. `lifespan(app)` body now calls `janitor.sweep_expired_sessions()` inside try/except — D-B1 trigger (a) startup sweep. Optional `CORSMiddleware` conditionally registered when `config.CORS_ALLOW_ORIGINS` is non-empty. `_PROCESS_STATUS` extended with three entries: `original_tampered:503`, `session_corrupted:410`, `processing_timeout:504` — defense in depth (api/process.py raises HTTPException directly with these codes, but the mapping catches any future re-raise via PipelineError).
- `web/js/app.js` — COPY object: 5 new keys (`originalTampered`, `sessionCorrupted`, `processingTimeout`, `sessionTtlHint`, `sessionExpired`). `messageForError` switch: 3 new cases. Added `sessionHintEl` + `ensureSessionHintEl/showSessionTtlHint/showSessionExpired/hideSessionHint` — polite live-region (aria-live="polite" role="status") created via createElement + textContent (XSS-safe, never innerHTML). Wired: `handleFile` success path calls `showSessionTtlHint()` (D-B2); `showError` detects `{status: 404, code: "session_not_found"}` and calls `showSessionExpired()`; retry button clears the hint.
- `web/styles/app.css` — New `.app-session-hint` block, token-only (no hex), inherits dual-theme reskin automatically. Uses `--space-xs`, `--space-lg`, `--color-panel`, `--color-border`, `--color-text-muted`, `--font-size-small`. `[hidden]` selector forces display:none for the initial state.

**Tests modified (3):**

- `tests/test_storage.py` — 8 new tests: write_session_meta includes original_sha256; atomic-on-crash (dest absent + tmp cleaned); list_session_ids union + non-token skip; session_age_seconds uses max-mtime; delete_session removes 4 kinds; delete_session handles readonly 0o444 originals (Pitfall 3); mark/is_session_corrupted round-trip; is_session_corrupted swallows InvalidSessionId.
- `tests/test_ingest.py` — 5 new + 1 updated: ingest writes original_sha256 for PDF; parametrized PNG/JPG/TIFF SHA-256 over raw image bytes (D-C4); pipeline raises PipelineError(original_tampered) on mismatch + sentinel written; pipeline raises PipelineError(session_corrupted) on legacy meta; pipeline doesn't mutate originals/ or pristine/ on verify failure (D-05 strengthening). Updated: `test_pipeline_resets_work_from_pristine_not_originals` no longer deletes originals/ (D-C2 now requires originals/ to be present for verify) — re-expressed as positive pristine-is-reset-source check.
- `tests/test_process_api.py` — 9 new tests: meta original_sha256 at ingest; original_tampered 503 end-to-end; corrupted session blocked → 410; legacy session → 410 OR 503 (both acceptable, same user-facing remedy); process_timeout → 504 (monkey-patch timeout + sleep); corrupted check runs before timeout (<1s elapsed); sessions POST calls janitor; process POST calls janitor; janitor failure does not taint /process response.

## STRIDE Threat Register Closure (this plan)

| Threat ID | Category | Disposition | Mitigation Landed |
|-----------|----------|-------------|-------------------|
| T-05-04 | S (Spoofing — SHA-256 forge) | accept (informational only) | v1 LAN tool; baseline is internal consistency, not crypto-strength tamper-evidence. No HMAC / key signing added (deferred). Carries Phase 4 T-04 wording. |
| T-05-05 | T/A (Janitor race) | mitigate (P1) | TTL=3600s ≫ PROCESS_TIMEOUT=60s (60x); `delete_session` is best-effort and itself never raises; `storage.subdir()` + `_SESSION_ID_RE` filter rejects token-poison; `session_age_seconds` uses max-mtime so outputs-just-downloaded gets protected; janitor wrapped in try/except at all three trigger sites. Test coverage: `test_janitor_failure_does_not_raise` + `test_janitor_failure_does_not_taint_process_request`. |
| T-05-06 | T (delete .corrupted sentinel) | accept (P2) | LAN tool; fs write capability ≈ attacker is already inside. Sentinel defends against accidental re-use, not malicious. HMAC-signed sentinel deferred to public-network path. |
| T-05-07 | I/E (path traversal on sid) | mitigate (P0) | All new helpers route through `storage.subdir()` + `_SESSION_ID_RE.fullmatch`; `is_session_corrupted` and `session_age_seconds` swallow `InvalidSessionId` → False / None so no error oracle. Janitor `list_session_ids` re-filters defensively. |
| T-05-08 | I (/health info leak) | accept (LAN) + mitigate by minimization | 5 fields are count/bytes/pct only; new `tests/test_health.py::test_health_does_not_leak_session_ids` greps the response body against the ingested sid + the hex-digest pattern, guarding any future field addition. |
| T-05-10 | A (timeout thread keeps running) | mitigate (acceptable) | UVICORN_WORKERS=2 (D-D2, Plan 05-01) ensures preview/ingest stay live on the other worker; MAX_RENDER_PIXELS=40MP + MAX_PAGES=30 collapse worst case from minutes to ~10–30s; Pitfall 1 in-source comment in `app/api/process.py` documents the rationale; ProcessPoolExecutor upgrade path deferred to v1.x. |
| Pitfall 1 | A | mitigate (acceptable) | Same as T-05-10. |
| Pitfall 3 | A (Windows chmod 0o444 + rmtree) | mitigate (P0) | `_on_rm_error` in `app/storage.py` re-chmods 0o644 → retry for PermissionError on unlink/rmdir/remove; shared between `delete_session` and janitor (single source of truth). Test coverage: `test_delete_session_handles_readonly_original` + `test_janitor_handles_chmod_0o444_originals_cross_platform`. |
| Pitfall 4 | A (legacy session migration) | mitigate by fail-closed | meta.json without `original_sha256` → `IntegrityError("session_corrupted")` → 410; 1h TTL reclaims naturally (Phase 5 deployment 1h after migration = legacy fully cleared). Test coverage: `test_verify_treats_legacy_session_as_corrupted` + `test_legacy_session_without_sha256_treated_as_corrupted`. |
| A7 | I/T (atomic write cross-drive) | mitigate (P1) | `tempfile.mkstemp(dir=str(dest.parent))` forces tmp + dest on same FS → os.replace is genuinely atomic on Windows. Test coverage: `test_write_session_meta_is_atomic_on_simulated_crash`. |

**Phase 5 全局 STRIDE 收口**: Phase 4 已收 17/17; Plan 05-01 處理 T-05-01..03 / 08 / 09 + Pitfall 2/5/7/10; Plan 05-02 (本 plan) 處理 T-05-04..07 / 08 / 10 + Pitfall 1/3/4/A7. **Phase 5 累計 27/27 closed** (15 mitigate + 7 accept + 5 "accept by mitigation equivalent").

## End-to-End Verification (test-time sample)

Full pytest suite runs in ~11s on the local dev machine:

```
$ .venv/Scripts/python.exe -m pytest tests/ --no-header
...
287 passed, 1 skipped in 11.44s
```

Breakdown by module:

- `tests/test_api.py` — 33 passed (Phase 1–4 + Plan 05-01 baseline)
- `tests/test_coords.py` — 33 passed (Phase 2-01 mapper)
- `tests/test_health.py` — 5 passed + 1 skipped (POSIX-only unreadable-originals)
- `tests/test_ingest.py` — 42 passed (Phase 1–4 + 5 new Phase 5)
- `tests/test_integrity.py` — 6 passed (Phase 5 NEW)
- `tests/test_janitor.py` — 8 passed (Phase 5 NEW)
- `tests/test_logo.py` — 22 passed (Phase 3)
- `tests/test_phase1_gaps.py` — 6 passed
- `tests/test_phase2_gaps.py` — 3 passed
- `tests/test_process_api.py` — 43 passed (Phase 2-3-4 + 9 new Phase 5)
- `tests/test_redact.py` — 34 passed (including AGPL seam grep)
- `tests/test_render.py` — 9 passed
- `tests/test_storage.py` — 43 passed (Phase 1–4 + 8 new Phase 5)

Source-grep acceptance (33 grep gates from `<acceptance_criteria>` across the three tasks): all 33 pass.

## Known Limitations / Deferred

- **Pitfall 1 — Thread cannot be killed after 504**: documented inline in `app/api/process.py` AND in `README.md::Known Limitations` (added by Plan 05-01 Task 3). UVICORN_WORKERS=2 is the v1 mitigation; ProcessPoolExecutor upgrade path is deferred to v1.x if real abuse appears.
- **D-B2 frontend test coverage** (acceptance accepted source-grep + DOM structure): "literal `此次處理 1 小時內完成下載` in app.js" + "`.app-session-hint` block in app.css" + "aria-live='polite' wired in JS" are grep-asserted (manual run shown above). A `tests/test_frontend_session_hint.py` BeautifulSoup-driven check is **deferred to phase-level UAT**.
- **SHA-256 forge (T-05-04)** — accepted for v1 LAN. Public-network deployment must add HMAC-signed meta.json (use a server-side key + hmac.compare_digest verify); the existing IntegrityError code path stays unchanged, only `compute_original_hash` / `verify_original_hash` would need re-signing.
- **`.corrupted` sentinel bypass (T-05-06)** — accepted for v1 LAN (attacker who can rewrite filesystem is already inside). HMAC-signed sentinel deferred to public-network upgrade.
- **CORS_ALLOW_ORIGINS** — off by default. Sub-domain embedding (e.g. Ubuntu portal: `pdf-logo.internal` ≠ `intranet.internal`) sets the env var; no code change required.
- **Phase-level UAT items** (carried over from Plan 05-02 `<output>` spec):
  - **(a)** Zeabur deploy + manual SHA-256 篡改 round-trip — needs Zeabur account + live deployment.
  - **(b)** Ubuntu nginx strip-prefix embedding — needs Ubuntu portal staging.
  - **(c)** Large CAD 50 MB PDF /process timeout characterization — needs real customer 50 MB sample.

## Pitfall Inline Notes Verification

- **`app/api/process.py`** — Pitfall 1 inline comment present (multi-line block before the `asyncio.wait_for` call) explaining: timeout returns 504 but thread keeps running; MAX_RENDER_PIXELS+MAX_PAGES collapse worst case; UVICORN_WORKERS=2 keeps preview alive; ProcessPoolExecutor upgrade path documented. Grep gate: `grep -A 2 "Pitfall 1" app/api/process.py` returns non-empty.
- **`app/services/integrity.py`** — Module docstring documents Pitfall 4 (legacy session fail-closed) and T-05-04 disposition (accept as informational).
- **`app/services/janitor.py`** — Module docstring documents D-B4 race protection (TTL ≫ timeout) and AGPL seam guarantee.

## Self-Check: PASSED

- All 5 created files exist on disk:
  - `app/services/integrity.py` ✓
  - `app/services/janitor.py` ✓
  - `tests/test_integrity.py` ✓
  - `tests/test_janitor.py` ✓
  - `tests/test_health.py` ✓
- All 8 modified files contain Phase 5 markers:
  - `app/config.py` contains `SESSION_TTL_SECONDS` ✓
  - `app/storage.py` contains `def is_session_corrupted` ✓
  - `app/services/ingest.py` contains `compute_original_hash(data)` ✓
  - `app/services/pipeline.py` contains `verify_original_hash(session_id)` ✓
  - `app/api/process.py` contains `asyncio.wait_for` + `is_session_corrupted` ✓
  - `app/api/sessions.py` contains `janitor.sweep_expired_sessions` ✓
  - `app/main.py` contains `"original_tampered": 503` + lifespan `janitor.sweep_expired_sessions` ✓
  - `web/js/app.js` contains `此次處理 1 小時內完成下載` + `app-session-hint` ✓
  - `web/styles/app.css` contains `.app-session-hint` ✓
- All 6 task commits visible in `git log --oneline`:
  - `732bcde` test(05-02): add failing tests for atomic meta + storage helpers + integrity ✓
  - `ad72796` feat(05-02): atomic meta + 5 storage helpers + integrity module ✓
  - `4958cbc` test(05-02): add failing tests for janitor module + pipeline verify integration ✓
  - `c2c1f0f` feat(05-02): janitor module + pipeline verify_original_hash integration ✓
  - `fc43fa4` test(05-02): add failing tests for /process timeout + corrupted gate + janitor triggers ✓
  - `852b75f` feat(05-02): /process timeout + corrupted gate + janitor 3 triggers + frontend mapping ✓
- AGPL seam preserved: `python -c "import ast; ..."` AST-grep on integrity.py + janitor.py returns 0 fitz imports ✓
- Test count regression check: Phase 4 baseline 243 → Phase 5 Plan 02 close 287 + 1 skipped = 288 total. +45 new tests, **zero regressions**.

## TDD Gate Compliance

Each task followed the RED → GREEN cycle with separate commits:

- **Task 1**: RED commit `732bcde` (test only) → GREEN commit `ad72796` (impl + tests pass).
- **Task 2**: RED commit `4958cbc` (test only) → GREEN commit `c2c1f0f` (impl + tests pass).
- **Task 3**: RED commit `fc43fa4` (test only) → GREEN commit `852b75f` (impl + tests pass).

No REFACTOR commits were needed (the GREEN implementations matched the patterns in `05-PATTERNS.md` directly).
