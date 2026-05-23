# Requirements: PDF 商標替換工具 (PDF Logo Replacement Tool)

**Defined:** 2026-05-22
**Core Value:** 能乾淨地「移除而非覆蓋」供應商的商標圖案與文字,並換上我司商標,產出品牌正確、可對外使用的 PDF。

## v1 Requirements

初版範圍。每項需求對應到 roadmap 的某個階段。

### 上傳與輸入 (UPLOAD)

- [x] **UPLOAD-01**: 使用者可上傳單一向量 PDF 進行處理
- [ ] **UPLOAD-02**: 使用者可上傳圖片型(點陣/掃描)PDF 進行處理
- [x] **UPLOAD-03**: 使用者可上傳獨立影像檔(PNG/JPG/TIFF),系統將其正規化為可處理的單頁文件
- [x] **UPLOAD-04**: 系統保留原始檔案不被修改,所有結果輸出為新檔

### 預覽 (PREVIEW)

- [x] **PREVIEW-01**: 使用者可在瀏覽器中預覽上傳的檔案內容
- [x] **PREVIEW-02**: 使用者可在多頁文件之間切換瀏覽

### 框選 (REGION)

- [x] **REGION-01**: 使用者可在頁面上以矩形框選一個或多個要處理的區域
- [x] **REGION-02**: 使用者可在多頁分別框選不同區域

### 移除 (REMOVE)

- [x] **REMOVE-01**: 對向量內容,框選區域內的供應商商標物件與文字被真正移除(移除後無法再被選取或抽取),而非覆蓋
- [ ] **REMOVE-02**: 對點陣圖/影像內容,框選區域以白色填滿(以周圍底色填滿列為加值,見 v2)
- [x] **REMOVE-03**: 移除與後續置入的結果精準落在使用者框選的位置(所見即所得)
- [x] **REMOVE-04**: 使用者可在套用前預覽移除前後的效果(before/after),確認沒有誤刪或殘留

### 商標置入 (LOGO)

- [x] **LOGO-01**: 系統提供固定的我司商標庫,使用者可瀏覽並挑選要使用的 logo
- [x] **LOGO-02**: 使用者可將選定的 logo 放到框選位置,並維持長寬比縮放貼合

### 輸出 (OUTPUT)

- [x] **OUTPUT-01**: 使用者可下載處理後的 PDF 檔案

## v2 Requirements

已知但延後到後續版本,目前不納入 roadmap。

### 批次與整合 (BATCH / INTEGRATION)

- **BATCH-01**: 一次上傳多個檔案並自動套用相同處理
- **INTEG-01**: 將工具嵌入同事的表單簽核網站(iframe 或 API)
- **AUTH-01**: 帳號登入與權限控管

### 進階編輯 (ADVANCED)

- **ADV-01**: 框選動作可復原/重做(undo/redo)
- **ADV-02**: 點陣圖移除區域以周圍底色智慧填滿(背景色取樣),而非只填白
- **ADV-03**: 每個區域可細調移除模式(文字/向量/影像分別開關)
- **ADV-04**: logo 置入後可微調位置與大小

## Out of Scope

明確排除,記錄以防範圍蔓延。

| Feature | Reason |
|---------|--------|
| AI inpainting(智慧還原被商標蓋住的內容) | 複雜度高,非核心;移除後填白/底色已可接受 |
| 自動偵測商標位置(影像比對) | 已選擇手動框選,商標樣式多變,手動最可靠 |
| 自動 OCR 辨識並移除文字 | 手動框選已涵蓋,避免誤判 |
| 行動裝置原生 App | 以網頁工具為主,內網桌面使用情境 |

## Traceability

各需求對應到哪個階段。

| Requirement | Phase | Status |
|-------------|-------|--------|
| UPLOAD-01 | Phase 1 | Complete |
| UPLOAD-04 | Phase 1 | Complete |
| PREVIEW-01 | Phase 1 | Complete |
| PREVIEW-02 | Phase 1 | Complete |
| REGION-01 | Phase 2 | Complete |
| REGION-02 | Phase 2 | Complete |
| REMOVE-01 | Phase 2 | Complete |
| REMOVE-03 | Phase 2 | Complete |
| REMOVE-04 | Phase 2 | Complete |
| OUTPUT-01 | Phase 2 | Complete |
| LOGO-01 | Phase 3 | Complete |
| LOGO-02 | Phase 3 | Complete |
| UPLOAD-02 | Phase 4 | Pending |
| UPLOAD-03 | Phase 4 | Complete |
| REMOVE-02 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0 ✓

> Phase 5(部署與穩固化)為跨切面交付,不對應特定 v1 需求 ID。

---
*Requirements defined: 2026-05-22*
*Last updated: 2026-05-22 after initial definition*
