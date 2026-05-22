/*
 * viewer.js — server-rendered page viewer: display, multi-page navigation, CSS-scale zoom.
 *
 * The browser only ever loads a server-rendered PNG (server-authoritative render; no client-side
 * PDF parser — SKELETON.md). We size the page frame to the TRUE render box (img_w x img_h from
 * api.pageMeta) so the displayed pixels stay attached to the server render box and are never
 * letterboxed/detached — a coordinate-fidelity carry-forward for Phase 2's overlay mapper.
 *
 * Zoom (D-02): discrete steps + fit-to-width CSS-SCALE the already-fetched PNG. The zoom handlers
 * only change CSS width on the <img> and the matching frame size; they NEVER re-request the image
 * at a different dpi (pageImageURL is called once per page, with no dpi argument => server default 200).
 */

import * as api from "./api.js";

const COPY = {
  pageLoading: "載入中…",
  pageRenderFailure: "此頁無法顯示。請重新整理或更換檔案。",
  // Long (accessible) form; the compact toolbar form is "{current} / {total}".
  indicatorLabel: (current, total) => `第 ${current} 頁,共 ${total} 頁`,
};

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]; // 50/75/100/125/150/200%

// ---- DOM refs ---------------------------------------------------------------------
const stage = document.getElementById("page-stage");
const pageFrame = document.getElementById("page-frame");
const pageImage = document.getElementById("page-image");
const pageLoader = document.getElementById("page-loader");

// ---- Overlay hook (Phase 2) --------------------------------------------------------
// regions.js subscribes to these signals to keep its overlay attached to the true render box.
// We dispatch CustomEvents on #page-stage (additive — the render/zoom logic is NOT forked):
//   "page:zoomed"  {factor, frameW, frameH} — emitted by applyZoom; reproject rects to the box.
//   "page:changed" {index, factor, frameW, frameH} — emitted after a successful render; swap the
//                  shown page's regions. (Fired from renderPage's onload so the frame is sized.)
// frameW/frameH are the displayed render-box pixels; regions.js maps image-px<->displayed-px from
// them and the per-page image dimensions it reads from api.pageMeta. Keep the renderToken guard
// authoritative — these events fire only for the winning (current) render.
function emitPageZoomed(factor) {
  stage.dispatchEvent(
    new CustomEvent("page:zoomed", {
      detail: { factor, frameW: pageFrame.clientWidth, frameH: pageFrame.clientHeight },
    })
  );
}

function emitPageChanged(index, factor) {
  stage.dispatchEvent(
    new CustomEvent("page:changed", {
      detail: {
        index,
        factor,
        frameW: pageFrame.clientWidth,
        frameH: pageFrame.clientHeight,
      },
    })
  );
}

const prevBtn = document.getElementById("page-prev");
const nextBtn = document.getElementById("page-next");
const jumpInput = document.getElementById("page-jump");
const indicatorCompact = document.getElementById("page-indicator-compact");
const indicatorLabel = document.getElementById("page-indicator-label");

const zoomOutBtn = document.getElementById("zoom-out");
const zoomInBtn = document.getElementById("zoom-in");
const zoomFitBtn = document.getElementById("zoom-fit");
const zoomLevel = document.getElementById("zoom-level");

const rotateCwBtn = document.getElementById("rotate-cw");
const rotateCcwBtn = document.getElementById("rotate-ccw");

// ---- State ------------------------------------------------------------------------
const state = {
  sessionId: null,
  pageCount: 0,
  pageIndex: 0, // 0-based
  zoomStep: 2, // index into ZOOM_STEPS (1.0 == 100%)
  fitPage: false, // when true, zoom factor fits the WHOLE page into the stage (contain), not a step
  // True render box (CSS px == device-independent px the server rendered at 200 DPI / devicePixelRatio).
  renderBox: { cssW: 0, cssH: 0 },
  // Per-page USER rotation (0/90/180/270), keyed by page index. Default 0; persists so paging
  // away and back keeps each page's rotation. Baked into the download via the /process payload.
  userRotation: new Map(),
};

/** The user rotation (0/90/180/270) for a page index; default 0. */
function rotationFor(index) {
  return state.userRotation.get(index) || 0;
}

// ---- Helpers ----------------------------------------------------------------------
function showPageLoader(show) {
  if (pageLoader) pageLoader.hidden = !show;
}

