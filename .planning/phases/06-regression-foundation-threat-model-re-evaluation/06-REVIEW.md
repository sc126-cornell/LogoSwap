---
phase: 06-regression-foundation-threat-model-re-evaluation
reviewed: 2026-05-28T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - scripts/sanitize_fixture.py
  - tests/_illustrator_attack.py
  - tests/test_illustrator_attack_regression.py
  - tests/fixtures/cad-glyph/README.md
  - tests/fixtures/cad-glyph/text-glyph-01.json
  - tests/fixtures/cad-glyph/figure-glyph-01.json
  - tests/fixtures/cad-glyph/mixed-glyph-01.json
  - .gitignore
findings:
  critical: 1
  warning: 7
  info: 5
  total: 13
status: fixed
fixed_at: 2026-05-28T00:00:00Z
fixed_count:
  critical: 1
  warning: 7
  info: 0
  total: 8
deferred_count:
  info: 5
---

# Phase 6: Code Review Report

**Reviewed:** 2026-05-28T00:00:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 6 is test + scripts + docs only (production `app/**/*.py` untouched, by design).
Three deliverables drive the v1.1 regression baseline:

1. `scripts/sanitize_fixture.py` — supplier IP scrubber with self-assert gates.
2. `tests/_illustrator_attack.py` — verbatim port of the 2026-05-28 attack reproduction.
3. `tests/test_illustrator_attack_regression.py` — strict-xfail handoff signal to Phase 7.

The decorator order (parametrize above xfail), `JobSpec` instantiation (not raw dict), the
AGPL seam (only `app/**/*.py` is guarded; `import fitz` in `scripts/` + `tests/` is the
documented exception per `tests/conftest.py:12` and `tests/test_redact.py:1190`), and the
multi-stream `update_stream` asymmetric write pattern are all correctly preserved.

The single **blocker** finding is a numeric-vs-string-key bug in `_metadata_all_empty` that
will silently report "metadata empty" when in fact the producer/creator fields are still
populated — defeating the **first** of the four self-assert gates that the README + AGPL
§13 statement publicly promises was upheld for every committed fixture. The remaining
warnings cover sidecar schema drift, regex robustness on real PDFs, fragile path
substring matching on Windows, and a few minor issues that will surface as test failures
in Phase 7 if not addressed.

## Critical Issues

### CR-01: `_metadata_all_empty` uses wrong key names — self-assert is a no-op

**File:** `scripts/sanitize_fixture.py:196-222` (also affects line 540, line 656)
**Issue:**
`_USER_METADATA_FIELDS` lists keys as PyMuPDF API names (`"author"`, `"producer"`,
`"creationDate"`, etc.). However, `doc.metadata` in PyMuPDF 1.27.x returns a dict keyed
by the **PDF `/Info`-dict spelling** with capitalized first letter for *most* fields
(`"author"` lowercase is correct, but `"creationDate"`/`"modDate"`/`"trapped"` are
canonicalized differently across PyMuPDF versions, and `doc.set_metadata({k: "" for k in
_USER_METADATA_FIELDS})` at line 499 also uses these keys — meaning whatever you wrote
through `set_metadata`, you can read back through `doc.metadata` with the same key only
if PyMuPDF round-trips the dictionary verbatim).

More importantly, **the loop short-circuits on the very first match**: line 220 reads
`v = md.get(field)` and returns `False` only when `v not in (None, "", b"")`. If
PyMuPDF returns the empty string for fields you set to `""` (the happy path), the loop
returns `True` — but if PyMuPDF stores those fields under the canonical PDF spelling
(`/Author`, `/Producer`, `/CreationDate`) and `doc.metadata` exposes them under
`"author"` / `"producer"` / `"creationDate"`, then a *stray* leftover field your script
never touched (e.g. the PDF had `/PTEX.Fullbanner` or a custom XMP key surfaced via
PyMuPDF metadata) will be **invisible** to this check — `md.get("PTEX.Fullbanner")`
returns `None`, the loop happily passes.

