---
phase: 08-documentation-sync-live-rollout
plan: 02
subsystem: documentation
tags: [docs, decision-log, handoff, requirements-gate, option-b]
requires:
  - "Phase 7 Option B landed (delete_zero_area_type_f_fills_inside + redact.py dispatcher wiring)"
  - "08-01 THREAT-02 docstring sync complete (THREAT-02 checkbox flipped, STATE advanced to plan 2/4)"
provides:
  - "HANDOFF.md §6.5 Option B content-stream surgery (three-layer defence + CAD-glyph vs general-vector handling)"
  - "HANDOFF.md §6.2 Option A reference reframed as Option A + B 雙層防線"
  - "PROJECT.md Key Decisions Hotfix v1.1 Option B 落地 row (forensic-evidence-cited rationale)"
  - "STATE.md Option B promoted note final-cleaned to DONE/shipped"
  - "REQUIREMENTS.md DOC-01 + DOC-02 checkboxes checked + traceability Complete (milestone-close gate pre-staged)"
affects:
  - HANDOFF.md
  - .planning/PROJECT.md
  - .planning/STATE.md
  - .planning/REQUIREMENTS.md
tech-stack:
  added: []
  patterns:
    - "docs-only minimum-change: only named edits, no unrelated reformatting"
    - "primary-write-then-reconcile: DOC-02 edits are authoritative; /gsd-complete-milestone (Plan 04) runs a second Key Decisions audit + STATE rewrite at close"
key-files:
  created:
    - .planning/phases/08-documentation-sync-live-rollout/08-02-SUMMARY.md
  modified:
    - HANDOFF.md
    - .planning/PROJECT.md
    - .planning/STATE.md
    - .planning/REQUIREMENTS.md
decisions:
  - "DEPLOY-01 checkbox left unchecked here (strict-honesty path): its LIVE-deploy + attack-sim work is Plan 03 (Wave 2); Plan 04 milestone-close verifies all four checkboxes regardless"
  - "Added exactly one new PROJECT.md Key Decisions row; line-105 historical Option-A-deferral row left unchanged as historical record"
  - "STATE.md final-clean targets the Promoted note (lines 88-91), NOT a Deferred-table row (Option B was already removed from the Deferred table at v1.1 launch — RESEARCH flag A4)"
metrics:
  duration: ~3 min
  tasks_completed: 3
  files_modified: 4
  completed: 2026-05-29
---

# Phase 8 Plan 02: HANDOFF 6.5 + PROJECT/STATE Decision Sync + Requirement Gate Pre-stage Summary

Synchronised the decision docs to post-Phase-7 reality (Option B shipped) and pre-staged the milestone-close requirement gate — three atomic doc-only commits, zero code touched.

## What Was Done

### Task 1 — HANDOFF.md §6.5 + §6.2 Option A reference (DOC-01) — commit `659befb`
- Inserted a new `### 6.5 Option B content-stream surgery(三層防線分工)` subsection as the last subsection of §6, positioned after §6.4 and before the `---` separator that precedes §7.
- §6.5 names all three layers: (1) `apply_redactions` baseline (truly removes normal-area text + fully-covered vectors + image pixels), (2) Option B `delete_zero_area_type_f_fills_inside` — upstream page-level content-stream surgery that truly DELETES zero-area `type='f'` CAD-glyph fills `apply_redactions` cannot reach, (3) Option A (`replace_region_with_white_raster` dense / `cover_zero_area_artefacts` sparse) — last-mile OVERLAY for form-XObject-internal residue (page-level-only, logged via `log_xobject_intersect`) + regex-miss fail-safe.
- Documented the CAD-glyph vs general-vector distinction: normal-area vector logos are truly removed by `apply_redactions` so Option B is a **no-op (SEC-02)**; CAD-glyph supplier marks decompose into many zero-area `type='f'` fills that `apply_redactions` leaves in the stream, which Option B targets exactly.
- Adjusted the only §6 Option A reference (the line-172 `(dCt-residue Option A)` mention inside §6.2) to note Option A is now one layer of the **「Option A + B 雙層防線」** and cross-reference §6.5. The surrounding REMOVE_IF_TOUCHED vs REMOVE_IF_COVERED guidance + commit-history caution were left intact.

