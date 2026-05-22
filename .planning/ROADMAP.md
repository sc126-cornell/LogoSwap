# Roadmap: PDF 商標替換工具 (PDF Logo Replacement Tool)

## Overview

從一個能上傳並預覽供應商 PDF 的骨幹開始,先把核心價值(框選後「真正移除」向量商標與文字)做穩,再加上換成我司 logo 的置入與移除前後對照,接著擴充到點陣圖型 PDF 與獨立影像檔的支援,最後打包成可在 Ubuntu 伺服器穩定執行的網頁工具。座標對應(瀏覽器像素 ↔ PDF 點,含頁面旋轉與 DPI)是貫穿全程的關鍵風險,於 Phase 2 優先建立並充分測試,再進行任何移除邏輯。採伺服器端渲染預覽 + 延後到匯出才真正改檔(deferred-mutation)的設計。

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: 輸入與預覽骨幹** - 上傳向量 PDF、伺服器端渲染、瀏覽器多頁預覽,原始檔保留 (completed 2026-05-22)
- [x] **Phase 2: 框選與真正移除(向量)+ 下載** - 座標對應骨幹、矩形框選、向量/文字真正移除、前後對照、下載 (completed 2026-05-22)
- [ ] **Phase 3: 商標置入** - 固定商標庫、挑選並置入我司 logo(維持長寬比)
- [ ] **Phase 4: 點陣圖與圖片型檔案支援** - 圖片型 PDF 與獨立影像檔、移除區域填白
- [ ] **Phase 5: 部署與穩固化(Ubuntu)** - Docker/Nginx 部署、大型/旋轉頁面、暫存清理

## Phase Details

### Phase 1: 輸入與預覽骨幹
**Goal**: 使用者能上傳一個向量 PDF,在瀏覽器中看到伺服器渲染的頁面並逐頁瀏覽;原始檔案完整保留,後續處理一律針對工作副本。
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: UPLOAD-01, UPLOAD-04, PREVIEW-01, PREVIEW-02
**Success Criteria** (what must be TRUE):
  1. 使用者可上傳向量 PDF,並在瀏覽器看到正確渲染的頁面
  2. 多頁文件可前後切換,瀏覽每一頁
  3. 上傳後原始檔案保留不被更動(以三目錄分離:originals/work/outputs)
**Plans**: 2 plans

Plans:
**Wave 1**
- [x] 01-01: 後端骨架(FastAPI)、檔案上傳與儲存、三目錄隔離、PyMuPDF 頁面渲染 API(get_pixmap + 頁面 metadata)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-02: 前端預覽介面 — 顯示伺服器渲染頁面、多頁切換、縮放

### Phase 2: 框選與真正移除(向量)+ 下載
**Goal**: 使用者能在頁面上框選一個或多個矩形區域(可跨頁),把區域內的向量物件與文字「真正移除」(非覆蓋),先看移除前後對照確認無誤,再下載新的 PDF。本階段優先建立並測試「瀏覽器像素 ↔ PDF 點」座標對應骨幹。
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: REGION-01, REGION-02, REMOVE-01, REMOVE-03, REMOVE-04, OUTPUT-01
**Success Criteria** (what must be TRUE):
  1. 使用者可在頁面上框選一個或多個矩形區域,並可在多頁分別框選
  2. 匯出的 PDF 中,框選區域內的向量物件與文字被真正移除(無法再被選取或抽取),且結果精準落在框選位置(含旋轉頁面)
  3. 使用者可在套用前看到移除前後對照,確認沒有誤刪或殘留
  4. 使用者可下載處理後的 PDF
**Plans**: 3 plans

Plans:

**Wave 1**
- [x] 02-01-PLAN.md — 座標對應模組(coords.py,純函式)+ 0/90/180/270 度與偏移 MediaBox 往返測試 harness(往返誤差 < 1px);先做且測試通過才寫移除邏輯(REMOVE-03 基礎)