The bigger problem: the docstring at line 209-216 explicitly states "本 check 只看 user
fields" — but that means **any future supplier PDF carrying custom `/Info` keys outside
the hardcoded 9-field list will pass the self-assert with the leak still in the file.**
Combined with `garbage=4, deflate=True, clean=True` at line 600 (which does scrub many
but not all `/Info` keys), there is a non-zero residual risk that a sanitized fixture
gets committed to public repo with a leaked custom metadata key — directly violating
the README §4 AGPL §13 statement at `tests/fixtures/cad-glyph/README.md:72-78`.

This is the **first** of four self-assert gates that the README publicly promises was
upheld, and it is currently the weakest. For a script whose entire purpose is "we
can prove this fixture is safe to publish under AGPL", a self-assert that only checks a
hardcoded denylist of 9 well-known keys is a Critical-tier gap.

**Fix:**
Iterate the actual keys present in `doc.metadata` (allowlist style: anything not in a
known-computed-only set must be empty). Computed-only fields per PyMuPDF docs are
`format` and `encryption`; everything else in `doc.metadata` is `/Info` content:

```python
_COMPUTED_METADATA_FIELDS = frozenset({"format", "encryption"})

def _metadata_all_empty(doc: fitz.Document) -> bool:
    """Allow-list check: every non-computed field in doc.metadata must be empty/None.

    Computed fields (format, encryption) are derived from PDF structure, not /Info, and
    are NOT cleared by set_metadata; ignore them. Every OTHER key is treated as
    potentially-leaked supplier IP — if any non-computed value is non-empty, fail.
    """
    md = doc.metadata or {}
    for field, value in md.items():
        if field in _COMPUTED_METADATA_FIELDS:
            continue
        if value not in (None, "", b""):
            return False
    return True
```

Also extend the test pass at line 548 to iterate `page.get_text("dict")` blocks AND
`doc.xref_xml_metadata()` (or equivalent) to confirm XMP stream is also empty — the
current self-assert only checks `page.get_text()` for supplier name, not the XMP stream
bytes directly. If `set_xml_metadata("")` silently failed inside the bare `except` at
line 502-503, the XMP supplier name leak survives but the self-assert never notices.

---

## Warnings

### WR-01: Synthetic-mode `expected_zero_area_count_pre_process` is actually POST-process count

**File:** `scripts/sanitize_fixture.py:678-695`
**Issue:**
In `_run_synthesize_mode`, the manifest field `expected_zero_area_count_pre_process` is
populated from `post_count_final` — a count taken *after* the doc is saved (line 681-683).
For real-supplier mode (line 610) it is populated from `original_zero_area_count` taken
*before* any sanitization. Same field name, two different semantics:

- Real supplier: "how many zero-area fills existed in the supplier PDF before we touched it".
- Synthetic: "how many zero-area fills are in the final committed PDF".

Cross-referencing the JSON sidecars, `mixed-glyph-01.json` (real) has 1742 and the synthetic
manifests have 120 — these are *not* comparable. Any Phase 7 test that consumes the field
expecting "pre-process count" will silently misinterpret synthetic fixtures.

**Fix:**
Either rename the synthetic-mode field (e.g. `expected_zero_area_count`, dropping the
`_pre_process` suffix) and key consumers off the `synthetic` flag, or — cleaner — make
the field always mean "the canonical count the test should assert against, post-build".
For real supplier mode, record `original_zero_area_count` under a separate
`original_supplier_zero_area_count` field. Document the semantics in the manifest schema
section of the script docstring.

### WR-02: q...Q regex splits on `Q` byte inside PDF string literals

