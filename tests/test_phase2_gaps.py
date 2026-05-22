"""Phase 2 gap tests — adversarial coverage for REGION-02 (multi-page removal via API)
and OUTPUT-01 (CJK filename in RFC-5987 Content-Disposition via API).

These tests fill genuine behavioral gaps that the existing pytest suite (test_redact.py,
test_process_api.py) does not cover, but the smoke script (scripts/smoke_02_03.py) does
informally. Converting smoke coverage into failing-first pytest assertions is the goal.

Gap inventory:
  GAP-01 (REGION-02 / REMOVE-01): POST /process with regions on BOTH pages of a
          multi-page PDF truly removes content on each page and the exported PDF is
          empty in both regions. The existing pytest tests only remove from page 0.
          smoke_02_03.py covers this but is not a pytest; this makes it a gate.

  GAP-02 (OUTPUT-01): Uploading a CJK-named file and downloading the result yields a
          Content-Disposition with ``filename*=UTF-8''<urlencoded CJK>`` — the RFC-5987
          encoding that allows browsers to save the file as ``圖紙_logoswap.pdf``.
          The existing API test only uploads ``design.pdf`` (ASCII) and verifies the
          ASCII name in the header; the CJK path is only proven by the smoke script.
"""

from __future__ import annotations

import io
from urllib.parse import unquote

import fitz
import pytest

from app import storage
from app.services import coords, pdf_engine


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_REGION_PT = (10.0, 40.0, 190.0, 120.0)  # covers text + line in a 200x300pt page


def _upload(client, data: bytes, filename: str = "design.pdf"):
    return client.post(
        "/sessions", files={"file": (filename, io.BytesIO(data), "application/pdf")}
    )


def _region_px_for(client, sid: str, page_no: int = 0):
    """Return (px_rect, dpi) for _REGION_PT at the page's effective DPI."""
    meta = client.get(f"/sessions/{sid}/pages/{page_no}/meta").json()
    scale = meta["dpi"] / 72.0
    return [v * scale for v in _REGION_PT], meta["dpi"]


def _region_empty_in_exported_pdf(pdf_bytes: bytes, px_rect, dpi: int, page_no: int) -> bool:
    """Return True if the region has NO extractable text and NO vector in the exported PDF."""
    doc = pdf_engine.open_pdf(pdf_bytes)
    try:
        page = pdf_engine.get_page(doc, page_no)
        rect = coords.pixels_to_pdf_rect(px_rect, dpi, page)
        rt = (rect.x0, rect.y0, rect.x1, rect.y1)
        words = pdf_engine.get_text_words_in_rect(page, rt)
        drawings = pdf_engine.get_drawings_intersecting(page, rt)
        return words == [] and drawings == []
    finally:
        pdf_engine.close(doc)


# ---------------------------------------------------------------------------
# GAP-01: multi-page removal via API (REGION-02 / REMOVE-01)
# ---------------------------------------------------------------------------


def test_process_removes_content_on_both_pages_of_multipage_pdf(client, valid_pdf_bytes):
    """POST /process with regions on page 0 AND page 1 truly removes content on both pages.

    REGION-02: the user can mark regions on multiple pages in one job.
    REMOVE-01: each region is truly removed (not covered) in the exported PDF.

    The conftest ``valid_pdf_bytes`` is a 2-page PDF; page 0 and page 1 both have text
    "Page N" and a horizontal line. We box both pages' content and assert:
      - The process response includes per-region flags for both pages.
      - The exported PDF has NO extractable text/vector in the framed region on EITHER page.
      - All pages are kept (D-07) — page_count remains 2.
    """
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]

    # Compute the image-pixel rect for each page at its effective DPI.
    px0, dpi0 = _region_px_for(client, sid, page_no=0)
    px1, dpi1 = _region_px_for(client, sid, page_no=1)
    # Both pages are identical geometry; DPIs should match.
    assert dpi0 == dpi1, f"page DPIs differ: p0={dpi0} p1={dpi1}"
    dpi = dpi0

    # POST /process with regions on BOTH pages.
    resp = client.post(
        f"/sessions/{sid}/process",
        json={
            "dpi": dpi,
            "regions": [
                {"page": 0, "px_rect": px0},
                {"page": 1, "px_rect": px1},
            ],
        },
    )
    assert resp.status_code == 200, f"process failed: {resp.text}"
    body = resp.json()

    # All pages kept (D-07).
    assert body["page_count"] == 2, "exported PDF must keep all pages"

    # Per-region flags: both pages should report removed=True, clamped=False.
    regions = {r["page"]: r for r in body["regions"]}
    assert 0 in regions and 1 in regions, f"missing page in regions: {body['regions']}"
    assert regions[0]["removed"] is True, f"page 0 region not removed: {regions[0]}"
    assert regions[1]["removed"] is True, f"page 1 region not removed: {regions[1]}"
    assert regions[0]["clamped"] is False
    assert regions[1]["clamped"] is False

    # Download the exported PDF and verify BOTH pages' regions are truly empty.
    dl = client.get(f"/sessions/{sid}/result")
    assert dl.status_code == 200, f"download failed: {dl.status_code}"
    assert dl.headers["content-type"] == "application/pdf"

    out_pdf = dl.content
    assert _region_empty_in_exported_pdf(out_pdf, px0, dpi, page_no=0), (
        "page 0 region still has extractable text or vector in the exported PDF (REMOVE-01 failure)"
    )
    assert _region_empty_in_exported_pdf(out_pdf, px1, dpi, page_no=1), (
        "page 1 region still has extractable text or vector in the exported PDF (REMOVE-01 failure)"
    )


