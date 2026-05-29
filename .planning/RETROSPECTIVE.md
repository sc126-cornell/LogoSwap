# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.1 — Illustrator Hardening

**Shipped:** 2026-05-29
**Phases:** 3 (6, 7, 8) | **Plans:** 9 | **Sessions:** 1 extended

### What Was Built
- **Option B content-stream surgery** (`pdf_engine.py`): truly deletes page-level zero-area `type='f'` CAD-glyph fill operators — closing the "Illustrator pulls the image XObject overlay → supplier CAD glyph reappears" attack from v1.0.
- **CAD-glyph regression foundation** (Phase 6): 3 real-supplier sanitized fixtures + `tests/_illustrator_attack.py` + xfail-strict attack-simulation pytest (red→green handoff), and a 4-tier `sanitize_fixture.py` fallback (content-stream strip → latin-1 replace → glyph redaction → Form-XObject stamp delete).
- **PieceInfo + metadata strip on save** (Phase 8, UAT-discovered): `strip_piece_info` + `scrub_document_metadata` remove embedded Adobe Illustrator private editing data (`/PieceInfo` → `%!PS-Adobe` PGF) and `/Info`/XMP supplier fingerprint at the `save_doc` seam.
- **LIVE rollout + authoritative UAT**: redeployed to Zeabur; 9 real supplier PDFs verified clean in Adobe Illustrator (the ground-truth gate).

### What Worked
- **Red-light-first** (Phase 6 before Phase 7): building the failing attack-simulation fixtures before Option B gave an objective green/red signal for the fix.
- **Minimum-change discipline** (the 5330290 lesson held): Option B + the PieceInfo fix touched only `pdf_engine.py` + `redact.py`, 0 deletions to existing dispatchers, AGPL seam intact throughout.
- **Adversarial user verification**: the user opening output in Adobe Illustrator caught a true-removal hole that MuPDF + PDFium + content-stream scanning ALL certified as clean. This was the decisive QA.
- **`/gsd-debug` with a pre-confirmed root cause**: the hole was investigated collaboratively first, then the debug session landed the proven fix + regression test fast, with no re-investigation.

### What Was Inefficient
- **I over-trusted render/content-stream verification** and confidently (wrongly) declared F1 clean — twice — before the user's Illustrator screenshot of a byte-identical copy forced the real finding. A whole arc of MuPDF/PDFium/object-scan analysis missed the embedded `/PieceInfo` because it isn't page content.
- **File-identity confusion**: a screenshot showing `_logoswap (9).pdf` (a stale v1.0-era download) was initially conflated with the v1.1 `(2)` output, costing a couple of rounds to disambiguate (the title bar / many same-named downloads).

### Patterns Established
- **Editor-residue scrub on save**: strip `/PieceInfo` (page + catalog) + clear `/Info` user fields + XMP `/Metadata`, then `garbage=4` GC the orphans. Content-neutral; no-op for non-Illustrator PDFs.
- **Authoritative true-removal gate = Adobe Illustrator open-and-recover.** Automated render/content-stream checks are only a proxy; the `/PieceInfo` + `%!PS-Adobe`-stream presence check is a programmatic detector for this specific class.

### Key Lessons
1. **Render/content-stream verification — even cross-engine (MuPDF + PDFium) — cannot certify "true removal."** Content can survive in a form every renderer ignores but an editor (Illustrator) reconstructs. The only trustworthy gate is opening the output in the actual adversary tool. (Recorded in memory `feedback_illustrator_verification`.)
2. **Embedded application private data is a distinct removal vector.** Adobe Illustrator "preserve editing capabilities" embeds a full editable artwork copy under `/PieceInfo`; redacting the rendered page content never touches it. Any tool that "removes" content from an editor-sourced PDF must strip these private representations too.
3. **Adversarial human QA is irreplaceable for a security-critical core value.** The user's insistence + Illustrator screenshots found the structural blind spot in the verification tooling itself.

### Cost Observations
- Model mix: primarily a single extended session; subagents used for the debug-session-manager + code-reviewer (independent review of the fix).
- Notable: the most expensive stretch was the forensic investigation of the false-clean F1 — unavoidable given the blind spot, but it produced the durable lesson + a programmatic detector.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 MVP | multi | 1-5 | Build → deploy → real-UAT hotfix loop (Option A overlay for CAD-glyph residue) |
| v1.1 Illustrator Hardening | 1 extended | 6-8 | Red-light fixtures first; threat model upgraded to editor-class attacker; **verification gate shifted to Adobe Illustrator** after render/script proved insufficient |

### Cumulative Quality

| Milestone | Tests | AGPL seam | Notable |
|-----------|-------|-----------|---------|
| v1.0 | 301 passed / 3 skipped | single-file `pdf_engine.py` | 27 STRIDE threats closed; LIVE on Zeabur |
| v1.1 | 345 passed / 3 skipped | intact | Option B true-removal; PieceInfo/metadata strip; 9-file Illustrator UAT |

### Top Lessons (Verified Across Milestones)

1. **Real UAT on actual supplier files beats synthetic confidence** — v1.0's hotfix-06 and v1.1's PieceInfo hole were both found only by processing real supplier PDFs and inspecting the result in the adversary's tool.
2. **Minimum-change discipline on a stable fix** (5330290) — held in v1.1; nice-to-have polish stays out of a hotfix-class change.
