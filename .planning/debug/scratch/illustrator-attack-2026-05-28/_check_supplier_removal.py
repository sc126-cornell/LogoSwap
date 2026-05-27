"""Forensic check of LogoSwap output PDFs: is the supplier brand truly removed
or just covered by white?

Note: in this CAD PDF the supplier brand "NINGBO dCt" is NOT rendered as
searchable text — it's a CAD glyph (drawn as vector paths). So "did the
text get removed" is the wrong question; the right questions are:

  1. Does the LIVE pipeline leave supplier vector paths under a white cover
     that a re-color attack could un-mask?
  2. Or does it use Option A (raster overlay = opaque image XObject) that
     blocks the re-color attack entirely?

Per Phase 5 hotfix 06 (dCt-residue), Option A landed. Expected POST state
in the framed region:
  - 0 (or few) residual zero-area black-fill drawings inside the region
  - 0 white-fill DRAWINGS (the old cover_zero_area_artefacts path is skipped)
  - 1+ image XObject covering the region (the raster overlay)

This script is a one-shot check; not committed.
"""
from __future__ import annotations
import sys
from pathlib import Path
import fitz
import numpy as np

ORIG = Path("samples/3013A-13A-C6-XX-3D02-A01-00040.pdf")
OUTPUTS = [
    Path("3013A-13A-C6-XX-3D02-A01-00040_logoswap (2).pdf"),
    Path("3013A-13A-C6-XX-3D02-A01-00040_logoswap (3).pdf"),
    Path("3013A-13A-C6-XX-3D02-A01-00040_logoswap (4).pdf"),
    Path("3013A-13A-C6-XX-3D02-A01-00040_logoswap (5).pdf"),
]


def categorize_drawings(page: fitz.Page, rect: fitz.Rect) -> dict:
    """Categorize drawings intersecting rect."""
    cats = {
        "black_normal": 0,
        "black_zero_area": 0,
        "white_normal": 0,
        "white_zero_area": 0,
        "other_fill": 0,
        "stroke": 0,
    }
    for d in page.get_drawings():
        bbox = fitz.Rect(d["rect"])
        if not bbox.intersects(rect):
            continue
        is_zero = (bbox.width < 0.01) or (bbox.height < 0.01)
        if d["type"] == "s":
            cats["stroke"] += 1
            continue
        fill = d.get("fill")
        if fill is None:
            cats["other_fill"] += 1
            continue
        is_white = all(c >= 0.99 for c in fill)
        is_black = all(c <= 0.01 for c in fill)
        if is_white:
            cats["white_zero_area" if is_zero else "white_normal"] += 1
        elif is_black:
            cats["black_zero_area" if is_zero else "black_normal"] += 1
        else:
            cats["other_fill"] += 1
    return cats


def images_in_rect(page: fitz.Page, rect: fitz.Rect) -> int:
    """Count image XObjects whose displayed bbox intersects rect."""
    n = 0
    for img in page.get_images(full=True):
        xref = img[0]
        for bbox in page.get_image_rects(xref):
            if fitz.Rect(bbox).intersects(rect):
                n += 1
                break
    return n


def find_diff_regions(orig: fitz.Page, out: fitz.Page) -> list[fitz.Rect]:
    """Find all connected diff regions (cluster pixels into bboxes)."""
    dpi = 72
    a = orig.get_pixmap(dpi=dpi, alpha=False)
    b = out.get_pixmap(dpi=dpi, alpha=False)
    if a.width != b.width or a.height != b.height:
        return []
    arr_a = np.frombuffer(a.samples, dtype=np.uint8).reshape(a.height, a.width, a.n)
    arr_b = np.frombuffer(b.samples, dtype=np.uint8).reshape(b.height, b.width, b.n)
    diff = np.any(arr_a != arr_b, axis=2)
    if not diff.any():
        return []
    # Simple connected-component bbox: dilate then find row/col runs.
    # For our use case (1–few rectangular regions), a single bbox is enough.
    ys, xs = np.where(diff)
    # Cluster by vertical gaps > 30px (separate regions if user framed multiple).
    y_sorted = np.unique(ys)
    if len(y_sorted) == 0:
        return []
    gaps = np.where(np.diff(y_sorted) > 30)[0]
    cluster_starts = [0] + [g + 1 for g in gaps]
    cluster_ends = list(gaps) + [len(y_sorted) - 1]
    regions = []
    for s, e in zip(cluster_starts, cluster_ends):
        y_lo = int(y_sorted[s])
        y_hi = int(y_sorted[e])
        rows_mask = (ys >= y_lo) & (ys <= y_hi)
        x_cluster = xs[rows_mask]
        if len(x_cluster) == 0:
            continue
        regions.append(fitz.Rect(int(x_cluster.min()), y_lo,
                                 int(x_cluster.max()) + 1, y_hi + 1))
    return regions


