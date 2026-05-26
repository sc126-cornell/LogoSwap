"""Hotfix #05 / dCt-residue live verification — diagnostic mode.

Runs the FIXED redaction pipeline on the reproduction PDF
(``3013A-13A-C6-XX-3D02-A01-00040.pdf``) with the same framed region the UAT
captured (PDF pt (603, 480) -> (826, 511)). Bypasses the pipeline's RedactError so
we can introspect WHICH residual category survived even if the strict assertion
trips.

Scratch script — does NOT live in tests/. Run with:
    .venv/Scripts/python.exe _verify_dct_residue_fix.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import config  # noqa: E402
from app.services import coords, pdf_engine, redact  # noqa: E402

REPRO_PDF = REPO_ROOT / "3013A-13A-C6-XX-3D02-A01-00040.pdf"
REGION_PT = (603.0, 480.0, 826.0, 511.0)
DPI = config.DEFAULT_DPI


def main() -> int:
    if not REPRO_PDF.is_file():
        print(f"[verify] FAIL: reproduction PDF not found at {REPRO_PDF}")
        return 2

    # Open a WORK copy directly (skip storage layer to make introspection straightforward).
    work_path = REPO_ROOT / "_verify_work_copy.pdf"
    work_path.write_bytes(REPRO_PDF.read_bytes())
    doc = pdf_engine.open_pdf(work_path)
    try:
        page = pdf_engine.get_page(doc, 0)
        rect_w_pt = float(page.rect.width)
        rect_h_pt = float(page.rect.height)
        intrinsic_rot = pdf_engine.page_intrinsic_rotation(doc, 0)
        print(
            f"[verify] page.rect (displayed): {rect_w_pt:.1f} x {rect_h_pt:.1f} pt "
            f"intrinsic_rotation={intrinsic_rot}"
        )

        # The displayed region in PDF points; convert directly to an unrotated-page Rect
        # without bouncing through pixel space.
        unrot = pdf_engine.map_rect_to_unrotated(page, REGION_PT)
        rt = (unrot.x0, unrot.y0, unrot.x1, unrot.y1)
        print(
            f"[verify] region pt: {REGION_PT} -> unrotated page rect: "
            f"({rt[0]:.2f}, {rt[1]:.2f}) -> ({rt[2]:.2f}, {rt[3]:.2f})"
        )

        # Pre-condition probes.
        pre_words = pdf_engine.get_text_words_in_rect(page, rt)
        pre_draws = pdf_engine.get_drawings_intersecting(page, rt)
        pre_white = pdf_engine.get_white_fill_drawings_intersecting(page, rt)
        print(
            f"[verify] PRE words={len(pre_words)} intersecting_drawings={len(pre_draws)} "
            f"whitepaint={len(pre_white)}"
        )

        # Run the VECTOR branch directly (the dispatcher would also pick it because the
        # framed region does not overlap an image XObject — Evidence: page.get_images() = []
        # in the UAT artefact).
        try:
            result = redact.remove_region_vector(page, unrot)
            print(f"[verify] remove_region_vector returned removed={result}")
        except redact.RedactError as exc:
            print(f"[verify] RedactError raised by the new strict assertion: {exc.code}: {exc.message}")
            # Even when raised, apply_redactions already ran — the page state is post-redaction.
            # Continue to introspect what survived so we know if it is the dCt shape or
            # something else.

        # Post-condition probes (the dispatch's residual checks, computed independently).
        post_words = pdf_engine.get_text_words_in_rect(page, rt)
        post_draws = pdf_engine.get_drawings_intersecting(page, rt)
        post_white = pdf_engine.get_white_fill_drawings_intersecting(page, rt)
        post_inside = pdf_engine.get_drawings_fully_inside(page, rt)
        print(
            f"[verify] POST words={len(post_words)} intersecting_drawings={len(post_draws)} "
            f"fully_inside={len(post_inside)} whitepaint={len(post_white)}"
        )

        if post_words:
            print(f"[verify]   sample words: {[w[4] for w in post_words[:5]]}")
        if post_draws:
            sample = [
                (
                    d.get("type"),
                    tuple(round(c, 3) for c in (d.get("fill") or (None, None, None)))
                    if d.get("fill") is not None else None,
                    tuple(round(c, 2) for c in (d["rect"].x0, d["rect"].y0, d["rect"].x1, d["rect"].y1)),
                )
                for d in post_draws[:8]
            ]
            print(f"[verify]   sample post drawings (type, fill, bbox): {sample}")
        if post_white:
            sample = [
                tuple(round(c, 2) for c in (d["rect"].x0, d["rect"].y0, d["rect"].x1, d["rect"].y1))
                for d in post_white[:8]
            ]
            print(f"[verify]   sample post whitepaint bboxes: {sample}")

        # The core claim: under LINE_ART_REMOVE_IF_TOUCHED, the dCt-residue signature
        # (non-degenerate WHITE fills inside the framed rect) must be 0.
        if post_white:
            print(
                f"[verify] >>> WHITEPAINT RESIDUE STILL PRESENT: "
                f"{len(post_white)} non-degenerate white-fill drawings <<<"
            )
            return 1

        # Tolerate ONLY legitimate cover_zero_area_artefacts paint (type='f', fill=(1,1,1),
        # source bbox was zero-area; the cover routine paints ±0.5pt covers, themselves
        # tiny). If post_draws contains anything else, that is a real survivor.
        non_cover = []
        for d in post_draws:
            d_rect = d["rect"]
            is_cover_paint = (
                d.get("type") == "f"
                and d.get("fill") == (1.0, 1.0, 1.0)
                and (d_rect.width <= 1.5 and d_rect.height <= 1.5)  # tiny ±0.5pt cover
            )
            if not is_cover_paint:
                non_cover.append(d)
        if non_cover:
            print(f"[verify] >>> NON-COVER DRAWINGS REMAIN: {len(non_cover)} <<<")
            sample = [
                (
                    d.get("type"),
                    d.get("fill"),
                    (round(d["rect"].x0, 2), round(d["rect"].y0, 2), round(d["rect"].x1, 2), round(d["rect"].y1, 2)),
                )
                for d in non_cover[:8]
            ]
            print(f"[verify]   sample: {sample}")
            return 1

        if post_words:
            print(f"[verify] >>> RESIDUAL TEXT REMAINS: {len(post_words)} <<<")
            return 1

        print("[verify] >>> FIX VERIFICATION PASSED <<<")
        print("[verify] (whitepaint residue=0, no non-cover drawings, no text — dCt shape gone)")
        return 0
    finally:
        pdf_engine.close(doc)


if __name__ == "__main__":
    sys.exit(main())
