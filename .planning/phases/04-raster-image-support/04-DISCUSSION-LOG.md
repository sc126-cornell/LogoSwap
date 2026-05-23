# Phase 4: 點陣圖與圖片型檔案支援 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-23
**Phase:** 4-raster-image-support
**Areas discussed:** 獨立影像正規化策略, 分類偵測與路由策略, 填色與影像移除語意, 上傳 UI 與檔案接受策略

---

## 獨立影像正規化策略 (UPLOAD-03)

### Q1. PNG/JPG/TIFF 上傳正規化成單頁 PDF 時,頁面尺寸怎麼定?

| Option | Description | Selected |
|--------|-------------|----------|
| native pixels ÷ 72 DPI → pt(最直接) | 影像 1:1 進去,頁面點數 = 像素數 ÷ 72。大圖可能變超大頁面 | |
| 假設 96/150 DPI → 較合理大小 | 例如 1200×800 px @ 96 DPI = 900×600 pt | |
| 固定 A4 + 置中 fit(保長寬比) | 不管影像大小都是 A4 (595×842 pt) + 置中 fit | ✓ |

**User's choice:** 固定 A4 + 置中 fit(保長寬比)

### Q2. TIFF 多頁怎麼處理?

| Option | Description | Selected |
|--------|-------------|----------|
| 只取第一頁(最簡單) | 多頁 TIFF 只讀 page 0 | |
| 全部展開成多頁 PDF | 與原始資訊量一致,需在頁數上限內 | |
| 拒絕多頁 TIFF(只接受單頁) | 結構化 4xx,使用者自己拆 | ✓ |

**User's choice:** 拒絕多頁 TIFF(只接受單頁)

### Q3. CMYK 影像怎麼處理?

| Option | Description | Selected |
|--------|-------------|----------|
| 強制轉 RGB 再嵌入 | Pillow convert("RGB"),避免 Pitfall 5 黑框 | ✓ |
| 原樣嵌入(CMYK 送 fitz) | 保留色彩但可能下游出黑框 | |
| 拒絕 CMYK | ingest 直接 4xx,要求使用者轉 | |

**User's choice:** 強制轉 RGB 再嵌入

### Q4. 影像上傳上限?

| Option | Description | Selected |
|--------|-------------|----------|
| 完全沿用 50MB / 30 頁 | 同一個關 | ✓ |
| 新增「影像像素數上限」(如 50/100MP) | 防止 100MB 超大掃描爛庫 | |
| Claude 選擇 | 預設沿用 + 新增像素上限 | |

**User's choice:** 完全沿用 50MB / 30 頁

---

## 分類偵測與路由策略 (UPLOAD-02 + REMOVE-02)

### Q1. 判斷向量 vs 點陣 的粒度要多細?

| Option | Description | Selected |
|--------|-------------|----------|
| 每框獨立路由(最準確) | 每框查框內是否有 image XObject,有 → raster 分支,沒有 → vector 分支 | ✓ |
| 整頁判斷 | 一頁一次判斷,該頁所有框走同一路 | |
| 一律雙路都跑(最簡單) | 不判斷,所有框都跑 text=REMOVE + images=PIXELS | |

**User's choice:** 每框獨立路由(最準確)

### Q2. 雙層內容(掃描底 + OCR 文字)怎麼處理?

| Option | Description | Selected |
|--------|-------------|----------|
| 框內同時移文字 + 填白底(最安全) | text=REMOVE + images=IMAGE_PIXELS,Pitfall 3 雙層 leak 封堵 | ✓ |
| 只填白底(不動 text) | 只針對影像像素,OCR 文字仍可被抽取 | |
| Claude 選擇 | 推薦:框內同時移文字 + 填白底 | |

**User's choice:** 框內同時移文字 + 填白底(最安全)

### Q3. 偵測到的檔案類型(向量/點陣/掃描/混合)是否在 UI 揭露?

| Option | Description | Selected |
|--------|-------------|----------|
| 不顯示,所有檔案一律內在處理(使用者不需知) | UX 最簡單,v1 內部工具直接做事 | ✓ |
| 在頁面上顯示模式 badge | 使用者知道為何某些頁刪不到 | |
| Claude 選擇 | 推薦:v1 不顯示 | |

**User's choice:** 不顯示,所有檔案一律內在處理(使用者不需知)

---

## 填色與影像移除語意 (REMOVE-02)

### Q1. 點陣/影像路徑要用哪一個 PyMuPDF flag?

| Option | Description | Selected |
|--------|-------------|----------|
| IMAGE_PIXELS(只 blank 重疊像素,保留 image xref) | 框內部分像素變白,不動整張影像。標準 PyMuPDF 預設 | |
| IMAGE_REMOVE 全部 | 框內碰到 image 整張從 PDF 刪除;對 standalone 影像 = 整頁空白 | |
| 混合:standalone 也用 IMAGE_PIXELS | 一致用 IMAGE_PIXELS;需 garbage=4 deflate=True 避免肥 | |
| **Claude 決定** | Researcher 驗證 PyMuPDF IMAGE_PIXELS 實際行為後決定 | ✓ |