def render_region_stats(page: fitz.Page, rect: fitz.Rect) -> dict:
    """Render the region at 288dpi and report pixel composition."""
    pm = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=rect, alpha=False)
    arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
    near_white = np.all(arr >= 250, axis=2).sum()
    near_black = np.all(arr <= 30, axis=2).sum()
    total = pm.width * pm.height
    return {
        "total_px": int(total),
        "near_white_pct": round(100 * near_white / total, 2) if total else 0.0,
        "near_black_pct": round(100 * near_black / total, 2) if total else 0.0,
        "other_pct": round(100 * (total - near_white - near_black) / total, 2) if total else 0.0,
    }


def recolor_attack_simulation(page: fitz.Page, rect: fitz.Rect) -> dict:
    """Simulate the re-color attack on whatever white-fill drawings exist
    in the rect. If the region is shielded by an opaque image XObject (Option
    A), the attack is impossible — the drawing stack lies UNDER the image and
    doesn't render.

    We approximate the attack by:
      1. Drawing a red rect over every white-fill drawing inside `rect`
      2. Rendering, checking if any near-red pixels appear inside the bbox of
         each original white-fill
    If no red pixels appear, the image XObject above is opaque (= true block).
    If red pixels appear in a recognizable shape, that's the residual supplier
    content the attack can unmask.
    """
    white_fills = []
    for d in page.get_drawings():
        bbox = fitz.Rect(d["rect"])
        if not bbox.intersects(rect):
            continue
        fill = d.get("fill")
        if fill is None or d["type"] == "s":
            continue
        if all(c >= 0.99 for c in fill) and bbox.width > 0.01 and bbox.height > 0.01:
            white_fills.append(bbox)
    if not white_fills:
        return {"white_fills_found": 0, "attack_red_pixels": 0, "attack_blocked": True}

    # Render baseline
    pm0 = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=rect, alpha=False)
    arr0 = np.frombuffer(pm0.samples, dtype=np.uint8).reshape(pm0.height, pm0.width, pm0.n).copy()

    # Open page in a writable copy, draw red over each white-fill, re-render
    src = fitz.open(page.parent.name)
    p = src[page.number]
    for bbox in white_fills:
        p.draw_rect(bbox, color=(1, 0, 0), fill=(1, 0, 0), overlay=True)
    pm1 = p.get_pixmap(matrix=fitz.Matrix(4, 4), clip=rect, alpha=False)
    arr1 = np.frombuffer(pm1.samples, dtype=np.uint8).reshape(pm1.height, pm1.width, pm1.n)
    src.close()

    # Count pixels that became red (R high, G/B low) AND were not red before
    became_red = (arr1[..., 0] >= 200) & (arr1[..., 1] <= 60) & (arr1[..., 2] <= 60)
    was_red = (arr0[..., 0] >= 200) & (arr0[..., 1] <= 60) & (arr0[..., 2] <= 60)
    newly_red = (became_red & ~was_red).sum()
    return {
        "white_fills_found": len(white_fills),
        "attack_red_pixels": int(newly_red),
        "attack_blocked": int(newly_red) < 100,  # heuristic
    }


