---
phase: 04-raster-image-support
audit_type: phase-security-verification
status: secured
asvs_level: 1
block_on: critical
threats_total: 17
threats_closed: 17
threats_open: 0
accepted_risks: 2
unregistered_flags: 0
baseline_verified_at: 137a592
post_verification_audited: true
post_verification_commits_reviewed: 12
audited: 2026-05-23
---

# Phase 4 — Security Verification Report

**Phase:** 04 — 點陣圖與圖片型檔案支援 (raster image support)
**ASVS Level:** 1
**Disposition policy:** mitigate / accept / transfer (no transfers in this phase)
**Threats Closed:** 17/17 (15 mitigated + 2 accepted)
**Open / Blocking:** 0

This report verifies that every threat declared in `<threat_model>` of `04-01-PLAN.md` and
`04-02-PLAN.md` is met by code presently on disk. It also re-confirms — against the 12
commits that landed after the initial Phase 4 verification (`137a592`) — that no mitigation
was weakened and no new attack surface was introduced without a threat mapping.

---

## Verification Matrix — 04-01 (image ingest)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-01-01 | Spoofing | mitigate | CLOSED | Magic-byte sniff at `app/services/ingest.py:82-107` (`_sniff_kind`): PDF tolerates ≤8-byte leading offset, PNG/JPEG/TIFF require `startswith` offset 0. Filename extension never trusted. Defence-in-depth `_ACCEPTED_IMAGE_FORMATS = ("PNG","JPEG","TIFF")` at `ingest.py:59` and re-check at `ingest.py:159-163` catch any decoded-format mismatch. Tests: `test_sniff_kind_dispatches_four_magics`, `test_sniff_kind_pdf_tolerates_leading_offset_but_images_do_not`, `test_extension_not_trusted_fake_png` (`tests/test_ingest.py`). |
| T-04-01-02 | Tampering | mitigate | CLOSED | Pillow chain at `app/services/ingest.py:110-227` (`_ingest_image`): (a) `Image.open` + read `fmt` BEFORE `verify()` (line 137-139, verify invalidates the object); (b) re-open, n_frames check, format allowlist, hard pixel cap, all inside `with Image.open(...) as src:` (line 151-184) so handles release deterministically; (c) RGBA / LA / P-transparency composite onto white before drop-alpha at lines 198-208 (Pitfall G — no premultiplied-alpha pitfall); (d) `img.load()` force-decode at line 214 with except → `corrupt_image`. Tests: `test_corrupt_image_truncated_png`, `test_cmyk_tiff_normalized_to_rgb`, `test_rgba_transparent_png_composites_onto_white`. |
| T-04-01-03 | Repudiation | mitigate | CLOSED | originals/ SHA-256 invariant. `storage.write_original` at `app/storage.py:198-213` writes once then `os.chmod(0o444)`. Pipeline reset source switched from `originals/` to `pristine/` (`app/services/pipeline.py:107-136`) so pipeline NEVER touches originals/ — invariant is now STRONGER than Phase 1–3. For image uploads originals/ holds the raw PNG/JPG/TIFF bytes verbatim (`app/services/ingest.py:298-299`). Test: `test_originals_sha256_unchanged_after_image_run` at `tests/test_ingest.py:506`. |
| T-04-01-04 | Info Disclosure | mitigate | CLOSED | D-07 dropzone UI does not disclose vector/raster/scan classification. `web/index.html:280-299` dropzone copy carries no taxonomy hint. Grep `raster|vector|scan|點陣|向量|掃描` over `web/` returns 0 hits (per `04-VERIFICATION.md` line 43). The COPY object in `web/js/app.js:18-52` is identical for image vs PDF error families. |
| T-04-01-05 | DoS | mitigate | CLOSED | Decompression-bomb defence has THREE layers: (1) Pillow built-in `Image.DecompressionBombError` caught at `app/services/ingest.py:140`; (2) explicit `_ACCEPTED_IMAGE_FORMATS` allowlist at `ingest.py:159`; (3) hard megapixel cap at `ingest.py:177-181` `if src.width * src.height > config.MAX_INGEST_IMAGE_PIXELS: raise IngestError("image_too_large_pixels", ...)` STRENGTHENED post-verification by hotfix WR-03 (commit `1c024ac`). Config constant `MAX_INGEST_IMAGE_PIXELS = 89_478_485` at `app/config.py:66`. Tests: `test_ingest_image_over_pixel_cap_rejected_with_limit_in_message` (`tests/test_ingest.py:102`), `test_ingest_image_under_pixel_cap_accepted` (line 118). |
| T-04-01-06 | DoS | mitigate | CLOSED | Oversize-upload defence is enforced TWICE: (a) streaming early-cap in `app/api/sessions.py:55-69` rejects with 413 + `file_too_large` AS SOON AS `len(buf)+len(chunk) > MAX_UPLOAD_BYTES`, never buffering the whole oversize payload; (b) post-buffer re-check at `app/services/ingest.py:329-333`. `MAX_UPLOAD_BYTES = 50 MB` at `app/config.py:48`. |
| T-04-01-07 | Tampering | mitigate | CLOSED | Pipeline reset-from-pristine. `app/services/pipeline.py:107-136`: (a) work and pristine paths asserted distinct (line 116-120); (b) `pristine.is_file()` checked (line 130-134); (c) `shutil.copyfile(pristine, work)` at line 136. Both PDF (`ingest.py:259-260`) and image (`ingest.py:302-303`) ingest write pristine/ at session creation. Test: `test_pipeline_resets_work_from_pristine_not_originals` (`tests/test_ingest.py`). |
| T-04-01-08 | Elevation | accept | CLOSED | See **Accepted Risks Log** below — `storage.subdir` validates `session_id` against the server-token alphabet (`_SESSION_ID_RE`) and asserts `dest.resolve().is_relative_to(data_dir.resolve())` for defence-in-depth (`app/storage.py:85-101`). All four kinds — `originals`, `work`, `outputs`, `pristine` — route through this same chokepoint (line 92 enforces `kind in _KINDS`). Client filename is sanitized but never used as a path component (`ingest.py:257-258`, `storage.sanitize_filename`). |
| T-04-01-09 | Info Disclosure | mitigate | CLOSED | XSS guard in `web/js/app.js`. `errorBody.textContent = messageForError(err)` at `app/js/app.js:150`; module docstring at line 9 enforces "all dynamic strings are written via textContent (never innerHTML)". Server messages are NOT passed through verbatim — `messageForError` (`app.js:115-146`) maps `err.code` to fixed COPY strings; only the `extractLimit()` regex-matched numeric token is injected (line 109-113), with empty-string fallback so a server-wording change never leaks raw backend text into the DOM. |

