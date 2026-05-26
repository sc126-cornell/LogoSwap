# Roadmap: PDF 商標替換工具 (PDF Logo Replacement Tool / LogoSwap)

## Milestones

- ✅ **v1.0 MVP — LogoSwap LIVE** — Phases 1-5 (shipped 2026-05-24,LIVE-UAT verified 2026-05-27 after hotfix 06+07) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

## Phases

<details>
<summary>✅ v1.0 MVP — LogoSwap LIVE (Phases 1-5) — SHIPPED 2026-05-24 (hotfix 06+07 閉環 2026-05-27)</summary>

- [x] **Phase 1: 輸入與預覽骨幹** (2/2 plans) — 上傳向量 PDF、伺服器端渲染、瀏覽器多頁預覽,原始檔保留 (completed 2026-05-22)
- [x] **Phase 2: 框選與真正移除(向量)+ 下載** (3/3 plans) — 座標對應骨幹、矩形框選、向量/文字真正移除、前後對照、下載 (completed 2026-05-22)
- [x] **Phase 3: 商標置入** (2/2 plans) — 固定商標庫、挑選並置入我司 logo(維持長寬比) (completed 2026-05-23)
- [x] **Phase 4: 點陣圖與圖片型檔案支援** (2/2 plans) — 圖片型 PDF 與獨立影像檔、移除區域填白(243 tests, 17 STRIDE threats closed) (completed 2026-05-23)
- [x] **Phase 5: 部署與穩固化(Ubuntu)** (2/2 plans) — Docker/Zeabur 部署、AGPL §13 三件套、SHA-256 integrity、1h TTL janitor、LIVE 上線(291 tests, 27 STRIDE threats closed) (completed 2026-05-24)

**Post-LIVE hotfixes (driven by real UAT on supplier CAD PDF):**

- [x] **Hotfix 06: dCt-residue Option A** — raster overlay for dense zero-area residue;closes the 1742-cover-union recovers-logo attack;5330290 second-push silent fail incident → revert → cherry-pick recovery (LIVE-UAT verified 2026-05-27)
- [x] **Hotfix 07: loader gap + error-copy UX** — `showResultImage` page loader, 4 apply-fail messages add 「,或重新開啟檔案再操作一次」 (LIVE-UAT verified 2026-05-27)

Final test count: 301 passed, 3 skipped. AGPL fitz seam preserved throughout (single-file import in `app/services/pdf_engine.py`).

</details>

### 📋 Next Milestone (planned)

To be defined by `/gsd-new-milestone`.

## Progress

| Phase | Milestone | Plans Complete | Status   | Completed  |
| ----- | --------- | -------------- | -------- | ---------- |
| 1. 輸入與預覽骨幹      | v1.0 | 2/2 | Complete | 2026-05-22 |
| 2. 框選與真正移除      | v1.0 | 3/3 | Complete | 2026-05-22 |
| 3. 商標置入            | v1.0 | 2/2 | Complete | 2026-05-23 |
| 4. 點陣圖與圖片型檔案  | v1.0 | 2/2 | Complete | 2026-05-23 |
| 5. 部署與穩固化        | v1.0 | 2/2 | Complete | 2026-05-24 |

## Backlog

候選但未排入 milestone 的工作,留待 `/gsd-new-milestone` 時考慮:

- **Option B — content-stream surgery**:真正從 PDF content stream 物理刪除 zero-area sources(目前 Option A overlay 已對使用者實質不可恢復,但 source paths 仍在)。僅在威脅模型提升(對外公開使用、未授信使用者環境)時才需要。
- **`is_raster_fallback_image(page, xref)` getter**:讓下游 colleague-system integration 區分 raster fallback overlay 與真 logo image。等實際 integration 需求出現再做。
- **`residual_whitepaint` 顯式列入 `_PROCESS_STATUS`**:目前透過 dict.get 預設 422 fallback 正確運作,僅 self-documentation gain。
- **超大影像錯誤訊息實機驗證**(WR-03 megapixel cap UI):自動測試覆蓋 OK,UI 字串待真實 ≥89MP 樣本到手再驗。
- **多檔批次處理**:目前每次只能處理一個 PDF。批次模式須引入 task queue(如 Celery + Redis)。Phase 5 close 時刻意排除。
- **嵌入式整合(colleague approval site)**:v1 預留 API base path + iframe-friendly設計;實際整合留到下游需求出現。