// The render box in CSS pixels: the 200-DPI image is img_w device pixels wide; divide by the
// device pixel ratio so a 100% zoom shows the page at its natural on-screen size.
function computeRenderBox(meta) {
  const dpr = window.devicePixelRatio || 1;
  state.renderBox.cssW = meta.img_w / dpr;
  state.renderBox.cssH = meta.img_h / dpr;
}

// Current zoom factor: either the active discrete step, or the fit-to-PAGE derived factor.
// Fit-to-page (the default on load) contains the whole page in the stage viewport: it takes the
// smaller of the width- and height-fit ratios so a tall page is fully visible without scrolling,
// and is capped at 1.0 so a small page is never upscaled (blurred) past its natural size.
function currentZoomFactor() {
  if (state.fitPage && state.renderBox.cssW > 0 && state.renderBox.cssH > 0) {
    const availW = stage.clientWidth - 64; // minus stage padding (~--space-xl each side)
    const availH = stage.clientHeight - 64;
    const fit = Math.min(availW / state.renderBox.cssW, availH / state.renderBox.cssH);
    return Math.max(0.1, Math.min(fit, 1.0));
  }
  return ZOOM_STEPS[state.zoomStep];
}

// Apply the current zoom by CSS-scaling the displayed image + sizing the frame to match.
// This does NOT touch the image URL/dpi (D-02) — the same fetched PNG is scaled.
function applyZoom() {
  const factor = currentZoomFactor();
  const w = Math.round(state.renderBox.cssW * factor);
  const h = Math.round(state.renderBox.cssH * factor);
  if (w > 0) {
    pageImage.style.width = w + "px";
    pageImage.style.height = h + "px";
    // Frame tracks the displayed render box so the overlay host stays sized to the true box.
    pageFrame.style.width = w + "px";
    pageFrame.style.height = h + "px";
  }
  zoomLevel.textContent = Math.round(factor * 100) + "%";
  updateZoomButtons();
  // Notify the overlay so it reprojects committed rectangles to the new displayed box (D-02).
  emitPageZoomed(factor);
}

function updateZoomButtons() {
  // Discrete-step bounds (fit-to-page is a separate mode; both step buttons stay usable from it).
  zoomOutBtn.disabled = !state.fitPage && state.zoomStep <= 0;
  zoomInBtn.disabled = !state.fitPage && state.zoomStep >= ZOOM_STEPS.length - 1;
}

function updateNavButtons() {
  prevBtn.disabled = state.pageIndex <= 0;
  nextBtn.disabled = state.pageIndex >= state.pageCount - 1;
}

// Render the page indicator: compact "{current} / {total}" with the active number in the accent
// span, plus the long-form accessible label. All via textContent (no innerHTML) — T-01-15.
function updateIndicator() {
  const current = state.pageIndex + 1;
  const total = state.pageCount;

  indicatorCompact.replaceChildren();
  const cur = document.createElement("span");
  cur.className = "page-current";
  cur.textContent = String(current);
  indicatorCompact.append(cur, document.createTextNode(" / " + total));

  indicatorLabel.textContent = COPY.indicatorLabel(current, total);
  jumpInput.max = String(total);
}

// ---- Page rendering ---------------------------------------------------------------
// Monotonic request-generation token (WR-01): fast navigation (double-click Next, holding
// ArrowRight, jump-then-arrow) interleaves async /meta fetches and image loads. Each
// renderPage call claims the next token; any continuation — the awaited /meta result, the
// img onload/onerror — bails out the moment a newer call has superseded it, so a slower
// earlier page can never paint under a newer page's indicator or read a clobbered renderBox.
let renderToken = 0;