**File:** `scripts/sanitize_fixture.py:325-371`, `tests/_illustrator_attack.py:122-135`
**Issue:**
Both `_strip_brand_glyph_block` (sanitize script) and `delete_image_xobjects_intersecting`
(attack helper) use the regex `q\b[^Q]*?Q\b` with `re.DOTALL`. The `[^Q]` character class is
byte-level: any literal capital-Q byte inside a PDF string literal — e.g. `(Quality)Tj`,
`(QC report)Tj`, or even a byte `0x51` inside a binary inline image — will terminate the
non-greedy match early and split the q...Q block at the wrong byte offset.

For the sanitize script (offline, with self-assert backstop), this manifests as either
"surgery missed the brand block" (silent — caller gets `stripped=0` and falls back) or
"surgery stripped too little" (caught by the supplier-name `get_text()` self-assert,
which then triggers the CMap fallback). For the attack helper (regression test
mechanism), this manifests as **inconsistent attack reproduction**: the attack might
"succeed" on supplier A and "fail" on supplier B not because supplier B is safer, but
because supplier B's content stream contains a `Q` byte inside a string literal that
splits the targeted block.

The sanitize script's docstring at line 322-324 candidly acknowledges "若有巢狀 q...Q,
可能漏抓 — 對 CAD title block supplier brand 已 proven 足夠". This is fine for the
sanitize script (offline, has self-assert) but is **not** documented for the attack
helper, which is the canonical regression mechanism Phase 7 will rely on.

**Fix:**
For the attack helper, add an explicit caveat to the module docstring noting the regex
fragility and the implication for future test failures. Long-term (post-v1.1) consider
a proper content-stream tokenizer (pdfminer.six, or a small state machine that respects
PDF string literal `(...)` and hex-string `<...>` boundaries) for the attack path —
sanitize is offline so the heuristic is acceptable, but the regression test mechanism
should be deterministic across all real supplier PDFs the team encounters.

### WR-03: Out-path containment check is case-sensitive substring — bypassable on Windows

**File:** `scripts/sanitize_fixture.py:455-461` (also self-assert at line 590-595)
**Issue:**
`out_str = str(out_path).replace("\\", "/")` then `"tests/fixtures/cad-glyph/" not in out_str`.
This is a **substring** check, not a **prefix** check. Pathological out paths that contain
the substring elsewhere — e.g. `/tmp/tests/fixtures/cad-glyph/decoy/../../../etc/foo.pdf`,
or `C:/Users/scott/tests/fixtures/cad-glyph/lateral/../../../somewhere-else.pdf` — pass the
guard. Also on Windows, `Path` comparison is case-insensitive but substring is
case-sensitive, so `Tests/Fixtures/Cad-Glyph/foo.pdf` bypasses the guard.

Given this is a one-person dev tool with no adversarial caller, the risk is "developer
typo writes to wrong location", not exploitation. But it is one of the four self-assert
gates the README publicly promises (`Section 3` "out path 必在 tests/fixtures/cad-glyph/"),
so it should be tight.

**Fix:**
Use `Path.resolve()` and `is_relative_to()` (Python 3.9+):

```python
FIXTURES_DIR = (Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "cad-glyph").resolve()
if not out_path.resolve().is_relative_to(FIXTURES_DIR):
    print(f"錯誤:--out 必須在 {FIXTURES_DIR} 底下;收到 {out_path.resolve()}", file=sys.stderr)
    return 1
```

This also makes the self-assert at line 590-595 actually different from the entry-point
check (currently they are bit-identical and the "redundancy is safety" comment hides the
fact that they share the bug).

### WR-04: `_strip_brand_glyph_block` coordinate-based hit test only checks `m`/`l` operands

**File:** `scripts/sanitize_fixture.py:330-352`
**Issue:**
The `coord_re` regex only matches `m` (moveto) and `l` (lineto). CAD-glyph supplier PDFs
also commonly emit `c` (curveto with 6 operands), `v` (curveto, 4 ops), `y` (curveto, 4
ops), `re` (rectangle, 4 ops), and `cm` (transformation matrix, 6 ops) — the last of
which is interesting because the *transformation matrix* often moves the path origin
into the target region, but the subsequent `m`/`l` ops are written in the *post-transform
local* coordinate space, not the page-coordinate space the regex assumes.

