/*
 * api.js — the ONLY module that contacts the server (the embedding seam, ARCHITECTURE Pattern 4).
 *
 * The server origin/base path is configurable via window.PDFTOOL_API_BASE so the colleague's
 * approval site can iframe the static UI or mount it under a prefix (e.g. "/pdf-logo") without
 * touching any other file. No other web/js module may hardcode a server URL.
 *
 * Backend contract consumed (authored by Plan 01-01):
 *   POST /sessions                         (multipart "file") -> 201 { session_id, page_count, filename }
 *     errors -> 4xx { detail: { code, message } }  code in: unsupported_type | file_too_large |
 *                                                  too_many_pages | corrupt_pdf | empty_file |
 *                                                  unsupported_image_format | multi_page_tiff_unsupported |
 *                                                  corrupt_image  (last three added in Phase 4, UPLOAD-03)
 *   GET  /sessions/{id}                     -> 200 { session_id, page_count, filename } | 404
 *   GET  /sessions/{id}/pages/{n}/image     -> 200 image/png  (n is 0-based; dpi optional, server default 200)
 *   GET  /sessions/{id}/pages/{n}/meta      -> 200 { page_no, page_w_pt, page_h_pt, rotation, dpi, img_w, img_h }
 *
 * Phase 2 contract consumed (authored by Plan 02-02 — see 02-02-SUMMARY):
 *   POST /sessions/{id}/process             body { dpi, regions:[{ page, px_rect:[x0,y0,x1,y1] }] }
 *                                            -> 200 { output_filename, page_count, regions:[{ page, removed, clamped }] }
 *     errors -> 4xx { detail: { code, message } }  code in: session_not_found | invalid_request |
 *                                                  page_out_of_range | residual_content
 *   GET  /sessions/{id}/result/pages/{n}/image  -> 200 image/png (the 移除結果 after-image; same six X- headers)
 *   GET  /sessions/{id}/result                  -> 200 application/pdf attachment (原名_logoswap.pdf);
 *                                                  404 result_not_ready before any /process run
 *
 * Phase 3 contract consumed (authored by Plan 03-01):
 *   GET  /logos                             -> 200 { logos:[{ id, name, tags }] } (no fs paths);
 *                                              empty/absent library -> { logos: [] } (picker empty-state)
 *   GET  /logos/{id}/image                  -> 200 image/png (the picker thumbnail src; CSS-scaled);
 *                                              crafted/unknown id -> 404 { detail:{ code:"logo_not_found" } }
 *   POST /sessions/{id}/process             gains an OPTIONAL global logo_id (D-01; added by Plan 03-02):
 *                                              body { dpi, regions, logo_id? } — logo_id null/omitted = pure removal
 *
 * The image/result endpoints are plain URLs — set them as an <img> src / anchor href. The browser
 * never parses the PDF (server-authoritative render; PDF.js is forbidden per SKELETON.md).
 */

// Configurable base; empty string => same-origin (the FastAPI static mount serves us at /).
export const API_BASE =
  (typeof window !== "undefined" && window.PDFTOOL_API_BASE) || "";

/**
 * Error thrown for non-2xx server responses. Carries the server's structured detail.code AND
 * detail.message so callers can map to fixed UI copy and surface the {limit} value verbatim.
 */
export class ApiError extends Error {
  constructor(code, message, status) {
    super(message || code || "api_error");
    this.name = "ApiError";
    this.code = code || "unknown";
    this.serverMessage = message || "";
    this.status = status;
  }
}

// Parse a 4xx/5xx body into an ApiError. Tolerates non-JSON bodies (e.g. a proxy 502).
async function toApiError(response) {
  let code = "unknown";
  let message = "";
  try {
    const body = await response.json();
    if (body && body.detail && typeof body.detail === "object") {
      code = body.detail.code || code;
      message = body.detail.message || "";
    }
  } catch {
    // Non-JSON error body — leave defaults; caller maps "unknown" to the generic copy.
  }
  return new ApiError(code, message, response.status);
}

/**
 * Upload a single file. Resolves to { session_id, page_count, filename }.
 * Throws ApiError (carrying detail.code + detail.message) on a non-2xx response, or a plain
 * Error on a network/transport failure (fetch rejects) so the caller maps it to the network copy.
 */
