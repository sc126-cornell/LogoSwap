---
phase: 05-ubuntu
fixed_at: 2026-05-24T00:00:00Z
review_path: .planning/phases/05-ubuntu/05-REVIEW.md
iteration: 1
depth: standard
date: 2026-05-24
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-05-24
**Source review:** `.planning/phases/05-ubuntu/05-REVIEW.md`
**Iteration:** 1
**Depth:** standard

**Summary:**
- Findings in scope: 9 (2 BLOCKER + 7 Warning)
- Fixed: 9
- Skipped: 0
- Test suite after fixes: 290 passed, 3 skipped, 1 pre-existing failure (NOT introduced — see "Notes" below)

## Fixed Issues

### CR-01: Startup janitor swallows ALL exceptions with no diagnostic

**Severity:** BLOCKER
**Files modified:** `app/main.py`, `app/api/sessions.py`, `app/api/process.py`
**Commit:** `6abca8e`
**Applied fix:** Replaced all three `except Exception: pass` blocks (lifespan startup, /sessions POST `finally`, /process `finally`) with `logger.warning(..., exc_info=True)`. Added `import logging` + module-level `logger = logging.getLogger(__name__)` to each file. The /process log line carries the session_id for context. Tests still see clean 200 responses (the diagnostic is a log line, not a response change), so existing janitor-failure tests (e.g. `test_janitor_failure_does_not_taint_process_request`) keep passing.

### CR-02: `.corrupted` sentinel NOT enforced on GET /result + GET /result/pages/{n}/image

**Severity:** BLOCKER
**Files modified:** `app/api/process.py`, `tests/test_process_api.py`
**Commit:** `b02ae56`
**Applied fix:** Extracted the existing inline corrupted-session 410 raise from `process_session` into a shared `_reject_if_corrupted(session_id)` helper, then called it from both GET endpoints (`get_result_page_image` and `download_result`) right after `_require_session`. Contract is now uniform across all three D-C3 surfaces. Added two new tests: `test_corrupted_session_blocked_from_get_result_download` (process → download → mark corrupted → 410) and `test_corrupted_session_blocked_from_result_page_image` (render before-image → mark corrupted → 410). Both tests + 3 existing corrupted tests pass.

### WR-01: `__main__.py` ignores empty / non-integer PORT and UVICORN_WORKERS

**Severity:** WARNING
**Files modified:** `app/__main__.py`
**Commit:** `f7ad897`
**Applied fix:** Replaced `int(os.environ.get(...))` with the existing `config._env_int` helper for both `PORT` and `UVICORN_WORKERS`. The helper handles `None`, empty string, and non-integer input by falling back to the default — matching the rest of the codebase (consistency over duplication). Verified by running `_env_int('PORT', 8000)` against `PORT=""` and `_env_int('UVICORN_WORKERS', 1)` against `UVICORN_WORKERS=auto` (both return the default cleanly instead of raising `ValueError`).

### WR-02: `/health` `active_sessions` undercounts during image-ingest race window

**Severity:** WARNING
**Files modified:** `app/main.py`, `tests/test_health.py`
**Commit:** `88d933c`
**Applied fix:** Replaced the inline `originals/` scan in `/health` with `sum(1 for _ in storage.list_session_ids())` — the canonical "well-formed session" surface that covers all four kind dirs and is already covered by unit tests. Updated the POSIX chmod-0 test (`test_health_active_sessions_minus_one_on_unreadable_originals` → renamed to `test_health_active_sessions_robust_to_unreadable_kind_dir`) because `list_session_ids` catches `OSError` per-root and continues, so a single unreadable kind dir no longer surfaces -1; the new assertion is "endpoint stays 200 + count is a non-negative int or -1" — matching the actual robustness contract. Docstring at `/health` updated to describe the new semantic.

### WR-03: `session_age_seconds` mtime fragility against future overwrite-in-place refactor

