---
phase: 03-logo-placement
plan: 01
subsystem: logo-library + picker
tags: [LOGO-01, logo-library, picker, path-traversal-defense, fitz-free]
requires:
  - "Phase 1/2 spine: storage allowlist (validate_session_id/subdir), render.RenderError shape, main.py typed-error handlers, web/js/api.js sole seam, web/js/regions.js stale machine, side-panel column"
provides:
  - "logo.resolve(logo_id) -> bytes (manifest allowlist) — consumed by 03-02 pipeline"
  - "logo.list_logos() -> [{id, name, tags}]"
  - "GET /logos + GET /logos/{id}/image endpoints"
  - "config.LOGOS_DIR + config.MAX_LOGO_BYTES"
  - "LogoError typed error + main.py exception handler (404/422)"
  - "web/js/logos.js getSelectedLogoId() + selectedLogoId client state — consumed by 03-02"
  - "regions.js notifyJobInputChanged() shared stale hook"
affects:
  - app/config.py
  - app/main.py
  - app/services/logo.py
  - app/api/logos.py
  - web/js/api.js
  - web/js/regions.js
  - web/js/app.js
  - web/index.html
  - web/styles/app.css
  - web/styles/tokens.css
  - logos/manifest.json
  - logos/placeholder.png
  - tests/test_logo.py
  - tests/conftest.py
tech-stack:
  added: []
  patterns:
    - "manifest-dict allowlist (logo_id is a key, never a path) + is_relative_to containment assert (T-03-01, mirrors storage.subdir)"
    - "lazy config read (_logos_dir) for monkeypatchable tests (mirrors _data_dir)"
    - "per-asset try/except skip in list_logos (bad asset never crashes the catalog)"
    - "createElement-only DOM build + api.js sole seam (no innerHTML, no direct fetch)"
    - "ONE shared stale machine reused via regions.notifyJobInputChanged (no fork)"
key-files:
  created:
    - app/services/logo.py
    - app/api/logos.py
    - web/js/logos.js
    - logos/manifest.json
    - logos/placeholder.png
    - tests/test_logo.py
  modified:
    - app/config.py
    - app/main.py
    - web/js/api.js
    - web/js/regions.js
    - web/js/app.js
    - web/index.html
    - web/styles/app.css
    - web/styles/tokens.css
    - tests/conftest.py
decisions:
  - "[03-01] logo_id resolves ONLY as a manifest dict key + is_relative_to(LOGOS_DIR) assert; never LOGOS_DIR/logo_id (T-03-01)"
  - "[03-01] %2F-encoded / URL-normalized traversal forms 404 at routing before any handler (still safe, no path build); reachable crafted ids map to structured logo_not_found"
  - "[03-01] logo.py/logos.py are fitz-free (json/pathlib/PIL/config only) — AGPL seam intact, enforced by existing AST grep test"
  - "[03-01] ONE shared stale machine: logos.js calls regions.notifyJobInputChanged(staleNotice) on every selection change (Pitfall 5), not a forked action group"
  - "[03-01] Picker is the ONE new accent element (selected thumbnail ring); hover is neutral --color-neutral-hover; only two new theme-agnostic tokens added"
metrics:
  duration: ~25 min
  completed: 2026-05-22
---

# Phase 3 Plan 01: Logo Library + Side-Panel Picker Summary

Fixed read-only logo library (`logos/` + `manifest.json`) served via fitz-free `logo.py` (manifest-allowlist `resolve(logo_id)->bytes` with an `is_relative_to(LOGOS_DIR)` containment assert), `GET /logos` + `GET /logos/{id}/image` endpoints, and a side-panel single-select thumbnail picker (`logos.js`) that reuses the Phase-2 dual-theme tokens, 繁中 copy, and the one shared stale machine — delivering the LOGO-01 browse/pick slice end-to-end and the `logo.resolve` / `selectedLogoId` contract 03-02 will consume.

## What Was Built

