"""v1.1 LIVE-UAT regression — Adobe Illustrator ``/PieceInfo`` private-artwork strip.

Debug session: ``.planning/debug/ai-pieceinfo-residual-mark.md``.

THE HOLE
--------
PDFs saved from Adobe Illustrator with "preserve editing capabilities" embed a COMPLETE
editable copy of the artwork — including the supplier mark — under page
``/PieceInfo <</Illustrator N 0 R>>`` -> ``<</LastModified .. /Private M 0 R>>`` ->
``%!PS-Adobe`` PGF private-data streams. LogoSwap's redaction (``apply_redactions`` + the
Phase 7 Option-B content-stream surgery) only edits the rendered page ``/Contents``,
never this private copy. Every NORMAL renderer (MuPDF / PDFium / Acrobat / browsers) then
shows the mark removed, but Adobe Illustrator reads its OWN private artwork and the supplier
mark reappears fully editable — defeating the v1.1 core value ("truly remove, not cover")
for exactly the modeled Illustrator-class-editor attacker.

THE FIX (under test)
--------------------
``app.services.pdf_engine.strip_piece_info`` removes ``/PieceInfo`` from every page and the
catalog; ``pdf_engine.save_doc`` calls it immediately before ``doc.save(garbage=4,
deflate=True, clean=True)`` so the orphaned PGF private streams are garbage-collected out of
the file. A plain GC alone does NOT remove them (they stay reachable via the PieceInfo chain
until the reference is cut). Stripping page-piece data changes no visible content.

WHY NO COMMITTED SUPPLIER FIXTURE
---------------------------------
The real LIVE-UAT file's PGF streams retain supplier IP (``%%Title``, ``%%For`` author,
``%%DocumentFonts`` + the recoverable mark artwork). Committing them to a PUBLIC repo (AGPL
§13) is forbidden. So — mirroring ``tests/conftest.py``'s "build fixtures in-memory, never
commit binaries" philosophy — these tests SYNTHESIZE an Illustrator-style PDF carrying the
exact ``/PieceInfo -> /Illustrator -> /Private -> %!PS-Adobe`` attack structure with purely
synthetic content (no supplier IP). The fitz license header is the project convention (the
AGPL guard scope is ``app/**/*.py``; ``tests/`` is out of scope — ``tests/conftest.py:12``).

FINAL ACCEPTANCE remains a human Adobe Illustrator open-and-try-to-recover (per project
principle ``feedback_illustrator_verification``); this automated PieceInfo/PGF-stream check
is a strong proxy, not a full substitute.
"""

from __future__ import annotations

import fitz  # only the test harness may use fitz directly to BUILD fixtures (conftest.py:12)
import numpy as np
import pytest

from app.models import JobSpec, RegionMark
from app.services import ingest, pdf_engine, pipeline


# --- Synthetic Illustrator-style PDF builder (no committed binary, no supplier IP) ----

# The visible "supplier mark" box — placed where the framed redaction rect will sit.
_MARK_RECT = fitz.Rect(50.0, 50.0, 200.0, 120.0)
# Body content kept OUTSIDE the mark rect, to prove the strip never touches visible content.
_BODY_TEXT_POINT = (230.0, 220.0)
_PAGE_W, _PAGE_H = 400.0, 300.0

# Synthetic PGF private stream. Structurally identical to a real Illustrator
# ``/PieceInfo`` PGF carrier (``%!PS-Adobe`` + ``%%Creator: Adobe Illustrator`` + an
# editable path), but every byte is invented — NO supplier name, title, font, or artwork.
_SYNTHETIC_PGF = (
    b"%!PS-Adobe-3.0 \r\n"
    b"%%Creator: Adobe Illustrator(R) 16.0\r\n"
    b"%AI5_FileFormat 12.0\r\n"
    b"%%BoundingBox: 0 0 400 300\r\n"
    b"%% SYNTHETIC editable original-artwork copy (no real supplier IP)\r\n"
    b"0 0 m 150 0 l 150 70 l 0 70 l f\r\n"
    b"%%EOF\r\n"
)


