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
