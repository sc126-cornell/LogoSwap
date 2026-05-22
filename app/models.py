"""Pydantic v2 response models — the API contract Plan 01-02 (frontend) consumes.

Shapes are defined exactly by the <interfaces> block of 01-01-PLAN.md.
"""

from __future__ import annotations

from pydantic import BaseModel


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
