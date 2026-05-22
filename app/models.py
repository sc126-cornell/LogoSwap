"""Pydantic v2 request/response models — the API contract the frontend consumes.

Phase-1 shapes are defined by the <interfaces> block of 01-01-PLAN.md; the Phase-2
job-spec shapes (RegionMark / JobSpec) by 02-02-PLAN.md — they are the validated
``POST /sessions/{id}/process`` request contract Plan 02-03 (region UI) will POST.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, field_validator

from . import config


class SessionInfo(BaseModel):
    """Returned by POST /sessions and GET /sessions/{id}."""

    session_id: str
    page_count: int
    filename: str


class PageMeta(BaseModel):
    """Per-page metadata for the coordinate seam (Phase 2) and pre-load page sizing.

    ``page_w_pt`` / ``page_h_pt`` are the unrotated page dimensions in PDF points;
    ``img_w`` / ``img_h`` are the rendered pixel dimensions at ``dpi``.
    """

    page_no: int
    page_w_pt: float
    page_h_pt: float
    rotation: int
    dpi: int
    img_w: int
    img_h: int


class ErrorDetail(BaseModel):
    """Structured error body: responses are shaped ``{"detail": {code, message}}``."""

    code: str
    message: str


class RegionMark(BaseModel):
    """One region to remove: a rectangle in IMAGE-pixel space on a given page.

    ``px_rect`` is ``(x0, y0, x1, y1)`` measured on exactly the PNG ``render.render_page``
    produced at the job's ``dpi`` (preview-image pixels, top-left origin, displayed/rotated
    orientation). The pipeline maps it to the unrotated page via ``coords.pixels_to_pdf_rect``
    and clamps it with ``coords.clamp_px_rect`` before redaction (threat T-02-01), so an
    out-of-bounds or inverted rect can never read/redact outside the page.
    """

    page: int = Field(ge=0, description="0-based page index")
    px_rect: List[float] = Field(
        ..., description="(x0, y0, x1, y1) in image pixels at the job dpi"
    )

    @field_validator("px_rect")
    @classmethod
    def _exactly_four_finite(cls, v: List[float]) -> List[float]:
        if len(v) != 4:
            raise ValueError("px_rect must have exactly 4 numbers (x0, y0, x1, y1)")
        # Reject NaN/inf at the boundary so a non-finite coordinate never reaches the
        # clamp/mapper (the clamp is NaN-safe too — this is defence in depth, T-02-01).
        for coord in v:
            f = float(coord)
            if f != f or f in (float("inf"), float("-inf")):
                raise ValueError("px_rect coordinates must be finite numbers")
        return v


class JobSpec(BaseModel):
    """The ``POST /sessions/{id}/process`` request body: regions + the render DPI.

    ``dpi`` MUST be the DPI the client measured ``px_rect`` at (echoed from the render
    contract's ``X-Render-Dpi`` header) so server and client cannot disagree on scale.
    Validated into ``[MIN_DPI, MAX_DPI]`` and ``len(regions) <= MAX_REGIONS`` to bound
    redaction cost (DoS T-02-04). An empty ``regions`` list is allowed (a no-op export).

    ``logo_id`` is the OPTIONAL global logo (Phase 3, D-01): when present, the same logo is
    placed into every removed region; when null/absent the job is pure removal (Phase-2
    behavior). It is resolved server-side via the ``logo.py`` manifest allowlist (a dict key,
    never a path — T-03-01), so no charset validator is needed for safety; the ``max_length``
    is cheap defense-in-depth against absurd inputs (V5).
    """

    dpi: int = Field(..., ge=config.MIN_DPI, le=config.MAX_DPI)
    regions: List[RegionMark] = Field(default_factory=list)
    logo_id: str | None = Field(
        default=None,
        max_length=128,
        description="optional global logo id (D-01); resolved via manifest allowlist",
    )

    @field_validator("regions")
    @classmethod
    def _cap_region_count(cls, v: List[RegionMark]) -> List[RegionMark]:
        if len(v) > config.MAX_REGIONS:
            raise ValueError(
                f"too many regions: {len(v)} (max {config.MAX_REGIONS})"
            )
        return v