async function renderPage(index) {
  if (index < 0 || index >= state.pageCount) return;
  const myToken = ++renderToken;
  state.pageIndex = index;
  updateNavButtons();
  updateIndicator();

  showPageLoader(true);

  // Size the frame to the true render box BEFORE the image loads (coordinate fidelity).
  // Measure against the ROTATED meta (img_w/img_h swap for a quarter turn) so the overlay's
  // projection denominator matches the rotated image the server returns.
  const rotate = rotationFor(index);
  try {
    const meta = await api.pageMeta(state.sessionId, index, rotate);
    if (myToken !== renderToken) return; // a newer navigation superseded us
    computeRenderBox(meta);
    applyZoom();
  } catch {
    if (myToken !== renderToken) return; // stale failure — let the newer call own the UI
    // /meta failed — fall back to letting the image's natural size drive layout once it loads.
    state.renderBox.cssW = 0;
    state.renderBox.cssH = 0;
  }

  // Set the <img> src to the server render URL (no dpi arg => server default 200). One fetch
  // per page; zoom never changes this URL.
  pageImage.onload = () => {
    if (myToken !== renderToken) return; // a later page's load is the authoritative one
    showPageLoader(false);
    // If /meta was unavailable, derive the render box from the image's natural pixels now.
    if (state.renderBox.cssW === 0) {
      const dpr = window.devicePixelRatio || 1;
      state.renderBox.cssW = pageImage.naturalWidth / dpr;
      state.renderBox.cssH = pageImage.naturalHeight / dpr;
      applyZoom();
    }
    // The frame is now sized to the true render box: tell the overlay which page is shown so it
    // swaps in this page's region set and reprojects. (Only the winning render reaches here.)
    emitPageChanged(state.pageIndex, currentZoomFactor());
  };
  pageImage.onerror = () => {
    if (myToken !== renderToken) return; // stale error from a superseded page
    showPageLoader(false);
    showPageError();
  };
  pageImage.src = api.pageImageURL(state.sessionId, index, undefined, rotate);
}

// Render-failure: surface the inline page-render-failure copy on the stage's error state.
function showPageError() {
  const states = stage.querySelectorAll("[data-state]");
  states.forEach((el) => {
    el.hidden = el.getAttribute("data-state") !== "error";
  });
  const errorBody = document.getElementById("error-body");
  const errorHeading = document.getElementById("error-heading");
  if (errorHeading) errorHeading.textContent = "無法開啟此檔案";
  if (errorBody) errorBody.textContent = COPY.pageRenderFailure;
}

// ---- Navigation -------------------------------------------------------------------
function goPrev() {
  if (state.pageIndex > 0) renderPage(state.pageIndex - 1);
}
function goNext() {
  if (state.pageIndex < state.pageCount - 1) renderPage(state.pageIndex + 1);
}
function jumpTo(value) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return;
  const clamped = Math.min(Math.max(n, 1), state.pageCount); // clamp 1..total
  renderPage(clamped - 1);
}

// ---- Zoom -------------------------------------------------------------------------
function zoomIn() {
  state.fitPage = false;
  if (state.zoomStep < ZOOM_STEPS.length - 1) state.zoomStep += 1;
  applyZoom();
}
function zoomOut() {
  state.fitPage = false;
  if (state.zoomStep > 0) state.zoomStep -= 1;
  applyZoom();
}
function fitToPage() {
  state.fitPage = true;
  applyZoom();
}

// ---- Rotation ---------------------------------------------------------------------
// 順時針 = (r+90)%360, 逆時針 = (r+270)%360. Per-page (persists across nav). On rotate we
// DROP the cached render box (its dims swap for a quarter turn) and re-render the current page:
// renderPage re-fetches /meta?rotate + the image?rotate, re-applies zoom/fit, and emits
// page:changed so regions.js reprojects committed rectangles onto the new (rotated) box.
function rotateBy(deltaDeg) {
  if (state.sessionId === null) return;
  const cur = rotationFor(state.pageIndex);
  const next = (cur + deltaDeg + 360) % 360;
  state.userRotation.set(state.pageIndex, next);
  // Tell the overlay this page's image dims are now stale (they swap for a quarter turn) so it
  // drops its cached /meta dims and re-fetches at the new rotation before reprojecting. The
  // page:changed event from the re-render's onload then triggers the reprojection. This is a
  // job-input change (the download bakes the rotation), so regions.js also invalidates any
  // fresh result (notifyJobInputChanged) on receiving it.
  stage.dispatchEvent(
    new CustomEvent("page:rotated", {
      detail: { index: state.pageIndex, rotation: next, delta: (deltaDeg + 360) % 360 },
    })
  );
  // Force a fresh render-box measurement (the cached one is for the previous orientation).
  state.renderBox.cssW = 0;
  state.renderBox.cssH = 0;
  renderPage(state.pageIndex);
}

