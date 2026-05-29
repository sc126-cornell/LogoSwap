---
phase: 08-documentation-sync-live-rollout
reviewed: 2026-05-29T00:00:00Z
depth: deep
files_reviewed: 2
files_reviewed_list:
  - app/services/pdf_engine.py
  - tests/test_pieceinfo_strip.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-05-29
**Depth:** deep
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Reviewed the v1.1 LIVE-UAT security fix introduced by commit `d594335` (diff against `d594335^`): a new `strip_piece_info(doc)` helper at `app/services/pdf_engine.py:1011` and its one-line wiring into `save_doc` at `:1085`, plus the new `tests/test_pieceinfo_strip.py` (329 lines, 4 test functions). The fix closes a "true removal" hole where supplier marks survive in embedded Adobe Illustrator private editing data (`/PieceInfo` -> `/Illustrator` -> `/Private` -> `%!PS-Adobe` PGF streams) that PyMuPDF redaction never touches.

**The implementation is correct, minimal, and well-tested for the modeled threat.** It verifiably closes the `/PieceInfo` carrier for the LIVE-UAT file and synthetic equivalents. The five focus areas from the review brief all check out positively on the core mechanism:

- **AGPL seam invariant (focus 1): CLEAN.** The only production `import fitz` remains `app/services/pdf_engine.py:21`. The new helper adds no import and uses only `doc.xref_get_key` / `doc.xref_set_key` / `doc.pdf_catalog` — fitz APIs invoked on handles already inside the seam. The AST-based guard (`tests/test_integrity.py:90`, `tests/test_redact.py::test_fitz_import_confined_to_engine_seam`) covers this; the `integrity.py:11` grep hit is a docstring mention, not an import.
- **Correctness / edge cases (focus 2): CORRECT.** The `if existing and existing[0] != "null"` guard makes the no-op path write nothing (no spurious incremental updates), idempotency is proven by `test_strip_piece_info_return_count_and_no_op`, multi-page iteration is safe (`xref_set_key` mutates an object-dict value, never the page tree, so `for page in doc` is not invalidated), and `garbage=4, clean=True` only GCs the now-orphaned PGF streams (visible-content-neutrality asserted pixel-for-pixel in `test_save_doc_strips_pieceinfo_and_pgf_streams`).
- **Privacy / public-repo AGPL §13 (focus 4): CLEAN.** No committed binary fixture; the PGF attack surface is synthesized in-memory (`_SYNTHETIC_PGF`) and the fixture self-test explicitly asserts supplier strings (`NINGBO`, `DAN-CHIEF`) are absent.
- **Minimum-change discipline (focus 5): CLEAN.** Only the new helper + one-line wire + new test file changed. The honest-limitation markers (`pdf_engine.py:933`, `:1246`, `:1416`, `:1570`) and the entire Option-B content-stream-surgery path (`:1089+`) are untouched — all outside the `1008–1086` diff hunk.

The findings below are one WARNING on **security completeness** (focus 3 — other embedded-editable carriers are not addressed and the v1.1 scope-limit is undocumented in production code) and three INFO items.

## Warnings

### WR-01: Other embedded-editable-original carriers are unaddressed and the `/PieceInfo`-only scope is undocumented in production code

**File:** `app/services/pdf_engine.py:1011-1058` (`strip_piece_info`)
**Issue:**
The fix strips only `/PieceInfo`. The originating debug session explicitly instructed the implementer to *"remove `/PieceInfo` from every page and from the catalog (**and consider any analogous private alternate-representation keys**)"* (`.planning/debug/ai-pieceinfo-residual-mark.md:59`). The "analogous keys" half of that instruction was not acted on, and the production docstring does not record that the threat coverage was deliberately scoped to `/PieceInfo` only.

The debug "Eliminated" scan (`:46-54`) ruled out form-XObjects, OCG layers, inline images, surviving text, and orphaned objects **for the one modeled file (`3013A-13A-C6-XX`)**. It did *not* evaluate other supplier-mark carriers that an Illustrator-class editor (or a forensic recovery) can read and that `garbage=4, clean=True` will NOT remove because they remain legitimately referenced:

- **XMP metadata (`/Metadata` on the catalog).** Illustrator writes an XMP packet that can embed thumbnails and `xmpMM` history; not page-piece data, survives GC. The threat model's attacker reads private editor data — XMP is exactly that class.
- **Document `/Info` dictionary** (`/Creator (Adobe Illustrator)`, `/Producer`, `/Author`, `/Title`). This is a residual *fingerprint* (supplier/author identity), not the recoverable mark artwork, so it is lower-impact than `/PieceInfo` — but it is still supplier IP leaking into a public-facing output and is trivially strippable.
- **`/AF` (associated files) / `EmbeddedFiles`** — an alternate channel for an embedded editable original; not present in the modeled file but not scanned-for in the general case.
- **Image XObject `/Alternates`** — alternate image representations.

