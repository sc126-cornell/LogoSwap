---
phase: 03-logo-placement
reviewed: 2026-05-22T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - app/api/logos.py
  - app/api/process.py
  - app/config.py
  - app/main.py
  - app/models.py
  - app/services/logo.py
  - app/services/pdf_engine.py
  - app/services/pipeline.py
  - tests/conftest.py
  - tests/test_logo.py
  - tests/test_process_api.py
  - web/index.html
  - web/js/api.js
  - web/js/app.js
  - web/js/logos.js
  - web/js/regions.js
  - web/styles/app.css
  - web/styles/tokens.css
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-05-22
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 3 adds the logo-library service, the `logo_id` path-traversal defense, the
`place_logo` insert-image seam, the `JobSpec.logo_id` field, and the frontend logo
picker. The phase's headline security and architecture goals are met and verifiable:

- **Path-traversal defense (T-03-01):** sound. `logo_id` is only ever a `dict.get`
  key into the parsed manifest (`logo.py:150`) — never joined to a path. The admin
  `file` basename is joined and re-checked with `is_relative_to(LOGOS_DIR)`
  (`_resolve_path`, lines 75–86). An unknown/crafted id is a structured 404 with no
  oracle, exercised by `test_logo_id_path_traversal_rejected`.
- **AGPL isolation:** `place_logo` correctly lives in `pdf_engine.py` (the sole `fitz`
  importer); `logo.py` imports only PIL/json/pathlib. Boundary intact.
- **Redaction ordering (Pitfall 1):** `place_logo` is called strictly AFTER
  `redact.remove_region` (which runs `apply_redactions`) — `pipeline.py:186` then 193.
  Verified by `test_logo_survives_redaction`.
- **Deferred mutation (D-05):** the work copy is reset from the chmod-0o444 original on
  every run; a path-equality guard aborts if work == original; the original's SHA-256 is
  asserted unchanged across a remove+insert run. Sound.
- **XSS:** the picker builds DOM with `createElement` + `textContent` only; no
  `innerHTML` anywhere in the new JS. Confirmed.

No blockers. Findings below are robustness/quality issues, the most material being a
stale-after-image caching bug (WR-01) and a logo-decode failure that aborts an entire
otherwise-successful redaction job (WR-02).

## Warnings

### WR-01: Result after-image is cached, so a re-apply can show a stale "移除結果"

**File:** `web/js/regions.js:573`, `web/js/regions.js:684`; `web/js/viewer.js:343`; `web/js/api.js:164`
**Issue:** `resultImageURL(id, n)` returns a fixed URL with no cache-busting token.
After a first apply, the browser caches `/sessions/{id}/result/pages/{n}/image`. On a
second apply (the "重新套用" flow) the work copy on disk is freshly re-redacted with a
different region set, but `showResultImage` sets the same `pageImage.src` string. The
browser may serve the cached PNG from the first apply, showing the user a stale
after-image that does not match the new result they are about to download. The download
itself is correct (different endpoint, attachment), so the preview silently disagrees
with the file — a correctness/trust defect for the core before/after comparison.
**Fix:** append a cache-busting query param keyed to the apply, e.g.
```js
// regions.js: bump a token on each successful apply
let resultVersion = 0;
// ...in applyRemoval() success branch: resultVersion++;
// api.js
export function resultImageURL(id, n, v) {
  let u = API_BASE + "/sessions/" + encodeURIComponent(id) +
          "/result/pages/" + encodeURIComponent(n) + "/image";
  if (v !== undefined) u += "?v=" + encodeURIComponent(v);
  return u;
}
```
Pass `resultVersion` at both call sites (`setViewMode` line 573 and `onPageChanged`
line 684).

### WR-02: A corrupt/oversized library asset turns a valid job into a hard failure

**File:** `app/services/pipeline.py:147-151`, `app/services/logo.py:142-160`
**Issue:** `logo.resolve(job_spec.logo_id)` is called for the global logo and, on a
decode/size failure, raises `LogoError("logo_unreadable"/"logo_invalid")` which maps to
422 in `main.py`. The picker only ever surfaces ids from `list_logos`, which already
SKIPS unreadable assets — so an id present in the picker is one that passed validation
at list time. But the asset can be replaced/corrupted on disk between the list call and
the process call (or `MAX_LOGO_BYTES` lowered via env), and then a legitimate, fully
specified removal job is aborted with NO redaction and NO export produced — the user
loses the whole run because of a logo-library problem unrelated to their framing. The
"degrade gracefully to pure removal" philosophy stated for the catalog (A2) is not
applied on the placement path.
**Fix:** decide the intended contract. If placement is best-effort, catch `LogoError`
from `resolve` in `process_job`, proceed with pure removal, and report a per-job warning
flag (e.g. `"logo_skipped": true`) the frontend surfaces. If placement is mandatory when
requested, keep the 422 but document it and ensure the frontend maps `logo_unreadable` /
`logo_invalid` to specific copy — currently `mapErrorCopy` (regions.js:583) falls through
to the generic `removalFailed` for these codes, so the user gets no actionable message.