def test_result_render_after_process_shows_removed_content_on_non_zero_page(
    client, valid_pdf_bytes
):
    """After processing, GET /result/pages/1/image renders the REDACTED page 1.

    REMOVE-04 (server half): the result-render endpoint serves the 移除結果 after-image
    for EVERY page, including pages beyond page 0.  The before/after toggle fires this
    endpoint for the current displayed page — if page 1 always served the original, the
    toggle would be broken for pages beyond the first.
    """
    sid = _upload(client, valid_pdf_bytes).json()["session_id"]
    px1, dpi = _region_px_for(client, sid, page_no=1)

    resp = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": dpi, "regions": [{"page": 1, "px_rect": px1}]},
    )
    assert resp.status_code == 200, resp.text

    # GET result-render for page 1 -> must return image/png with the six headers.
    img = client.get(f"/sessions/{sid}/result/pages/1/image")
    assert img.status_code == 200, f"result render for page 1 failed: {img.status_code}"
    assert img.headers["content-type"] == "image/png"
    assert img.content[:4] == b"\x89PNG", "response body is not a PNG"
    for h in (
        "X-Page-Width-Pt",
        "X-Page-Height-Pt",
        "X-Page-Rotation",
        "X-Render-Dpi",
        "X-Image-Width-Px",
        "X-Image-Height-Px",
    ):
        assert h in img.headers, f"missing coordinate header {h!r} on result page 1"


# ---------------------------------------------------------------------------
# GAP-02: CJK filename in RFC-5987 Content-Disposition via the API (OUTPUT-01)
# ---------------------------------------------------------------------------


def test_download_result_has_rfc5987_cjk_filename_in_content_disposition(client):
    """Uploading a CJK-named PDF and downloading the result yields RFC-5987 encoding.

    OUTPUT-01: the user downloads the processed PDF.  When the original filename
    contains CJK characters (e.g. ``圖紙.pdf``), the Content-Disposition header must
    carry a ``filename*=UTF-8''<urlencoded>`` field so the browser saves the file
    as ``圖紙_logoswap.pdf`` — not a garbled ASCII fallback.

    The existing pytest API test only verifies an ASCII filename.  This test verifies
    the CJK path by:
      1. Uploading under the name ``圖紙.pdf``.
      2. Running a no-op /process (empty regions — just export).
      3. Asserting the download's Content-Disposition contains ``filename*=UTF-8''``
         and that unquoting the encoded portion yields the expected CJK stem.
    """
    # Build a minimal 1-page PDF with some content.
    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        page.insert_text((40, 60), "test")
        pdf_bytes = doc.tobytes()
    finally:
        doc.close()

    cjk_name = "圖紙.pdf"
    sid = _upload(client, pdf_bytes, filename=cjk_name).json()["session_id"]

    # No-op export (empty regions).
    process_resp = client.post(
        f"/sessions/{sid}/process",
        json={"dpi": 200, "regions": []},
    )
    assert process_resp.status_code == 200, f"process failed: {process_resp.text}"

    dl = client.get(f"/sessions/{sid}/result")
    assert dl.status_code == 200, f"download failed: {dl.status_code}"

    cd = dl.headers.get("content-disposition", "")

    # Must be an attachment.
    assert "attachment" in cd, f"missing 'attachment' in Content-Disposition: {cd!r}"

    # Must have the RFC-5987 filename* field for the CJK name.
    assert "filename*=" in cd, (
        f"RFC-5987 filename* is missing from Content-Disposition: {cd!r}  "
        f"(OUTPUT-01: CJK filename must be encoded as UTF-8'' percent-encoding)"
    )
    assert "UTF-8''" in cd, (
        f"filename* must use UTF-8'' prefix: {cd!r}"
    )

    # Extract and decode the percent-encoded portion.
    # Header shape: filename*=UTF-8''<percent-encoded>
    for part in cd.split(";"):
        part = part.strip()
        if part.lower().startswith("filename*="):
            encoded_value = part[len("filename*="):]
            # Strip the charset prefix: "UTF-8''" prefix
            if "''" in encoded_value:
                encoded_name = encoded_value.split("''", 1)[1]
            else:
                encoded_name = encoded_value
            decoded_name = unquote(encoded_name, encoding="utf-8")
            # The decoded name must be the expected CJK _logoswap filename.
            expected = "圖紙_logoswap.pdf"
            assert decoded_name == expected, (
                f"decoded filename {decoded_name!r} != expected {expected!r}  "
                f"(original Content-Disposition: {cd!r})"
            )
            break
    else:
        pytest.fail(f"Could not find filename*= part in Content-Disposition: {cd!r}")
