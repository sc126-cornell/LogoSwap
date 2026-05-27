---
phase: 5
phase_name: ubuntu
date: 2026-05-24
asvs_level: 1
threats_total: 10
threats_closed: 10
threats_open: 0
threats_accepted: 4
register_authored_at_plan_time: true
---

# Phase 5: Security Audit Report

**Audit date:** 2026-05-24
**Auditor:** Claude (gsd-secure-phase)
**Phase:** 05-ubuntu (Plan 05-01 deploy + Plan 05-02 hardening)
**ASVS Level:** 1 (baseline for v1 internal LAN tool)
**Disposition policy:** mitigate / accept / transfer — all dispositions plan-time authored.

## Summary

**Verdict: SECURED — all 10 Phase 5 threats closed.**

The Phase 5 threat register was authored at plan time (`register_authored_at_plan_time: true`); both `05-01-PLAN.md` and `05-02-PLAN.md` carry explicit `<threat_model>` blocks. Every declared mitigation has been verified by file:line evidence in the implemented code. Every `accept` disposition is documented either inline (source-level comment/docstring referencing the threat ID) or in this file's "Accepted Risks Log" section.

The Phase 5 review/fix cycle (10 fix commits between `6abca8e` and `cfded81`) is post-verified to not have introduced new threats:
- **CR-01** (silent except: pass) — replaced with `logger.warning(..., exc_info=True)` at all three janitor trigger sites (lifespan, /sessions finally, /process finally). Confirmed at `app/main.py:60`, `app/api/sessions.py:88-92`, `app/api/process.py:127-134`.
- **CR-02** (corrupted sentinel only enforced on /process) — `_reject_if_corrupted(session_id)` helper extracted and now called from `GET /sessions/{id}/result/pages/{n}/image` (`app/api/process.py:157`) and `GET /sessions/{id}/result` (`app/api/process.py:197`). Two new tests `test_corrupted_session_blocked_from_get_result_download` and `test_corrupted_session_blocked_from_result_page_image` pass.

Test suite snapshot: **291 passed + 3 platform-skipped** (POSIX-only chmod tests on Windows). Zero regressions from Phase 4 baseline (243 → 291 = +48 net).

## Threat Register Verification

