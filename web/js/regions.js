/*
 * regions.js — Phase 2 region selection: a transparent drawing overlay over the Phase-1 page
 * stage, a per-page region model, the side-panel region list, the before/after toggle, and the
 * apply / download action group. Vanilla JS, no build (SKELETON.md).
 *
 * Coordinate fidelity (the load-bearing seam, ARCHITECTURE Pattern 2 / PITFALLS 1-2):
 *   - Rectangles are stored in IMAGE-PIXEL space at the page's EFFECTIVE render DPI — deferred-
 *     mutation D-05. The browser holds image-pixel rects; the SERVER (Plan 02-02) is the only place
 *     that converts to PDF points and mutates documents.
 *   - CR-01: the effective render DPI can be REDUCED below the requested 200 by the server's
 *     pixel-budget guard (render.fit_dpi_to_pixel_budget) for a large-MediaBox page. So we NEVER
 *     hardcode dpi=200 for measurement: the overlay measures px against the img_w/img_h /meta
 *     reported for THAT page (which are already at the effective DPI), and we record meta.dpi per
 *     page. The JobSpec carries the requested render DPI as the ceiling; the server re-derives the
 *     effective DPI PER PAGE (identical fit) so client and server agree on scale by construction.
 *   - The overlay is a child of #page-frame (position:absolute inset:0). The frame is sized by
 *     viewer.js to the displayed render box (renderBox × zoom). We map overlay-local CSS pixels to
 *     image pixels via the per-page image dimensions (img_w/img_h from api.pageMeta) divided by the
 *     frame's displayed size: imageX = localX × (img_w / frameW). Inverse for projecting committed
 *     rects back to the displayed box. This stays correct across CSS-scale zoom (frameW changes;
 *     img_w is the constant effective-DPI pixel width).
 *
 * Security:
 *   - All dynamic strings are written via textContent / createElement — never innerHTML (T-02-11).
 *   - This module NEVER contacts the server directly: it builds result/download URLs only via the
 *     api.js helpers and swaps images through the viewer helpers (T-02-12 — api.js is the sole seam).
 */

import * as api from "./api.js";
// WR-04: getViewerState was imported but never used (the module drives off currentPage +
// page:changed event detail, not the viewer snapshot). Dropped to keep the data flow honest.
import { showOriginalImage, showResultImage } from "./viewer.js";

// ---- Verbatim SPEC copy (繁體中文) -------------------------------------------------
const COPY = {
  // counts / scope
  count: (n) => `已框選 ${n} 個區域`,
  scope: (current) => `目前顯示第 ${current} 頁的框選`,
  regionLabel: (n) => `區域 ${n}`,
  deleteRegion: "刪除此區域",
  // action group / status
  applyDisabledHint: "先框選至少一個區域,再套用移除",
  applying: "正在套用移除…",
  resultReady: "移除結果已就緒,可切換對照或下載",
  staleNotice: "框選已變更,請重新套用以更新結果",
  preparingDownload: "正在準備下載…",
  reapply: "重新套用",
  apply: "套用移除",
  // before/after
  noResultYet: "尚無移除結果,請先套用移除",
  // notices / errors
  nothingRemoved:
    "框選區域內沒有可移除的內容。請確認框選位置,或此頁可能為圖片型(將於後續版本支援)。",
  clamped: "框選超出頁面範圍,已自動調整到頁面邊界。",
  removalFailed: "套用移除時發生問題。請再試一次,或調整框選範圍後重試。",
  resultRenderFailed: "無法產生移除結果預覽。請重新套用移除。",
  downloadFailed: "下載失敗,請檢查網路連線後再試一次。",
};

// The REQUESTED render DPI (the ceiling). The server clamps this and may reduce the EFFECTIVE
// DPI per page to fit the pixel budget (CR-01); px_rect is always measured against the per-page
// effective-DPI image dims from /meta, never assumed to be this value. Kept in sync with the
// server default (config.DEFAULT_DPI) so a job posts the same ceiling the viewer renders at.
const REQUESTED_DPI = 200;
const DRAG_THRESHOLD = 4; // px — sub-threshold drags create no region (no accidental zero-area).