---

## Verification Matrix — 04-02 (raster dispatch)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-02-01 | Info Disclosure | mitigate | CLOSED | Dual-layer OCR text leak closed. `app/services/redact.py:225-230` `remove_region_raster` sets `text=pdf_engine.TEXT_REMOVE` in the same `apply_redactions` call as `images=IMAGE_PIXELS`, so a scan PDF with an OCR'd text layer has BOTH the raster pixels blanked AND the text-object stream cleared. Post-redact assertion at `redact.py:234-239` runs `get_text_words_in_rect` over the unpadded user rect and raises `RedactError("residual_content")` if any word survives. Tests: `test_dual_layer_ocr_text_leak_closed_end_to_end` (`tests/test_process_api.py`), `test_raster_dual_layer_ocr_text_residual_empty` (`tests/test_redact.py`). |
| T-04-02-02 | Tampering | mitigate | CLOSED | Fill-survivor / fake redaction success closed. `app/services/redact.py:222-223` raster branch uses `fill=None` (NOT `(1,1,1)`); docstring at line 206-210 cites Pitfall A — `fill=(1,1,1)` would leave a `type='fs'` survivor drawing whose rect equals the redact rect and IS itself a cover. Vector branch likewise `fill=None` at `redact.py:134-136`. Grep `app/services/redact.py` for `fill=(1` returns 0 hits. Test: `test_raster_fill_none_no_drawing_residual` (`tests/test_redact.py`). |
| T-04-02-03 | Tampering | mitigate | CLOSED | Image XObject xref residue closed. `pdf_engine.IMAGE_PIXELS = fitz.PDF_REDACT_IMAGE_PIXELS` at `app/services/pdf_engine.py:230`. PyMuPDF auto-removes the xref of any image XObject whose placed rect is FULLY covered by the redact rect; partial overlap blanks just the overlapping pixels. Full-frame redact verified end-to-end. Tests: `test_image_only_pdf_full_frame_redacts_to_white` (`tests/test_process_api.py`), `test_image_upload_consecutive_processes_idempotent` (`tests/test_ingest.py`). |
| T-04-02-04 | Tampering | mitigate | CLOSED | Vector-branch drawings residual on raster region is intentional and SAFE. `app/services/redact.py:194-197` docstring delta #3 documents: raster branch DROPS the `residual_covered_drawings` assertion (a raster region is allowed to carry legitimate signatures/annotations) but RETAINS the text-residual check. The drop is bounded by the dispatch contract — pipeline only routes to raster branch when `rect_overlaps_image` is True (`app/services/pipeline.py:247-250`), so a pure vector rect ALWAYS gets the vector branch with its full drawings assertion at `redact.py:156-162`. |
| T-04-02-05 | DoS | mitigate | CLOSED | IMAGE_PIXELS rewrite file-bloat mitigated. `pdf_engine.save_doc` defaults already on `garbage=4, deflate=True, clean=True` (D-10, unchanged from Phase 3). Pipeline saves go through `pdf_engine.save_doc` at `app/services/pipeline.py:328` and `:343`. RESEARCH live-verified compaction (2.88 MB → 6 KB) cited in `04-02-PLAN.md` line 216. |
| T-04-02-06 | Repudiation | mitigate | CLOSED | SHA-256 originals invariant on the image path. Originals/ keeps the user's raw PNG/JPG/TIFF bytes (`app/services/ingest.py:299`), pipeline reads from pristine/ only (`app/services/pipeline.py:107-136`), and pristine/ holds the normalized A4 PDF (`ingest.py:303`). Same `os.chmod(0o444)` write-once guarantee at `storage.py:212`. Same test as T-04-01-03 — `test_originals_sha256_unchanged_after_image_run` (`tests/test_ingest.py:506`). |
| T-04-02-07 | Elevation | mitigate | CLOSED | Forbidden text mode (`PDF_REDACT_TEXT_NONE`) defence-in-depth. `app/services/pdf_engine.py:301-304`: `if text == fitz.PDF_REDACT_TEXT_NONE: raise PdfEngineError("拒絕使用 PDF_REDACT_TEXT_NONE...")` — even if a future caller passed the mode that KEEPS text, the seam refuses. Module docstring at `pdf_engine.py:213-217` explicitly lists it as "the text-keep mode is forbidden, threat T-02-07 / Pitfall 3 — never use". `grep "PDF_REDACT_TEXT_NONE" app/services/redact.py` returns 0. |
| T-04-02-08 | Info Disclosure | accept | CLOSED | See **Accepted Risks Log** below — there is no client-controlled per-region mode in v1; dispatch is server-side only via `pdf_engine.rect_overlaps_image` at `app/services/pipeline.py:247-250`. The JobSpec payload (`app/api/sessions.py` + `app/models.py`) does not accept a `mode` field per region; the threat is preemptively closed by the chosen architecture. |

