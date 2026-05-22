---
phase: 01-input-preview
reviewed: 2026-05-22T00:00:00Z
depth: standard
files_reviewed: 28
files_reviewed_list:
  - app/__init__.py
  - app/api/__init__.py
  - app/api/pages.py
  - app/api/sessions.py
  - app/config.py
  - app/main.py
  - app/models.py
  - app/services/__init__.py
  - app/services/ingest.py
  - app/services/pdf_engine.py
  - app/services/render.py
  - app/storage.py
  - pytest.ini
  - requirements.txt
  - tests/__init__.py
  - tests/conftest.py
  - tests/test_api.py
  - tests/test_ingest.py
  - tests/test_render.py
  - tests/test_storage.py
  - web/index.html
  - web/js/api.js
  - web/js/app.js
  - web/js/theme.js
  - web/js/viewer.js
  - web/styles/app.css
  - web/styles/tokens.css
findings:
  critical: 1
  warning: 7
  info: 5
  total: 13
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-05-22
**Depth:** standard
**Files Reviewed:** 28 (27 source + this scope)
**Status:** issues_found

## Summary

Phase 1 (input + preview skeleton) is a well-structured slice. The phase's headline security
properties largely hold up under adversarial reading: `fitz` is isolated to `pdf_engine.py`
(confirmed by grep — only one importer), the original is written write-once and chmod'd 0o444,
the client filename never becomes a path component (a server token is used instead), no
frontend code uses `innerHTML`/`document.write` (only mentioned in comments), the theme value is
enum-guarded, and parser failures are funnelled into typed 4xx via global handlers.

However, the trust boundary has a hole the threat model claims is closed: **the `session_id`
URL path parameter is concatenated into a filesystem path with no validation, while the
write-once original-preservation guarantee (UPLOAD-04 / T-01-05) does not actually protect the
work copy a malformed path could reach.** Combined with the fact that path-traversal protection
was only ever tested on `sanitize_filename` (the client filename), not on the route parameter
that actually builds paths, this is the one finding that should block: the threat-model claim
"the client filename is never used as a path" is true, but a *different* untrusted string
(`session_id`) **is** used as a path, and it is unguarded.

Secondary issues: a stale-image async race in the viewer that can show page N's image under
page M's indicator during fast navigation; a fallback in the frontend error mapper that leaks
the raw server message into user copy; and several robustness / contract-fidelity gaps. None of
the secondary items risk data loss, but the viewer race and the error-leak both undermine
stated Phase-1 behaviors.

## Critical Issues

### CR-01: `session_id` path parameter is used to build filesystem paths without validation (path traversal / arbitrary-path access)

**File:** `app/storage.py:37-41` (sink); reached from `app/api/pages.py:43-44`, `app/api/pages.py:74-75`, `app/api/sessions.py:80-86`
**Issue:**
`subdir()` builds `self._data_dir() / kind / session_id` directly from the caller-supplied
`session_id`, and `session_id` originates from the untrusted URL path in every page/session
endpoint. Nothing validates that `session_id` matches the server-issued
`secrets.token_urlsafe` shape before it becomes a path segment:

```python
def subdir(kind: str, session_id: str) -> Path:
    if kind not in _KINDS:
        raise ValueError(f"unknown storage kind: {kind!r}")
    return _data_dir() / kind / session_id   # session_id is untrusted, unchecked
```

The threat model (T-01-04) asserts traversal is mitigated because "the client filename is
never used as a path." That is true — but it is the wrong string. `session_id` is the string
that actually constructs paths, and it is unguarded. `session_exists()` gates reads via
`work_path(session_id).is_file()`, and percent-encoded separators (`%2F`, `%5C`) or dot
segments that survive Starlette's path handling would resolve against `DATA_DIR/work/`.
While the single-segment route converter, the `_KINDS` allowlist, and the fixed
`doc.pdf` / `source.pdf` suffixes substantially narrow what an attacker can name, relying on
those incidental constraints — rather than an explicit allowlist on the identifier that builds
the path — is exactly the gap the phase claims to have closed. On Windows (the documented dev
platform) `..%5C` handling differs from POSIX, widening the blast radius.

This is classified BLOCKER because (a) it is an unvalidated untrusted-input-to-filesystem-path
flow on a no-auth LAN service, (b) the threat model explicitly claims this class is mitigated
when it is not, and (c) there is zero test coverage for the actual sink (see WR-07).

**Fix:** Validate `session_id` against the exact token alphabet before any path use. Centralize
it in `subdir()` so every caller is covered:

```python
import re
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")  # secrets.token_urlsafe alphabet

def subdir(kind: str, session_id: str) -> Path:
    if kind not in _KINDS:
        raise ValueError(f"unknown storage kind: {kind!r}")
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise ValueError(f"invalid session id: {session_id!r}")
    return _data_dir() / kind / session_id
```