### WR-03: `mapErrorCopy` does not handle the new logo error codes

**File:** `web/js/regions.js:583-595`
**Issue:** Phase 3 introduces `logo_not_found`, `logo_invalid`, and `logo_unreadable`
as possible `/process` error codes (a bad `logo_id` reaches `logo.resolve` inside the
pipeline). `mapErrorCopy` switches only on `residual_content`, `page_out_of_range`,
`invalid_request`, `result_not_ready`, and otherwise returns `COPY.removalFailed`. So a
logo-specific failure is reported as "套用移除時發生問題" with no hint that the logo (not
the framing) is the cause — the user may repeatedly retry the same doomed selection.
**Fix:** add cases mapping the three logo codes to dedicated 繁中 copy, e.g. "所選商標已
無法使用,請改選其他商標或先不置入商標。" Keep them distinct from the framing-failure copy.

### WR-04: `_validate_png` accepts any Pillow-decodable format, not only PNG

**File:** `app/services/logo.py:89-106`, `app/api/logos.py:54`
**Issue:** The function is named `_validate_png` and the image endpoint serves the bytes
with a hardcoded `media_type="image/png"`, but `Image.open(...).verify()` accepts JPEG,
GIF, TIFF, BMP, etc. A manifest entry whose `file` is a `.jpg` that decodes fine passes
validation, is listed, and is then served to the browser labelled `image/png`. The
thumbnail may still render (browsers sniff), but the Content-Type is a lie and a
non-PNG could be embedded by `place_logo` via `stream=` with the wrong assumptions. The
manifest is admin-controlled so this is not a user-facing exploit, but it is a silent
format mismatch the name and the endpoint both promise against.
**Fix:** assert the decoded format is PNG, e.g.
```python
with Image.open(path) as img:
    if img.format != "PNG":
        raise LogoError("logo_invalid", "商標檔案必須為 PNG 格式。")
    img.verify()
```
Note `verify()` invalidates the image object, so check `.format` before calling it
(as above) or re-open. Alternatively, if other formats are intended, rename the function
and set the served media type from the detected format.

## Info

### IN-01: `sessionId` is stored but unused in `logos.js`

**File:** `web/js/logos.js:49,99,154-155,161-162`
**Issue:** `initLogos`/`resetLogos` set and clear `sessionId`, but the module never reads
it (`api.listLogos()` and `api.logoImageURL(id)` take no session). Dead state that
suggests a session-scoped intent the library does not actually have (the library is a
fixed shared asset, per `logos.py` docstring).
**Fix:** drop the `sessionId` variable and the `session_id` destructuring from
`initLogos`, or add a comment explaining the deliberate retention for a future seam.

### IN-02: Logo selection is not reset when the picker re-renders on catalog reload

**File:** `web/js/logos.js:137-151`, `web/js/regions.js:528`
**Issue:** `loadCatalog` (invoked by the retry button, line 174) calls `renderGrid`
without resetting `selectedLogoId`. If a previously selected id is no longer in the
reloaded catalog, `applySelection` simply marks nothing selected, but
`getSelectedLogoId()` still returns the stale id, which then flows into the next
`/process` as `logo_id` and 404s server-side (handled, but avoidable). Minor because the
server rejects it cleanly.
**Fix:** in `renderGrid`, if `selectedLogoId` is not among the rendered ids, clear it and
call `notifyJobInputChanged` / `refreshResultLabel`.

### IN-03: `_logoswap_name` strips control chars but not other header-hostile separators

**File:** `app/services/pipeline.py:63-72`
**Issue:** Defense is solid (Cc category strip + length cap + percent-encoding at the call
site, `process.py:128`), so this is not exploitable. For completeness, characters in
category `Cf` (format controls, e.g. zero-width / bidi overrides) survive the filter and
can produce visually deceptive download filenames. Cosmetic / phishing-adjacent only.
**Fix:** optionally extend the filter to also drop `Cf`, or normalize with
`unicodedata.normalize("NFKC", stem)` before the strip.

### IN-04: `place_logo` ignores the returned xref on the first placement if it is 0

**File:** `app/services/pdf_engine.py:233-258`, `app/services/pipeline.py:194-199`
**Issue:** The dedup logic uses `logo_xref == 0` to mean "not yet embedded." PyMuPDF's
`insert_image` returns the image xref, which is always a positive integer for a real
embed, so this is safe in practice. But the invariant ("0 means unembedded") is implicit;
if a future engine swap ever returned 0 for a valid embed, every region would re-embed.
Worth a one-line assert or comment pinning the assumption.
**Fix:** `assert logo_xref > 0` after the first placement, or document that a 0 return is
treated as "re-embed next time" by contract.

---

_Reviewed: 2026-05-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
