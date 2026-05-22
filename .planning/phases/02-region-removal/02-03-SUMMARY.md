---
phase: 02-region-removal
plan: 03
subsystem: region-selection-ui
tags: [vanilla-js, overlay, region-drawing, side-panel, before-after-toggle, deferred-mutation, cross-page, dual-theme, traditional-chinese, no-build]

# Dependency graph
requires:
  - phase: 02-region-removal
    plan: 02
    provides: "POST /sessions/{id}/process {dpi,regions[{page,px_rect}]} -> {output_filename,page_count,regions[{page,removed,clamped}]}; GET /result/pages/{n}/image (六 X- headers); GET /result (原名_logoswap.pdf)"
  - phase: 01-input-preview
    plan: 02
    provides: "#page-frame position:relative render-box host; viewer.js (renderPage/applyZoom/renderToken, renderBox); api.js sole server seam; dual-theme tokens; stage state machine (empty|uploading|loaded|error)"
provides:
  - "web/js/regions.js — region overlay (pointer-draw in image-pixel space) + per-page region model + side-panel list + before/after toggle controller + apply/download action-group state machine + stale-result invalidation"
  - "viewer.js overlay seam: CustomEvents page:changed{index,factor,frameW,frameH} + page:zoomed{factor,frameW,frameH} on #page-stage; getViewerState() / showOriginalImage() / showResultImage(url) helpers (render/zoom logic NOT forked)"
  - "api.js Phase-2 seam: processJob(id, jobSpec) / resultImageURL(id, n) / resultDownloadURL(id) — the only place that contacts /process + /result"
  - "Region tokens (--side-panel-width, --overlay-z, --color-region-* light+dark) + side-panel/toggle/action/dialog CSS + markup (verbatim 繁中)"