Map the resulting `ValueError` (or a typed error) to a 404 in the API layer so a crafted id is
indistinguishable from a missing session. As defense-in-depth, also resolve the final path and
assert it is contained within `DATA_DIR` (`dest.resolve().is_relative_to(DATA_DIR)`).

## Warnings

### WR-01: Stale-image async race in the viewer corrupts the displayed page during fast navigation

**File:** `web/js/viewer.js:120-156`
**Issue:**
`renderPage(index)` is `async` and `await`s `api.pageMeta(...)`, then assigns the shared
singleton `pageImage.onload` / `pageImage.onerror` handlers and `pageImage.src`. Two rapid
calls (double-clicking Next, holding ArrowRight, or jump-then-arrow) interleave: `state.pageIndex`
and the indicator are set synchronously for the *latest* call, but image loads complete out of
order, so a slower earlier page's PNG can finish last and be displayed under a newer page's
indicator. There is no request-generation token to discard stale results. The `onload` closure
also reads `state.renderBox` which a later call may have already overwritten.

**Fix:** Guard with a monotonic token and ignore stale completions:

```js
let renderToken = 0;
async function renderPage(index) {
  if (index < 0 || index >= state.pageCount) return;
  const myToken = ++renderToken;
  state.pageIndex = index;
  updateNavButtons();
  updateIndicator();
  showPageLoader(true);
  try {
    const meta = await api.pageMeta(state.sessionId, index);
    if (myToken !== renderToken) return; // a newer navigation superseded us
    computeRenderBox(meta);
    applyZoom();
  } catch {
    if (myToken !== renderToken) return;
    state.renderBox.cssW = 0; state.renderBox.cssH = 0;
  }
  pageImage.onload = () => { if (myToken !== renderToken) return; /* ...existing... */ };
  pageImage.onerror = () => { if (myToken !== renderToken) return; showPageLoader(false); showPageError(); };
  pageImage.src = api.pageImageURL(state.sessionId, index);
}
```

### WR-02: Frontend error mapper leaks the raw server message into user-facing copy

**File:** `web/js/app.js:71-75` (`extractLimit`), consumed at `web/js/app.js:86`
**Issue:**
`extractLimit` is meant to pull only a numeric limit (e.g. "50 MB") out of the server message so
the fixed copy `檔案超過大小上限({limit})` can interpolate just that token. But the fallback
returns the **entire** server message when the regex does not match:

```js
return m ? m[1].trim() : serverMessage;   // whole raw server string on no-match
```