This is a SECURITY fix whose stated core value is "truly remove, unrecoverable even in an Illustrator-class editor." Shipping with only one carrier closed, with no in-code statement that the others were considered and consciously deferred, risks a false sense of completeness: the next Illustrator-sourced supplier file that carries the mark via a *different* private key will silently regress the v1.1 guarantee with no test or comment flagging the gap.

Per the review brief, scoping v1.1 to `/PieceInfo` is acceptable **if documented**. It is currently not documented in the production code (only the strip mechanism is described). Recommended fix — add an explicit scope-limitation note and, ideally, a cheap defensive sweep of the other catalog-level carriers (they are one `xref_set_key`/metadata call each and content-neutral):

```python
def strip_piece_info(doc: "fitz.Document") -> int:
    """Remove ``/PieceInfo`` ... Return keys removed.

    ...

    SCOPE (v1.1): this strips ONLY the ``/PieceInfo`` page-piece carrier, which is the
    sole embedded-editable-original channel observed in the LIVE-UAT corpus (debug
    ``ai-pieceinfo-residual-mark`` §Eliminated ruled out form-XObject / OCG / inline-image
    / orphaned-object carriers for the modeled file). Other private channels an
    Illustrator-class editor could read — XMP ``/Metadata``, the document ``/Info`` dict
    (``/Creator: Adobe Illustrator`` + author/title), ``/AF`` / ``EmbeddedFiles``,
    image ``/Alternates`` — are NOT yet stripped. They survive ``garbage=4, clean=True``
    because they remain legitimately referenced. Revisit before any supplier file that
    carries the mark via one of those keys ships. (T-08-xx)
    """
```

If a defensive sweep is in-scope for the fix (recommended for `/Info`, which is a near-zero-risk content-neutral scrub of supplier identity in a PUBLIC-output tool):

```python
    # Document-info supplier fingerprint (e.g. /Creator "Adobe Illustrator",
    # /Author, /Title). Content-neutral; clearing it removes supplier IP from the
    # shipped output. set_metadata({}) clears the /Info dict via the seam.
    doc.set_metadata({})
```

(Note: adding `/Info` scrubbing is a behaviour change — gate it behind a regression test asserting the output `/Info` no longer carries `/Creator`/`/Author`, and confirm no existing test asserts metadata survival.)

## Info

### IN-01: `strip_piece_info` runs twice per job (work-copy save + output save)

**File:** `app/services/pdf_engine.py:1085` (called from `app/services/pipeline.py:342` and `:357`)
**Issue:** `pipeline.process_job` calls `save_doc` twice on the *same* in-memory `doc` — once for the work/preview copy (`:342`) and once for the baked output (`:357`). Because the scrub is embedded inside `save_doc`, `strip_piece_info` executes twice. The second invocation is a verified no-op (idempotency is asserted in `test_strip_piece_info_return_count_and_no_op:259`), so this is correct, not a bug — but it does re-scan every page a second time and the `removed`-count telemetry from the second call is always 0, which could mislead a future caller that logs the return value at the output-save site.
**Fix:** No change required for correctness. If telemetry is added later, log the count from the *work-copy* save (the meaningful one) or hoist the strip to a single call before both saves. A one-line comment on the `save_doc` strip noting "idempotent — safe to re-run on the second pipeline save" would document the intent.

### IN-02: No coverage for a multi-page document where only some pages carry `/PieceInfo`

**File:** `tests/test_pieceinfo_strip.py` (whole file)
**Issue:** Every fixture (`_build_illustrator_style_pdf`) is single-page. The helper's per-page loop and its mixed no-op/strip branch (`if existing and existing[0] != "null"`) are therefore never exercised across a document where page 0 has `/PieceInfo` and page 1 does not (or vice versa). The return-count arithmetic (`removed += 1` per page) and the per-page guard are the most logic-bearing lines in the helper; a 2+ page mixed fixture would lock in that the count equals the number of *carrying* pages, not the page count.
**Fix:** Add a test building a 2-page doc with `/PieceInfo` on page 0 only, asserting `strip_piece_info(doc) == 1` (page) + catalog handling, and that page 1 was never written to. Low priority — the existing single-page + catalog parametrization already covers the page and catalog branches independently.

### IN-03: `_piece_info_present` return type annotation is loose (`tuple[list, object]`)

**File:** `tests/test_pieceinfo_strip.py:154`
**Issue:** The probe returns `(list-of-2-tuples, 2-tuple)` but is annotated `tuple[list, object]`. Test-only and harmless, but `object` for the catalog value discards the `(type, value)` shape that every call site indexes as `catalog[0]` (`:235`, `:320`). A reader has to infer the shape from usage.
**Fix:** Annotate as `tuple[list[tuple[str, str]], tuple[str, str]]` (or a small named alias) to match what `xref_get_key` actually returns and what callers index. Purely cosmetic.

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
