"""Round-trip + placement proof for the coordinate mapper (the spine, Build-Order step 3).

These tests are THE GATE for Phase 2: Plan 02-02 (redaction) must not land until they are
green. They prove that a rectangle drawn in browser-image pixels maps to the correct
PyMuPDF ``Rect`` on the UNROTATED page and back, within < 1px per edge, at every page
rotation (0/90/180/270) AND on a page whose MediaBox does not start at (0,0) — the two
coordinate pitfalls (PITFALLS 1-2) that decide whether the whole tool works.

Per the conftest precedent, the TEST harness may import ``fitz`` directly to BUILD
rotated / offset-MediaBox fixtures and to draw a mapped Rect for the visual-overlap
sanity check. Production ``coords.py`` stays fitz-free (asserted by ``test_seam`` here and
by the repo-wide grep acceptance check).
"""

from __future__ import annotations

import fitz  # test harness only — builds rotated/offset fixtures (matches conftest precedent)
import pytest

from app.services import coords, pdf_engine, render

# --- tolerances (explicit; these are the hard gate criteria) ---
EDGE_TOL_PX = 1.0  # round-trip error must be < 1px per edge
IOU_MIN = 0.95  # 0deg visual-overlap sanity: backend-drawn rect overlaps the selection

ROTATIONS = [0, 90, 180, 270]
BASE_W = 400.0
BASE_H = 600.0
OFFSET_MEDIABOX = (10.0, 10.0, 410.0, 610.0)  # non-(0,0) origin


# --------------------------------------------------------------------------------------
# Fixtures: build a page at a given rotation / mediabox, write to disk, expose via the
# engine seam exactly as production would (open_pdf -> get_page) so the test mirrors the
# real handle the mapper receives.
# --------------------------------------------------------------------------------------
def _make_pdf_bytes(rotation: int = 0, mediabox=None) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=BASE_W, height=BASE_H)
        if mediabox is not None:
            page.set_mediabox(fitz.Rect(*mediabox))
        # genuine vector content so the page renders meaningfully
        page.insert_text((40, 60), "coords fixture")
        page.draw_rect(fitz.Rect(50, 50, 150, 150), color=(0, 0, 0), width=1)
        if rotation:
            page.set_rotation(rotation)
        return doc.tobytes()
    finally:
        doc.close()


def _open_page(pdf_bytes: bytes):
    """Open via the engine seam and return (doc, page) — caller closes doc."""
    doc = pdf_engine.open_pdf(pdf_bytes)
    page = pdf_engine.get_page(doc, 0)
    return doc, page


def _meta_for(pdf_path) -> dict:
    """The EXACT dpi/img dims render would emit for page 0 (real render contract)."""
    return render.page_meta(pdf_path, 0)


