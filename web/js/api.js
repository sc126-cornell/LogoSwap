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
 *                                                  too_many_pages | corrupt_pdf | empty_file
 *   GET  /sessions/{id}                     -> 200 { session_id, page_count, filename } | 404
 *   GET  /sessions/{id}/pages/{n}/image     -> 200 image/png  (n is 0-based; dpi optional, server default 200)
 *   GET  /sessions/{id}/pages/{n}/meta      -> 200 { page_no, page_w_pt, page_h_pt, rotation, dpi, img_w, img_h }
 *
 * The image endpoint is a plain URL — set it as an <img> src. The browser never parses the PDF
 * (server-authoritative render; PDF.js is forbidden per SKELETON.md).
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
export function pageImageURL(id, n, dpi) {
  let url =
    API_BASE +
    "/sessions/" +
    encodeURIComponent(id) +
    "/pages/" +
    encodeURIComponent(n) +
    "/image";
  if (dpi !== undefined && dpi !== null) {
    url += "?dpi=" + encodeURIComponent(dpi);
  }
  return url;
}

/** Fetch render metadata for a page (used to size the page stage to the true render box). */
export async function pageMeta(id, n) {
  const response = await fetch(
    API_BASE +
      "/sessions/" +
      encodeURIComponent(id) +
      "/pages/" +
      encodeURIComponent(n) +
      "/meta"
  );
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json();
}
