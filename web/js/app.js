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

// ---- Verbatim SPEC copy (繁體中文) -------------------------------------------------
const COPY = {
  uploading: "正在上傳檔案…",
  processing: "正在處理檔案,準備預覽…",
  errorHeading: "無法開啟此檔案",
  unsupportedType: "此檔案格式不支援。請改用 PDF 檔案後再試一次。",
  corruptPdf: "這個 PDF 檔案無法讀取,可能已損毀。請確認檔案後再試一次。",
  // {limit} is the numeric token extracted from the server message (e.g. "50 MB").
  // Degrade gracefully when no limit could be parsed: omit the parenthetical rather
  // than rendering an empty "()" or leaking the raw server string (WR-02 / T-01-14).
  fileTooLarge: (limit) =>
    limit
      ? `檔案超過大小上限(${limit})。請改用較小的檔案。`
      : "檔案超過大小上限。請改用較小的檔案。",
  networkFailure: "上傳失敗,請檢查網路連線後再試一次。",
  confirmReplace: "更換檔案會清除目前的預覽,確定要繼續嗎?",
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

// Track whether a document is currently loaded (gates the soft-confirm on replace).
let hasLoadedDoc = false;

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

// ---- Error mapping -----------------------------------------------------------------
// Pull ONLY a numeric limit token (e.g. "50 MB" or "30 頁") out of the server message.
// On no-match, fall back to "" — NEVER the raw server string (WR-02 / T-01-14): the
// caller's COPY.fileTooLarge("") omits the parenthetical, so a server-wording change can
// no longer surface raw backend text in user-facing copy.
function extractLimit(serverMessage) {
  if (!serverMessage) return "";
  const m = serverMessage.match(/(\d[\d.,]*\s*(?:MB|GB|KB|頁|pages?))/i);
  return m ? m[1].trim() : "";
}

function messageForError(err) {
  const code = err && err.code ? err.code : "unknown";
  switch (code) {
    case "unsupported_type":
      return COPY.unsupportedType;
    case "corrupt_pdf":
      return COPY.corruptPdf;
    case "file_too_large":
    case "too_many_pages":
      return COPY.fileTooLarge(extractLimit(err && err.serverMessage));
    case "empty_file":
      // Empty file is a bad/unsupported input from the user's view.
      return COPY.unsupportedType;
    default:
      // Network/transport failures (fetch rejected) and any unmapped server code.
      return COPY.networkFailure;
  }
}

function showError(err) {
  // textContent only — never inject server/error text as HTML (T-01-14 / T-01-15).
  errorBody.textContent = messageForError(err);
  showState("error");
}

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
    showState("loaded");

    // Hand off to the viewer (Task 3). It renders page 0 and wires nav/zoom.
    await initViewer({
      session_id: session.session_id,
      page_count: session.page_count,
    });
  } catch (err) {
    hasLoadedDoc = false;
    setDocControlsEnabled(false);
    resetViewer();
    showError(err);
  } finally {
    // Allow re-choosing the same file (change event won't fire twice otherwise).
    fileInput.value = "";
  }
}

// Open the native file picker, optionally guarding when a doc is already loaded.
function openPicker() {
  if (hasLoadedDoc && !window.confirm(COPY.confirmReplace)) {
    return;
  }
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
  if (hasLoadedDoc && !window.confirm(COPY.confirmReplace)) return;
  handleFile(file);
});

// ---- Initial state -----------------------------------------------------------------
setDocControlsEnabled(false);
showState("empty");
