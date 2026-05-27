---
phase: 03-logo-placement
verified: 2026-05-22T00:00:00Z
resolved: 2026-05-23
status: passed
score: 9/9 must-haves verified + 6 human-UAT items resolved (see 03-HUMAN-UAT.md)
overrides_applied: 0
human_verification:
  - test: "Load a PDF in the browser. In the side panel, verify the 我司商標 section appears below the region list with the placeholder thumbnail on a neutral backing. Switch between light and dark themes and confirm the grid renders correctly in both."
    expected: "Thumbnail grid visible with placeholder logo, neutral background (not accent), both themes work."
    why_human: "Cannot verify CSS theme rendering programmatically."
  - test: "Click the placeholder thumbnail. Confirm an accent-ring border appears around it (accent ring, not neutral hover). Click 不置入商標 and confirm the ring disappears."
    expected: "is-selected accent ring on selection; no ring on clear."
    why_human: "CSS visual state requires a browser."
  - test: "Draw a region, select the placeholder logo, click 套用移除. The after-segment label must read 移除+置入結果. Deselect the logo (click 不置入商標) and re-apply; the after-segment must revert to 移除結果."
    expected: "Conditional relabel per D-06."
    why_human: "DOM text-content change requires browser interaction."
  - test: "With the placeholder selected and a region drawn, click 套用移除. The before/after toggle shows the placeholder logo centered in the framed region in the after-image. Download the PDF and open it — the region contains the logo and the supplier content is gone."
    expected: "Logo visible in the correct position in the after-image preview and in the downloaded PDF."
    why_human: "Visual correctness of logo placement and before/after toggle behavior require human inspection."
  - test: "Apply once (result fresh). Change the selected logo (switch between placeholder and 不置入商標). Confirm the action group reverts to 重新套用 and the notice reads 所選商標已變更,請重新套用以更新結果."
    expected: "Stale-result machine triggers on logo change via notifyJobInputChanged."
    why_human: "DOM/UI state interaction requires browser."
  - test: "Apply twice in sequence (重新套用 flow). Confirm the after-image refreshes and does NOT show the first apply's stale cached PNG."
    expected: "Cache-busting ?v= token causes the browser to fetch a fresh after-image on each apply."
    why_human: "Browser cache behavior requires manual inspection in DevTools."
---

# Phase 3: Logo Placement Verification Report

**Phase Goal:** 在 Phase 2 已真正移除的框選區域內放上我司商標。建立固定商標庫(logos/ + manifest.json)供瀏覽挑選,選定的 logo 以維持長寬比(insert_image keep_proportion)置入移除區域,整合進既有 deferred-mutation 匯出流程;移除與置入可在同一流程完成並下載。
**Verified:** 2026-05-22
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 使用者可從固定商標庫瀏覽並挑選一個 logo (LOGO-01) | VERIFIED | `logos/manifest.json` + `logos/placeholder.png` (842B valid PNG) exist. `GET /logos` endpoint in `app/api/logos.py` serves `list_logos()`. `web/js/logos.js` exports `initLogos`/`resetLogos`/`getSelectedLogoId`. `web/index.html` has `id="logo-picker"` and `id="logo-grid"`. `test_list_logos` passes. |
| 2 | 選定的 logo 以維持長寬比置入框選位置,輸出 PDF 位置正確 (LOGO-02) | VERIFIED | `pdf_engine.place_logo` calls `page.insert_image(keep_proportion=True, overlay=True)`. `keep_proportion=False` absent. `test_inserted_logo_bbox_within_rect_and_aspect_preserved` PASSES (placed bbox within target rect ±TOL, aspect within ASPECT_TOL=0.05). |
| 3 | 移除與置入可在同一流程中完成並下載 (SC-3) | VERIFIED | `pipeline.process_job` resolves logo bytes once, then in the per-region loop calls `redact.remove_region` then `pdf_engine.place_logo` on the same `pdf_rect`. The saved output file is the download artifact. `test_logo_survives_redaction` PASSES (text removed AND logo present). `test_original_unchanged_across_remove_insert` PASSES (SHA-256 unchanged). |

**Score:** 9/9 truths verified (all three roadmap success criteria + all six plan must-have truths confirmed — see sections below)

