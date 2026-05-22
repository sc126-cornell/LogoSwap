/*
 * theme.js — light/dark theme controller (pure front-end; NO server calls, does not import api.js).
 *
 * Behavior (D-06): the initial theme follows prefers-color-scheme; the user's EXPLICIT choice is
 * persisted to localStorage and survives reload. index.html runs a tiny inline copy of the resolve
 * step before first paint to avoid a flash of the wrong theme; this module then owns the toggle,
 * persistence, and following the OS while no explicit choice exists.
 *
 * Security (T-01-16): the persisted value is treated as a strict "light"/"dark" enum — any other
 * value (tampered/garbage) falls back to the prefers-color-scheme default. The theme is applied
 * via setAttribute('data-theme', ...) / removeAttribute, NEVER written into innerHTML, so a
 * tampered localStorage entry cannot inject markup or arbitrary attributes.
 */

const STORAGE_KEY = "pdftool-theme";
const root = document.documentElement;

const isValidTheme = (value) => value === "light" || value === "dark";

function storedTheme() {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isValidTheme(value) ? value : null;
  } catch {
    return null; // localStorage unavailable (private mode quotas, etc.) — treat as no choice.
  }
}

function osPrefersDark() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

/**
 * Resolve the initial theme: an explicit stored "light"/"dark" wins; otherwise follow the OS
 * preference. The implicit OS default is NOT persisted — only an explicit user toggle is stored.
 */
export function resolveInitialTheme() {
  const stored = storedTheme();
  if (stored) return stored;
  return osPrefersDark() ? "dark" : "light";
}

/** Apply a theme: light = absence of the attribute (so :root light tokens apply); dark sets it. */
export function applyTheme(theme) {
  const normalized = isValidTheme(theme) ? theme : "light";
  if (normalized === "dark") {
    root.setAttribute("data-theme", "dark");
  } else {
    root.removeAttribute("data-theme");
  }
  reflectToggleState(normalized);
}

function currentTheme() {
  return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function persist(theme) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* persistence is best-effort; the toggle still works for this session. */
  }
}

/** Flip current<->other, apply, and persist the explicit choice. */
export function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  applyTheme(next);
  persist(next);
  return next;
}

// Reflect state on the toggle button (aria-pressed = true when dark; icon visibility is CSS-driven).
function reflectToggleState(theme) {
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  }
}

/** Wire the toggle and (optionally) follow the OS while the user has made no explicit choice. */
export function init() {
  // Re-apply on load (the inline head script set the attribute; this syncs aria-pressed and
  // covers the case where the inline script was unavailable).
  applyTheme(resolveInitialTheme());

  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.addEventListener("click", () => toggleTheme());
  }

  // Follow the OS only while no explicit choice is stored.
  if (typeof window.matchMedia === "function") {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e) => {
      if (!storedTheme()) {
        applyTheme(e.matches ? "dark" : "light");
      }
    };
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onChange);
    } else if (typeof mq.addListener === "function") {
      mq.addListener(onChange); // older Safari
    }
  }
}

// Run immediately on module load.
init();