def _build_illustrator_style_pdf(
    *, with_catalog_piece_info: bool = False
) -> bytes:
    """Return bytes of a 1-page PDF carrying the Illustrator ``/PieceInfo`` attack surface.

    Structure (mirrors the LIVE-UAT forensic chain):
        page ``/PieceInfo`` -> ``<</Illustrator A 0 R>>``
        object A           -> ``<</LastModified .. /Private B 0 R>>``
        object B (stream)  -> ``%!PS-Adobe`` PGF private editable-artwork copy

    Visible content: a filled "mark" box inside ``_MARK_RECT`` + body text outside it.

    When ``with_catalog_piece_info`` is True, an additional ``/PieceInfo`` is attached to
    the document catalog (some Illustrator exports carry document-level page-piece data),
    so the catalog-strip branch is exercised too.
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
        # Visible "supplier mark" (the thing the user frames + removes).
        page.draw_rect(_MARK_RECT, fill=(0.0, 0.0, 0.0), color=None)
        # Body content well outside the mark rect — must survive untouched.
        page.insert_text(_BODY_TEXT_POINT, "KEEP THIS BODY TEXT")

        # Build the PGF private stream object.
        priv_xref = doc.get_new_xref()
        doc.update_object(priv_xref, "<<>>")
        doc.update_stream(priv_xref, _SYNTHETIC_PGF)
        # Build the /Illustrator dict pointing at the Private stream.
        ai_xref = doc.get_new_xref()
        doc.update_object(
            ai_xref,
            f"<</LastModified (D:20241018140806+09'00') /Private {priv_xref} 0 R>>",
        )
        # Attach page /PieceInfo -> <</Illustrator ai_xref 0 R>>.
        doc.xref_set_key(page.xref, "PieceInfo", f"<</Illustrator {ai_xref} 0 R>>")

        if with_catalog_piece_info:
            cat_priv = doc.get_new_xref()
            doc.update_object(cat_priv, "<<>>")
            doc.update_stream(cat_priv, _SYNTHETIC_PGF)
            cat_ai = doc.get_new_xref()
            doc.update_object(cat_ai, f"<</Private {cat_priv} 0 R>>")
            doc.xref_set_key(
                doc.pdf_catalog(), "PieceInfo", f"<</Illustrator {cat_ai} 0 R>>"
            )

        # tobytes WITHOUT garbage collection — keep the PGF reachable via PieceInfo so the
        # built fixture genuinely carries the attack surface (a clean GC here would not
        # remove it anyway, but we avoid mutating the fixture pre-test on principle).
        return doc.tobytes()
    finally:
        doc.close()


# --- Stream / structure probes (test-harness fitz, no production code) ----------------


def _count_ps_adobe_streams(pdf_bytes: bytes) -> int:
    """Count DECOMPRESSED streams beginning with the ``%!PS-Adobe`` PGF marker.

    Real Illustrator PGF streams are frequently stored inside compressed object streams
    (``/ObjStm``), so a raw byte search misses them — every stream must be decompressed
    via ``xref_stream`` before scanning (this is what fooled the early LIVE-UAT renderer
    checks into thinking the file was clean)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        n = 0
        for x in range(1, doc.xref_length()):
            if not doc.xref_is_stream(x):
                continue
            try:
                s = doc.xref_stream(x)
            except Exception:  # noqa: BLE001 — a malformed/undecodable stream is not a PGF hit
                continue
            if b"%!PS-Adobe" in s or b"Adobe Illustrator" in s:
                n += 1
        return n
    finally:
        doc.close()


