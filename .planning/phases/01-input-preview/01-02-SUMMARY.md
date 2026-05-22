---
phase: 01-input-preview
plan: 02
subsystem: frontend
tags: [vanilla-js, css-custom-properties, dual-theme, dark-mode, upload, preview, viewer, zoom, walking-skeleton, no-build]

# Dependency graph
requires:
  - phase: 01-input-preview
    plan: 01
    provides: "FastAPI backend — POST /sessions, GET /sessions/{id}, GET .../pages/{n}/image (PNG @200 DPI + six X- coordinate headers), GET .../pages/{n}/meta, /health; guarded web/ StaticFiles mount at /"
provides:
  - "Vanilla HTML/CSS/JS preview UI served at / by FastAPI (no build step)"
  - "Dual-theme design-token set (web/styles/tokens.css): light :root + [data-theme=\"dark\"] overrides — blue #2563EB / amber #F59E0B accents — reused by Phases 2-5"
  - "API seam (web/js/api.js): the ONLY module contacting the server (window.PDFTOOL_API_BASE override) — embedding seam for the future approval-site host"
  - "Theme controller (web/js/theme.js): prefers-color-scheme init + localStorage-persisted explicit choice, no flash of wrong theme, pure front-end"
  - "Server-rendered page viewer (web/js/viewer.js): multi-page nav + CSS-scale zoom over a position:relative page stage sized to the true render box (overlay-ready for Phase 2)"
  - "Four-state upload stage machine (web/js/app.js): empty/uploading/loaded/error with verbatim Traditional-Chinese copy"
affects: [02-coordinate-mapper, 02-region-selection, 03-logo-picker]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "API-first seam: web/js/api.js is the sole server-contacting module (window.PDFTOOL_API_BASE override); no other JS file embeds a server URL"
    - "Dual-theme via CSS custom properties: light tokens on :root, [data-theme=\"dark\"] overrides only color values; all component CSS consumes var() tokens so one attribute flip reskins the UI"
    - "Server-authoritative render / client display: the browser only ever loads a server-rendered PNG via <img>; no client-side PDF parser (PDF.js forbidden)"
    - "CSS-scale zoom (D-02): the fetched PNG is scaled via CSS width/height; the image is never re-requested at a different dpi on zoom"
    - "Page stage as overlay host: position:relative wrapper sized to the true render box (img_w/img_h) so a Phase-2 absolute overlay drops in pixel-aligned, not letterboxed"
    - "XSS-safe dynamic text: filenames, page numbers, and server messages are written via textContent / createElement, never innerHTML"
    - "Enum-guarded persisted theme: localStorage theme value constrained to light|dark, applied via setAttribute, never reflected as HTML"

key-files:
  created:
    - web/index.html
    - web/styles/tokens.css
    - web/styles/app.css
    - web/js/api.js
    - web/js/theme.js
    - web/js/viewer.js
    - web/js/app.js
  modified: []

key-decisions:
  - "Light theme = absence of [data-theme]; only dark sets the attribute, so the :root light tokens are the natural default and a tampered/garbage stored value safely yields light"
  - "Render box computed in CSS px as img_w / devicePixelRatio so 100% zoom shows the page at its natural on-screen size; zoom factor scales that box (no re-render)"
  - "Fit-to-width is a distinct zoom MODE (derives its factor from stage width) layered over the discrete 50–200% steps; the +/- step buttons remain usable from it"
  - "An inline (non-module) theme-resolve script runs in <head> before first paint to prevent a flash of the wrong theme; theme.js then owns the toggle + persistence"

# Metrics
duration: ~16min
completed: 2026-05-22
---

# Phase 1 Plan 02: 前端預覽介面 (Vanilla-JS Preview Frontend) Summary