def check_file(path: Path, orig_doc: fitz.Document) -> None:
    print(f"\n{'=' * 72}")
    print(f"FILE: {path.name}")
    print(f"  size: {path.stat().st_size:,} bytes")
    if not path.exists():
        print("  MISSING")
        return
    doc = fitz.open(path)
    try:
        page = doc[0]
        orig_page = orig_doc[0]

        # Diff regions
        regions = find_diff_regions(orig_page, page)
        if not regions:
            print("  [??] no visual diff vs original — page was not modified?")
            return
        print(f"  {len(regions)} diff region(s) found")

        all_clean = True
        for i, region in enumerate(regions, 1):
            print(f"\n  Region {i}: PDF pts {tuple(round(v, 1) for v in region)}  "
                  f"({region.width:.0f} x {region.height:.0f})")

            # 1. drawings categorization
            orig_cats = categorize_drawings(orig_page, region)
            out_cats = categorize_drawings(page, region)
            print(f"    drawings:")
            print(f"      {'category':<20} {'ORIG':>6}  {'OUT':>6}  {'delta':>7}")
            for k in ["black_normal", "black_zero_area", "white_normal",
                      "white_zero_area", "other_fill", "stroke"]:
                delta = out_cats[k] - orig_cats[k]
                print(f"      {k:<20} {orig_cats[k]:>6}  {out_cats[k]:>6}  {delta:+7d}")

            # 2. image XObjects
            orig_imgs = images_in_rect(orig_page, region)
            out_imgs = images_in_rect(page, region)
            print(f"    image XObjects: ORIG={orig_imgs}, OUT={out_imgs}  "
                  f"(+{out_imgs - orig_imgs} new)")
            option_a_active = out_imgs > orig_imgs

            # 3. visual composition
            stats = render_region_stats(page, region)
            print(f"    visual @ 288dpi: white={stats['near_white_pct']}%, "
                  f"black={stats['near_black_pct']}%, "
                  f"other={stats['other_pct']}%")

            # 4. re-color attack
            attack = recolor_attack_simulation(page, region)
            print(f"    re-color attack: {attack['white_fills_found']} white-fills targeted, "
                  f"{attack['attack_red_pixels']} new red px → "
                  f"{'BLOCKED' if attack['attack_blocked'] else 'EXPOSED'}")

            # Verdict per region
            zero_residue = out_cats["black_zero_area"]
            normal_residue = out_cats["black_normal"]
            if not attack["attack_blocked"]:
                print(f"    >>> VERDICT: region {i} — SUPPLIER CONTENT EXPOSED by re-color attack")
                all_clean = False
            elif option_a_active and out_cats["white_normal"] == 0:
                print(f"    >>> VERDICT: region {i} — TRUE REMOVAL (Option A raster overlay active, "
                      f"no cover-path drawings, attack blocked)")
            elif zero_residue > 50 and out_cats["white_normal"] > 50:
                print(f"    >>> VERDICT: region {i} — OLD COVER PATH (cover_zero_area_artefacts), "
                      f"vulnerable to re-color → check attack result above")
                if not attack["attack_blocked"]:
                    all_clean = False
            elif normal_residue > 10:
                print(f"    >>> VERDICT: region {i} — RESIDUAL SUPPLIER BLACK-FILL ({normal_residue}), "
                      f"check visually whether it's the inserted company logo")
            else:
                print(f"    >>> VERDICT: region {i} — looks clean "
                      f"(no significant residue, attack blocked)")

        print(f"\n  OVERALL: {'CLEAN' if all_clean else '!! RESIDUAL DETECTED !!'}")
    finally:
        doc.close()


def main() -> int:
    if not ORIG.exists():
        print(f"ERROR: original sample not found at {ORIG}")
        return 1
    orig_doc = fitz.open(ORIG)
    print(f"Original: {ORIG.name}")
    print(f"  size: {ORIG.stat().st_size:,} bytes")
    print(f"  pages: {orig_doc.page_count}")
    print(f"  page rect: {orig_doc[0].rect}")
    print(f"  total drawings on p1: {len(orig_doc[0].get_drawings())}")
    print(f"  total image XObjects on p1: {len(orig_doc[0].get_images(full=True))}")

    for out_path in OUTPUTS:
        check_file(out_path, orig_doc)

    orig_doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
