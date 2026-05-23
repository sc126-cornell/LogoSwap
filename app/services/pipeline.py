"""Deferred-mutation removal pipeline (D-05) — orchestrates a /process job.

:func:`process_job` is the ONLY place a session's PDF is mutated, and it mutates the
``work/`` copy exclusively — never the immutable original (chmod 0o444). Each run first
RESETS the work copy from the pristine original (WR-01) so every apply / "重新套用" is
computed from the unmutated document and never accumulates stale redactions. For each region
in the :class:`~app.models.JobSpec` it:

  1. clamps the untrusted image-pixel rect to the page box (threat T-02-01),
  2. maps it to the unrotated page via the proven Plan 02-01 mapper
     (``coords.pixels_to_pdf_rect`` — REMOVE-03; placement correctness inherited),
  3. truly removes the content inside it. Phase 4 D-05 dispatches per-region:
     :func:`pdf_engine.rect_overlaps_image` → :func:`redact.remove_region_raster`
     (raster branch, IMAGE_PIXELS); otherwise :func:`redact.remove_region_vector`
     (vector branch, IMAGE_NONE — original Phase 2 path, REMOVE-01),

then saves the redacted result BACK to the work copy (so the result-render endpoint can
show the "移除結果" after-image) AND to ``outputs/原名_logoswap.pdf`` for download
(OUTPUT-01 / D-06), keeping ALL pages (D-07). The original's bytes are unchanged across the
whole run (D-05) — proven by an automated SHA-256 test.

PURITY (threat T-02-03): no fitz import here. PDF open/page/save go through
:mod:`app.services.pdf_engine`; coordinate math through :mod:`app.services.coords`;
removal through :mod:`app.services.redact`.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path

from .. import storage
from . import coords, integrity, logo, pdf_engine, redact, render

# WR-05: the export stem is the (possibly CJK) display name and is reflected into the
# Content-Disposition header. Bound it so a 10 KB name cannot reach the header, and below we
# strip control characters so embedded CR/LF/NUL bytes never do either.
MAX_STEM_LEN = 128


class PipelineError(Exception):
    """Typed pipeline failure carrying a stable ``code`` (mapped to a structured 4xx)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _logoswap_name(filename: str | None) -> str:
    """Build the export filename ``{stem}_logoswap.pdf`` from the stored display name (D-06).

    The display name may be CJK (e.g. ``圖紙.pdf`` -> ``圖紙_logoswap.pdf``). This is only
    ever used in the Content-Disposition header / as the output basename intent; the actual
    on-disk path in ``outputs/`` is fixed and session-scoped (threat T-02-06).

    WR-05: the stem is sanitized before use — control characters (Unicode category ``Cc``,
    incl. CR/LF/TAB/NUL) are stripped and the result is capped to :data:`MAX_STEM_LEN` — so an
    adversarial display name (very long, or containing control bytes that survived earlier
    sanitization) cannot be reflected into the response header. Header injection is already
    mitigated by percent-encoding at the call site; this closes the unbounded-length /
    control-char gap at the source. Falls back to ``source`` when nothing safe remains.
    """
    name = filename or "source.pdf"
    stem = Path(name).stem or "source"
    # Strip control characters (Cc) — defends the Content-Disposition header (WR-05).
    stem = "".join(ch for ch in stem if unicodedata.category(ch) != "Cc")
    # Collapse any residual whitespace runs and trim, then cap the length.
    stem = re.sub(r"\s+", " ", stem).strip()
    stem = stem[:MAX_STEM_LEN].strip()
    if not stem:
        stem = "source"
    return f"{stem}_logoswap.pdf"


def output_filename(session_id: str) -> str:
    """Return the export filename for a session (reads the stored display name)."""
    meta = storage.read_session_meta(session_id)
    display = meta.get("filename") if meta else None
    return _logoswap_name(display)


