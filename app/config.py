"""Module-level settings, read from the environment with safe defaults.

The limit constants here are the threat-model DoS parameters (T-01-01 upload size,
T-01-02 page count / pixel budget) AND the source of the ``{limit}`` value the
frontend "檔案過大" copy injects. They are pinned by phase decision D-04:
MAX_UPLOAD_BYTES = 50 MB, MAX_PAGES = 30; and D-02: DEFAULT_DPI = 200.

DPI is a *request parameter* exposed by the render endpoint; DEFAULT_DPI is only the
default used when the caller does not ask for one. MIN/MAX_DPI clamp the per-render
pixel budget (Pitfall 8) so a caller cannot request a multi-gigabyte pixmap.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Where the three-directory session layout lives (originals/ work/ outputs/).
DATA_DIR: Path = Path(os.environ.get("DATA_DIR", "./data")).resolve()

# Fixed read-only logo library (Phase 3). Defaults to a repo-relative ./logos; bake-in/mount
# in deploy (CLAUDE.md "read-only volume for the fixed logo library"). An absent dir yields an
# empty picker rather than an error (graceful degradation to pure removal, A2).
LOGOS_DIR: Path = Path(os.environ.get("LOGOS_DIR", "./logos")).resolve()

# Per-asset guard (T-03-02 / Pitfall 6): cap a library PNG's file size BEFORE Pillow decode so a
# crafted/oversized asset cannot inflate memory. A bad asset is skipped from the list, not fatal.
MAX_LOGO_BYTES: int = _env_int("MAX_LOGO_BYTES", 10 * 1024 * 1024)

# Render DPI policy (D-02: 200 DPI default for CAD line clarity).
DEFAULT_DPI: int = _env_int("DEFAULT_DPI", 200)
MIN_DPI: int = _env_int("MIN_DPI", 72)
MAX_DPI: int = _env_int("MAX_DPI", 300)

# Upload limits (D-04 — the DoS-mitigation parameters).
# 50 MB expressed exactly so the acceptance grep `50 * 1024 * 1024` resolves.
MAX_UPLOAD_BYTES: int = _env_int("MAX_UPLOAD_BYTES", 50 * 1024 * 1024)
MAX_PAGES: int = _env_int("MAX_PAGES", 30)

# Per-render pixel ceiling (WR-06). The DPI clamp alone does NOT bound memory: a single
# page can declare an enormous MediaBox, so even at MAX_DPI a pathological page would
# allocate a multi-hundred-MB pixmap (~ w_px * h_px * 4 bytes). When the projected pixel
# count exceeds this budget we scale the effective DPI DOWN to fit (graceful degradation)
# rather than refusing to render. 40 MP * 4 bytes ~= 160 MB upper bound per render.
MAX_RENDER_PIXELS: int = _env_int("MAX_RENDER_PIXELS", 40 * 1_000_000)

# Phase 4 ingest: Pillow decompression-bomb budget (89,478,485 px ≈ 89 MP). The default
# matches Pillow 12.x's built-in ``Image.MAX_IMAGE_PIXELS``; exposing it as an env-driven
# setting lets ops tune it without monkey-patching Pillow's global state at runtime. The
# value is intentionally HIGHER than MAX_RENDER_PIXELS (40 MP) because ingest does NOT
# expand pixels into a pixmap — it embeds the image as a stream inside an A4 PDF and the
# render layer's ``fit_dpi_to_pixel_budget`` later applies the render-side cap. This is
# the only Phase 4 image-specific ingest cap; size/page caps stay at the unified
# MAX_UPLOAD_BYTES / MAX_PAGES values (D-04).
MAX_INGEST_IMAGE_PIXELS: int = _env_int("MAX_INGEST_IMAGE_PIXELS", 89_478_485)

# Phase 4 image ingest: JPEG re-encode quality used when the Pillow chain re-emits a
# JPEG (e.g. after CMYK→RGB conversion or alpha flattening for a JPEG-sniffed upload).
# 90 = visually lossless ceiling — chosen because downstream uses may include printing
# or approval workflows. JPEG-sniffed bytes that need no conversion are passed through
# byte-exact and this constant has no effect on them.
JPEG_REENCODE_QUALITY: int = _env_int("JPEG_REENCODE_QUALITY", 90)

# Per-job region cap (Phase 2 DoS mitigation T-02-04). A /process JobSpec carrying an
# unbounded ``regions`` list could drive arbitrarily many redact/extract passes; reject
# over this cap with a 422 rather than doing the work. 200 is generous for manual framing.
MAX_REGIONS: int = _env_int("MAX_REGIONS", 200)

# Human-readable forms used inside limit-bearing error messages so the frontend can
# surface the {limit} value. Derived from the byte limit so they never drift.
MAX_UPLOAD_MB: int = MAX_UPLOAD_BYTES // (1024 * 1024)

API_TITLE: str = os.environ.get("API_TITLE", "PDF 商標替換工具 API")

# Phase 5: deployment / embedding (Plan 05-01).
# Worker count is exposed so /preview is not starved while /process holds one worker
# (D-D2). Default 2 is generous for desktop and reasonable for the Ubuntu portal;
# Zeabur free tier can drop to 1 via env. APP_BASE_PATH is the optional FastAPI
# root_path (D-A2) — empty string keeps the default root mount, non-empty (e.g.
# "/pdf-logo") matches a strip-prefix reverse proxy in front of uvicorn.
UVICORN_WORKERS: int = _env_int("UVICORN_WORKERS", 2)
APP_BASE_PATH: str = os.environ.get("APP_BASE_PATH", "")

# Phase 5: hardening (Plan 05-02).
# SESSION_TTL_SECONDS — janitor TTL hard upper bound (D-B2). 1h gives users headroom
# while making "disk fills" structurally impossible for a single-user LAN tool. TTL ≫
# PROCESS_TIMEOUT_SECONDS (60x) is the race-window guarantee that backs D-B4: an
# in-flight /process job cannot age out mid-run.
# PROCESS_TIMEOUT_SECONDS — /process hard ceiling enforced by asyncio.wait_for at the
# route handler (D-D3). On timeout the HTTP returns 504; the underlying thread cannot
# be killed (Pitfall 1) — workers=2 (D-D2) ensures previews stay responsive.
# CORS_ALLOW_ORIGINS — comma-separated allowlist; empty string disables the CORSMiddleware
# (the default — same-origin / iframe / strip-prefix all work without it). Sub-domain
# embedding (Phase 5 future) sets this to enable cross-origin requests.
SESSION_TTL_SECONDS: int = _env_int("SESSION_TTL_SECONDS", 3600)
PROCESS_TIMEOUT_SECONDS: int = _env_int("PROCESS_TIMEOUT_SECONDS", 60)
CORS_ALLOW_ORIGINS: str = os.environ.get("CORS_ALLOW_ORIGINS", "")

# Hotfix #06 (dCt-residue): density threshold for the per-artefact-cover → raster-overlay
# dispatcher in :func:`app.services.redact.remove_region_vector`. When the residual
# zero-area ``type='f'`` fill count fully inside the user rect after ``apply_redactions``
# is >= this value, the dispatcher swaps the per-artefact white-cover strategy
# (:func:`app.services.pdf_engine.cover_zero_area_artefacts`) for a single solid-white
# image XObject overlay (:func:`app.services.pdf_engine.replace_region_with_white_raster`)
# — closing the "re-colour the per-artefact covers to reveal the supplier shape" attack.
#
# 100 is the empirical default: DC.pdf-class CAD line corners surface single-digit-to-low-
# tens zero-area artefacts (well below 100); the hotfix-#06 reproduction file (a supplier
# CAD-glyph "dCt" logo decomposed into 1742 zero-area paths) sits two orders of magnitude
# above. The default is robust to a 5–10× shift in either population. Ops can tune via
# ``LOGOSWAP_ZERO_AREA_RASTER_THRESHOLD`` without a code change. See
# ``.planning/phases/05-ubuntu/hotfix-06-dct-residue/`` for the derivation.
ZERO_AREA_RASTER_THRESHOLD: int = _env_int("LOGOSWAP_ZERO_AREA_RASTER_THRESHOLD", 100)
