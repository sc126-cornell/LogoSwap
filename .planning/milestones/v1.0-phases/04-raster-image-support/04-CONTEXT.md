# Phase 4: 點陣圖與圖片型檔案支援 - Context

**Gathered:** 2026-05-23
**Status:** Ready for planning

<domain>
## Phase Boundary

支援圖片型(點陣/掃描)PDF 與獨立影像檔(PNG/JPG/TIFF)做為輸入,沿用 Phase 1–3 既有預覽 / 框選 / 移除 / logo 置入 / 匯出流程。點陣或掃描內容的框選區域以白色填滿(PDF_REDACT_IMAGE_PIXELS,REMOVE-02),同樣可置入我司 logo。獨立影像檔在 ingest 階段正規化為單頁 PDF,後續流程一律走 PDF 管線(一個處理路徑服務所有輸入)。

**Carrying forward(已決定,不再討論):**
- AGPL seam:`import fitz` 僅在 `app/services/pdf_engine.py`(Phase 1–3 沿用)。
- Deferred-mutation:處理只動 work 副本,原始檔永不變(SHA-256 驗證 D-05)。
- 座標對應骨幹:`pixels_to_pdf_rect` + `clamp_px_rect` + `derotation_matrix`(Phase 2 已驗證 0/90/180/270)。
- 雙主題 token、繁中文案、page-stage overlay(沿用 Phase 1 UI-SPEC)。
- 整份 90° 旋轉(Phase 3 UAT 鎖定)。
- 套用後鎖框、以「恢復原圖」為唯一重置入口(Phase 3 UAT 鎖定)。
- 自動依框選形狀挑 logo(Phase 3 UAT 鎖定 — Phase 4 影像型檔案同樣套用)。
- 點陣移除採填白(非 inpainting)— PROJECT.md Key Decision。
- 影像型檔案同樣可置入 logo — Phase 4 success criteria #3。

**不含(歸其他階段):** AI inpainting / 背景智慧填色(明確 out-of-scope)、自動偵測 logo 位置(out-of-scope)、per-region 不同 image-redact 模式(v1.x)、OCG 層級顯示/切換(Phase 5 或 v1.x)、上傳並接受向量 SVG logo(v1.x)、Ubuntu Docker 部署 + 暫存清理(Phase 5)。

</domain>

<decisions>
## Implementation Decisions

### 獨立影像正規化 (Standalone image normalization, UPLOAD-03)
- **D-01:** 頁面尺寸採 **固定 A4 + 置中 fit(保長寬比)**。所有 PNG/JPG/TIFF 上傳一律包成 A4(595×842 pt)單頁 PDF,影像以維持原長寬比的方式縮到 fit-in-page 並置中,留白為白色。理由:輸出統一(下游列印 / 簽核流程一致),不需用 DPI 假設或暴露像素尺寸給使用者。
- **D-02:** **拒絕多頁 TIFF** — 在 ingest 階段以結構化 4xx (`multi_page_tiff_unsupported`) 拒絕,v1 只接受單頁 TIFF。使用者若需要處理多頁 TIFF,自行先拆成多個單頁檔。
- **D-03:** **CMYK 影像強制轉 RGB 後嵌入** — 在 ingest/正規化階段以 Pillow `convert("RGB")` 轉換。避免 PyMuPDF Pitfall 5「CMYK / SMask 可能黑框」,且內部使用情境本就以螢幕顯示 / 簽核 PDF 為主,不是印刷出版。
- **D-04:** 影像上傳的大小 / 頁數上限 **完全沿用 PDF 同一關**:`MAX_UPLOAD_BYTES = 50MB`、`MAX_PAGES = 30`(影像正規化後通常 = 1 頁,30 頁上限實質只在多頁 TIFF 被拒之前作為單一檻)。`MAX_RENDER_PIXELS = 40 MP` 像素預算同樣對影像生效(`fit_dpi_to_pixel_budget` 沿用)。

