# Phase 3: 商標置入 (Logo Placement) - Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 13 (4 new, 9 modified) + 1 new asset dir
**Analogs found:** 13 / 13 (every file has a strong in-repo analog)

> Phase 3 is an **additive layer on a proven Phase-1/2 spine**. There is essentially zero net-new
> infrastructure: every sub-problem maps to an existing service-module shape, an existing router
> shape, an existing Pydantic field/validator, an existing frontend module + the single `api.js`
> seam, or an existing test pattern. Copy the analogs below verbatim and change the nouns.

---

## File Classification

| New/Modified File | New? | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|------|-----------|----------------|---------------|
| `app/services/logo.py` | NEW | service (fitz-free) | file-I/O + transform (load manifest, validate PNG, id→bytes) | `app/services/render.py` (module shape, typed `*Error`, `config` read) + `app/storage.py` (allowlist + containment) | exact (composite) |
| `app/services/pdf_engine.py` | MOD | service (fitz seam) | transform (insert image into rect) | existing `add_redact_annot` / `save_doc` wrappers in the SAME file | exact |
| `app/services/pipeline.py` | MOD | service (orchestrator) | request-response (per-region loop) | the existing per-region loop in `process_job` (lines 143-179) | exact (in-place edit) |
| `app/api/logos.py` | NEW | route (FastAPI router) | request-response (GET list; GET image bytes) | `app/api/pages.py` (router + `Response` bytes + `run_in_threadpool`) + `app/api/process.py` (`_require_session` shape) | exact |
| `app/api/process.py` | MOD | route | request-response | itself — handler is UNCHANGED; only `JobSpec` it accepts gains a field | exact |
| `app/models.py` | MOD | model (Pydantic v2) | validation | `JobSpec` / `RegionMark` already in the file (optional field + `field_validator`) | exact |
| `app/storage.py` | MOD | storage helpers | file-I/O (resolve fixed read-only dir) | existing `_data_dir()` / `subdir()` / `original_path()` helpers in the SAME file | exact |
| `app/config.py` | MOD | config | n/a | existing `DATA_DIR` path + `_env_int` limit constants | exact |
| `app/main.py` | MOD | error wiring | n/a | existing `RedactError` / `PipelineError` exception handlers + `_PROCESS_STATUS` table | exact |
| `web/js/logos.js` | NEW | frontend module | event-driven (catalog fetch + selection state) | `web/js/regions.js` (COPY object, DOM refs, `createElement` rows, stale machinery, public init/reset) | exact |
| `web/js/api.js` | MOD | server seam | request-response | existing `pageMeta()` / `pageImageURL()` / `processJob()` in the SAME file | exact |
| `web/index.html` | MOD | markup | n/a | the `aside#side-panel` → `.side-panel__inner` block (the region-panel section) | exact |
| `web/styles/app.css` | MOD | styles | n/a | `.region-panel__header` / `.region-empty` / `.region-list` rules + `tokens.css` vars | exact |
| `logos/` (+ `manifest.json` + `*.png`) | NEW | fixed read-only asset | n/a | none (content, not code) — see "No Analog Found" | n/a |
| `tests/test_logo.py` | NEW | test (pytest + TestClient) | n/a | `tests/test_process_api.py` + `tests/test_redact.py` (helpers, fixtures, fitz-grep) | exact |

---

## Pattern Assignments

### `app/services/logo.py` (NEW — service, fitz-free, file-I/O + transform)

The single net-new service. It is a **composite** of two proven analogs:
- **Module shape + typed error + lazy `config` read** ← `app/services/render.py`
- **The path-traversal defense (the load-bearing security pattern)** ← `app/services/redact.py` purity note + `app/storage.py` `validate_session_id` / `subdir`

**Analog A — typed-error + module shape** (`app/services/render.py:1-52`):
```python
class RenderError(Exception):
    """Typed render failure carrying a stable ``code`` (e.g. "page_not_found")."""
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
```
Mirror as `class LogoError(Exception)` with `code`/`message` (RESEARCH calls it `LogoError`, threat T-02-08). Codes to emit: `logo_not_found` (unknown id → 404) and `logo_unreadable` / `logo_invalid` for a corrupt asset (→ 422, mirror `corrupt_pdf`). **This is the only way a bad `logo_id` leaves this module — never a bare 500.**

