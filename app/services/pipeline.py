"""Deferred-mutation removal pipeline (D-05) — orchestrates a /process job.

:func:`process_job` is the ONLY place a session's PDF is mutated, and it mutates the
``work/`` copy exclusively — never the immutable original (chmod 0o444). For each region
in the :class:`~app.models.JobSpec` it:

  1. clamps the untrusted image-pixel rect to the page box (threat T-02-01),
  2. maps it to the unrotated page via the proven Plan 02-01 mapper
     (``coords.pixels_to_pdf_rect`` — REMOVE-03; placement correctness inherited),
  3. truly removes the content inside it (``redact.remove_region`` — REMOVE-01),

then saves the redacted result BACK to the work copy (so the result-render endpoint can
show the "移除結果" after-image) AND to ``outputs/原名_logoswap.pdf`` for download
(OUTPUT-01 / D-06), keeping ALL pages (D-07). The original's bytes are unchanged across the
whole run (D-05) — proven by an automated SHA-256 test.

PURITY (threat T-02-03): no fitz import here. PDF open/page/save go through
:mod:`app.services.pdf_engine`; coordinate math through :mod:`app.services.coords`;
removal through :mod:`app.services.redact`.
"""

from __future__ import annotations

from pathlib import Path

from .. import storage
from . import coords, pdf_engine, redact


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
    """
    name = filename or "source.pdf"
    stem = Path(name).stem or "source"
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
        }

    Raises :class:`PipelineError` for an out-of-range page index, and propagates
    :class:`redact.RedactError` if true-removal could not be verified for a region. The
    document is always closed.
    """
    work = storage.work_path(session_id)
    original = storage.original_path(session_id)

    # Deferred-mutation invariant (D-05 / threat T-02-05): we only ever open the work copy
    # for writing; the original is never touched. Assert the paths differ as a structural
    # guard so a future refactor cannot silently point this at the immutable source.
    if Path(work).resolve() == Path(original).resolve():
        raise PipelineError(
            "work_copy_misconfigured",
            "內部錯誤:工作副本路徑與原始檔相同,已中止以保護原始檔。",
        )

    dpi = job_spec.dpi
    doc = pdf_engine.open_pdf(work)
    try:
        n_pages = pdf_engine.page_count(doc)
        results: list[dict] = []

        for region in job_spec.regions:
            page_no = region.page
            if page_no < 0 or page_no >= n_pages:
                raise PipelineError(
                    "page_out_of_range",
                    f"區域指定的頁碼超出範圍:第 {page_no} 頁(共 {n_pages} 頁)。",
                )

            page = pdf_engine.get_page(doc, page_no)

            # Compute the page's rendered pixel box at this dpi so we can clamp the
            # untrusted client rect to it (T-02-01). unrotated_content_box derotates the
            # displayed image box; we need the DISPLAYED pixel dims for clamp_px_rect, which
            # are (page_w_pt, page_h_pt) of the DISPLAYED rect scaled by dpi/72.
            dims = pdf_engine.page_dimensions(doc, page_no)
            scale = dpi / 72.0
            img_w = dims["page_w_pt"] * scale
            img_h = dims["page_h_pt"] * scale

            clamped_px, was_clamped = coords.clamp_px_rect(
                region.px_rect, img_w, img_h
            )
            pdf_rect = coords.pixels_to_pdf_rect(clamped_px, dpi, page)
            removed = redact.remove_region(page, pdf_rect)

            results.append(
                {"page": page_no, "removed": removed, "clamped": was_clamped}
            )

        # Save the redacted result to BOTH the work copy (the result-render substrate) and
        # the outputs file for download. Save to a temp path then replace the work copy so a
        # crash mid-save cannot corrupt it (the original is untouched regardless). Pitfall 9:
        # garbage=4, deflate=True, clean=True undoes redaction bloat.
        out_name = output_filename(session_id)
        out_dir = storage.outputs_dir(session_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / out_name
        pdf_engine.save_doc(doc, out_file)

        work_tmp = Path(work).with_suffix(".redacted.tmp.pdf")
        pdf_engine.save_doc(doc, work_tmp)
    finally:
        pdf_engine.close(doc)

    # Atomically replace the work copy with the redacted version (outside the open doc).
    Path(work_tmp).replace(work)

    return {
        "output_filename": out_name,
        "page_count": n_pages,
        "regions": results,
    }