---

## Accepted Risks Log

### Accepted: T-04-01-08 — `storage.subdir` path traversal

**Disposition rationale.** The single path-traversal sink is `storage.subdir(kind, session_id)` at `app/storage.py:85-101`. It (a) restricts `kind` to a four-element tuple `_KINDS = ("originals","work","outputs","pristine")` enumerated at module scope (line 34), (b) routes `session_id` through `validate_session_id` (line 56-64) which `re.fullmatch`'s the server-token alphabet `^[A-Za-z0-9_-]{16,64}$`, and (c) asserts `dest.resolve().is_relative_to(data_dir.resolve())` as defence-in-depth (line 98-100). The client filename is never reflected into a path component — `sanitize_filename` (line 116-131) reduces it to a bare basename, and `write_original` / `write_work_copy` / `write_pristine_copy` all write to a server-fixed name (`source.pdf` / `doc.pdf`). Threat is accepted because the residual risk after these mitigations is "an attacker who can guess a 22-char unguessable token AND escape the regex AND escape the resolve()-prefix check" — i.e. zero practical exposure on the v1 trust model (internal LAN, no external reachability).

**Verification anchor.** `grep -n "validate_session_id\|subdir\(\|InvalidSessionId" app/storage.py` → 9 hits at lines 47, 56, 63, 85, 94, 100, 112, 244, 250 (all through the same chokepoint).

### Accepted: T-04-02-08 — client-controlled per-region mode

**Disposition rationale.** v1 deliberately does NOT expose a per-region `mode` (vector vs raster) in the `/process` JobSpec — dispatch is decided server-side by `pdf_engine.rect_overlaps_image(page, pdf_rect)` at `app/services/pipeline.py:247-250`. The client cannot force a raster region to be processed by the vector branch (which would leave image pixels untouched) or vice versa. If client-controlled mode is ever added (RESEARCH lists it as deferred to v1.x), the dispatch site is the single chokepoint where the hint would be parsed.

