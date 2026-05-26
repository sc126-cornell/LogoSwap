---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: ready_to_complete
stopped_at: Milestone v1.0 + hotfix 06 (dCt-residue Option A) + hotfix 07 (loader gap + error-copy) 全部 LIVE + LIVE-UAT 驗證閉環 at https://logoswap.scottchen0622.com。等待 /gsd-complete-milestone 歸檔
last_updated: "2026-05-27T00:45:00.000Z"
last_activity: 2026-05-27 -- hotfix 06 (dCt-residue) + hotfix 07 (loader + error copy) LIVE 驗證閉環,LogoSwap (2) 通過 forensic + re-color attack 雙重檢驗
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 11
  completed_plans: 11
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-24 — milestone v1.0 complete)

**Core value:** 能乾淨地「移除而非覆蓋」供應商商標圖案與文字,換上我司商標,產出品牌正確的 PDF。
**Current focus:** Milestone v1.0 上線完成 — 等 `/gsd-complete-milestone` 歸檔

## Current Position

Milestone: **v1.0 — LIVE** at https://logoswap.scottchen0622.com
Phase: 5 of 5 (all phases COMPLETE)
Plans: 11 of 11 complete
Status: Phase 5 完整交付 + 上線 + 兩輪 post-LIVE hotfix 閉環。Zeabur (Tencent Tokyo 2C 2GB K3s, IP 43.163.207.206) + Cloudflare DNS-only (灰色雲) + Let's Encrypt TLS 自動續發。AGPL §13 三件套(public GitHub https://github.com/sc126-cornell/LogoSwap + LICENSE AGPL-3.0 + UI footer source link)同步就位。Hotfix 06 (dCt-residue Option A raster overlay) + Hotfix 07 (loader gap + error-copy UX) 已 LIVE-UAT 驗證閉環。
Last activity: 2026-05-27 -- hotfix 06/07 LIVE 驗證閉環。LogoSwap (2) 檔案 forensic 通過:white-fill drawings=0, residual text=0, re-color attack 產出純空白,標題塊 EXW logo + Excellence Wire Ind. Co., Ltd 正確顯示

**Phase 5 post-execute hotfix 收口記錄(自 ad72796 後 12 個 hotfix commit):**

- 9 code-review fix(6abca8e..63fc4ce):CR-01/CR-02 + WR-01..07
- 1 inline test hotfix(cfded81):integrity AGPL-seam test 改 AST(避免 docstring false-positive)
- 2 UAT hotfix(db4e1c3 + c0e4233):rename「更換檔案」→「開啟新檔」+ 移除 1h TTL sticky bar;Dockerfile 加 GITHUB_OWNER build-arg
- 2 deploy hotfix(0c63ac8 + bfb93bd):repo rename logoswap → LogoSwap PascalCase URLs;Dockerfile ENV PATH=/install/bin(Zeabur 第一次 build 抓出的 runtime bug)
- 測試:243 → 291 passed + 3 platform-skipped(零回歸)
- STRIDE:Phase 5 新增 10 個 threats 全 closed(6 mitigate + 4 explicit accept);累積 27/27

**Post-LIVE hotfix 06 + 07 收口記錄(2026-05-26 → 2026-05-27,push to LIVE):**