**Task 1 — backend (TDD, RED→GREEN):**
- `config.LOGOS_DIR` (`./logos` default, `.resolve()`) + `config.MAX_LOGO_BYTES` (10 MB per-asset DoS cap, T-03-02).
- `app/services/logo.py` (fitz-free): `LogoError` typed error (`logo_not_found`→404, `logo_invalid`/`logo_unreadable`→422); `_logos_dir()` lazy read; `_load_manifest()` graceful `{}` on absent/bad manifest; `list_logos()` skips bad assets per-entry; `resolve(logo_id)` = manifest dict lookup → `is_relative_to` assert → Pillow `verify()` → raw PNG bytes. Never builds `LOGOS_DIR / logo_id`.
- `app/api/logos.py`: `GET /logos` (`{logos: list_logos()}`) + `GET /logos/{id}/image` (`run_in_threadpool(logo.resolve)` → 404/422 map → `Response(image/png)`).
- `app/main.py`: `LogoError` import + router registration + `_LOGO_STATUS` table + `@app.exception_handler(LogoError)` (mirrors `_handle_redact_error`; covers a `LogoError` raised inside 03-02's `/process`, T-02-08).
- Seeded `logos/manifest.json` + a transparent `logos/placeholder.png` (842 B) so the picker is non-empty at runtime.
- `tests/test_logo.py` (5 tests) + `logo_png_bytes` / `logo_library` in-memory fixtures in `conftest.py`.

**Task 2 — frontend:**
- `web/js/api.js`: `listLogos()` + `logoImageURL()` seam helpers + JSDoc contract block for the three Phase-3 endpoints and the optional `/process` `logo_id`.
- `web/js/logos.js`: createElement-only single-select grid, `不置入商標` clear cell, loading/empty/failed states, verbatim 繁中 `COPY`; `initLogos`/`resetLogos`/`getSelectedLogoId` exports; calls `regions.notifyJobInputChanged()` on selection change.
- `web/js/regions.js`: `notifyJobInputChanged(message)` exported hook running the same stale branch as `onRegionsEdited` (one machine, Pitfall 5).
- `web/index.html`: logo-picker section below the region list inside `.side-panel__inner`; `logos.js` script ordered after `regions.js`, before `app.js`.
- `web/js/app.js`: `initLogos`/`resetLogos` wired alongside the region equivalents (load success, catch reset, error-retry).
- `web/styles/tokens.css`: `--logo-thumb-size` + `--logo-grid-gap` (no new color tokens).
- `web/styles/app.css`: `.logo-grid` auto-fill grid, `.logo-thumb` (neutral `--color-surface` backing + neutral hover), `.logo-thumb.is-selected` accent ring (the one new accent element), `object-fit: contain` thumbs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Path-traversal test over-asserted framework routing behaviour**
- **Found during:** Task 1 (GREEN run)
- **Issue:** The test asserted a `%2F`-encoded `../../app/config.py` id and a bare `..` id would both reach the handler and return a structured `{detail:{code:"logo_not_found"}}`. In practice Starlette/httpx URL-normalize those forms and 404 them at routing *before* any handler runs (body `{"detail":"Not Found"}`), so `.json()["detail"]["code"]` raised `TypeError`. The security property still holds (never a path build, never a 500) — only the assertion shape was wrong.
- **Fix:** Split the assertion: encoded-multi-segment / normalized forms must be a 404 (never 500) without requiring the structured code; reachable single-segment crafted ids (`%2e%2e`, unknown id) must carry the structured `logo_not_found`. Documented the rationale in the test docstring.
- **Files modified:** tests/test_logo.py
- **Commit:** be41d3d

**2. [Rule 3 - Blocking] `innerHTML` literal in logos.js comments tripped the substring grep**
- **Found during:** Task 2 (automated verify)
- **Issue:** The Task 2 verify uses a substring check `'innerHTML' not in src`; two explanatory comments contained the literal token "innerHTML", failing the XSS guard even though the code never uses it.
- **Fix:** Reworded both comments to "no HTML-string injection" so the source contains no `innerHTML` token. The code was already createElement-only.
- **Files modified:** web/js/logos.js
- **Commit:** 1442676

## Authentication Gates

None — no auth in this project (internal LAN, v1).

## Tests

- `tests/test_logo.py` — 5 tests (list, empty-library degrade, image happy, traversal rejection, bad-asset skip): all green.
- Full suite: 155 passed (150 prior + 5 new), including `test_fitz_import_confined_to_engine_seam` confirming `logo.py`/`logos.py` did not leak fitz.
- Static (logos.js): no `innerHTML`, no direct `fetch(`, uses `api.listLogos`/`api.logoImageURL` — Task 2 automated check passes.

## Notes for 03-02

- Consume `logo.resolve(logo_id) -> bytes` in the pipeline (place AFTER `redact.remove_region` on the same `pdf_rect`); the `LogoError` handler already maps failures to 4xx.
- Read the picker selection via `getSelectedLogoId()` and include it as `logo_id` in `api.processJob(...)`. Add `logo_id` to `JobSpec` (deferred to 03-02 per plan).
- Add `pdf_engine.place_logo` (the only new fitz call) and the conditional `#view-result` relabel (`移除+置入結果`) in 03-02.

## Known Stubs

None. The `logos/placeholder.png` is an intentional seed asset (admin replaces it in deploy); the picker is fully wired to live data via `GET /logos`.

## Self-Check: PASSED

All created files exist on disk; all three per-task commits (4be1ee1 RED, be41d3d GREEN, 1442676 frontend) are present in git history.
