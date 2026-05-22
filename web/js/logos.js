/*
 * logos.js — the side-panel logo picker (Phase 3, D-05 / LOGO-01).
 *
 * A single-select thumbnail grid of the fixed logo library. Mirrors regions.js end-to-end:
 *   - a verbatim 繁中 COPY object (UI-SPEC §Copywriting);
 *   - createElement-ONLY DOM building (no HTML-string injection — XSS guard T-03-04 / T-02-11);
 *   - single-select state by dataset comparison (mirrors setActiveRegion — NOT a CSS-selector
 *     string built from the id, WR-03);
 *   - public initLogos/resetLogos exports wired by app.js.
 *
 * api.js is the SOLE server seam: this module calls api.listLogos() / api.logoImageURL() and
 * NEVER fetches or builds a server URL itself (embedding contract, T-02-12).
 *
 * A logo selection/clear is a job-input change, so it reuses the ONE shared stale machine via
 * regions.notifyJobInputChanged() — it does NOT fork the action-group state machine (Pitfall 5).
 */

import * as api from "./api.js";
import { notifyJobInputChanged } from "./regions.js";

// Internal sentinel for the "自動(依框選形狀)" choice — NOT a real manifest id. In auto mode the
// backend ignores logo_id and picks per-region by aspect (auto_logo flag), so getSelectedLogoId()
// returns null and isAutoLogo() returns true.
const AUTO = "__auto__";

// ---- Verbatim SPEC copy (繁體中文) -------------------------------------------------
const COPY = {
  heading: "我司商標",
  subtext: "選擇要置入移除區域的商標(套用後置入所有框選區域)",
  selectAria: (name) => `選擇商標:${name}`,
  noLogo: "不置入商標",
  auto: "自動(依框選形狀)",
  emptyHeading: "尚無可用的商標",
  emptyBody:
    "商標庫目前是空的。您仍可框選並移除供應商商標,完成後下載。商標由管理者預先放入。",
  loading: "正在載入商標庫…",
  loadFailed: "無法載入商標庫,請重新整理後再試一次。",
  staleNotice: "所選商標已變更,請重新套用以更新結果",
};

// ---- DOM refs ----------------------------------------------------------------------
const grid = document.getElementById("logo-grid");
const emptyEl = document.getElementById("logo-empty");
const emptyHeadingEl = document.getElementById("logo-empty-heading");
const emptyBodyEl = document.getElementById("logo-empty-body");
const loadingEl = document.getElementById("logo-loading");
const loadingTextEl = document.getElementById("logo-loading-text");
const noticeEl = document.getElementById("logo-notice");
const noticeBodyEl = document.getElementById("logo-notice-body");
const noticeRetryEl = document.getElementById("logo-notice-retry");

// ---- State -------------------------------------------------------------------------
// The single client-side selection (D-01: one global logo). null = pure removal.
let selectedLogoId = null;
let sessionId = null;

// ---- View helpers (mutually-exclusive states) --------------------------------------
function showState(name) {
  loadingEl.hidden = name !== "loading";
  grid.hidden = name !== "populated";
  emptyEl.hidden = name !== "empty";
  noticeEl.hidden = name !== "failed";
}

function setLoading() {
  loadingTextEl.textContent = COPY.loading;
  showState("loading");
}

function setEmpty() {
  emptyHeadingEl.textContent = COPY.emptyHeading;
  emptyBodyEl.textContent = COPY.emptyBody;
  showState("empty");
}

function setFailed() {
  noticeBodyEl.textContent = COPY.loadFailed;
  showState("failed");
}

// ---- Selection (single-select by dataset comparison; mirrors setActiveRegion) -------
function applySelection() {
  // Mark exactly the matching cell selected; clear the rest. Compare dataset values rather
  // than building a CSS selector from the (untrusted-ish) id (WR-03).
  for (const cell of grid.children) {
    const isSel = cell.dataset.logoId === (selectedLogoId ?? "");
    cell.classList.toggle("is-selected", isSel);
    cell.setAttribute("aria-pressed", isSel ? "true" : "false");
  }
}

function selectLogo(logoId) {
  // logoId === null means the explicit "不置入商標" clear cell.
  selectedLogoId = logoId;
  applySelection();
  // A logo change is a job-input change -> reuse the ONE shared stale machine (Pitfall 5).
  notifyJobInputChanged(COPY.staleNotice);
}

// ---- Grid building (createElement ONLY — no HTML-string injection) ------------------
function makeThumbCell(id, name) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "logo-thumb";
  btn.dataset.logoId = id ?? ""; // "" marks the clear cell
  btn.setAttribute("aria-pressed", "false");

  if (id === null) {
    // The "不置入商標" clear cell: a neutral caption, no image.
    btn.setAttribute("aria-label", COPY.noLogo);
    const caption = document.createElement("span");
    caption.className = "logo-thumb__caption";
    caption.textContent = COPY.noLogo;
    btn.appendChild(caption);
  } else if (id === AUTO) {
    // The "自動(依框選形狀)" cell: caption-only, no single preview image.
    btn.setAttribute("aria-label", COPY.auto);
    const caption = document.createElement("span");
    caption.className = "logo-thumb__caption";
    caption.textContent = COPY.auto;
    btn.appendChild(caption);
  } else {
    btn.setAttribute("aria-label", COPY.selectAria(name));
    const img = document.createElement("img");
    img.className = "logo-thumb__img";
    img.src = api.logoImageURL(id); // api.js is the sole seam
    img.alt = ""; // the button's aria-label carries the name (no redundant alt)
    const caption = document.createElement("span");
    caption.className = "logo-thumb__caption";
    caption.textContent = name; // verbatim manifest text via textContent (T-03-04)
    btn.append(img, caption);
  }

  btn.addEventListener("click", () => selectLogo(id));
  return btn;
}

function renderGrid(logos) {
  grid.replaceChildren();
  // Lead with the explicit clear choice, then the auto-by-shape choice, then the logos.
  grid.appendChild(makeThumbCell(null, COPY.noLogo));
  grid.appendChild(makeThumbCell(AUTO, COPY.auto));
  for (const entry of logos) {
    grid.appendChild(makeThumbCell(entry.id, entry.name));
  }
  applySelection();
  showState("populated");
}

// ---- Catalog load ------------------------------------------------------------------
async function loadCatalog() {
  setLoading();
  try {
    const data = await api.listLogos();
    const logos = (data && Array.isArray(data.logos)) ? data.logos : [];
    if (logos.length === 0) {
      setEmpty();
    } else {
      renderGrid(logos);
    }
  } catch {
    // Non-blocking: the flow still allows pure removal. Never surface raw server text.
    setFailed();
  }
}

// ---- Public API (called by app.js) -------------------------------------------------
export function initLogos({ session_id } = {}) {
  sessionId = session_id ?? null;
  selectedLogoId = null;
  loadCatalog();
}

export function resetLogos() {
  sessionId = null;
  selectedLogoId = null;
  grid.replaceChildren();
  showState("loading");
  loadingEl.hidden = true; // fully hidden on reset
}

/** The current global logo selection (consumed by the /process payload). null = pure removal OR auto. */
export function getSelectedLogoId() {
  return selectedLogoId === AUTO ? null : selectedLogoId;
}

/** True when the "自動(依框選形狀)" choice is active — the backend picks per-region by aspect. */
export function isAutoLogo() {
  return selectedLogoId === AUTO;
}

// ---- Wiring (idempotent at module load) --------------------------------------------
noticeRetryEl.addEventListener("click", () => loadCatalog());