def output_path(session_id: str) -> Path:
    """Absolute path of the exported PDF in the session's outputs dir."""
    return storage.outputs_dir(session_id) / output_filename(session_id)


def process_job(session_id: str, job_spec) -> dict:
    """Redact every region of ``job_spec`` on the WORK copy and export the result.

    ``job_spec`` is a validated :class:`~app.models.JobSpec` (dpi + regions). Returns a
    small result dict::

        {
          "output_filename": "原名_logoswap.pdf",
          "page_count": <unchanged>,
          "regions": [{"page": int, "removed": bool, "clamped": bool}, ...],
          "logo_skipped": bool,  # WR-02: a requested logo could not be placed (pure removal)
        }

    Raises :class:`PipelineError` for an out-of-range page index, and propagates
    :class:`redact.RedactError` if true-removal could not be verified for a region. The
    document is always closed.
    """
    work = storage.work_path(session_id)
    pristine = storage.pristine_path(session_id)

    # Deferred-mutation invariant (D-05 / threat T-02-05 / Phase 4 reset-from-pristine):
    # the work copy is the editing substrate; the pristine PDF is the immutable reset
    # source. Assert the paths differ as a structural guard so a future refactor cannot
    # silently point this at the reset source. (originals/ is also untouched — for image
    # uploads originals/ holds raw PNG/JPG/TIFF bytes that are NOT a PDF, so the pipeline
    # must never try to open them; for PDF uploads originals/ stays SHA-256-invariant.)
    if Path(work).resolve() == Path(pristine).resolve():
        raise PipelineError(
            "work_copy_misconfigured",
            "內部錯誤:工作副本路徑與初始 PDF 副本相同,已中止以保護工作流程。",
        )

    # Phase 5 (Plan 05-02 D-C2): verify the SHA-256 baseline of originals/source.pdf
    # against the value recorded in meta.json at ingest. Failure → IntegrityError with
    # a typed code (original_tampered | session_corrupted), which the integrity layer
    # has ALREADY converted into a .corrupted sentinel before re-raising — so the next
    # /process on this sid short-circuits at the route layer (410). We re-raise as a
    # PipelineError so the existing main.py exception handler can map it to a status:
    # _PROCESS_STATUS["original_tampered"] = 503 / ["session_corrupted"] = 410
    # (added in Task 3). Verify runs BEFORE the reset-from-pristine copy so a tampered
    # session never even gets its work copy written.
    try:
        integrity.verify_original_hash(session_id)
    except integrity.IntegrityError as err:
        raise PipelineError(err.code, err.message) from err

    # WR-01: reset the work copy from the PRISTINE PDF snapshot before redacting, so every
    # apply (and every "重新套用") is computed from the unmutated document. Without this, a
    # prior successful run leaves the work copy already-redacted, and a second apply with a
    # different region set would operate on that stale substrate (accumulating removals /
    # masking the real result). copyfile copies CONTENT only — the work copy stays writable
    # and never mutates the read-only pristine source. Phase 4: pristine/ is guaranteed to be
    # a valid PDF (PDF uploads write it byte-identical to originals/; image uploads write the
    # normalized A4 PDF here), so this open + reset never fails on a non-PDF stream.
    if not Path(pristine).is_file():
        raise PipelineError(
            "work_copy_misconfigured",
            "內部錯誤:找不到初始 PDF 副本,無法重設工作副本。",
        )
    Path(work).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pristine, work)

    # The client's ``dpi`` is the REQUESTED render DPI (the ceiling the overlay measured
    # against). It is NOT trusted as the per-page scale: render may have reduced the
    # *effective* DPI below it for a large-MediaBox page via fit_dpi_to_pixel_budget
    # (CR-01). We re-derive the effective DPI PER PAGE here, by construction identical to
    # what render.page_meta / render.render_page produced, so the client overlay (which
    # measured px against those reduced dims) and the server mapping cannot disagree on
    # scale. This closes the silent "wrong area redacted" pitfall the phase guards against.
    requested_dpi = render.clamp_dpi(job_spec.dpi)

    # Per-page USER rotation (D-12): page-index -> degrees (0/90/180/270), already normalized by
    # JobSpec. We BAKE these onto the download output (the user asked for a rotated PDF) and we
    # also set them on the work page BEFORE coords mapping so pixels_to_pdf_rect derotates against
    # the SAME effective orientation the user framed on (intrinsic + user). After saving the
    # download we RESET each page back to its intrinsic rotation before saving the work copy, so
    # the work copy stays at intrinsic rotation and the result-render endpoint re-applies the
    # rotation transiently (symmetric with the 原圖 path) — no double rotation.
    rotations: dict[int, int] = dict(getattr(job_spec, "rotations", {}) or {})

    doc = pdf_engine.open_pdf(work)
    try:
        n_pages = pdf_engine.page_count(doc)
        results: list[dict] = []

        # Validate rotation page indices and record each touched page's INTRINSIC rotation so we
        # can restore it before saving the work copy. Then apply the effective rotation up front
        # so EVERY rotated page (region or not) is baked into the download output.
        intrinsic_by_page: dict[int, int] = {}
        for page_idx, user_deg in rotations.items():
            if page_idx < 0 or page_idx >= n_pages:
                raise PipelineError(
                    "page_out_of_range",
                    f"旋轉指定的頁碼超出範圍:第 {page_idx} 頁(共 {n_pages} 頁)。",
                )
            if user_deg % 360 == 0:
                continue
            page = pdf_engine.get_page(doc, page_idx)
            intrinsic_by_page[page_idx] = pdf_engine.page_intrinsic_rotation(doc, page_idx)
            pdf_engine.set_page_rotation(
                page, (intrinsic_by_page[page_idx] + user_deg) % 360
            )

        # Resolve the OPTIONAL global logo ONCE outside the loop (D-01): a manifest-allowlist
        # lookup yielding validated PNG bytes. WR-02: placement is BEST-EFFORT and degrades
        # gracefully to pure removal — consistent with the catalog's "empty/missing library ->
        # pure removal" philosophy (A2 / D-04). The picker only ever surfaces ids that passed
        # validation at list time, but an asset can be replaced/corrupted on disk (or
        # MAX_LOGO_BYTES lowered) between the list call and this process call. Rather than abort
        # an otherwise-valid redaction job (losing ALL the user's framing work over a
        # logo-library problem unrelated to it), we catch LogoError here, skip placement, and
        # surface a per-job ``logo_skipped`` flag the frontend can act on. The redaction + export
        # still complete (pure removal). A logo_not_found from a stale/cleared selection likewise
        # degrades rather than failing the whole run.
        # auto_logo (per-region by framed shape) takes precedence over the single global logo_id.
        # In auto mode we resolve+embed lazily per CHOSEN id inside the loop, caching bytes and
        # the embedded xref per id so repeats of the same logo dedup (Pitfall 4) while two
        # different logos across regions each embed once.
        auto_logo = bool(getattr(job_spec, "auto_logo", False))
        logo_bytes = None
        logo_skipped = False
        logo_bytes_cache: dict[str, bytes] = {}
        logo_xrefs: dict[str, int] = {}
        if auto_logo:
            pass  # per-region selection happens in the loop
        elif getattr(job_spec, "logo_id", None):
            try:
                logo_bytes = logo.resolve(job_spec.logo_id)
            except logo.LogoError:
                logo_skipped = True
        logo_xref = 0

        for region in job_spec.regions:
            page_no = region.page
            if page_no < 0 or page_no >= n_pages:
                raise PipelineError(
                    "page_out_of_range",
                    f"區域指定的頁碼超出範圍:第 {page_no} 頁(共 {n_pages} 頁)。",
                )

            page = pdf_engine.get_page(doc, page_no)

            # Re-derive the page's EFFECTIVE render DPI exactly as the render endpoints do
            # (clamp -> fit to the pixel budget). On a normal page this equals requested_dpi;
            # on an oversized MediaBox it is the same reduced value /meta reported and the
            # overlay measured against — so px_rect, the projection, and this mapping all
            # agree on ONE effective DPI for this page (CR-01).
            dims = pdf_engine.page_dimensions(doc, page_no)
            effective_dpi = render.fit_dpi_to_pixel_budget(
                requested_dpi, dims["page_w_pt"], dims["page_h_pt"]
            )

            # Compute the page's rendered pixel box at the EFFECTIVE dpi so we can clamp the
            # untrusted client rect to it (T-02-01). We need the DISPLAYED pixel dims for
            # clamp_px_rect, which are (page_w_pt, page_h_pt) of the DISPLAYED rect scaled by
            # effective_dpi/72 — identical to the img_w/img_h /meta returned for this page.
            scale = effective_dpi / 72.0
            img_w = dims["page_w_pt"] * scale
            img_h = dims["page_h_pt"] * scale

            clamped_px, was_clamped = coords.clamp_px_rect(
                region.px_rect, img_w, img_h
            )
            pdf_rect = coords.pixels_to_pdf_rect(clamped_px, effective_dpi, page)

            # Phase 4 D-05: per-region dispatch by image-overlap probe in PDF point
            # space. ``rect_overlaps_image`` takes an unrotated-page rect — exactly what
            # ``pixels_to_pdf_rect`` produces — so no extra conversion. True → route to
            # ``remove_region_raster`` (images=IMAGE_PIXELS + text-only residual
            # assertion); False → route to ``remove_region_vector`` (Phase 2 path
            # unchanged, images=IMAGE_NONE + text + drawings assertions).
            if pdf_engine.rect_overlaps_image(page, pdf_rect):
                removed = redact.remove_region_raster(page, pdf_rect)
            else:
                removed = redact.remove_region_vector(page, pdf_rect)

            # Place the logo STRICTLY AFTER remove_region (which runs apply_redactions
            # internally) so it is not redacted away (Pitfall 1), on the SAME pdf_rect, and
            # REGARDLESS of `removed` (the user framed it as a replacement target — A1).
            # First placement embeds (stream=bytes) and returns the xref; subsequent regions
            # reuse that xref (stream=None) to dedup the one global logo (D-01 / Pitfall 4).
            if auto_logo:
                # Pick the logo whose native aspect best matches THIS region's framed shape.
                # Use the CLAMPED PIXEL rect aspect (display space, what the user framed) — it
                # equals the pdf_rect aspect at this dpi and needs no fitz here. Resolve+embed
                # once per chosen id; reuse that id's xref for repeats (dedup, Pitfall 4). A bad
                # asset / empty library degrades to pure removal for that region (WR-02 / D-04).
                rect_w = clamped_px[2] - clamped_px[0]
                rect_h = clamped_px[3] - clamped_px[1]
                chosen = logo.pick_logo_id_for_rect(rect_w, rect_h)
                if chosen is None:
                    logo_skipped = True
                else:
                    try:
                        if chosen not in logo_bytes_cache:
                            logo_bytes_cache[chosen] = logo.resolve(chosen)
                        prev_xref = logo_xrefs.get(chosen, 0)
                        logo_xrefs[chosen] = pdf_engine.place_logo(
                            page,
                            pdf_rect,
                            stream=(logo_bytes_cache[chosen] if prev_xref == 0 else None),
                            xref=prev_xref,
                        )
                    except logo.LogoError:
                        logo_skipped = True
            elif logo_bytes is not None:
                logo_xref = pdf_engine.place_logo(
                    page,
                    pdf_rect,
                    stream=(logo_bytes if logo_xref == 0 else None),
                    xref=logo_xref,
                )

            results.append(
                {"page": page_no, "removed": removed, "clamped": was_clamped}
            )

        # Save the redacted result to BOTH the work copy (the result-render substrate) and
        # the outputs file for download. Pitfall 9: garbage=4, deflate=True, clean=True undoes
        # redaction bloat.
        out_name = output_filename(session_id)
        out_dir = storage.outputs_dir(session_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / out_name

        # WR-05: save the WORK COPY FIRST, then bake the user rotation and save the OUTPUT.
        # The two saves are asymmetric (work stays at intrinsic rotation so the result-render
        # endpoint can re-apply rotation transiently, symmetric with 原圖; output keeps rotation
        # baked for download). The PRIOR order (output first, then reset rotations, then work)
        # left a stale-work failure mode: if saving the work copy failed (disk full, permission),
        # the output PDF was already on disk but the work copy had been reset to the pristine
        # original at the start (shutil.copyfile, line ~129) and was NOT redacted. /result then
        # downloaded a redacted PDF while /result/pages/.../image (which renders the work copy)
        # showed the UNREDACTED page — before/after preview lied about the download contents.
        #
        # Reorder + write-to-tmp + atomic swap-at-end keeps the two artifacts in lockstep:
        #   1. Reset each rotated page back to its intrinsic rotation.
        #   2. Save the work copy to a tmp file.
        #   3. Re-apply the user rotation for the output bake.
        #   4. Save the output PDF to a tmp file.
        #   5. Atomically swap BOTH tmp files into place outside the open doc.
        # If steps 2 or 4 fail, neither final artifact has been written: the work copy is still
        # the pristine original from the start-of-run reset and there is NO output file (so
        # /result returns the same 404 result_not_ready as before any apply). The before/after
        # preview can never disagree with the downloaded artifact.

        # Step 1: reset rotated pages to intrinsic (the work copy substrate is symmetric with 原圖).
        for page_idx, intrinsic in intrinsic_by_page.items():
            pdf_engine.set_page_rotation(pdf_engine.get_page(doc, page_idx), intrinsic)

        # Step 2: save the work copy first. If THIS fails, we bail with no half-state on disk.
        work_tmp = Path(work).with_suffix(".redacted.tmp.pdf")
        pdf_engine.save_doc(doc, work_tmp)

        # Step 3: re-apply the user rotation onto the in-memory doc for the download bake.
        for page_idx, user_deg in rotations.items():
            if user_deg % 360 == 0:
                continue
            pdf_engine.set_page_rotation(
                pdf_engine.get_page(doc, page_idx),
                (intrinsic_by_page[page_idx] + user_deg) % 360,
            )

        # Step 4: save the output to its own tmp so a failure here leaves no half-written
        # out_file on disk either.
        out_tmp = out_file.with_suffix(".swap.tmp.pdf")
        try:
            pdf_engine.save_doc(doc, out_tmp)
        except Exception:
            # If the output save fails, clean up BOTH tmps so we leave no stray *.tmp.* files
            # behind. The work copy on disk is still the pristine original from the start-of-run
            # reset, so the run as a whole is a clean failure (no output, work unchanged).
            try:
                Path(work_tmp).unlink()
            except OSError:
                pass
            try:
                out_tmp.unlink()
            except OSError:
                pass
            raise
    finally:
        pdf_engine.close(doc)

    # Step 5: atomically swap both tmp files into place. .replace is atomic on the same
    # filesystem; the worst-case partial state (work swapped, out_file not yet replaced) leaves
    # the output absent, which the download endpoint surfaces as 404 result_not_ready — never
    # the inverse stale-work failure WR-05 closed.
    Path(work_tmp).replace(work)
    Path(out_tmp).replace(out_file)

    return {
        "output_filename": out_name,
        "page_count": n_pages,
        "regions": results,
        # WR-02: true only when a logo was REQUESTED but could not be resolved/placed; the
        # redaction + export still completed (pure removal). The frontend surfaces a notice so
        # the user knows the logo was not placed without losing the run.
        "logo_skipped": logo_skipped,
    }
