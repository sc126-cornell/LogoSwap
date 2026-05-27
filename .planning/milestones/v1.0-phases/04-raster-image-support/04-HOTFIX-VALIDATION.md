---
phase: 04-raster-image-support
scope: post-verification (hotfix + UI polish + code-review fix)
validated: 2026-05-23T13:30:00Z
status: nyquist_compliant
total_tests: 243
new_tests_added: 2
coverage:
  hotfix_commits: 5
  ui_commits: 1
  review_fix_commits: 6
  with_dedicated_tests: 7
  refactor_only: 4
  validation_gaps_filled: 1
---

# Phase 4 Post-Verification Validation

**Scope:** All commits after the Phase 4 verification commit (`137a592 docs(04): phase 4 verification passed`) up to and including the validation tests added by this pass. This is a focused audit of the hotfix + UI-polish + code-review-fix work that landed AFTER Phase 4 was originally marked complete.

**Result:** Nyquist-compliant. Every behavior-changing commit has dedicated test coverage; refactor-only commits do not need new tests but are gated by the existing 241-test regression suite.

---

## Per-Commit Coverage Map

| Commit | Type | Behavior change? | Dedicated test(s) | Status |
|--------|------|------------------|-------------------|--------|
| `8c7e90a` fix(04-01): RGBA → white composite | hotfix | Yes — alpha compositing | `test_rgba_transparent_png_composites_onto_white` (test_ingest.py) | COVERED |
| `a844946` fix(04-01): /pages/meta + /image read from pristine | hotfix | Yes — endpoint data source | `test_image_upload_meta_geometry_matches_work_pipeline`, `test_image_upload_auto_logo_places_with_center_frame` (test_ingest.py) | COVERED |
| `e308f6a` fix(02): zero-area drawings filter | hotfix | Yes — residual emptiness check | `test_get_drawings_fully_inside_keeps_zero_bbox_stroke_visible_line` (test_redact.py) | COVERED |
| `e352b6d` fix(02): zero-area `type='f'` fills | hotfix | Yes — extends e308f6a to fill artefacts | test_redact.py +80 lines | COVERED |
| `9b84b83` fix(02): physical cover for FILL artefacts | hotfix | Yes — Adobe-hairline post-redact cover | test_redact.py +83 lines | COVERED |
| `6ae755f` feat(ui): brand heading + logo picker | UI polish | UI only (no server behavior) | manual UAT (Launch preview) | OUT-OF-SCOPE for unit tests |
| `7c1a745` chore(04-hotfix): WR-01 `.gitignore` `*.tmp.*` | review-fix | No (build hygiene) | N/A | REFACTOR_ONLY |
| `e2db4b4` fix(04-hotfix): WR-02 `int(page.rotation)` | review-fix | No (refactor, output identical) | guarded by existing `place_logo` rotation tests | REFACTOR_ONLY |
| `1c024ac` fix(04-hotfix): WR-03 megapixel cap | review-fix | **Yes — new IngestError path** | **`test_ingest_image_over_pixel_cap_rejected_with_limit_in_message`, `test_ingest_image_under_pixel_cap_accepted` (added 2026-05-23 by this validate pass)** | GAP_FILLED |
| `4a7bc23` fix(04-hotfix): IN-01 lift `_DEGENERATE_BBOX_EPS` | review-fix | No (constant promotion) | guarded by existing zero-area tests | REFACTOR_ONLY |
| `e86a6aa` fix(04-hotfix): IN-02 drop dead `sessionId` | review-fix | No (dead-code removal) | XSS/grid tests unchanged | REFACTOR_ONLY |
| `403b6ac` fix(04-hotfix): IN-03 `getchannel("A")` + with-block | review-fix | No (idiom swap; commit msg explicitly notes "composite math unchanged") | guarded by `test_rgba_transparent_png_composites_onto_white` | REFACTOR_ONLY |

---

## Gap Analysis

Before this validate pass:
- **Behavior-changing commits without dedicated tests:** 1 (WR-03)
- **Behavior-changing commits with dedicated tests:** 6 (8c7e90a, a844946, e308f6a, e352b6d, 9b84b83, and `_build_image_only_pdf` fixtures used by multiple)
- **Refactor-only / build-hygiene / UI-only commits:** 5 (no new tests required)

After this validate pass:
- **All behavior-changing commits have dedicated tests:** 7/7 = 100%
- **Test count:** 241 → 243

---

## Behaviors Newly Covered

### WR-03 Megapixel Cap (post-hotfix, this validate pass)

`app/services/ingest.py:_ingest_image` now checks `src.width * src.height > config.MAX_INGEST_IMAGE_PIXELS` and raises `IngestError("image_too_large_pixels", ...)` BEFORE `image_to_a4_pdf` re-encodes. The two new tests prove:

1. **Strict-greater-than semantics** — image at exactly the cap is accepted; image one pixel over is rejected. Catches off-by-one regressions.
2. **User-facing message contract** — error message contains the limit number and the Traditional-Chinese 「像素」 token, which `web/js/app.js:extractLimit()` parses to render the SPEC copy with the actual server-side limit.

Both tests use `monkeypatch.setattr(config, "MAX_INGEST_IMAGE_PIXELS", N)` so they do not require a 100-MP fixture file in the repo (mirrors the existing `MAX_UPLOAD_BYTES` test pattern).

---

## Manual-Only Items

| Item | Why manual | Tracking |
|------|------------|----------|
| UI commit (6ae755f) — brand heading logo render, logo-picker reorder, centered cells | Visual layout, hover state, theme switching | UAT covered via Launch preview during build; recheck before Phase 5 ship |

---

## Sign-Off

- [x] Test infrastructure: pytest 7.x via `.venv/Scripts/python.exe -m pytest`
- [x] Pre-validate baseline: 241 passing
- [x] Post-validate: 243 passing (delta = +2 new WR-03 tests; zero regression)
- [x] AGPL seam: `import fitz` confined to `app/services/pdf_engine.py` (unchanged by validate pass)
- [x] XSS guard: `web/js/logos.js` still uses `createElement` + `textContent` only (unchanged by validate pass)
- [x] SHA-256 D-05 invariant: `originals/` untouched on read paths (unchanged by validate pass)

_Validated: 2026-05-23T13:30:00Z_
_Validator: Claude (manual /gsd-validate-phase pass — workflow.nyquist_validation gate is `false` in config so the auditor agent was not spawned)_