### Plan 03-01 Must-Have Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 使用者可在側欄縮圖網格中瀏覽固定商標庫並挑選一個 logo (D-05/LOGO-01) | VERIFIED | `logos.js` thumbnails built with `createElement`, `initLogos` wired in `app.js:147`. |
| 2 | GET /logos 回傳商標庫清單（id+name），不洩漏檔案系統路徑 (LOGO-01) | VERIFIED | `_public_entry` returns `{id, name, tags}` only; no `file` key. `test_list_logos` asserts `"file" not in entry`. |
| 3 | 商標庫為空或缺檔時 GET /logos 回 {logos: []}，不 500 (D-04/A2) | VERIFIED | `_load_manifest` catches `(FileNotFoundError, ValueError, OSError)` and returns `{}`. `test_list_logos_empty_library_is_not_500` PASSES. |
| 4 | 未受信任的 logo_id（../或不存在）→ 404 logo_not_found，永不建構路徑，永不 500 (T-03-01) | VERIFIED | `resolve(logo_id)` is a manifest dict lookup only; `is_relative_to(LOGOS_DIR)` containment assert present (`logo.py:84`). `test_logo_id_path_traversal_rejected` PASSES. |
| 5 | 選定的 logo_id 為純前端狀態，更換選取時沿用 Phase 2 stale 機制 (D-05/Pitfall 5) | VERIFIED | `logos.js:91` calls `notifyJobInputChanged(COPY.staleNotice)` on selection change. `notifyJobInputChanged` exported from `regions.js:478`. |
| 6 | 商標庫資產為 PNG 去背格式；載入時以 Pillow 驗證為合法 PNG，不支援 SVG (D-03/LOGO-01) | VERIFIED | `_validate_png` enforces `img.format != "PNG"` → `logo_invalid` (WR-04 fix). `test_non_png_asset_rejected` PASSES. |