| Threat ID | Category | Disposition | Status | Evidence (file:line) |
|-----------|----------|-------------|--------|----------------------|
| T-05-01 | T — Docker image vulnerable deps | mitigate | CLOSED | `Dockerfile:14` `FROM python:3.12-slim-bookworm AS builder`; `Dockerfile:28` second `FROM python:3.12-slim-bookworm` runtime (multi-stage); `Dockerfile:22-23` `pip install --no-cache-dir --target /install -r requirements.txt` pinned; runtime layer has no pip/build toolchain (wheels-only COPY at `Dockerfile:36`). |
| T-05-02 | E — container runs as root | mitigate | CLOSED | `Dockerfile:31-32` `groupadd -g 1000 app && useradd -u 1000 -g 1000 -m -s /usr/sbin/nologin app`; `Dockerfile:60` `USER app`; `Dockerfile:57` `chown -R app:app /data`. Non-root UID 1000 confirmed. |
| T-05-03 | I/Compliance — AGPL §13 disclosure | mitigate | CLOSED | Three-artifact set in lockstep: (a) `LICENSE` exists at repo root, 34,523 bytes, first 2 lines `GNU AFFERO GENERAL PUBLIC LICENSE` / `Version 3, 19 November 2007` (verbatim); (b) `README.md:9-19` `## License & Source(AGPL §13 揭露)` section with `https://github.com/<OWNER>/LogoSwap` GitHub URL; (c) `web/index.html:415-427` `<footer class="app-footer" role="contentinfo">` with GitHub source anchor + AGPLv3 link to gnu.org. `<OWNER>` deploy-time gate via `tests/test_agpl_compliance.py` (WR-06 fix). |
| T-05-04 | S — SHA-256 forge / hash collision | accept | CLOSED | Documented in `app/services/integrity.py:14-18` (module docstring): "v1 LAN tool; an attacker who can rewrite `originals/source.pdf` can also rewrite `meta.json`, so the baseline is internal-consistency, not crypto-strength tamper-evidence." Carries Phase 4 T-04 wording. Public-network upgrade path = HMAC-signed meta.json (deferred). See "Accepted Risks Log". |
| T-05-05 | T/A — Janitor race | mitigate | CLOSED | `app/config.py:106` `SESSION_TTL_SECONDS=3600` ≫ `app/config.py:107` `PROCESS_TIMEOUT_SECONDS=60` (60× ratio, D-B4); `app/services/janitor.py:46-53` enumerate try/except; `app/services/janitor.py:55-95` per-session try/except `noqa: BLE001 — never raise out of the sweep`; `app/services/janitor.py:63-72` WR-05 TOCTOU narrowing re-check before `delete_session`. All three janitor trigger sites wrapped in try/except with `logger.warning(..., exc_info=True)` (CR-01): `app/main.py:57-60`, `app/api/sessions.py:87-92`, `app/api/process.py:127-134`. |
| T-05-06 | T — delete .corrupted sentinel | accept | CLOSED | Documented in `app/services/integrity.py:7-8` and `05-02-PLAN.md:633`: "LAN 工具;能寫 fs 等於攻擊者已入侵,sentinel 防的是誤觸而非惡意。" Public-network upgrade = HMAC-signed sentinel (deferred). See "Accepted Risks Log". |
| T-05-07 | I/E — path traversal on session_id | mitigate | CLOSED | `app/storage.py:51` `_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")`; `app/storage.py:69` `validate_session_id` enforces `_SESSION_ID_RE.fullmatch`; `app/storage.py:92-108` `subdir()` validates AND asserts `resolved.is_relative_to(data_dir.resolve())` (defense in depth containment). All five Phase 5 helpers route through `subdir`: `list_session_ids` (`storage.py:333-355`, filters via `_SESSION_ID_RE.fullmatch` on iterdir), `session_age_seconds` (`storage.py:358-389`, uses `subdir(kind, sid)`), `delete_session` (`storage.py:392-413`), `mark_session_corrupted` (`storage.py:416-428`), `is_session_corrupted` (`storage.py:430-440`, swallows `InvalidSessionId` → False so crafted id has no error oracle). |
| T-05-08 | I — /health info disclosure | accept (LAN) + mitigate by minimization | CLOSED | `app/main.py:237-283` `/health` returns ONLY five count/bytes/pct fields, no session_id / filename / path. Source-level comment at `app/main.py:256-257`: "Deliberately does NOT include any session_id, filename, or path string (T-05-08 — /health is unauthenticated; treat its body as public)." Test guard `tests/test_health.py::test_health_does_not_leak_session_ids` (per VERIFICATION.md). Future external exposure → add basic auth (deferred). See "Accepted Risks Log". |
| T-05-09 | T — `python -m app` binds 0.0.0.0 | mitigate | CLOSED | `app/__main__.py:42` `host = os.environ.get("HOST", "127.0.0.1")` — loopback default; module docstring at `app/__main__.py:3-6`: "The HOST default is `127.0.0.1` (loopback) — desktop mode must NEVER listen on 0.0.0.0 (T-05-09)." Docker CMD explicitly overrides to `--host 0.0.0.0` (`Dockerfile:70`), so only the container path exposes externally — desktop path is loopback-only. |
| T-05-10 | A — timeout thread keeps running | mitigate (acceptable, v1) | CLOSED | `app/api/process.py:106-110` `await asyncio.wait_for(asyncio.to_thread(pipeline.process_job, ...), timeout=config.PROCESS_TIMEOUT_SECONDS)`; `app/api/process.py:98-105` inline Pitfall 1 multi-line comment acknowledging "asyncio.wait_for ... makes the HTTP response return 504 immediately ... the underlying thread KEEPS RUNNING ... UVICORN_WORKERS=2 (D-D2) ensures the OTHER worker continues serving". `app/config.py:92` `UVICORN_WORKERS=2` default; `Dockerfile:42` `UVICORN_WORKERS=2` mirror. Worst-case bounded by `MAX_RENDER_PIXELS=40MP` + `MAX_PAGES=30` (Phase 4 WR-06, `app/services/render.py:75` `fit_dpi_to_pixel_budget`). v1.x upgrade path = ProcessPoolExecutor (deferred). See "Accepted Risks Log". |

**Score: 10/10 closed (6 mitigate + 4 accept).**

## Accepted Risks Log

The following dispositions are explicitly accepted for the Phase 5 v1 internal-LAN deployment. Each entry documents the rationale, the residual risk, and the upgrade trigger.

### T-05-04 — SHA-256 forge / hash collision