### Task 2 — PROJECT.md Key Decisions row + STATE.md final-clean (DOC-02) — commit `013bc5e`
- PROJECT.md: added exactly **one** new 3-column Key Decisions row "**Hotfix v1.1 — Option B 落地**" matching the existing `| Decision | Rationale | Outcome |` shape. Rationale cites the 2026-05-28 forensic attack evidence dir `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/` (the v1.0 deferral assumption "Option A overlay 對使用者實質不可恢復" was disproven — Illustrator can pull the image XObject overlay). Outcome = `✓ Validated (Phase 7,T-06-01 + T-02-07 CLOSED via Option B;baseline 338 passed + 3 skipped + 0 xfailed)`. The line-105 historical Option-A-deferral row was left unchanged.
- STATE.md: final-cleaned the "Promoted from Deferred to Active" note (lines 88-91) from "v1.1 active(Phase 7 核心)" to "**DONE / shipped**(Phase 7 落地完成,v1.1 LIVE rollout 進行中 Phase 8)", including the Phase-7-complete evidence (338 passed + 3 skipped + 0 xfailed; three gates green; T-06-01 + T-02-07 CLOSED). The disproven-assumption forensic explanation was retained for the record. The two genuinely-deferred-onward Deferred-table rows (Form-XObject recursive surgery; `type='s'` stroke surgery) were left untouched.

### Task 3 — Requirement checkbox flips + traceability (milestone-close gate pre-stage) — commit `41e30f1`
- Flipped DOC-01 (line 40) and DOC-02 (line 41) from `- [ ]` to `- [x]` in REQUIREMENTS.md; THREAT-02 (line 26) was already `[x]` from 08-01 and was verified + left checked.
- Set the traceability table Status for DOC-01 and DOC-02 from "Pending" to "Complete". Remaining "Pending" rows: exactly 1 (DEPLOY-01).
- **DEPLOY-01 left unchecked** (strict-honesty path per the plan's Task 3 sequencing caveat): its actual work (LIVE deploy + attack-sim green) happens in Plan 03 (Wave 2). Plan 04's milestone-close task independently verifies all four checkboxes before close, so the gate is satisfied either way.
- ROADMAP.md Phase 8 line 36 (`- [ ]`) was **not** flipped — that is the phase-completion checkbox owned by phase/milestone close.

## Verification

All automated `<verify>` checks passed:
- Task 1: `6.5` present (2), `雙層防線` present (1), `delete_zero_area_type_f_fills_inside` present (1), overlay helpers present, `SEC-02` mentioned (1).
- Task 2: `Option B 落地` in PROJECT.md, `illustrator-attack-2026-05-28-archived` cited; PROJECT.md diff = 1 added line (single row, no duplicate, line-105 unchanged); STATE.md `遞迴 surgery` row intact (1), `type='s'` row intact (1), promoted note reads `DONE / shipped`.
- Task 3: THREAT-02/DOC-01/DOC-02 all `[x]`; DEPLOY-01 still `[ ]`; traceability Pending = 1 (DEPLOY-01 only); ROADMAP Phase 8 line still `- [ ]`.

Overall scope guard: `git diff --name-only 5c9bcbc..HEAD` shows only the 4 named doc files; `git diff --name-only 5c9bcbc..HEAD -- app/` is empty (no code touched); only git tag is `v1.0` (no v1.1 tag created); 08-01 progress (STATE plan 2/4, THREAT-02 checkbox) not reverted.

## Deviations from Plan

None — plan executed exactly as written. The DEPLOY-01 deferral and the line-172 Option A reference choice were both explicitly offered as planner-sanctioned options (Task 3 sequencing caveat + RESEARCH flag A3) and are documented above.

## Known Stubs

None. All edits are final decision-doc text; no placeholders, no unwired data.

## Notes for Downstream Plans

- **Plan 03 (DEPLOY-01):** must flip DEPLOY-01's REQUIREMENTS.md checkbox (line 47) + traceability Status to Complete as its final sub-step once LIVE-UAT is green, OR leave it for Plan 04 — either satisfies the close gate.
- **Plan 04 (/gsd-complete-milestone):** runs its OWN full PROJECT.md Key Decisions audit + STATE.md rewrite at close. The DOC-02 edits here are the PRIMARY authoritative write; do NOT duplicate the Option B row — the close workflow reconciles. The close workflow also owns the `git tag v1.1` (no double-tag).

## Commits

- `659befb` — docs(08-02): add HANDOFF 6.5 Option B content-stream surgery + Option A dual-layer ref (DOC-01)
- `013bc5e` — docs(08-02): PROJECT Key Decisions Option B row + STATE Option B final-clean (DOC-02)
- `41e30f1` — docs(08-02): flip DOC-01 + DOC-02 req checkboxes + traceability Complete (milestone-close gate pre-stage)

## Self-Check: PASSED

- All 5 referenced files exist on disk (SUMMARY + 4 modified docs).
- All 3 task commits exist in git history (659befb, 013bc5e, 41e30f1).
- Scope guard: no `app/` code touched; no v1.1 tag created; 08-01 progress not reverted.
