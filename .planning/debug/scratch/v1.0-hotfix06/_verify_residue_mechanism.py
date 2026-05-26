"""Diagnostic: characterize the EXISTING broken _logoswap.pdf output to confirm the
real residue mechanism. Compares:

  ORIG: 3013A-13A-C6-XX-3D02-A01-00040.pdf         (untouched supplier PDF)
  SWAP: 3013A-13A-C6-XX-3D02-A01-00040_logoswap.pdf (LIVE pipeline output — the bug)

For the framed region PDF pt (603, 480) -> (826, 511), reports:
  - black-fill drawings, zero-area vs non-zero
  - white-fill drawings, zero-area vs non-zero
  - text words

The user's debug file claims the SWAP has 1742 WHITE-FILL paths whose union
reproduces the dCt logo when re-coloured. Verify that count, then check the
ORIG to see if those WHITE shapes are 1-to-1 with zero-area BLACK shapes (i.e.
they are cover_zero_area_artefacts paint, not surviving supplier vectors with
inverted colour).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services import pdf_engine  # noqa: E402

ORIG_PDF = REPO_ROOT / "3013A-13A-C6-XX-3D02-A01-00040.pdf"
SWAP_PDF = REPO_ROOT / "3013A-13A-C6-XX-3D02-A01-00040_logoswap.pdf"
REGION_PT = (603.0, 480.0, 826.0, 511.0)


def _classify(page, rt):
    """Bucket all drawings intersecting ``rt`` by type/fill/zero-area."""
    counts = {
        "black_fill_zero_area": 0,
        "black_fill_normal": 0,
        "white_fill_zero_area": 0,
        "white_fill_normal": 0,
        "other_fill_zero_area": 0,
        "other_fill_normal": 0,
        "stroke": 0,
    }
    samples = {k: [] for k in counts}
    EPS = 0.01

    for d in page.get_drawings():
        d_rect = d.get("rect")
        if d_rect is None:
            continue
        x0, y0, x1, y1 = d_rect.x0, d_rect.y0, d_rect.x1, d_rect.y1
        if x0 > rt[2] or x1 < rt[0] or y0 > rt[3] or y1 < rt[1]:
            continue  # not intersecting
        w = x1 - x0
        h = y1 - y0
        zero_area = (w < EPS or h < EPS)
        t = d.get("type")
        fill = d.get("fill")
        if t == "s" or fill is None:
            key = "stroke"
        else:
            is_black = all(abs(c) <= 0.005 for c in fill[:3])
            is_white = all(abs(c - 1.0) <= 0.005 for c in fill[:3])
            if is_black:
                key = "black_fill_zero_area" if zero_area else "black_fill_normal"
            elif is_white:
                key = "white_fill_zero_area" if zero_area else "white_fill_normal"
            else:
                key = "other_fill_zero_area" if zero_area else "other_fill_normal"
        counts[key] += 1
        if len(samples[key]) < 3:
            samples[key].append(
                (t, tuple(round(c, 3) for c in fill) if fill else None,
                 (round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)))
            )
    return counts, samples


def report(label, pdf_path):
    print(f"\n=== {label}: {pdf_path.name} ===")
    if not pdf_path.is_file():
        print(f"   (missing — skip)")
        return None
    doc = pdf_engine.open_pdf(pdf_path)
    try:
        page = pdf_engine.get_page(doc, 0)
        rect_w = float(page.rect.width)
        rect_h = float(page.rect.height)
        intrinsic = pdf_engine.page_intrinsic_rotation(doc, 0)
        print(f"   page rect: {rect_w:.1f} x {rect_h:.1f} pt  intrinsic_rot={intrinsic}")
        unrot = pdf_engine.map_rect_to_unrotated(page, REGION_PT)
        rt = (unrot.x0, unrot.y0, unrot.x1, unrot.y1)
        print(f"   region unrotated: ({rt[0]:.2f}, {rt[1]:.2f}) -> ({rt[2]:.2f}, {rt[3]:.2f})")
        words = pdf_engine.get_text_words_in_rect(page, rt)
        print(f"   text words: {len(words)}  samples={[w[4] for w in words[:5]]}")
        counts, samples = _classify(page, rt)
        for k, v in counts.items():
            print(f"   {k:>30}: {v}")
        for k, sl in samples.items():
            if sl:
                print(f"     {k} samples:")
                for s in sl:
                    print(f"       {s}")
        # Total drawings on page (sanity check the user's "1742" claim).
        total = sum(1 for _ in page.get_drawings())
        print(f"   total drawings on page: {total}")
        return counts
    finally:
        pdf_engine.close(doc)


def main() -> int:
    orig_counts = report("ORIG (untouched supplier PDF)", ORIG_PDF)
    swap_counts = report("SWAP (current broken LIVE output)", SWAP_PDF)
    if orig_counts and swap_counts:
        print("\n=== DIFF (swap - orig) inside framed region ===")
        for k in orig_counts:
            d = swap_counts.get(k, 0) - orig_counts.get(k, 0)
            if d:
                print(f"   {k:>30}: {d:+d}  (orig={orig_counts[k]}, swap={swap_counts[k]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