function rotateCw() {
  rotateBy(90);
}
function rotateCcw() {
  rotateBy(270);
}

// ---- Wiring (idempotent: initViewer may run once per upload) -----------------------
let wired = false;
function wireControls() {
  if (wired) return;
  wired = true;

  prevBtn.addEventListener("click", goPrev);
  nextBtn.addEventListener("click", goNext);
  zoomInBtn.addEventListener("click", zoomIn);
  zoomOutBtn.addEventListener("click", zoomOut);
  zoomFitBtn.addEventListener("click", fitToPage);
  rotateCwBtn.addEventListener("click", rotateCw);
  rotateCcwBtn.addEventListener("click", rotateCcw);

  // Re-fit on viewport resize while in fit-to-page mode so the page stays fully visible.
  window.addEventListener("resize", () => {
    if (state.fitPage && state.renderBox.cssW > 0) applyZoom();
  });

  jumpInput.addEventListener("change", () => jumpTo(jumpInput.value));
  jumpInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      jumpTo(jumpInput.value);
    }
  });

  // Keyboard: Left/Right page nav when the stage has focus; +/- zoom.
  stage.addEventListener("keydown", (e) => {
    if (e.target === jumpInput) return; // don't hijack typing in the jump field
    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        goPrev();
        break;
      case "ArrowRight":
        e.preventDefault();
        goNext();
        break;
      case "+":
      case "=": // unshifted "+" key
        e.preventDefault();
        zoomIn();
        break;
      case "-":
      case "_":
        e.preventDefault();
        zoomOut();
        break;
      default:
        break;
    }
  });
}

// ---- Public API (called by app.js) -------------------------------------------------
export async function initViewer({ session_id, page_count }) {
  state.sessionId = session_id;
  state.pageCount = page_count || 0;
  state.pageIndex = 0;
  state.zoomStep = 2; // 100% (used once the user picks a discrete zoom step)
  state.fitPage = true; // default: fit the WHOLE page into the viewport so it's visible at once
  state.userRotation = new Map(); // a new doc starts with no per-page rotation

  // Enable per-control disabled attributes (the clusters were revealed by app.js).
  jumpInput.disabled = false;
  zoomFitBtn.disabled = false;
  rotateCwBtn.disabled = false;
  rotateCcwBtn.disabled = false;

  wireControls();
  await renderPage(0);
}

export function resetViewer() {
  state.sessionId = null;
  state.pageCount = 0;
  state.pageIndex = 0;
  pageImage.removeAttribute("src");
  showPageLoader(false);
}

// ---- Phase 2 accessors for the region overlay + before/after toggle ----------------
// regions.js needs the live session/page coordinates and a way to swap the displayed image
// between the original render and the 移除結果 render WITHOUT contacting the server itself or
// forking the render machinery. These helpers keep api.js the sole seam (regions.js calls them
// and api.* URL builders only) and reuse the same <img> + frame the viewer already sizes.

/** Snapshot of the viewer's live coordinates for the overlay/action group. */
export function getViewerState() {
  return {
    sessionId: state.sessionId,
    pageIndex: state.pageIndex,
    pageCount: state.pageCount,
  };
}

/** Restore the ORIGINAL page render for the current page (原圖), at its user rotation. */
export function showOriginalImage() {
  if (state.sessionId === null) return;
  pageImage.src = api.pageImageURL(
    state.sessionId,
    state.pageIndex,
    undefined,
    rotationFor(state.pageIndex)
  );
}

/** Show the 移除結果 (after) render for the current page. `url` is built by api.resultImageURL. */
export function showResultImage(url) {
  if (state.sessionId === null || !url) return;
  pageImage.src = url;
}

/** The user rotation (0/90/180/270) for the current page — regions.js builds the result URL. */
export function getCurrentRotation() {
  return rotationFor(state.pageIndex);
}

/**
 * The non-zero per-page rotations as a plain object { pageIndex: degrees } for the /process
 * payload. Only pages the user actually rotated are included (a 0 is the default and omitted),
 * so the server bakes exactly those into the download. Keys are numbers; degrees are 0/90/180/270.
 */
export function getRotations() {
  const out = {};
  for (const [index, deg] of state.userRotation.entries()) {
    if (deg) out[index] = deg;
  }
  return out;
}
