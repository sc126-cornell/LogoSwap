---
phase: 08-documentation-sync-live-rollout
plan: 03
subsystem: infra
tags: [zeabur, pymupdf, pieceinfo, illustrator, redaction, agpl, deploy, metadata]

requires:
  - phase: 07-option-b-implementation-content-stream-surgery
    provides: Option B content-stream surgery (zero-area CAD-glyph true-removal) that this plan deployed + UAT'd
provides:
  - LIVE v1.1 deploy on Zeabur (Dockerfile build, /health 200, section-13 footer = sc126-cornell)
  - Editor-residue removal on save — strip Adobe Illustrator /PieceInfo private artwork + clear /Info + XMP document metadata
  - LIVE-UAT proven on 9 real supplier PDFs, authoritatively verified in Adobe Illustrator
affects: [milestone-close, plan-04, future-supplier-pdf-processing]

tech-stack:
  added: []
  patterns:
    - "On output save, strip editor-private alternate-representations (/PieceInfo) + document metadata (/Info user fields + XMP /Metadata) so no recoverable supplier residue ships"
    - "Verification of true removal MUST include Adobe Illustrator open-and-recover — render/content-stream checks (even multi-engine) are insufficient"

key-files:
  created:
    - tests/test_pieceinfo_strip.py
  modified:
    - app/services/pdf_engine.py
    - .gitignore
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Root cause of the LIVE-UAT true-removal failure = embedded Adobe Illustrator private editing data (page /PieceInfo -> %!PS-Adobe PGF streams); PyMuPDF redaction only edits page /Contents, so Illustrator recovers the mark while every normal renderer shows it removed"
  - "Fix = strip_piece_info + scrub_document_metadata at the save_doc seam, then save(garbage=4, clean=True); content-neutral, no-op for non-Illustrator PDFs"
  - "The original D-04 render-based attack-sim was SUPERSEDED by a 9-file Adobe Illustrator manual batch UAT (a stronger, authoritative verification)"
  - "Render/content-stream verification (MuPDF + PDFium + content scan) is insufficient to certify true removal — Adobe Illustrator is the authoritative gate (memory: feedback_illustrator_verification)"

patterns-established:
  - "Editor-residue scrub on save: /PieceInfo (page+catalog) + /Info user metadata + XMP /Metadata, GC'd via garbage=4"
  - "PieceInfo/%!PS-Adobe presence is a programmatic proxy for the Illustrator-recoverable-mark class; final acceptance stays human Illustrator verification"

requirements-completed: [DEPLOY-01]

duration: multi-session (LIVE-UAT across F1-F4 + F1 forensic investigation + /gsd-debug fix + code-review + redeploy + 9-file re-UAT)
completed: 2026-05-29
---

# Phase 8 Plan 03: LIVE Deploy + UAT Summary

**v1.1 deployed to LIVE on Zeabur; LIVE-UAT on real supplier PDFs exposed a true-removal hole (Adobe Illustrator recovered the supplier mark from embedded /PieceInfo private artwork) that render/content-stream checks could NOT detect — fixed by stripping /PieceInfo + document metadata on save, redeployed, and verified across 9 supplier files in Adobe Illustrator.**

## Performance

- **Tasks:** 3 (gitignore guard; push+deploy+LIVE-UAT; D-04/retire — D-04 superseded by Illustrator batch)
- **Completed:** 2026-05-29
- **Files modified:** 4 (pdf_engine.py, test_pieceinfo_strip.py [new], .gitignore, REQUIREMENTS.md)

