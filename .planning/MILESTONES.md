# Milestones

## v1.1 Illustrator Hardening (Shipped: 2026-05-29)

**Phases completed:** 3 phases, 9 plans, 15 tasks

**Key accomplishments:**

- Option B linear recipe(per checker Blocker #1):
- 3 exports + 2 private helpers,全部 type-hinted、無 module-level side effect、無 main()
- Hybrid get_drawings()+anchor-regex helper that truly deletes page-level zero-area type='f' fills (both PScript5 m/l and Acrobat re shapes) with a 5-context safe-skip mask, cardinality fail-safe, and PATTERNS S1 multi-stream write-back, plus a SEC-03 form-XObject intersect logger — all behind the AGPL seam, covered by 14 TEST-03 unit tests.
- 把 Plan 07-01 的 Option B helper 接進 redact.remove_region_vector 的 line 195/197 boundary(2 LOC import + ~15 LOC dispatcher block,既有 dispatcher 一字不改),並拔除 Phase 6 三個 xfail-strict regression decorator;Option B 對 text-glyph fixture 真正刪除 page-level 零面積 source(count 1→0、render 99.59% 白),但 SEC-01 acceptance gate 未過 — 3 個 regression case 因 Plan 07-01 helper 在 mixed-glyph(3396 ZAF cardinality fail-safe)限制 + figure-glyph 既有 residual_content 斷言 + text-glyph 缺 Option A overlay 可攻擊(attack precondition)而 FAIL,屬上游 scope,標記 Self-Check FAILED 交 orchestrator。
- 關閉 Plan 07-02 標記 FAILED 的 SEC-01 acceptance gate:把 Shape 1 locator 從 per-zaf 全串流 finditer(765s / 14% 命中)重寫為鏡像 Shape 2 的 single-pass 候選索引 + bbox-keyed Option (ii) cardinality(<5s / 100% 命中、重複-bbox 全刪),並修正 `_NUMBER` 對 PScript5 leading-dot real(`-.061` / `.06`)的漏抓根因 — 此為 mixed-glyph 14%→100% 命中率的決定性修補。同步重設計 attack precondition(承認 Option B true removal → 無 overlay 可拔 + region 乾淨 = PASS,兩道真實安全閘門檻不放鬆),並把 figure-glyph fixture 從 raw B-3012IP 的真實零面積 cluster 重新 sanitize。結果:`python -m pytest -k illustrator_attack -v` 顯示 3 PASSED,全套件 321 passed + 3 skipped + 0 xfailed + 0 failed。
- v1.1 deployed to LIVE on Zeabur; LIVE-UAT on real supplier PDFs exposed a true-removal hole (Adobe Illustrator recovered the supplier mark from embedded /PieceInfo private artwork) that render/content-stream checks could NOT detect — fixed by stripping /PieceInfo + document metadata on save, redeployed, and verified across 9 supplier files in Adobe Illustrator.

---

## v1.0 MVP — LogoSwap LIVE (Shipped: 2026-05-24,LIVE-UAT verified: 2026-05-27)

**LIVE URL:** https://logoswap.scottchen0622.com
**GitHub:** https://github.com/sc126-cornell/LogoSwap (AGPL-3.0)

**Phases completed:** 5 phases, 11 plans, 21 tasks
**Stats:** 14,126 LOC(Python 10,357 / JS 2,225 / CSS 1,086 / HTML 458);203 commits;6 天(2026-05-22 → 2026-05-27);最終測試 301 passed + 3 skipped

### Key accomplishments

- **Phase 1 — 輸入與預覽骨幹**:FastAPI 服務接收 PDF,write-once 三目錄(originals/work/outputs)保留原始檔,PyMuPDF 200 DPI PNG 渲染 + 六個 X- coordinate-seam headers;**fitz 隔離在單一 AGPL-seam module**;vanilla HTML/CSS/JS no-build 預覽 UI + 雙主題 design tokens + multi-page navigation + CSS zoom。Walking Skeleton end-to-end slice 完成。
- **Phase 2 — 框選與真正移除**:`coords.py` 純 px↔pt mapper(0/90/180/270 rotation + offset MediaBox round-trip < 1px);`redact.remove_region` + `pipeline.process_job` 走 deferred-mutation work-copy;**`apply_redactions` 真正移除文字 + 向量**(post-redaction emptiness assertion 證明);原檔 SHA-256 byte-exact;前端 region-drawing overlay + 跨頁框選 + 套用移除 + 原圖/結果 toggle + 下載 `原名_logoswap.pdf`。**REMOVE-01 核心價值落地**。
- **Phase 3 — 商標置入**:固定商標庫(`logos/` 唯讀目錄)+ auto-by-aspect-ratio 或手動 picker 模式;`place_logo` 在 `apply_redactions` 之後執行(LOGO-02 避免被自己 redact 掉);維持長寬比 + 置中 contain 演算法;同一 logo dedup 為單一 xref(D-01)。
- **Phase 4 — 點陣圖與圖片型檔案**:PNG/JPG/TIFF 標準影像上傳 → `image_to_a4_pdf` 包成 A4 PDF;`remove_region_raster` sibling(`IMAGE_PIXELS` blank 影像 pixels + text-only residual assertion 處理 dual-layer OCR 漏洞);per-region dispatch by `rect_overlaps_image`;Pillow CMYK→RGB 與 alpha 處理。Hotfix #05 `cover_zero_area_artefacts` 解 DC.pdf class 第三方 renderer hairline 問題。
- **Phase 5 — 部署與穩固化(Ubuntu)**:多階段 Dockerfile + APP_BASE_PATH/root_path 嵌入 seam + `/health` 五欄位 observability + **AGPL §13 三件套**(public GitHub + LICENSE + UI footer source link)同步上線;Zeabur (Tencent Tokyo 2C 2GB K3s) + Cloudflare DNS + Let's Encrypt TLS;原始檔 SHA-256 baseline + `verify_original_hash` + `.corrupted` sentinel + **1h TTL janitor**(D-B2,disk-fill 結構性防護)+ `/process` 60s timeout。**LIVE 上線於 logoswap.scottchen0622.com**。

### Post-LIVE hotfixes (driven by real UAT on supplier CAD PDF)

- **Hotfix 06 — dCt-residue Option A(raster overlay for dense zero-area residue,2026-05-26 → 2026-05-27)**
  - 起因:LIVE 對供應商 CAD-glyph 商標(1742 個零面積 `type='f'` filled path)的處理,既有 `cover_zero_area_artefacts` 用 1742 個 ±0.5pt 白色 cover 蓋住,但 union 重現 logo 形狀,re-color attack 可完整還原 dCt logo
  - 修法:`remove_region_vector` 加 density dispatcher,當 zero-area count ≥ `ZERO_AREA_RASTER_THRESHOLD`(=100)改用 `replace_region_with_white_raster`(單一 32×32 白色 image XObject overlay)取代 per-artefact 白色 covers
  - **5330290 silent-fail incident**(教訓):第二輪 push 一次修 9 個 nice-to-have findings(WR-01/04/05/06/07 + IN-01/02/03/05)觸發 production-only silent fail,3 小時內偵測 → revert(`e5700e5`)→ cherry-pick 跳過(`0a2fa99..724253a` 等同 `e7e7ca2..0bbeb6d`)→ 重新部署成功。教訓:hotfix 階段「過度堆疊 polish 違反 minimum-change 原則」會引入未知 production-only 失敗候選。
  - Security audit:**SECURED 5/5**(4 mitigate + 1 D-01 contract revision accept)
  - 文件:`.planning/phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-REVIEW.md` + `06-HOTFIX-SECURITY.md`

- **Hotfix 07 — loader gap + error-copy UX(2026-05-27)**
  - `web/js/viewer.js::showResultImage` 加 `showPageLoader(true/false)` 包住 `pageImage.src` swap — 解決「套用後瀏覽器繼續顯示原圖直到新 fetch 完成」的視覺空窗
  - `web/js/regions.js` 4 條 apply-fail COPY 訊息結尾加「,或重新開啟檔案再操作一次」(empirical observation 顯示重開檔常解決 session-state 問題)
  - 範圍:純 frontend,2 檔 +26/-5 行,後端零變動

### Final LIVE-UAT verification (2026-05-27)

LogoSwap (2) 檔案 forensic 通過:

- `white_dr=0`(legacy 攻擊面消失);`text=0`(NINGBO 真正刪除);`images=2`(EXW logo + raster fallback overlay)
- Re-color attack 產出純空白(vs 舊版 LIVE 可還原 dCt logo)
- 視覺渲染乾淨:「EXW Excellence Wire Ind. Co., Ltd」正確顯示,dCt + NINGBO 完全不見

### Key lessons learned

1. **AGPL §13 三件套**(public GitHub URL + LICENSE + UI footer source link)是 lockstep 部署,缺一即不合規 — 列入 Phase 5 Task 3 atomic commit
2. **Deferred-mutation pipeline**(work-copy 編輯,export 才匯出)+ **SHA-256 baseline 驗證**是「真正移除」威脅模型的雙保險
3. **fitz seam(單一檔案 import)**讓 PyMuPDF AGPL 邊界可被 swap,且 grep 一行即可驗證合規
4. **5330290 教訓**:已穩定的修法上「再加 polish」不是免費的 — 多檔同時改、跨 module 邊界、加 assertion / logging 都是潛在 production-only 失敗來源。Hotfix 階段堅守 minimum-change + sufficient-testing。
5. **Option A vs Option B trade-off**:PyMuPDF API 限制下,真正從 content stream 刪除 zero-area items 需要 content-stream surgery(Option B);Option A 用 raster overlay 對使用者實質不可恢復、對工程實作可控可測,符合 v1 內網威脅模型

### Deferred items (carried forward)

| Category | Item | Reason |
|---|---|---|
| Security | Option B — content-stream surgery 真正刪除 zero-area sources | v1 內網威脅模型不需要;對外公開使用時再評估 |
| Integration | `is_raster_fallback_image(page, xref)` getter | colleague-system integration 出現時再加 |
| Self-doc | `residual_whitepaint` 顯式列入 `_PROCESS_STATUS` | 目前 dict.get fallback 422 正確,僅可讀性 gain |
| UAT | 超大影像錯誤訊息實機驗證(WR-03 megapixel cap UI) | 自動測試覆蓋 OK;UI 字串待 ≥89MP 真檔 |

### Git tag

`v1.0` — 2026-05-27

---