Concretely: a brand-glyph block that starts with `1 0 0 1 700 490 cm 0 0 m 10 0 l ...`
draws at page-coordinate (700, 490) but the regex sees `0 0 m`, `10 0 l`, `etc.` — none
fall inside `union_bbox=(602,481,827,511)`. The block is NOT stripped, the script
falls back to the CMap supplier-name pass at line 554, which is a *string* find-replace
that does not touch glyph geometry. The visual brand survives, and `get_text()`
self-assert only catches the case where the supplier name is a *decodable* text run.

The 2026-05-28 forensic evidence on `3013A-13A-C6-XX-3D02-A01-00040.pdf` apparently
worked, but that is N=1. For the two synthetic fixtures this code path doesn't run
(synthesize mode skips Step 3), so the bug is dormant — but the moment a new real
supplier PDF arrives via the engineer-delayed-delivery contingency (per the README's
PROVISIONAL banner), this will surface.

**Fix:**
Two options:
1. Track the cumulative `cm` transformation matrix while scanning the q...Q block,
   apply it to operand coordinates before the bbox test. Standard PDF interpreter
   work — about 30 lines of code.
2. Punt the coordinate match entirely and just strip any q...Q block whose nominal
   bbox (computed via fitz's drawings API which already handles `cm`) intersects
   `union_bbox`. This is what `page.get_drawings()` at line 236 already does for the
   union-bbox computation — re-use that data instead of re-parsing the content stream.

Option 2 is preferable: it avoids hand-rolling PDF interpreter logic, and it aligns
the strip step with the same source-of-truth that produced the bbox in Step 2.

### WR-05: `_inject_testco_zero_area_wordmark` n_target=1 case produces a single zero-area fill in a degenerate anchor

**File:** `scripts/sanitize_fixture.py:283-295`
**Issue:**
When `n_target=1`, `span/max(n_target, 1) = span`, the loop runs once with `i=0`, `x=x_start`,
producing a single `fitz.Rect(x_start, y_top, x_start, y_bot)` (zero-width, OK). But if
the original supplier had `original_zero_area_count = 1` (edge case), the self-assert
threshold becomes `0.9 * 1 = 0.9`, and `post_zero_area_count >= 0.9` requires
`post_zero_area_count >= 1`. Combined with `n_target = max(int(1 * 0.95), 1) = max(0, 1) = 1`
at line 534, it works — but only barely. If the supplier had 2 fills,
`int(2 * 0.95) = int(1.9) = 1`, threshold `0.9 * 2 = 1.8`, post_count would need to be `>= 1.8`
i.e. `>= 2`, but only 1 is committed → self-assert fails.

The threshold/target arithmetic is mis-aligned for very small `original_zero_area_count`
values. For `original_zero_area_count` in [2, 10], `int(original * 0.95)` underestimates
the threshold of `0.9 * original` by 1 fill, causing reproducible self-assert failures
on small-count fixtures.

**Fix:**
Use `math.ceil` on the target so the injection matches or exceeds the threshold:

```python
import math
n_target = max(math.ceil(original_zero_area_count * 0.95), 1)
```

Or, more conservatively, target `original_zero_area_count` exactly (no 5% haircut) —
the 0.95 multiplier appears to be a "leave some margin under 1.0" heuristic but with
floor-rounding it overshoots the margin and creates a real bug.

### WR-06: Bare `except Exception` swallows real errors in XMP clear path

**File:** `scripts/sanitize_fixture.py:500-503` (also `:644-647`)
**Issue:**
```python
try:
    doc.set_xml_metadata("")
except Exception as e:  # noqa: BLE001 — 某些 PDF 無 XMP stream
    print(f"  (XMP set_xml_metadata 警告 — 視為無 XMP:{e})")
```

The comment says "某些 PDF 無 XMP stream" — but `set_xml_metadata("")` on a PDF with no
XMP is documented to be a no-op (PyMuPDF source), not to raise. The exceptions this
clause actually swallows in practice are:
- `RuntimeError` for malformed XMP streams (real leak risk — the supplier IP is in
  there, you just can't write to it).
- `MemoryError` / `OSError` for corrupt PDFs (script should abort, not continue).
- `AttributeError` if a future PyMuPDF version renames the method.

Combined with CR-01 (the metadata self-assert can't see XMP residue), an XMP clear
failure silently leaks supplier IP into the committed fixture.

**Fix:**
Catch only the specific exception PyMuPDF actually raises (test empirically; likely
`RuntimeError`), and on catch, **fail** rather than warn — the whole point of the
sanitize script is "we proved this is safe". The synthetic path at line 644-647 has
the same issue.

```python
try:
    doc.set_xml_metadata("")
except (RuntimeError, AttributeError) as e:
    # If we couldn't clear XMP, we cannot prove the fixture is safe — abort.
    print(f"錯誤:無法清空 XMP metadata({e!r})— 視為脫敏失敗", file=sys.stderr)
    return 1
```

### WR-07: `delete_image_xobjects_intersecting` deletes resource references via *unbounded* bare-Do fallback regex

**File:** `tests/_illustrator_attack.py:131-135`
**Issue:**
The bare-fallback regex `/<name>\s+Do\b` matches **all** occurrences of `/<name> Do`
anywhere in the content stream, including ones outside any q...Q wrap and including
matches that happen by string coincidence in unrelated resource names. PDF resource
names are short tokens like `/Im0`, `/Im1` — `re.escape("Im1")` then matched as
`/Im1\s+Do\b` will also match `/Im10`, `/Im11`, `/Im12` etc. because `\s+` doesn't
require a word boundary on the left side of the digit (wait — actually `/Im1\s+Do` does
NOT match `/Im10\s+Do` because `0` doesn't match `\s`, so this is fine for `Im1` vs
`Im10`).

The actual collision risk is on the right side: `/Im1 Do` followed by another `/Im1 Do`
in the same stream — both are correctly matched and removed; that is the intended
behavior. But `re.escape(name.lstrip("/"))` strips one leading `/` then prepends one
back — if the name comes with two slashes (defensive scenario, PDF parser bug), the
regex pattern becomes `//<name>\s+Do\b` which won't match anything. The verbatim
docstring tag suggests this is intentional fidelity to the 2026-05-28 scratch, but
worth a check.

More importantly, the *attack helper returns `len(xrefs)` not the actual number of
content-stream substitutions made*. If the regex fails to substitute for any reason
(unusual whitespace, the name was already wrapped in `BT...ET`), `n_deleted >= 1` at
line 155 of `test_illustrator_attack_regression.py` passes, but the attack didn't
actually happen — the test then proceeds, the white-pct assertion fails for the wrong
reason, xfail strict catches it, all looks normal. But the Phase 7 implementer who
removes the marker post-Option-B will see a "false PASS" because the attack never
happened in the first place.

**Fix:**
Track the actual substitution count from `pattern.subn(...)` returns (currently
discarded with `_n` at lines 128 and 134) and return the **smaller** of "xrefs found"
and "substitutions made" — or, better, return both and let the caller assert
correctness. This costs ~5 lines and tightens the regression signal materially.

```python
total_subs = 0
for name in names:
    pattern = re.compile(...)
    stream_text, n = pattern.subn("", stream_text)
    total_subs += n
# ... bare fallback also tracked ...
if total_subs == 0:
    return 0  # we found xrefs but couldn't delete from stream — attack didn't fire
return len(xrefs)
```

---

## Info

### IN-01: `_short_git_sha` swallows `FileNotFoundError` silently

**File:** `scripts/sanitize_fixture.py:183-193`
**Issue:** If `git` is not on PATH (e.g. CI container without git), the function returns
`"unknown"` silently. This is reasonable behavior but the resulting manifest field
`sanitization_script_commit_sha: "unknown"` will be confusing in audit if it occurs.
**Fix:** Log a stderr warning when fallback fires (single line, doesn't change exit code):
```python
except FileNotFoundError:
    print("警告:git 不在 PATH,manifest commit_sha 會記為 'unknown'", file=sys.stderr)
    return "unknown"
```

### IN-02: `original_supplier_name_sha256` only stores 16 hex chars (64 bits)

**File:** `scripts/sanitize_fixture.py:425-427`
**Issue:** The field name says `sha256` but only `[:16]` of the digest is stored. 64-bit
truncation is fine for "this is a salted opaque ID" purposes (the field's actual job is
non-collision audit, not cryptographic), but the naming is misleading — readers will
expect 64-hex-chars after the `sha256:` prefix.
**Fix:** Either store the full digest (`hexdigest()`) or rename the field to
`original_supplier_name_sha256_prefix16` for honesty.

### IN-03: Decorator order docstring comment in regression test is helpful but inverted relative to Python semantics

**File:** `tests/test_illustrator_attack_regression.py:66-72`
**Issue:** The comment at line 66 says "Python 由下而上應用" (applied bottom-up), then at
line 67 says `parametrize 在外層` (outer layer). Bottom-up application means the
**bottom** decorator (`xfail` at line 74) is applied **first**, then `parametrize` at
line 73 wraps the xfail-wrapped function — so `parametrize` is the **outermost**
decorator in the resulting call chain, but it is also the **first listed in source**.
The wording "在外層" (outer layer) is correct in semantic effect but confusing because
"外層" naturally reads as "wraps the inner", which is what happens at runtime.

The crucial invariant — "parametrize must appear ABOVE xfail in source" — is correctly
enforced by line 73 sitting above line 74. The comment just explains *why* in a
roundabout way.
**Fix:** Trim the explanation:

```python
# Decorator order (must stay this way per 06-PATTERNS Risk Callout #3):
#   parametrize ABOVE xfail in source ⇒ each parametrized case carries its own
#   xfail marker. Reverse this and pytest may collect only 1 xfail item instead of 3.
```

### IN-04: `mixed-glyph-01.json` `created_at_iso` predates the listed git sha

**File:** `tests/fixtures/cad-glyph/mixed-glyph-01.json:19`
**Issue:** `created_at_iso: 2026-05-27T18:51:10.682191+00:00` but `sanitization_script_commit_sha: d671548`. Per `git log`, commit `d671548` is the listed
sha for this plan task. The text-glyph and figure-glyph timestamps are similar (`2026-05-27T18:51:28`).
This is a chicken-and-egg issue: the manifest is written when the script runs, but the
commit sha is read from `git rev-parse HEAD` which is the commit *before* the manifest
is added (since the manifest is part of the same commit). Inconsequential for v1.1 —
just be aware.
**Fix:** None required; consider documenting in the script docstring that
`sanitization_script_commit_sha` is the parent-of-fixture commit (the script version
that produced it), not the commit that contains the fixture.

### IN-05: `.gitignore` `*-supplier-raw.pdf` future-proof pattern is not root-anchored

**File:** `.gitignore:71-72`
**Issue:** The three guards added explicitly for Phase 6 are root-anchored
(`/3013A-...`, `/samples/...`, `/.planning/debug/scratch/illustrator-attack-...`).
The convention pattern at line 72 `*-supplier-raw.pdf` is **not** anchored — it matches
recursively, including inside `tests/fixtures/cad-glyph/` (which is the documented
allowed-binary location).

Today this is harmless because no `*-supplier-raw.pdf`-named files exist anywhere. If
the team later names a sanitized test fixture `something-supplier-raw-redacted.pdf`
(unlikely but possible), the pattern would block it. The intent — "anything explicitly
named *-supplier-raw is raw" — is clear; the implementation is just slightly looser
than the surrounding patterns.
**Fix (optional):** Either root-anchor it (`/*-supplier-raw.pdf`) to match the surrounding
style, or document that this pattern is intentionally recursive in the comment block at
line 58-62.

---

_Reviewed: 2026-05-28T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---

## Fix Application

**Fixed at:** 2026-05-28
**Fixer:** Claude (gsd-code-fixer)
**Worktree branch:** `gsd-reviewfix/06-114654`(fast-forward 至 master)
**Scope:** Critical + Warning(default `--fix` mode);Info findings 不在 scope。

### Baseline preservation

- ✓ pytest baseline `301 passed, 3 skipped, 3 xfailed` 保留(規定不能變)
- ✓ AGPL guard test `test_fitz_import_confined_to_engine_seam` 綠燈
- ✓ `app/**/*.py` production code 0 改動(`git diff --stat master app/` 為空)
- ✓ `import fitz` 仍只出現於 `app/services/pdf_engine.py`(seam intact)

### Fixed Issues

| ID | Title | Commit | Files Modified |
|---|---|---|---|
| CR-01 | `_metadata_all_empty` uses wrong key names — self-assert is a no-op | `d0370de` | `scripts/sanitize_fixture.py` |
| WR-01 | Synthetic-mode `expected_zero_area_count_pre_process` is actually POST-process count | `5b2efaf` | `scripts/sanitize_fixture.py` |
| WR-02 | q...Q regex splits on `Q` byte inside PDF string literals | `179f05f` | `tests/_illustrator_attack.py` |
| WR-03 | Out-path containment check is case-sensitive substring — bypassable on Windows | `509cef7` | `scripts/sanitize_fixture.py` |
| WR-04 | `_strip_brand_glyph_block` coordinate-based hit test only checks `m`/`l` operands | `5be5ef9` | `scripts/sanitize_fixture.py` |
| WR-05 | `_inject_testco_zero_area_wordmark` n_target rounding mis-aligns with 0.9× threshold | `dca2ec4` | `scripts/sanitize_fixture.py` |
| WR-06 | Bare `except Exception` swallows real errors in XMP clear path | `e3ac65f` | `scripts/sanitize_fixture.py` |
| WR-07 | `delete_image_xobjects_intersecting` returns intent count, not actual substitution count | `7514ef1` | `tests/_illustrator_attack.py` |

### Fix Strategy Notes

- **CR-01:** allowlist-style — iterate `doc.metadata.items()`, skip computed fields `{format, encryption}`, fail on any non-empty key. 任何 supplier 帶 hardcoded 9-key 之外的 `/Info` key 都會被攔下。
- **WR-01:** additive — 保留 LEGACY 欄位(已 commit 的 manifest 不破壞),新增 `original_supplier_zero_area_count` 與 `expected_zero_area_count_post_build` 兩個明確語義欄位;docstring + manifest 模組 docstring 雙文件化。**現有 fixture JSON 不自動 regenerate** — 下次跑 `scripts/sanitize_fixture.py` 時新欄位才會寫入。
- **WR-02:** docstring-only — module docstring 加長段 caveat 解釋 regex 對 PDF string literal Q-byte 脆弱、對 Phase 7 implementer 的影響、長期改用 tokenizer 的建議。Cross-reference WR-04(共享同 regex)+ WR-07(實際 subn count 讓 regex miss case surface)。
- **WR-03:** 引入 `FIXTURES_DIR` 常數 + `_out_path_in_fixtures_dir` helper(Path.resolve + is_relative_to)。empirical verification 確認 legit/traversal/decoy 三 case 行為正確。
- **WR-04:** docstring + inline LIMITATION comment + TODO。Option 2 重寫預估 30-50 行 + 需 multi-fixture 驗證,超出 Phase 6 minimum-change 教訓 → 留 Phase 7+。
- **WR-05:** **logic-affecting fix** — empirical verification 顯示舊 floor 行為對 original ∈ {2, 3, 5} 必 fail self-assert,新 ceil 行為三 case 全 pass、original=1742 也 pass(no regression)。
- **WR-06:** 從 `except Exception` 收緊到 `except (RuntimeError, AttributeError)`,且 fail-loud(`return 1`)而非 warn。real-mode + synthetic-mode 同步修復。
- **WR-07:** track `total_subs`(主 regex + bare fallback 兩條 `subn` count 總和)。若 `xrefs` 非空但 `total_subs == 0` → 回傳 0,讓 caller 的 `assert n_deleted >= 1` 誠實 surface 「attack precondition 不成立」。

### Deferred Issues (Info)

5 個 Info findings 不在 default `--fix` scope:

- **IN-01:** `_short_git_sha` swallows `FileNotFoundError` — 補 stderr warning(cosmetic)
- **IN-02:** `original_supplier_name_sha256` 只存 16 hex 字元(命名 misleading)
- **IN-03:** decorator order docstring 解釋繞口
- **IN-04:** `mixed-glyph-01.json` `created_at_iso` 預先於 listed git sha(chicken-and-egg artefact)
- **IN-05:** `.gitignore` `*-supplier-raw.pdf` 非 root-anchored

Phase 6 close 不修;若 Phase 7+ 修 sanitize script 時順手帶可,但不強迫。

### Logic Bug Disclosure(per fixer protocol)

- **WR-05** 是 logic-affecting fix(改 floor → ceil)。已透過 standalone Python 腳本 empirical verification 三組 cases(orig ∈ {2, 3, 5} fail→pass,orig=1742 pass→pass)。但 sanitize script 本身在 phase close 時的執行尚需 Phase 7 implementer 跑「實際 supplier PDF + small-count brand glyph」case 驗證 — 雖然 verification 數學正確,**建議 developer 在 commit 進 master 前親自 cross-check** 此修復對既有 fixtures 的影響(本 worktree 沒重跑 sanitize regenerate manifest,避免 churn 既有 committed JSON)。

---

_Fixed: 2026-05-28T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Commits: d0370de → e3ac65f(8 atomic commits on `gsd-reviewfix/06-114654`)_

---

## Post-review maintenance addendum(2026-05-28)

**範圍外 maintenance commit(不屬於本 review/fix 的 scope):**

Post-review 同日,sanitize_fixture.py 補強了兩個新 fallback function(commit `0045c6b`):
- `_redact_supplier_name_glyph()` — glyph-level redaction for CMap-encoded fonts(Impl note C)
- `_delete_supplier_annotations()` — Form-XObject stamp annotation 整塊刪除(Impl note D)

**為什麼不在本 review/fix scope:**

1. 這兩個 fallback 的觸發點是「sanitize_fixture.py 處理工程師後續交付的 supplier PDF 時遇到 CMap-encoded font + Form-XObject stamp annotation」,**不是 review-time 已知問題**
2. 觸發場景需要 real supplier PDF 才能 surface(synthetic PDFs 不會走到這條 path)
3. 兩個新 function 沒有改既有 fallback chain 的 A/B 行為,只是擴充 C/D
4. 上線同日 maintenance 加 + 對應的 fixture 升級已分別 atomic commit(`0045c6b` + `f7f34e8`),git history 清楚

**建議:** 下次 `/gsd-code-review 6 --fix` re-run 時,新增的兩個 function 自動進入掃描 scope。若有額外的安全 / 邏輯問題會被抓出。本 maintenance round 不主動重跑 review(per 5330290 教訓 — minimum-change,加 polish 留下個 sprint)。

**Phase 6 截至 2026-05-28 close 時的 review/fix 狀態:**
- 本 review 識別的 1 Critical + 7 Warnings:**全部 fixed**
- 5 Info:**deferred**(不在 default `--fix` scope)
- Phase 6 close 後 maintenance:`sanitize_fixture.py` Impl C + D 補強 + 3/3 fixture real upgrade — **無 reviewed-but-unfixed findings**

*Addendum recorded: 2026-05-28(post-review maintenance round)*