// ---- DOM refs ---------------------------------------------------------------------
const stage = document.getElementById("page-stage");
const pageFrame = document.getElementById("page-frame");
const pageImage = document.getElementById("page-image");

const sidePanel = document.getElementById("side-panel");
const regionCountEl = document.getElementById("region-count");
const regionScopeEl = document.getElementById("region-scope");
const regionEmptyEl = document.getElementById("region-empty");
const regionListEl = document.getElementById("region-list");
const clearAllBtn = document.getElementById("clear-all");

const noticeEl = document.getElementById("region-notice");
const noticeBodyEl = document.getElementById("region-notice-body");
const noticeRetryBtn = document.getElementById("region-notice-retry");

const beforeafterToggle = document.getElementById("beforeafter-toggle");
const viewOriginalBtn = document.getElementById("view-original");
const viewResultBtn = document.getElementById("view-result");

const actionGroup = document.getElementById("action-group");
const actionStatusEl = document.getElementById("action-status");
const applyBtn = document.getElementById("apply-removal");
const downloadBtn = document.getElementById("download-pdf");

const clearConfirm = document.getElementById("clear-confirm");
const clearConfirmScrim = document.getElementById("clear-confirm-scrim");
const clearCancelBtn = document.getElementById("clear-cancel");
const clearConfirmBtn = document.getElementById("clear-confirm-btn");

// ---- Model -------------------------------------------------------------------------
// Per-page region map: pageIndex -> [{ id, pxRect:[x0,y0,x1,y1] }] in IMAGE-PIXEL space (dpi 200).
const regionsByPage = new Map();
// Per-page image dimensions (image pixels) + effective DPI from api.pageMeta — the projection
// denominator. dpi is the EFFECTIVE per-page render DPI (CR-01), recorded so px measurements and
// any per-page scale stay attached to the exact image the server produced for that page.
const imageDimsByPage = new Map(); // pageIndex -> { imgW, imgH, dpi }

let sessionId = null;
// WR-04: pageCount was assigned but never read (nav/paging is owned by viewer.js; this module
// reacts to the page:changed event detail). Removed to avoid dead source-of-truth state.
let currentPage = 0;
let nextRegionId = 1;

// Overlay element (created once, re-parented under #page-frame).
let overlay = null;
// In-progress drag rubber-band element + start point (image-px) while drawing.
let drawEl = null;
let dragStart = null; // { localX, localY }
let dragActiveId = null; // pointer id captured during a draw

// before/after state
let viewMode = "original"; // "original" | "result"
// Result freshness: true only between a successful apply and the next region edit (D-05/D-07).
let resultFresh = false;
let applying = false;

// ---- Helpers -----------------------------------------------------------------------
function pageList(index) {
  if (!regionsByPage.has(index)) regionsByPage.set(index, []);
  return regionsByPage.get(index);
}

function totalRegionCount() {
  let total = 0;
  for (const list of regionsByPage.values()) total += list.length;
  return total;
}

// image-px <-> displayed-px projection for the CURRENT page using the live frame box.
function projection() {
  const dims = imageDimsByPage.get(currentPage);
  const frameW = pageFrame.clientWidth;
  const frameH = pageFrame.clientHeight;
  // Fall back to the image's natural pixels if /meta dims aren't recorded yet.
  const imgW = (dims && dims.imgW) || pageImage.naturalWidth || frameW;
  const imgH = (dims && dims.imgH) || pageImage.naturalHeight || frameH;
  return {
    toImageX: (localX) => (frameW > 0 ? (localX * imgW) / frameW : 0),
    toImageY: (localY) => (frameH > 0 ? (localY * imgH) / frameH : 0),
    toDispX: (imgX) => (imgW > 0 ? (imgX * frameW) / imgW : 0),
    toDispY: (imgY) => (imgH > 0 ? (imgY * frameH) / imgH : 0),
    imgW,
    imgH,
  };
}

// Clamp an image-px coordinate to the page's pixel box (defensive; server clamps authoritatively).
function clampImg(value, max) {
  return Math.max(0, Math.min(value, max));
}

