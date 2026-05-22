---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Phase 2 context gathered
last_updated: "2026-05-22T08:38:54.386Z"
last_activity: 2026-05-22
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 5
  completed_plans: 3
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-22)

**Core value:** 能乾淨地「移除而非覆蓋」供應商商標圖案與文字,換上我司商標,產出品牌正確的 PDF。
**Current focus:** Phase 2 — 框選與真正移除(向量)+ 下載

## Current Position

Phase: 2 of 5 (框選與真正移除(向量)+ 下載)
Plan: 1 of 3 complete (02-01 coordinate-mapper spine done; 02-02 removal next)
Status: 02-01 complete — coordinate mapper proven (round-trip < 1px gate green)
Last activity: 2026-05-22 -- executed 02-01 (coords spine)

Progress: [██████░░░░] 60%

## Performance Metrics

**Velocity:**

- Total plans completed: 1
- Average duration: ~30 min
- Total execution time: ~0.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 1 P01 | 1 | 30 min (2 tasks, 21 files) | 30 min |

**Recent Trend:**

- Last 5 plans: 01-01 (30 min)
- Trend: —

*Updated after each plan completion*
| Phase 01 P02 | ~16min | 3 tasks | 7 files |
| Phase 02 P01 | ~35min | 2 tasks | 3 files |

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

Last session: 2026-05-22T08:38:54.372Z
Stopped at: Phase 2 context gathered
Resume file: None
