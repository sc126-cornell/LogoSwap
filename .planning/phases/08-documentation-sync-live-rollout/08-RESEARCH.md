# Phase 8: Documentation Sync + LIVE Rollout - Research

**Researched:** 2026-05-28
**Domain:** Documentation sync (docstrings + decision docs) + Zeabur/Docker LIVE deploy + one-off attack-sim verification + v1.1 milestone close
**Confidence:** HIGH (every claim grounded in this repo's actual files; all file:line citations re-verified against current source)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** LIVE-UAT runs on the live Zeabur site (`https://logoswap.scottchen0622.com`) — `git push` triggers Zeabur auto-deploy. This is a **scoped exception** to the usual "UAT period commit local but never push" cadence, deliberately overriding it. Rationale: v1.1 only touches 2 production files (`pdf_engine.py` + `redact.py`) + docs, and Phase 7 already passed all three gates. Normal phases still keep the original cadence — this exception does not spill over.
- **D-02:** Fixed deploy order: **(1)** all three LIMITATION docstrings + HANDOFF 6.5 + PROJECT/STATE edits done and committed locally → **(2)** single push deploys to Zeabur (this push carries Phase 6 fixtures + Phase 7 Option B + Phase 8 docs — **v1.1's first time on production**) → **(3)** LIVE-UAT → **(4)** green-light then final code-review/fix pass → **(5)** tag v1.1. final code-review deliberately lands AFTER the push (tradeoff accepted because Phase 7 already passed three gates).
- **D-03:** End-to-end LIVE-UAT uses the engineer's **ORIGINAL (un-sanitized) supplier PDF**, NOT a repo fixture — closest to real usage (full supplier marks). This file **does NOT enter the repo** (binary/sensitive, violates conftest "never commit binary" convention). ⚠️ **Blocking prerequisite: engineer must supply a fresh real supplier CAD-glyph PDF** — planner should list "sample acquisition" as a blocking prerequisite of the UAT task.
- **D-04:** attack-sim verification of the LIVE-downloaded output uses a **one-off scratch script** (in `.planning/debug/scratch/`) that imports the existing `tests/_illustrator_attack.py` logic, asserts render ≥98% white + selected-region zero-area `type='f'` count == 0 against the downloaded file, then retires. Reuses existing attack logic, adds **no new production/test surface** (minimum-change, 5330290 discipline). **Rejected** the "package as standalone CLI runner into `scripts/`" option (avoids new maintenance surface).
- **D-05:** Phase 8 scope **extends all the way through milestone close** — plans must include final code-review/fix + push origin + `git tag v1.1` + running `/gsd-complete-milestone` (archive ROADMAP, PROJECT.md milestone audit, prep next version). One clean wrap-up, no loose ends.

### Carried Forward (not re-discussed — existing standards)
- **Three gates** at phase boundary: standard review/fix + validate + secure. Note: Phase 8 mostly touches doc text + deploy config, so secure is expected to be near no-op (THREAT-02 is docstring honesty, not a new mitigation, no threat-surface change); validate Nyquist is disabled in this repo's config (no-op); review/fix MUST run — success criterion 5's "final code-review pass" lands at this gate.
- **AGPL seam untouched:** `import fitz` only in `app/services/pdf_engine.py`; §13 three-piece set (GitHub public + LICENSE + UI footer source link) already in place — this phase only adjusts text.
- **Python 3.12 pin (IN-02):** `Dockerfile` both stages already `python:3.12-slim-bookworm`; deploy layer already satisfies it. During LIVE verification, confirm the online runtime really is 3.12 (the secure audit env was 3.14; maintain regex/logging parity).
- **minimum-change discipline (5330290 lesson):** the doc phase especially must not smuggle in polish; nice-to-haves go to a maintenance sprint.

### Claude's Discretion
- The actual **wording** of HANDOFF 6.5 / PROJECT Key Decisions row / the three docstrings is for the planner/executor to draft per the success criteria. The **direction** of the three LIMITATION rewrites is fixed by success criterion 1: from "recovery requires deleting image XObject + per-path bbox surgery attack (Option A overlay is the only defence)" → to "Option B has closed the page-level zero-area source path; form XObject internals remain Option A overlay-only (already logged)".

### Deferred Ideas (OUT OF SCOPE)
- **Standalone LIVE-UAT attack runner (`scripts/`)** — rejected this phase, using a one-off scratch instead (D-04). If LIVE-UAT becomes a routine flow in future, re-evaluate packaging into a repeatable CLI.
- (Per CONTEXT.md `<domain>` scope anchor — also out of scope this phase): any production logic change (Option B already done in Phase 7), form XObject recursive surgery, `type='s'` stroke surgery, AGPL §13 three-piece-set structural change. This phase touches only "doc text + deploy + verify + milestone close".
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **THREAT-02** | Three "LIMITATION (be honest)" docstring blocks synchronized — `pdf_engine.py::replace_region_with_white_raster`, `redact.py` module-level `TRUE_REMOVAL_LIMITATION`, `redact.py` dispatcher inline comment "HONEST LIMITATION" — rewritten from "requires delete image XObject + per-path bbox surgery attack" → "Option B closed the page-level zero-area source path". | §1 below quotes the EXACT current text of all 3 targets + confirms which OTHER `HONEST LIMITATION` markers are already Option-B-accurate (NOT targets). §6 gives the factually-correct Option B behaviour for the rewrite. |
| **DOC-01** | `HANDOFF.md` §6 gains 6.5 "Option B content-stream surgery"; §6 Option A description adjusted to "Option A + B 雙層防線". | §2 maps §6 subsection structure (6.1–6.4), exact insertion point, and quotes the current Option A sentence that must change. |
| **DOC-02** | `PROJECT.md` Key Decisions gains a "Hotfix v1.1 — Option B 落地" row; `STATE.md` Deferred table Option B entry final-clean. | §3 gives the Key Decisions table format + quotes the existing STATE.md Deferred table + "Promoted from Deferred" note. |
| **DEPLOY-01** | New build to Zeabur LIVE + ≥1 CAD-glyph sample completes upload → 框選 → process → download → attack-sim all green. | §4 documents Zeabur/Docker deploy mechanics, `<OWNER>` sed, 3.12 pin/verification. §5 documents the attack-sim mechanics for the D-04 scratch script. |
</phase_requirements>

## Summary

Phase 8 is a **documentation-sync + rollout + milestone-close** phase, not a feature build. Option B (page-level content-stream surgery that truly deletes zero-area `type='f'` fills) already landed in Phase 7 and passed all three gates (baseline 338 passed + 3 skipped + 0 xfailed). What remains is purely: (a) make three "honest limitation" docstrings reflect the new reality, (b) add 6.5 to HANDOFF.md + a v1.1 row to PROJECT.md Key Decisions + final-clean the STATE.md Deferred entry, (c) deploy to LIVE and run an end-to-end attack-sim verification on a real supplier sample, and (d) close the v1.1 milestone.

The research confirms the canonical file:line citations in CONTEXT.md are **all still accurate**: `pdf_engine.py:933` (`LIMITATION (be honest)`), `redact.py:6` (`TRUE_REMOVAL_LIMITATION` heading; the prose body spans lines 6-36), `redact.py:245` (dispatcher `HONEST LIMITATION` comment). The three `HONEST LIMITATION` markers inside `pdf_engine.py` at lines 1173, 1343, 1497 are **NOT THREAT-02 targets** — they were written in Phase 7, live inside the Option B helpers themselves, and already accurately describe the Option B regex fail-safe; rewriting them would be scope creep and would risk re-stating the helper's own contract incorrectly.

The two highest-risk surprises for the planner: **(1)** `master` is **61 commits ahead of origin** — the D-02 single push is a large push carrying all of Phase 6+7+8; and **(2)** the `.planning/debug/scratch/**` directory is **git-tracked** (the gitignore underscore-prefix guards `/_*.py` are root-anchored only, NOT effective inside the scratch dir), so the D-04 scratch script will be committed unless explicitly deleted before the push or added to gitignore — and the D-03 real supplier PDF must be kept out of the repo by a non-root-anchored pattern. There is also a sequencing nuance: `/gsd-complete-milestone` creates the `git tag v1.1` itself, so the planner must avoid double-tagging.

**Primary recommendation:** Sequence the plan strictly per D-02: (1) all doc/docstring edits committed locally → (2) one push to deploy → (3) LIVE-UAT with the engineer-supplied real PDF via a one-off scratch script → (4) final review/fix → (5) milestone close (which itself tags v1.1). Treat THREAT-02 as three precise before→after string edits (text quoted in §1), keep the doc phase free of any production-logic change, verify the LIVE runtime is Python 3.12, and ensure the scratch script + real PDF never enter the repo.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| THREAT-02 docstring rewrites | Source code (docstrings/comments in `app/services/`) | — | Comments-only; AGPL seam unaffected (no `import fitz` change). Pure string edits in `pdf_engine.py` + `redact.py`. |
| DOC-01 HANDOFF 6.5 | Repo-root docs (`HANDOFF.md`) | — | Colleague-facing integration doc, not in `.planning/`. |
| DOC-02 PROJECT/STATE | Planning docs (`.planning/PROJECT.md`, `.planning/STATE.md`) | — | Decision-log + state tracking. `commit_docs: true` so these are committed. |
| DEPLOY-01 build + deploy | CI/CD + container (Dockerfile → Zeabur PaaS) | DNS (Cloudflare) | Zeabur autodetects the Dockerfile on git push; Cloudflare fronts `logoswap.scottchen0622.com`. |
| DEPLOY-01 LIVE-UAT | Browser (upload/框選/download) + API/backend (process) | — | Manual end-to-end through the live web UI; backend runs the Phase 7 pipeline. |
| attack-sim verification | Local dev (one-off scratch script importing `tests/_illustrator_attack.py`) | — | Runs locally against the LIVE-downloaded file; NOT a server-side capability. |
| Milestone close | Workflow tooling (`/gsd-complete-milestone`) + git (tag/push) | — | Archives docs, creates tag v1.1, updates STATE/MILESTONES/RETROSPECTIVE. |

## Standard Stack

This phase introduces **no new dependencies**. The relevant existing pins (all already in the repo; do NOT bump in a doc phase per minimum-change discipline):

### Core (already pinned — `requirements.txt`)
| Library | Pin | Purpose | Note |
|---------|-----|---------|------|
| PyMuPDF (`fitz`) | `>=1.27,<1.28` | Core redaction + Option B content-stream surgery | [VERIFIED: requirements.txt:5]. AGPL seam: imported ONLY in `pdf_engine.py:21` [VERIFIED: grep]. |
| FastAPI | `>=0.115,<1.0` | Backend API | [VERIFIED: requirements.txt:8] |
| uvicorn[standard] | `>=0.34` | ASGI server (Dockerfile CMD runs `--workers ${UVICORN_WORKERS:-2}`) | [VERIFIED: requirements.txt:9, Dockerfile:85] |
| Pillow | `>=12,<13` | Image decode | [VERIFIED: requirements.txt:12] |
| python-multipart | `>=0.0.9` | FastAPI multipart uploads | [VERIFIED: requirements.txt:15] |
| pytest, httpx | (unpinned, dev/test) | Test harness; `_illustrator_attack.py` uses `numpy` (transitively present) | [VERIFIED: requirements.txt:18-19]; NumPy used at `tests/_illustrator_attack.py:61] |

**Python runtime:** `requirements.txt` does NOT pin a Python version — it relies on the Dockerfile's `python:3.12-slim-bookworm`. The comment at `requirements.txt:2-3` explicitly notes the PyMuPDF cp310-abi3 stable-ABI wheel is forward-compatible with 3.14 (which is why the secure audit env on 3.14 worked) — but the **LIVE deploy must be 3.12** to maintain regex/logging parity (IN-02). [VERIFIED: requirements.txt:1-5, Dockerfile:14+28]

## Architecture Patterns

### Deploy Flow (DEPLOY-01)

```
  git push origin master  ──────────────────────────►  GitHub (sc126-cornell/LogoSwap)
                                                              │  (Zeabur watches the repo)
                                                              ▼
                                          Zeabur autodetect Dockerfile (no zeabur.json/zbpack.json)
                                                              │
                            ┌─────────────────────────────────┘
                            ▼
        docker build  (Stage 1 builder: python:3.12-slim-bookworm, pip --target /install)
                            │
                            ▼
        docker build  (Stage 2 runtime: python:3.12-slim-bookworm, non-root user app)
                            │   ARG GITHUB_OWNER=sc126-cornell (default)
                            │   RUN sed -i "s|<OWNER>|${GITHUB_OWNER}|g" web/index.html README.md
                            ▼
        container start  →  sh -c "uvicorn app.main:app --port ${PORT} --workers 2 ..."
                            │   (Zeabur injects $PORT; HEALTHCHECK hits /health)
                            ▼
        Cloudflare DNS  →  https://logoswap.scottchen0622.com   (publicly reachable on push)
```

### LIVE-UAT + attack-sim Flow (DEPLOY-01 / D-03 / D-04)

```
  engineer's ORIGINAL supplier CAD-glyph PDF  (NOT in repo — D-03)
                            │
                            ▼
  Browser: upload → 框選 (draw rect) → process (logo or pure-removal) → download
                            │   (live site runs Phase 7 Option B pipeline)
                            ▼
  downloaded output PDF  (local, NOT in repo)
                            │
                            ▼
  one-off scratch script  .planning/debug/scratch/<session>/_xxx.py   (D-04)
    import tests._illustrator_attack:
      1. fitz.open(downloaded.pdf)
      2. delete_image_xobjects_intersecting(doc, page_index, region_pdf_pts)  ← simulate Illustrator
      3. doc.save(attacked.pdf)
      4. render_region_white_pct(attacked.pdf, page_index, region_pdf_pts)   ≥ 98.0  (gate a)
      5. count_zero_area_fills_in_region(attacked.pdf, page_index, region_pdf_pts) == 0  (gate b)
                            │
                            ▼
  GREEN  →  LIVE-UAT verified  →  retire scratch (delete, never commit)
```

### Pattern: THREAT-02 as three independent string edits
**What:** Each LIMITATION block is a self-contained docstring/comment. Edit each in place; no logic touched.
**When to use:** Exactly the three locations in §1. The rewrite direction is fixed by success criterion 1.
**Anti-pattern to avoid:** Do NOT touch the three `HONEST LIMITATION` markers inside the Phase 7 helpers (`pdf_engine.py:1173/1343/1497`) — they already accurately describe Option B's own regex fail-safe (§1.4). Editing them = scope creep + risk of misstating helper contract.

### Anti-Patterns to Avoid
- **Double-tagging v1.1:** `/gsd-complete-milestone` creates `git tag -a v1.1` in its `git_tag` step (§7). Do NOT also create the tag in a separate Phase 8 task — let the milestone-close workflow own it (or, if a task creates it first, the workflow's tag step would fail on an existing tag). Recommend: the tag is created BY `/gsd-complete-milestone`.
- **Committing the scratch script / real PDF:** `.planning/debug/scratch/**` is git-tracked (§4, Runtime State Inventory). The scratch script and the engineer's PDF must be deleted (or gitignored) before the push.
- **Bumping deps / smuggling polish in a doc phase:** minimum-change discipline (5330290). The Pending Backlog items (`is_raster_fallback_image` getter, `residual_whitepaint` in `_PROCESS_STATUS`, etc.) are explicitly deferred — do not touch.

## Concrete Research Findings

### §1 — THREAT-02: exact current text of the three LIMITATION blocks

All three CONTEXT.md citations are **CURRENT and accurate** (re-verified). The rewrite direction (success criterion 1): from "recovery requires deleting image XObject + per-path bbox surgery (Option A overlay = only defence)" → "Option B has closed the page-level zero-area source path; form-XObject internals remain Option A overlay-only (already logged)".

#### Target 1 — `app/services/pdf_engine.py` lines 933-948 (in `replace_region_with_white_raster`)
[VERIFIED: pdf_engine.py:933-948]. Current text:
```
    LIMITATION (be honest)
    ----------------------

    The zero-area BLACK source paths remain in the content stream. They are not
    deleted — only visually superseded by the image overlay. Recovering the
    original supplier mark requires:

      1. Removing this image XObject (one structural edit in a PDF editor), AND
      2. Expanding the zero-area path bboxes to non-zero width/height
         (per-path geometry surgery).

    This is strictly harder than the failure mode it replaces — the prior
    ``cover_zero_area_artefacts`` leak recovers the mark by simply re-colouring
    the per-artefact covers, no geometry surgery needed. True deletion of
    zero-area sources requires content-stream surgery (a candidate hotfix for a
    future iteration if higher assurance is required).
```
**Rewrite note:** the phrase "True deletion ... requires content-stream surgery (a candidate hotfix for a future iteration)" is now FALSE — Option B shipped. This block describes the DENSE raster-overlay branch specifically, so the honest framing is: "this overlay is now a LAST-MILE defence; Option B (`delete_zero_area_type_f_fills_inside`) runs UPSTREAM and has already truly deleted page-level zero-area sources before this branch can fire; this overlay only remains relevant for form-XObject-internal residue, which Option B does not descend into (logged via `log_xobject_intersect`)."

#### Target 2 — `app/services/redact.py` lines 6-36 (module-level `TRUE_REMOVAL_LIMITATION`)
[VERIFIED: redact.py:6-36]. This is a **prose section in the module docstring**, not a Python string constant (despite the "string" wording in CONTEXT.md — flag: it is a docstring heading, not an assignable variable). Current text (the load-bearing claims that become false):
```
TRUE_REMOVAL_LIMITATION (hotfix #06 / dCt-residue, 2026-05-26)
--------------------------------------------------------------

One narrow case violates the "true removal at the content-stream level" guarantee:
when a supplier mark is rendered as a CAD-glyph decomposition ... PyMuPDF's
``apply_redactions`` does NOT remove those zero-area items in ANY graphics mode ...
The sources remain in the content stream.

When :func:`remove_region_vector` detects DENSE zero-area residue ... it overlays a
single solid-white image XObject ... This is an OVERLAY, not a delete ...

Recovering a supplier mark from a dense-residue output requires BOTH (1)
removing the image XObject ... AND (2) expanding each zero-area path's bbox ...

True deletion of zero-area sources requires content-stream surgery (a candidate
hotfix #07 / Option B if higher assurance is required); see
``.planning/phases/05-ubuntu/hotfix-06-dct-residue/`` for the full analysis.
```
**Rewrite note:** the closing sentence ("True deletion ... requires content-stream surgery (a candidate hotfix #07 / Option B if higher assurance is required)") describes Option B as a *future candidate*. It is now shipped. The honest rewrite: Option B (`pdf_engine.delete_zero_area_type_f_fills_inside`) now runs in `remove_region_vector` BEFORE the dense/sparse dispatcher and truly deletes page-level zero-area `type='f'` sources from the content stream; the OVERLAY described here remains as a last-mile defence only for (a) form-XObject-internal residue Option B does not descend into, and (b) regex-miss fail-safe cases. Note `remove_region_vector`'s Option B block is at redact.py:205-220.

#### Target 3 — `app/services/redact.py` lines 245-252 (dispatcher inline comment `HONEST LIMITATION`)
[VERIFIED: redact.py:245-252]. Current text:
```
    # HONEST LIMITATION (mirrors replace_region_with_white_raster's docstring and
    # the module-level TRUE_REMOVAL_LIMITATION note): the dense branch removes the
    # COVERS' attack surface but does NOT delete the zero-area BLACK source paths
    # from the content stream — they remain, visually superseded by the opaque
    # image XObject. Recovery now requires removing the image AND per-path bbox
    # surgery (strictly harder than re-colouring vector covers, but not impossible).
    # True content-stream deletion of zero-area sources is deferred to a future
    # content-stream-surgery hotfix (Option B / #07).
```
**Rewrite note:** the last sentence ("True content-stream deletion ... is deferred to a future ... hotfix (Option B / #07)") is now false. This comment sits inside the dense/sparse dispatcher (which now runs AFTER the Option B call at redact.py:213). Honest rewrite: page-level zero-area sources have already been truly deleted upstream by Option B (`delete_zero_area_type_f_fills_inside`, redact.py:213); this dense branch's overlay is now a last-mile defence for form-XObject-internal residue (page-level-only strategy) + regex-miss fail-safe.

#### §1.4 — The OTHER `HONEST LIMITATION` markers in pdf_engine.py (NOT THREAT-02 targets)
There are exactly three more `HONEST LIMITATION` headings in `pdf_engine.py`, ALL inside Phase-7 Option B helpers and ALL already Option-B-accurate. **Do NOT rewrite these** (scope creep + risk). [VERIFIED: grep + read]:

| Line | Location | Why already accurate |
|------|----------|----------------------|
| `pdf_engine.py:1173` | `_build_shape1_candidate_index` docstring | Describes the regex-anchor fail-safe: a miss → cardinality "missing" → `return 0` + `logger.warning("option_b_parse_anomaly")` → existing dispatcher (Phase 4-6 Option A overlay) takes last-mile defence. This is the *Option B internal* limitation, correct as-is. |
| `pdf_engine.py:1343` | `delete_zero_area_type_f_fills_inside` docstring | Same fail-safe framing (regex miss → cardinality fail → return 0 + warning → existing dispatcher). Correct as-is. |
| `pdf_engine.py:1497` | `log_xobject_intersect` docstring | States page-level Option B does NOT descend into form-XObject internal streams (SEC-03 page-level-only); residue handled by existing dispatcher's dense/sparse branch. Correct as-is — in fact this is the SOURCE OF TRUTH the three targets should align TO. |

**Confidence: HIGH** — all six markers read directly from current source.

### §2 — DOC-01: HANDOFF.md §6 structure + insertion point + Option A sentence

[VERIFIED: HANDOFF.md]. Section 6 ("核心領域知識備忘(避免踩雷)") begins at line 142. Subsections:

| Subsection | Line | Heading |
|------------|------|---------|
| 6.1 | 146 | 為何用 PyMuPDF 而非 pypdf / PyPDF2 |
| 6.2 | 156 | Redaction 真正移除原理 (numbered 4-step code block, lines 158-167) |
| 6.3 | 175 | PDF.js viewport 座標換算(前端碰之前必讀) |
| 6.4 | 187 | 「永遠存新檔」是硬性規則 |
| **(insert 6.5 here)** | **between 195 and 198** | New: "Option B content-stream surgery" |
| 7 (next section) | 198 | 接手後第一週建議 |

**Insertion point:** after 6.4's last line (line 195, the `---` separator at line 196 precedes section 7). New 6.5 goes after 6.4's body and before the `---` at line 196 (i.e. as the last subsection of §6). Per success criterion 2, 6.5 must describe the **three-layer division of labour** (`apply_redactions` + Option A + Option B) and the **CAD-glyph vs general vector logo handling difference**.

**The Option A sentence that must change to "Option A + B 雙層防線":** the only mention of "Option A" in §6 is at line 172 (inside 6.2):
```
graphics=` 與 `images=` 的選項可調(`REMOVE_IF_TOUCHED` vs
`REMOVE_IF_COVERED`),影響「碰到邊就刪」還是「完全被蓋才刪」的行為 — milestone
v1.0 hotfix 06 調校過(dCt-residue Option A),動之前先看
`app/services/pdf_engine.py` 的 commit history。
```
The "(dCt-residue Option A)" reference at line 172 should be adjusted to reflect "Option A + B 雙層防線" (or cross-reference the new 6.5). Note: there is NO standalone "Option A is the only defence" sentence in HANDOFF.md to flip — the honesty rewrite lives mainly in the three docstrings (§1); HANDOFF.md's change is primarily the additive 6.5 + this one cross-reference adjustment. **Flag for planner:** confirm with success-criterion-2 wording whether the line-172 touch counts as "Option A 描述同步調整" — it is the only Option A description in §6.

**Three-layer facts for 6.5 (from §6 below):**
1. `apply_redactions` (truly removes normal-area text + fully-covered vectors + image pixels) — the baseline.
2. **Option B** (`delete_zero_area_type_f_fills_inside`, page-level content-stream surgery) — truly DELETES page-level zero-area `type='f'` CAD-glyph fills that `apply_redactions` cannot reach. Runs upstream.
3. **Option A** (`replace_region_with_white_raster` dense / `cover_zero_area_artefacts` sparse) — last-mile OVERLAY defence for form-XObject-internal residue (Option B is page-level-only) + Option B regex-miss fail-safe.

**CAD-glyph vs general vector:** general/normal-area vector logos are truly removed by `apply_redactions` (Option B is a no-op for them — SEC-02). CAD-glyph supplier marks decompose into many zero-area `type='f'` fills that `apply_redactions` leaves in the stream → Option B targets exactly these.

### §3 — DOC-02: PROJECT.md Key Decisions format + STATE.md Deferred text

#### PROJECT.md "## Key Decisions" table format
[VERIFIED: PROJECT.md:88-112]. The section starts at line 88. It is a **3-column markdown table**: `| Decision | Rationale | Outcome |` (header at line 92, separator at line 93). A new v1.1 row must match this exact 3-column shape. Outcome cells use markers: `✓ Validated (Phase N)`, `⚠️ Revisit`, `— Pending`. Existing rows relevant to the new entry:
- **Line 104:** `| Hotfix 06 — Option A raster overlay (取代 per-artefact white covers) | ... | ✓ Validated (LIVE-UAT 2026-05-27 LogoSwap (2)) |`
- **Line 105 (the row Option B invalidates):** `| Hotfix 06 / 接受 zero-area sources 仍在 content stream(Option A) | PyMuPDF API 限制無法刪零面積;Option A overlay 對使用者實質不可恢復,符合 v1 內網威脅模型;真正刪除留待 Option B(對外公開時) | ✓ Validated (T-02-07 mitigation,SECURED 5/5) |`

**New row to add (DOC-02 / success criterion 3):** "Hotfix v1.1 — Option B 落地". The **Rationale must cite the 2026-05-28 forensic attack evidence** (the deferral assumption "Option A is effectively unrecoverable for users" was disproven). Evidence citation point: `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/` [VERIFIED: dir exists with `_attack_proof_supplier_revealed.png`, `_attack_image_xobject_deleted.pdf`, `_attack_target_pre.png`, `_attack_orig_for_comparison.png`, 3 supplier PDFs, README.md]. **Flag for planner:** the line-105 row's Rationale ("真正刪除留待 Option B(對外公開時)") is now historically resolved — consider whether to leave it as-is (historical record) or annotate; success criterion 3 only requires ADDING the new row, not editing line 105. Note `/gsd-complete-milestone` also runs a full "Key Decisions audit" at close (§7 step `evolve_project_full_review`), so PROJECT.md gets a second pass during milestone close — avoid duplicating the row.

#### STATE.md "## Deferred Items" table + "Promoted from Deferred" note
[VERIFIED: STATE.md:74-90]. The Deferred Items table (`## Deferred Items`, line 74) is a 4-column table `| Category | Item | Status | Reason |`. **There is NO "Option B" row left in the active Deferred table** — Option B was already removed from the Deferred *table* at v1.1 launch. What remains is the "Promoted from Deferred to Active" note at lines 88-90:
```
**Promoted from Deferred to Active(2026-05-28):**

- ~~Option B — content-stream surgery 真正刪除 zero-area sources~~ → **v1.1 active(Phase 7 核心)**。原 deferral 假設「Option A 對使用者實質不可恢復」已被 2026-05-28 forensic attack script 證明不成立(Illustrator 可拔 image XObject overlay)。
```
**What "final-clean" means (success criterion 3):** the STATE.md Option B entry currently shows as a *promoted-from-deferred* note (struck-through item → "v1.1 active"). Phase 8 final-clean = update this note to reflect Option B is now **DONE/shipped** (Phase 7 complete + v1.1 LIVE), not merely "active". The two STATE.md Deferred *table* rows added during v1.1 (line 85 "Form XObject 內 zero-area fills 遞迴 surgery", line 86 "Zero-area type='s' stroke surgery") are genuinely deferred-onward and stay. **Flag for planner:** CONTEXT.md/ROADMAP refer to "Deferred 表的 Option B 條目" — but Option B is NOT in the Deferred *table*; it is in the *Promoted note* below the table. The final-clean target is the **Promoted note (lines 88-90)**, not a table row. STATE.md is also rewritten by `/gsd-complete-milestone` (status, current focus, Deferred Items) at close — coordinate so the final-clean is not overwritten or duplicated.

### §4 — DEPLOY-01: Zeabur/Docker deploy mechanics

[VERIFIED: Dockerfile, README.md, git remote, gitignore]

- **How push triggers deploy:** Zeabur watches the GitHub repo `https://github.com/sc126-cornell/LogoSwap.git` [VERIFIED: `git remote -v`]. A `git push origin master` triggers Zeabur's auto-build. **There is NO `zeabur.json` or `zbpack.json`** [VERIFIED: glob found none] — Zeabur **autodetects the `Dockerfile`** at repo root and builds it directly (Dockerfile presence overrides zbpack buildpack autodetection). The live site is `https://logoswap.scottchen0622.com` (Cloudflare DNS fronting Zeabur) [VERIFIED: README.md:11, PROJECT.md:26, CONTEXT.md:24].
- **`GITHUB_OWNER` build-arg / AGPL §13 `<OWNER>` sed:** [VERIFIED: Dockerfile:62-68]
  ```
  ARG GITHUB_OWNER=sc126-cornell
  RUN sed -i "s|<OWNER>|${GITHUB_OWNER}|g" /app/web/index.html /app/README.md
  ```
  The source tree keeps the literal `<OWNER>` (so `tests/test_agpl_compliance.py` stays green in dev mode); the image bakes the real owner at build time. The default `sc126-cornell` **matches the actual git remote owner** — so a Zeabur build with no `--build-arg` override produces the correct §13 disclosure URL `https://github.com/sc126-cornell/LogoSwap`. The placeholder appears in two source files: `web/index.html:419` (footer `<a href="https://github.com/<OWNER>/LogoSwap">`) and `README.md:22` [VERIFIED: grep]. **Planner action:** confirm Zeabur build either passes `GITHUB_OWNER=sc126-cornell` or relies on the matching Dockerfile default — no source edit needed; the §13 three-piece set is structurally unchanged this phase (LICENSE present, public GitHub repo, UI footer link).
- **Python 3.12 pin (both stages):** [VERIFIED: Dockerfile:14 `FROM python:3.12-slim-bookworm AS builder` + Dockerfile:28 `FROM python:3.12-slim-bookworm`]. Both stages are pinned to 3.12. **VERIFYING LIVE runtime is 3.12:** the running container exposes `GET /health` (5-field health check) [VERIFIED: HANDOFF.md:133, Dockerfile:79-80]. Options to confirm 3.12 on LIVE: (a) check whether `/health` returns a Python/runtime version field (planner should inspect the `/health` payload shape — HANDOFF.md calls it "五欄位健康檢查"); (b) Zeabur build log shows the base image tag; (c) if `/health` does not expose version, the 3.12 guarantee is structural (Dockerfile pin) and the IN-02 concern is satisfied by confirming the deploy used this Dockerfile, not a buildpack. Note `requirements.txt:2-3` documents the PyMuPDF wheel works on 3.14 too — so the audit-env-3.14 mismatch is NOT a defect; the pin is about regex/logging behaviour parity, guaranteed by the Dockerfile base image.
- **Deploy config Zeabur autodetects:** with no `zeabur.json`/`zbpack.json`, Zeabur uses the Dockerfile. `$PORT` is injected by Zeabur and consumed by the CMD `--port ${PORT:-8000}` [VERIFIED: Dockerfile:82-85]. `APP_BASE_PATH` defaults empty (root mount) [Dockerfile:48]; `UVICORN_WORKERS=2` default [Dockerfile:49]; `DATA_DIR=/data` is a VOLUME [Dockerfile:52,73]; `LOGOS_DIR=/app/logos` [Dockerfile:53].

### §5 — attack-sim mechanics (`tests/_illustrator_attack.py`)

[VERIFIED: tests/_illustrator_attack.py + tests/test_illustrator_attack_regression.py]. Three public functions:

| Function | Signature | Inputs | Returns |
|----------|-----------|--------|---------|
| `delete_image_xobjects_intersecting` | `(doc: fitz.Document, page_index: int, rect: tuple[float,float,float,float]) -> int` | open in-memory `fitz.Document`, page index, **PDF-point** rect (x0,y0,x1,y1) | int = actual content-stream substitution count (main regex + bare fallback). `0` = found image xrefs but regex missed OR no intersecting image. [VERIFIED: lines 105-192] |
| `render_region_white_pct` | `(pdf_path: Path\|str, page_index: int, rect: tuple[...]) -> float` | **path** to PDF, page index, PDF-point rect | float [0.0,100.0]; renders at `fitz.Matrix(4,4)` 4× zoom, clip=rect, white = all channels ≥250. [VERIFIED: lines 200-230] |
| `count_zero_area_fills_in_region` | `(pdf_path: Path\|str, page_index: int, rect: tuple[...]) -> int` | **path** to PDF, page index, PDF-point rect | int = zero-area `type='f'` count fully inside rect. Delegates to production `pdf_engine.count_zero_area_fills_fully_inside` via function-internal import. [VERIFIED: lines 238-263] |

**The two assertions (the gates) — from `test_illustrator_attack_regression.py:174-185`:**
```
assert white_pct >= 98.0    # gate (a): 視覺乾淨閘 (render region ≥98% white)
assert zero_area_count == 0 # gate (b): content-stream 乾淨閘 (zero-area type='f' count == 0 inside region)
```
[VERIFIED: test_illustrator_attack_regression.py:174-185]. There is also a precondition (lines 165-171): fail only if `n_deleted == 0 AND not region_is_clean` (i.e. no overlay to pull AND Option B failed = a real hole). This precondition was redesigned in 07-03 to acknowledge true removal (a clean region with nothing to pull is a PASS).

**How the regression test wires the helper to fixtures (the template the D-04 scratch should mirror):** [VERIFIED: test_illustrator_attack_regression.py:46-160]
1. Discovers `tests/fixtures/cad-glyph/*.pdf` + sidecar `.json` manifests (`_load_fixtures`).
2. Reads from manifest: `region_rect_pdf_points` (tuple → the rect), `region_rect_px`, `page_index`, `dpi`.
3. ingest → `pipeline.process_job(session_id, JobSpec(dpi=..., regions=[RegionMark(page=page_index, px_rect=...)], logo_id=None))` → `pipeline.output_path(session_id)`.
4. `fitz.open(output_pdf)` → `delete_image_xobjects_intersecting(doc, page_index, region_pdf_pts)` → `doc.save(attacked_pdf, garbage=4, deflate=True)`.
5. `render_region_white_pct(attacked_pdf, page_index, region_pdf_pts)` + `count_zero_area_fills_in_region(attacked_pdf, page_index, region_pdf_pts)` → two asserts.

**What the D-04 one-off scratch script needs to import/call** to run the same check against an arbitrary LIVE-downloaded PDF + chosen region:
- `from tests._illustrator_attack import delete_image_xobjects_intersecting, render_region_white_pct, count_zero_area_fills_in_region`
- Needs: the **downloaded output PDF path**, the **page_index**, and the **region rect in PDF points** (x0,y0,y1,y1). Since the LIVE-UAT region is drawn manually in the browser (D-03, not from a fixture manifest), the scratch script needs the region's PDF-point coords. **Flag for planner:** the browser sends PDF-point coords to `/process`; the scratch script author must capture the chosen region's PDF-point rect (e.g. from the `/process` request payload, browser devtools, or by re-deriving from the px rect + dpi using the same `coords` mapping the pipeline uses). This is the one non-trivial input-plumbing detail of D-04 — the helper functions themselves take a plain `(x0,y0,x1,y1)` tuple, so once the rect is known the calls are direct.
- The scratch script does NOT need pytest, fixtures, or `JobSpec` — it operates on the already-processed downloaded file (steps 4-5 above), skipping the ingest/process steps (those happen on the LIVE site through the browser).
- `import fitz` is allowed in the scratch script under the same test-harness exception (the AGPL AST guard scopes only `app/**/*.py`; `tests/` and scratch are exempt — see `tests/conftest.py:12` exception referenced at `_illustrator_attack.py:9-14`). [VERIFIED: _illustrator_attack.py:9-14]

### §6 — Option B facts for accurate docstrings (factual source of truth)

[VERIFIED: pdf_engine.py:1016-1541, redact.py:88-283]. For the THREAT-02 rewrites to be factually correct:

| Helper / fact | Verified behaviour |
|---------------|--------------------|
| `delete_zero_area_type_f_fills_inside(page, user_rect, tolerance=_DEGENERATE_BBOX_EPS)` | [pdf_engine.py:1311]. Page-level content-stream surgery: finds fully-inside-rect zero-area `type='f'` paths via `page.get_drawings()`, locates byte ranges via anchor regex over a 5-context safe-skip mask, splices them out, writes back via `doc.update_stream` (asymmetric multi-stream pattern). Returns the TRUE delete count (byte ranges spliced, WR-05 honest telemetry). Returns 0 on (a) no zero-area fills inside (SEC-02 no-op) or (b) cardinality mismatch (D-A5 fail-safe → `logger.warning("option_b_parse_anomaly")`, content stream UNTOUCHED). |
| `count_zero_area_fills_fully_inside(page, rect)` | [pdf_engine.py:856]. Counts `type='f'` zero-area (bbox W or H < `_DEGENERATE_BBOX_EPS=0.01`) drawings fully inside rect. Used by the dispatcher to choose dense vs sparse, and by the attack gate (b). |
| `_DISALLOWED_IN_BLOCK` fail-safe | [pdf_engine.py:451 `re.compile(rb"\bDo\b\|\bBT\b\|\bsh\b\|\bBI\b")`]. CR-01 over-delete guard: if a candidate `q...Q` block co-locates legitimate content (XObject `Do`, text `BT`, shading `sh`, inline image `BI`), the candidate is NOT indexed → that bbox treated as missing → cardinality fail-safe → existing Option A overlay takes last-mile defence. "Better not delete (overlay can cover) than over-delete (irreversible)." [VERIFIED: pdf_engine.py:1215-1222] |
| Page-level only + form-XObject log strategy (SEC-03) | [pdf_engine.py:1339-1341, 1483-1541]. `page.read_contents()` is page-level by API contract — form-XObject internal streams are NOT traversed. `log_xobject_intersect(page, rect, logger)` walks `page.get_xobjects()` (Form XObjects only) and emits `logger.warning("option_b_xobject_intersect")` when a Form XObject bbox intersects the rect. Never mutates. |
| Dispatcher wiring in `remove_region_vector` | [redact.py:205-220]. Option B runs AFTER the residual assertion, BEFORE the dense/sparse dispatcher: `deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, rect)` → if `>0` `logger.info("option_b_deleted")` → `pdf_engine.log_xobject_intersect(page, rect, logger=logger)`. Existing dispatcher (dense `replace_region_with_white_raster` / sparse `cover_zero_area_artefacts`) is downstream and unchanged (0 deletions). |
| Shape 1/2 single-pass locators | [pdf_engine.py:1144 `_build_shape1_candidate_index`, 1249 `_build_shape2_candidate_index`]. Shape 1 = PScript5 `q ... cm? m/l ... fillop ... Q`; Shape 2 = `<x> <y> <w> <h> re ... fillop`. Single-pass bbox-keyed index (07-03 perf fix 765s→<5s). |

**The honest claim Option B now supports (for all three rewrites):** zero-area `type='f'` CAD-glyph sources at the **page content-stream level** are now **truly deleted** (not just overlaid) before any overlay fires. The overlay (Option A) is now a **last-mile defence** that fires only when Option B cannot reach the residue: (1) the residue lives inside a **form XObject** (page-level-only strategy — logged, not deleted), or (2) the regex anchor missed and the **fail-safe returned 0** (cardinality mismatch / `_DISALLOWED_IN_BLOCK` co-located-content guard). Normal-area vector logos remain a **no-op** for Option B (SEC-02).

### §7 — `/gsd-complete-milestone` workflow expectations

[VERIFIED: $HOME/.claude/get-shit-done/workflows/complete-milestone.md]. The planner should sequence the milestone-close task LAST (per D-05). What the workflow expects and does:

- **Mode is `yolo`** [VERIFIED: config.json:41] → the "verify_readiness" milestone-scope confirmation is **auto-approved** (no prompt). The pre-close `audit-open` artifact audit still runs and shows output.
- **Requirements completion check:** it parses `REQUIREMENTS.md` traceability and surfaces any non-`[x]` rows. THREAT-02/DOC-01/DOC-02/DEPLOY-01 are currently `[ ]` Pending [VERIFIED: REQUIREMENTS.md:26,40,41,47 + traceability:84-87]. **The planner must ensure these four requirement checkboxes are flipped to `[x]` in REQUIREMENTS.md before milestone close**, or the workflow surfaces an "Unchecked Requirements" warning (proceed/audit/abort). This checkbox-flip is itself a DOC task.
- **It archives** ROADMAP.md + REQUIREMENTS.md to `.planning/milestones/v1.1-*.md`, runs a **full PROJECT.md evolution review** (Key Decisions audit, move Active→Validated, Out-of-Scope audit), reorganizes ROADMAP.md with milestone grouping (preserving Backlog), `git rm REQUIREMENTS.md`, updates STATE/MILESTONES/RETROSPECTIVE. **Implication:** PROJECT.md (DOC-02 row) and STATE.md (DOC-02 final-clean) get a second editing pass during close — the planner should treat the explicit DOC-02 edits as the primary write and let milestone-close audit reconcile, avoiding duplicate rows.
- **It creates the git tag itself:** step `git_tag` runs `git tag -a v1.1 -m "..."` and then asks "Push tag to remote? (y/n)". **The planner must NOT add a separate `git tag v1.1` task** — the tag is owned by `/gsd-complete-milestone`. (D-02 step 5 "tag v1.1" is satisfied BY running the milestone-close workflow.)
- **Branching strategy is `none`** [VERIFIED: config.json:13] → the `handle_branches` step is skipped.
- **`commit_docs: true`** [VERIFIED: config.json:3] → `.planning/` docs are committed (not stripped from staging).
- **Push:** the workflow's tag step offers to push the *tag*; the D-02 single push of the *branch* (master → origin) is a separate Phase 8 deploy task that happens earlier (step 2). The final "all push to origin" (D-02 step / success criterion 5) means master is pushed (it deploys) AND the v1.1 tag is pushed at close. **Flag:** `master` is currently **61 commits ahead of origin** [VERIFIED: `git branch -vv`] — the D-02 single push is large (carries Phase 6+7+8). No force-push needed (fast-forward ahead).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Attack-sim against LIVE-downloaded PDF | A new attack script / CLI runner | Import the 3 existing functions from `tests/_illustrator_attack.py` (D-04) | They are already VERBATIM-ported from the 2026-05-28 forensic evidence and battle-tested by 3 regression tests. New code = new surface + risk of diverging from proven attack mechanics. |
| Zero-area fill counting in the gate | Re-implement the counter | `count_zero_area_fills_in_region` → delegates to production `count_zero_area_fills_fully_inside` | Single source of truth; the gate must measure the same thing production decides on. |
| Git tag v1.1 | A standalone tag task | Let `/gsd-complete-milestone` create it (§7) | Workflow owns the tag; double-tagging fails / drifts. |
| AGPL §13 `<OWNER>` substitution | Editing source to hardcode owner | Dockerfile `sed` + `GITHUB_OWNER` build-arg (default already correct) | Source keeps `<OWNER>` so `test_agpl_compliance.py` stays green; image bakes the real owner. |

**Key insight:** This phase's entire value is *precision and discipline*, not new capability. Every "new" thing (scratch script, attack run) reuses Phase 6/7 assets; the only genuinely new artifacts are doc text and the (transient) scratch script.

## Runtime State Inventory

This phase includes string edits to docstrings/comments + a deploy. It is not a rename, but the deploy + scratch-script + real-PDF handling create real runtime-state concerns the grep audit won't catch:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore. Sessions are filesystem-transient (`DATA_DIR=/data`, 1h TTL). [VERIFIED: Dockerfile:51-52, HANDOFF.md:189-191] | None |
| Live service config | Zeabur build config lives in the Zeabur dashboard, NOT in git (no `zeabur.json`/`zbpack.json`). Zeabur autodetects the Dockerfile. AGPL `<OWNER>` is baked at build via `GITHUB_OWNER` build-arg (default `sc126-cornell`, matches remote). [VERIFIED: glob + Dockerfile:67 + git remote] | Confirm Zeabur build uses Dockerfile + correct/defaulted `GITHUB_OWNER`; verify LIVE `/health` reflects the new build (deploy succeeded). |
| OS-registered state | None (PaaS — no Task Scheduler / systemd / pm2 on the dev machine for this app). | None |
| Secrets/env vars | No app secrets (internal LAN, no auth — v1 design). Env vars (`PORT`, `APP_BASE_PATH`, `UVICORN_WORKERS`, `DATA_DIR`, `LOGOS_DIR`) are Dockerfile defaults / Zeabur-injected `$PORT`. [VERIFIED: Dockerfile:44-53,82-85] | None — code-only docstring edits don't read any renamed env var. |
| Build artifacts | The LIVE container is a fresh `docker build` on push (no stale local artifact concern). The Python 3.12 pin is in the Dockerfile (not affected by the local 3.14 audit env). [VERIFIED: Dockerfile:14,28] | Verify LIVE runtime is 3.12 (IN-02) per §4. |
| **Repo-tracked scratch / sensitive PDF (D-03/D-04)** | `.planning/debug/scratch/**` is **git-TRACKED** — the gitignore underscore guards (`/_*.py`, `/_*.pdf`, `/_*.png` at lines 36-38) are **root-anchored only** and do NOT cover the scratch subdir. [VERIFIED: .gitignore:33,36-38] | The D-04 scratch script and the D-03 real supplier PDF MUST be kept out of the commit: either delete the scratch script before the push, OR add a scratch-dir-anchored ignore. The real supplier PDF: `*-supplier-raw.pdf` (line 75) is NOT root-anchored so a PDF named with that suffix is ignored anywhere — recommend the planner instruct naming the LIVE-UAT input `*-supplier-raw.pdf` (or keep it entirely outside the repo tree). |

**The canonical question for this phase's runtime state:** *After the doc edits land and the push deploys, does any transient artifact (scratch script, real supplier PDF, attacked.pdf) leak into the public GitHub repo?* The answer must be NO — see the last row.

## Common Pitfalls

### Pitfall 1: Committing the D-04 scratch script or D-03 real PDF to the public repo
**What goes wrong:** `.planning/debug/scratch/**` is tracked; a scratch script left there gets pushed to the public GitHub repo, and a real supplier PDF (sensitive IP) could leak.
**Why it happens:** the root-anchored gitignore underscore guards give a false sense of safety — they do NOT apply inside `.planning/debug/scratch/`.
**How to avoid:** delete the scratch script after the attack-sim passes (D-04 says "retire after"); keep the real PDF outside the repo tree or name it `*-supplier-raw.pdf` (non-root-anchored ignore). Verify with `git status` before the D-02 push.
**Warning signs:** `git status` shows an untracked/new file under `.planning/debug/scratch/` or a `.pdf` not matching an ignore pattern.

### Pitfall 2: Double-tagging v1.1
**What goes wrong:** a Phase 8 task creates `git tag v1.1`, then `/gsd-complete-milestone`'s `git_tag` step tries again and fails (tag exists) or the two diverge.
**Why it happens:** D-02 lists "tag v1.1" as step 5 and D-05 lists milestone close — easy to plan both as tag creators.
**How to avoid:** the tag is created BY `/gsd-complete-milestone` (§7). The plan's milestone-close task is the single tag owner.
**Warning signs:** two tasks both mention `git tag v1.1`.

### Pitfall 3: Rewriting the wrong "HONEST LIMITATION" markers
**What goes wrong:** editing the three `HONEST LIMITATION` blocks inside the Phase-7 Option B helpers (`pdf_engine.py:1173/1343/1497`) instead of (or in addition to) the three THREAT-02 targets.
**Why it happens:** a naive `grep HONEST LIMITATION` returns 6 hits in `app/services/`; only 3 are THREAT-02 targets.
**How to avoid:** THREAT-02 targets are exactly: `pdf_engine.py:933` (`LIMITATION (be honest)`), `redact.py:6` (module `TRUE_REMOVAL_LIMITATION` prose), `redact.py:245` (dispatcher comment). The other three (§1.4) already describe Option B correctly — leave them.
**Warning signs:** a diff touches `pdf_engine.py` lines >1000.

### Pitfall 4: Forgetting to flip the four requirement checkboxes
**What goes wrong:** `/gsd-complete-milestone` surfaces an "Unchecked Requirements" warning because THREAT-02/DOC-01/DOC-02/DEPLOY-01 are still `[ ]` in REQUIREMENTS.md.
**Why it happens:** the checkbox flip is a separate doc edit, easy to miss.
**How to avoid:** include a task to set `[x]` on all four (and update the traceability table Status column from Pending) once their work is verified, before milestone close.
**Warning signs:** REQUIREMENTS.md lines 26/40/41/47 or traceability rows 84-87 still show Pending.

### Pitfall 5: Deploy succeeds at build but fails at runtime (uvicorn PATH)
**What goes wrong:** a Docker build success but container start failure ("uvicorn: not found").
**Why it happens:** `pip install --target /install` puts the `uvicorn` script under `/install/bin`, not the default PATH — already handled by `ENV PATH="/install/bin:$PATH"` at Dockerfile:44.
**How to avoid:** this is already fixed; just confirm LIVE `/health` returns 200 after deploy (the HEALTHCHECK catches it). The Dockerfile comment at lines 38-43 documents this exact prior incident.
**Warning signs:** Zeabur shows build-success but the site 502s / health check fails.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| git remote `origin` | D-02 push | ✓ | `https://github.com/sc126-cornell/LogoSwap.git` | — |
| Zeabur (PaaS) | DEPLOY-01 LIVE | Assumed up (live URL exists; CONTEXT.md says "若 Zeabur 仍開著") | — | D-01/ROADMAP allow local Docker fallback |
| Live site | LIVE-UAT | `https://logoswap.scottchen0622.com` (Cloudflare DNS) | — | local `docker compose up` |
| `tests/_illustrator_attack.py` | D-04 scratch | ✓ | repo file | — (REQUIRED) |
| Engineer's real supplier CAD-glyph PDF | D-03 LIVE-UAT | ✗ — **must be supplied by engineer** | — | **No fallback** — this is a blocking prerequisite; a repo fixture is explicitly NOT used per D-03 |
| Python 3.12 (LIVE container) | IN-02 parity | ✓ structurally (Dockerfile pin both stages) | 3.12-slim-bookworm | — (verify via deploy, §4) |

**Missing dependencies with no fallback:**
- **Engineer's fresh real supplier CAD-glyph PDF** — D-03 mandates the original un-sanitized supplier PDF (not a repo fixture). The planner MUST list "sample acquisition from engineer" as a BLOCKING prerequisite of the LIVE-UAT task. Until it arrives, DEPLOY-01's end-to-end step cannot complete.

**Missing dependencies with fallback:**
- **Zeabur availability** — if Zeabur is closed, ROADMAP success criterion 4 + REQUIREMENTS DEPLOY-01 explicitly allow "本機 Docker" (local Docker) as the LIVE environment. The attack-sim gate is identical regardless of host.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Zeabur autodetects the Dockerfile (no `zeabur.json`/`zbpack.json` present) and builds it on push | §4 | If Zeabur defaults to a buildpack instead of the Dockerfile, the 3.12 pin + `<OWNER>` sed would NOT apply → LIVE could run wrong Python or ship `<OWNER>` literal. Mitigation: verify the Zeabur build log shows Dockerfile build + check the LIVE footer renders `sc126-cornell` not `<OWNER>`. [Confidence: HIGH that no config files exist; MEDIUM on Zeabur's autodetect precedence — verify in the build log] |
| A2 | `/health` (五欄位) may or may not expose the Python runtime version | §4 | If it doesn't, "verify LIVE is 3.12" relies on the Dockerfile pin + build log rather than a runtime probe. Low risk — the pin is structural. Planner should inspect the `/health` payload shape during UAT to decide the verification method. |
| A3 | The line-172 "(dCt-residue Option A)" reference in HANDOFF.md §6.2 is the "Option A description" that success-criterion-2 wants adjusted | §2 | If the intent was a different/standalone "Option A is the only defence" sentence, none exists in HANDOFF.md — the change is then just the additive 6.5. Low risk; flagged for planner confirmation. |
| A4 | "final-clean of the Option B Deferred entry" targets the STATE.md *Promoted note* (lines 88-90), since Option B is no longer in the Deferred *table* | §3 | If a reviewer expects a table-row edit, they'll find none. The Promoted note is the only Option B artifact left in STATE.md Deferred section. Low risk; explicitly flagged. |

## Open Questions

1. **Region PDF-point coords for the D-04 scratch script**
   - What we know: the helper functions take a plain `(x0,y0,x1,y1)` PDF-point tuple; the regression test reads them from a fixture manifest.
   - What's unclear: for a manually-drawn LIVE-UAT region (D-03, no manifest), how does the scratch-script author obtain the exact PDF-point rect? Options: capture the `/process` request payload, read browser devtools, or re-derive from the px rect + dpi via the pipeline's `coords` mapping.
   - Recommendation: the planner should make "capture the chosen region's PDF-point rect" an explicit sub-step of the LIVE-UAT task (e.g. note it from the `/process` POST body in browser network tab). This is the only non-trivial plumbing in D-04.

2. **Zeabur build-arg passing for `GITHUB_OWNER`**
   - What we know: Dockerfile default is `sc126-cornell`, which matches the remote owner.
   - What's unclear: whether the current Zeabur project passes an explicit `--build-arg` or relies on the default.
   - Recommendation: since the default is correct, no action needed unless the LIVE footer shows a wrong owner; verify the footer renders `sc126-cornell` after deploy.

## Project Constraints (from CLAUDE.md)

- **PyMuPDF AGPL seam:** `import fitz` only in `app/services/pdf_engine.py` [VERIFIED: pdf_engine.py:21 is the sole `import fitz` in `app/`]. Phase 8 touches only docstrings/comments in `pdf_engine.py` + `redact.py` — must NOT add any `import fitz` elsewhere. The §13 three-piece set (public GitHub + LICENSE + UI footer source link) is structurally unchanged this phase.
- **Python 3.12 mandate (IN-02):** Dockerfile both stages pinned; LIVE must run 3.12 (verify per §4). The 3.14 audit env is not a defect (PyMuPDF wheel is forward-compatible) — the pin is for regex/logging parity.
- **GSD workflow enforcement:** all edits go through a GSD command (this phase runs under `/gsd-execute-phase`). No direct repo edits outside the workflow.
- **minimum-change discipline (5330290):** doc phase must not smuggle production-logic changes or nice-to-have polish. The Backlog deferred items stay deferred.
- **Discussion language:** Traditional Chinese (繁體中文) per user memory — docstring rewrites + HANDOFF 6.5 should follow the existing bilingual convention in those files (HANDOFF.md is zh-TW; the docstrings mix English + zh-TW comments as the surrounding code does).

## State of the Art

| Old (pre-Phase-7) | Current (post-Phase-7, what Phase 8 documents) | When Changed | Impact |
|-------------------|------------------------------------------------|--------------|--------|
| Zero-area `type='f'` CAD-glyph sources only OVERLAID (Option A); recovery = pull image XObject + per-path bbox surgery | Page-level zero-area `type='f'` sources TRULY DELETED upstream (Option B); overlay = last-mile defence for form-XObject residue + regex-miss fail-safe | Phase 7 (2026-05-28) | The three docstrings (THREAT-02) and HANDOFF/PROJECT/STATE must now say "deleted, not overlaid" for the page-level case |
| T-02-07 "CLOSED with documented residual" | T-02-07 + T-06-01 "CLOSED via Option B" | Phase 7 close | THREAT-01 already updated in Phase 6/7 SECURITY.md; THREAT-02 is the docstring catch-up |

**Deprecated/outdated language to remove in the three docstrings:**
- "True deletion of zero-area sources requires content-stream surgery (a candidate hotfix for a future iteration / #07 / Option B)" — Option B shipped; this is now false in all three targets.

## Sources

### Primary (HIGH confidence — this repo's actual files, re-read this session)
- `app/services/pdf_engine.py` — lines 21 (fitz seam), 451 (`_DISALLOWED_IN_BLOCK`), 856-899 (`count_zero_area_fills_fully_inside`), 903-948 (`replace_region_with_white_raster` + THREAT-02 target 1), 1016-1541 (Phase 7 Option B helpers + the 3 non-target `HONEST LIMITATION` markers at 1173/1343/1497)
- `app/services/redact.py` — lines 6-36 (THREAT-02 target 2, `TRUE_REMOVAL_LIMITATION` prose), 205-220 (Option B dispatcher wiring), 245-252 (THREAT-02 target 3)
- `tests/_illustrator_attack.py` — lines 9-14 (AGPL test exception), 105-263 (3 public attack-sim functions)
- `tests/test_illustrator_attack_regression.py` — lines 46-185 (fixture wiring + the two gate assertions)
- `HANDOFF.md` — section 6 structure (142-195), Option A reference at 172, §13 facts
- `.planning/PROJECT.md` — Key Decisions table format (88-112), live URL (26)
- `.planning/STATE.md` — Deferred Items table (74-86) + Promoted note (88-90)
- `.planning/REQUIREMENTS.md` — req text (26,40,41,47) + traceability (84-87)
- `.planning/ROADMAP.md` — Phase 8 section (90-101)
- `Dockerfile` — 3.12 pin (14,28), `GITHUB_OWNER` sed (62-68), CMD/`$PORT` (82-85), PATH fix (38-44)
- `requirements.txt` — pins + 3.14-compat note (1-19)
- `web/index.html` — §13 footer `<OWNER>` (419), `README.md` `<OWNER>` (22)
- `.gitignore` — scratch-dir tracking + root-anchored guards (28-75)
- `.planning/config.json` — mode yolo, commit_docs true, nyquist_validation false, branching none
- `$HOME/.claude/get-shit-done/workflows/complete-milestone.md` — milestone-close behaviour (tag, archive, audit)
- `git remote -v` / `git branch -vv` / `git tag` — remote owner `sc126-cornell`, master ahead 61, only tag `v1.0`
- `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/` — forensic evidence dir (DOC-02 citation point) confirmed present

### Secondary / Tertiary
- None — no web research needed; all findings are repo-grounded and re-verified at source.

## Metadata

**Confidence breakdown:**
- THREAT-02 targets + non-targets: HIGH — all 6 markers read directly; line citations re-verified
- DOC-01/DOC-02 structure + insertion points: HIGH — read directly; two minor interpretation flags raised (A3, A4)
- DEPLOY-01 deploy mechanics: HIGH on Dockerfile/remote facts; MEDIUM on Zeabur autodetect precedence (A1) + `/health` version exposure (A2) — both verifiable during deploy
- attack-sim mechanics: HIGH — signatures + assertions + wiring read directly
- Milestone-close sequencing: HIGH — workflow file read directly; tag-ownership + checkbox-flip flagged

**Validation Architecture:** SKIPPED — `workflow.nyquist_validation: false` in config.json (no-op per carried-forward decisions).

**Security Domain:** Near no-op this phase per CONTEXT.md carried-forward note — THREAT-02 is docstring honesty (not a new mitigation), no threat-surface change. The standard secure gate still runs at phase boundary; no new ASVS categories apply (no auth, no new input surface, no crypto change; AGPL §13 structure unchanged).

**Research date:** 2026-05-28
**Valid until:** 2026-06-04 (7 days — the LIVE deploy state + git-ahead count are fast-moving; the doc/code citations are stable until the files are edited by this phase's own execution)