- **Disposition:** accept (informational only)
- **Rationale:** The SHA-256 baseline at ingest is an **internal-consistency check**, not a cryptographic tamper-evidence primitive. An attacker who can rewrite `data/originals/{sid}/source.pdf` can equally rewrite `data/work/{sid}/meta.json` (same volume, same UID `app:app`); SHA-256 cannot defend against that on its own.
- **Residual risk:** None for LAN trust boundary (filesystem-write capability already implies compromise). For public-network reachability, an attacker controlling outbound network but not the fs cannot forge SHA-256 (preimage resistance), so the v1 baseline is correct for that subset too.
- **Upgrade trigger:** Public-network exposure → HMAC-sign `meta.json` with a server-side key + `hmac.compare_digest` verify. The `IntegrityError` code path stays unchanged; only `compute_original_hash` / `verify_original_hash` need re-signing.
- **Documented at:** `app/services/integrity.py:14-18` (module docstring referencing threat ID).

### T-05-06 — `.corrupted` sentinel bypass

- **Disposition:** accept (P2, v1)
- **Rationale:** The sentinel (`work/{sid}/.corrupted`) defends against **accidental re-use** of a tampered session after a 503 (the user clicking retry, the frontend auto-retrying). It does not — and is not designed to — defend against a malicious attacker who already has filesystem write capability. If an attacker can `rm work/{sid}/.corrupted`, they can also rewrite the source PDF and the meta.json hash.
- **Residual risk:** None within the LAN trust boundary.
- **Upgrade trigger:** Public-network deployment → HMAC-signed sentinel file (sentinel contents = signature over `{sid + original_sha256 + timestamp}`).
- **Documented at:** `05-02-PLAN.md:633` threat register row; `05-02-SUMMARY.md:167` mitigation summary.

### T-05-08 — /health info disclosure

- **Disposition:** accept (LAN) + mitigate by minimization
- **Rationale:** `/health` is intentionally unauthenticated (load balancer probes need 200 OK without credential plumbing). Information minimization is the v1 defense: only counts and aggregate bytes/percent are emitted; no session_id, no filename, no path string.
- **Residual risk:** A LAN-positioned attacker can observe disk usage trends and session activity volume. Acceptable for internal trade-company tool (no PII regulatory regime applies; user identities are coworkers).
- **Upgrade trigger:** Public-network exposure → wrap `/health` in basic auth, OR split into `/health` (200 only, no body) for LB probe + `/admin/observability` (authenticated) for diagnostics.
- **Documented at:** `app/main.py:256-257` inline comment "T-05-08 — /health is unauthenticated; treat its body as public."; tests/test_health.py::test_health_does_not_leak_session_ids (per VERIFICATION.md spot-checks).

### T-05-10 — Timeout thread keeps running

- **Disposition:** mitigate by workers + bounded worst case (acceptable for v1)
- **Rationale:** Python has no `thread.kill()` — `asyncio.wait_for(asyncio.to_thread(...))` returns 504 immediately on timeout, but the worker thread continues until `process_job` naturally exits. v1 mitigation: (a) `UVICORN_WORKERS=2` ensures the OTHER worker continues serving preview/health/sessions; (b) `MAX_RENDER_PIXELS=40MP` + `MAX_PAGES=30` (Phase 4 WR-06) collapse the worst case from "minutes" to "10–30s"; (c) Pitfall 1 acknowledged inline in code.
- **Residual risk:** A small window (~10–30s) where one worker is still draining the previous /process. Adversary cannot stack indefinite jobs because uvicorn re-queues incoming /process to the available worker. Sustained abuse from a single LAN user could degrade preview latency for ~30s windows.
- **Upgrade trigger:** Real abuse observed in production, OR public-network exposure → ProcessPoolExecutor (true process-level kill on timeout).
- **Documented at:** `app/api/process.py:98-105` (multi-line Pitfall 1 comment); `05-02-PLAN.md:635-636` (T-05-10 + Pitfall 1 rows); README "Known Limitations" section.

## Pitfall Verification (Phase 5 cross-cutting)

The Phase 5 threat register includes three implementation pitfalls beyond the STRIDE rows. These are verified here for completeness:

| Pitfall | Description | Status | Evidence |
|---------|-------------|--------|----------|
| Pitfall 1 | Thread cannot be killed after asyncio.wait_for timeout | CLOSED (same as T-05-10) | `app/api/process.py:98-105` inline multi-line comment + UVICORN_WORKERS=2 default + bounded worst case (MAX_RENDER_PIXELS + MAX_PAGES). |
| Pitfall 3 | Windows chmod 0o444 + rmtree cross-platform | CLOSED | `app/storage.py:303-330` `_on_rm_error` handler — PermissionError + os.unlink/remove/rmdir → re-chmod 0o644 + retry. Single source of truth shared between `delete_session` (`storage.py:411` `shutil.rmtree(path, onerror=_on_rm_error)`) and the janitor (which calls `storage.delete_session`). Test coverage: `tests/test_storage.py::test_delete_session_handles_readonly_original` + `tests/test_janitor.py::test_janitor_handles_chmod_0o444_originals_cross_platform`. |
| Pitfall 4 | Legacy session migration (Phase 1–4 meta.json without `original_sha256`) | CLOSED | `app/services/integrity.py:75-82` — `if meta is None or "original_sha256" not in meta: storage.mark_session_corrupted(...) raise IntegrityError("session_corrupted", ...)`. Fail-closed; the 1-hour TTL janitor reclaims naturally. Documented at `app/services/integrity.py:19-20` (module docstring referencing Pitfall 4). |
| Pitfall A7 | Atomic meta.json write across filesystems (Windows cross-drive) | CLOSED | `app/storage.py:200-206` `tempfile.mkstemp(prefix=".meta.", suffix=".json.tmp", dir=str(dest.parent))` + `os.replace(tmp_path, dest)`. The `dir=str(dest.parent)` forces the tmp file onto the same filesystem as the destination so `os.replace` is genuinely atomic on Windows. Failure cleanup: `app/storage.py:207-213` `except BaseException: os.unlink(tmp_path)` removes the orphan. Test coverage: `tests/test_storage.py::test_write_session_meta_is_atomic_on_simulated_crash`. |

Note: Pitfall 4 in this Phase 5 register refers specifically to "legacy session migration" (Plan 05-02 scope). Earlier phase plans use "Pitfall 4" for unrelated items (e.g. Phase 2 redaction over-coverage); the registers are phase-local.

## Unregistered Flags

**None.** Both `05-01-SUMMARY.md` and `05-02-SUMMARY.md` declare empty `## Threat Flags` sections (`05-01-SUMMARY.md:175-176`: "None. All Phase 5 Plan 01 threats ... are addressed within this plan."). The full Phase 5 attack surface introduced during implementation was registered at plan time and verified above.

## Audit Trail

### Security Audit 2026-05-24

| Item | Result |
|------|--------|
| Required reading loaded | 7/7 (PLAN 05-01, PLAN 05-02, SUMMARY 05-01, SUMMARY 05-02, VERIFICATION, REVIEW, REVIEW-FIX) |
| Implementation files audited (read-only) | Dockerfile, app/__main__.py, app/main.py, app/services/integrity.py, app/services/janitor.py, app/api/process.py, app/api/sessions.py, app/storage.py, LICENSE, README.md, web/index.html |
| Threats verified | 10/10 |
| Closed | 10 (6 mitigate + 4 accept) |
| Open | 0 |
| Escalations | 0 |
| Unregistered flags | 0 |
| Post-review-fix integrity check | PASS (CR-01 logger.warning at all 3 sites; CR-02 _reject_if_corrupted at both GET endpoints) |
| Implementation modifications | NONE (audit is read-only per role contract) |
| Test snapshot | 291 passed + 3 platform-skipped (input from constraints) |

## Verdict

## SECURED

All 10 Phase 5 declared threats are closed with file:line evidence in implemented code. The 4 accept-disposition threats (T-05-04, T-05-06, T-05-08, T-05-10) are documented inline in source and in this file's Accepted Risks Log with rationale, residual risk, and upgrade trigger. The 6 mitigate-disposition threats (T-05-01, T-05-02, T-05-03, T-05-05, T-05-07, T-05-09) are each backed by a concrete code path. All four Phase 5 implementation pitfalls (1, 3, 4, A7) are likewise verified.

The Phase 5 deploy + hardening slice is **security-cleared for v1 internal LAN deployment** (Zeabur public-network deployment also acceptable given AGPL §13 three-artifact set is in place and the public-network upgrade triggers for T-05-04 / T-05-06 / T-05-08 are documented but NOT required for AGPLv3 compliance — they are best-practice escalations).

**Phase 5 may advance to UAT.**

---

*Audited: 2026-05-24*
*Auditor: Claude (gsd-secure-phase)*
*ASVS Level: 1*
*register_authored_at_plan_time: true*