### 分類偵測與路由 (Classification & routing, UPLOAD-02 + REMOVE-02)
- **D-05:** **每框獨立路由**(per-region detection)。對每個框,在 PDF 點空間查該 rect 是否與任何 image XObject 重疊(經 `pdf_engine` 提供的新 helper):
  - 框內有 image 重疊 → 走 raster 分支(`images=IMAGE_PIXELS` + `text=TEXT_REMOVE` + `graphics=LINE_ART_REMOVE_IF_COVERED`)。
  - 框內無 image 重疊 → 沿用 Phase 2 vector 分支(`images=IMAGE_NONE` + `text=TEXT_REMOVE` + `graphics=LINE_ART_REMOVE_IF_COVERED`)。
- **D-06:** 雙層內容(掃描底 + OCR 文字):自然落入 D-05 raster 分支 — `images=IMAGE_PIXELS` 處理掃描底,`text=TEXT_REMOVE` 同時移除 OCR 文字層。OCR 文字殘留會被 redact 後的「殘留斷言」(目前 vector 路徑已有的 `get_text_words_in_rect`)抓出來。Pitfall 3 雙層 leak 因此封堵。
- **D-07:** **偵測到的模式不在 UI 揭露** — 使用者不需要知道某頁是向量 / 點陣 / 掃描 / 混合,所有檔案一律內在處理。理由:UX 最簡單(v1 內部工具,使用者就只想框選 + 換 logo)。若未來 UAT 出現「為什麼這頁刪不掉」之類疑問,再考慮加 badge。

### 填色與影像移除語意 (Fill semantics & image redaction)
- **D-08:** **image flag 策略 — Claude 決定**,以「選擇該路徑」為原則,並由 researcher 驗證 PyMuPDF 實際行為。當前傾向:
  - 預設用 `IMAGE_PIXELS`(blank 重疊像素,保留 image xref) — standalone 影像檔(整頁就是一張 image)框選整張 = 整頁變空白,使用者預期能「換」logo 進來;但若整張 image 都被 IMAGE_REMOVE 拔掉,result PNG 就是純白頁,反而看不出框的對應。`IMAGE_PIXELS` 在區域內 blank pixels 仍保留 image 物件參考,視覺上等效「框內變白」。
  - `IMAGE_REMOVE` 列為 deferred(若未來發現 standalone image 上殘留 xref 是真的會洩漏供應商內容,再切換)。
- **D-09:** **redact annot 的 fill — Claude 決定**,以「選擇該路徑」+「不留新 drawing 假陽性」為原則:
  - Vector 分支(框內無 image):沿用 Phase 2 `fill=None`(不畫白方塊,避免新 drawing 假陽性)。
  - Raster 分支(框內有 image):以 `fill=(1,1,1)` 白色 — 配合 `IMAGE_PIXELS` 確保結果區域為白底(REMOVE-02 字面「以白色填滿」)。
  - **後置驗證注意:**raster 分支執行後,`get_drawings_fully_inside` 會看到 redact 留下的白色填色 drawing,這對 raster 分支必須改為「不要在那個 rect 上斷言 drawings」或只斷言「沒有除了 redaction 本身以外的 drawing」— researcher/planner 需設計兼容方式(可能拆成 `redact_vector` / `redact_raster` 兩個 entry point,或在 raster 分支跳過 drawings 殘留斷言只保留 text 殘留斷言)。**Text 殘留斷言一律保留**(REMOVE-01 + Pitfall 3 雙層 leak 防護)。
- **D-10:** **匯出 save 時加 `garbage=4, deflate=True, clean=True`** — 處理 Pitfall 5 IMAGE_PIXELS 重寫為未壓縮 PNG 造成檔肥(輸出可能 2–3 倍大)。對 vector 路徑亦無害(只會更小)。納入 `pdf_engine.save_doc()` 包裝 / 或 process_job 收尾的 save 呼叫。