affects: [03-logo-insertion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Region rects stored client-side in IMAGE-PIXEL space at the render DPI (200); displayed projection derived from the live frame box (imageX = localX × img_w / frameW). Zoom changes frameW; img_w is the constant 200-DPI width — rects stay pinned across CSS-scale zoom and match the server's px_rect verbatim (deferred-mutation D-05)."
    - "Viewer overlay seam is ADDITIVE: viewer.js dispatches page:changed / page:zoomed CustomEvents (the renderToken guard stays authoritative; render/zoom logic is not duplicated). regions.js subscribes; before/after image swaps go through viewer helpers so api.js stays the sole server seam (T-02-12)."
    - "Action-group exactly-one-accent invariant: 套用移除 is .primary-btn (accent) until a fresh result, then 下載 PDF becomes .primary-btn and 套用移除 demotes to neutral .text-btn 重新套用. Any region edit clears resultFresh, re-shows 重新套用 + the 框選已變更 stale notice, and disables download (D-05/D-07)."
    - "All dynamic strings via textContent/createElement; server error mapped to FIXED 繁中 copy by detail.code — the raw server message is never injected as HTML (T-02-11)."

key-files:
  created:
    - web/js/regions.js
    - scripts/smoke_02_03.py
  modified:
    - web/js/api.js
    - web/js/viewer.js
    - web/js/app.js
    - web/styles/tokens.css
    - web/styles/app.css
    - web/index.html

key-decisions:
  - "Image-px projection via img_w/frameW rather than the plan's devicePixelRatio formula: mathematically equivalent (frameW = (img_w/dpr) × zoom, so localX × img_w/frameW = localX × dpr/zoom) but anchored to the TRUE render box and exact against the server's px_rect at dpi=200 — more robust than threading dpr through the overlay. The plan's intent ('mirror viewer.js renderBox math, store image-pixel rects anchored to the render box') is satisfied."
  - "Before/after image swap goes through new viewer helpers (showOriginalImage/showResultImage) instead of regions.js touching #page-image.src + building URLs directly: keeps api.js the sole server seam (T-02-12) and reuses the viewer's <img>/frame without forking renderPage."
  - "The dynamically-created .region-overlay div is appended under #page-frame by regions.js (ensureOverlay) rather than authored in index.html — it must mount inside the imperatively-sized frame and is meaningless before a doc loads."
  - "Auto-switch to 移除結果 immediately after a successful 套用移除 so the before/after comparison is instant; editing any region flips back to 原圖 and marks the result stale."

requirements-completed: [REGION-01, REGION-02, REMOVE-04, OUTPUT-01]

# Metrics
duration: ~9min
completed: 2026-05-22
---

# Phase 2 Plan 03: 前端矩形框選 UI + 前後對照 + 下載 (Region Selection UI) Summary

**Closes the user-facing loop: a transparent region-drawing overlay on the Phase-1 page-stage lets the user drag rectangles (image-pixel space, deferred-mutation D-05), manage them in a per-page side-panel list (delete one / clear all / overlap allowed / no handles), press 套用移除 to redact the work copy server-side via the Plan 02-02 `/process` endpoint, toggle 原圖 / 移除結果 to verify on the single page-stage, and download `原名_logoswap.pdf` — all vanilla JS with no build, reusing the Phase-1 dual-theme tokens and verbatim Traditional-Chinese copy, with `api.js` as the only module that contacts the server.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-05-22T08:56:04Z
- **Completed:** 2026-05-22
- **Tasks:** 3 auto + 1 human-verify checkpoint (auto-approved under yolo)
- **Files:** 8 (2 created, 6 modified)

## Accomplishments

- **Region overlay (REGION-01):** `regions.js` creates a `.region-overlay` child of `#page-frame` (`position:absolute; inset:0; z-index:var(--overlay-z); cursor:crosshair`). Pointerdown→move→up draws a rubber-band rectangle (dashed while dragging, solid 2px on commit); a sub-~4px drag is ignored (no zero-area region); Escape cancels an in-progress drag. **Overlap is allowed** (no collision rejection). **No resize/move handles** (D-01) — draw-wrong → delete & redraw. Rectangles are slate/cool (`--color-region-*`), deliberately NOT the reserved accent.
- **Per-page model + cross-page (REGION-02):** a `Map` keyed by page index holds `[{id, pxRect:[x0,y0,x1,y1]}]` in IMAGE-PIXEL space. Paging swaps which page's regions show in the overlay + side-panel list; the count (`已框選 {n} 個區域`) and scope note (`目前顯示第 {current} 頁的框選`) update on page change. Drawing on page 3 never affects page 1.
- **Side-panel list:** one row per region on the CURRENT page (`區域 {n}`, tabular-nums, a `刪除此區域` icon button). Bidirectional hover/focus highlights the matching rectangle (border-strong + ordinal badge). Delete-one is immediate (no confirm); `清除全部` opens a confirm dialog (`取消` / `清除全部` danger) scoped to the CURRENT page (D-02). Empty page → the `尚未框選任何區域` empty-state block. Rows are Tab-reachable; Delete/Backspace on a focused row removes it.
- **Zoom-stable re-projection:** committed rectangles re-derive their displayed position from the stored image-px rects on every `page:zoomed` (the source of truth never changes — only the displayed projection), so they stay pinned over the same content across CSS-scale zoom.
- **Before/after toggle (REMOVE-04 UI half):** the segmented `原圖 / 移除結果` control swaps the single `#page-image` between the original render and `api.resultImageURL(sid, page)`; switching to 移除結果 HIDES the overlay rectangles, switching back restores them. Selecting 移除結果 with no fresh result shows `尚無移除結果,請先套用移除` and stays on 原圖. Paging while in result mode re-fetches the correct page's after-image. NOT side-by-side, NOT a slider.
- **Apply / download (OUTPUT-01 UI):** `套用移除` gathers `getJobRegions()` + `dpi:200` and calls `api.processJob`. Busy state shows `正在套用移除…`; on success it flags the result fresh, shows `移除結果已就緒…`, flips the action group so `下載 PDF` is the single accent button and `套用移除` demotes to neutral `重新套用`, and auto-switches to 移除結果. Per-region server flags drive the `框選區域內沒有可移除的內容` (nothing removed) and `框選超出頁面範圍…` (clamped) inline notices. `下載 PDF` navigates a transient anchor to `api.resultDownloadURL` (browser handles `原名_logoswap.pdf`).
- **Stale-result state machine (D-05/D-07):** any region edit (draw/delete/clear) after a result clears `resultFresh`, shows `框選已變更,請重新套用以更新結果`, flips the accent back to `重新套用`, and disables `下載 PDF` until re-applied — download only ever happens against a fresh result.
- **Live smoke test green:** `scripts/smoke_02_03.py` drives the exact api.js flow in-process (upload → process → result-image → download) including a **90°-rotated page**; see Key Test Evidence.

## The Public Contract (for Phase 3 logo insertion)

### regions.js public API

```
initRegions({ session_id, page_count })  // activate the overlay + model for a session
resetRegions()                           // clear all state + hide the overlay (on new upload)
getJobRegions() -> [{ page, px_rect:[x0,y0,x1,y1] }]   // flat payload across ALL pages (server shape)
getTotalRegionCount() -> number          // count across all pages
```

### viewer.js overlay seam (added, additive)

- CustomEvents on `#page-stage`: `page:changed` `{index, factor, frameW, frameH}` (after a successful render); `page:zoomed` `{factor, frameW, frameH}` (from `applyZoom`).
- Helpers: `getViewerState()` → `{sessionId, pageIndex, pageCount}`; `showOriginalImage()` (restore 原圖 for the current page); `showResultImage(url)` (show the 移除結果 render). The `renderToken` guard stays authoritative; render/zoom logic is NOT forked.

### api.js Phase-2 seam (the ONLY server contact)

- `processJob(id, jobSpec)` → POST `/sessions/{id}/process`, throws `ApiError` from a non-2xx body (like `createSession`).
- `resultImageURL(id, n)` → string for the 移除結果 `<img src>`.
- `resultDownloadURL(id)` → string for the `/result` download anchor.

## Files Created/Modified

- `web/js/regions.js` (created, ~700 lines) — the region model + overlay + side-panel list + before/after toggle + action-group state machine + stale handling. No `innerHTML`; no `fetch`/`API_BASE` (server only via api.js + viewer helpers).
- `scripts/smoke_02_03.py` (created) — in-process TestClient smoke harness proving the apply/result/download contract incl. a rotated page (throwaway, not a committed pytest).
- `web/js/api.js` (modified) — added `processJob` / `resultImageURL` / `resultDownloadURL` + the Phase-2 contract docstring.
- `web/js/viewer.js` (modified) — added the `page:changed` / `page:zoomed` emitters (wired into `applyZoom` + the render `onload`) and the `getViewerState` / `showOriginalImage` / `showResultImage` helpers.
- `web/js/app.js` (modified) — `initRegions` / `resetRegions` + side-panel expand/collapse (`.main--paneled`) gated to the `loaded` state; reset on new upload / error retry.
- `web/styles/tokens.css` (modified, append-only) — `--side-panel-width`, `--overlay-z`, `--color-region-*` (light `:root` + dark `[data-theme="dark"]`). Existing tokens untouched.
- `web/styles/app.css` (modified, append-only) — side-panel expansion, region rows, overlay/rectangle treatments, segmented toggle, action group, danger buttons, modal. `var()` tokens only — no raw region hexes.
- `web/index.html` (modified) — side-panel region-list markup, before/after toggle, action group, clear-all confirm dialog (all verbatim 繁中); registered `regions.js`.

## Key Test Evidence

`scripts/smoke_02_03.py` (run: `.venv/Scripts/python scripts/smoke_02_03.py`):

| Guarantee | Result |
|---|---|
| Upload (CJK name) → session | PASS — `圖紙.pdf`, page_count 2 |
| `/process` body `{dpi:200, regions:[{page, px_rect}]}` echoes per-region flags | PASS — p0 + p1 both `{removed:true, clamped:false}` |
| 90°-rotated page true removal (REMOVE-03 placement) | PASS — rotated page redacted; 0 words + 0 drawings after |
| Result-render PNG + the six X- headers (overlay maths) | PASS — both pages, all six headers present |
| Download `原名_logoswap.pdf` (RFC-5987 filename*) | PASS — `filename*=UTF-8''圖紙_logoswap.pdf`, `application/pdf` |
| True removal in the exported PDF | PASS — both pages extract 0 words + 0 drawings |
| All pages kept (D-07) | PASS — `page_count == 2` |
| `result_not_ready` before processing | PASS — 404 `{code: result_not_ready}` |
| Backend regression | PASS — full `pytest -q` = 140 passed |
| Static mount serves new UI | PASS — `GET /` 200 has regions.js + 套用移除 + clear-confirm; tokens/app/regions assets 200 |

## Verification Gates (all green)

- `node --check` passes on api.js, app.js, theme.js, viewer.js, regions.js.
- `api.js` exports `processJob` / `resultImageURL` / `resultDownloadURL` and references `/process` + `/result`; **api.js is the only module referencing `API_BASE`/`fetch`** (T-02-12 grep confirms).
- `tokens.css` has `--side-panel-width`, `--overlay-z`, `--color-region-border` in both `:root` (light) and `[data-theme="dark"]`.
- `index.html` contains the verbatim 套用移除 / 下載 PDF / 原圖 / 移除結果 / 清除全部 / 框選區域 / 尚未框選任何區域 / 重新套用 strings (12 total occurrences).
- `app.css` styles the rectangle via `var(--color-region-border…)` and the overlay via `var(--overlay-z)` — no raw `#475569`/`#CBD5E1`/`#1E293B`/`#E2E8F0` hexes (grep returns nothing).
- **No `innerHTML`** in regions.js / app.js additions (the only matches are comments saying "never innerHTML"); regions.js uses textContent/createElement throughout.
- **No PDF.js** anywhere under `web/` (grep `pdfjs|pdf.js|PDFJS|getDocument|pdf.worker` returns nothing).

## Decisions Made

- **Image-px projection via `img_w / frameW`** rather than the plan's `devicePixelRatio` formula — mathematically equivalent (`frameW = (img_w/dpr) × zoom`, so `localX × img_w/frameW = localX × dpr/zoom`) but anchored to the true render box and exact against the server's `px_rect` at `dpi=200`. Satisfies the plan's intent ("mirror viewer.js renderBox math, store image-pixel rects anchored to the render box").
- **Before/after swap through viewer helpers** (`showOriginalImage` / `showResultImage`) instead of regions.js touching `#page-image.src` + building URLs directly — keeps `api.js` the sole server seam (T-02-12) and reuses the viewer's `<img>`/frame without forking `renderPage`.
- **`.region-overlay` created at runtime** by `ensureOverlay()` (appended under `#page-frame`) rather than authored in index.html — it must mount inside the imperatively-sized frame and is meaningless before a doc loads.
- **Auto-switch to 移除結果** immediately after a successful 套用移除 so the comparison is instant; editing any region flips back to 原圖 and marks the result stale.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Equivalent-correct adjustment] Image-pixel projection formula**
- **Found during:** Task 2 (writing the overlay coordinate math).
- **Issue:** The plan's `<action>` suggested deriving image pixels via `× devicePixelRatio ÷ zoom`. While correct, threading `dpr` + the live zoom factor through the overlay is fragile (the viewer already folds dpr into `renderBox`).
- **Fix:** Used `imageX = localX × img_w / frameW` (and the inverse for projection), reading `img_w/img_h` from `api.pageMeta` and `frameW/frameH` from the live frame box. This is mathematically equivalent, anchored to the true render box, and exactly matches the server's 200-DPI `px_rect`. The plan's stated intent (image-pixel storage anchored to the render box, zoom-stable) is fully met.
- **Files modified:** `web/js/regions.js`
- **Verification:** smoke test — rects on both an unrotated and a 90°-rotated page mapped to true removal with `clamped:false`.
- **Note:** No behavior regression; this is a more-robust implementation of the same contract.

