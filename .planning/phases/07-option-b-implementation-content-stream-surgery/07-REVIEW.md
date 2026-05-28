---
phase: 07-option-b-implementation-content-stream-surgery
reviewed: 2026-05-28T00:00:00Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - app/services/pdf_engine.py
  - app/services/redact.py
  - tests/test_pdf_engine.py
  - tests/test_illustrator_attack_regression.py
  - tests/test_redact.py
  - tests/fixtures/cad-glyph/figure-glyph-01.json
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-05-28
**Depth:** deep
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 7 implements Option B — page-level content-stream surgery to truly delete
zero-area `type='f'` fills (CAD-glyph supplier-logo decompositions) instead of
overlaying/covering them. The architecture is sound: a 5-context safe-skip mask, two
single-pass bbox-keyed candidate indexes (Shape 1 q...Q / Shape 2 `re`), a bbox-keyed
cardinality fail-safe that returns 0 and never writes back on a miss, and an asymmetric
multi-stream write-back ported verbatim from the verified attack helper. The AGPL seam is
intact (`import fitz` confined to `pdf_engine.py:21`; verified by grep and the AST test).
redact.py is strictly additive (git diff: 0 deletion lines), preserving the existing
Hotfix-06 dispatcher verbatim. All 64 reviewed tests pass (17 TEST-03 + 3 attack
regression + 44 redact), and the Phase 6→7 xfail handoff completed (marker removed, 3
fixtures PASS).

The implementation's fail-safe discipline is genuinely strong for the *under-delete*
direction: a regex miss leaves the stream untouched and degrades to the prior Phase 4-6
defence. However, the review surfaced one **over-delete data-loss path that the fail-safe
does NOT catch** (CR-01, BLOCKER) and a cluster of correctness/robustness gaps concentrated
in the Shape 2 detector — which, unlike Shape 1, never received the 07-03 `_NUMBER`
leading-dot fix and carries a dangling-operator splice bug. None of the Shape 2 fill-operator
variants (`f*`, `B`, `b`, `B*`, `b*`) nor leading-dot reals are exercised by any test.

## Critical Issues

### CR-01: Whole `q...Q` block deletion can over-delete legitimate co-located content (data loss)

**File:** `app/services/pdf_engine.py:1083-1134` (index build) + `1346-1360` (splice)
**Issue:** `_build_shape1_candidate_index` stores the **entire** `q...Q` block byte range
(`_Q_BLOCK_RE` `start, end`) as the deletion range for a matched zero-area fill. The bbox
is computed only from the block's `m`/`l` points and a fill operator is merely required to
*exist* — there is no check that the block contains *only* the zero-area fill. When a
`q...Q` block contains a zero-area path (collinear `m`/`l` points → zero-area union bbox)
AND other legitimate content in the same wrapper (a `/Fm0 Do` Form-XObject invocation,
another visible path, an image `Do`, etc.), splicing the whole block silently deletes that
co-located content.

Reproduced directly against the index builder:
```
input block : q 10 20 m 10 100 l f /Fm0 Do Q
indexed key : (10.0, 20.0, 10.0, 100.0)   # zero-width union -> indexed
spliced range covers: b'q 10 20 m 10 100 l f /Fm0 Do Q'   # /Fm0 Do destroyed
```
The cardinality fail-safe (D-A5) does **not** protect against this: the key *exists* in the
index (it is a match, not a miss), so deletion proceeds. The regression-test safety gates
(`white>=98%` / `zero_area_count==0`) cannot catch it either — deleting *extra* content only
makes the region cleaner, never dirtier. This is exactly the "over-delete = silent
corruption" threat the phase brief names as the top risk, and it directly violates the
project's core value ("乾淨地移除而非破壞 wanted content"). Real-world trigger probability
depends on supplier emit style (PScript5 usually wraps one graphic per `q...Q`, lowering but
not eliminating the risk), but there is no guard and no fail-safe, so when it fires it is
unrecoverable data loss in the output PDF.

