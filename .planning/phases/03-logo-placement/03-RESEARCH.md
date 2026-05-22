# Phase 3: 商標置入 (Logo Placement) - Research

**Researched:** 2026-05-22
**Domain:** PyMuPDF `insert_image` logo placement into already-redacted regions, integrated into a proven deferred-mutation remove→export pipeline; fixed read-only logo library with safe id→file resolution; side-panel thumbnail picker reusing the dual-theme/繁中 UI contract.
**Confidence:** HIGH (the load-bearing claim — `insert_image(keep_proportion=True)` contains+centers, returns a reusable xref, and the placed bbox is verifiable — was live-verified against the installed PyMuPDF 1.27.2.3; the pipeline insertion seam and frontend seam were read directly from the built Phase-2 code.)

## Summary

Phase 3 is a **small, additive layer on a proven Phase-2 spine**, not new infrastructure. The removal loop in `pipeline.process_job` already computes, per region, the exact unrotated-page `pdf_rect` and calls `redact.remove_region(page, pdf_rect)`. Logo placement is one more call **on the same `page` and the same `pdf_rect`, immediately after** removal: a new `pdf_engine.place_logo(page, rect, stream=...)` wrapper around `Page.insert_image(rect, stream=logo_bytes, keep_proportion=True)`. Because `insert_image` defaults to `keep_proportion=True` and `overlay=True`, the logo is scaled to *contain* (fit inside) the rect, **centered**, with natural letterbox margins where aspect differs — which is exactly D-02. This was verified live: a 2:1 logo placed into a 100×100 rect landed as a centered 100×50 image whose bbox is fully inside the target. LOGO-02 ("維持長寬比") is therefore satisfied by a default argument, and is verifiable by `Page.get_image_rects(xref)`.

The other half is the **logo library**: a fixed read-only `logos/` directory + `manifest.json` placed by an admin (no upload UI — D-04). The single real risk here is the same one Phase 1/2 already solved for `session_id` and the client filename: **an untrusted `logo_id` must never build a filesystem path**. The proven pattern (`storage.validate_session_id` allowlist regex + `subdir` containment assert, threat T-01-04 / T-02-06) maps directly: resolve `logo_id` through the manifest dict (an allowlist of known ids→filenames), reject anything not in it with a 404, and never `Path(...) / logo_id`. Pillow (already installed, 12.2.0) validates each PNG at load.

On the frontend, `api.js` stays the sole server seam (add one `listLogos()` call + the `logo_id` field on the existing `/process` POST). The side-panel currently hosts the region list; the logo picker is a **new section in the same `aside#side-panel`** (the Phase 1/2 contract explicitly reserved this column for it). Selecting/changing a logo must reuse the existing "編輯使結果失效 → 重新套用" stale machinery in `regions.js` — a logo change is a job-input change, so it invalidates a fresh result exactly like a region edit does. The result preview (D-06) needs **zero new rendering**: `/result/.../image` already renders the work copy, which now contains the inserted logo, so the existing 原圖/移除結果 toggle shows the logo for free.

**Primary recommendation:** Add `pdf_engine.place_logo()` (the only new fitz call) + a `logo.py` service that loads/validates `manifest.json` and resolves `logo_id`→bytes through the manifest allowlist; hook one `place_logo` call into `process_job` immediately after `redact.remove_region` on the same `pdf_rect`, deduping the embedded image via the returned `xref` across all regions; extend `JobSpec` with an optional `logo_id`; add a `GET /logos` endpoint and a side-panel thumbnail picker wired through `api.js`, with a logo change invalidating a fresh result.

## User Constraints (from CONTEXT.md)

<user_constraints>

### Locked Decisions

- **D-01: 全域單一 logo.** 套用後,JobSpec 內**所有**移除區域都置入同一個選定的 logo。`JobSpec` 擴充為帶一個**選用的全域 `logo_id`**(`{dpi, regions[], logo_id?}`);未選 logo 時為純移除,維持 Phase 2 行為。不做 per-region 不同 logo(列入 deferred)。
- **D-02: contain + 置中.** logo 在每個移除區域框內「置中、完整顯示」:維持長寬比(`keep_proportion`,LOGO-02 鎖定)縮到框內並**置中**,長寬比與框不符處自然留白。對齊採置中,非靠邊。
- **D-03: PNG 去背(含 alpha 透明).** v1 庫可容納**多個版本**(如水平/直式/深淺),非單一檔。不支援 SVG(`insert_image` 不直接吃 SVG,需先轉點陣 — 列入 deferred)。
- **D-04: 庫 = `logos/` 目錄 + `manifest.json`.** manifest 每筆至少帶 `id`、檔名、顯示名,(選用)尺寸/版型標籤。庫為**固定唯讀資產**,由管理者放檔(v1 無上傳 UI)。
- **D-05: 側欄縮圖網格選擇器**,沿用雙主題 token 與繁中文案。
- **D-06: 結果預覽含 logo.** 延伸現有「移除結果」after-image,在後端對 work 副本套用「移除 + logo 置入」後渲染,讓使用者在下載前於「原圖 / 移除+置入結果」對照中就看到 logo 已就定位。

### Claude's Discretion

縮圖網格的版面細節、選取狀態樣式、側欄確切位置;`manifest.json` 的精確 schema/欄位;未選 logo 時的行為(預設純移除,download/套用按鈕狀態);更換 logo 或變更選取是否使既有結果失效(沿用 Phase 2「編輯框選使結果失效、需『重新套用』」模式);logo alpha 邊緣的渲染細節;商標庫的種子內容(可先放 placeholder logo)。維持沿用 UI-SPEC token、雙主題與繁中文案。

### Deferred Ideas (OUT OF SCOPE)

- per-region 不同 logo / 逐區開關置入 — v1.x。
- 移除框與置入框分開(獨立置入位置)— v1.x。
- SVG 向量 logo 支援(需轉點陣)— 視需求再議。
- logo 透明度/旋轉/拖曳微調、框內對齊切換(靠邊/可調留白/內距)— 目前固定置中 contain。
- 商標上傳 UI(自助新增 logo 到庫)— v1 由管理者放檔。
- 點陣圖/掃描型 PDF 與獨立影像檔的 logo 置入 — Phase 4。

</user_constraints>

## Phase Requirements

<phase_requirements>