**Severity:** WARNING
**Files modified:** `app/storage.py`
**Commit:** `f8fda90`
**Applied fix:** Added a WR-03 paragraph to the `session_age_seconds` docstring explaining the dependency on rename-based atomic replace (which IS what `pipeline.py`'s tempfile-then-os.replace flow does today) and flagging that a future refactor to overwrite-in-place would silently break mtime detection. Pure documentation change — no behavior change, no test change.

### WR-04: Janitor `deleted` counter misleading on Windows partial-rmtree

**Severity:** WARNING
**Files modified:** `app/services/janitor.py`
**Commit:** `8734bdc`
**Applied fix:** Replaced the `if not any(...): deleted += 1` block with an explicit `remaining = [kind for kind in (...) if exists]` list. When `remaining` is empty (full delete), increment `deleted`. When non-empty (Windows open-handle case), log at WARNING with the list of kind dirs still present so the half-state is observable instead of the sweep silently returning 0. Existing `test_janitor_sweeps_expired_session` (which asserts `deleted >= 1` on a clean POSIX run) still passes.

### WR-05: TOCTOU between `session_age_seconds` and `delete_session`

**Severity:** WARNING
**Files modified:** `app/services/janitor.py`
**Commit:** `22bf973`
**Applied fix:** Added a re-check of `storage.session_age_seconds(sid)` immediately before the `delete_session` call. If the re-check shows the session is no longer expired (because a concurrent worker's `/process` bumped outputs/{sid} mtime between the two checks), `continue` to the next sid — the next sweep round will revisit it once it ages out again. Narrows the TOCTOU window from "anywhere between iteration loop entry and rmtree" to "the microseconds between the second stat and rmtree itself". Eliminating the window entirely would require an inter-worker lock; rejected per D-B4 ("single-process LAN tool — no IPC lock").

### WR-06: `<OWNER>` placeholder ships in production HTML/markdown — no automated gate

**Severity:** WARNING
**Files modified:** `tests/test_agpl_compliance.py` (new)
**Commit:** `fca14fb`
**Applied fix:** Added a new test module with two parametrized test families:

  1. `test_owner_placeholder_present_in_pristine_repo[index.html|README.md]` — asserts the placeholder IS present in the pristine source tree, catching the case where a developer accidentally hand-substitutes their personal GitHub handle. Runs on every CI run (no env gate). PASSES on dev branches.

  2. `test_owner_placeholder_substituted_before_release[index.html|README.md]` — guarded by `LOGOSWAP_RELEASE_GATE=1`. Asserts the placeholder is ABSENT — used by the deploy pipeline as a fail-closed gate. Skipped by default (dev branches stay green) and FAILS when run on un-substituted production HTML. Verified by running `LOGOSWAP_RELEASE_GATE=1 pytest tests/test_agpl_compliance.py` — both release-gate tests fail loudly as expected.

The two regimes are documented in the module docstring and the test skipif reasons, so the deploy operator gets clear instructions on how to wire the gate (`LOGOSWAP_RELEASE_GATE=1 pytest tests/test_agpl_compliance.py` after the substitution step).

### WR-07: `app-session-hint` inserted inside `<main>` breaks the `app-shell` grid

**Severity:** WARNING
**Files modified:** `web/js/app.js`, `web/styles/app.css`
**Commit:** `63fc4ce`
**Applied fix:** Changed `ensureSessionHintEl()` to insert the hint as a direct child of `.app-shell`, immediately before `.app-footer` — NOT inside `<main>`. Updated `.app-shell { grid-template-rows: auto 1fr auto auto; }` (was 3 rows; now 4 — toolbar | main | hint | footer). When `[hidden]` (default), the hint row collapses to 0 so the pre-fix 3-row appearance is preserved until a TTL hint actually shows. Fixed the misleading comment about the hint living "inside the page-stage container" (it now genuinely lives at app-shell level). Defensive fallbacks: append to `.app-shell` if footer is missing; ultimately fall back to `document.body`. Node `--check` confirms the JS parses.

## Skipped Issues

None — all 9 in-scope findings were fixed cleanly.

## Notes

**Pre-existing test failure (NOT introduced by these fixes):**

`tests/test_integrity.py::test_integrity_module_does_not_import_fitz` fails before AND after this fix batch. The test uses a naive substring grep:

```python
assert "import fitz" not in src
```

against `app/services/integrity.py`. The module's docstring contains the literal phrase **"NO ``import fitz``"** at line 11 — explaining the AGPL seam invariant. The naive grep matches that explanation, not an actual import. The module itself has NO `import fitz` statement (verified). This is a test-logic bug (should use AST analysis, e.g. `ast.walk(tree)` checking `ast.Import`/`ast.ImportFrom` nodes), not a real AGPL seam violation. Out of scope for this review-fix iteration; flagged here for the next code-review pass.

**Test count delta:**
- Before fixes: 286 passed, 1 skipped, 1 failed
- After fixes: 290 passed (+4: CR-02 ×2 new tests + WR-06 pristine ×2 new tests), 3 skipped (+2: WR-06 release-gate ×2 skipped without env var; 1 existing POSIX skip), 1 failed (unchanged — pre-existing integrity grep test)

---

_Fixed: 2026-05-24_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