**Fix:** Narrow the Shape-1 deletion range to the *path sub-span* rather than the whole
`q...Q` wrapper, OR refuse to index any block that contains non-path content. Concretely,
before indexing a block, verify the body contains nothing but path-construction
(`m`/`l`/`h`/`re`), colour, and fill operators (no `Do`, no nested non-path `q` content, no
unmasked text). If the body has extra operators, route the ZAF to `has_mixed_empty_zaf`
fail-safe instead of deleting:
```python
# after collecting points and confirming a fill op exists:
_DISALLOWED_IN_BLOCK = re.compile(rb"\bDo\b|\bBT\b|\bsh\b|\bBI\b")
if _DISALLOWED_IN_BLOCK.search(body):
    # block carries co-located content; whole-block splice would over-delete.
    # Do NOT index this candidate -> dispatch will treat the ZAF key as missing
    # -> D-A5 fail-safe (return 0, no destructive write).
    continue
```
A tighter alternative is to compute the byte sub-range from the first path operand to the
fill operator and splice only that, leaving the wrapper and siblings intact.

## Warnings

### WR-01: Shape 2 detector never got the 07-03 `_NUMBER` leading-dot fix

**File:** `app/services/pdf_engine.py:358, 366-369`
**Issue:** The 07-03 fix replaced `-?\d+\.?\d*` with `_NUMBER = [-+]?(?:\d+\.?\d*|\.\d+)`
for Shape 1 (`_CM_RE`, `_POINT_RE`) to handle leading-dot reals (`.5`, `-.061`) that
"PScript5 供應商 CAD glyph 大量使用". But `_RE_FILL_RECT_RE` (x/y/w/h groups) and
`_SAFE_BETWEEN_TOKEN`'s numeric branch still use the **old buggy** `-?\d+\.?\d*`. Verified:
```
".5 10 0 80 re f"     -> x captured as b'5'  (skips '.5', mis-parses operands)
"-.061 10 0 80 re f"  -> x captured as b'061' = 61 (gross bbox distortion)
"10 20 80 .0 re f"    -> NO MATCH AT ALL (leading-dot height -> regex misses the rect)
```
A supplier whose `re`-form CAD fills use leading-dot reals (legal per ISO 32000-1 §7.3.3,
and explicitly called out as common) will produce wrong bboxes (key miss → fail-safe → no
deletion) or no match at all. Option B then deletes nothing for that supplier class and
falls back to the Phase 4-6 overlay/cover — i.e. the recoverable-content failure mode
Phase 7 exists to close. Degrades safely (no corruption) but defeats the feature's purpose
for an important supplier class. The fix doc itself documents this exact root cause for
Shape 1; it must be applied to Shape 2.
**Fix:** Use the shared `_NUMBER` pattern for the x/y/w/h groups in `_RE_FILL_RECT_RE` and
for the numeric branch of `_SAFE_BETWEEN_TOKEN`:
```python
_RE_FILL_RECT_RE = re.compile(
    rb"(?P<x>" + _NUMBER + rb") \s+ (?P<y>" + _NUMBER + rb") \s+ "
    rb"(?P<w>" + _NUMBER + rb") \s+ (?P<h>" + _NUMBER + rb") \s+ re \b ...",
    re.VERBOSE,
)
# and in _SAFE_BETWEEN_TOKEN: replace rb"-?\d+\.?\d* " with _NUMBER + rb" "
```

### WR-02: Shape 2 `f*`/`b*`/`B*` fill leaves a dangling `*` after splice (malformed output)

**File:** `app/services/pdf_engine.py:372-373`
**Issue:** The `fillop` group is `(?P<fillop>f\*|f|F|B\*|b\*|B|b)` followed by `\b`. After a
`*`, the next byte is whitespace; `\b` between `*` (non-word) and whitespace (non-word) is
**false**, so the `f\*\b` / `b\*\b` / `B\*\b` alternatives never match. The engine backtracks
to the bare `f`/`b`/`B` (which satisfies `\b` because the following `*` is non-word), so the
match span **excludes the trailing `*`**. Splicing that range leaves an orphaned `*`:
```
input : q 10 20 0 80 re f* Q
match : b'10 20 0 80 re f'   (the '*' is NOT consumed)
after splice: b'q * Q'       <-- dangling '*' in the content stream
```
This is malformed PDF output on the surgery path (the very thing the phase guards against).
Most readers tolerate a stray token, but it is genuine content-stream litter and a latent
parser hazard. Same defect would also strand the `*` of any even-odd fill.
**Fix:** Drop the trailing `\b` after the `fillop` group (the operator alternation already
self-delimits), or replace it with `(?![A-Za-z*])` so the full `f*`/`b*`/`B*` token is
captured:
```python
(?P<fillop>f\*|f|F|B\*|b\*|B|b)(?![A-Za-z*])
```

