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

# Human-readable forms used inside limit-bearing error messages so the frontend can
# surface the {limit} value. Derived from the byte limit so they never drift.
MAX_UPLOAD_MB: int = MAX_UPLOAD_BYTES // (1024 * 1024)

API_TITLE: str = os.environ.get("API_TITLE", "PDF 商標替換工具 API")
