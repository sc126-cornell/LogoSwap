/*
 * app.js — upload flow + stage state machine (empty | uploading | loaded | error).
 *
 * Exactly one stage state is visible at a time. On file choose/drop we call api.createSession;
 * on success we hand off to viewer.initViewer({ session_id, page_count }); on failure we map the
 * server's detail.code to the EXACT Traditional-Chinese SPEC copy (injecting only the numeric
 * {limit} from the server message) and render the inline error block with a 重試 action.
 *
 * Security: all dynamic strings are written via textContent (never innerHTML), so a filename or
 * server message can never inject markup (T-01-14 / T-01-15). api.js is the only server seam.
 */

import * as api from "./api.js";
import { initViewer, resetViewer } from "./viewer.js";
import { initRegions, resetRegions } from "./regions.js";
import { initLogos, resetLogos } from "./logos.js";

// ---- Verbatim SPEC copy (繁體中文) -------------------------------------------------
const COPY = {
  uploading: "正在上傳檔案…",
  processing: "正在處理檔案,準備預覽…",
  errorHeading: "無法開啟此檔案",
  // Phase 4 D-11 / UI-SPEC update: dropzone now accepts PDF + PNG/JPG/TIFF, so
  // the "next step" copy mirrors the dropzone hint instead of saying "改用 PDF".
  unsupportedType:
    "此檔案格式不支援。請改用 PDF、PNG、JPG 或 TIFF 檔案後再試一次。",
  corruptPdf: "這個 PDF 檔案無法讀取,可能已損毀。請確認檔案後再試一次。",
  // {limit} is the numeric token extracted from the server message (e.g. "50 MB").
  // Degrade gracefully when no limit could be parsed: omit the parenthetical rather
  // than rendering an empty "()" or leaking the raw server string (WR-02 / T-01-14).
  fileTooLarge: (limit) =>
    limit
      ? `檔案超過大小上限(${limit})。請改用較小的檔案。`
      : "檔案超過大小上限。請改用較小的檔案。",
  networkFailure: "上傳失敗,請檢查網路連線後再試一次。",
  // Phase 4 — three new ingest error codes (UI-SPEC 04 Inline error block table).
  // Family-consistent with unsupportedType / corruptPdf: "問題描述 + 下一步".
  unsupportedImageFormat:
    "此影像格式不支援。請改用 PDF、PNG、JPG 或 TIFF 檔案後再試一次。",
  multiPageTiffUnsupported:
    "暫不支援多頁 TIFF。請先將 TIFF 拆成單頁後再上傳。",
  corruptImage:
    "這個影像檔案無法讀取,可能已損毀。請確認檔案後再試一次。",
  // Phase 4 hotfix WR-03: DoS-class pixel-count cap. The server message carries
  // the configured pixel limit (e.g. "89,478,485 像素"); we extract it via
  // extractLimit() and inject it into the parenthetical here, just like
  // fileTooLarge does for size/page limits.
  imageTooLargePixels: (limit) =>
    limit
      ? `影像像素數過多(超過 ${limit})。請先縮圖再上傳。`
      : "影像像素數過多。請先縮圖再上傳。",
  // Phase 5 Plan 05-02 — three new server error codes from the integrity + timeout
  // layer. Wording matches the server-side message literals (Traditional Chinese, no
  // technical jargon, leads with "問題描述" and ends with the user-actionable "下一步").
  originalTampered:
    "系統偵測到原始檔異常,此工作階段已停用,請重新上傳此檔。",
  sessionCorrupted:
    "此工作階段已過期或無法使用,請重新上傳檔案。",
  processingTimeout:
    "處理逾時,請改用較小檔案或減少框選區域數量後再試一次。",
  // Phase 5 Plan 05-02 D-B2 — session TTL UI hint + 404 expired friendly message.
  // Static literals (no {limit} injection) inserted into a polite live-region node
  // created via createElement + textContent (XSS-safe — no innerHTML).
  sessionTtlHint:
    "此次處理 1 小時內完成下載 — 逾時需重新上傳。",
  sessionExpired:
    "此次處理已過期,請重新上傳此檔。",
};

// ---- DOM refs ---------------------------------------------------------------------
const stage = document.getElementById("page-stage");
const states = {
  empty: stage.querySelector('[data-state="empty"]'),
  uploading: stage.querySelector('[data-state="uploading"]'),
  loaded: stage.querySelector('[data-state="loaded"]'),
  error: stage.querySelector('[data-state="error"]'),
};
const fileInput = document.getElementById("file-input");
const chooseBtn = document.getElementById("choose-file");
const dropzone = document.getElementById("dropzone");
const uploadingText = document.getElementById("uploading-text");
const errorBody = document.getElementById("error-body");
const errorRetry = document.getElementById("error-retry");
const replaceBtn = document.getElementById("replace-file");
const docControls = Array.from(document.querySelectorAll("[data-doc-control]"));
const mainEl = document.querySelector("main.main");
const sidePanelEl = document.getElementById("side-panel");