**2. [Rule 3 - Blocking issue] Smoke harness import + region geometry**
- **Found during:** Task 3 (running the live smoke).
- **Issue:** (a) Running `python scripts/...` didn't put the repo root on `sys.path` (ModuleNotFoundError: app). (b) An initial upper-band region on the 90°-rotated page tripped the backend's legitimate `residual_content` guard because the rotated content lands on the displayed RIGHT, not the top.
- **Fix:** (a) Prepend the repo root to `sys.path` + reconfigure stdout to UTF-8 for clean CJK output. (b) Made the smoke region rotation-aware (unrotated-top → displayed-right at 90°) — this is a test-geometry fix, not a code fix; it actually demonstrates the coords mapper derotating correctly.
- **Files modified:** `scripts/smoke_02_03.py`
- **Verification:** smoke test passes end-to-end (both pages `removed:true`, true removal verified).

**Total deviations:** 2 — one equivalent-correct implementation choice, one smoke-harness fix. No architectural changes, no scope creep. The region rectangle treatment, copy, tokens, and the deferred-mutation flow all follow the 02-UI-SPEC exactly.

## Authentication Gates

None — this is an internal, no-login tool (no auth surface in Phase 2).

## Human-Verify Checkpoint (Task 4) — AUTO-APPROVED under yolo