// ---- Side-panel list rendering -----------------------------------------------------
function renderList() {
  const list = pageList(currentPage);

  // Count + scope (textContent — never innerHTML).
  regionCountEl.textContent = COPY.count(totalRegionCount());
  regionScopeEl.textContent = COPY.scope(currentPage + 1);

  // Clear-all is enabled only when the CURRENT page has regions (its scope is this page, D-02).
  clearAllBtn.disabled = list.length === 0;

  // Empty-state vs the row list.
  const isEmpty = list.length === 0;
  regionEmptyEl.hidden = !isEmpty;
  regionListEl.hidden = isEmpty;

  // Rebuild rows (createElement only).
  regionListEl.replaceChildren();
  list.forEach((region, i) => {
    const li = document.createElement("li");
    li.className = "region-row";
    li.dataset.regionId = String(region.id);
    li.tabIndex = 0; // Tab-reachable with the focus ring

    const label = document.createElement("span");
    label.className = "region-row__label";
    label.textContent = COPY.regionLabel(i + 1);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "region-row__delete";
    del.setAttribute("aria-label", COPY.deleteRegion);
    del.title = COPY.deleteRegion;
    del.appendChild(makeTrashIcon());

    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteRegion(region.id);
    });

    // Bidirectional hover/focus: highlight the matching rectangle.
    const activate = () => setActiveRegion(region.id, true);
    const deactivate = () => setActiveRegion(region.id, false);
    li.addEventListener("mouseenter", activate);
    li.addEventListener("mouseleave", deactivate);
    li.addEventListener("focus", activate);
    li.addEventListener("blur", deactivate);
    li.addEventListener("keydown", (e) => {
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        deleteRegion(region.id);
      }
    });

    li.append(label, del);
    regionListEl.appendChild(li);
  });
}

function makeTrashIcon() {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("width", "18");
  svg.setAttribute("height", "18");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(NS, "path");
  path.setAttribute(
    "d",
    "M4 6h12M8 6V4.5h4V6M6 6l.7 9.5h6.6L14 6M9 9v4M11 9v4"
  );
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.5");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.appendChild(path);
  return svg;
}

// ---- Overlay rectangle rendering ---------------------------------------------------
function ensureOverlay() {
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.className = "region-overlay";
  overlay.id = "region-overlay";
  pageFrame.appendChild(overlay);
  wireOverlayPointer();
  return overlay;
}

// Re-derive ALL committed rectangles for the current page from their stored image-px rects, at the
// current displayed projection. The stored image-px source of truth never changes — only the
// displayed projection (so rectangles stay pinned over the same content across zoom).
function renderOverlay() {
  if (!overlay) return;
  // Keep any in-progress drag element; remove only committed rects, then rebuild them.
  overlay
    .querySelectorAll(".region-rect:not(.region-rect--drawing)")
    .forEach((el) => el.remove());

  // In result mode the overlay rectangles are HIDDEN (UI-SPEC: the after view has no rects).
  if (viewMode === "result") return;

  const list = pageList(currentPage);
  const proj = projection();
  list.forEach((region, i) => {
    const [x0, y0, x1, y1] = region.pxRect;
    const left = proj.toDispX(Math.min(x0, x1));
    const top = proj.toDispY(Math.min(y0, y1));
    const width = proj.toDispX(Math.abs(x1 - x0));
    const height = proj.toDispY(Math.abs(y1 - y0));

    const rect = document.createElement("div");
    rect.className = "region-rect";
    rect.dataset.regionId = String(region.id);
    rect.style.left = left + "px";
    rect.style.top = top + "px";
    rect.style.width = width + "px";
    rect.style.height = height + "px";

    // Ordinal badge (shown when active; created always, hidden until active via CSS sibling state).
    const badge = document.createElement("span");
    badge.className = "region-rect__badge";
    badge.textContent = String(i + 1);
    badge.hidden = true;
    rect.appendChild(badge);

    // Bidirectional hover: highlight the matching list row.
    rect.addEventListener("mouseenter", () => setActiveRegion(region.id, true));
    rect.addEventListener("mouseleave", () => setActiveRegion(region.id, false));

    overlay.appendChild(rect);
  });
}

