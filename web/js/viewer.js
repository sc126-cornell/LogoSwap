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

const prevBtn = document.getElementById("page-prev");
const nextBtn = document.getElementById("page-next");
const jumpInput = document.getElementById("page-jump");
const indicatorCompact = document.getElementById("page-indicator-compact");
const indicatorLabel = document.getElementById("page-indicator-label");

const zoomOutBtn = document.getElementById("zoom-out");
const zoomInBtn = document.getElementById("zoom-in");
const zoomFitBtn = document.getElementById("zoom-fit");
const zoomLevel = document.getElementById("zoom-level");

// ---- State ------------------------------------------------------------------------
const state = {
  sessionId: null,
  pageCount: 0,
  pageIndex: 0, // 0-based
  zoomStep: 2, // index into ZOOM_STEPS (1.0 == 100%)
  fitWidth: false, // when true, zoom factor is derived from the stage width instead of a step
  // True render box (CSS px == device-independent px the server rendered at 200 DPI / devicePixelRatio).
  renderBox: { cssW: 0, cssH: 0 },
};

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

// Current zoom factor: either the active discrete step, or the fit-to-width derived factor.
function currentZoomFactor() {
  if (state.fitWidth && state.renderBox.cssW > 0) {
    const available = stage.clientWidth - 64; // minus stage padding (~--space-xl each side)
    return Math.max(0.1, available / state.renderBox.cssW);
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
}

function updateZoomButtons() {
  // Discrete-step bounds (fit-to-width is a separate mode; both step buttons stay usable from it).
  zoomOutBtn.disabled = !state.fitWidth && state.zoomStep <= 0;
  zoomInBtn.disabled = !state.fitWidth && state.zoomStep >= ZOOM_STEPS.length - 1;
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
  try {
    const meta = await api.pageMeta(state.sessionId, index);
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
  };
  pageImage.onerror = () => {
    if (myToken !== renderToken) return; // stale error from a superseded page
    showPageLoader(false);
    showPageError();
  };
  pageImage.src = api.pageImageURL(state.sessionId, index);
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
  state.fitWidth = false;
  if (state.zoomStep < ZOOM_STEPS.length - 1) state.zoomStep += 1;
  applyZoom();
}
function zoomOut() {
  state.fitWidth = false;
  if (state.zoomStep > 0) state.zoomStep -= 1;
  applyZoom();
}
function fitToWidth() {
  state.fitWidth = true;
  applyZoom();
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
  zoomFitBtn.addEventListener("click", fitToWidth);

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
  state.zoomStep = 2; // 100%
  state.fitWidth = false;

  // Enable per-control disabled attributes (the clusters were revealed by app.js).
  jumpInput.disabled = false;
  zoomFitBtn.disabled = false;

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
