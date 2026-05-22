"""Smoke test for Plan 02-03: drives the exact HTTP contract web/js/api.js wires to.

Builds a vector PDF (text + a line; one page rotated 90 deg), then exercises the frontend flow
end-to-end via FastAPI's in-process TestClient (no port juggling):
  upload -> /process {dpi:200, regions:[{page, px_rect}]} -> /result/pages/{n}/image -> /result.

Asserts the wiring the UI depends on:
  - process echoes per-region {removed, clamped} flags the action group reads
  - the result-render endpoint returns PNG + the six X- headers (so the overlay maths matches)
  - the downloaded PDF keeps ALL pages and the boxed region extracts NO text (true removal)

This is a throwaway harness (NOT a committed pytest); it proves the api.js contract for the UAT.
Run: .venv/Scripts/python scripts/smoke_02_03.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

# Ensure the repo root (parent of scripts/) is importable when run as `python scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Print CJK cleanly on the Windows console (cosmetic; avoids mojibake in the smoke output).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 — older/non-reconfigurable streams: leave as-is.
    pass

import fitz
from fastapi.testclient import TestClient

from app.main import app


def build_pdf() -> bytes:
    """A 2-page vector PDF; page 2 is rotated 90 deg. Text + a line = genuine vector content."""
    doc = fitz.open()
    try:
        p0 = doc.new_page(width=300, height=400)
        p0.insert_text((60, 80), "SUPPLIER LOGO")
        p0.draw_line(fitz.Point(50, 120), fitz.Point(250, 120))

        p1 = doc.new_page(width=300, height=400)
        p1.insert_text((60, 80), "ROTATED MARK")
        p1.draw_line(fitz.Point(50, 120), fitz.Point(250, 120))
        p1.set_rotation(90)
        return doc.tobytes()
    finally:
        doc.close()


def main() -> int:
    client = TestClient(app)

    # 1. Upload (the frontend's api.createSession).
    pdf = build_pdf()
    resp = client.post(
        "/sessions",
        files={"file": ("圖紙.pdf", io.BytesIO(pdf), "application/pdf")},
    )
    assert resp.status_code == 201, (resp.status_code, resp.text)
    sess = resp.json()
    sid = sess["session_id"]
    page_count = sess["page_count"]
    print(f"[upload] session_id={sid} page_count={page_count} filename={sess['filename']}")
    assert page_count == 2

    # 2. Read page 0 render metadata (the overlay's projection denominator: img_w/img_h + dpi).
    meta0 = client.get(f"/sessions/{sid}/pages/0/meta").json()
    print(f"[meta p0] dpi={meta0['dpi']} img={meta0['img_w']}x{meta0['img_h']} rot={meta0['rotation']}")
    meta1 = client.get(f"/sessions/{sid}/pages/1/meta").json()
    print(f"[meta p1] dpi={meta1['dpi']} img={meta1['img_w']}x{meta1['img_h']} rot={meta1['rotation']}")

    # 3. Process: a region over the text/line on BOTH pages, in IMAGE-PIXEL space at dpi 200
    #    (exactly what regions.js sends via api.processJob). The box covers the upper drawn band.
    # The drawn content sits in the UPPER band of each page's UNROTATED content space. The overlay
    # always works in DISPLAYED image-pixel space, so on the 90 deg page the same content appears on
    # the RIGHT of the landscape image — exactly the rotated-page placement the human checkpoint
    # verifies. We box the displayed region where the content actually lands per rotation; the
    # coords mapper (Plan 02-01) derotates it back. (A generous box so the server fully clears it.)
    def upper_band_box(meta):
        w, h, rot = meta["img_w"], meta["img_h"], meta["rotation"]
        if rot == 90:
            # unrotated-top maps to displayed-right (landscape image)
            return [int(w * 0.55), int(h * 0.02), int(w * 0.98), int(h * 0.98)]
        if rot == 270:
            return [int(w * 0.02), int(h * 0.02), int(w * 0.45), int(h * 0.98)]
        if rot == 180:
            return [int(w * 0.02), int(h * 0.55), int(w * 0.98), int(h * 0.98)]
        return [int(w * 0.02), int(h * 0.02), int(w * 0.98), int(h * 0.45)]

    job = {
        "dpi": meta0["dpi"],
        "regions": [
            {"page": 0, "px_rect": upper_band_box(meta0)},
            {"page": 1, "px_rect": upper_band_box(meta1)},
        ],
    }
    resp = client.post(f"/sessions/{sid}/process", json=job)
    assert resp.status_code == 200, (resp.status_code, resp.text)
    result = resp.json()
    print(f"[process] output_filename={result['output_filename']} regions={result['regions']}")
    assert result["page_count"] == 2
    assert result["output_filename"].endswith("_logoswap.pdf")
    # Per-region flags the action group reads.
    assert all("removed" in r and "clamped" in r for r in result["regions"])
    assert any(r["removed"] for r in result["regions"]), "expected at least one region removed"

    # 4. Result-render (the 移除結果 after-image) for each page: PNG + the six X- headers.
    for n in range(page_count):
        r = client.get(f"/sessions/{sid}/result/pages/{n}/image")
        assert r.status_code == 200, (n, r.status_code, r.text)
        assert r.headers["content-type"] == "image/png"
        for h in ("X-Page-Width-Pt", "X-Page-Height-Pt", "X-Page-Rotation",
                  "X-Render-Dpi", "X-Image-Width-Px", "X-Image-Height-Px"):
            assert h in r.headers, f"missing header {h} on result image p{n}"
        print(f"[result-image p{n}] {len(r.content)} bytes; headers OK")

    # 5. Download the exported PDF (api.resultDownloadURL) and prove true removal + all pages kept.
    r = client.get(f"/sessions/{sid}/result")
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.headers["content-type"] == "application/pdf"
    cd = r.headers.get("content-disposition", "")
    print(f"[download] {len(r.content)} bytes; content-disposition={cd!r}")
    assert "filename*=" in cd  # RFC-5987 CJK name

    out = fitz.open(stream=r.content, filetype="pdf")
    try:
        assert out.page_count == 2, "all pages must be kept (D-07)"
        # The test PDF's only content is the boxed band, so after true removal each page must
        # extract NO text at all (rotation-agnostic — the band was the entire content).
        for n in range(out.page_count):
            page = out[n]
            words = page.get_text("words")
            print(f"[verify p{n}] words after removal: {words}")
            assert not words, f"residual extractable text on p{n}: {words}"
            drawings = page.get_drawings()
            print(f"[verify p{n}] drawings after removal: {len(drawings)}")
    finally:
        out.close()

    # 6. result_not_ready path for a fresh session (download before processing -> 404).
    pdf2 = build_pdf()
    sid2 = client.post(
        "/sessions",
        files={"file": ("other.pdf", io.BytesIO(pdf2), "application/pdf")},
    ).json()["session_id"]
    r = client.get(f"/sessions/{sid2}/result")
    print(f"[result_not_ready] status={r.status_code} body={r.json()}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "result_not_ready"

    print("\nSMOKE 02-03 PASSED: upload -> process -> result-image -> download; "
          "true removal verified, all pages kept, result_not_ready guarded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