**Analog B — the allowlist + containment defense (COPY THIS EXACTLY)** (`app/storage.py:36-89`):
```python
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

def validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        raise InvalidSessionId(f"invalid session id: {session_id!r}")
    return session_id

def subdir(kind: str, session_id: str) -> Path:
    ...
    validate_session_id(session_id)
    data_dir = _data_dir()
    dest = data_dir / kind / session_id
    resolved = dest.resolve()
    if not resolved.is_relative_to(data_dir.resolve()):   # containment assert
        raise InvalidSessionId(f"invalid session id: {session_id!r}")
    return dest
```
**The `logo_id` analog is STRONGER than `session_id`:** `logo_id` is resolved as a **dict key into the parsed manifest**, never a path segment. The manifest's `file` field (an admin-controlled bare basename) is what joins to `LOGOS_DIR`. So:
1. `entry = manifest_dict.get(logo_id)` → `None` ⇒ `raise LogoError("logo_not_found", ...)` (404, no oracle — mirrors `session_not_found`).
2. Build `path = LOGOS_DIR / entry["file"]`, then **defense-in-depth** assert `path.resolve().is_relative_to(Path(config.LOGOS_DIR).resolve())` exactly like `subdir` (T-03-01).
3. **NEVER** `LOGOS_DIR / logo_id` or `LOGOS_DIR / f"{logo_id}.png"` (RESEARCH Anti-Patterns / Pitfall 3).

**Analog C — lazy config read so tests can monkeypatch** (`app/storage.py:68-70`):
```python
def _data_dir() -> Path:
    """Resolve DATA_DIR at call time so tests can monkeypatch config.DATA_DIR."""
    return Path(config.DATA_DIR)
```
Add the identical `_logos_dir()` reading `config.LOGOS_DIR` (the tmp-LOGOS_DIR fixture in `test_logo.py` monkeypatches it — Wave 0 gap).

**Analog D — manifest JSON read with graceful `None`/empty** (`app/storage.py:156-170`):
```python
def read_session_meta(session_id: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return None
    ...
```
Mirror for `manifest.json`: an absent/empty/unparseable manifest ⇒ `list_logos()` returns `[]` (picker empty-state, A2), NOT a 500. Wrap per-asset Pillow validation in try/except and **skip** a bad asset rather than failing the whole list (T-03-02 / T-03-03 / Pitfall 6).

**Public API to expose** (named in RESEARCH §Architecture):
- `list_logos() -> list[dict]` — `[{id, name, ...}]`, never filesystem paths.
- `resolve(logo_id) -> bytes` — manifest-allowlist lookup → validated PNG bytes (for `pipeline` + the image endpoint).
- PNG validation via Pillow (`Image.open(...).verify()` / inspect `.mode in {"RGBA","LA"}` or palette `transparency`) — RESEARCH §Don't Hand-Roll / Pitfall 2.

**Purity (T-02-03):** `logo.py` is **fitz-free** — `import` only `json`, `re`, `pathlib`, `PIL`, and `from .. import config`. Mirror the `redact.py` module-docstring purity note (`app/services/redact.py:20-26`). The `test_fitz_import_confined_to_engine_seam` test will fail if `logo.py` imports fitz.

---

### `app/services/pdf_engine.py` (MOD — service, fitz seam: add `place_logo`)

**Analog:** the redaction wrappers in the SAME file (`add_redact_annot` 193-208, `apply_redactions` 211-230, `save_doc` 338-352). Same shape: a thin docstring'd wrapper around a single fitz call, taking an opaque `page`, re-exporting nothing the caller can't pass fitz-free.

**Exact code to add** (from RESEARCH §Code Examples — signature live-verified against installed 1.27.2.3):
```python
def place_logo(page, rect, *, stream: bytes | None = None, xref: int = 0) -> int:
    """Place a logo into ``rect`` (the SAME unrotated-page Rect the removal used), centered and
    aspect-preserved (D-02 / LOGO-02). MUST be called AFTER apply_redactions (after
    redact.remove_region) so the logo is not itself redacted.

    First placement: pass ``stream=<png bytes>`` (validated by logo.py). Returns the embedded
    image ``xref``. Subsequent placements of the SAME logo: pass ``xref=<that value>`` (omit
    stream) to reuse the embedded object and avoid file bloat (Pitfall 4 / verified dedup).
    """
    return page.insert_image(
        rect,
        stream=stream,
        xref=xref,
        keep_proportion=True,   # contain + center (LOGO-02) — verified default
        overlay=True,           # paint ON TOP of the cleaned content — verified default
    )
```