export async function createSession(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(API_BASE + "/sessions", {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json();
}

/** Look up an existing session: { session_id, page_count, filename }. */
export async function getSession(id) {
  const response = await fetch(API_BASE + "/sessions/" + encodeURIComponent(id));
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json();
}

/**
 * Build the page-image URL (0-based n). Returns a string to set as an <img> src.
 * dpi is OPTIONAL — omit it to use the server default (200). Per D-02, zoom CSS-scales this
 * already-fetched PNG; callers MUST NOT pass a per-zoom dpi here.
 */
export function pageImageURL(id, n, dpi, rotate) {
  let url =
    API_BASE +
    "/sessions/" +
    encodeURIComponent(id) +
    "/pages/" +
    encodeURIComponent(n) +
    "/image";
  const params = [];
  if (dpi !== undefined && dpi !== null) {
    params.push("dpi=" + encodeURIComponent(dpi));
  }
  // rotate is the user's TRANSIENT rotation degrees (0/90/180/270) added to the page's
  // intrinsic /Rotate for this render only; omit (or 0) => no user rotation.
  if (rotate) {
    params.push("rotate=" + encodeURIComponent(rotate));
  }
  if (params.length) url += "?" + params.join("&");
  return url;
}

/**
 * Fetch render metadata for a page (used to size the page stage to the true render box).
 * Optional `rotate` (0/90/180/270) returns dims + rotation in the rotated orientation so the
 * overlay measures px against the rotated image (img_w/img_h swap for a quarter turn).
 */
export async function pageMeta(id, n, rotate) {
  let url =
    API_BASE +
    "/sessions/" +
    encodeURIComponent(id) +
    "/pages/" +
    encodeURIComponent(n) +
    "/meta";
  if (rotate) url += "?rotate=" + encodeURIComponent(rotate);
  const response = await fetch(url);
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json();
}

// ---- Phase 2 seam: process (true removal on the work copy) + result render + download --------

/**
 * Apply removal on the work copy (deferred-mutation, D-05). POSTs the job spec
 * { dpi, regions:[{ page, px_rect:[x0,y0,x1,y1] }] } to /process and resolves to
 * { output_filename, page_count, regions:[{ page, removed, clamped }] }.
 *
 * Throws ApiError (carrying detail.code + detail.message) on a non-2xx response, exactly like
 * createSession, so the caller maps the code to fixed UI copy and never surfaces a raw server
 * message as HTML (T-02-11). A network/transport failure rejects with a plain Error.
 */
export async function processJob(id, jobSpec) {
  const response = await fetch(
    API_BASE + "/sessions/" + encodeURIComponent(id) + "/process",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(jobSpec),
    }
  );
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json();
}

/**
 * Build the result (移除結果) page-image URL (0-based n) — the server's render of the redacted
 * work copy. Returns a string to set as an <img> src. Carries the same six X- headers as the
 * original page image, so the overlay maths is identical (D-04 before/after toggle).
 */
export function resultImageURL(id, n, v, rotate) {
  let url =
    API_BASE +
    "/sessions/" +
    encodeURIComponent(id) +
    "/result/pages/" +
    encodeURIComponent(n) +
    "/image";
  const params = [];
  // WR-01: an optional cache-busting token. The result endpoint URL is otherwise identical
  // across re-applies, so the browser may serve a STALE after-image from a prior apply even
  // though the work copy on disk was freshly re-redacted. Bumping ?v= each apply forces a fresh
  // fetch so the before/after preview always matches the file the user is about to download.
  if (v !== undefined && v !== null) {
    params.push("v=" + encodeURIComponent(v));
  }
  // rotate is applied transiently (symmetric with pageImageURL) so the after-image shows the
  // same rotated orientation the user framed on; the work copy stays at intrinsic rotation.
  if (rotate) {
    params.push("rotate=" + encodeURIComponent(rotate));
  }
  if (params.length) url += "?" + params.join("&");
  return url;
}

/**
 * Build the result-download URL (the exported 原名_logoswap.pdf attachment). Returns a string to
 * navigate to / set as an anchor href; the browser handles the attachment + filename* (OUTPUT-01).
 */
export function resultDownloadURL(id) {
  return API_BASE + "/sessions/" + encodeURIComponent(id) + "/result";
}

// ---- Phase 3 seam: fixed logo library (LOGO-01) ------------------------------------------

/**
 * List the fixed logo library: resolves to { logos: [{ id, name, tags }] }. An empty/absent
 * library returns { logos: [] } (the picker shows an empty state — not an error). Throws
 * ApiError on a non-2xx response so the caller maps it to fixed copy (never raw server text).
 */
export async function listLogos() {
  const response = await fetch(API_BASE + "/logos");
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json();
}

/**
 * Build a logo-image URL (the picker thumbnail src), mirroring pageImageURL. Returns a string
 * to set as an <img> src; the server resolves the id through the manifest allowlist (a crafted
 * id is a plain 404, never a path read).
 */
export function logoImageURL(id) {
  return API_BASE + "/logos/" + encodeURIComponent(id) + "/image";
}