## Accomplishments
- **LIVE deploy:** master pushed to origin → Zeabur Dockerfile build; `/health` 200 (5-field), section-13 footer renders `sc126-cornell` (not `<OWNER>`). New build confirmed live (uptime reset).
- **LIVE-UAT found a real, ship-blocking true-removal hole** my entire verification (PyMuPDF render + get_drawings + zero-area count + alpha + PDFium cross-check) certified as clean, but Adobe Illustrator recovered the full supplier mark from F1. Root-caused (via `/gsd-debug ai-pieceinfo-residual-mark`) to embedded Adobe Illustrator private editing data: page `/PieceInfo` → `%!PS-Adobe` PGF streams, which PyMuPDF redaction never touched.
- **Fix landed + reviewed:** `strip_piece_info` + `scrub_document_metadata` at the `save_doc` AGPL seam. Code-review (WR-01) surfaced that the output also leaked supplier metadata (the supplier's internal Windows path as `/Info` title, drafter id as author, plus XMP) — fixed by the metadata scrub. Full suite 345 passed / 3 skipped; AGPL seam intact (`import fitz` only in pdf_engine.py).
- **Redeployed + re-UAT:** 9 real supplier PDFs re-processed on the fixed LIVE build; batch editor-residue check clean on all 9 (0 PieceInfo / 0 %!PS-Adobe / metadata cleared / no XMP) AND **Adobe Illustrator manual verification PASS on all 9** (authoritative).
- **Privacy:** no supplier PDF binary or scratch script committed; scratch retired (only `_deep_check.py` + `_batch_reuat.py` kept as gitignored reusable tools); `git ls-files` clean under the scratch session dir.

## Task Commits
1. **Task 1: .gitignore scratch/supplier-PDF guard** — `946da28`
2. **Task 2: push + LIVE deploy + LIVE-UAT** — deploy push chain culminating `8a043a8`; LIVE-UAT exposed the PieceInfo hole
3. **Mid-plan /gsd-debug fix:** strip Illustrator /PieceInfo on save — `d594335` (fix + test + debug-session record)
4. **Code review:** `6abfc69` (08-REVIEW.md)
5. **WR-01 fix:** scrub /Info + XMP document metadata on save — `2edb62d`
6. **Handoff state:** `8a043a8`
7. **Task 3: DEPLOY-01 flip + this summary** — (this commit)

## Files Created/Modified
- `app/services/pdf_engine.py` — `strip_piece_info(doc)` + `scrub_document_metadata(doc)` helpers, wired into `save_doc` before `save(garbage=4, clean=True)`. AGPL seam unchanged.
- `tests/test_pieceinfo_strip.py` (new) — synthesizes an Illustrator-style PieceInfo/PGF + supplier-shaped metadata in-memory (no supplier IP) and asserts save_doc + process_job strip PieceInfo, GC the PGF streams, clear /Info + XMP, and keep visible content intact.
- `.gitignore` — scratch/supplier-PDF guard (Task 1).
- `.planning/REQUIREMENTS.md` — DEPLOY-01 flipped to complete.

## Decisions Made
See key-decisions frontmatter. Headline: the v1.1 threat model's "Illustrator-class editor attacker" turned out to have a second, dominant vector (PieceInfo) beyond Phase 7's zero-area CAD-glyphs; closing it required a save-step scrub, and the verification method itself had to shift to Adobe Illustrator as the authoritative gate.

## Deviations from Plan

**1. [Scope — UAT-discovered true-removal hole] Embedded Illustrator /PieceInfo + metadata not removed**
- **Found during:** Task 2 LIVE-UAT (Adobe Illustrator recovery of F1's supplier mark).
- **Issue:** Phase 7 Option B closed page-content zero-area CAD-glyphs, but Illustrator-sourced supplier PDFs also carry the full editable artwork in `/PieceInfo` private data + supplier fingerprint in `/Info`/XMP — none touched by redaction. Output looked clean in every renderer but the mark (and supplier path/author) were recoverable in Illustrator.
- **Fix:** `strip_piece_info` + `scrub_document_metadata` at `save_doc`; landed via `/gsd-debug` + code-review (`d594335`, `2edb62d`). Redeployed.
- **Verification:** 345 tests green; batch editor-residue check + Adobe Illustrator manual verification PASS on 9 supplier files.

**2. [Verification method] D-04 render attack-sim superseded by Illustrator batch UAT**
- The planned D-04 one-off render-based attack-sim (delete image overlay → render ≥98% white + zero-area==0) was rendered redundant/insufficient by the finding that render checks miss the PieceInfo vector. The authoritative LIVE-UAT proof is the user's Adobe Illustrator manual verification across 9 real supplier files (stronger than the scripted render attack-sim). The reusable content-stream tools (`_deep_check.py`, `_batch_reuat.py`) are kept (gitignored) as proxies.

**Total deviations:** 2 (1 major scope fix from UAT, 1 verification-method supersession). **Impact:** the scope fix was essential to the core value (true removal); no unplanned scope creep beyond closing the discovered hole.

## Issues Encountered
- My MuPDF/PDFium/content-stream verification gave a FALSE clean on F1 — the central lesson recorded in memory `feedback_illustrator_verification`: never certify true removal on render/script evidence alone; Adobe Illustrator open-and-recover is the authoritative gate.
- `set_xml_metadata("")` raises `FzErrorArgument` on PyMuPDF 1.27.x when a /Metadata stream is present — worked around by cutting the `/Metadata` reference (page+catalog) and letting GC drop the stream (same reference-cut pattern as PieceInfo).

## User Setup Required
None - LIVE deploy used the existing Zeabur project; no new external configuration.

## Next Phase Readiness
- DEPLOY-01 complete; all four Phase 8 requirements (THREAT-02, DOC-01, DOC-02, DEPLOY-01) now `- [x]`.
- Ready for **Plan 04**: final code-review/fix pass (the PieceInfo fix was already reviewed) + validate (Nyquist no-op) + secure + `/gsd-complete-milestone` (archive + `git tag v1.1`; master already pushed).
- Concern/follow-up: other editor-readable carriers (`/AF`, EmbeddedFiles, image `/Alternates`) were not present in the modeled supplier PDFs and are left to the GC pass + future review (documented in the save_doc docstring). Optional future task: broader supplier-identity sanitization of the public repo's planning docs (established posture since Phase 6, out of scope here).

---
*Phase: 08-documentation-sync-live-rollout*
*Completed: 2026-05-29*