// Track whether a document is currently loaded (gates the soft-confirm on replace).
let hasLoadedDoc = false;

// Phase 5 Plan 05-02 D-B2 — session TTL UI hint node. Created lazily (once) and reused
// across uploads. WR-07: inserted as a sibling of <main> inside .app-shell (between
// <main> and <footer>) — NOT inside <main>. The <main> element is itself a 2-column
// grid (stage 1fr + side-panel); injecting the hint there created a third grid cell
// that misaligned the side-panel once .main--paneled engaged. The .app-shell row grid
// is widened to accommodate the hint as its own row (auto 1fr auto auto).
// aria-live="polite" announces text changes to screen readers without interrupting
// other live regions. Strictly textContent — never innerHTML (T-01-14).
let sessionHintEl = null;

function ensureSessionHintEl() {
  if (sessionHintEl) return sessionHintEl;
  const el = document.createElement("p");
  el.className = "app-session-hint";
  el.setAttribute("aria-live", "polite");
  el.setAttribute("role", "status");
  el.hidden = true;
  // Insert as a sibling of <main> inside .app-shell, placed before the footer so the
  // shell row order stays: toolbar | main | hint | footer. Falls back to appending to
  // .app-shell when no footer is present (defensive); ultimately to body if the shell
  // is somehow absent (should not happen — index.html always has it).
  const shell = document.querySelector(".app-shell");
  const footerEl = shell ? shell.querySelector(".app-footer") : null;
  if (shell && footerEl) {
    shell.insertBefore(el, footerEl);
  } else if (shell) {
    shell.appendChild(el);
  } else {
    document.body.appendChild(el);
  }
  sessionHintEl = el;
  return el;
}

function showSessionTtlHint() {
  const el = ensureSessionHintEl();
  el.textContent = COPY.sessionTtlHint;
  el.hidden = false;
}

function showSessionExpired() {
  const el = ensureSessionHintEl();
  el.textContent = COPY.sessionExpired;
  el.hidden = false;
}

function hideSessionHint() {
  if (sessionHintEl) sessionHintEl.hidden = true;
}

// ---- State machine ----------------------------------------------------------------
function showState(name) {
  for (const [key, el] of Object.entries(states)) {
    if (!el) continue;
    el.hidden = key !== name;
  }
}

// Enable/disable the doc-dependent toolbar clusters (page-nav + zoom). The theme toggle is
// independent and always usable. We reveal the clusters once a doc loads and toggle a
// disabled-look via aria-disabled (CSS dims + blocks pointer events); viewer.js manages the
// per-control disabled attributes for nav boundaries.
function setDocControlsEnabled(enabled) {
  for (const group of docControls) {
    group.hidden = !enabled;
    group.setAttribute("aria-disabled", enabled ? "false" : "true");
  }
  replaceBtn.hidden = !enabled;
}

// Phase 2: expand the reserved side-panel to --side-panel-width when a doc is loaded (region UI
// is active only in the `loaded` state); collapse it back to 0 otherwise. Driven by a class on
// the shell so the CSS grid does the layout (no inline width math here).
function setSidePanelExpanded(expanded) {
  if (mainEl) mainEl.classList.toggle("main--paneled", expanded);
  if (sidePanelEl) sidePanelEl.setAttribute("aria-hidden", expanded ? "false" : "true");
}

// ---- Error mapping -----------------------------------------------------------------
// Pull ONLY a numeric limit token (e.g. "50 MB", "30 頁", "89,478,485 像素") out of the
// server message. On no-match, fall back to "" — NEVER the raw server string
// (WR-02 / T-01-14): the caller's COPY.fileTooLarge("") omits the parenthetical, so a
// server-wording change can no longer surface raw backend text in user-facing copy.
function extractLimit(serverMessage) {
  if (!serverMessage) return "";
  const m = serverMessage.match(/(\d[\d.,]*\s*(?:MB|GB|KB|頁|pages?|像素))/i);
  return m ? m[1].trim() : "";
}

function messageForError(err) {
  const code = err && err.code ? err.code : "unknown";
  switch (code) {
    case "unsupported_type":
      return COPY.unsupportedType;
    case "corrupt_pdf":
      return COPY.corruptPdf;
    // Phase 4 — three new image-ingest error codes (UI-SPEC 04). Grouped between
    // the PDF family (above) and the size/page family (below) so the switch reads
    // family-by-family.
    case "unsupported_image_format":
      return COPY.unsupportedImageFormat;
    case "multi_page_tiff_unsupported":
      return COPY.multiPageTiffUnsupported;
    case "corrupt_image":
      return COPY.corruptImage;
    // Phase 4 hotfix WR-03 — pixel-count DoS cap. Same "問題描述 + 下一步" family
    // as the size/page caps, but with a distinct piece of UX copy because the
    // remedy is different ("先縮圖", not "改用較小的檔案").
    case "image_too_large_pixels":
      return COPY.imageTooLargePixels(extractLimit(err && err.serverMessage));
    case "file_too_large":
    case "too_many_pages":
      return COPY.fileTooLarge(extractLimit(err && err.serverMessage));
    case "empty_file":
      // Empty file is a bad/unsupported input from the user's view.
      return COPY.unsupportedType;
    // Phase 5 Plan 05-02 — integrity + timeout family. ApiError.code surface from the
    // server's structured { detail: { code, message } } 4xx/5xx; the existing pathway
    // in api.js (toApiError) already extracts these. We map to fixed COPY strings so
    // the raw server message is never reflected as user-visible text (T-01-14 holdover).
    case "original_tampered":
      return COPY.originalTampered;
    case "session_corrupted":
      return COPY.sessionCorrupted;
    case "processing_timeout":
      return COPY.processingTimeout;
    default:
      // Network/transport failures (fetch rejected) and any unmapped server code.
      return COPY.networkFailure;
  }
}

