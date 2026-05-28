---
phase: 08-documentation-sync-live-rollout
plan: 01
subsystem: pdf
tags: [threat-02, docstring-sync, option-b, honest-limitation, agpl-seam, minimum-change, doc-only]

# Dependency graph
requires:
  - phase: 07-option-b-implementation-content-stream-surgery (Plan 07-01)
    provides: "delete_zero_area_type_f_fills_inside + log_xobject_intersect (Option B helpers — the SOURCE-OF-TRUTH the rewrites align to)"
  - phase: 07-option-b-implementation-content-stream-surgery (Plan 07-02/07-03)
    provides: "remove_region_vector Option B wiring upstream of the dense/sparse dispatcher (redact.py:213)"
provides:
  - "pdf_engine.replace_region_with_white_raster LIMITATION block rewritten Option-B-accurate (last-mile framing)"
  - "redact.py module-level TRUE_REMOVAL_LIMITATION prose rewritten (Option B SHIPPED, runs upstream)"
  - "redact.py dispatcher HONEST LIMITATION comment rewritten (page-level sources already deleted upstream)"
  - "THREAT-02 documentation-integrity threat (T-08-01) mitigated: false 'future candidate' framing removed from all three blocks"
affects: [08-doc-01-handoff, 08-doc-02-project-state, 08-milestone-close]

# Tech tracking
tech-stack:
  added: []  # 無新 runtime/dev 套件 — 純 docstring/comment 文字編輯
  patterns:
    - "THREAT-02 = three independent before→after string edits; zero logic change; AGPL seam untouched"
    - "Three rewrites align TO the already-accurate §1.4 SOURCE-OF-TRUTH markers (pdf_engine.py:1173/1343/1497) — those NOT edited (scope-creep guard)"
    - "honest framing: page-level Option B truly deletes upstream; Option A overlay = last-mile defence for form-XObject residue (logged) + regex-miss / _DISALLOWED_IN_BLOCK fail-safe"

key-files:
  created:
    - ".planning/phases/08-documentation-sync-live-rollout/08-01-SUMMARY.md"
  modified:
    - "app/services/pdf_engine.py"   # replace_region_with_white_raster LIMITATION block (lines ~933-958) — docstring text only
    - "app/services/redact.py"       # module TRUE_REMOVAL_LIMITATION prose (lines ~27-47) + dispatcher HONEST LIMITATION comment (lines ~245-267) — comment/docstring text only

key-decisions:
  - "Rewrite direction locked by ROADMAP success criterion 1 / CONTEXT D Discretion: 'candidate hotfix / future iteration / Option B / #07' → 'Option B 已關閉 page-level 零面積 source 路徑;form-XObject 內部仍為 Option A overlay-only(已記 log)'"
  - "Kept the still-true sentences (zero-area BLACK sources remain when THIS branch fires — because it only fires when Option B could not reach them) rather than deleting wholesale"
  - "Did NOT touch the three §1.4 HONEST LIMITATION markers at pdf_engine.py:1173/1343/1497 — already Option-B-accurate; editing them = scope creep + risk of misstating the helper's own fail-safe contract (Pitfall 3)"
  - "Changed NO executable line: AGPL fitz seam stays a single import statement at pdf_engine.py:21; added no fitz import to redact.py"
  - "minimum-change discipline (5330290): touched only the three named blocks; no surrounding refactor / unrelated docstring polish"

patterns-established:
  - "When a deferred capability ships, the honest-limitation docs that deferred it must be synchronized in the SAME phase — leaving false 'future candidate' framing under-states the shipped defence and misleads maintainers/legal (THREAT-02)"

requirements-completed: [THREAT-02]

# Metrics
duration: ~15min
completed: 2026-05-28
---

# Phase 8 Plan 01: THREAT-02 Honest-Limitation Docstring Sync Summary

Synchronized the three "honest limitation" docstring/comment blocks in `pdf_engine.py` and `redact.py` from a now-FALSE "true deletion is a future/candidate Option B hotfix" framing to the post-Phase-7 reality: Option B (`delete_zero_area_type_f_fills_inside`) runs UPSTREAM in `remove_region_vector` and TRULY deletes page-level zero-area `type='f'` CAD-glyph sources from the content stream before any overlay fires; the Option A overlay is now a last-mile defence only (form-XObject-internal residue, logged not deleted; plus regex-miss / `_DISALLOWED_IN_BLOCK` fail-safe). Pure documentation edit — zero logic change, AGPL seam intact.

## What Was Built