// Highlight (or clear) the rectangle + row for a region id (bidirectional row<->rect).
// WR-03: look up by dataset comparison rather than interpolating `id` into a CSS selector
// string. Interpolation is safe only while ids are internal integers; a future non-numeric or
// quote-bearing id would break the selector or allow selector injection. Comparing
// dataset.regionId === String(id) is robust regardless of the id's shape.
function setActiveRegion(id, active) {
  const key = String(id);
  if (overlay) {
    const rect = [...overlay.querySelectorAll(".region-rect")].find(
      (el) => el.dataset.regionId === key
    );
    if (rect) {
      rect.classList.toggle("is-active", active);
      const badge = rect.querySelector(".region-rect__badge");
      if (badge) badge.hidden = !active;
    }
  }
  const row = [...regionListEl.querySelectorAll(".region-row")].find(
    (el) => el.dataset.regionId === key
  );
  if (row) row.classList.toggle("is-active", active);
}

// ---- Drawing (pointer) -------------------------------------------------------------
function wireOverlayPointer() {
  overlay.addEventListener("pointerdown", onPointerDown);
  overlay.addEventListener("pointermove", onPointerMove);
  overlay.addEventListener("pointerup", onPointerUp);
  overlay.addEventListener("pointercancel", cancelDraw);
}

function localPoint(e) {
  const box = overlay.getBoundingClientRect();
  return { localX: e.clientX - box.left, localY: e.clientY - box.top };
}

function onPointerDown(e) {
  // Only draw in original mode (overlay hidden/disabled in result mode), primary button only.
  if (viewMode === "result") return;
  if (e.button !== undefined && e.button !== 0) return;
  if (sessionId === null) return;

  dragStart = localPoint(e);
  dragActiveId = e.pointerId;
  try {
    overlay.setPointerCapture(e.pointerId);
  } catch {
    /* setPointerCapture can throw if the pointer is already released — ignore. */
  }

  drawEl = document.createElement("div");
  drawEl.className = "region-rect region-rect--drawing";
  drawEl.style.left = dragStart.localX + "px";
  drawEl.style.top = dragStart.localY + "px";
  drawEl.style.width = "0px";
  drawEl.style.height = "0px";
  overlay.appendChild(drawEl);
}

function onPointerMove(e) {
  if (!dragStart || !drawEl) return;
  const { localX, localY } = localPoint(e);
  const left = Math.min(localX, dragStart.localX);
  const top = Math.min(localY, dragStart.localY);
  const width = Math.abs(localX - dragStart.localX);
  const height = Math.abs(localY - dragStart.localY);
  drawEl.style.left = left + "px";
  drawEl.style.top = top + "px";
  drawEl.style.width = width + "px";
  drawEl.style.height = height + "px";
}

function onPointerUp(e) {
  if (!dragStart || !drawEl) return;
  const { localX, localY } = localPoint(e);
  const dx = Math.abs(localX - dragStart.localX);
  const dy = Math.abs(localY - dragStart.localY);

  const start = dragStart;
  cleanupDrag(e);

  // Sub-threshold drag (a stray click) -> no region (no accidental zero-area region).
  if (dx < DRAG_THRESHOLD && dy < DRAG_THRESHOLD) {
    renderOverlay();
    return;
  }

  // Convert the displayed-CSS drag box to IMAGE-PIXEL space (the stored, server-bound coords).
  const proj = projection();
  const ix0 = clampImg(proj.toImageX(Math.min(localX, start.localX)), proj.imgW);
  const iy0 = clampImg(proj.toImageY(Math.min(localY, start.localY)), proj.imgH);
  const ix1 = clampImg(proj.toImageX(Math.max(localX, start.localX)), proj.imgW);
  const iy1 = clampImg(proj.toImageY(Math.max(localY, start.localY)), proj.imgH);

  // Overlap is allowed (no collision rejection) — just append (D-01).
  pageList(currentPage).push({
    id: nextRegionId++,
    pxRect: [
      Math.round(ix0),
      Math.round(iy0),
      Math.round(ix1),
      Math.round(iy1),
    ],
  });

  onRegionsEdited();
}

function cancelDraw(e) {
  if (!dragStart) return;
  cleanupDrag(e);
  renderOverlay();
}