| ID | Description | Research Support |
|----|-------------|------------------|
| **LOGO-01** | 系統提供固定的我司商標庫,使用者可瀏覽並挑選要使用的 logo | `logos/` dir + `manifest.json` (D-04); new `logo.py` service loads/validates the manifest; `GET /logos` lists it; side-panel thumbnail grid (D-05) fetches via `api.js`. Safe `logo_id`→file resolution mirrors the proven `validate_session_id` allowlist pattern (§Don't Hand-Roll, §Security). |
| **LOGO-02** | 使用者可將選定的 logo 放到框選位置,並維持長寬比縮放貼合 | `Page.insert_image(rect, stream=, keep_proportion=True)` — **live-verified**: contains + centers, aspect preserved exactly, placed bbox ⊆ target rect (§Code Examples, §Validation Architecture). Target rect = the SAME `pdf_rect` the removal loop already computes (REMOVE-03 placement correctness inherited). |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

These directives carry the same authority as locked decisions. The planner must verify compliance.

- **PyMuPDF is the core PDF engine** — logo insertion uses `Page.insert_image`, not a cover-rectangle or any other library.
- **`import fitz` lives in EXACTLY ONE file** (`app/services/pdf_engine.py`) — the AGPL isolation seam (threat T-02-03). The new `place_logo` wrapper MUST go in `pdf_engine.py`; `logo.py`/`pipeline.py` stay fitz-free. An acceptance grep checks no other file imports fitz.
- **Deferred mutation (D-05)** — only the `work/` copy is ever mutated; the immutable original (chmod 0o444) is never touched. `process_job` already resets the work copy from the pristine original on every run (WR-01); logo insertion happens on that same work copy in the same pass.
- **Three-directory isolation** — `originals/` / `work/` / `outputs/`. The logo library is a **fourth, fixed, read-only asset location OUTSIDE** the per-session dirs (it is shared, not session-scoped).
- **FastAPI + Pydantic v2** for the API contract; **vanilla JS + server-rendered PNG** on the frontend (PDF.js is forbidden per SKELETON.md — the browser never parses the PDF). `web/js/api.js` is the sole server seam.
- **All user-facing strings are Traditional Chinese (繁體中文)**; dynamic strings written via `textContent` / `createElement`, never `innerHTML` (threat T-02-11).
- **CPU-bound work runs in `run_in_threadpool`** (the existing `/process` handler already does this; insertion adds negligible cost but stays inside that threadpool call).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Logo image insertion into the PDF rect | **API / Backend** (`pdf_engine.insert_image` via `pipeline`) | — | All PDF mutation is server-authoritative (PyMuPDF, Python). The browser never edits the PDF. Inserting the logo is a fitz call → must be in `pdf_engine.py`. |
| Logo library storage + manifest | **Database / Storage** (filesystem `logos/` + `manifest.json`) | API (`logo.py` reads it) | No DB in v1; the library is static files. A fixed read-only dir is the right "storage" tier. |
| Logo list + metadata serving | **API / Backend** (`GET /logos`) | — | The frontend gets the catalog over the API seam (embeddability — Pattern 4); never reads `logos/` directly. |
| `logo_id` → file resolution + validation | **API / Backend** (`logo.py` allowlist) | — | Untrusted input must be validated server-side through a manifest allowlist before it ever names a file (T-01-04 pattern). |
| Logo thumbnail picker + selection state | **Browser / Client** (`web/js/` new section in `side-panel`) | — | Pure UI state (which logo is selected); crystallizes into the `logo_id` field of the `/process` payload. |
| Result preview WITH logo | **API / Backend** render of work copy | Browser (existing toggle) | `/result/.../image` already renders the work copy; the logo is in it after insertion. Zero new rendering (D-06). |
| Stale-result invalidation on logo change | **Browser / Client** (`regions.js` action group) | — | A logo change is a job-input change; reuse the existing "編輯使結果失效" machinery client-side. |

## Standard Stack

No new dependencies. Phase 3 uses libraries already pinned and installed.

### Core
| Library | Version (verified) | Purpose | Why Standard |
|---------|--------------------|---------|--------------|
| PyMuPDF (`fitz`) | **1.27.2.3** installed (pin `>=1.27,<1.28`) | `Page.insert_image` for logo placement; `Page.get_image_rects` for placement verification | The project-mandated engine; `insert_image` is the canonical logo-placement API and is the same module already doing redaction/render. `[VERIFIED: .venv python -c "import fitz; fitz.version" → ('1.27.2.3','1.27.2',None)]` |
| Pillow (`PIL`) | **12.2.0** installed (pin `>=12,<13`) | Validate/inspect logo PNGs at library load (open, verify mode/alpha, read native px size for the manifest/thumbnail) | Already a dependency (declared for the Phase-4 image path). The standard, safe way to confirm a file is a real decodable PNG with the expected alpha before it reaches the PDF engine. `[VERIFIED: python -c "import PIL; PIL.__version__" → 12.2.0]` |
| FastAPI + Pydantic v2 | 0.115.x / 2.x (installed) | `GET /logos` endpoint; extend `JobSpec` with optional `logo_id`; Pydantic validation of the new field | Already the framework; one new field + one new GET route follow the existing `process.py`/`models.py` patterns verbatim. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python stdlib `json` | — | Parse `manifest.json` | Always (already used by `storage.read_session_meta`). |
| Python stdlib `re` | — | `logo_id` allowlist regex (mirror `_SESSION_ID_RE`) | At every `logo_id` resolution. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `insert_image(stream=logo_bytes)` | `insert_image(filename=logo_path)` | `filename=` reads from disk each call; `stream=` lets `logo.py` read+validate the bytes once (Pillow) and pass them in, keeping all file I/O in the service layer and the path off the fitz call. **Use `stream=`.** `[CITED: pymupdf.readthedocs.io/en/latest/page.html#Page.insert_image]` |
| Raster PNG logos (D-03) | `show_pdf_page()` for vector logos | Vector logos stay crisp at any scale, but require 1-page-PDF logo assets and SVG→PDF conversion — explicitly **deferred** (D-03). Stick with `insert_image` + PNG for v1. |
| Re-embed logo per region | Reuse returned `xref=` | Re-embedding bloats the file linearly with placements (Pitfall 7). Reuse the xref. **Live-verified the xref is reusable** (§Code Examples). |

**Installation:** None required — all packages already in `requirements.txt` and installed in `.venv`.

**Version verification (performed this session):**
```
.venv/Scripts/python.exe -c "import fitz; print(fitz.version)"   # → ('1.27.2.3', '1.27.2', None)  [VERIFIED]
python -c "import PIL; print(PIL.__version__)"                     # → 12.2.0                         [VERIFIED]
```

## Architecture Patterns

### System Architecture Diagram

```
                ┌─────────────────────────── BROWSER (thin client) ──────────────────────────┐
                │                                                                              │
  user picks ──▶│  side-panel: [ region list (Phase 2) ] + [ NEW logo thumbnail grid (D-05) ] │
  a logo        │         │ selects logo_id                          │ draws regions          │
                │         ▼                                          ▼                         │
                │   selectedLogoId ──────────────┐         regionsByPage (image-px)           │
                │   (logo change ⇒ stale, like a region edit — reuse onRegionsEdited)         │
                └───────────────┬──────────────────────────────────┬───────────────────────────┘
                                │ GET /logos (once)                 │ POST /process
                                │   via api.listLogos()             │   { dpi, regions[], logo_id? }
                                ▼                                   ▼   (logo_id rides along)
   ┌──────────────────────────────────── API LAYER (FastAPI) ────────────────────────────────────┐
   │  GET /logos ─▶ logo.list_logos()          POST /sessions/{id}/process ─▶ pipeline.process_job │
   │       (reads manifest, returns catalog)         (run_in_threadpool, existing handler)         │
   └─────────────┬───────────────────────────────────────────────┬─────────────────────────────────┘
                 │                                                 │
                 ▼                                                 ▼
   ┌──────────── logo.py (NEW, fitz-free) ────────────┐   ┌─────────── pipeline.process_job ──────────┐
   │ load manifest.json (json) + validate PNGs (PIL)  │   │ reset work from pristine original (WR-01)  │
   │ list_logos() → [{id, name, ...}]                 │   │ for each region:                           │
   │ resolve(logo_id) → bytes  (ALLOWLIST via manifest│◀──┤   clamp px_rect → pdf_rect (coords)        │
   │   dict; NEVER Path()/logo_id — T-01-04 pattern)  │   │   redact.remove_region(page, pdf_rect)     │
   └──────────────────────┬───────────────────────────┘   │   ── if logo_id: ──────────────────────────│
                          │ logo bytes                     │   pdf_engine.place_logo(page, pdf_rect,    │
                          └────────────────────────────────┼─▶   stream=logo_bytes, xref=cached_xref)  │
                                                            │   (insert AFTER redaction; same rect)      │
                                                            │ save → work/ + outputs/原名_logoswap.pdf  │
                                                            └──────────────────┬─────────────────────────┘
                                                                               │ fitz calls only here
                                                                               ▼
                                                            ┌──── pdf_engine.py (SOLE fitz import) ────┐
                                                            │ place_logo() → page.insert_image(rect,    │
                                                            │   stream=, keep_proportion=True,           │
                                                            │   overlay=True, xref=) → returns xref      │
                                                            └────────────────────────────────────────────┘

   Result preview (D-06): GET /result/.../image renders the WORK copy — which now contains the
   inserted logo — so the existing 原圖/移除結果 toggle shows the logo with ZERO new rendering.
```

### Recommended Structure (additions only — bold = new)

```
app/
├── api/
│   ├── process.py          # extend: JobSpec now carries optional logo_id (handler unchanged otherwise)
│   └── logos.py            # ★ NEW: GET /logos (list the fixed library)
├── services/
│   ├── pdf_engine.py       # ADD place_logo(page, rect, *, stream/xref) wrapping insert_image (fitz seam)
│   ├── pipeline.py         # hook place_logo into the per-region loop AFTER remove_region (same pdf_rect)
│   └── logo.py             # ★ NEW (fitz-free): load+validate manifest, list_logos(), resolve(logo_id)→bytes
├── models.py               # extend JobSpec with optional logo_id (validated)
├── storage.py              # ADD logos_dir()/manifest path helpers (fixed read-only location)
└── config.py               # ADD LOGOS_DIR path (+ optional MAX_LOGO_BYTES guard)
logos/                      # ★ NEW fixed read-only asset dir
├── manifest.json           # [{ id, file, name, (optional) native_w/native_h/tags }]
└── *.png                   # transparent company logos (admin-placed; v1 may seed a placeholder)
web/
├── index.html              # ADD a logo-picker section inside aside#side-panel (above/below region list)
├── js/api.js               # ADD listLogos(); add logo_id to the /process body
└── js/logos.js (or extend regions.js) # ★ thumbnail grid, selection state, logo-change ⇒ result stale
web/styles/app.css          # ADD thumbnail-grid styles using EXISTING tokens (no new token file)
tests/
└── test_logo.py (+ test_process_api additions) # ★ LOGO-01/02 + path-traversal + bbox/aspect assertions
```

### Pattern 1: Insert AFTER redaction, on the SAME rect, in the SAME pass

**What:** In `pipeline.process_job`'s per-region loop, the current body is:
```python
pdf_rect = coords.pixels_to_pdf_rect(clamped_px, effective_dpi, page)
removed = redact.remove_region(page, pdf_rect)
```
Phase 3 adds the logo insertion **immediately after** `remove_region`, on the **same `pdf_rect`**:
```python
removed = redact.remove_region(page, pdf_rect)
if logo_bytes is not None:
    logo_xref = pdf_engine.place_logo(page, pdf_rect, stream=logo_bytes, xref=logo_xref)
```

**When to use:** Every region, only when a `logo_id` was supplied (D-01: one global logo across all regions; no `logo_id` ⇒ pure removal, Phase 2 behavior preserved).

**Why ordering is mandatory (CONFIRMED):** `redact.remove_region` calls `page.apply_redactions(...)` internally. `apply_redactions` rewrites the page content stream and removes pending redaction annotations. If you `insert_image` *before* `apply_redactions`, the just-inserted logo image overlaps the redaction rect and would itself be redacted/blanked by the same apply pass. Inserting *after* `apply_redactions` (i.e. after `remove_region` returns) means the logo is painted onto the cleaned page and survives. `[CITED: pymupdf.readthedocs.io/en/latest/page.html — apply_redactions removes content + pending annots; insert_image with overlay=True paints on top]` `[VERIFIED: redact.remove_region calls pdf_engine.apply_redactions and returns after it — app/services/redact.py:117]`

**Note on `remove_region` returning `False`:** when a region had nothing removable, `remove_region` returns `False` (not an error). D-01/D-02 still call for the logo to be placed in that rect (the user framed it as a replacement target). **Place the logo regardless of the `removed` flag** when a `logo_id` is set — the flag controls the "沒有可移除的內容" *notice*, not whether the logo goes in. `[ASSUMED]` — see Assumptions Log A1.

### Pattern 2: Embed once, reuse `xref` across all regions

**What:** `Page.insert_image` returns the `xref` of the embedded image object. For the second and subsequent regions (same global logo, D-01), pass `xref=<that value>` and omit `stream=` so PyMuPDF references the already-embedded object instead of re-embedding the PNG.

**Live-verified:** inserting the same bytes via the returned `xref=` on a second page returned the **same xref (5)** with no new image object — confirming dedup works (§Code Examples).

**Why:** Pitfall 7 / Performance Trap — re-embedding the logo per placement grows the file linearly with the number of regions. With one global logo across potentially many regions/pages (D-01), dedup matters. `[CITED: pymupdf.readthedocs.io/en/latest/page.html#Page.insert_image — "xref (int) ... reuse ... avoids storing same image multiple times"]` `[VERIFIED: live test, xref reused]`

### Pattern 3: `logo_id` → bytes through a manifest ALLOWLIST (never a path)

**What:** `logo.py` loads `manifest.json` once into a dict keyed by `id`. `resolve(logo_id)` looks `logo_id` up in that dict; a hit yields the manifest entry whose `file` field (a known, admin-controlled basename) is joined to `LOGOS_DIR`; a miss raises a typed error the API maps to 404. The untrusted `logo_id` is **only ever a dict key**, never a path component.

**When to use:** Every `logo_id` resolution (in `process_job` and anywhere a logo is fetched).

**Why:** This is the identical defense the codebase already uses for `session_id` (`storage.validate_session_id` allowlist regex + `subdir` containment assert, T-01-04) and the client filename (`sanitize_filename`, never used as a path). A `logo_id` like `../../etc/passwd` or `..\\config.py` can never escape because it is not in the manifest dict and even a matching key resolves to a fixed admin-controlled basename. Defense-in-depth: also `resolve()` the final path and assert `is_relative_to(LOGOS_DIR)` (mirrors `subdir`). `[VERIFIED: app/storage.py:48-89 — validate_session_id + subdir containment]`

### Anti-Patterns to Avoid
- **Building the logo path from `logo_id` directly** (`LOGOS_DIR / logo_id` or `LOGOS_DIR / f"{logo_id}.png"`): path traversal sink. Resolve through the manifest dict only.
- **Inserting the logo before `apply_redactions`** (i.e. before/inside `remove_region`): the logo gets redacted away. Insert after.
- **`keep_proportion=False`**: stretches/distorts the logo to fill a mismatched rect — violates LOGO-02. Keep the default `True`.
- **`overlay=False`**: paints the image *under* existing content; on a freshly-redacted (background) area it may look fine but is semantically wrong and fragile. Keep the default `overlay=True` (logo on top).
- **A bare `draw_rect`/white cover instead of redaction** (Phase 2 concern, restated): never reintroduce a cover; the logo goes on top of *truly removed* content.
- **`logos.js` (or any web module) fetching `logos/` or building server URLs itself**: breaks the embedding seam. Go through `api.js` (Pattern 4).
- **Reading `manifest.json` from the frontend**: the catalog comes from `GET /logos`, not a static file read, so the path stays configurable for embedding.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fit logo into rect preserving aspect, centered | Manual scale math + offset computation to center within the rect | `insert_image(rect, keep_proportion=True)` (default) | PyMuPDF does contain+center natively — **live-verified** a 2:1 logo → centered 100×50 in a 100×100 rect. Hand-rolled scale/center math is error-prone and unnecessary. |
| Verify the placed logo's position/aspect (LOGO-02 test) | Re-derive expected pixel bbox by hand | `Page.get_image_rects(xref)` | Returns the actual placed bbox(es); assert ⊆ target rect and aspect ≈ source. This is the authoritative placement record. |
| Avoid file bloat from repeated logo | Custom image-object caching/dedup in the PDF | `insert_image(..., xref=<returned xref>)` | PyMuPDF dedups via xref reuse — verified. |
| `logo_id` → file safely | Ad-hoc string sanitizing or path joins | Manifest-dict allowlist + `is_relative_to(LOGOS_DIR)` assert (mirror `validate_session_id`/`subdir`) | The proven T-01-04 pattern already lives in `storage.py`. Reuse it; don't invent a new sanitizer. |
| Confirm a library file is a real PNG with alpha | Parse PNG headers by hand | `PIL.Image.open(...).verify()` / inspect `.mode` (`RGBA`/`LA`/`P+transparency`) | Pillow is already a dependency; it's the standard safe decoder. |
| Render the result-with-logo for preview | A new "render with logo" code path | The existing `/result/.../image` (renders the work copy) | The work copy already contains the inserted logo after `process_job` (D-06). Zero new code. |

**Key insight:** Almost every "logo placement" sub-problem is already solved — by a PyMuPDF default (`keep_proportion`), a PyMuPDF return value (`xref`, `get_image_rects`), an existing codebase pattern (the `session_id` allowlist), or an existing endpoint (`/result/.../image`). Phase 3's net-new code is small: one fitz wrapper, one fitz-free service, one model field, one GET route, one frontend picker.

## Runtime State Inventory

> Phase 3 is greenfield-additive (new files + additive edits), not a rename/migration. This section is included only to record the **new fixed asset** the phase introduces and its deployment implication.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore; sessions are filesystem dirs and Phase 3 adds no per-session persisted state. The logo library is fixed shared assets, not user data. | None — verified: no DB in v1 (CLAUDE.md "What NOT to Use: A database in v1"). |
| Live service config | None — no external services configured. | None. |
| OS-registered state | None. | None. |
| Secrets/env vars | A new optional env var `LOGOS_DIR` (path to the library) follows the `DATA_DIR` pattern in `config.py`. No secret. | Document the new env var; default to a repo-relative `./logos`. |
| Build artifacts / new fixed assets | **NEW: `logos/` directory + `manifest.json` + `*.png`** must exist at deploy time. In Docker (CLAUDE.md deploy notes) this is "a separate read-only volume/baked-in dir for the fixed logo library". | Deployment must bake-in or mount `logos/`. v1 may seed a placeholder logo so the picker is non-empty. Flag for the deploy phase (Phase 5). |

**The canonical question (adapted):** After the code change, what must exist on the target machine that the repo alone doesn't guarantee? → **The `logos/` library content.** The code reads `manifest.json`; if it's absent or empty, `GET /logos` should return an empty list gracefully (picker shows an empty state) rather than 500. Document the admin "place files in `logos/`" step.

## Common Pitfalls

### Pitfall 1: Logo gets redacted because it was inserted before `apply_redactions`
**What goes wrong:** The logo is placed, then `apply_redactions` blanks/removes it (or part of it) because the redaction annotation for that rect is still pending.
**Why it happens:** Inserting inside or before the removal step. `remove_region` *is* the apply step.
**How to avoid:** Insert strictly **after** `redact.remove_region(page, pdf_rect)` returns (Pattern 1). The order in the loop is: map rect → remove → place.
**Warning signs:** Logo missing or clipped in the output; appears only on regions where nothing was removed.

### Pitfall 2: PNG transparency shows a white/opaque box over the cleaned area
**What goes wrong:** A logo that should be transparent paints an opaque rectangle, defeating the clean replacement.
**Why it happens:** The PNG is flattened (no alpha), or alpha isn't carried. (Pitfall 7 in PITFALLS.md.)
**How to avoid:** Library logos are transparent PNGs (D-03). For a PNG that carries its own alpha channel (color type 6 RGBA / type 4 LA / palette+tRNS), `insert_image(stream=png_bytes)` honors it **without** a separate `mask=` argument — **live-verified** with an RGBA PNG. Validate at library load (Pillow: assert `mode in {"RGBA","LA"}` or palette has transparency) and flag opaque logos so an admin notices. Verify rendering over a **colored** background, not just white.
**Warning signs:** White box behind a logo on a colored page.

### Pitfall 3: `logo_id` used to build a path (traversal)
**What goes wrong:** An attacker (or a typo) supplies `logo_id="../../app/config.py"`; if the code does `LOGOS_DIR / logo_id` it reads outside the library.
**Why it happens:** Treating the id as a filename.
**How to avoid:** Manifest-dict allowlist + containment assert (Pattern 3 / §Security). Unknown id → 404 `logo_not_found`, indistinguishable from a missing logo (no oracle), exactly like the `session_not_found` pattern.
**Warning signs:** Any `Path` constructed from `logo_id`; any 500 on a crafted id.

### Pitfall 4: File bloat from re-embedding the logo per region
**What goes wrong:** Output PDF grows by one embedded PNG per region across all pages.
**Why it happens:** Calling `insert_image(stream=...)` for every region instead of reusing the xref.
**How to avoid:** Embed once (first region), reuse the returned `xref=` thereafter (Pattern 2). `save_doc` already uses `garbage=4, deflate=True, clean=True`, which further compacts.
**Warning signs:** Output size scales with region count.

### Pitfall 5: Stale result not invalidated when the logo changes
**What goes wrong:** User applies (remove+logo A), sees the result, switches to logo B, downloads — and gets logo A because the result wasn't marked stale.
**Why it happens:** The logo selection isn't wired into the existing stale machinery.
**How to avoid:** Treat a logo selection/change as a job-input change: call the same `onRegionsEdited()`-style invalidation that region edits use (`resultFresh = false`, demote to 重新套用, show 框選已變更/equivalent stale notice). `[VERIFIED: regions.js:440 onRegionsEdited + updateActionGroup state machine]`
**Warning signs:** Downloaded PDF shows a different logo than the preview.

### Pitfall 6: Oversized/malicious PNG in the library (decompression / alpha bomb / huge dimensions)
**What goes wrong:** A crafted PNG with enormous decompressed dimensions inflates memory when decoded/embedded.
**Why it happens:** The library is admin-placed, but defense-in-depth still applies (and a future upload path would need it).
**How to avoid:** At library load, cap file size (`MAX_LOGO_BYTES`) and decoded dimensions via Pillow before use; Pillow already guards against the classic decompression bomb (`Image.MAX_IMAGE_PIXELS` raises `DecompressionBombError`). Reject + skip a bad asset (it just doesn't appear in the picker) rather than crashing `GET /logos`.
**Warning signs:** Memory spike on `GET /logos` or on `/process` with a particular logo.

## Code Examples

Verified against the installed PyMuPDF 1.27.2.3 this session.

### `place_logo` wrapper (goes in `pdf_engine.py` — the fitz seam)
```python
# Source: pymupdf.readthedocs.io/en/latest/page.html#Page.insert_image  [CITED]
# Verified signature (installed 1.27.2.3):
#   insert_image(page, rect, *, alpha=-1, filename=None, height=0, keep_proportion=True,
#                mask=None, oc=0, overlay=True, pixmap=None, rotate=0, stream=None,
#                width=0, xref=0)
def place_logo(page, rect, *, stream: bytes | None = None, xref: int = 0) -> int:
    """Place a logo into ``rect`` (the SAME unrotated-page Rect the removal used), centered and
    aspect-preserved (D-02 / LOGO-02). MUST be called AFTER apply_redactions (after
    redact.remove_region) so the logo is not itself redacted.

    First placement: pass ``stream=<png bytes>`` (validated by logo.py). Returns the embedded
    image ``xref``. Subsequent placements of the SAME logo: pass ``xref=<that value>`` (omit
    stream) to reuse the embedded object and avoid file bloat (Pitfall 4 / verified dedup).
    keep_proportion=True and overlay=True are the verified defaults — pass explicitly for clarity.
    """
    return page.insert_image(
        rect,
        stream=stream,
        xref=xref,
        keep_proportion=True,   # contain + center (LOGO-02) — verified
        overlay=True,           # paint ON TOP of the cleaned content — verified default
    )
```

### Live-verified contain + center + bbox (the behavior LOGO-02 relies on)
```python
# Source: this research session, .venv PyMuPDF 1.27.2.3  [VERIFIED]
target = fitz.Rect(50, 100, 150, 200)        # 100 x 100 (square)
xref = page.insert_image(target, stream=rgba_png_2x1, keep_proportion=True)  # logo aspect 2:1
rects = page.get_image_rects(xref)
# → [(50.0, 125.0, 150.0, 175.0)]
#   placed 100 x 50, aspect 2.0 (== source), center (100,150) == target center,
#   bbox fully contained in target.  ← contain + center + aspect-preserve all confirmed.
```

### `pipeline.process_job` integration (the per-region loop — additive lines marked ►)
```python
# Existing loop (app/services/pipeline.py:143-179), with logo insertion hooked in.
logo_bytes = logo.resolve(job_spec.logo_id) if getattr(job_spec, "logo_id", None) else None  # ►
logo_xref = 0                                                                                  # ►
for region in job_spec.regions:
    ...                                       # page bounds check, effective_dpi, clamp (unchanged)
    pdf_rect = coords.pixels_to_pdf_rect(clamped_px, effective_dpi, page)
    removed = redact.remove_region(page, pdf_rect)
    if logo_bytes is not None:                                                                 # ►
        # Insert AFTER removal, on the SAME rect; reuse xref after the first embed.            # ►
        logo_xref = pdf_engine.place_logo(                                                     # ►
            page, pdf_rect,                                                                    # ►
            stream=(logo_bytes if logo_xref == 0 else None),                                   # ►
            xref=logo_xref,                                                                    # ►
        )                                                                                      # ►
    results.append({"page": page_no, "removed": removed, "clamped": was_clamped})
# save → outputs/原名_logoswap.pdf + work copy (unchanged; garbage=4/deflate/clean compacts).
```
Note: `logo.resolve` raising for a bad id should surface as a typed error mapped to 404/422 by `main.py` (mirror `RedactError`/`PipelineError` handlers), never a 500.

### `JobSpec` extension (`app/models.py`)
```python
class JobSpec(BaseModel):
    dpi: int = Field(..., ge=config.MIN_DPI, le=config.MAX_DPI)
    regions: List[RegionMark] = Field(default_factory=list)
    logo_id: str | None = Field(default=None, description="optional global logo id (D-01)")  # ►
    # No length/charset validator needed for safety (resolution is a manifest-dict lookup),
    # but a light Field(max_length=...) is cheap defense-in-depth against absurd inputs.
```

### `GET /logos` (new `app/api/logos.py`, mirrors `process.py` structure)
```python
@router.get("/logos")
async def list_logos() -> dict:
    """List the fixed logo library for the picker (LOGO-01). Reads manifest.json via logo.py;
    returns {"logos": [{id, name, (optional) native_w/native_h/tags, thumb_url?}]}.
    Never exposes filesystem paths; an absent/empty library yields {"logos": []} (picker shows
    an empty state), not a 500."""
    return {"logos": logo.list_logos()}
```

### Frontend seam additions (`web/js/api.js`)
```javascript
/** List the fixed logo library: { logos: [{ id, name, ... }] }. */
export async function listLogos() {
  const response = await fetch(API_BASE + "/logos");
  if (!response.ok) throw await toApiError(response);
  return response.json();
}
// processJob() already exists — the caller just includes logo_id in jobSpec:
//   api.processJob(sid, { dpi, regions: getJobRegions(), logo_id: selectedLogoId || null });
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Cover logo with opaque image / white rect | True removal (Phase 2) + `insert_image` overlay on top | Established in Phase 2 | Phase 3 places the logo on *truly removed* content — the brand-correct, non-recoverable result. |
| `keep_proportion` uncertainty | Confirmed default `True` in 1.27.x, contains+centers | Verified this session | LOGO-02 needs no custom math. |

**Deprecated/outdated:**
- `pip install fitz` (the unrelated PyPI package) — never; PyMuPDF provides the `fitz` module. (CLAUDE.md.)
- SVG logos via `insert_image` — not supported directly; deferred (D-03).

## Assumptions Log

> Claims tagged `[ASSUMED]` that the planner / discuss-phase should confirm.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | When `logo_id` is set, the logo is placed in **every** region's rect regardless of whether `remove_region` returned `removed=False` (nothing-removable region). D-01/D-02 say "all removed regions get the logo"; the natural reading is "every region the user framed." | Pattern 1 | If the intended behavior is "only place where content was actually removed," a framed-but-empty region would wrongly get a logo. Low risk (user framed it as a target), but worth a one-line confirmation. Cheap to change (gate on `removed`). |
| A2 | An absent or empty `logos/`/`manifest.json` should yield `GET /logos → {"logos": []}` and a picker empty-state, not an error; with no logo selectable the flow degrades to pure removal (Phase 2). | §Code Examples, §Runtime State | If the team wants a hard "library required" failure instead, the empty-state behavior differs. Discretion item per CONTEXT ("未選 logo 時的行為"). |
| A3 | The logo picker lives as a **new section within the existing `aside#side-panel`** alongside the region list (the UI-SPEC reserved this column for "Phase 3's logo picker"). Exact placement (above/below the region list, or a tab) is Claude's discretion. | §Architecture, §Validation | Layout-only; no functional risk. Confirmed-compatible with the reserved-column contract. |

## Open Questions

1. **Thumbnail source for the grid (D-05)**
   - What we know: the picker is a thumbnail grid; logos are PNGs in `logos/`.
   - What's unclear: whether thumbnails are (a) the full PNG served via a `GET /logos/{id}/thumb` (or static) and CSS-scaled, or (b) pre-generated. For a small fixed library, serving the full PNG and CSS-scaling is simplest.
   - Recommendation: serve the logo image via a dedicated `GET /logos/{id}/image` endpoint (same allowlist resolution) and CSS-scale into the grid; defer pre-generated thumbnails unless the library grows large. Keep the seam in `api.js` (a `logoImageURL(id)` builder, like `pageImageURL`).

2. **Manifest schema exactness (Claude's discretion)**
   - What we know: each entry needs at least `id`, `file`, display `name`; optional size/variant tags.
   - Recommendation: `{ "id": "acme-horizontal", "file": "acme-horizontal.png", "name": "ACME 橫式", "native_w": 0, "native_h": 0, "tags": [] }`. Validate `id` is unique and matches a safe charset; `file` is a bare basename that exists and is a valid PNG (Pillow).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PyMuPDF (`fitz`) | logo insertion + placement verification | ✓ | 1.27.2.3 (`.venv`) | — |
| Pillow (`PIL`) | PNG validation at library load | ✓ | 12.2.0 | — |
| FastAPI / Pydantic v2 / Uvicorn | `/logos` route + `JobSpec` field | ✓ | per requirements.txt | — |
| `logos/` library content | LOGO-01 (something to pick) | ✗ (not yet created) | — | v1 may seed a placeholder PNG so the picker is non-empty; absent library → empty picker (graceful, A2) |
| pytest / httpx | LOGO-01/02 tests | ✓ | per requirements.txt | — |

**Missing dependencies with no fallback:** None — all runtime libs are installed.

**Missing dependencies with fallback:** The `logos/` library is content, not a tool. The phase *creates* it (a plan deliverable) and should seed at least one placeholder logo so the picker and tests have a real asset; deployment (Phase 5) bakes-in/mounts it.

## Validation Architecture

> `workflow.nyquist_validation` is `false` in config.json, so the full Nyquist sampling apparatus is NOT mandated. This section is included because the phase brief explicitly requests an automated proof for LOGO-02, and a `tests/` suite already exists (140 backend tests). It documents the targeted tests the plan should add — consistent with the project's per-phase quality gate (MEMORY: review/fix + validate + secure at every phase boundary).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ httpx `TestClient`) — installed |
| Config file | none dedicated; tests under `tests/`, fixtures in `tests/conftest.py` (DATA_DIR redirected to tmp; in-memory PDFs built via fitz) |
| Quick run command | `.venv/Scripts/python.exe -m pytest tests/test_logo.py -x` |
| Full suite command | `.venv/Scripts/python.exe -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOGO-02 | Inserted logo bbox lies within the target rect AND aspect ≈ source within tolerance | unit | `pytest tests/test_logo.py::test_inserted_logo_bbox_within_rect_and_aspect_preserved -x` | ❌ Wave 0 |
| LOGO-02 | Logo inserted AFTER redaction survives (region has the image; text/vector still removed) | unit | `pytest tests/test_logo.py::test_logo_survives_redaction -x` | ❌ Wave 0 |
| LOGO-02 | One global logo across N regions reuses a single xref (no per-region re-embed) | unit | `pytest tests/test_logo.py::test_global_logo_single_xref -x` | ❌ Wave 0 |
| LOGO-01 | `GET /logos` lists the manifest entries (id+name), no filesystem paths leaked | api | `pytest tests/test_logo.py::test_list_logos -x` | ❌ Wave 0 |
| LOGO-01 (sec) | Untrusted `logo_id` (`../`, unknown) → 404, never a path read or 500 | api | `pytest tests/test_logo.py::test_logo_id_path_traversal_rejected -x` | ❌ Wave 0 |
| D-01 | No `logo_id` ⇒ pure removal, identical to Phase 2 (no image inserted) | api | `pytest tests/test_process_api.py::test_process_without_logo_is_pure_removal -x` | ❌ Wave 0 (add) |
| D-05 | Original SHA-256 unchanged across a remove+insert run | api | (extend existing deferred-mutation assertion in `test_process_api.py`) | ✅ pattern exists |
| AGPL seam | `import fitz` still only in `pdf_engine.py` after `place_logo` added | static | (extend existing grep test in `test_redact.py`) | ✅ pattern exists |

**How to assert LOGO-02 (concrete):** after `process_job` with a `logo_id`, open the exported PDF, get the page, recompute the target `pdf_rect` via `coords.pixels_to_pdf_rect` (same as `test_process_api._exported_region_empty` does for emptiness), then:
```python
xrefs = page.get_images()                       # the embedded logo is present
placed = page.get_image_rects(<logo xref>)      # actual bbox(es)
for r in placed:
    assert target.x0-TOL <= r.x0 and r.y0 >= target.y0-TOL \
       and r.x1 <= target.x1+TOL and r.y1 <= target.y1+TOL     # contained (D-02)
    assert abs((r.width/r.height) - source_aspect) < ASPECT_TOL  # aspect preserved (LOGO-02)
```
This mirrors the existing `_exported_region_empty` helper and the conftest geometry (200×300pt page, region pts `(10,40,190,120)`).

### Sampling Rate
- **Per task commit:** `pytest tests/test_logo.py -x` (the new logo tests).
- **Per wave merge:** `pytest -q` (full suite — 140 existing + new must stay green).
- **Phase gate:** Full suite green before `/gsd-verify-work`; plus the per-phase manual visual check that the logo renders transparently over a colored page (Pitfall 2) and the 原圖/移除+置入結果 toggle shows the logo (D-06).

### Wave 0 Gaps
- [ ] `tests/test_logo.py` — LOGO-01 (`/logos` list + path-traversal rejection) and LOGO-02 (bbox-within-rect + aspect + survives-redaction + single-xref).
- [ ] A real transparent-PNG fixture: build an RGBA PNG in-memory in `conftest.py` (the technique in this research — stdlib `struct`+`zlib`, no binary committed — or via Pillow `Image.new("RGBA", ...)`), exposed as a fixture like `logo_png_bytes`.
- [ ] A tmp logo library fixture: write `manifest.json` + the PNG into a tmp `LOGOS_DIR` (monkeypatch `config.LOGOS_DIR`), mirroring the `isolated_data_dir` autouse fixture.
- [ ] Extend `test_process_api.py`: no-logo path = pure removal (D-01); extend the existing original-SHA-256 assertion to cover a remove+insert run (D-05).

*(Framework already present — no install needed.)*

## Security Domain

> `security_enforcement` is not set to `false` in config.json (absent ⇒ enabled). The phase brief explicitly requests a threat list for the planner's `<threat_model>`. The codebase already uses a stable `T-0X-NN` threat-id scheme; new Phase-3 threats are numbered `T-03-NN` and existing ones referenced by their original ids.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | v1 is internal LAN, no login (out of scope, locked). |
| V3 Session Management | partial | Session ids are unguessable `secrets.token_urlsafe` tokens (existing T-01-07); Phase 3 adds no new session state. |
| V4 Access Control / path safety | **yes** | **`logo_id` → file via manifest allowlist + `is_relative_to(LOGOS_DIR)` assert** — the existing `validate_session_id`/`subdir` pattern (T-01-04). The library is read-only (no write path from user input). |
| V5 Input Validation | **yes** | Pydantic validates `JobSpec.logo_id` (type/optional/length). Untrusted display text rendered via `textContent` only (T-02-11). PNG assets validated by Pillow at load (decompression-bomb guard). |
| V6 Cryptography | no | No crypto introduced. |
| V12 Files & Resources | **yes** | `MAX_LOGO_BYTES` + Pillow dimension cap on library assets; `GET /logos` degrades gracefully on a bad/absent asset (no 500); CPU-bound work stays in `run_in_threadpool`; output compacted (`garbage=4`). |

### Known Threat Patterns for {FastAPI + PyMuPDF + fixed asset library}

| Threat ID | Pattern | STRIDE | Standard Mitigation |
|-----------|---------|--------|---------------------|
| **T-03-01** | Untrusted `logo_id` used to build a path → traversal / arbitrary file read | Tampering / Info Disclosure | Resolve via manifest **dict allowlist** only; unknown id → 404 `logo_not_found` (no oracle); defense-in-depth `Path(...).resolve().is_relative_to(LOGOS_DIR)`. Mirrors T-01-04. |
| **T-03-02** | Malicious/oversized PNG in the library (decompression bomb, huge dimensions, alpha bomb) → memory exhaustion / DoS | Denial of Service | `MAX_LOGO_BYTES` cap + Pillow decode/dimension validation at load (Pillow raises `DecompressionBombError`); skip+log a bad asset rather than crash `/logos`. |
| **T-03-03** | Crafted PNG triggers a parser crash in the image decode path → worker down | Denial of Service | Wrap library load/decode in typed try/except → structured error, never a bare 500 (mirrors `PdfEngineError` handling, T-01-03). Keep PyMuPDF/Pillow patched. |
| **T-03-04** | Logo `name`/manifest text reflected into the picker as HTML → XSS | Tampering (stored) | Frontend writes all logo text via `textContent`/`createElement`, never `innerHTML` (existing T-02-11 discipline). |
| **T-03-05** | Logo image object re-embedded per region → output bloat (resource) | Denial of Service (mild) | Reuse `xref=` across regions (Pattern 2); `save_doc` compacts with `garbage=4,deflate=True,clean=True`. |
| (carried) **T-02-04** | Unbounded regions in a job drives unbounded insert passes | Denial of Service | Existing `MAX_REGIONS=200` cap on `JobSpec.regions` already bounds the loop the logo insertion runs inside. |
| (carried) **T-02-05 / D-05** | Mutating the original instead of the work copy | Tampering | `process_job` resets+edits only the work copy; original is chmod 0o444 and its SHA-256 is asserted unchanged. Logo insertion is on the same work copy. |
| (carried) **T-02-08** | A logo-resolution/insertion failure escaping as a 500 leaking internals | Info Disclosure | Add `LogoError`-style typed error mapped in `main.py` (mirror `RedactError`/`PipelineError`), → structured 4xx. |
| (carried) **T-02-03 / AGPL** | `import fitz` leaking out of `pdf_engine.py` | (licensing/architecture) | `place_logo` is the only new fitz call and lives in `pdf_engine.py`; `logo.py`/`pipeline.py` stay fitz-free; existing grep test enforces it. |

## Sources

### Primary (HIGH confidence)
- **Installed PyMuPDF 1.27.2.3** — live verification this session: `insert_image` signature (`keep_proportion=True`, `overlay=True`, `xref` defaults), contain+center behavior, `get_image_rects` placed bbox, `xref=` dedup, RGBA-PNG alpha honored without `mask=`. `[VERIFIED]`
- **Installed Pillow 12.2.0** — `python -c "import PIL; print(PIL.__version__)"`. `[VERIFIED]`
- **PyMuPDF official docs — `Page.insert_image` / `apply_redactions` / `get_image_rects`**: https://pymupdf.readthedocs.io/en/latest/page.html `[CITED]` (keep_proportion semantics, overlay, xref reuse, apply-then-insert ordering).
- **Built Phase-1/2 codebase** (read directly this session): `app/services/pipeline.py` (per-region loop + `pdf_rect`), `app/services/pdf_engine.py` (fitz seam + redaction wrappers), `app/services/redact.py` (`remove_region` calls `apply_redactions`), `app/services/coords.py` (mapper), `app/storage.py` (`validate_session_id`/`subdir` allowlist — the T-01-04 pattern to mirror), `app/api/process.py`, `app/models.py` (`JobSpec`), `app/main.py` (typed-error→4xx handlers), `web/js/api.js`/`regions.js`/`viewer.js`/`index.html` (the seam, stale machinery, side-panel), `tests/conftest.py`/`test_process_api.py`/`test_redact.py` (test patterns). `[VERIFIED]`

### Secondary (MEDIUM confidence)
- **Project research** `.planning/research/STACK.md`, `ARCHITECTURE.md`, `PITFALLS.md` — `insert_image(keep_proportion=True)` after redaction, Pitfall 7 (logo scale/aspect/alpha/colorspace + per-placement bloat), AGPL isolation, logo-library design (`logos/` + `manifest.json`). Cross-consistent with the live verification.
- **CLAUDE.md** Technology Stack section — PyMuPDF/Pillow versions, fitz-isolation, deploy notes (read-only logo volume).

### Tertiary (LOW confidence)
- None requiring validation — the load-bearing claims were promoted to HIGH by live verification.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against the actual `.venv`; no new deps.
- `insert_image` behavior (contain/center/aspect/xref/alpha): HIGH — live-verified, not assumed.
- Pipeline integration point + ordering: HIGH — read the exact loop and confirmed `remove_region` wraps `apply_redactions`.
- Logo-id safety pattern: HIGH — the proven `validate_session_id`/`subdir` pattern is in the codebase.
- Frontend integration: HIGH — read `api.js`/`regions.js`/`index.html`; stale machinery and reserved side-panel column confirmed.
- Manifest schema / picker layout / empty-library behavior: MEDIUM — Claude's-discretion items (recommendations given; A1–A3 flagged for confirmation).

**Research date:** 2026-05-22
**Valid until:** ~2026-06-21 (stable; pinned deps, internal tool). Re-verify only if PyMuPDF crosses a minor version or the Phase-2 pipeline shape changes.
