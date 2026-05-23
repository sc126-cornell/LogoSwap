---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 4 plan 04-01 complete (image ingest vertical slice landed)
last_updated: "2026-05-23T09:30:00.000Z"
last_activity: 2026-05-23 -- Phase 04 plan 04-01 complete
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 9
  completed_plans: 8
  percent: 88
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-23)

**Core value:** 能乾淨地「移除而非覆蓋」供應商商標圖案與文字,換上我司商標,產出品牌正確的 PDF。
**Current focus:** Phase 04 — raster-image-support

## Current Position

Phase: 04 (raster-image-support) — EXECUTING
Plan: 2 of 2 (04-01 complete; 04-02 raster redact dispatch pending)
Status: Executing Phase 04
Last activity: 2026-05-23 -- Phase 04 plan 04-01 complete

Progress: [████████░░] 88%

## Performance Metrics

**Velocity:**

- Total plans completed: 3
- Average duration: ~30 min
- Total execution time: ~0.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 1 P01 | 1 | 30 min (2 tasks, 21 files) | 30 min |
| 3 | 2 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 (30 min)
- Trend: —

*Updated after each plan completion*
| Phase 01 P02 | ~16min | 3 tasks | 7 files |
| Phase 02 P01 | ~35min | 2 tasks | 3 files |
| Phase 02 P02 | ~8min | 2 tasks | 9 files |
| Phase 02 P03 | ~9min | 3 tasks | 8 files |
| Phase 03 P01 | ~25 min | 2 tasks | 14 files |
| Phase 03 P02 | 15min | 2 tasks | 7 files |
| Phase 04 P01 | ~50 min | 3 tasks | 13 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- 手動框選決定移除區域(非自動偵測)
- 點陣圖移除採填白/底色(非 inpainting)
- 移除後置入固定商標庫中的我司 logo 圖檔
- 以 PyMuPDF 為核心(redaction 做真正移除)
- v1 獨立工具、內網免登入
- [Phase 1]: Python 3.14.4 viable: PyMuPDF 1.27.2.3 installs via cp310-abi3 wheel (no source build needed)
- [Phase 1]: Backend exposes server-authoritative render metadata (DPI + page_w/h_pt + rotation + img_w/h) via headers and /meta for the Phase 2 coordinate seam
- [Phase 1]: Dual-theme CSS-custom-property token set established (light :root + [data-theme=dark] overrides, blue #2563EB / amber #F59E0B) — reused by Phases 2-5; all component CSS consumes var() tokens
- [Phase 1]: Preview is a server-rendered PNG in a position:relative page stage sized to the true render box (no client PDF parser, no re-render on zoom per D-02) — overlay-ready host for Phase 2 region selection
- [Phase 1]: web/js/api.js is the sole server seam (window.PDFTOOL_API_BASE override); theme switching is pure front-end via localStorage
- [Phase 2-01]: Coordinate mapper is pure (no fitz); the derotation/rotation matrix multiply lives in pdf_engine so `import fitz` stays in exactly one file (AGPL seam intact, T-02-03)
- [Phase 2-01]: derotation_matrix maps displayed->unrotated CONTENT space (mediabox), NOT page.rect; redaction containment bound = derotated full-image box (pdf_engine.unrotated_content_box)
- [Phase 2-01]: px<->pt round-trip proven < 1px (observed ~0.00004px) at 0/90/180/270 + offset MediaBox; this harness (tests/test_coords.py) gates Plan 02-02 removal
- [Phase ?]: [Phase 2-02]: True removal uses fill=None (not white) — a white-fill annot paints a survivor rect that defeats the emptiness assertion; fill=None removes content and paints nothing (REMOVE-01)
- [Phase ?]: [Phase 2-02]: Post-redaction emptiness assertion over the UNPADDED rect (5pt pad catches stroke wrappers); get_drawings overlap is degenerate-bbox-aware to catch flat stroke survivors (Pitfall 4)
- [Phase ?]: [Phase 2-02]: /process + result-render + /result endpoints; JobSpec{dpi,regions[{page,px_rect}]} validated contract for 02-03; original SHA-256 proven unchanged (D-05); fitz still only in pdf_engine.py
- [Phase ?]: [Phase 2-03]: Region rects stored client-side in IMAGE-PIXEL space (imageX = localX × img_w/frameW), anchored to the true render box — zoom-stable and exact against the server px_rect at dpi=200 (deferred-mutation D-05)
- [Phase ?]: [Phase 2-03]: viewer.js overlay seam is additive — page:changed/page:zoomed CustomEvents + showOriginal/showResult helpers; api.js stays the sole server seam (regions.js never fetches)
- [Phase ?]: [Phase 2-03]: Action group keeps exactly ONE accent button — 套用移除 until a fresh result, then 下載 PDF; editing invalidates the result (重新套用 + 框選已變更 stale notice, download disabled)
- [Phase ?]: [Phase 3-01]: logo_id resolves only as a manifest dict key + is_relative_to(LOGOS_DIR) assert (T-03-01); logo.py/logos.py fitz-free; ONE shared stale machine
- [Phase ?]: [Phase 3-02]: place_logo is the only new fitz call (pdf_engine.py); insert AFTER apply_redactions, keep_proportion=True center+contain (LOGO-02), one global logo dedups to a single xref (D-01); no logo_id = pure removal; original SHA-256 unchanged (D-05); pipeline stays fitz-free
- [Phase 4-01]: image_to_a4_pdf is the only new fitz call (pdf_engine.py); ingest dispatch on four magic headers; image magics MUST match at offset 0 (PDF-only allows ≤8 leading offset, D-12); Pillow chain verify/load CMYK→RGB + n_frames check; pipeline reset source switched originals→pristine (D-05 invariant on originals/ now STRICTER — pipeline never touches originals/); AGPL seam still 1 file

### Pending Todos

None yet.

### Blockers/Concerns

- **座標對應是最高風險**:瀏覽器像素 ↔ PDF 點(含頁面旋轉 derotation_matrix、DPI、top-left 原點)。於 Phase 2 優先建立並以 0/90/180/270 度往返測試證明,再寫任何移除邏輯。
- **PyMuPDF AGPL 授權**:v1 內網使用可接受,但未來嵌入表單簽核網站(對外可達)前須重新確認授權,並將 fitz 隔離在可替換的服務邊界後。
- **移除「覆蓋 vs 真正移除」**:必須呼叫 apply_redactions(),並在移除後以 get_text 斷言該區域無殘留文字。

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-23T09:30:00.000Z
Stopped at: Phase 4 plan 04-01 complete (image ingest vertical slice landed)
Resume file: .planning/phases/04-raster-image-support/04-01-SUMMARY.md