function cleanupDrag(e) {
  if (drawEl && drawEl.parentNode) drawEl.parentNode.removeChild(drawEl);
  drawEl = null;
  dragStart = null;
  if (dragActiveId !== null) {
    try {
      overlay.releasePointerCapture(dragActiveId);
    } catch {
      /* already released — ignore */
    }
  }
  dragActiveId = null;
}

// ---- Mutations (delete one / clear all) --------------------------------------------
function deleteRegion(id) {
  const list = pageList(currentPage);
  const idx = list.findIndex((r) => r.id === id);
  if (idx === -1) return;
  list.splice(idx, 1);
  onRegionsEdited();
}

function clearAllCurrentPage() {
  regionsByPage.set(currentPage, []);
  onRegionsEdited();
}

// ---- Region-edit reaction (re-render + stale handling) -----------------------------
// Any region edit (draw/delete/clear) after a result exists invalidates the shown 移除結果 (D-05).
function onRegionsEdited() {
  if (resultFresh) {
    resultFresh = false;
    // If we were viewing the (now stale) result, drop back to 原圖 so the user re-applies.
    if (viewMode === "result") {
      setViewMode("original");
    }
    setActionStatus(COPY.staleNotice);
  }
  renderList();
  renderOverlay();
  updateActionGroup();
}

// ---- Job-input change hook (the ONE shared stale machine — Pitfall 5 load-bearing) -------
// A logo selection/clear (logos.js) is a job-input change, exactly like a region edit, so it
// MUST run the SAME invalidation rather than forking the action-group machine. logos.js calls
// this on every selection change. An optional message lets the logo case use its own stale copy
// (UI-SPEC default #7); otherwise the Phase-2 notice is reused.
export function notifyJobInputChanged(message) {
  if (resultFresh) {
    resultFresh = false;
    if (viewMode === "result") {
      setViewMode("original");
    }
    setActionStatus(message || COPY.staleNotice);
  }
  updateActionGroup();
}

// ---- Action group state machine ----------------------------------------------------
// Exactly ONE accent-filled button per state: 套用移除 (accent) until a fresh result exists, then
// 下載 PDF (accent) and apply demotes to neutral 重新套用. The accent is .primary-btn; neutral is
// .text-btn (the same neutral treatment as 更換檔案 etc.).
function updateActionGroup() {
  const total = totalRegionCount();

  if (resultFresh) {
    // Result-ready: download is the single accent CTA; apply demotes to neutral 重新套用.
    applyBtn.textContent = COPY.reapply;
    applyBtn.className = "text-btn";
    applyBtn.disabled = total === 0 || applying;
    applyBtn.removeAttribute("title");

    downloadBtn.hidden = false;
    downloadBtn.className = "primary-btn";
    downloadBtn.disabled = false;
  } else {
    // No fresh result: apply is the single accent CTA (disabled with 0 regions); download disabled.
    applyBtn.textContent = COPY.apply;
    applyBtn.className = "primary-btn";
    applyBtn.disabled = total === 0 || applying;
    if (total === 0) {
      applyBtn.title = COPY.applyDisabledHint;
    } else {
      applyBtn.removeAttribute("title");
    }

    // Keep the download button in the layout but neutral + disabled until a fresh result.
    downloadBtn.className = "text-btn";
    downloadBtn.disabled = true;
    downloadBtn.hidden = total === 0; // only meaningful once the user is in the flow
  }

  // The 移除結果 segment is only selectable when a fresh result exists.
  viewResultBtn.disabled = !resultFresh && viewMode !== "result";
}

function setActionStatus(text) {
  actionStatusEl.textContent = text || "";
}

// ---- Inline notice / error ---------------------------------------------------------
function showNotice(text, withRetry, onRetry) {
  noticeBodyEl.textContent = text; // textContent — never inject server text as HTML (T-02-11).
  noticeRetryBtn.hidden = !withRetry;
  noticeEl.hidden = false;
  if (withRetry) {
    noticeRetryBtn.onclick = () => {
      hideNotice();
      if (onRetry) onRetry();
    };
  } else {
    noticeRetryBtn.onclick = null;
  }
}