function showError(err) {
  // textContent only — never inject server/error text as HTML (T-01-14 / T-01-15).
  errorBody.textContent = messageForError(err);
  // Phase 5 D-B2 友善訊息: a 404 on GET /sessions/{id} means the TTL janitor cleaned this
  // session — swap the loaded-time TTL hint for the explicit "expired" message so the
  // user understands re-upload is required. We detect via the ApiError shape that
  // api.js attaches: { status: 404, code: "session_not_found" }. Other 404s on different
  // endpoints (logos, pages) leave the hint alone.
  if (err && err.status === 404 && err.code === "session_not_found") {
    showSessionExpired();
  }
  showState("error");
}

// Public hook so other modules (regions.js / logos.js) can surface the expired-session
// message without duplicating the COPY string. Wired now (D-B2); modules subscribe in
// a future plan if needed — current acceptance is source-grep + DOM structure.
window.__logoSwapShowSessionExpired = showSessionExpired;

// ---- Upload flow -------------------------------------------------------------------
async function handleFile(file) {
  if (!file) return;

  showState("uploading");
  uploadingText.textContent = COPY.uploading;

  try {
    const session = await api.createSession(file);
    // Show processing copy while the viewer fetches the first page render.
    uploadingText.textContent = COPY.processing;

    hasLoadedDoc = true;
    setDocControlsEnabled(true);
    setSidePanelExpanded(true);
    showState("loaded");

    // Phase 5 D-B2: show the 1-hour TTL hint immediately after a successful upload so
    // the user knows to finish the round-trip within the window. Placed AFTER showState
    // ("loaded") so the hint never appears alongside an upload error.
    showSessionTtlHint();

    // Activate the Phase 2 region UI for this session (per-page model + overlay + action group).
    // Init regions BEFORE the first render so it's subscribed when viewer fires page:changed.
    initRegions({
      session_id: session.session_id,
      page_count: session.page_count,
    });

    // Activate the Phase 3 logo picker (fetches the catalog once via api.js). The library
    // is global / session-less (Phase 3 D-01), so initLogos takes no args. IN-02.
    initLogos();

    // Hand off to the viewer. It renders page 0 and wires nav/zoom (and fires page:changed,
    // which regions.js consumes to project the overlay onto the sized render box).
    await initViewer({
      session_id: session.session_id,
      page_count: session.page_count,
    });
  } catch (err) {
    hasLoadedDoc = false;
    setDocControlsEnabled(false);
    setSidePanelExpanded(false);
    resetRegions();
    resetLogos();
    resetViewer();
    showError(err);
  } finally {
    // Allow re-choosing the same file (change event won't fire twice otherwise).
    fileInput.value = "";
  }
}

// Open the native file picker directly. No extra confirmation on replace — the native dialog
// is itself cancellable, and the current preview is only replaced once a file is actually chosen
// (handleFile); cancelling the dialog leaves everything intact.
function openPicker() {
  fileInput.click();
}

// ---- Wiring ------------------------------------------------------------------------
chooseBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  openPicker();
});

// Clicking anywhere on the dropzone (the empty-state card) opens the picker.
dropzone.addEventListener("click", () => openPicker());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openPicker();
  }
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files && fileInput.files[0];
  handleFile(file);
});

replaceBtn.addEventListener("click", () => openPicker());

errorRetry.addEventListener("click", () => {
  // Retry returns to the empty state so the user can choose a file again.
  hasLoadedDoc = false;
  setDocControlsEnabled(false);
  setSidePanelExpanded(false);
  resetRegions();
  resetLogos();
  hideSessionHint();
  showState("empty");
});

// ---- Drag & drop -------------------------------------------------------------------
function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

["dragenter", "dragover", "dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, preventDefaults);
});

["dragenter", "dragover"].forEach((evt) => {
  dropzone.addEventListener(evt, () => dropzone.classList.add("is-dragover"));
});

["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, () => dropzone.classList.remove("is-dragover"));
});

dropzone.addEventListener("drop", (e) => {
  const dt = e.dataTransfer;
  const file = dt && dt.files && dt.files[0];
  if (!file) return;
  handleFile(file);
});

// ---- Initial state -----------------------------------------------------------------
setDocControlsEnabled(false);
showState("empty");