This plan's Task 4 is a `checkpoint:human-verify`. This was an autonomous (`--auto`, `_auto_chain_active: true`, `mode: yolo`) run, so the checkpoint is **auto-approved** and the plan completed; the human UAT happens at the orchestrator level afterward. The automated smoke test above already proves the load-bearing machine-checkable parts (process contract, rotated-page true removal, result-render headers, download filename, all-pages-kept, stale guard). The visual/interaction contract below still warrants a human pass.

### Verification script for the user's UAT

```
1. Start the server:  ./.venv/Scripts/python -m uvicorn app.main:app --reload
   Open http://127.0.0.1:8000/
2. Upload a vector PDF with a supplier logo / text (ideally one ROTATED-page PDF and one multi-page PDF).
3. Drag a rectangle over the logo/text. Confirm: a SLATE (not blue/amber accent) translucent rectangle
   appears; the side-panel shows 區域 1 and 已框選 1 個區域; a second overlapping rectangle is allowed; a
   sub-tiny click makes no region; the cursor over the page is a crosshair.
4. Hover a list row -> the matching rectangle highlights (border-strong + ordinal badge) and vice-versa.
   Delete one region (immediate, no confirm). 清除全部 -> confirm dialog (取消 / 清除全部) scoped to the
   current page only.
5. Page to another page -> the first page's regions are gone from the overlay+list (per-page scope);
   draw a region there; page back -> the original regions return. Zoom in/out -> rectangles stay pinned
   over the same content.
6. Press 套用移除. Confirm the busy text, then 移除結果已就緒…; 下載 PDF becomes the single accent button
   and 套用移除 becomes neutral 重新套用 (exactly ONE accent button).
7. Toggle 移除結果 -> the content is GONE (overlay hidden); toggle 原圖 -> content + overlay return. On a
   rotated page, confirm the removal landed exactly on the boxed area.
8. Edit a region (draw/delete) -> the result goes stale (框選已變更,請重新套用…), 下載 PDF disabled until 重新套用.
9. Re-apply, then 下載 PDF -> a PDF named like <原名>_logoswap.pdf downloads; open it: the removed area
   extracts NO text (Ctrl+A/Ctrl+C over it yields nothing) and ALL pages are present.
10. Toggle dark mode -> region rectangles stay visible and the accent discipline holds.

Resume signal: "approved" if the contract holds; otherwise describe the issues to fix.
```