function hideNotice() {
  noticeEl.hidden = true;
  noticeBodyEl.textContent = "";
  noticeRetryBtn.hidden = true;
  noticeRetryBtn.onclick = null;
}

// ---- Before/after toggle -----------------------------------------------------------
function setViewMode(mode) {
  // Guard: can't show the result without a fresh one.
  if (mode === "result" && !resultFresh) {
    setActionStatus(COPY.noResultYet);
    return;
  }
  viewMode = mode;

  const showingResult = mode === "result";
  viewOriginalBtn.classList.toggle("is-selected", !showingResult);
  viewOriginalBtn.setAttribute("aria-pressed", String(!showingResult));
  viewResultBtn.classList.toggle("is-selected", showingResult);
  viewResultBtn.setAttribute("aria-pressed", String(showingResult));

  if (showingResult) {
    // Swap the page image to the result render (via the viewer helper + api URL); hide overlay.
    showResultImage(api.resultImageURL(sessionId, currentPage));
    if (overlay) overlay.hidden = true;
  } else {
    showOriginalImage();
    if (overlay) overlay.hidden = false;
  }
  renderOverlay();
}

// ---- Apply / download (Task 3 wiring) ----------------------------------------------
function mapErrorCopy(err) {
  const code = err && err.code ? err.code : "unknown";
  switch (code) {
    case "residual_content":
    case "page_out_of_range":
    case "invalid_request":
      return COPY.removalFailed;
    case "result_not_ready":
      return COPY.downloadFailed;
    default:
      return COPY.removalFailed; // network/unknown during apply
  }
}

async function applyRemoval() {
  if (applying) return;
  const total = totalRegionCount();
  if (total === 0) return;

  hideNotice();
  applying = true;
  updateActionGroup();
  setActionStatus(COPY.applying);

  try {
    const result = await api.processJob(sessionId, {
      // The requested render DPI (ceiling). The server re-derives the EFFECTIVE DPI per page
      // and maps px_rect — which the overlay measured against the per-page effective dims — so
      // a page whose effective DPI was reduced below this still redacts the correct area (CR-01).
      dpi: REQUESTED_DPI,
      regions: getJobRegions(),
    });

    applying = false;
    resultFresh = true;

    // Surface per-region feedback from the server's authoritative result (never assume applied).
    const flags = (result && result.regions) || [];
    const anyRemoved = flags.some((r) => r.removed);
    const anyClamped = flags.some((r) => r.clamped);
    if (flags.length > 0 && !anyRemoved) {
      showNotice(COPY.nothingRemoved, false);
    } else if (anyClamped) {
      showNotice(COPY.clamped, false);
    } else {
      hideNotice();
    }

    setActionStatus(COPY.resultReady);
    updateActionGroup();
    // Auto-switch to the result view so the before/after comparison is immediate.
    setViewMode("result");
  } catch (err) {
    applying = false;
    resultFresh = false;
    setActionStatus("");
    showNotice(mapErrorCopy(err), true, applyRemoval);
    updateActionGroup();
  }
}

function downloadResult() {
  if (!resultFresh) return;
  setActionStatus(COPY.preparingDownload);
  // Navigate to the download URL; the browser handles the attachment + filename* (原名_logoswap.pdf).
  // Using a transient anchor keeps the SPA page intact (no full navigation away).
  const a = document.createElement("a");
  a.href = api.resultDownloadURL(sessionId);
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Clear the transient status shortly after (the browser owns the actual transfer).
  window.setTimeout(() => {
    if (actionStatusEl.textContent === COPY.preparingDownload) setActionStatus("");
  }, 1500);
}

// ---- Clear-all confirm dialog ------------------------------------------------------
function openClearConfirm() {
  if (pageList(currentPage).length === 0) return;
  clearConfirm.hidden = false;
  clearConfirmBtn.focus();
}

function closeClearConfirm() {
  clearConfirm.hidden = true;
}