### 上傳 UI 與檔案接受策略 (Upload UI & file acceptance)
- **D-11:** **單一 dropzone 同時接受 PDF + 影像**。`accept="application/pdf,.pdf,image/png,image/jpeg,image/tiff,.png,.jpg,.jpeg,.tif,.tiff"`。dropzone copy 從「上傳 PDF 以開始」/「支援 PDF 檔(單一檔案)」改成「上傳 PDF 或影像以開始」/「支援 PDF、PNG、JPG、TIFF(單一檔案)」之類。aria-label 同步更新。檔名顯示一律以使用者上傳的原名為主(`scan.tiff` → 顯示 `scan.tiff`),內部 work 副本與 outputs 仍是 PDF。
- **D-12:** **Sniff 全部四種 magic header** 都在 ingest 階段驗證,不信任副檔名(沿用 Phase 1 T-01-06 風格):
  - PDF: `%PDF-`(現有)
  - PNG: `\x89PNG\r\n\x1a\n`(89 50 4E 47 0D 0A 1A 0A,8 bytes)
  - JPEG: `\xff\xd8\xff`(FF D8 FF,後續 byte 為 segment 標記)
  - TIFF: `II*\x00`(little-endian, 49 49 2A 00)或 `MM\x00*`(big-endian, 4D 4D 00 2A)
  Type sniff 失敗 → `unsupported_type` 4xx。Pillow `Image.open(BytesIO).verify()` 在後續正規化階段做精細驗證(decompression bomb 防護、format 確認、CMYK 偵測等);Pillow 失敗則 `corrupt_image` 4xx。
- **D-13:** **輸出檔名沿用 stem + `_logoswap.pdf` 規則**(D-06 of Phase 2):`scan.png` → `scan_logoswap.pdf`、`drawing.tiff` → `drawing_logoswap.pdf`。pipeline 的 `_logoswap_name()` 控制字元 / 長度上限 sanitization 沿用。

### Claude's Discretion
- D-08 / D-09 的最終 flag/fill 組合由 researcher 驗證 PyMuPDF 實際 IMAGE_PIXELS 行為後決定;若驗證發現「需 fill=(1,1,1) 才能讓 PyMuPDF 真的把 image 像素 blank 成白」則照辦,若不需要可以雙分支都 fill=None 並依賴 IMAGE_PIXELS 預設行為。
- 影像正規化 helper 的精確 API surface(獨立模組 vs 併入 ingest);PDF 內每頁的 image-overlap 偵測 helper 的命名與回傳格式;每框「raster 分支 vs vector 分支」的 dispatch 機制(在 `redact.remove_region` 多型 / 在 `pipeline.process_job` 分流 / 全部走「一律雙路」的單一 apply_redactions 呼叫)。
- raster 分支殘留斷言的設計(改為純 text 殘留斷言 / 或新增「白色 fill drawing 是 redact 自己的、不算殘留」過濾器)。
- A4 fit 的留白填色(白色 vs 透明 — 但 PDF 頁面背景本就是白,實作上等價)。
- Pillow 寫出嵌入到 PDF 的中介格式(直接以 raw bytes 用 `page.insert_image(stream=...)`、或先存成 PNG bytes、或先存 JPG 為 JPEG 來源避免 PNG 轉壓肥)。
- A4 fit 時長寬比明顯不符的影像(超長條 / 超扁)是否要旋轉成 landscape A4 給更大顯示面積 — researcher / planner 可決定預設策略(建議:預設 portrait A4,影像若 landscape orientation 自動轉 landscape A4;或始終 portrait,讓使用者自己用整份 90° 旋轉切換)。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — UPLOAD-02(圖片型 PDF)、UPLOAD-03(獨立影像檔正規化為單頁 PDF)、REMOVE-02(點陣框選區以白色填滿)。