**A no-build vanilla HTML/CSS/JS preview UI served at `/` by FastAPI: uploads one PDF, displays each server-rendered PNG (200 DPI) inside a position:relative page stage sized to the true render box, with multi-page navigation, CSS-scale zoom (no re-render on zoom), and a light/dark theme toggle (blue #2563EB / amber #F59E0B) persisted to localStorage — completing the Phase-1 Walking-Skeleton end-to-end slice (browser → upload → server render → browser display). Verified live against the running backend.**

## Performance

- **Duration:** ~16 min
- **Started:** 2026-05-22T06:37:00Z (approx)
- **Completed:** 2026-05-22T06:53:34Z
- **Tasks:** 3 auto + 1 human-verify checkpoint (auto-approved under yolo/auto-chain)
- **Files created:** 7 (1 HTML, 2 CSS, 4 JS); 0 modified

## Accomplishments

- **End-to-end Walking Skeleton verified live.** Started `uvicorn app.main:app` and confirmed: `GET /` → 200 serving the zh-Hant UI; all 6 static assets (tokens.css, app.css, api.js, theme.js, viewer.js, app.js) → 200; `POST /sessions` with a 3-page PDF → 201 `{session_id, page_count:3, filename}`; `GET .../pages/0/image` → `image/png`, `x-render-dpi: 200`, `x-image-width-px: 1700` (= 612pt × 200/72, matching viewer.js's render-box math); `GET .../pages/0/meta` → `{img_w:1700, img_h:2200, dpi:200}`; error path (upload a non-PDF) → `HTTP 415 {detail:{code:"unsupported_type"}}`, which app.js maps to the verbatim copy.
- **Dual-theme token system established (D-06/D-07)** for reuse by Phases 2–5: light tokens on `:root`, a `[data-theme="dark"]` block overriding only color values (surface `#0F172A`, panel `#1E293B`, accent amber `#F59E0B`, accent-hover `#D97706`, danger/text/border darks). All component CSS in app.css consumes `var(--color-*)` tokens — zero raw theme hexes — so a single attribute flip reskins the whole UI.
- **Accent discipline enforced (60/30/10):** `--color-accent` appears ONLY on the primary CTA (`選擇 PDF 檔案`) and the active page-number indicator (`.page-current`), in both themes. Prev/next/zoom/jump/theme-toggle/secondary buttons are neutral surface + border; the accent hue is reused only as the focus-ring affordance.
- **Theme controller (theme.js)** resolves the initial theme from `prefers-color-scheme`, persists only an EXPLICIT toggle choice to `localStorage`, follows the OS while no choice is stored, and reflects state via `aria-pressed` + CSS-driven sun/moon icon swap. An inline head script applies the resolved theme before first paint (no flash). Pure front-end — no `fetch`, no api.js import, no server URL.
- **API seam (api.js)** is the sole server-contacting module (`window.PDFTOOL_API_BASE` override → empty string = same-origin). `createSession` throws an `ApiError` carrying `detail.code` + `detail.message` so the UI surfaces the `{limit}` value verbatim; `pageImageURL` is the only image-URL builder and is called once per page with no dpi argument.
- **Viewer (viewer.js)** displays the server PNG via `<img>` inside the `position:relative` `.page-frame` (the Phase-2 overlay host), sizes the frame to the true render box from `/meta` (with a natural-size fallback if `/meta` fails), supports prev/next (disabled at boundaries) + jump-to-page (clamped 1..total) + discrete zoom (50–200%) + fit-to-width, and keyboard Left/Right (page) and +/− (zoom) when the stage is focused. Zoom CSS-scales the already-fetched PNG — it never re-requests the image at a different dpi (D-02).
- **Four-state stage machine (app.js):** exactly one of empty / uploading / loaded / error is visible; server `detail.code` is mapped to the exact Traditional-Chinese SPEC copy under the generic heading `無法開啟此檔案` with a `重試` action; drag-over visual state, `更換檔案` action, and the soft-confirm shown ONLY when a file is already loaded.

## Task Commits

Each task committed atomically:

1. **Task 1: App shell, dual-theme tokens, upload flow + state machine** — `70394ce` (feat) — web/index.html, web/styles/tokens.css, web/styles/app.css, web/js/api.js, web/js/app.js
2. **Task 2: Light/dark theme toggle (prefers-color-scheme + localStorage)** — `abe2d64` (feat) — web/js/theme.js
3. **Task 3: Server-rendered page viewer (display, nav, CSS-scale zoom)** — `6afa2ed` (feat) — web/js/viewer.js
4. **Task 4: Human-verify checkpoint** — auto-approved under yolo / `_auto_chain_active` (verification environment confirmed live); no commit.

**Plan metadata:** this SUMMARY + STATE/ROADMAP — committed separately as `docs(01-02)`.

_Note: index.html and app.css were authored in Task 1 already containing the `#theme-toggle` markup, sun/moon icons, and `.page-current`/page-stage styling that Tasks 2 and 3 activate, so those tasks needed no further edits to those files — the structural shell anticipated the wiring. The viewer.js stub that app.js imports was delivered whole in Task 3 (node --check parses each file independently, so app.js passed its Task-1 check before viewer.js existed)._

## Files Created/Modified

- `web/index.html` (279 lines) — `lang="zh-Hant"` app shell: CSS-grid toolbar row + main `[preview stage 1fr | reserved side-panel 0]`; inline pre-paint theme-resolve script; accent CTA `選擇 PDF 檔案`, dropzone (doubles as empty state) with `accept="application/pdf,.pdf"`; page-nav + zoom clusters (hidden/disabled until load); `#theme-toggle` (always usable, aria-label `切換深淺色模式`, sun/moon SVGs); `#page-stage` (position relative) hosting the four state blocks and the `.page-frame`>`<img>`; loads api/theme/viewer/app as ES modules.
- `web/styles/tokens.css` (93 lines) — spacing (xs–3xl), 40px control hit target, CJK-aware `--font-sans`, 4 font sizes / 2 weights, radii + sheet shadow; LIGHT color tokens on `:root`; `[data-theme="dark"]` overriding color tokens with the dark values; focus-ring utility.
- `web/styles/app.css` (438 lines) — all components styled via `var()` tokens only (no raw theme hexes): app-shell grid, toolbar, primary/icon/text buttons, theme-toggle icon-state CSS, page indicator (tabular-nums, `.page-current` = accent), jump input, zoom level, page stage (position relative) + state machine, dropzone (idle/drag-over), neutral spinner (accent stroke as motion), page-frame + page-loader overlay, inline error block, single ≤720px breakpoint.
- `web/js/api.js` (114 lines) — sole server seam: `API_BASE` from `window.PDFTOOL_API_BASE`; `ApiError` (code + serverMessage + status); `createSession`, `getSession`, `pageImageURL` (optional dpi, omitted by callers), `pageMeta`.
- `web/js/theme.js` (113 lines) — `resolveInitialTheme`, `applyTheme` (setAttribute/removeAttribute), `toggleTheme` (flip + persist), `init` (wire toggle + follow-OS-while-no-choice); enum-guards the stored value; no network calls.
- `web/js/viewer.js` (270 lines) — `initViewer({session_id, page_count})` / `resetViewer`; render-box from `/meta` (CSS px = img_w/devicePixelRatio); prev/next/jump nav with boundary guards + 1..total clamp; discrete zoom + fit-to-width that CSS-scale the fetched PNG; single-page loader; img onerror → page-render copy; keyboard nav/zoom.
- `web/js/app.js` (199 lines) — four-state stage machine; server-code→verbatim-Chinese error mapping with `{limit}` extraction; drag-and-drop with drag-over state; `更換檔案` + soft-confirm gating; all dynamic text via textContent.

## Decisions Made

- **Light = no attribute, dark = `[data-theme="dark"]`.** Making light the natural `:root` default (rather than an explicit `data-theme="light"`) means a tampered or garbage localStorage value safely resolves to light, and the pre-paint inline script only ever needs to *add* the dark attribute — simplest no-flash path.
- **Render box measured in CSS pixels (`img_w / devicePixelRatio`).** The backend rasterizes at 200 DPI, so a Letter page is 1700 device px wide; dividing by DPR makes 100% zoom render at the page's natural on-screen size, and the zoom factor scales that box. This keeps displayed pixels attached to the true render box (coordinate-fidelity carry-forward) while honoring D-02 (no re-render on zoom).
- **Fit-to-width as a separate mode.** Rather than snapping to the nearest discrete step, fit-to-width derives its factor from the live stage width (re-evaluated on render), giving an exact fit; the discrete +/- buttons stay usable and switch back to step mode on click.
- **Inline pre-paint theme script duplicated (minimally) in `<head>`.** The ~10-line enum-guarded reader runs synchronously before any styled element paints — a module script (deferred) cannot guarantee that. theme.js re-applies + syncs `aria-pressed` on load and owns all subsequent behavior, so the duplication is a deliberate no-flash technique, not divergent logic.

## Deviations from Plan

None — the plan executed exactly as written. All three auto tasks were implemented with real, runnable code; the human-verify checkpoint was auto-approved per the active yolo / `_auto_chain_active` configuration after the verification environment was confirmed working end-to-end against the live backend. No bugs, missing-critical-functionality, or blocking issues were encountered (Rules 1–4 not triggered). No architectural decisions arose.

## Authentication Gates

None — the tool is an internal LAN app with no auth (consistent with PROJECT.md and Plan 01-01). No login/token/secret steps were required at any point.

## Threat surface scan

No new security surface beyond the plan's `<threat_model>`. Mitigations implemented as specified:
- **T-01-11** (out-of-range page index): `viewer.jumpTo` clamps to 1..total before requesting; backend also 404s out-of-range (defense in depth).
- **T-01-12** (server-origin leak): all server contact funneled through `web/js/api.js` via `window.PDFTOOL_API_BASE`; grep confirms no other `web/js` file references it; theme.js makes no network calls.
- **T-01-13** (client-side PDF parser): recursive grep for `pdfjs`/`pdf.js`/`PDFJS`/`pdf.worker` under `web/` returns nothing; the browser only loads server-rendered PNGs.
- **T-01-14** (raw server error text in DOM): app.js maps `detail.code` to fixed Chinese copy and injects only a parsed numeric/limit token via textContent — no raw server message/stack as HTML.
- **T-01-15** (unescaped dynamic HTML): page numbers and all dynamic text set via `textContent` / `createElement` + `textContent`, never `innerHTML`.
- **T-01-16** (tampered theme value): theme.js enum-guards the localStorage value to `light`/`dark` (else falls back to prefers-color-scheme) and applies it via `setAttribute('data-theme', ...)` — never `innerHTML`.
- **T-01-17** (no client audit trail): `accept` — internal LAN tool, no auth/compliance in v1.

No `threat_flag` items found — the frontend introduces no network endpoint, auth path, file-access pattern, or schema beyond what the threat model already covers (it only consumes the existing backend endpoints).

## Known Stubs

None. The UI is fully wired to the live backend (verified end-to-end: upload → render → meta → navigate → error). The reserved side-panel column (`grid-template-columns: 1fr 0`) is intentionally collapsed/empty — it is a documented forward-compatibility seam for Phase 2 (region list) / Phase 3 (logo picker), not a data stub, and renders nothing in Phase 1 by design.

## Issues Encountered

- **`node --check` only parses single files** (does not resolve ES-module imports), so app.js passed its Task-1 syntax check before viewer.js existed; the full module graph was then validated at runtime by serving the page (all six assets returned 200 and the page rendered).
- **A transient `curl` `HTTP 000` on the first error-path upload** (a file-handle quirk with `@/tmp/bad.txt;type=...` on this shell) resolved on retry with a plain `-F "file=@/tmp/bad.txt"`, which correctly returned `415 unsupported_type`. Not a server or app defect.
- **Git LF→CRLF normalization warnings** on every staged file — benign Windows line-ending normalization (same as noted in Plan 01-01); no action needed.

## Next Phase Readiness

- **Phase 2 (框選與真正移除 + coordinate mapper) is unblocked on the UI side:** the page stage is a clean `position:relative` host whose `.page-frame` is sized to the true render box (`img_w/img_h` from `/meta`), so a transparent `position:absolute; inset:0` overlay `<canvas>`/`<div>` drops on top pixel-aligned with no layout change. The render metadata (`page_w_pt`, `page_h_pt`, `rotation`, `dpi`, `img_w`, `img_h`) the px↔pt mapper needs is already fetched per page in viewer.js and exposed by the backend headers + `/meta`.
- **The app shell reserves the side-panel column** (`grid-template-columns: 1fr 0`) so Phase 2's region list and Phase 3's logo picker expand it to a fixed width without restructuring the grid.
- **The dual-theme token set + API seam are project-wide foundations** later phases inherit for free: new components only need to use `var(--color-*)` tokens to be theme-correct, and all new server calls go through `web/js/api.js`.
- **No region/canvas/redaction/logo/download UI was built** (correctly deferred to Phases 2–4); no client-side PDF parser was introduced.

## Self-Check: PASSED

- All 7 claimed created files verified present on disk (web/index.html, web/styles/tokens.css, web/styles/app.css, web/js/api.js, web/js/theme.js, web/js/viewer.js, web/js/app.js).
- All 3 task commits verified in git log: `70394ce` (Task 1), `abe2d64` (Task 2), `6afa2ed` (Task 3).
- `node --check` passes on all four JS modules; recursive grep for PDF.js under web/ returns nothing; `PDFTOOL_API_BASE` appears only in api.js; tokens.css is dual-theme (`#F59E0B` + `#0F172A` under `[data-theme="dark"]`); app.css contains no raw light theme hexes. End-to-end live smoke test confirmed `/` + assets 200, upload→201, image→image/png@200DPI, meta→img_w 1700, error→415.

---
*Phase: 01-input-preview*
*Completed: 2026-05-22*
