# Roadmap: PDF 商標替換工具 (PDF Logo Replacement Tool / LogoSwap)

## Milestones

- ✅ **v1.0 MVP — LogoSwap LIVE** — Phases 1-5 (shipped 2026-05-24, LIVE-UAT verified 2026-05-27 after hotfix 06+07) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 — Illustrator Hardening** — Phases 6-8 (shipped 2026-05-29) — see [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

## Phases

<details>
<summary>✅ v1.0 MVP — LogoSwap LIVE (Phases 1-5) — SHIPPED 2026-05-24 (hotfix 06+07 閉環 2026-05-27)</summary>

- [x] **Phase 1: 輸入與預覽骨幹** (2/2) — 上傳向量 PDF、伺服器端渲染、瀏覽器多頁預覽 (2026-05-22)
- [x] **Phase 2: 框選與真正移除(向量)+ 下載** (3/3) (2026-05-22)
- [x] **Phase 3: 商標置入** (2/2) (2026-05-23)
- [x] **Phase 4: 點陣圖與圖片型檔案支援** (2/2) (2026-05-23)
- [x] **Phase 5: 部署與穩固化(Ubuntu)** (2/2) — Docker/Zeabur、AGPL §13 三件套、LIVE 上線 (2026-05-24)
- [x] Hotfix 06 (dCt-residue Option A) + Hotfix 07 (loader/UX) — LIVE-UAT verified 2026-05-27

Full details: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

</details>

<details>
<summary>✅ v1.1 — Illustrator Hardening (Phases 6-8) — SHIPPED 2026-05-29</summary>

**Goal:** 把威脅模型從「內網 CLI 攻擊者」升級為「Illustrator/Acrobat Pro 級編輯者」,並真正刪除供應商商標的可還原來源。

- [x] **Phase 6: Regression Foundation + Threat Model Re-evaluation** (2/2) — CAD-glyph fixture suite + attack-simulation pytest (red-light baseline) + STRIDE 加入 Illustrator-class attacker (2026-05-28)
- [x] **Phase 7: Option B Implementation — Content-Stream Surgery** (3/3) — `pdf_engine` 真正刪除 page-level 零面積 type='f' fills + 攻擊測試轉綠 (2026-05-28)
- [x] **Phase 8: Documentation Sync + LIVE Rollout** (4/4) — LIMITATION docstrings + HANDOFF/PROJECT/STATE 同步 + LIVE 部署 + **LIVE-UAT 揭露並修復 PieceInfo/metadata 真正移除漏洞** + 9 檔 Adobe Illustrator 權威驗證通過 (2026-05-29)

**v1.1 的關鍵延伸(UAT 發現,超出原計畫範圍):** Phase 8 LIVE-UAT 發現 Illustrator 來源的供應商 PDF 把可編輯原稿藏在內嵌 `/PieceInfo`(`%!PS-Adobe` PGF 串流)+ `/Info`/XMP metadata —— 一般渲染器看不到、Illustrator 還原得出。修法:`pdf_engine.save_doc` strip `/PieceInfo` + 清 metadata/XMP(debug session `ai-pieceinfo-residual-mark`)。**教訓:render/content-stream 驗證(含多引擎)不足以證明真正移除,Adobe Illustrator open-and-recover 才是權威閘門(memory: feedback_illustrator_verification)。**

Full details: [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

</details>

## Progress

| Phase | Milestone | Plans | Status | Completed |
| ----- | --------- | ----- | ------ | --------- |
| 1-5 (v1.0 MVP) | v1.0 | 11/11 | Complete | 2026-05-24 |
| 6. Regression Foundation + Threat Model | v1.1 | 2/2 | Complete | 2026-05-28 |
| 7. Option B — Content-Stream Surgery | v1.1 | 3/3 | Complete | 2026-05-28 |
| 8. Documentation Sync + LIVE Rollout | v1.1 | 4/4 | Complete | 2026-05-29 |

Both milestones shipped + LIVE. Final test suite: 345 passed, 3 skipped. AGPL fitz seam preserved (single-file import in `app/services/pdf_engine.py`).

## Backlog

候選但未排入當前 milestone 的工作,留待下個 `/gsd-new-milestone` 時考慮:

- **`is_raster_fallback_image(page, xref)` getter**:讓下游 colleague-system integration 區分 raster fallback overlay 與真 logo image。等實際 integration 需求出現再做。
- **`residual_whitepaint` 顯式列入 `_PROCESS_STATUS`**:目前透過 dict.get 預設 422 fallback 正確運作,僅 self-documentation gain。
- **超大影像錯誤訊息實機驗證**(WR-03 megapixel cap UI):自動測試覆蓋 OK,UI 字串待真實 ≥89MP 樣本到手再驗。
- **多檔批次處理**:目前每次只能處理一個 PDF。批次模式須引入 task queue(如 Celery + Redis)。Phase 5 close 時刻意排除。
- **嵌入式整合(colleague approval site)**:v1 預留 API base path + iframe-friendly 設計;實際整合留到下游需求出現。
- **對 form XObject 內 zero-area fills 做遞迴 surgery**:v1.1 SEC-03 採 page-level only + log 策略,真正出現實際樣本再評估遞迴方案。
- **對 zero-area `type='s'`(stroke)做 surgery**:目前威脅證據都是 type='f';stroke 未出現殘留問題。
- **其他編輯器級殘留載體掃除**(v1.1 PieceInfo review WR-01 衍生):`/AF`、`EmbeddedFiles`、image `/Alternates` 等 —— 在已驗證的供應商 PDF 中未出現,v1.1 範圍只到 `/PieceInfo` + `/Info` + XMP;真實樣本出現再評估。
- **公開 repo 供應商身份脫敏**:`.planning/` 規劃文件自 Phase 6 起含供應商名/料號(既有 posture);若要從 public repo 整體脫敏為獨立 task。