### Project research
- `.planning/research/PITFALLS.md` — **特別**:Pitfall 5(IMAGE_PIXELS 行為 / 白底現實 / 檔肥 / IMAGE_REMOVE 取捨 / transparent 影像 segfault / CMYK 黑框)、Pitfall 6(掃描型 PDF 偵測、雙層 OCR、TIFF 多頁、CMYK)、Pitfall 3 雙層 text leak、Pitfall 11(上傳安全 / sniff 不信任 extension)。
- `.planning/research/STACK.md` — Pillow 12.x(PNG/JPG/TIFF decode + CMYK→RGB convert)、PyMuPDF `apply_redactions(images=IMAGE_PIXELS)`、`page.insert_image(stream=, keep_proportion=...)`。
- `.planning/research/ARCHITECTURE.md` — deferred-mutation、座標對應、AGPL seam、三目錄。
- `.planning/research/SUMMARY.md` — 鎖定棧與架構。

### Phase 1–3 artifacts (built — Phase 4 builds on these)
- `app/services/ingest.py` — 已含 `_looks_like_pdf` magic sniff + `IngestError` typed codes;Phase 4 需擴充為「PDF 或影像 sniff + dispatch」+ 新增 `corrupt_image` / `multi_page_tiff_unsupported` / `unsupported_image_format` codes。
- `app/services/pdf_engine.py` — fitz 唯一進入點;Phase 4 新增 helper:(a) PDF 內某頁 + 某 rect 與 image XObject 是否重疊、(b) 影像正規化為單頁 PDF(從 Pillow Image 或 bytes 寫出 PDF,可能用 `page.insert_image` 到 fitz 建立的空白 A4 page);(c) `apply_redactions` 已支援 `images=` 參數,需新增公開常數 `IMAGE_PIXELS`(目前只 export `IMAGE_NONE`)。
- `app/services/redact.py` — Phase 4 改為「依框內 image 重疊與否分流」:當前 hard-coded `images=IMAGE_NONE`,需新增條件路徑用 `images=IMAGE_PIXELS`。殘留斷言對 raster 分支需調整(D-09)。
- `app/services/pipeline.py` — `process_job` 已有 deferred-mutation + reset-work-from-pristine + atomic save;Phase 4 需:(a) save 加 `garbage=4, deflate=True, clean=True`(D-10)、(b) 每 region 在 redact 前查 image-overlap 並傳給 redact。
- `app/services/render.py` — 沿用(pixel-budget fit、DPI clamp、`page_meta` 都對影像正規化後的 PDF 一體適用)。
- `app/services/coords.py` — 沿用(`pixels_to_pdf_rect`、`clamp_px_rect` 對影像化頁同樣可用)。
- `app/services/logo.py` — 沿用(Phase 3 logo 庫 + auto-pick;影像型檔案使用完全相同的 logo 流程,Phase 4 success criteria #3)。
- `app/api/pages.py`、`app/api/sessions.py`、`app/api/process.py` — 沿用既有契約(`/sessions/{id}/process` 已收 `JobSpec`,Phase 4 不改 JobSpec shape;`/sessions/{id}/pages/{n}/image` 對影像化頁回相同 PNG + headers)。
- `app/models.py` — `JobSpec` / `RegionMark` 沿用,**不需 Phase-4 新欄位**(per-region image-overlap 由後端推導,不從前端傳)。
- `app/config.py` — `MAX_UPLOAD_BYTES`、`MAX_PAGES`、`MAX_RENDER_PIXELS` 沿用;可新增 `MAX_IMAGE_PIXELS_PER_FRAME`(影像本身像素上限,在 Pillow 解碼後檢查)— Claude's discretion。
- `web/index.html` — dropzone accept、copy、aria-label、提示文字更新(D-11)。
- `web/js/api.js` — sole server seam 沿用;`POST /sessions` 上傳的 multipart 已自動帶 Content-Type,前端不需特別調整(後端 sniff 才是真實單一信任點)。
- `web/js/app.js` / `web/js/viewer.js` — 沿用(影像化頁與向量 PDF 在前端 zero-difference)。
- `.planning/phases/01-input-preview/01-CONTEXT.md` / `01-UI-SPEC.md` — token、雙主題、page-stage 契約。
- `.planning/phases/02-region-removal/02-CONTEXT.md` — 框選、redaction 真正移除、deferred-mutation、`_logoswap.pdf` 命名規則(D-06 of Phase 2)。
- `.planning/phases/03-logo-placement/03-CONTEXT.md` — logo 庫、auto-pick、`place_logo` + `keep_proportion`、stale machine、套用後鎖框、整份 90° 旋轉。
- `.planning/STATE.md` — 累積決定(尤其 Phase 1–3 的 `import fitz` 收斂、effective DPI per page、SHA-256 D-05 保證)。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ingest.py` 已有 magic-header sniff 模式(`_looks_like_pdf`,8-byte 容許 leading offset)— Phase 4 擴展為 PDF + PNG + JPEG + TIFF 四個 magic 的 dispatch,結構幾乎照抄 `_looks_like_pdf`。錯誤碼 schema(`IngestError(code, message)` + 對應到 4xx)同樣可重用,新增 `unsupported_image_format`(415)、`multi_page_tiff_unsupported`(415 或 422)、`corrupt_image`(422)、`image_dimensions_invalid`(422)等。
- `pipeline.process_job` 的 deferred-mutation + reset-work + atomic save(WR-01 / WR-05)+ 每 region 「clamp → map → redact」 迴圈骨幹完全沿用 — Phase 4 只新增「redact 前查 image-overlap、傳給 redact」與「save 加 garbage=4」兩個點。
- `redact.remove_region` 的 padding(~5pt) + apply_redactions + 殘留斷言骨幹沿用 — Phase 4 只新增 raster 分支的 `images=IMAGE_PIXELS`,殘留斷言對 raster 改為純 text 殘留(or 加 fill-drawing 過濾)。
- `pdf_engine` 的 `add_redact_annot` / `apply_redactions` / `get_text_words_in_rect` / `get_drawings_*` / `place_logo` 等 wrapper 全部沿用 — Phase 4 新增 `images_overlapping_rect(page, rect) -> bool` 之類 helper,以及把 PNG/JPG/TIFF Pillow Image → 單頁 A4 PDF 的正規化 helper(可能叫 `image_to_pdf(image_bytes, format) -> pdf_bytes`)。
- `logo.py` 完全不用動 — 影像型檔案的 logo 置入走完全相同的 `place_logo` + auto-pick + manifest 路徑(Phase 4 success criteria #3 直接從 Phase 3 繼承)。
- `render.py` 完全不用動 — 影像正規化成單頁 PDF 後,渲染與 metadata 走相同管線。
- `coords.py` 完全不用動 — 影像化頁的 page rect 已透過 `page.rect`(MediaBox-aware)拿到,座標 round-trip 與 Phase 2 一致。
- 前端 `viewer.js` / `regions.js` / `app.js` 完全不用動 — 對前端而言,影像化檔案與向量 PDF 在 `/pages/{n}/image` 取回的 PNG 一模一樣,框選 / 預覽 / 套用流程 zero-difference。

### Established Patterns
- **Three-directory deferred-mutation**(D-05):originals / work / outputs 三目錄,原始檔 chmod 0o444,每次 process 前從 pristine reset work copy。**Phase 4 影像型檔案**:`originals/` 寫的是「使用者上傳的原始影像 bytes」,`work/` 與 `outputs/` 都是 PDF(影像在 ingest 階段已轉成 PDF)— 即 originals 仍是「使用者上傳的真實 bytes」,work/outputs 一律 PDF。SHA-256 對 originals 的不動性同樣適用。
- **AGPL seam**:`import fitz` 只在 `pdf_engine.py`(Phase 1–3 enforced by test);Phase 4 的「影像 → PDF 正規化」必定要用 fitz 的 `Document` 與 `insert_image`,必須走 `pdf_engine` 的 wrapper,**不可** 在 ingest.py 直接 `import fitz`。
- **Magic-header content-sniff**:`ingest._looks_like_pdf` 模式(byte slice + `.find` + leading offset 容許)— Phase 4 三種影像 magic 同樣以此模式。
- **Typed `*Error(code, message)` + main.py 對應 4xx**:`IngestError` / `LogoError` / `RedactError` / `RenderError` / `PipelineError` — Phase 4 新增的錯誤碼一律走這個模式。
- **`config.py` 常數命名**:`MAX_X_Y` / `MIN_X` / `DEFAULT_X` — 新增常數沿用。
- **繁中錯誤訊息**:對使用者顯示的 4xx message 一律繁中(沿用 Phase 1–3)。

### Integration Points
- **後端 ingest**:`ingest.py` 從「PDF only」改為「PDF + 影像 dispatch」。PDF 走原路;影像走新增的「Pillow decode → 拒 multi-page TIFF → CMYK→RGB → 嵌入 A4 PDF → 後續流程與 PDF 一致」。新增的常數 / 錯誤碼在 main.py 對應到 4xx。
- **後端 redact**:`redact.remove_region` 從「單一 path(`images=IMAGE_NONE`)」改為「每框查 image-overlap → 分流到 vector / raster 分支」。
- **後端 pipeline**:`process_job` save 呼叫加 `garbage=4, deflate=True, clean=True`(同時對 vector 路徑有益)。
- **前端 UI**:`web/index.html` dropzone `accept` / copy / aria-label 更新。前端 JS 完全不動。
- **沒有新 API**:`/sessions` / `/sessions/{id}/process` / `/sessions/{id}/pages/{n}/image` / `/sessions/{id}/result` 契約完全不變。

</code_context>

<specifics>
## Specific Ideas

- 核心場景:供應商提供的「整頁掃描 PDF」(裡面就一張 image)+ 使用者框選 logo 位置 → 框內白底 + 我司 logo 置入。需與向量 PDF 走的核心場景一致地「乾淨、可下載、可對外使用」。
- 獨立影像場景:供應商寄來 PNG/JPG 而非 PDF — 不要求使用者先轉 PDF,工具自己包成 A4。
- 雙層 OCR PDF(掃描底 + OCR 文字層):redact 必須兩層都動(框內移文字 + 填白),避免 Pitfall 3 leak。
- 影像型檔案的 logo 置入要與 Phase 3 完全一致(同一個 picker、同一個 auto-pick by aspect、同一個 place_logo)。
- 不在 UI 暴露「向量 / 點陣 / 掃描」概念 — 使用者只看到「上傳檔案 → 框選 → 套用 → 下載」一條線。

</specifics>

<deferred>
## Deferred Ideas

- **IMAGE_REMOVE 模式**(框內 image 整張拔除)— v1 用 IMAGE_PIXELS;若實際發現 standalone 影像殘留 xref 真會洩漏供應商內容,再切換或加為 per-region 選項。
- **per-region 不同 image-redact 模式**(let user 在 UI 切「整張拔 / 局部白」)— v1.x。
- **OCG / 隱藏層處理**(Pitfall 8、Pitfall 6)— v1 不偵測 OCG;若使用者回報「Acrobat 看得到的 logo 沒在我們的預覽出現」再加。延後到 Phase 5 或 v1.x。
- **多頁 TIFF 展開成多頁 PDF** — v1 直接拒絕;若需求出現再做。
- **使用者上傳的影像偵測 EXIF orientation 自動轉正** — v1 不處理,影像進來原樣 fit;UAT 若回報倒置可加。
- **A4 fit 自動依影像長寬比選 portrait / landscape** — Claude's discretion 範圍,researcher / planner 可決定;若超出範圍可延後。
- **背景智慧填色 / inpainting** — 明確 out-of-scope(PROJECT.md)。
- **UI 揭露偵測到的檔案模式**(向量/點陣/掃描 badge)— v1 不做,UAT 出現困惑再加(Pitfall 6 提示)。
- **使用者上傳並 PIL 預檢失敗時的 detailed 錯誤分類**(decompression bomb / unsupported colorspace / corrupt)— v1 一律 `corrupt_image` 4xx;若 UAT 需要精細分類再拆。

</deferred>

---

*Phase: 4-raster-image-support*
*Context gathered: 2026-05-23*