// ---- Page-change / zoom subscription (from viewer.js) ------------------------------
function onPageChanged(detail) {
  currentPage = detail.index;
  // Record this page's image dimensions for the projection (fetched lazily; see ensureDims).
  ensureDims(currentPage);
  // Cancel any in-progress draw when paging.
  if (dragStart) cleanupDrag({});
  // Paging while viewing the result: re-fetch the correct page's after-image; else show original.
  if (viewMode === "result" && resultFresh) {
    showResultImage(api.resultImageURL(sessionId, currentPage));
    if (overlay) overlay.hidden = true;
  } else if (viewMode === "result" && !resultFresh) {
    setViewMode("original");
  }
  renderList();
  renderOverlay();
  updateActionGroup();
}

function onPageZoomed() {
  // Source of truth (image-px rects) is unchanged — only reproject to the new displayed box.
  renderOverlay();
}

// Lazily fetch + cache a page's image dimensions for the projection denominator.
async function ensureDims(index) {
  if (imageDimsByPage.has(index) || sessionId === null) return;
  try {
    const meta = await api.pageMeta(sessionId, index);
    // Record the EFFECTIVE per-page DPI alongside the dims (CR-01): img_w/img_h are already
    // measured at meta.dpi, which may be < the requested 200 for a large page.
    imageDimsByPage.set(index, { imgW: meta.img_w, imgH: meta.img_h, dpi: meta.dpi });
    if (index === currentPage) renderOverlay();
  } catch {
    /* /meta failed — projection() falls back to the image's natural pixels. */
  }
}

// ---- Public API (called by app.js) -------------------------------------------------
// app.js passes { session_id, page_count }; page_count is intentionally unused here (paging is
// viewer.js's concern — WR-04), so we only read session_id.
export function initRegions({ session_id }) {
  sessionId = session_id;
  currentPage = 0;
  regionsByPage.clear();
  imageDimsByPage.clear();
  nextRegionId = 1;
  resultFresh = false;
  applying = false;
  viewMode = "original";

  ensureOverlay();
  overlay.hidden = false;

  // Reset toggle to 原圖.
  viewOriginalBtn.classList.add("is-selected");
  viewOriginalBtn.setAttribute("aria-pressed", "true");
  viewResultBtn.classList.remove("is-selected");
  viewResultBtn.setAttribute("aria-pressed", "false");

  hideNotice();
  setActionStatus("");
  ensureDims(0);
  renderList();
  renderOverlay();
  updateActionGroup();
}

export function resetRegions() {
  sessionId = null;
  currentPage = 0;
  regionsByPage.clear();
  imageDimsByPage.clear();
  resultFresh = false;
  applying = false;
  viewMode = "original";

  if (overlay) {
    overlay.replaceChildren();
    overlay.hidden = true;
  }
  hideNotice();
  setActionStatus("");
}

/** The flat job payload for the server: [{ page, px_rect:[x0,y0,x1,y1] }] across ALL pages. */
export function getJobRegions() {
  const out = [];
  for (const [page, list] of regionsByPage.entries()) {
    for (const region of list) {
      out.push({ page, px_rect: region.pxRect });
    }
  }
  return out;
}

/** Total region count across all pages (used by the action group + count indicator). */
export function getTotalRegionCount() {
  return totalRegionCount();
}

// ---- Wiring (idempotent at module load) --------------------------------------------
stage.addEventListener("page:changed", (e) => onPageChanged(e.detail));
stage.addEventListener("page:zoomed", () => onPageZoomed());

clearAllBtn.addEventListener("click", openClearConfirm);
clearCancelBtn.addEventListener("click", closeClearConfirm);
clearConfirmScrim.addEventListener("click", closeClearConfirm);
clearConfirmBtn.addEventListener("click", () => {
  closeClearConfirm();
  clearAllCurrentPage();
});

viewOriginalBtn.addEventListener("click", () => setViewMode("original"));
viewResultBtn.addEventListener("click", () => setViewMode("result"));

applyBtn.addEventListener("click", applyRemoval);
downloadBtn.addEventListener("click", downloadResult);

// Keyboard: Escape cancels an in-progress drag OR closes the confirm dialog. Delete/Backspace
// while a region rectangle/row is focused is handled per-row; the stage-level handler avoids
// hijacking the jump input / buttons (viewer.js owns arrow/+/- there).
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (dragStart) {
      cancelDraw(e);
    } else if (!clearConfirm.hidden) {
      closeClearConfirm();
    }
  }
});