**User's choice:** Claude 選擇(以「選擇該路徑」為原則 → 傾向 IMAGE_PIXELS,IMAGE_REMOVE 列 deferred)

### Q2. redact annot 的 fill 願景怎麼給?

| Option | Description | Selected |
|--------|-------------|----------|
| fill=(1,1,1) 白(REMOVE-02 字面「填白」) | redact annot 直接畫白色覆蓋 | |
| fill=None 不填(與 Phase 2 一致) | 不畫新繪圖,依賴 IMAGE_PIXELS blank pixels 為白 | |
| **Claude 決定**,以「選擇該路徑」為原則 | Researcher 驗證後決定;當前傾向:vector 路徑 fill=None,raster 路徑 fill=(1,1,1) | ✓ |

**User's choice:** Claude 選擇(分流:vector 沿用 fill=None,raster 用 fill=(1,1,1))

### Q3. 影像處理後檔肥(Pitfall 5 uncompressed PNG bloat),save 結果要不要強制重壓縮?

| Option | Description | Selected |
|--------|-------------|----------|
| 在 process_job save 加 deflate=True / garbage=4 / clean=True(讓輸出檔不肥) | Pitfall 5 明註的最佳實踐;對 vector 路徑也有益 | ✓ |
| 保持現狀,不處理檔肥(v1 可接受) | 輸出可能 2-3 倍大 | |
| Claude 選擇 | 推薦:加 garbage=4 deflate=True clean=True | |

**User's choice:** 在 process_job save 加 deflate=True / garbage=4 / clean=True(讓輸出檔不肥)

---

## 上傳 UI 與檔案接受策略

### Q1. dropzone(上傳控件)要怎麼設計?

| Option | Description | Selected |
|--------|-------------|----------|
| 同一個 dropzone 同時接受 PDF + 影像(推薦) | accept 列全部副檔名,後端 sniff dispatch | ✓ |
| 兩個 dropzone tab 切換(明確區分) | 多一個 UI 元素要設計 | |
| 仍只接受 PDF,影像要使用者先轉 | 違反 Phase 4 UPLOAD-03 — not a real option | |

**User's choice:** 同一個 dropzone 同時接受 PDF + 影像(推薦)

### Q2. 上傳類型 sniffing(不信任副檔名,讀 magic header)?

| Option | Description | Selected |
|--------|-------------|----------|
| 介四個 magic header(PDF/PNG/JPEG/TIFF)都在 ingest 驗證 | 沿用 Phase 1 _looks_like_pdf 模式擴展 | ✓ |
| Pillow 判別 + PDF 沿原 magic | 影像部分丟 Pillow Image.open(BytesIO) 抓 format | |
| Claude 選擇 | 推薦:四種 magic header(輕量、與 Phase 1 一致),Pillow 在正規化階段才精細驗證 | |

**User's choice:** 介四個 magic header(PDF=%PDF-, PNG=\x89PNG, JPEG=\xff\xd8\xff, TIFF=II*\x00 / MM\x00*)都在 ingest 驗證

### Q3. 輸出檔名規則?

| Option | Description | Selected |
|--------|-------------|----------|
| 沿用 stem + `_logoswap.pdf`(`pic.png` → `pic_logoswap.pdf`) | Phase 2 D-06 規則一致 | ✓ |
| 加類型標記(`pic_image_logoswap.pdf`) | 凸顯原始類型 | |
| Claude 選擇 | 推薦:沿用 `_logoswap.pdf` | |

**User's choice:** 沿用 stem + `_logoswap.pdf`(`pic.png` → `pic_logoswap.pdf`)

---

## Claude's Discretion

以下交由 researcher / planner 決定(已在 CONTEXT.md `Claude's Discretion` 段落列出):

- D-08 / D-09 最終 image flag + fill 組合(researcher 驗證 PyMuPDF IMAGE_PIXELS 實際行為)。
- 影像正規化 helper 的 API surface(獨立模組 vs 併入 ingest)。
- 每頁 image-overlap 偵測 helper 命名與回傳格式。
- 每框 raster/vector 分支的 dispatch 機制(redact.remove_region 多型 / pipeline 分流 / 一律雙路單呼叫)。
- raster 分支殘留斷言設計(純 text 殘留 / fill-drawing 過濾)。
- A4 fit 留白填色(白色 vs 透明,實作等價)。
- Pillow → PDF 嵌入的中介格式(raw stream / PNG bytes / JPEG bytes)。
- 超長條 / 超扁影像的 A4 fit orientation(預設 portrait + 自動 landscape switch / 始終 portrait)。

## Deferred Ideas

- IMAGE_REMOVE 模式 — v1.x。
- per-region 不同 image-redact 模式 — v1.x。
- OCG / 隱藏層處理 — Phase 5 或 v1.x(Pitfall 8 / 6)。
- 多頁 TIFF 展開為多頁 PDF — v1 拒絕。
- EXIF orientation 自動轉正 — v1 不處理。
- A4 fit 自動 portrait/landscape 切換 — Claude's discretion 範圍。
- 背景智慧填色 / inpainting — 明確 out-of-scope。
- UI 揭露偵測到的檔案模式 badge — v1 不做。
- Pillow 預檢失敗的精細錯誤分類 — v1 一律 corrupt_image。