def _bbox_of_drawn_rect(pdf_bytes: bytes, page_no: int, rect: "fitz.Rect", dpi: int):
    """Draw ``rect`` (filled) on a copy, render at ``dpi``, return the filled pixel bbox.

    Used for the visual-overlap sanity: confirms the mapped Rect occupies the intended
    pixels. Returns ``(x0, y0, x1, y1)`` in image pixels, or ``None`` if nothing drawn.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[page_no]
        # Draw an unmistakable solid red box at the mapped (unrotated) rect.
        page.draw_rect(rect, color=(1, 0, 0), fill=(1, 0, 0), width=0)
        pix = page.get_pixmap(dpi=dpi)
        n = pix.n
        samples = pix.samples
        w, h = pix.width, pix.height
        min_x = min_y = None
        max_x = max_y = None
        for y in range(h):
            row = y * pix.stride
            for x in range(w):
                off = row + x * n
                r = samples[off]
                g = samples[off + 1]
                b = samples[off + 2]
                # red-ish pixel (the fill), tolerant of antialiasing
                if r > 180 and g < 80 and b < 80:
                    if min_x is None or x < min_x:
                        min_x = x
                    if max_x is None or x > max_x:
                        max_x = x
                    if min_y is None or y < min_y:
                        min_y = y
                    if max_y is None or y > max_y:
                        max_y = y
        if min_x is None:
            return None
        return (float(min_x), float(min_y), float(max_x + 1), float(max_y + 1))
    finally:
        doc.close()


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _assert_roundtrip(px_rect, dpi, page, tol=EDGE_TOL_PX):
    """px -> pt(unrotated Rect) -> px must reproduce px_rect within ``tol`` per edge."""
    rect = coords.pixels_to_pdf_rect(px_rect, dpi, page)
    back = coords.pdf_rect_to_pixels(rect, dpi, page)
    expected = coords._normalize_tuple(tuple(float(v) for v in px_rect))
    for i, (got, exp) in enumerate(zip(back, expected)):
        assert abs(got - exp) < tol, (
            f"edge {i}: round-trip {got:.4f} vs expected {exp:.4f} "
            f"(|Δ|={abs(got - exp):.4f} >= {tol}) for px_rect={px_rect}"
        )
    return rect, back


# --------------------------------------------------------------------------------------
# Task 1 core proof: round-trip at all four rotations + offset MediaBox, purity, drag dir.
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_roundtrip_at_each_rotation(rotation, tmp_path):
    """px -> pt -> px reproduces the input within < 1px at 0, 90, 180, 270 degrees."""
    pdf_bytes = _make_pdf_bytes(rotation=rotation)
    pdf_path = tmp_path / f"rot{rotation}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    meta = _meta_for(pdf_path)
    dpi, iw, ih = meta["dpi"], meta["img_w"], meta["img_h"]

    doc, page = _open_page(pdf_bytes)
    try:
        # several representative rects in DISPLAYED image-pixel space
        rects = [
            (10, 20, 110, 220),  # interior
            (0, 0, 50, 50),  # touches top-left corner / origin
            (iw - 60, ih - 60, iw, ih),  # touches bottom-right corner
            (iw / 2 - 30, ih / 2 - 40, iw / 2 + 30, ih / 2 + 40),  # centered
            (0, 0, iw, ih),  # full page
        ]
        # The correct containment bound for a DEROTATED rect is the unrotated content
        # box (= derotation of the full displayed image), NOT page.rect — on rotated
        # pages page.rect is the DISPLAYED rect and a derotated point legitimately falls
        # outside it (e.g. y up to the unrotated height). See pdf_engine.unrotated_content_box.
        bx0, by0, bx1, by1 = pdf_engine.unrotated_content_box(page, iw, ih, dpi)
        for px_rect in rects:
            rect, _ = _assert_roundtrip(px_rect, dpi, page)
            assert rect.x0 >= bx0 - EDGE_TOL_PX and rect.y0 >= by0 - EDGE_TOL_PX
            assert rect.x1 <= bx1 + EDGE_TOL_PX and rect.y1 <= by1 + EDGE_TOL_PX
    finally:
        pdf_engine.close(doc)


@pytest.mark.parametrize("base_rotation", ROTATIONS)
@pytest.mark.parametrize("user_rotation", ROTATIONS)
def test_roundtrip_composed_base_and_user_rotation(base_rotation, user_rotation, tmp_path):
    """px -> pt -> px stays < 1px for EVERY (intrinsic, user) rotation combination.

    Mirrors test_roundtrip_at_each_rotation but composes the page-rotation feature's
    effective rotation: a page rendered/framed at (intrinsic + user) % 360. We build the
    fixture at the INTRINSIC rotation, then set the EFFECTIVE rotation on the page via the
    engine seam exactly as the render/pipeline layers do (set_page_rotation), so the mapper
    derotates against the same orientation the user framed on. The fitz import here is the
    test harness's (production coords.py stays fitz-free — see test_seam).
    """
    pdf_bytes = _make_pdf_bytes(rotation=base_rotation)
    pdf_path = tmp_path / f"base{base_rotation}_user{user_rotation}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    doc, page = _open_page(pdf_bytes)
    try:
        effective = (base_rotation + user_rotation) % 360
        pdf_engine.set_page_rotation(page, effective)
        assert int(page.rotation) == effective

        # The render contract at the EFFECTIVE rotation: dims swap for a quarter turn. Mirror
        # render.page_meta's math against the now-rotated page rect so dpi/img dims match what
        # the rotated PNG would carry (page.rect already reflects /Rotate after set_rotation).
        clamped = render.clamp_dpi(render.config.DEFAULT_DPI)
        eff_dpi = render.fit_dpi_to_pixel_budget(
            clamped, float(page.rect.width), float(page.rect.height)
        )
        scale = eff_dpi / 72.0
        iw = round(float(page.rect.width) * scale)
        ih = round(float(page.rect.height) * scale)

        rects = [
            (10, 20, 110, 220),
            (0, 0, 50, 50),
            (iw - 60, ih - 60, iw, ih),
            (iw / 2 - 30, ih / 2 - 40, iw / 2 + 30, ih / 2 + 40),
            (0, 0, iw, ih),
        ]
        bx0, by0, bx1, by1 = pdf_engine.unrotated_content_box(page, iw, ih, eff_dpi)
        for px_rect in rects:
            rect, _ = _assert_roundtrip(px_rect, eff_dpi, page)
            assert rect.x0 >= bx0 - EDGE_TOL_PX and rect.y0 >= by0 - EDGE_TOL_PX
            assert rect.x1 <= bx1 + EDGE_TOL_PX and rect.y1 <= by1 + EDGE_TOL_PX
    finally:
        pdf_engine.close(doc)


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_offset_mediabox_roundtrip_and_inside_page(rotation, tmp_path):
    """On a non-(0,0) MediaBox page the round-trip still holds and stays INSIDE page.rect.

    No constant offset must appear (Pitfall 2): page.rect carries the MediaBox offset, so
    coords (which never touches raw MediaBox numbers) maps correctly at every rotation.
    """
    pdf_bytes = _make_pdf_bytes(rotation=rotation, mediabox=OFFSET_MEDIABOX)
    pdf_path = tmp_path / f"offset_rot{rotation}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    meta = _meta_for(pdf_path)
    dpi, iw, ih = meta["dpi"], meta["img_w"], meta["img_h"]

    doc, page = _open_page(pdf_bytes)
    try:
        # a center rect must map to a Rect that lies inside the unrotated content box
        # (no constant offset, no escape outside the page) — the box already carries any
        # MediaBox offset because it is derived by derotating the rendered image rect.
        center_px = (iw / 2 - 40, ih / 2 - 30, iw / 2 + 40, ih / 2 + 30)
        rect, _ = _assert_roundtrip(center_px, dpi, page)
        bx0, by0, bx1, by1 = pdf_engine.unrotated_content_box(page, iw, ih, dpi)
        assert rect.x0 >= bx0 - EDGE_TOL_PX, f"{rect} escaped left of box {(bx0, by0, bx1, by1)}"
        assert rect.y0 >= by0 - EDGE_TOL_PX, f"{rect} escaped top of box {(bx0, by0, bx1, by1)}"
        assert rect.x1 <= bx1 + EDGE_TOL_PX, f"{rect} escaped right of box {(bx0, by0, bx1, by1)}"
        assert rect.y1 <= by1 + EDGE_TOL_PX, f"{rect} escaped bottom of box {(bx0, by0, bx1, by1)}"
    finally:
        pdf_engine.close(doc)


def test_zero_rotation_identity_scale(tmp_path):
    """At 0deg / origin-(0,0), px*72/dpi equals the unrotated Rect coordinates directly."""
    pdf_bytes = _make_pdf_bytes(rotation=0)
    pdf_path = tmp_path / "id.pdf"
    pdf_path.write_bytes(pdf_bytes)
    meta = _meta_for(pdf_path)
    dpi = meta["dpi"]
    doc, page = _open_page(pdf_bytes)
    try:
        px_rect = (40, 80, 200, 360)
        s = 72.0 / dpi
        rect = coords.pixels_to_pdf_rect(px_rect, dpi, page)
        for got, exp in zip(
            (rect.x0, rect.y0, rect.x1, rect.y1),
            (px_rect[0] * s, px_rect[1] * s, px_rect[2] * s, px_rect[3] * s),
        ):
            assert abs(got - exp) < (EDGE_TOL_PX * s)
    finally:
        pdf_engine.close(doc)


def test_drag_direction_independence(tmp_path):
    """A reversed rect (x1,y1,x0,y0) maps to the SAME normalized Rect as (x0,y0,x1,y1)."""
    pdf_bytes = _make_pdf_bytes(rotation=90)  # rotation makes this a real test, not trivial
    pdf_path = tmp_path / "drag.pdf"
    pdf_path.write_bytes(pdf_bytes)
    meta = _meta_for(pdf_path)
    dpi = meta["dpi"]
    doc, page = _open_page(pdf_bytes)
    try:
        fwd = coords.pixels_to_pdf_rect((30, 40, 130, 240), dpi, page)
        rev = coords.pixels_to_pdf_rect((130, 240, 30, 40), dpi, page)
        for a, b in zip((fwd.x0, fwd.y0, fwd.x1, fwd.y1), (rev.x0, rev.y0, rev.x1, rev.y1)):
            assert abs(a - b) < 1e-6
        # and the output is normalized
        assert fwd.x0 <= fwd.x1 and fwd.y0 <= fwd.y1
    finally:
        pdf_engine.close(doc)


def test_clamp_px_rect_clamps_and_flags():
    """clamp_px_rect clamps out-of-bounds / NaN rects to the box and flags ONLY those.

    WR-06: ``was_clamped`` is the BOUNDARY-clamp flag. A reversed-but-in-bounds drag is mere
    normalization and must NOT be flagged (else the frontend wrongly says the box exceeded the
    page); only an actual edge move to 0/img_w/img_h (or a NaN) sets the flag.
    """
    img_w, img_h = 800, 1200
    # in-bounds, forward -> unchanged, not flagged
    r, flagged = coords.clamp_px_rect((10, 20, 100, 200), img_w, img_h)
    assert r == (10.0, 20.0, 100.0, 200.0)
    assert flagged is False

    # negative + beyond bounds -> clamped to [0,img] and flagged
    r, flagged = coords.clamp_px_rect((-50, -10, img_w + 999, img_h + 999), img_w, img_h)
    assert r == (0.0, 0.0, float(img_w), float(img_h))
    assert flagged is True

    # inverted drag, fully IN bounds -> normalized but NOT flagged (direction-only correction).
    r, flagged = coords.clamp_px_rect((300, 400, 100, 200), img_w, img_h)
    assert r == (100.0, 200.0, 300.0, 400.0)
    assert flagged is False, "a reversed in-bounds drag is normalization, not a boundary clamp"

    # inverted drag that ALSO exceeds a boundary -> normalized AND flagged (an edge was moved).
    r, flagged = coords.clamp_px_rect((300, 400, 100, -50), img_w, img_h)
    assert r == (100.0, 0.0, 300.0, 400.0)
    assert flagged is True

    # NaN -> safe (no crash), flagged, inside box
    r, flagged = coords.clamp_px_rect((float("nan"), 10, 50, 60), img_w, img_h)
    assert flagged is True
    assert 0.0 <= r[0] <= img_w and 0.0 <= r[2] <= img_w


def test_seam_coords_imports_no_fitz():
    """coords.py must not import the engine (purity / AGPL seam, threat T-02-03).

    Checked at the statement level (not a naive substring) so prose mentioning the
    library in docstrings does not false-trigger, mirroring the repo-wide acceptance
    grep ``grep -rl "import fitz" app/`` returning only ``pdf_engine.py``.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(coords))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "fitz" not in imported, f"coords imported the engine: {imported}"
    # the module object must not carry a bound fitz reference either
    assert not hasattr(coords, "fitz")