That raw string is then injected verbatim into the displayed copy. This undercuts the stated
mitigation (T-01-14: "maps the server detail.code to fixed copy ... does not inject raw server
message"). It is written via `textContent` so it is not XSS, but it is an information-leak /
copy-fidelity defect: any server-side wording change (or a future code that reuses
`file_too_large` with a different message) surfaces raw backend text to the user.

**Fix:** Fall back to an empty string (or a fixed placeholder), never the raw message:

```js
return m ? m[1].trim() : "";
```

and have `COPY.fileTooLarge("")` degrade gracefully (e.g. omit the parenthetical when empty).

### WR-03: `get_session` re-opens and parses the work PDF on every lookup, mapping internal failures to a misleading `corrupt_pdf`

**File:** `app/api/sessions.py:86-99`
**Issue:**
`get_session` recovers `page_count` by re-opening and parsing the work copy through the engine on
every call. Two problems: (1) it performs a full parse for a metadata read that already happened
at ingest, an avoidable cost on the hot lookup path; (2) if `pdf_engine.open_pdf` raises
`PdfEngineError` here, the global handler in `main.py:63-70` returns **422 `corrupt_pdf`** for a
session that *exists and already passed ingest validation*. A parse failure at this point is an
internal/storage problem, not a client-supplied corrupt upload, so reporting `corrupt_pdf` (a
client-input code) is misleading and could mask real disk/corruption issues.

**Fix:** Persist `page_count` (and the original filename) in a tiny per-session sidecar at ingest
(e.g. `work/{sid}/meta.json`) and read that in `get_session`, avoiding the re-parse entirely. If
re-parsing is kept for now, catch `PdfEngineError` locally and surface a distinct
internal/`session_unreadable` code rather than the client-facing `corrupt_pdf`.

### WR-04: Upload size guard buffers the entire file in a Python list before joining

**File:** `app/api/sessions.py:49-66`
**Issue:**
The streaming guard correctly stops at `MAX_UPLOAD_BYTES` (good — T-01-01), but it accumulates
every 1 MB chunk into `chunks: list[bytes]` and then `b"".join(chunks)`, transiently holding
~2x the file size in memory (the list of chunks plus the joined `bytes`) for an accepted upload.
At the 50 MB cap with multiple concurrent uploads on the documented 2–4 worker deployment, this
is a real (if bounded) memory amplification. It also re-buffers immediately again inside ingest →
storage writes.

**Fix:** Stream to a `tempfile.SpooledTemporaryFile` (or `bytearray` with `extend`, then a single
`bytes(buf)`), or better, write directly to the work/original paths while hashing/counting, so the
full payload is not held twice in the heap. At minimum use a single `bytearray` accumulator
instead of `list[bytes]` + `join`.

### WR-05: PDF content sniff can be fooled by `%PDF-` appearing anywhere in the first 1 KB

**File:** `app/services/ingest.py:39-42`
**Issue:**
`_looks_like_pdf` returns true if `b"%PDF-"` appears **anywhere** within the first 1024 bytes
(`_PDF_MAGIC in head`), not at/near the start. A non-PDF payload that merely contains the bytes
`%PDF-` in its first kilobyte (e.g. a polyglot, or an unrelated binary) passes the type sniff and
proceeds to the parser. The real parse step (`open_pdf`) is the backstop, so this is not by itself
exploitable, but the sniff is weaker than the docstring implies ("Real PDFs start with %PDF-").

**Fix:** Anchor the check to the documented small leading window — PDFs allow a few junk bytes
before the header, so scan only the first ~8 bytes (or `head.lstrip()[:5] == _PDF_MAGIC`) rather
than the whole 1 KB:

```python
return data[:1024].find(_PDF_MAGIC) != -1 and data[:1024].find(_PDF_MAGIC) <= 8
```

or simply `return _PDF_MAGIC in data[:8]`.

### WR-06: `fitz.open` is called without a render/parse resource cap; only page-count and DPI are bounded

**File:** `app/services/pdf_engine.py:30-42, 50-65`; budget intent stated in `app/services/render.py:7-10`
**Issue:**
The phase's pixel-budget guard is the DPI clamp, and page count is capped at ingest — both good.
But a single page can still declare an enormous MediaBox (page rect in points). `get_pixmap(dpi=dpi)`
allocates `~(w_pt*dpi/72) x (h_pt*dpi/72) x 4` bytes; with `dpi` clamped to 300 a pathological
multi-thousand-point page still yields a multi-hundred-megabyte pixmap. The "multi-gigabyte pixmap"
the comment says is prevented is mitigated for *normal* page sizes but not for an adversarial
oversized single page (within the 50 MB / 30-page envelope). The plan defers "large-page DPI caps"
to Phase 5, so this is a known gap — flagging it because the in-code comments
(`render.py:7-10`, `pdf_engine` docstring) overstate the current protection.

**Fix:** Add a pixel-count ceiling alongside the DPI clamp: compute
`px = round(w_pt*dpi/72) * round(h_pt*dpi/72)` and, if it exceeds a budget (e.g. 40 MP), reduce the
effective DPI to fit or raise a typed error. At minimum, soften the comments to state large-page
capping is deferred (Phase 5) so the documentation does not claim a guarantee the code lacks.

### WR-07: No test exercises path-traversal on the route that actually builds paths

**File:** `tests/test_storage.py:45-64`, `tests/test_api.py` (absent coverage)
**Issue:**
`test_sanitize_filename_strips_separators_and_dotdot` thoroughly tests `sanitize_filename`, but
that function is only applied to the *display* filename (`ingest.py:96`), which never becomes a
path. The string that *does* build paths — `session_id` — has **no** traversal test at the
storage or API layer (e.g. `GET /sessions/..%2F..%2Fwork/.../image`). This is why CR-01 went
unnoticed: the test suite validates the safe input and ignores the dangerous one.

**Fix:** Add API-level tests that a crafted `session_id` (encoded separators, dot segments,
absolute-style paths) returns 404 and never reads outside `DATA_DIR`, plus a storage-level test
that `subdir("work", "../escape")` raises (after the CR-01 fix).

## Info

### IN-01: `sanitize_filename` mangles legitimate filenames and is order-fragile

**File:** `app/storage.py:66-71`
**Issue:** `candidate.replace("..", "")` runs unconditionally and globally, so a legitimate name
like `revision..final.pdf` becomes `revisionfinal.pdf`, and `my..pdf` loses characters. Because the
result is display-only this is cosmetic, but it silently corrupts user-facing filenames. The `..`
strip also runs *after* `os.path.basename`, so it is redundant for traversal (basename already
removed directories) and only harms legitimate names.
**Fix:** Reject names that *are* exactly `.`/`..` (already done) but stop globally deleting the
`..` substring; if extra safety is wanted, collapse runs of dots only at the path-segment level.

### IN-02: `pdf_engine.page_dimensions` / `render_page_to_png` index `doc[page_no]` with no bounds guard of their own

**File:** `app/services/pdf_engine.py:64, 84`
**Issue:** Both functions do `doc[page_no]` and rely entirely on the caller (`render._validate_page_no`)
to bounds-check first. That contract holds today, but a future caller that forgets validation gets a
raw PyMuPDF `IndexError` escaping as a 500. The docstring acknowledges this ("page_no is validated by
the caller"). Low risk while the only callers validate.
**Fix:** Either bounds-check inside the engine and raise `PdfEngineError`, or leave as-is but keep the
validation contract enforced by tests.

### IN-03: `health` endpoint declares `-> dict` and is shadowed by the catch-all static mount ordering

**File:** `app/main.py:73-83`
**Issue:** `app.mount("/", StaticFiles(..., html=True))` is registered after the routers, which is
correct, but mounting at `/` with `html=True` is a broad catch-all; any future top-level route added
*after* the mount would be shadowed. Also `health()` is annotated `-> dict` (untyped) rather than a
model — fine for a liveness probe but inconsistent with the typed-contract style used elsewhere.
**Fix:** Keep the mount last (as now); consider mounting the SPA under a sub-path or using an explicit
catch-all route to avoid accidental shadowing as the API grows.

### IN-04: Duplicated ingest-code→HTTP-status table in two modules can drift

**File:** `app/api/sessions.py:21-27` and `app/main.py:36-42`
**Issue:** The `_CODE_STATUS` / `_INGEST_STATUS` maps are identical copies. The code comment in
`main.py` even says "mirrors api/sessions.py table." Two sources of truth for the same mapping invite
drift (e.g. adding a new ingest code in one place only).
**Fix:** Define the mapping once (e.g. in `app/services/ingest.py` next to `IngestError`, or in
`config.py`) and import it in both the router and the exception handler.

### IN-05: `jumpTo` parses with `parseInt` and silently accepts trailing garbage

**File:** `web/js/viewer.js:177-182`
**Issue:** `parseInt("3abc", 10)` returns `3`, so `頁碼` input like `3x` jumps to page 3 rather than
rejecting. The clamp keeps it in range so there is no out-of-bounds risk (and the backend 404s
anyway), but the lenient parse is mildly surprising. Cosmetic.
**Fix:** Use `Number(value)` with `Number.isInteger` validation, or strip non-digits before parsing,
if strict input is desired.

---

## Resolution (2026-05-22)

All Critical + all Warning findings fixed; each committed atomically on `master`. Full
suite: **87 passed** (was 35; +52 tests proving the fixes). Info findings (IN-01..05) were
intentionally left per scope.

| Finding | Status | Commit | Notes |
|---|---|---|---|
| CR-01 | Fixed | `5890a31` | `session_id` allowlist (`^[A-Za-z0-9_-]{16,64}$`) enforced in `subdir()` + DATA_DIR containment; typed `InvalidSessionId` -> 404 (handler + `session_exists` swallow). |
| WR-07 | Fixed | `5890a31` | Storage-layer allowlist tests + route-level traversal tests (single-segment ids reach the sink and 404; encoded separators never leak/500; handler-level raw-payload probe). Committed with CR-01 as one security change (the test is CR-01's proof). |
| WR-01 | Fixed | `0136474` | Monotonic `renderToken` in `viewer.js`; stale `/meta`, `onload`, `onerror` continuations bail out. |
| WR-02 | Fixed | `b5b52c4` | `extractLimit` falls back to `""` (never the raw server message); `COPY.fileTooLarge("")` omits the parenthetical. |
| WR-03 | Fixed | `a0dae28` | Per-session `work/{sid}/meta.json` sidecar written at ingest, read on lookup (no re-parse); fallback re-parse failure surfaces `session_unreadable` (500), not `corrupt_pdf`. |
| WR-04 | Fixed | `7d04b05` | Upload accumulates into a single `bytearray` (extend) + one `bytes()`, not `list[bytes]` + `join`; boundary preserved (test added). |
| WR-05 | Fixed | `6bd0913` | PDF sniff anchored to offset <= 8 (BOM-tolerant), not "anywhere in first 1 KB". |
| WR-06 | Fixed | `7a0cb28` | `MAX_RENDER_PIXELS` (40 MP) ceiling; effective DPI scaled down by `sqrt(budget/projected)` for oversized pages, applied in both `render_page` and `page_meta`. |

No finding was judged a non-issue. WR-03's fallback uses HTTP 500 deliberately (an existing
session that cannot be read is an internal/storage problem, not a client `corrupt_pdf`).

---

_Reviewed: 2026-05-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Fixes applied: 2026-05-22 (Claude, gsd-code-fixer)_