### WR-03: Inline-image safe-skip mask terminates early on a false `EI` token in binary data

**File:** `app/services/pdf_engine.py:331` (`BI \b [\s\S]*? \b ID \b [\s\S]*? \b EI \b`)
**Issue:** Inline-image binary data (after `ID`) is arbitrary bytes and can legally contain a
whitespace-delimited `EI` token. The non-greedy `[\s\S]*? \b EI \b` stops at the **first**
such `EI`, leaving the remaining binary tail UNMASKED. The `\b` boundary does NOT help when
the false `EI` is space-delimited (it is word-boundary-clean). Reproduced:
```
BI /W 4 /H 1 /BPC 8 ID <..bin.. EI ..bin..> 10 20 0 80 re f ... EI
-> 're f' lands in an UNMASKED region (mask byte == 1)
```
If the unmasked tail's bytes happen to match a shape detector AND its computed bbox rounds
to the same key as a real ZAF, that binary-pointing byte range enters `ranges_to_delete` and
corrupts the inline image (over-delete). Inline images are rare in CAD supplier PDFs and the
bbox-collision precondition is narrow, so this is a latent rather than likely path — but the
mask is documented as a *security boundary* and it has a hole.
**Fix:** Inline-image length is recoverable from `/L`/`/Length` when present; otherwise the
robust solution is a small stateful tokenizer that, on `ID`, scans to a `EI` that is
preceded by whitespace AND followed by whitespace/delimiter AND respects declared length.
At minimum, document the limitation and add a regression case asserting the mask covers an
inline image whose binary payload contains a standalone `EI`.

### WR-04: `_locate_shape2_byte_range` is dead code with a stale (unsafe) cardinality rule

**File:** `app/services/pdf_engine.py:1191-1213`
**Issue:** After the 07-03 rework, the dispatch loop iterates `shape2_index[key]` directly
(lines 1352-1357) and never calls `_locate_shape2_byte_range`. Grep confirms zero callers in
`app/` and `tests/`. The 07-03 SUMMARY says it was "保留供既有引用" (kept for existing
references) but there are none. Worse, it still encodes the OLD `if len(candidates) == 1`
single-match rule — the exact rule 07-03 abandoned for the duplicate-bbox bug. If a future
contributor wires it back in (its name and signature invite it), it silently reintroduces the
duplicate-bbox miss the rework fixed. Dead code that is also a behavioural trap.
**Fix:** Delete `_locate_shape2_byte_range` (and its docstring). The dispatch loop is the
single source of truth for the ≥1 bbox-keyed cardinality.

### WR-05: `delete_..._inside` returns `len(zafs)` (intent count), not actual deletions

**File:** `app/services/pdf_engine.py:1374`
**Issue:** The function returns `len(zafs)` — the count of *detected* ZAFs — not the number
of byte-ranges actually spliced. On the success path these coincide (post-condition
`count_after == 0` holds, confirmed by tests), and the value feeds only the `option_b_deleted`
info log. But the contract docstring says "Returns the count of paths deleted," which is not
what the code returns if detection and deletion ever diverge (e.g. a future change that
matches more/fewer ranges than detected ZAFs at a key). The number is purely advisory, so
this is not a safety bug — but the docstring overstates the guarantee and an operator reading
the log could be misled during an incident.
**Fix:** Either return `len(ranges_to_delete)` (true delete count) or amend the docstring to
"Returns the count of fully-inside zero-area `type='f'` fills detected and scheduled for
deletion." Prefer the former for honest telemetry.

### WR-06: Shape 2 fill-operator variants and leading-dot reals are entirely untested