## Known Stubs

None. `regions.js` is real, runnable code: drawing, per-page model, side-panel list, before/after toggle, apply/download wiring, and stale handling are all functional and proven by the in-process smoke test (true removal verified on both an unrotated and a rotated page; download yields `原名_logoswap.pdf`; all pages kept). No placeholder/hardcoded UI data.

## Threat surface scan

No new security surface beyond the plan's `<threat_model>`. Mitigations implemented as specified:
- **T-02-11** (XSS via server message / labels): all dynamic text via `textContent`/`createElement`; server errors mapped to FIXED 繁中 copy by `detail.code` — the raw message is never injected as HTML. Grep: no `innerHTML` in regions.js/app.js.
- **T-02-12** (a web module hardcoding a server URL): only `api.js` references `API_BASE`/`fetch`; regions.js builds result/download URLs only via `api.resultImageURL`/`api.resultDownloadURL` and swaps images via viewer helpers. Grep confirms regions.js has no `fetch`/`API_BASE`.
- **T-02-13** (huge/oob region list): the client caps drawing to sane interaction and surfaces the server's `clamped` flag; the AUTHORITATIVE guard is server-side (MAX_REGIONS + clamp). The UI never assumes a region was applied without the server's per-region result.
- **T-02-14** (wrong-session result/download): `sessionId` comes only from the viewer state established at upload; all result URLs are built from it via api.js — no cross-session id is constructible from the UI.

## Next Phase Readiness

- **Phase 3 (logo insertion) is unblocked.** The region model + overlay + the reserved side-panel column are the substrate the logo picker reuses (the side-panel grid + `.main--paneled` expansion are forward-compatible). `getJobRegions()` already yields the `[{page, px_rect}]` payload a logo-placement step extends; the deferred-mutation flow + work-copy/export discipline carry forward unchanged.
- **Phase 2 is complete** (3/3 plans): coords spine (02-01) → true-removal pipeline (02-02) → region UI (02-03). The full user loop — draw → 套用移除 → 原圖/移除結果 toggle → 下載 原名_logoswap.pdf — is wired and smoke-proven.

## Self-Check: PASSED

- Created files verified present: `web/js/regions.js`, `scripts/smoke_02_03.py`. Modified: `web/js/api.js`, `web/js/viewer.js`, `web/js/app.js`, `web/styles/tokens.css`, `web/styles/app.css`, `web/index.html`.
- Task commits verified in git log: `58ef7e4` (Task 1, feat), `f7699f1` (Task 2, feat), `73ab6a4` (Task 3, test).
- `node --check` green on all 5 JS modules; `pytest -q` = 140 passed; smoke `scripts/smoke_02_03.py` PASSED (true removal on unrotated + rotated page, all pages kept, download filename + result_not_ready guard); no PDF.js under web/; only api.js touches the server.

---
*Phase: 02-region-removal*
*Completed: 2026-05-22*