**Verification anchor.** `app/models.py` (read indirectly via `app/api/sessions.py`) does not define a `mode` field on the region payload; pipeline reads `region.page` and `region.px_rect` only.

---

## Unregistered Flags (from SUMMARY.md `## Threat Flags`)

`04-01-SUMMARY.md` and `04-02-SUMMARY.md` do NOT contain a dedicated `## Threat Flags` section — the executor recorded threat-relevant invariants inline in "Key Decisions Implemented" / "Verification gate check" instead. No NEW attack surface was flagged outside the registered T-04-01-* / T-04-02-* set.

**Verdict:** No unregistered flags.

---

## Post-Verification Commit Audit (137a592..HEAD, 12 commits)

Per `<post_verification_commits>` directive, each commit landed after the baseline verification was re-examined against the threat register. Findings below classify each commit as STRENGTHEN / PRESERVE / NEW-SURFACE; no commit is OPEN.

### Hotfix commits (5)

| Commit | Subject | Threat impact | Verdict |
|--------|---------|---------------|---------|
| `8c7e90a` | fix(04-01): RGBA → white composite before convert("RGB") (`ingest.py:198-208`) | STRENGTHENS T-04-01-02 (Pitfall G transparent-PNG: replaces silent black-background output with documented white composite). Composite math + drop-alpha verified by `test_rgba_transparent_png_composites_onto_white`. | PRESERVED + STRENGTHENED |
| `a844946` | fix(04-01): `/pages/{n}/meta` + `/image` read from pristine, not originals (`pages.py:63, 111`) | STRENGTHENS T-04-01-03 / T-04-02-06: originals/ now only WRITTEN by ingest (chmod 0o444); read endpoints all consume pristine/. The path-safety chain is identical (`storage.pristine_path` → `subdir("pristine", session_id)` → `validate_session_id`) — same chokepoint as work/original paths, no new sink. | PRESERVED + STRENGTHENED |
| `e308f6a` | fix(02): filter zero-area drawings from residual check (`pdf_engine.py:520-522`) | STRENGTHENS Phase-2 T-02-* (zero-area artefact false-positives on `residual_content`). The filter is RESTRICTED to `type='f' AND degenerate-bbox`; strokes (`type='s'`/`'fs'`) remain in the check, so a true visible-line survivor still raises. Threshold `_DEGENERATE_BBOX_EPS = 0.01` at `pdf_engine.py:250` is shared with the cover routine. | PRESERVED |
| `e352b6d` | fix(02): extend filter to type='f' fills (`pdf_engine.py:521`) | Same filter, extended scope (DC.pdf CAD glyph strokes). Same `type='f'` restriction. | PRESERVED |
| `9b84b83` | fix(02): physically cover zero-area FILL artefacts post-redact (`pdf_engine.py:528-583`, `redact.py:171`) | The cover (`cover_zero_area_artefacts`) runs **AFTER** the residual assertion at `redact.py:156-162` — so a genuine surviving filled drawing STILL raises `residual_content`. The cover is clamped to the user rect (`pdf_engine.py:576-579` `max(...query[0]), min(...query[2])`), so the white paint cannot bleed outside what the user framed. AGPL seam unchanged (cover lives in `pdf_engine.py`). | PRESERVED |

### UI polish (1)