**File:** `tests/test_pdf_engine.py` (all 17 cases) + `tests/test_redact.py:725-811`
**Issue:** Every Option B fixture uses `Shape.draw_rect(W=0)` or `draw_line`, which emit
`re ... h ... rg f` (plain `f`) or `... l ... f` (plain `f`). No test exercises `f*`, `B`,
`b`, `B*`, `b*` fill operators, nor leading-dot real operands, nor a `re` fill with a
negative w/h (the Pitfall-5 case the code explicitly handles at line 1175). As a result the
WR-01 leading-dot bug, the WR-02 dangling-`*` bug, and the negative-w/h handling are all
unverified. The test suite over-indexes on the two PyMuPDF-synthesizable shapes and leaves
the hand-rolled regex's actual edge surface uncovered.
**Fix:** Add unit tests that build raw content streams (via `doc.update_stream`) containing:
(a) `re ... f*` zero-area fill → assert deleted with no dangling `*`; (b) leading-dot
operands `.5 .061 0 .0 re f` → assert correct bbox/deletion; (c) a `re` with negative w/h
that is NOT zero-area → assert NOT indexed/deleted. These directly lock WR-01/WR-02/Pitfall-5.

## Info

### IN-01: `_FILL_OP_RE` matches `f*` as `f` (benign for its presence-check use)

**File:** `app/services/pdf_engine.py:414`
**Issue:** `_FILL_OP_RE = rb"\b(?:f\*|f|F|B\*|b\*|B|b)\b"` matches `f*` as just `f` for the
same trailing-`\b` reason as WR-02. It is used only as a boolean presence check
(`if not _FILL_OP_RE.search(body)`, line 1110), so matching `f` instead of `f*` still
returns truthy — no functional impact. Worth aligning with the WR-02 fix for consistency so
the constant doesn't mislead a future reader into reusing it for span capture.
**Fix:** Apply the same `(?![A-Za-z*])` boundary when the WR-02 fix lands.

### IN-02: Environment runs Python 3.14 / PyMuPDF 1.27.2.3 vs CLAUDE.md-mandated Python 3.12

**File:** (environment, not a source file)
**Issue:** The review environment is Python 3.14; CLAUDE.md mandates Python 3.12 (and warns
3.14 is "too new for some transitive deps"). Tests pass on 3.14, but CI/deploy parity should
be confirmed so behaviour (esp. regex/logging) matches the deploy target.
**Fix:** Verify the deployment/CI pins Python 3.12 per CLAUDE.md; no source change required.

### IN-03: `expected_zero_area_count_*` manifest fields are documentary only (not asserted)

**File:** `tests/fixtures/cad-glyph/figure-glyph-01.json:16-18`
**Issue:** The manifest records `expected_zero_area_count_pre_process: 3225`,
`original_supplier_zero_area_count: 3225`, and `expected_zero_area_count_post_build: 6289`,
but the regression test reads only `region_rect_pdf_points` / `region_rect_px` / `dpi` /
`page_index`. The count fields are never asserted, so fixture drift (e.g. a re-sanitize that
changes the glyph count) would go unnoticed. The px/pts pair IS internally consistent
(px = pts × 2.0 at dpi=144, verified). `synthetic: false` correctly flags real provenance.
**Fix:** Optionally assert `count_zero_area_fills_in_region(...)` against
`expected_zero_area_count_*` as a fixture-integrity precondition, so a stale fixture fails
loudly rather than silently passing on a different shape.

### IN-04: Regression-test precondition redesign is sound (no action; recorded for the record)

**File:** `tests/test_illustrator_attack_regression.py:157-185`
**Issue (verification, not a defect):** The 07-03 precondition redesign replaces
`assert n_deleted >= 1` with `if n_deleted == 0 and not region_is_clean: fail`. Traced all
branches: the two real safety gates (`white_pct >= 98.0`, `zero_area_count == 0`) remain
**unconditional asserts** that run regardless of the precondition, so the redesign can only
*add* a failure path, never suppress a real failure. A genuinely-failing attack with an
overlay present still fails the hard gates; the only PASS route requires both gates green.
The redesign correctly admits the legitimate Option-B-true-deletion case (no overlay to
pull, region already clean) without weakening either threshold. No change needed.

---

_Reviewed: 2026-05-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
