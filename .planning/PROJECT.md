# LogoSwap (PDF 商標替換工具)

## What This Is

一個可部署在 Ubuntu 伺服器的網頁工具,供貿易公司內部使用。供應商提供的產品設計 PDF(含 CAD 設計資料)裡有供應商的商標圖案與文字,本工具讓使用者在瀏覽器中預覽檔案、手動框選要處理的位置,將供應商商標/文字「真正移除」(而非覆蓋),換成本公司的商標,再輸出新的 PDF。

## Core Value

能乾淨地「移除而非覆蓋」供應商的商標圖案與文字,並換上我司商標,產出品牌正確、可對外使用的 PDF。

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- [x] 使用者可上傳單一**向量 PDF**(Phase 1 — UPLOAD-01/04)
- [x] 使用者可在瀏覽器預覽檔案,並在多頁之間切換(Phase 1 — PREVIEW-01/02,含整頁顯示預設縮放、深淺主題、整份文件 90° 旋轉)
- [x] 使用者可在頁面上手動框選一個或多個要處理的區域(可跨頁)(Phase 2 — REGION-01/02)
- [x] 對向量內容,框選區域內的供應商商標物件與文字被真正移除(非覆蓋)(Phase 2 — REMOVE-01/03/04)
- [x] 使用者可下載處理後的 PDF,原始檔案不被破壞(Phase 2 — OUTPUT-01;deferred-mutation 三目錄)
- [x] 系統提供固定的我司商標庫(`logos/` + `manifest.json`),使用者可瀏覽並挑選 logo(Phase 3 — LOGO-01)
- [x] 使用者可將選定的 logo 放到框選位置,維持長寬比、置中、隨頁面旋轉正立;支援「自動依框選形狀」逐區挑選(Phase 3 — LOGO-02)

### Active

<!-- Current scope. Building toward these. -->

- [ ] 使用者可上傳**圖片型(點陣/掃描)PDF** 與**獨立影像檔**(PNG/JPG/TIFF)(Phase 4 — UPLOAD-02/03)
- [ ] 對點陣圖/影像內容,框選區域以白色填滿(Phase 4 — REMOVE-02)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- 批次處理多檔 — v1 採手動框選,屬單檔互動;批次延後到後續版本
- 與表單簽核網站整合 — v1 先做可獨立使用的工具,整合延後
- 帳號登入/權限控管 — 僅內網使用,v1 不需要
- 自動偵測商標位置(影像比對/OCR)— 已選擇手動框選,較可靠且有彈性
- 點陣圖背景還原(inpainting)— 移除後填白/底色即可,不還原被蓋住的內容

## Context

- 使用者為貿易公司,供應商會提供含 CAD 設計資料的產品設計 PDF。
- 來源檔案型態多元:向量 PDF、整頁掃描/點陣圖的圖片型 PDF、以及非 PDF 的獨立影像檔(PNG/JPG/TIFF)。
- 目標部署環境為 Ubuntu 伺服器,於公司內部網路使用。
- 未來可能將本工具掛入同事開發的「表單簽核網站」作為小工具。
- 技術上傾向使用 PyMuPDF;其 redaction 機制可在指定矩形區域內真正移除文字/向量物件,並對影像區域填色,正好對應「移除而非覆蓋」的核心需求。

## Constraints

- **Tech stack**: 核心 PDF 處理使用 PyMuPDF(Python)— 使用者指定,且 redaction 功能符合「真正移除」需求
- **Deployment**: 可安裝於 Ubuntu 伺服器的網頁工具 — 內部部署需求
- **Architecture**: v1 為可獨立執行的網頁,未來需能嵌入既有簽核網站 — 設計上預留整合彈性
- **Access**: 內網免登入 — v1 不做帳號權限,降低複雜度
- **Interaction**: 手動框選需要前端能渲染 PDF 並支援矩形框選 — 影響前端技術選型

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 由使用者手動框選決定移除區域(非自動偵測) | 商標樣式多變,手動框選最可靠且有彈性 | ✓ Validated (Phase 2) |
| 點陣圖移除採填白/底色(非 inpainting) | 降低技術複雜度,且符合使用者可接受的結果 | — Phase 4 |
| 移除後貼上固定商標庫中的我司 logo 圖檔 | 公司 logo 固定,系統預存最方便挑選 | ✓ Validated (Phase 3) |
| 以 PyMuPDF 為核心 PDF 處理函式庫 | 使用者指定,且 redaction 符合「真正移除」需求 | ✓ Validated (Phase 2);fitz 嚴格限制在 `pdf_engine.py`(AGPL seam) |
| v1 為獨立工具、內網免登入 | 先交付核心價值,整合與權限控管延後 | ✓ Validated |
| Deferred-mutation:處理只動 work 副本,原始檔永不變(SHA-256 驗證) | 預覽 / 對照 / 重做不會破壞原檔,出錯也能恢復 | ✓ Validated (Phase 2/3) |
| Logo 自動依框選形狀挑選(原生長寬比最接近) | 多頁 PDF 上不同形狀的供應商商標,使用者不必逐區手動指定 | ✓ Validated (Phase 3 UAT) |
| 90° 旋轉作用在整份文件(非 per-page) | 供應商 PDF 多半整份方向一致,逐頁旋轉是反向使用情境 | ✓ Validated (Phase 3 UAT) |
| 套用變更後框選鎖定;以「恢復原圖」為唯一重置入口 | 保護跨多頁的變更不被誤動;後續編輯路徑更明確 | ✓ Validated (Phase 3 UAT) |
| 原圖 / 移除結果切換鈕移除(視圖自動切換) | 原圖渲染路徑修好前一直顯示移除結果;UAT 期間使用者選擇取消這組按鈕 | ✓ Validated (Phase 3 UAT) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-23 after Phase 3 completion (incl. UAT-driven hotfixes + code review/fix)*