### Plan 03-02 Must-Have Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 選定的 logo 以維持長寬比（keep_proportion）置入每個移除區域，置中、完整顯示 (D-02/LOGO-02) | VERIFIED | `place_logo` calls `insert_image(keep_proportion=True, overlay=True)`. LOGO-02 bbox test PASSES. |
| 2 | 輸出 PDF 中 logo 的 bbox 落在使用者框選的同一 pdf_rect 內，長寬比與來源相符 (LOGO-02/REMOVE-03) | VERIFIED | `test_inserted_logo_bbox_within_rect_and_aspect_preserved` asserts containment and aspect. PASSES. |
| 3 | logo 在 apply_redactions 之後置入，移除後的文字/向量仍被真正移除而 logo 本身存活 (D-02/Pitfall 1) | VERIFIED | `pipeline.py:196` remove_region then `pipeline.py:204` place_logo. `test_logo_survives_redaction` PASSES (text=[] AND images non-empty). |
| 4 | 全域單一 logo：所有移除區域置入同一 logo，跨多區重用單一 xref (D-01/Pitfall 4) | VERIFIED | `logo_xref` initialized to 0 before loop; reused for subsequent placements. `test_global_logo_single_xref` PASSES (1 shared xref across 2-page job). |
| 5 | 未選 logo（logo_id 為 null）時為純移除，原始檔 SHA-256 不變 (D-01/D-05) | VERIFIED | `test_process_without_logo_is_pure_removal` PASSES (no embedded image). `test_original_unchanged_across_remove_insert` PASSES (SHA-256 unchanged). |
| 6 | 結果預覽含 logo：現有 /result 端點渲染 work 副本（已含置入的 logo），前後對照標籤條件式改為「移除+置入結果」 (D-06) | VERIFIED | `regions.js` has `refreshResultLabel()` at line 537, sets `#view-result` textContent to `移除+置入結果` when logo selected, `移除結果` when null. Node check passes. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/logo.py` | fitz-free logo service: `list_logos`, `resolve`, `LogoError` | VERIFIED | All three present. Fitz-free confirmed by `test_fitz_import_confined_to_engine_seam`. `is_relative_to` containment assert at line 84. |
| `app/api/logos.py` | GET /logos + GET /logos/{id}/image endpoints | VERIFIED | Both routes present; uses `run_in_threadpool`; structured error mapping. |
| `web/js/logos.js` | Side-panel thumbnail grid, single-select state, `initLogos`/`resetLogos`/`getSelectedLogoId` exports | VERIFIED | All three exports present. No `innerHTML`, no direct `fetch(`. |
| `logos/manifest.json` | Fixed logo library manifest with at least one entry | VERIFIED | One entry: `{"id":"placeholder","file":"placeholder.png","name":"預設商標","tags":[]}`. |
| `tests/test_logo.py` | LOGO-01 list + path-traversal tests (at least 5 tests, 8 including LOGO-02) | VERIFIED | 11 tests collected, all passing. Includes `test_inserted_logo_bbox_within_rect_and_aspect_preserved`. |
| `app/services/pdf_engine.py` | `place_logo(page, rect, *, stream, xref)` + `get_image_rects` | VERIFIED | Both functions present. `keep_proportion=True` explicit; `keep_proportion=False` absent. |
| `app/models.py` | `JobSpec.logo_id: str | None` optional field | VERIFIED | Present at line 94: `logo_id: str | None = Field(default=None, max_length=128, ...)`. |
| `app/services/pipeline.py` | Per-region loop with `place_logo` after `remove_region`, `logo.resolve` call | VERIFIED | `logo.resolve` at line 159; `place_logo` at line 204; strictly after `remove_region`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `web/js/logos.js` | `GET /logos` | `api.listLogos()` (sole seam) | VERIFIED | `api.listLogos` called at line 172; no direct `fetch(` present. |
| `app/services/logo.py` | `config.LOGOS_DIR / entry["file"]` | manifest dict allowlist + `is_relative_to` guard | VERIFIED | `logo.py:83-84`: joins `entry["file"]` then asserts `is_relative_to(logos_dir.resolve())`. |
| `app/main.py` | `LogoError` | `@app.exception_handler(LogoError)` → structured 4xx | VERIFIED | `LogoError` imported at `main.py:27`; `_LOGO_STATUS` table at line 115; handler at line 120. Router registered at line 40. |
| `app/services/pipeline.py` | `pdf_engine.place_logo(page, pdf_rect, ...)` | After `redact.remove_region` on same `pdf_rect` | VERIFIED | `pipeline.py:196` remove_region, `pipeline.py:204` place_logo (same `pdf_rect`). |
| `app/services/pipeline.py` | `logo.resolve(job_spec.logo_id)` | Loop-exterior manifest allowlist resolve (03-01 contract) | VERIFIED | `pipeline.py:159`: `logo.resolve(job_spec.logo_id)`. `logo` imported at line 32. |
| `web/js/regions.js` | `logos.getSelectedLogoId()` | `applyRemoval` includes `logo_id` in `api.processJob` spec | VERIFIED | `regions.js:36` imports `getSelectedLogoId`; `regions.js:634` includes `logo_id: getSelectedLogoId() || null`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `logos.js` thumbnail grid | catalog fetched via `api.listLogos()` | `GET /logos` → `logo.list_logos()` → `manifest.json` | Yes — real manifest+PNG on disk; graceful empty for absent lib | FLOWING |
| `pipeline.py` logo placement | `logo_bytes` from `logo.resolve(job_spec.logo_id)` | Manifest dict lookup → `path.read_bytes()` | Yes — validated PNG bytes from `logos/` directory | FLOWING |
| `regions.js` `applyRemoval` | `logo_id` from `getSelectedLogoId()` | Client selection state in `logos.js` | Yes — real selection or null | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `.venv/Scripts/python.exe -m pytest -q` | 163 passed | PASS |
| LOGO-02 bbox+aspect test | `pytest tests/test_logo.py::test_inserted_logo_bbox_within_rect_and_aspect_preserved` | PASSED | PASS |
| Survives redaction test | `pytest tests/test_logo.py::test_logo_survives_redaction` | PASSED | PASS |
| Single xref dedup test | `pytest tests/test_logo.py::test_global_logo_single_xref` | PASSED | PASS |
| Fitz seam confinement | `pytest tests/test_redact.py::test_fitz_import_confined_to_engine_seam` | PASSED | PASS |
| No-logo = pure removal | `pytest tests/test_process_api.py::test_process_without_logo_is_pure_removal` | PASSED | PASS |
| SHA-256 unchanged across remove+insert | `pytest tests/test_process_api.py::test_original_unchanged_across_remove_insert` | PASSED | PASS |
| logos.js XSS + sole seam guard | Python static check (no innerHTML, no fetch(), uses api.listLogos/api.logoImageURL) | OK | PASS |
| regions.js logo_id payload + relabel | Node.js static check | logo_id payload + relabel present | PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` files found. Phase is covered by pytest.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| LOGO-01 | 03-01 | 系統提供固定的我司商標庫,使用者可瀏覽並挑選要使用的 logo | SATISFIED | `logos/manifest.json`, `GET /logos`, `logos.js` picker. `test_list_logos` PASSES. |
| LOGO-02 | 03-02 | 使用者可將選定的 logo 放到框選位置,並維持長寬比縮放貼合 | SATISFIED | `place_logo(keep_proportion=True)`. LOGO-02 bbox+aspect test PASSES. |

Both Phase 3 requirements confirmed as satisfied. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

Scan result: No `TBD`/`FIXME`/`XXX` markers, no unreferenced debt markers, no stub patterns, no hardcoded empty returns in the Phase 3 implementation files. The four review warnings (WR-01..WR-04) were addressed in commits `f955de0`, `6ca0be1`, `c4031b0`, `e5c137b`.

### Context Decision Verification (D-01..D-06)

| Decision | Status | Evidence |
|----------|--------|----------|
| D-01: global single logo, no-logo = pure removal | HONORED | `JobSpec.logo_id` optional; `process_job` resolves once; `test_process_without_logo_is_pure_removal` PASSES. |
| D-02: contain + center (keep_proportion) | HONORED | `place_logo` calls `insert_image(keep_proportion=True)`; `keep_proportion=False` absent. |
| D-03: PNG with alpha, no SVG | HONORED | `_validate_png` enforces `img.format == "PNG"`; `test_non_png_asset_rejected` PASSES. |
| D-04: `logos/` + `manifest.json`, admin-placed | HONORED | Assets exist; no upload UI; `list_logos` graceful for empty dir. |
| D-05: side-panel thumbnail grid, dual-theme tokens | HONORED | `logos.js` grid uses existing tokens; `--logo-thumb-size`/`--logo-grid-gap` the only two new token vars. |
| D-06: result preview includes logo, zero new rendering | HONORED | `refreshResultLabel()` conditionally sets `#view-result` text; no new render endpoint. |

### Human Verification Required

**1. Side-panel thumbnail grid visual rendering (both themes)**
**Test:** Load a PDF, observe the 我司商標 section in the side panel. Switch light/dark themes.
**Expected:** Thumbnail grid renders with neutral backing behind transparent PNG; both themes correct.
**Why human:** CSS theme rendering cannot be verified programmatically.

**2. Selected-logo accent ring**
**Test:** Click the placeholder thumbnail, observe border. Click 不置入商標 and observe border disappears.
**Expected:** `.logo-thumb.is-selected` shows `border: 2px solid var(--color-accent)` ring; cleared on deselect.
**Why human:** CSS visual state requires browser.

**3. Conditional after-label (移除+置入結果 / 移除結果)**
**Test:** Draw a region, select logo, apply → check after-segment label. Deselect logo, re-apply → check label reverts.
**Expected:** Label reads 移除+置入結果 with logo selected; 移除結果 without.
**Why human:** DOM textContent change requires browser interaction.

**4. Logo visible in before/after preview and downloaded PDF**
**Test:** Select placeholder logo, draw region over supplier logo, apply. In the after-image, logo appears centered in the region. Download and open PDF.
**Expected:** After-image shows placeholder logo in correct position; downloaded PDF contains logo; supplier content is gone.
**Why human:** Visual placement correctness requires human inspection.

**5. Stale-result trigger on logo change**
**Test:** Apply once (result fresh). Change logo selection. Observe the action group.
**Expected:** Action group shows 重新套用; status notice reads 所選商標已變更,請重新套用以更新結果.
**Why human:** DOM/UI state machine behavior requires browser.

**6. Cache-busting on re-apply (WR-01)**
**Test:** Apply twice. Open DevTools Network tab. Confirm second apply fetches the after-image with a different `?v=` query param and the image visually updates.
**Expected:** `?v=1` on first apply, `?v=2` on second apply; after-image refreshes.
**Why human:** Browser cache behavior requires manual DevTools inspection.

### Gaps Summary

No automated gaps found. All 9 must-have truths verified. All 163 tests pass. The six human-verification items are standard UI behavioral checks that cannot be confirmed programmatically — they are quality checks on the Phase 3 UI slice (visual theme rendering, selection state, conditional label, logo placement preview, stale machine, cache busting). Status is `human_needed` pending those checks.

---

_Verified: 2026-05-22_
_Verifier: Claude (gsd-verifier)_