| Commit | Subject | Threat impact | Verdict |
|--------|---------|---------------|---------|
| `6ae755f` | feat(ui): brand heading + reorder logo picker (`web/index.html:382`, `web/assets/logo.png`) | Adds `<img src="/assets/logo.png" alt="EXW" class="region-panel__heading-logo">` as STATIC markup at `web/index.html:382`. The new `/assets/logo.png` URL is served by the existing `StaticFiles(directory=str(_WEB_DIR), html=True)` mount at `app/main.py:176`; StaticFiles by design refuses path-escape requests (FastAPI/Starlette's `LookupError` → 404 for `..` traversal). No NEW endpoint, no Python route handler. The `alt` text "EXW" is a static string literal — no XSS via dynamic image alt. T-04-01-09 / T-03-04 (createElement-only) invariant preserved — `logos.js` still uses `createElement` + `textContent` exclusively (see `web/js/logos.js:104-165`). | PRESERVED — no new attack surface |

### Code-review fixes (6)

| Commit | Subject | Threat impact | Verdict |
|--------|---------|---------------|---------|
| `7c1a745` | chore: gitignore *.tmp.* | Build hygiene; removes editor-atomic-write leftovers that could double-count the AGPL grep. Strengthens audit trustworthiness. | PRESERVED |
| `e2db4b4` | fix: int() cast on `page.rotation` in `place_logo` (`pdf_engine.py:345`) | Pure idiom alignment. Output PDF byte-identical (per code-review note "guarded by existing place_logo rotation tests"). | PRESERVED |
| `1c024ac` | fix: WR-03 enforce hard megapixel cap on image ingest (`ingest.py:177-181`, `web/js/app.js:48-51`, `web/js/api.js:13`) | **STRENGTHENS T-04-01-05.** New `image_too_large_pixels` IngestError code, mapped to 413 via existing `_INGEST_STATUS` table (`app/main.py:43-58`; backend dict updated, parity test `test_ingest_status_dicts_in_sync` enforces sync with `app/api/sessions.py:_CODE_STATUS`). Frontend COPY entry added (`web/js/app.js:48-51`) with safe `extractLimit()` numeric extraction (no raw server text reflected). Two dedicated tests landed in same validate pass: `test_ingest_image_over_pixel_cap_rejected_with_limit_in_message`, `test_ingest_image_under_pixel_cap_accepted` (`tests/test_ingest.py:102-130`). | PRESERVED + STRENGTHENED |
| `4a7bc23` | fix: lift `_DEGENERATE_BBOX_EPS` to module scope (`pdf_engine.py:250`) | Eliminates drift risk between residual check and cover routine — strengthens consistency of the zero-area filter (related to hotfix #3-5 above). No behavioural delta. | PRESERVED |
| `e86a6aa` | fix: drop dead `sessionId` state from `logos.js` (`logos.js:198-210`) | Dead-code removal; no behavioural delta. `logos.js` continues to use `createElement` + `textContent` (XSS guard preserved). | PRESERVED |
| `403b6ac` | fix: `getchannel("A")` + `with`-block on second `Image.open` (`ingest.py:151, 207`) | Idiom swap (`rgba.split()[3]` → `rgba.getchannel("A")`); `with Image.open(...) as src:` releases the source handle deterministically. Composite math explicitly unchanged per commit message; covered by `test_rgba_transparent_png_composites_onto_white`. | PRESERVED |

### Aggregate Verdict

- **STRENGTHENED:** 4 mitigations (T-04-01-02, T-04-01-03, T-04-02-06, T-04-01-05) via hotfixes `8c7e90a`, `a844946`, `1c024ac`.
- **REGRESSED:** 0.
- **NEW ATTACK SURFACE:** 1 (`/assets/logo.png` static asset via `6ae755f`) — verified to ride the existing `StaticFiles` mount with no new handler, no dynamic input, no path-traversal sink. Static `<img src>` + static `alt`. **Not a registered threat, but evaluated and dismissed** because the StaticFiles invariant already covers it.
- **AGPL seam intact:** `import fitz` still confined to `app/services/pdf_engine.py:19`; verified by AST test `test_fitz_import_confined_to_engine_seam` (`tests/test_api.py`) still passing in the 243-test post-validate run.

---

## Sign-Off

- [x] All 17 registered threats verified by code citation or test name
- [x] 2 accepted-risk entries documented above with verification anchors
- [x] 0 OPEN threats — no BLOCKER
- [x] 0 unregistered flags (SUMMARY.md threat-flag section absent by convention; no out-of-band attack surface declared)
- [x] Post-verification 12-commit audit complete: 4 mitigations strengthened, 0 regressed, 1 new static asset surface evaluated and accepted as covered by existing StaticFiles mount
- [x] AGPL seam invariant intact (single `import fitz` at `app/services/pdf_engine.py:19`)
- [x] XSS guard intact (`textContent` / `createElement`-only DOM building; no `innerHTML` introduced in any post-verification commit)
- [x] originals/ SHA-256 D-05 invariant intact and strengthened (pipeline + read endpoints both decoupled from originals/)
- [x] `PDF_REDACT_TEXT_NONE` defence-in-depth guard intact at `app/services/pdf_engine.py:301-304`

**Status:** SECURED. Phase 04 cleared for the next workflow gate.

_Audited: 2026-05-23_
_Auditor: Claude (gsd-secure-phase)_
_Scope: 04-01-PLAN.md + 04-02-PLAN.md threat register (17 threats) + post-verification commit sweep (12 commits, 137a592..HEAD)_
