"""Simulate the Illustrator attack: remove the Option A image XObject so the
underlying supplier vector paths render normally. Then check whether the
supplier brand re-appears in the title-block region.
"""
from __future__ import annotations
import sys
import re
from pathlib import Path
import fitz
import numpy as np

ORIG = Path("samples/3013A-13A-C6-XX-3D02-A01-00040.pdf")
TARGET = Path("3013A-13A-C6-XX-3D02-A01-00040_logoswap (5).pdf")
ATTACK_OUT = Path("_attack_image_xobject_deleted.pdf")
PROOF_RENDER = Path("_attack_proof_supplier_revealed.png")
ORIG_RENDER = Path("_attack_orig_for_comparison.png")

REGION = fitz.Rect(602, 481, 827, 511)


def render_region(pdf_path: Path, rect: fitz.Rect, out_png: Path) -> dict:
    d = fitz.open(pdf_path)
    pm = d[0].get_pixmap(matrix=fitz.Matrix(4, 4), clip=rect, alpha=False)
    pm.save(out_png)
    arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
    d.close()
    return {
        "white_pct": round(100 * np.all(arr >= 250, axis=2).sum() / arr[..., 0].size, 2),
        "black_pct": round(100 * np.all(arr <= 30, axis=2).sum() / arr[..., 0].size, 2),
    }


def main() -> int:
    print("Step 1 — baseline renders")
    print(f"  original supplier region: {render_region(ORIG, REGION, ORIG_RENDER)}")
    print(f"  LogoSwap output region (pre-attack): "
          f"{render_region(TARGET, REGION, Path('_attack_target_pre.png'))}")

    print("\nStep 2 — locate image XObjects in target region")
    src = fitz.open(TARGET)
    page = src[0]
    image_xrefs = []
    for img in page.get_images(full=True):
        xref = img[0]
        for bbox in page.get_image_rects(xref):
            if fitz.Rect(bbox).intersects(REGION):
                image_xrefs.append(xref)
                break
    print(f"  image XObjects to remove: {image_xrefs}")

    print("\nStep 3 — surgical content-stream edit "
          "(remove `q ... /Imxx Do ... Q` blocks referencing target image)")

    # Find the resource name(s) the page uses for these image xrefs.
    res = page.read_contents()
    print(f"  page content stream size: {len(res):,} bytes")

    # Walk the page's /Resources/XObject dict to find which /ImN name maps
    # to each xref.
    page_obj = src.xref_object(page.xref, compressed=False)
    print(f"  page object preview: {page_obj[:400]}...")

    # Easier path: walk every /XObject dict in the page's resources and
    # find the name for our xref. PyMuPDF exposes get_page_xobjects?
    # Fallback: parse the /Resources /XObject sub-dict manually.
    # For this CAD PDF the structure is usually simple.

    # Strategy: get all xobject names → xref mappings via xref tables.
    xobj_names_for_target = set()
    for img_info in page.get_images(full=True):
        xref, _, _, _, _, _, _, name = img_info[:8]
        if xref in image_xrefs:
            xobj_names_for_target.add(name)
    print(f"  target image XObject resource names: {xobj_names_for_target}")

    if not xobj_names_for_target:
        print("  CANNOT locate resource name(s) — falling back to xref deletion")
        for xref in image_xrefs:
            src.delete_object(xref)
        # Also need to delete the entry from page resources or its rendering may error.
    else:
        # Rewrite content stream: blank out any `q ... /<Name> Do ... Q`
        # operator block whose name matches.
        stream_bytes = page.read_contents()
        stream_text = stream_bytes.decode("latin-1")
        for name in xobj_names_for_target:
            # Match the pattern: q (anything not containing q) /<Name> Do (anything) Q
            # CAD PDFs usually emit each image in its own q...Q block.
            pattern = re.compile(
                r"q\b[^Q]*?/" + re.escape(name.lstrip("/")) + r"\s+Do\b[^Q]*?Q\b",
                re.DOTALL,
            )
            new_text, n = pattern.subn("", stream_text)
            print(f"  removed {n} `q ... /{name} Do ... Q` block(s) from stream")
            stream_text = new_text
        # Also blank out any stray `<Name> Do` (in case operator wasn't wrapped in q...Q)
        for name in xobj_names_for_target:
            pattern = re.compile(r"/" + re.escape(name.lstrip("/")) + r"\s+Do\b")
            new_text, n = pattern.subn("", stream_text)
            if n:
                print(f"  also stripped {n} bare `/{name} Do` operator(s)")
            stream_text = new_text
        # Write back to the page's content stream.
        new_bytes = stream_text.encode("latin-1")
        content_xrefs = page.get_contents()
        print(f"  content stream xrefs: {content_xrefs}")
        # If single stream, just update it in place; if multiple, rewrite all
        # the rest to empty and put our edited stream in the first one.
        if len(content_xrefs) == 1:
            src.update_stream(content_xrefs[0], new_bytes, compress=True)
        else:
            src.update_stream(content_xrefs[0], new_bytes, compress=True)
            for xref in content_xrefs[1:]:
                src.update_stream(xref, b"", compress=True)
        print(f"  content stream written: {len(new_bytes):,} bytes (was {len(stream_bytes):,})")

    src.save(ATTACK_OUT, garbage=4, deflate=True)
    src.close()

    print(f"\nStep 4 — render attacked PDF same region")
    after = render_region(ATTACK_OUT, REGION, PROOF_RENDER)
    print(f"  attacked output region: {after}")

    revealed = after['white_pct'] < 95.0 or after['black_pct'] > 1.0
    print(f"\n{'=' * 70}")
    if revealed:
        print(f"!!! ATTACK SUCCEEDED — supplier content REVEALED.")
        print(f"    See {PROOF_RENDER} (compare to {ORIG_RENDER}).")
        print(f"    Option A's image XObject overlay was removable;")
        print(f"    underlying supplier zero-area fills rendered through.")
    else:
        print(f"--- Attack did not visibly reveal supplier content (likely image")
        print(f"    delete via content-stream rewrite did not take effect cleanly,")
        print(f"    or content was actually removed). Inspect renders manually.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
