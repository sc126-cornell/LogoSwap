---
slug: ai-pieceinfo-residual-mark
status: resolved
trigger: "UAT-discovered v1.1 true-removal hole: output PDFs from Illustrator-sourced supplier files keep the supplier mark recoverable in Adobe Illustrator via embedded /PieceInfo private artwork, even though all normal renderers show it removed."
created: 2026-05-29T07:51:40.121Z
updated: 2026-05-29T08:30:00.000Z
phase: 08-documentation-sync-live-rollout
milestone: v1.1
root_cause_preconfirmed: true
---

# Debug Session: ai-pieceinfo-residual-mark

> NOTE TO SESSION MANAGER / DEBUGGER: The root cause is ALREADY CONFIRMED and the fix is ALREADY
> PROVEN by hand on a real file (see Evidence + Resolution). Do NOT re-investigate from scratch.
> Your job is to LAND the proven fix in production code + add a regression test, minimum-change,
> respecting the constraints below. Spend a quick confirmation step, then go straight to fixing.

## Symptoms (pre-filled — gathered collaboratively during LIVE-UAT, not re-asked)

- expected: Output PDF has the supplier mark TRULY removed — unrecoverable even in an Illustrator-class editor (v1.1 core value + threat model).
- actual: For supplier PDFs that were saved from Adobe Illustrator with editing capabilities, the output looks clean in every normal renderer (MuPDF, PDFium/Chrome, Acrobat Reader, browsers) BUT opening the output in Adobe Illustrator shows the full supplier mark ("dCt / NINGBO DAN-CHIEF NETWORK") as editable vector paths.
- error: No error/exception. Silent — the mark is simply recoverable in Illustrator.
- timeline: Discovered 2026-05-29 during Phase 8 LIVE-UAT on file F1 (3013A-13A-C6-XX). The v1.1 Option B work (Phase 7) addressed content-stream zero-area CAD-glyphs but NOT embedded Illustrator private data.
- reproduction: Process `3013A-13A-C6-XX-3D02-A01-00040.pdf` through LogoSwap (frame the dСt/NINGBO mark in the title block, remove), download output, open output in Adobe Illustrator → mark reappears as paths.

## Current Focus

- hypothesis: CONFIRMED — the supplier mark survives in the embedded Adobe Illustrator private editing data (`/PieceInfo <</Illustrator N 0 R>>` on the page, pointing to `%!PS-Adobe-3.0 ... Creator: Adobe Illustrator` PGF streams). PyMuPDF redaction only edits the PDF page content stream (/Contents), never the PieceInfo private copy, so Illustrator reads its own private artwork (original, mark intact).
- test: After applying the fix (strip /PieceInfo + garbage-collect on save), assert the output has NO page/catalog `/PieceInfo` and NO `%!PS-Adobe` streams; visible page content unchanged (mark still removed in render).
- expecting: output free of any embedded editable original-artwork copy; mark unrecoverable in Illustrator.
- next_action: Land the proven fix in `app/services/pdf_engine.py` save step + add a regression test using a sanitized fixture; keep AGPL seam intact; minimum-change.
- reasoning_checkpoint: (none)
- tdd_checkpoint: (none)

## Evidence

- timestamp: 2026-05-29T07:00Z — File F1 output `(2)` (sha256 707242cc…, 626862 bytes): MuPDF render of the framed title-block mark row = blank (white% 96.6%); `count_zero_area_fills_fully_inside` = 0 (was 1742 in original); my CTM raw-stream fill scan: mark-band fills 3250→1; 0 image XObjects, 0 form XObjects, 0 annotations, 0 OCGs, no "NINGBO" in raw bytes. By page-content analysis it looked fully clean.
- timestamp: 2026-05-29T07:10Z — Cross-checked with a SECOND independent engine: PDFium (pypdfium2) also renders the mark row blank (white% 94.3%). Two mainstream renderers agree the mark is removed.
- timestamp: 2026-05-29T07:20Z — User opened a byte-for-byte identical copy (unique name, just-created, cache-proof) in Adobe Illustrator: the FULL supplier mark "dCt / NINGBO DAN-CHIEF NETWORK" renders as many editable Paths, single normal layer, no clip mask, 100% opacity. => content physically present in the file in a form only Illustrator reconstructs.
- timestamp: 2026-05-29T07:35Z — Located the mechanism: page `/PieceInfo = <</Illustrator 56 0 R>>`; objects 8/20/31 are `%!PS-Adobe-3.0 ... Creator: Adobe Illustrator` PGF private-data streams (the editable original artwork incl. the mark). Object 58 is the redacted page /Contents. Original file ALSO has /PieceInfo + Illustrator (it was saved from Illustrator with editing preserved).
- timestamp: 2026-05-29T07:45Z — PROVEN FIX by hand on the output: `doc.xref_set_key(page.xref,'PieceInfo','null')` (+ catalog) then `doc.save(garbage=4, deflate=True, clean=True)` → file 626862→188265 bytes; `%!PS-Adobe` streams = 0; page /PieceInfo = null; render mark-row still blank (96.6% white, visible content preserved). USER CONFIRMED in Adobe Illustrator: the mark is now UNRECOVERABLE (mark row blank, nothing to select).
- timestamp: 2026-05-29T07:48Z — Scope scan of UAT outputs for `/PieceInfo` + `%!PS-Adobe`: only F1 (3013A-13A-C6-XX) affected. F2 (3013A-36A-C6-W4), F3 (B-3012IP-WM02-T430), F4 (3013A-19-C3-W4, raster) have NO embedded AI private data and were Illustrator-verified clean by the user.