*Hotfix 06 — dCt-residue Option A (raster overlay for dense zero-area residue)*:
- 起因:LIVE v1.0 對供應商 CAD-glyph 商標(1742 個零面積 type='f' filled path)的處理,既有 `cover_zero_area_artefacts` 用 1742 個 ±0.5pt 白色 cover 蓋住,但 union 重現 logo 形狀,re-color attack 可完整還原 dCt logo
- 修法:在 `remove_region_vector` 加 density dispatcher,當 zero-area count ≥ `ZERO_AREA_RASTER_THRESHOLD`(=100)時改用 `replace_region_with_white_raster`(單一 32×32 白色 image XObject overlay)取代 per-artefact 白色 covers
- Commits(LIVE-deployed):0a2fa99(safe-landing helpers)+ 57da585(Option A raster overlay)+ 21a567f(debug doc rename)+ 3ea0572(code-review BL-01 + WR-02 + WR-03)+ 8ae3654(security audit SECURED 5/5)+ 724253a(debug session metadata)
- Failed attempt(已 revert):5330290(WR-01/04/05/06/07 + IN-01/02/03/05 一次全修)在 production 觸發 silent fail,3 個小時內偵測 → revert(e5700e5)→ cherry-pick e7e7ca2..0bbeb6d 跳過 5330290 還原工作狀態 → 重新部署成功
- 教訓:過度堆疊「nice-to-have」polish 在已穩定的修法上會引入未知 production-only 失敗候選;遵守「最小變更 + 充分測試」
- 測試:294 → 301 passed + 3 skipped(+7 net hotfix #06 tests)
- STRIDE:5 個重新驗證 threats 全 closed(4 mitigate + 1 D-01 contract revision accept-with-documented-rationale,Hotfix-06-SECURITY.md SECURED)
- LIVE 驗證(2026-05-26 23:36–23:37 LogoSwap (6)(7))+(2026-05-27 00:01–00:02 LogoSwap (2)(3))全部通過

*Hotfix 07 — loader gap + error-copy UX*:
- 起因 1:LIVE 套用變更後,瀏覽器 `<img>` 元素在 `pageImage.src` 重新指派與新 fetch 完成之間繼續顯示前一張圖(原圖),使用者誤以為套用沒生效
- 起因 2:使用者經驗發現「套用失敗常常重新開檔就 OK」,但 4 條相關錯誤訊息均未提及此 escalation path
- 修法 1:`web/js/viewer.js::showResultImage` 加 `showPageLoader(true/false)` 包住 src swap,onerror wrapper 先關 loader 再呼叫 caller 的 onError
- 修法 2:`web/js/regions.js` COPY 字典 4 條訊息(`removalFailed` / `resultRenderFailed` / `logoUnavailable` / `logoSkipped`)結尾各加「,或重新開啟檔案再操作一次」;`downloadFailed` 維持不變(下載失敗時重開檔會丟掉已完成的 work copy)
- Commits(LIVE-deployed):4ed9531(loader gap fix)+ 0a11c97(error-copy UX)
- 範圍:純 frontend,2 個檔案,+26/-5 行,後端零變動
- 測試:301 passed + 3 skipped(零回歸;前端無 JS 自動測試,手動 UAT 驗證)
- LIVE 驗證(2026-05-27 00:37 LogoSwap (2))通過

**LIVE-UAT 最終驗收(2026-05-27)**

LogoSwap (2):
- 結構 ✅ za_black=1742(被 image XObject 蓋住,合 Option A 預期);white_dr=0;text=0;images=2(EXW logo + raster fallback overlay)
- Re-color attack ✅ 0 白色 vector drawings 可染色,攻擊產出純空白
- 視覺 ✅ 標題塊乾淨顯示「All Copy Rights Reserved」+「EXW Excellence Wire Ind. Co., Ltd」,dCt + NINGBO 完全不見
- Loader gap ✅(視覺驗證,使用者確認 LIVE 行為改善)
- Error copy ✅ 4 條訊息結尾正確加上「重新開啟檔案再操作一次」(diff 已驗證,LIVE 路徑等下次自然觸發再驗)

**Hotfix 收口記錄(自 137a592 後 13 個 commit):**

- 5 UAT hotfix(8c7e90a..9b84b83)
- 1 UI 抛光(6ae755f)
- 6 code-review fix(7c1a745..403b6ac)
- 4 docs/test commit(355b37d, 7997a8b, 3bd6c57, ef30dab)
- 測試:233 → 243 passed
- STRIDE:17/17 threats closed(15 mitigate + 2 accept;4 mitigation 因 hotfix 被 STRENGTHENED)
- AGPL seam / XSS guard / SHA-256 D-05 invariant 全部維持

**人工 UAT 結果(2026-05-23):**

- ✅ #1 DC-1.pdf 完整 round-trip(zero-area artefact 已消)
- ✅ #2 DC-2.pdf 完整 round-trip
- ✅ #3 PNG 透明圖上傳(RGBA 合成白底生效)
- ✅ #4 影像檔上傳預覽座標(/pages/meta 改讀 pristine 後對齊)
- ⏸ #5 超大影像錯誤訊息 — DEFERRED(手邊無 ≥89MP 樣本)
- ✅ #6 UI 商標調整視覺(logo heading + 四格 picker 一致)
- ✅ #7 Phase 3 logo 置入(向量 PDF + auto 模式)零迴歸
- ✅ #8「不置入商標」選項輸出純白

Progress: [██████████] 100% (Phase 1–5 all complete; 11/11 plans landed)

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
| Phase 04 P02 | ~11 min | 3 tasks | 7 files |
| Phase 05 P01 | ~25 min | 3 tasks | 10 files |
| Phase 05 P02 | ~70 min | 3 tasks | 13 files |

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
- [Phase 4-02]: IMAGE_PIXELS + rect_overlaps_image new in pdf_engine.py (AGPL seam); redact.remove_region renamed to remove_region_vector + sibling remove_region_raster (fill=None, IMAGE_PIXELS, text-only residual assertion — RESEARCH推翻 CONTEXT 初步 fill=(1,1,1) 傾向 because fill=(1,1,1) leaves a type='fs' drawing surviving get_drawings_fully_inside); pipeline.process_job per-region dispatch by rect_overlaps_image (D-05); raster branch keeps text residual (Pitfall 3 dual-layer OCR closed) but skips drawings residual (allowed legitimate vectors); Phase 4 fully closed — UPLOAD-02 + REMOVE-02 + success-criteria #3 (logo on image) all e2e verified
- [Phase 5-01]: AGPL §13 three-artifact set ships in lockstep (LICENSE + README GitHub URL + UI footer); any single artifact missing breaks compliance — atomic deliverable in Task 3 commit bb11c0d
- [Phase 5-01]: App image deliberately excludes nginx (D-A1); reverse proxy / TLS belongs to the deployment target (Zeabur LB / Ubuntu portal nginx); image stays clean uvicorn-only ASGI
- [Phase 5-01]: HEALTHCHECK uses stdlib urllib (Pitfall 2 — python:3.12-slim ships without curl/wget); CMD via sh -c so $PORT (Zeabur) + conditional ${APP_BASE_PATH:+--root-path …} (D-A2) expand at start
- [Phase 5-01]: /health upgraded to 5 fields (status, uptime_seconds, active_sessions, data_dir_bytes, data_dir_pct); guarded against session_id leak (T-05-08 — /health is unauthenticated); active_sessions filtered by storage._SESSION_ID_RE for defense in depth
- [Phase 5-01]: _START_TIME captured at module top — spawn-safe per-worker semantic (Pitfall 7); each uvicorn worker reports its own uptime; lifespan(app) skeleton present so Plan 05-02 fills body only, never the FastAPI constructor
- [Phase 5-01]: Desktop entry app/__main__.py defaults host to 127.0.0.1 (T-05-09 — loopback only); only Dockerfile CMD binds 0.0.0.0; UVICORN_NO_BROWSER=1 suppresses auto-open
- [Phase 5-01]: <OWNER> placeholder reserved in README (5 places) + index.html footer (1 place); substitution is a deploy-ops gate before public-GitHub push, NOT in plan scope
- [Phase 5-02]: SHA-256 baseline written into meta.json atomically (tempfile.mkstemp(dir=dest.parent) + os.replace; A7 cross-drive guarantee); verify_original_hash runs at pipeline.process_job entry; side-effect-before-raise (sentinel written BEFORE IntegrityError) so caller catch path cannot bypass cleanup
- [Phase 5-02]: Janitor 1h TTL with 3 synchronous trigger points (lifespan startup + POST /sessions finally + POST /process finally); all try/except wrapped so failure never taints HTTP response (T-05-05 / D-B1); _on_rm_error shared rmtree handler re-chmods 0o444 → retry for Pitfall 3 cross-platform readonly cleanup
- [Phase 5-02]: /process 60s timeout via asyncio.wait_for(asyncio.to_thread(...)) (D-D3); 504 processing_timeout; Pitfall 1 inline note documents "thread cannot be killed; UVICORN_WORKERS=2 keeps preview live; ProcessPoolExecutor upgrade deferred to v1.x"
- [Phase 5-02]: Corrupted gate (is_session_corrupted short-circuit → 410 session_corrupted) at app/api/process.py BEFORE the timeout wrapper; legacy session (Phase 1-4 meta.json without original_sha256) fail-closed → session_corrupted; 1h TTL janitor reclaims naturally — no migration script needed (Pitfall 4)
- [Phase 5-02]: session_age_seconds uses MAX (not min) mtime across 4-kind dirs — protects freshly-downloaded outputs/ from premature sweep even when originals/ is hours old (D-B4 race protection)
- [Phase 5-02]: Image upload SHA-256 hashes user's RAW image bytes (not the normalized A4 PDF) so verify reads originals/ → both sides agree; Phase 4 D-05 strengthening (pipeline doesn't write to originals/) carried forward; integrity layer pipeline only READS originals/
- [Phase 5-02]: _PROCESS_STATUS extended with original_tampered:503 / session_corrupted:410 / processing_timeout:504 as DEFENSE IN DEPTH — api/process.py raises HTTPException directly; the dict catches any future PipelineError re-raise path
- [Phase 5-02]: Frontend繁中 message mapping for 3 new server codes (originalTampered / sessionCorrupted / processingTimeout) via existing messageForError switch — no new UI scaffolding; XSS posture preserved (textContent only)
- [Phase 5-02]: D-B2 session TTL UI hint「此次處理 1 小時內完成下載 — 逾時需重新上傳」 inserted as aria-live="polite" polite live region in page-stage on upload success; swaps to「此次處理已過期,請重新上傳此檔」 on GET /sessions/{id} 404; createElement + textContent (XSS-safe, no innerHTML)
- [Phase 5-02]: AGPL seam stays at 1 fitz file (pdf_engine.py) — integrity.py + janitor.py are stdlib-only (hashlib / shutil / os / tempfile / time); AST-grep guards in tests/test_integrity.py + tests/test_janitor.py mirror canonical test_fitz_import_confined_to_engine_seam
- [Phase 5-02]: Phase 5 STRIDE total = 27/27 closed (15 mitigate + 7 accept + 5 accept-by-mitigation-equivalent); Phase 5 success criteria #1 (Plan 05-01) + #2 + #3 (Plan 05-02) all landed

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
| UAT | #5 超大影像錯誤訊息實機驗證(WR-03 megapixel cap UI rendering) | DEFERRED — 手邊無 ≥89MP 影像樣本;自動測試已覆蓋(test_ingest_image_over_pixel_cap_rejected_with_limit_in_message),UI 字串渲染待真實大檔到手再驗 | 2026-05-23 |

## Session Continuity

Last session: 2026-05-24T00:00:00.000Z
Stopped at: Phase 5 Plan 02 (hardening slice) complete — 3/3 tasks, 287 passed + 1 platform-skipped, +45 new tests, AGPL seam preserved
Resume file: None (Phase 5 complete; ready for phase-level UAT + Zeabur deploy)