**Placement note:** add it in the "Redaction seam" section (after `apply_redactions`, near line 230) since it is the post-redaction companion. Keep `import fitz` the only one in the repo — the AST grep test (`test_redact.py:514-531`) asserts `offenders == ["pdf_engine.py"]`.

**Optional verification wrapper for the LOGO-02 test:** add a `get_image_rects(page, xref) -> list` thin wrapper (mirrors `get_text_words_in_rect` at 233-243) so `test_logo.py` can assert the placed bbox without importing fitz. RESEARCH §Validation Architecture uses `page.get_image_rects(xref)`.

---

### `app/services/pipeline.py` (MOD — orchestrator, in-place loop edit)

**Analog:** the existing per-region loop you are editing (`process_job` lines 143-179). The logo hook is **3 added lines inside the loop + 2 setup lines above it**. The `pdf_rect` is ALREADY computed (line 174) — the logo target rect IS that same rect.

**Existing loop body (lines 174-179) — DO NOT change the removal call, insert AFTER it:**
```python
            pdf_rect = coords.pixels_to_pdf_rect(clamped_px, effective_dpi, page)
            removed = redact.remove_region(page, pdf_rect)

            results.append(
                {"page": page_no, "removed": removed, "clamped": was_clamped}
            )
```

**Edit per RESEARCH §Code Examples (additive lines marked ►):**
```python
    # ► Setup ABOVE the loop (after the n_pages/results init, ~line 141):
    logo_bytes = logo.resolve(job_spec.logo_id) if getattr(job_spec, "logo_id", None) else None
    logo_xref = 0

    for region in job_spec.regions:
        ...
        pdf_rect = coords.pixels_to_pdf_rect(clamped_px, effective_dpi, page)
        removed = redact.remove_region(page, pdf_rect)
        if logo_bytes is not None:                                          # ►
            # Insert AFTER removal, on the SAME rect; reuse xref after first embed (Pitfall 4).
            logo_xref = pdf_engine.place_logo(                              # ►
                page, pdf_rect,                                            # ►
                stream=(logo_bytes if logo_xref == 0 else None),          # ►
                xref=logo_xref,                                           # ►
            )                                                             # ►
        results.append({"page": page_no, "removed": removed, "clamped": was_clamped})
```

**Critical ordering (RESEARCH Pattern 1 / Pitfall 1):** `redact.remove_region` calls `apply_redactions` internally (`redact.py:117`). Insert the logo **strictly after** it returns, or the logo gets redacted away. Place the logo **regardless of `removed`** (A1: the user framed it as a replacement target; `removed` only gates the "沒有可移除的內容" notice).

**Imports:** add `logo` to the existing `from . import coords, pdf_engine, redact, render` line (line 32). `pipeline.py` stays fitz-free — the only new fitz call is inside `place_logo` (in `pdf_engine`).

**Error surfacing:** `logo.resolve()` raising `LogoError` propagates out of `process_job` and is mapped to 4xx by `main.py` (see below) — mirror the existing `RedactError`/`PipelineError` propagation (the function already lets `redact.RedactError` escape, per the `process_job` docstring lines 99-101).

---

### `app/api/logos.py` (NEW — FastAPI router: `GET /logos` + `GET /logos/{id}/image`)

**Analog A — router skeleton + `_require_session`-style guard** (`app/api/process.py:24-46`):
```python
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from .. import config, storage
...
router = APIRouter(tags=["process"])

def _require_session(session_id: str) -> None:
    if not storage.session_exists(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "找不到此工作階段。"},
        )
```
Mirror: `router = APIRouter(tags=["logos"])`. The library is NOT session-scoped, so there is no `_require_session` here — instead an unknown `logo_id` on the image endpoint maps the `LogoError("logo_not_found")` to a 404 with the `{code,message}` shape.