## Eliminated

- hypothesis: white image/vector overlay covering the mark (Option A) — RULED OUT (0 images in region, 0 white vector fills, alpha 0% opaque-white cover).
- hypothesis: surviving zero-area type='f' CAD-glyph source (the Phase 7 / Option B vector) — RULED OUT (count 1742→0; Option B worked on the page content).
- hypothesis: content inside a form XObject (SEC-03 blind spot) — RULED OUT (0 form XObjects).
- hypothesis: hidden OCG layer / marked-content visibility — RULED OUT (0 OCGs, no /OCProperties).
- hypothesis: surviving text (Tj) in a font MuPDF can't render — RULED OUT (only 14 Tj, all grid labels elsewhere; no "NINGBO" text).
- hypothesis: inline image (BI/ID/EI) — RULED OUT (none).
- hypothesis: orphaned/leftover content-stream objects or incremental-update (/Prev) — RULED OUT (garbage=4 re-save same size → no unreachable objects; the "/Prev" raw match was actually "/Preview"; single xref, no incremental update).
- hypothesis: file-identity / Illustrator cache mismatch — RULED OUT (user opened a unique-named byte-identical copy and still saw the mark).

## Resolution (root cause confirmed; fix proven; landing in production now)

- root_cause: Embedded Adobe Illustrator private editing data. The supplier PDF was saved from Illustrator with "preserve editing capabilities", embedding a complete editable copy of the artwork (incl. the supplier mark) under page `/PieceInfo <</Illustrator …>>` → `%!PS-Adobe` PGF streams. LogoSwap's PyMuPDF redaction (`add_redact_annot` + `apply_redactions`, and Option B content-stream surgery) only touches the rendered PDF page content stream, never the PieceInfo private copy. Result: every normal renderer shows the mark removed, but Illustrator reads its own private data and the mark reappears fully editable. This defeats the v1.1 core value ("truly remove, not cover") for exactly the modeled Illustrator-class editor attacker.
- fix: In `app/services/pdf_engine.py` (the sole AGPL `import fitz` seam), at the OUTPUT save step (where the processed doc is written to the fresh output path), strip any embedded editable-original-artwork representation BEFORE/at save: remove `/PieceInfo` from every page and from the catalog (and consider any analogous private alternate-representation keys), then save with `garbage=4, deflate=True, clean=True` so the now-orphaned private streams are garbage-collected. Keep the existing redaction/Option-B path unchanged. Minimum-change; do not move `import fitz` out of this file.
- verification: regression test asserting a processed Illustrator-sourced fixture has (a) no page `/PieceInfo` and no catalog `/PieceInfo`, (b) zero `%!PS-Adobe`/Illustrator private-data streams, (c) visible page content still renders with the framed mark removed (white% threshold) — and ideally the existing illustrator-attack regression gates still pass. Fixture: sanitize `3013A-13A-C6-XX-3D02-A01-00040.pdf` via `scripts/sanitize_fixture.py` (it has /PieceInfo). FINAL acceptance remains a human Adobe Illustrator open-and-try-to-recover (per project principle); the automated PieceInfo/stream check is a strong proxy, not a full substitute.
- files_changed: app/services/pdf_engine.py (added `strip_piece_info(doc)` helper at the AGPL fitz seam + wired it into `save_doc` BEFORE `doc.save(garbage=4, deflate=True, clean=True)` — strips page + catalog `/PieceInfo` so the orphaned `%!PS-Adobe` PGF private streams are GC'd; visible content unchanged); tests/test_pieceinfo_strip.py (NEW — 5 regression tests: synthetic Illustrator-style PDF builder carrying a real `/PieceInfo -> /Illustrator -> /Private -> %!PS-Adobe` chain built IN-MEMORY with synthetic content; asserts save_doc + process_job outputs have no page/catalog `/PieceInfo` and zero PGF streams while visible content still renders; strip_piece_info return-count + no-op coverage). NO committed supplier fixture (the real PGF carries supplier IP — public repo / AGPL §13 — so the attack surface is synthesized in-memory per tests/conftest.py philosophy). NO production logic changes beyond the save-step scrub. AGPL seam intact (`import fitz` only in pdf_engine.py, verified by test_fitz_import_confined_to_engine_seam). Full suite: 343 passed, 3 skipped; the 3 existing illustrator-attack gates stay green.

## Constraints (MUST respect)

- AGPL seam: `import fitz` must remain ONLY in `app/services/pdf_engine.py`. The PieceInfo-strip helper lives in this file.
- Public repo (AGPL §13): the raw supplier PDF `C:\Users\scott\Downloads\test 1\3013A-13A-C6-XX-3D02-A01-00040.pdf` and any scratch scripts/attacked PDFs MUST NOT enter the repo. Run sanitize_fixture.py to produce a shippable fixture; the scratch dir `.planning/debug/scratch/08-live-uat/` is gitignored.
- minimum-change discipline (v1.0 hotfix-06 lesson): only the save-step scrub + its test. No nice-to-have refactors.
- Per-phase quality gates (project memory): after the fix lands, the phase boundary needs review/fix + validate + secure before advancing; and the milestone close still needs LIVE redeploy + a fresh Adobe Illustrator UAT on this file (the LIVE tool currently still has the bug — F1's clean version was a manual post-process, not the deployed tool).
- Commit cadence: commit locally; the single LIVE-deploy push is governed by Phase 8 Plan 03/04 (do not push ad-hoc).