| Target | File / Location | Change |
|--------|-----------------|--------|
| Target 1 | `pdf_engine.py` `replace_region_with_white_raster` LIMITATION block (~933) | Replaced "True deletion … requires content-stream surgery (a candidate hotfix for a future iteration)" with last-mile framing: Option B already deleted page-level sources upstream; this overlay only fires for form-XObject residue (logged via `log_xobject_intersect`) + Option B fail-safe. Kept the still-true "sources remain when THIS branch fires" sentences. |
| Target 2 | `redact.py` module-level `TRUE_REMOVAL_LIMITATION` prose (~6-47) | Replaced closing "(a candidate hotfix #07 / Option B if higher assurance is required)" with an "UPDATE (Phase 7 / Option B, 2026-05-28): page-level true deletion has SHIPPED" paragraph stating Option B runs upstream in `remove_region_vector` before the dispatcher; overlay = last-mile for form-XObject residue + regex-miss / `_DISALLOWED_IN_BLOCK` fail-safe. Kept the hotfix-#06 historical context + analysis-dir cross-reference. |
| Target 3 | `redact.py` dispatcher inline `HONEST LIMITATION` comment (~245-267) | Replaced "True content-stream deletion … is deferred to a future content-stream-surgery hotfix (Option B / #07)" with a note that page-level sources have ALREADY been truly deleted upstream by Option B (the `option_b_deleted` step at redact.py:213); this dense branch's overlay is now last-mile only. Kept the "mirrors replace_region_with_white_raster's docstring and the module-level TRUE_REMOVAL_LIMITATION note" cross-reference (still accurate after Targets 1+2). |

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite pdf_engine.py `replace_region_with_white_raster` LIMITATION block (THREAT-02 target 1) | `9a3a8c0` | `app/services/pdf_engine.py` |
| 2 | Rewrite redact.py module `TRUE_REMOVAL_LIMITATION` prose + dispatcher `HONEST LIMITATION` comment (THREAT-02 targets 2 & 3) | `c6a5274` | `app/services/redact.py` |

## Verification

| Check | Result |
|-------|--------|
| `pdf_engine.py` + `redact.py` parse as valid Python | `parse-ok` (both) |
| `grep -c "candidate hotfix for a future iteration" app/services/pdf_engine.py` | `0` (false phrase gone) |
| `grep -c "deferred to a future" app/services/redact.py` | `0` (dispatcher false framing gone) |
| `grep -c "a candidate" app/services/redact.py` | `0` (module prose "candidate hotfix #07 / Option B" framing gone) |
| `last-mile` present in rewritten pdf_engine.py block | line 953 (within ~936-958 range) |
| `upstream` / `UPSTREAM` / `last-mile` / `TRULY` present in both redact.py blocks | module prose (36/38/39) + dispatcher comment (262/265) |
| AGPL seam: real `import fitz` statement | exactly one — `app/services/pdf_engine.py:21`; none added to redact.py |
| `git diff -U0` pdf_engine.py hunks | single hunk `@@ -936,13 +936,25 @@` — NO lines >1000 touched; three §1.4 non-target markers (1173/1343/1497) untouched |
| `git diff -U0` redact.py hunks | `@@ -34,3 +34,13 @@` (docstring prose) + `@@ -251,2 +261,7 @@` (HONEST LIMITATION comment) — executable Option B wiring (205-220) + dispatcher logic (257+) untouched |

## Deviations from Plan

None — plan executed exactly as written. The two tasks were the three named string edits, with the rewrite direction fixed by ROADMAP success criterion 1 / CONTEXT D Discretion. No bugs, no missing functionality, no blocking issues, no architectural changes. minimum-change discipline held: only the three named blocks were touched.

Note on the plan's Task 2 `<verify>` shell command: `grep -c "candidate\nhotfix #07"` cannot match a literal newline in a single-line `grep`, so the authoritative `a candidate` / `deferred to a future` acceptance-criteria greps were used instead (both return `0`).

## Known Stubs

None. This is a documentation-only plan; no data sources, UI components, or placeholder values were introduced.

## Threat Flags

None. No new network endpoints, auth paths, file-access patterns, or schema changes. The change is the THREAT-02 mitigation itself (documentation-integrity threat T-08-01): the false "deletion is a future candidate" framing was removed so a maintainer cannot re-defer already-shipped protection. No code-level threat surface change.

## Self-Check: PASSED

- FOUND: `app/services/pdf_engine.py`
- FOUND: `app/services/redact.py`
- FOUND commit: `9a3a8c0` (Task 1)
- FOUND commit: `c6a5274` (Task 2)