**Analog B — `GET /logos` list endpoint** (mirror the simple-return style; RESEARCH §Code Examples):
```python
@router.get("/logos")
async def list_logos() -> dict:
    """List the fixed logo library for the picker (LOGO-01). Absent/empty library yields
    {"logos": []} (picker empty-state), never a 500."""
    return {"logos": logo.list_logos()}
```
`list_logos()` is fast (parse a small JSON + cached validation), so a `run_in_threadpool` is optional here. If Pillow re-decodes on each call, wrap it like the render call.

**Analog C — `GET /logos/{id}/image` returning raw bytes + the typed-404 map** (`app/api/pages.py:32-64` for the `Response(content=..., media_type=...)` bytes pattern; `app/api/process.py:79-87` for the `except <Error>` → 404 map):
```python
@router.get("/logos/{logo_id}/image")
async def get_logo_image(logo_id: str) -> Response:
    try:
        data = await run_in_threadpool(logo.resolve, logo_id)
    except LogoError as err:
        raise HTTPException(status_code=404, detail={"code": err.code, "message": err.message}) from err
    return Response(content=data, media_type="image/png")
```
This is the thumbnail source (RESEARCH Open Question 1 / UI-SPEC default #8): serve the full PNG, CSS-scale it in the grid. The `logo_id` here is resolved through the SAME manifest allowlist (T-03-01) — a crafted id is a plain 404, never a path read.

**Register the router** in `app/main.py` next to the others (`app/main.py:36-38`):
```python
from .api import logos, pages, process, sessions
...
app.include_router(logos.router)
```

---

### `app/api/process.py` (MOD — handler UNCHANGED)

**Analog:** itself. The handler `process_session` (lines 49-61) passes the whole validated `JobSpec` to `pipeline.process_job` — so adding `logo_id` to `JobSpec` flows through with **zero handler change**. The only thing to verify: the `api.js` JSDoc contract block and this file's docstring both mention the new optional field. No new endpoint.

---

### `app/models.py` (MOD — add optional `logo_id` to `JobSpec`)

**Analog:** `JobSpec` + its `_cap_region_count` validator already in the file (lines 77-96), and `RegionMark`'s optional-with-validator style.

**Exact edit (RESEARCH §Code Examples):**
```python
class JobSpec(BaseModel):
    dpi: int = Field(..., ge=config.MIN_DPI, le=config.MAX_DPI)
    regions: List[RegionMark] = Field(default_factory=list)
    logo_id: str | None = Field(                                            # ►
        default=None, max_length=128,                                       # ► cheap DoS guard
        description="optional global logo id (D-01); resolved via manifest allowlist",
    )
```
**No charset validator is needed for safety** (resolution is a manifest-dict lookup, never a path — RESEARCH note at the `JobSpec` example). A light `max_length` is defense-in-depth against absurd inputs (V5). Pydantic's existing `RequestValidationError` handler in `main.py` already shapes a bad type into `{code:"invalid_request"}` 422.

---

### `app/storage.py` (MOD — add fixed read-only library path helpers)

**Analog:** `_data_dir()` (68-70) + `original_path()` (122-124) in the SAME file.

**Pattern to mirror:**
```python
def _logos_dir() -> Path:
    """Resolve LOGOS_DIR at call time so tests can monkeypatch config.LOGOS_DIR."""
    return Path(config.LOGOS_DIR)

def logo_manifest_path() -> Path:
    return _logos_dir() / "manifest.json"
```
**Key distinction (RESEARCH §Project Constraints):** the logo library is a **fourth, fixed, read-only location OUTSIDE** the per-session `originals/`/`work/`/`outputs/` dirs — it is shared, not session-scoped, so it does NOT go through `subdir()` and is NOT validated by `_SESSION_ID_RE`. (The `logo_id`→file safety lives in `logo.py` via the manifest allowlist, not here.) These helpers may equally live in `logo.py` directly; pick one home and keep it consistent. The containment assert (`is_relative_to(LOGOS_DIR)`) belongs wherever the `entry["file"]` join happens.

---

### `app/config.py` (MOD — add `LOGOS_DIR` + optional `MAX_LOGO_BYTES`)

**Analog:** `DATA_DIR` path resolution (line 30) + the `_env_int` limit constants (33-52) in the SAME file.

**Pattern to mirror:**
```python
# Fixed read-only logo library (Phase 3). Defaults to a repo-relative ./logos; bake-in/mount
# in deploy (CLAUDE.md "read-only volume for the fixed logo library"). Absent dir ⇒ empty picker.
LOGOS_DIR: Path = Path(os.environ.get("LOGOS_DIR", "./logos")).resolve()

# Per-asset guard (T-03-02 / Pitfall 6): cap library PNG file size before Pillow decode.
MAX_LOGO_BYTES: int = _env_int("MAX_LOGO_BYTES", 10 * 1024 * 1024)
```
Follow the `DATA_DIR` `.resolve()` + env-default idiom exactly (Runtime State Inventory: "follows the `DATA_DIR` pattern; default to a repo-relative `./logos`").

---

### `app/main.py` (MOD — wire `LogoError` → structured 4xx)

**Analog:** the `RedactError` / `PipelineError` handlers + the `_PROCESS_STATUS` table (lines 84-106).

**Pattern to mirror:**
```python
from .services.logo import LogoError      # add to the imports block (~line 26-31)
...
_LOGO_STATUS: dict[str, int] = {
    "logo_not_found": 404,
    "logo_invalid": 422,
    "logo_unreadable": 422,
}

@app.exception_handler(LogoError)
async def _handle_logo_error(_request: Request, exc: LogoError) -> JSONResponse:
    status = _LOGO_STATUS.get(exc.code, 422)
    return JSONResponse(
        status_code=status,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )
```
This guarantees a `LogoError` raised inside `process_job` (when `/process` carries a bad `logo_id`) surfaces as a typed 4xx, never a bare 500 (T-02-08). It mirrors `_handle_redact_error` (91-97) byte-for-byte in shape.

---

### `web/js/logos.js` (NEW — frontend module: thumbnail grid + selection state)

**Analog:** `web/js/regions.js` end-to-end. Copy its **five structural patterns**:

**1. Verbatim COPY object** (`regions.js:34-58`) — all 繁中 strings from UI-SPEC §Copywriting in one object:
```js
const COPY = {
  heading: "我司商標",
  subtext: "選擇要置入移除區域的商標(套用後置入所有框選區域)",
  selectAria: (name) => `選擇商標:${name}`,
  noLogo: "不置入商標",
  emptyHeading: "尚無可用的商標",
  emptyBody: "商標庫目前是空的。您仍可框選並移除供應商商標,完成後下載。商標由管理者預先放入。",
  loading: "正在載入商標庫…",
  loadFailed: "無法載入商標庫,請重新整理後再試一次。",
  staleNotice: "所選商標已變更,請重新套用以更新結果",  // UI-SPEC default #7
};
```

**2. DOM refs at module top + `import * as api`** (`regions.js:29-95`). Import the stale machinery seam — but note Phase 3 must call `regions.js`'s invalidation. **Reuse the existing `onRegionsEdited()` stale path** rather than re-implementing it: the cleanest wiring is to add a small exported hook in `regions.js` (e.g. `export function notifyJobInputChanged()` that runs the same `resultFresh=false` + `setViewMode("original")` + `setActionStatus(staleNotice)` block at `regions.js:440-452`) and have `logos.js` call it on every selection change. This keeps ONE stale state machine (Pitfall 5 is load-bearing).

**3. `createElement`-only DOM building (NEVER innerHTML)** (`regions.js:160-238`, esp. `renderList` + `makeTrashIcon`). Build each thumbnail as a `<button type="button">` with an `<img src=api.logoImageURL(id)>`, a caption via `textContent`, and `aria-label` via `setAttribute` (T-03-04 / T-02-11). The `makeTrashIcon` SVG-via-`createElementNS` helper (218-238) is the exact pattern for an optional accent check badge.

**4. Single-select state + accent marker** (`regions.js:301-317` `setActiveRegion`): toggle a class + `aria-pressed` by `dataset` comparison (NOT a CSS-selector string built from the id — WR-03 note at 296-300). Hold `selectedLogoId` as the single client state (UI-SPEC: at most one accent thumbnail).

**5. Public `init`/`reset` exports** (`regions.js:675-717` `initRegions`/`resetRegions`): export `initLogos({ session_id })` (fetch catalog once, render grid or empty/loading/failed state) and `resetLogos()` (clear `selectedLogoId`). Wire them in `app.js` alongside `initRegions`/`resetRegions` (see below).

**Result-with-logo (D-06) needs NO new code in this module:** the existing before/after toggle (`regions.js:519-542` `setViewMode`) already swaps to `api.resultImageURL(...)` which renders the work copy — now containing the logo. Only the `#view-result` label text changes (UI-SPEC conditional relabel: `移除+置入結果` when a logo is selected, else `移除結果`).

**Module load wiring** (mirror `regions.js:736-764`): add `<script type="module" src="js/logos.js">` to `index.html` after `regions.js` and before `app.js`.

---

### `web/js/api.js` (MOD — add `listLogos()` + `logoImageURL()`; add `logo_id` to the process body)

**Analog:** `pageMeta()` (110-123, the fetch-or-throw GET) + `pageImageURL()` (95-107, the URL builder) + `processJob()` (136-149) — all in the SAME file.

**Exact additions (RESEARCH §Frontend seam):**
```js
/** List the fixed logo library: { logos: [{ id, name, ... }] }. */
export async function listLogos() {
  const response = await fetch(API_BASE + "/logos");
  if (!response.ok) throw await toApiError(response);
  return response.json();
}

/** Build a logo-image URL (the picker thumbnail src), mirroring pageImageURL. */
export function logoImageURL(id) {
  return API_BASE + "/logos/" + encodeURIComponent(id) + "/image";
}
```
`processJob()` is UNCHANGED — the caller (`logos.js`/`regions.js`) just includes `logo_id` in the spec: `api.processJob(sid, { dpi, regions: getJobRegions(), logo_id: selectedLogoId || null })`. Keep `api.js` the **sole** server seam (the module docstring at 1-27 states this; `logos.js` must call these helpers, never `fetch` directly — RESEARCH Anti-Patterns / T-02-12).

**Also update the JSDoc contract block** (the `Backend contract consumed` comment, 8-27) to document `GET /logos`, `GET /logos/{id}/image`, and the new optional `logo_id` on `/process` — the file conventionally documents every endpoint it touches.

---

### `web/index.html` (MOD — add logo-picker section inside `aside#side-panel`)

**Analog:** the `.region-panel__header` + `.region-empty` + `.region-list` block inside `.side-panel__inner` (lines 299-336).

**Pattern to mirror** — append a NEW section AFTER the region list/notice (UI-SPEC: below the region list, A3), inside the same `.side-panel__inner`:
```html
<!-- Logo picker (Phase 3) — new section below the region list, same side-panel column. -->
<section class="logo-picker" id="logo-picker">
  <header class="region-panel__header">      <!-- reuse the header treatment -->
    <h2 class="region-panel__heading">我司商標</h2>
    <p class="region-panel__scope">選擇要置入移除區域的商標(套用後置入所有框選區域)</p>
  </header>
  <div class="logo-grid" id="logo-grid" role="group" hidden></div>   <!-- rows via createElement -->
  <div class="region-empty" id="logo-empty" hidden> ... 尚無可用的商標 ... </div>
  <!-- loading: reuse .spinner; failed: reuse .region-notice block -->
</section>
```
Reuse `.region-panel__header`, `.region-panel__heading`, `.region-empty`, `.region-notice`, and `.spinner` rather than inventing new chrome (UI-SPEC §Component Inventory). The picker is visible only in the `loaded` state (the side-panel already toggles via `app.js`'s `setSidePanelExpanded` → `.main--paneled`).

**Relabel** the existing `#view-result` segment (line 160-162) text from `移除結果` → handled in JS conditionally (don't hardcode in HTML; `logos.js`/`regions.js` sets it per `selectedLogoId`).

---

### `web/styles/app.css` (MOD — thumbnail-grid styles using EXISTING tokens)

**Analog:** `.region-panel__header` (455-461), `.region-empty` (517-537), `.region-list` (541-548) — and `tokens.css` vars (`--space-md` 16, `--control-hit` 40, `--radius-sm` 6, `--side-panel-width` 320, `--color-surface`/`--color-accent`/`--color-border`/`--color-neutral-hover`).

**Pattern (UI-SPEC §Component Inventory):**
```css
/* tokens.css :root additions — exactly two, theme-agnostic (UI-SPEC New tokens): */
--logo-thumb-size: 72px;
--logo-grid-gap: var(--space-sm);

/* app.css — grid auto-fills the 320px column */
.logo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--logo-thumb-size), 1fr));
  gap: var(--logo-grid-gap);
  padding: var(--space-md);
}
.logo-thumb {                       /* a focusable <button> */
  min-height: var(--control-hit);   /* 40px hit target, mirrors .danger-text-btn */
  background: var(--color-surface);  /* neutral backing behind transparent PNG (Pitfall 2) */
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.logo-thumb:hover { background: var(--color-neutral-hover); }   /* NOT accent — mirrors .region-row:hover */
.logo-thumb.is-selected { border: 2px solid var(--color-accent); }   /* the ONE new accent element */
.logo-thumb img { width: 100%; height: 100%; object-fit: contain; }  /* matches D-02 contain */
```
No new color tokens, no new font sizes — only the two layout vars (UI-SPEC §Color / §New tokens). Add a `[data-theme="dark"]` override only if a real asset needs it (UI-SPEC default #4).

---

### `tests/test_logo.py` (NEW — pytest + TestClient)

**Analog:** `tests/test_process_api.py` (TestClient slice + `_upload` + `_exported_region_empty` helper + deferred-mutation SHA-256) and `tests/test_redact.py` (the fitz-import AST grep + `_build_pdf` geometry).

**Fixtures to add (Wave 0 gaps — mirror `conftest.py`):**
- A transparent-PNG fixture `logo_png_bytes` — build in-memory via `PIL.Image.new("RGBA", ...)` (no committed binary; mirrors how `conftest._build_pdf` builds PDFs in-memory at `conftest.py:18-32`).
- A tmp logo-library fixture — write `manifest.json` + the PNG into a tmp dir and `monkeypatch.setattr(config, "LOGOS_DIR", ...)`, mirroring the autouse `isolated_data_dir` (`conftest.py:47-56`).

**Test patterns to copy:**
- **LOGO-02 bbox/aspect** — mirror `_exported_region_empty` (`test_process_api.py:39-50`): open exported PDF, recompute `pdf_rect` via `coords.pixels_to_pdf_rect`, then `page.get_image_rects(xref)` (or the new `pdf_engine.get_image_rects` wrapper) and assert contained + aspect ≈ source (RESEARCH §Validation Architecture concrete snippet, lines 459-466). Geometry: 200×300pt page, region pts `(10,40,190,120)` — same `_REGION_PT` constant as `test_redact.py:34`.
- **LOGO-02 survives-redaction + single-xref** — mirror `test_remove_region_*` unit style (`test_redact.py:52-132`): assert text/vector still removed AND the logo image present; assert one xref reused across N regions (`page.get_images()`).
- **LOGO-01 list + path-traversal** — mirror the TestClient + structured-4xx assertions (`test_process_api.py:165-225`): `GET /logos` returns ids+names with no paths; `logo_id="../../app/config.py"` and an unknown id → 404 `logo_not_found`, never 500 (T-03-01). Mirror `test_process_crafted_session_id_is_404` (243-247).
- **D-01 no-logo = pure removal** — extend `test_process_api.py`: a `/process` with no `logo_id` produces NO embedded image (Phase-2 behavior unchanged).
- **D-05 original SHA-256** — extend the existing assertion (`test_process_api.py:63-79`) to cover a remove+insert run.
- **AGPL seam** — the existing `test_fitz_import_confined_to_engine_seam` (`test_redact.py:514-531`) ALREADY covers `logo.py` and `pipeline.py` automatically (it walks all `app/**/*.py`); just confirm it stays green after `place_logo` lands. No new grep test needed.

---

## Shared Patterns

### Path-traversal defense (the load-bearing security pattern)
**Source:** `app/storage.py:36-89` (`validate_session_id` allowlist + `subdir` `is_relative_to` containment).
**Apply to:** `logo.py` `resolve(logo_id)` and `GET /logos/{id}/image` — but as a **manifest-dict allowlist** (id is a dict key, never a path), plus the `is_relative_to(LOGOS_DIR)` containment assert on the resolved `entry["file"]` join (T-03-01). Unknown id → 404 `logo_not_found` (no oracle), exactly like `session_not_found`.

### Typed error → structured `{detail:{code,message}}` 4xx (never a bare 500)
**Source:** `app/services/render.py:26-32` (`RenderError` shape) + `app/main.py:91-106` (`@app.exception_handler` + `_PROCESS_STATUS` map).
**Apply to:** `LogoError` in `logo.py` + a `@app.exception_handler(LogoError)` + `_LOGO_STATUS` table in `main.py` (T-02-08 / T-03-03). Maps `logo_not_found`→404, decode failures→422.

### CPU-bound work in `run_in_threadpool`
**Source:** `app/api/pages.py:46-49` and `app/api/process.py:59-61`.
**Apply to:** the `GET /logos/{id}/image` resolve (Pillow decode) and any `/logos` decode path. The `/process` insertion stays inside the existing `process_job` threadpool call (RESEARCH §Project Constraints).

### Lazy `config.*` read for monkeypatchable tests
**Source:** `app/storage.py:68-70` (`_data_dir`).
**Apply to:** `_logos_dir()` reading `config.LOGOS_DIR`, so `test_logo.py` can monkeypatch it (mirrors `isolated_data_dir`).

### `api.js` is the sole server seam (embedding contract, Pattern 4)
**Source:** `web/js/api.js:1-31` (module docstring + `API_BASE` + `toApiError`).
**Apply to:** `listLogos()` / `logoImageURL()` go HERE; `logos.js` calls them and never `fetch`es or builds a server URL itself (T-02-12 / RESEARCH Anti-Patterns).

### `textContent` / `createElement` only — never `innerHTML` (XSS guard)
**Source:** `web/js/regions.js:160-238` + the security note at `regions.js:23-27`.
**Apply to:** ALL logo `name`/caption/aria rendering in `logos.js` (T-03-04 — manifest text is untrusted-ish admin content; still never reflected as HTML).

### Reuse ONE stale state machine on a job-input change
**Source:** `web/js/regions.js:440-490` (`onRegionsEdited` → `updateActionGroup`).
**Apply to:** a logo selection/clear is a job-input change ⇒ it MUST run the same invalidation (`resultFresh=false`, demote `下載 PDF`→disabled / `重新套用`→accent, drop result view to `原圖`, show stale notice). Add an exported hook to `regions.js`; do NOT fork the machine (Pitfall 5 is load-bearing).

---

## No Analog Found

| File | Role | Data Flow | Reason / Guidance |
|------|------|-----------|-------------------|
| `logos/manifest.json` + `logos/*.png` | fixed read-only asset (content) | n/a | Not code — it is application **content** the phase must CREATE (no in-repo precedent; the `logos/` dir does not exist yet — verified). Seed at least one transparent placeholder PNG so the picker + `test_logo.py` have a real asset (RESEARCH §Environment Availability / A2). Schema recommendation (RESEARCH Open Question 2): `{ "id": "...", "file": "...png", "name": "...", "native_w": 0, "native_h": 0, "tags": [] }`. Deployment (Phase 5) bakes-in/mounts it. This is the ONLY "no analog" item — and it's data, not a pattern gap. |

---

## Metadata

**Analog search scope:** `app/` (all 16 .py modules), `web/js/` + `web/index.html` + `web/styles/`, `tests/` (conftest + process/redact suites).
**Files scanned (read in full or targeted):** `app/api/process.py`, `app/api/pages.py`, `app/api/sessions.py`, `app/services/pdf_engine.py`, `app/services/pipeline.py`, `app/services/render.py`, `app/services/redact.py`, `app/services/ingest.py`, `app/storage.py`, `app/models.py`, `app/config.py`, `app/main.py`, `web/js/api.js`, `web/js/regions.js`, `web/js/app.js`, `web/js/viewer.js` (targeted), `web/index.html`, `web/styles/app.css` (targeted), `web/styles/tokens.css` (targeted), `tests/conftest.py`, `tests/test_process_api.py`, `tests/test_redact.py`.
**Verified absent:** `logos/` directory (net-new asset to create), any second `import fitz` (AST grep test enforces single seam).
**Pattern extraction date:** 2026-05-22