**Wave 2** *(blocked on 02-01)*
- [x] 02-02-PLAN.md — 向量/文字真正移除管線(add_redact_annot + apply_redactions、~5pt padding、移除後抽取斷言)、JobSpec 模型、結果預覽渲染與匯出/下載端點;對 work 副本套用、原始檔永不變(deferred-mutation D-05)

**Wave 3** *(blocked on 02-02)*
- [x] 02-03-PLAN.md — 前端矩形框選 overlay、區域清單(跨頁、刪除/清除、可重疊、無控制點)、前後對照切換、套用移除/下載串接(沿用 Phase 1 token、雙主題、繁中文案)

### Phase 3: 商標置入
**Goal**: 在移除後的區域放上我司商標。建立固定商標庫供瀏覽挑選,選定的 logo 以維持長寬比的方式置入框選位置。
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: LOGO-01, LOGO-02
**Success Criteria** (what must be TRUE):
  1. 使用者可從固定商標庫瀏覽並挑選一個我司 logo
  2. 選定的 logo 以維持長寬比(insert_image keep_proportion)的方式置入框選位置,輸出 PDF 中位置正確
  3. 移除與置入可在同一流程中完成並下載
**Plans**: 2 plans

Plans:
- [ ] 03-01: 商標庫(logos/ + manifest.json)、列表/挑選 API、前端 logo 選擇器
- [ ] 03-02: logo 置入(insert_image、alpha 透明、長寬比貼合)、整合進匯出流程

### Phase 4: 點陣圖與圖片型檔案支援
**Goal**: 支援圖片型(點陣/掃描)PDF 與獨立影像檔(PNG/JPG/TIFF)。移除區域以白色填滿,並可同樣置入我司 logo。
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: UPLOAD-02, UPLOAD-03, REMOVE-02
**Success Criteria** (what must be TRUE):
  1. 使用者可上傳圖片型 PDF 或獨立影像檔(PNG/JPG/TIFF),並能預覽與框選
  2. 點陣圖/影像的框選區域在輸出中以白色填滿(PDF_REDACT_IMAGE_PIXELS),原內容被移除
  3. 影像型檔案同樣可置入我司 logo 並下載
**Plans**: 2 plans

Plans:
- [ ] 04-01: 輸入分類(向量/點陣/掃描)、獨立影像檔正規化為單頁 PDF、圖片型偵測
- [ ] 04-02: 點陣圖移除分支(填白)、與既有移除/置入/匯出流程整合

### Phase 5: 部署與穩固化(Ubuntu)
**Goal**: 打包為可在 Ubuntu 伺服器執行的網頁服務(Docker + Nginx),處理大型與旋轉頁面、暫存檔清理,並確保原始檔不被竄改。
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: (跨切面;部署與穩固化,無新增 v1 需求 ID)
**Success Criteria** (what must be TRUE):
  1. 工具可透過 Docker 在 Ubuntu 伺服器上安裝並執行(Uvicorn + Nginx)
  2. 大型或含旋轉頁面的 PDF 可正確處理不崩潰(DPI 上限/背景工作)
  3. 暫存檔於處理後被清理,原始檔以雜湊驗證未被竄改
**Plans**: 2 plans

Plans:
- [ ] 05-01: 多階段 Dockerfile、Uvicorn workers、Nginx 反向代理、可設定的 API base(預留嵌入彈性)
- [ ] 05-02: 穩固化 — 大型/旋轉頁面處理、檔案大小限制、暫存清理 janitor、原始檔雜湊驗證

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. 輸入與預覽骨幹 | 2/2 | Complete   | 2026-05-22 |
| 2. 框選與真正移除(向量)+ 下載 | 3/3 | Complete   | 2026-05-22 |
| 3. 商標置入 | 0/2 | Not started | - |
| 4. 點陣圖與圖片型檔案支援 | 0/2 | Not started | - |
| 5. 部署與穩固化(Ubuntu) | 0/2 | Not started | - |