def _piece_info_present(pdf_bytes: bytes) -> tuple[list, object]:
    """Return (per-page PieceInfo values, catalog PieceInfo value).

    A value of ``("null", "null")`` means the key is absent / JS-null (stripped)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pages = [doc.xref_get_key(doc[i].xref, "PieceInfo") for i in range(doc.page_count)]
        catalog = doc.xref_get_key(doc.pdf_catalog(), "PieceInfo")
        return pages, catalog
    finally:
        doc.close()


def _nonwhite_pixel_count(pdf_bytes: bytes, page_index: int = 0) -> int:
    """Count visible (non-white) pixels on a page — a proxy for 'content still renders'."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pm = doc[page_index].get_pixmap(alpha=False)
        arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
        return int((arr < 250).any(axis=2).sum())
    finally:
        doc.close()


def _region_white_pct(pdf_bytes: bytes, rect: fitz.Rect, page_index: int = 0) -> float:
    """White-coverage percent inside ``rect`` (mirrors the illustrator-attack white gate)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pm = doc[page_index].get_pixmap(matrix=fitz.Matrix(4, 4), clip=rect, alpha=False)
        arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
        return round(100 * np.all(arr >= 250, axis=2).sum() / arr[..., 0].size, 2)
    finally:
        doc.close()


# --- Sanity: the synthetic fixture genuinely carries the attack surface ----------------


def test_synthetic_fixture_carries_pieceinfo_attack_surface():
    """The builder must produce a REAL attack surface, else the strip tests are vacuous.

    Guards against a future PyMuPDF/build change silently dropping the PGF on ``tobytes``
    — if that happened the strip assertions below would pass for the wrong reason."""
    raw = _build_illustrator_style_pdf()
    pages, catalog = _piece_info_present(raw)
    assert pages[0][0] == "dict", f"fixture page /PieceInfo missing: {pages[0]}"
    assert _count_ps_adobe_streams(raw) >= 1, (
        "fixture must carry at least one live %!PS-Adobe PGF private stream"
    )
    # And the synthetic PGF must contain NO supplier-IP markers (public-repo / AGPL §13).
    assert b"NINGBO" not in _SYNTHETIC_PGF
    assert b"DAN-CHIEF" not in _SYNTHETIC_PGF


# --- Seam-level: pdf_engine.save_doc strips the private artwork -------------------------


@pytest.mark.parametrize("with_catalog_piece_info", [False, True])
def test_save_doc_strips_pieceinfo_and_pgf_streams(tmp_path, with_catalog_piece_info):
    """``save_doc`` must remove page + catalog ``/PieceInfo`` AND GC the PGF streams,
    while leaving visible content byte-for-byte intact (the core LIVE-UAT fix)."""
    raw = _build_illustrator_style_pdf(with_catalog_piece_info=with_catalog_piece_info)

    # Precondition: the input genuinely carries the attack surface.
    assert _count_ps_adobe_streams(raw) >= 1
    nonwhite_before = _nonwhite_pixel_count(raw)
    assert nonwhite_before > 0, "fixture must have visible content to begin with"

    out = tmp_path / "saved.pdf"
    doc = pdf_engine.open_pdf(raw)
    try:
        pdf_engine.save_doc(doc, out)
    finally:
        pdf_engine.close(doc)

    saved = out.read_bytes()
    pages, catalog = _piece_info_present(saved)

    # (a) No page /PieceInfo survives.
    assert all(p[0] == "null" for p in pages), f"page /PieceInfo survived save_doc: {pages}"
    # (a') No catalog /PieceInfo survives.
    assert catalog[0] == "null", f"catalog /PieceInfo survived save_doc: {catalog}"
    # (b) Zero %!PS-Adobe / Illustrator private-data streams remain (orphans GC'd).
    assert _count_ps_adobe_streams(saved) == 0, (
        "PGF private-data streams survived — the supplier mark stays recoverable in Illustrator"
    )
    # (c) Visible content unchanged — stripping page-piece data draws nothing differently.
    assert _nonwhite_pixel_count(saved) == nonwhite_before, (
        "visible content changed after PieceInfo strip — the strip must be content-neutral"
    )


def test_strip_piece_info_return_count_and_no_op():
    """``strip_piece_info`` returns the keys cleared, and is a clean no-op on a plain PDF.

    The no-op path is the common case (non-Illustrator PDFs) and must never write spurious
    keys or alter content — verified via the conftest-style plain vector PDF."""
    # Illustrator-sourced (page + catalog PieceInfo) -> 2 keys cleared.
    ai_doc = pdf_engine.open_pdf(
        _build_illustrator_style_pdf(with_catalog_piece_info=True)
    )
    try:
        removed = pdf_engine.strip_piece_info(ai_doc)
        assert removed == 2, f"expected 2 PieceInfo keys cleared (page + catalog), got {removed}"
        # Idempotent: a second strip finds nothing.
        assert pdf_engine.strip_piece_info(ai_doc) == 0
    finally:
        pdf_engine.close(ai_doc)

    # A plain (non-Illustrator) PDF carries no /PieceInfo -> strip is a 0 no-op.
    plain_doc = fitz.open()
    try:
        plain_doc.new_page(width=_PAGE_W, height=_PAGE_H)
        plain_bytes = plain_doc.tobytes()
    finally:
        plain_doc.close()
    d = pdf_engine.open_pdf(plain_bytes)
    try:
        assert pdf_engine.strip_piece_info(d) == 0
    finally:
        pdf_engine.close(d)


# --- Pipeline-level: a full pure-removal job produces a PieceInfo-free output ----------


def test_process_job_output_has_no_illustrator_private_artwork(
    isolated_data_dir, logo_library
):
    """End-to-end production path: ingest an Illustrator-style PDF, run ``process_job``
    (pure removal, ``logo_id=None``), and assert the downloaded output is free of any
    page/catalog ``/PieceInfo`` and ``%!PS-Adobe`` PGF stream — with the framed mark
    region rendered clean.

    This proves the fix lands on the REAL output artifact (``process_job`` ends in
    ``pdf_engine.save_doc``), not just the seam helper. ``logo_library`` is declared for
    the same conservatism as ``test_illustrator_attack_regression`` (keep ``logo_id=None``
    off the real ``logos/`` dir)."""
    raw = _build_illustrator_style_pdf(with_catalog_piece_info=True)
    assert _count_ps_adobe_streams(raw) >= 1  # precondition: attack surface present

    session = ingest.ingest_upload("illustrator-source.pdf", raw)

    # Frame the visible mark rect (PDF points). dpi=144 matches the cad-glyph manifests;
    # RegionMark.px_rect is points * dpi / 72.0 (= points * 2 at 144 dpi).
    scale = 144 / 72.0
    px_rect = [
        _MARK_RECT.x0 * scale,
        _MARK_RECT.y0 * scale,
        _MARK_RECT.x1 * scale,
        _MARK_RECT.y1 * scale,
    ]
    job_spec = JobSpec(
        dpi=144,
        regions=[RegionMark(page=0, px_rect=px_rect)],
        logo_id=None,
    )
    pipeline.process_job(session.session_id, job_spec)
    output_pdf = pipeline.output_path(session.session_id)
    assert output_pdf.exists(), "process_job 未產出 output PDF"

    out_bytes = output_pdf.read_bytes()
    pages, catalog = _piece_info_present(out_bytes)

    # No recoverable Illustrator private artwork in the SHIPPED output.
    assert all(p[0] == "null" for p in pages), f"output page /PieceInfo survived: {pages}"
    assert catalog[0] == "null", f"output catalog /PieceInfo survived: {catalog}"
    assert _count_ps_adobe_streams(out_bytes) == 0, (
        "output retains %!PS-Adobe PGF streams — mark recoverable in Illustrator"
    )

    # And the framed mark region renders clean (mark removed in normal renderers too).
    white_pct = _region_white_pct(out_bytes, _MARK_RECT)
    assert white_pct >= 98.0, (
        f"framed mark region not visibly cleared — white {white_pct:.2f}% < 98%"
    )