# --------------------------------------------------------------------------------------
# Task 2 visual-overlap sanity: a mapped Rect drawn on the page occupies the intended
# pixels (>= 0.95 IoU at 0deg). This is the "backend-drawn rect overlaps the user
# selection" proof PITFALLS 1 demands.
# --------------------------------------------------------------------------------------
def test_visual_overlap_iou_at_zero_rotation(tmp_path):
    pdf_bytes = _make_pdf_bytes(rotation=0)
    pdf_path = tmp_path / "iou.pdf"
    pdf_path.write_bytes(pdf_bytes)
    meta = _meta_for(pdf_path)
    dpi = meta["dpi"]

    doc, page = _open_page(pdf_bytes)
    try:
        selection_px = (120.0, 160.0, 320.0, 420.0)
        rect = coords.pixels_to_pdf_rect(selection_px, dpi, page)
    finally:
        pdf_engine.close(doc)

    drawn_bbox = _bbox_of_drawn_rect(pdf_bytes, 0, rect, dpi)
    assert drawn_bbox is not None, "mapped Rect produced no visible pixels"
    iou = _iou(selection_px, drawn_bbox)
    assert iou >= IOU_MIN, f"IoU {iou:.4f} < {IOU_MIN}; drawn={drawn_bbox} sel={selection_px}"


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_visual_overlap_iou_all_rotations(rotation, tmp_path):
    """Extends the overlap proof to rotated pages: map px->Rect, draw it, render, and
    confirm the drawn pixels land back on the original selection (>= 0.95 IoU)."""
    pdf_bytes = _make_pdf_bytes(rotation=rotation)
    pdf_path = tmp_path / f"iou_rot{rotation}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    meta = _meta_for(pdf_path)
    dpi, iw, ih = meta["dpi"], meta["img_w"], meta["img_h"]

    doc, page = _open_page(pdf_bytes)
    try:
        selection_px = (
            iw * 0.25,
            ih * 0.25,
            iw * 0.65,
            ih * 0.6,
        )
        rect = coords.pixels_to_pdf_rect(selection_px, dpi, page)
    finally:
        pdf_engine.close(doc)

    drawn_bbox = _bbox_of_drawn_rect(pdf_bytes, 0, rect, dpi)
    assert drawn_bbox is not None
    iou = _iou(selection_px, drawn_bbox)
    assert iou >= IOU_MIN, (
        f"rot={rotation}: IoU {iou:.4f} < {IOU_MIN}; drawn={drawn_bbox} sel={selection_px}"
    )
