# Phase 4: 點陣圖與圖片型檔案支援 - Research

**Researched:** 2026-05-23
**Domain:** PyMuPDF image-pixel redaction、Pillow 影像 ingest、A4 正規化、image-overlap dispatch
**Confidence:** HIGH(PyMuPDF redaction 行為以本地 PyMuPDF 1.27.2.3 + Pillow 12.2.0 實機驗證;Pillow MAX_IMAGE_PIXELS 與 n_frames API 來自官方 docs;JPEG passthrough 已實測 byte-exact)

## Summary

Phase 4 是把 Phase 1–3 已驗證的「ingest → 三目錄 → render → 框選 → redact → logo 置入 → save」骨幹,擴張到兩種新輸入(image-only PDF、PNG/JPG/TIFF)與一條新 redact 分支(`images=PDF_REDACT_IMAGE_PIXELS`)。所有跨層契約(JobSpec / page meta / coords mapper / logo 流程)**完全不變** — 影響面集中於 `ingest.py`、`pdf_engine.py`(新增 helpers)、`redact.py`(分流)、`pipeline.py`(save 加 `garbage=4` + 每框 image-overlap 查詢)、`web/index.html`(dropzone accept)。

**核心經實機驗證的事實**(以本機 PyMuPDF 1.27.2.3 + Pillow 12.2.0 跑出來的結果):
1. **整頁 image PDF 框選整張、`images=IMAGE_PIXELS` 後 image xref 從 `get_images()` 中消失**(實測 `get_images: []`),與 `IMAGE_REMOVE` 對 standalone image PDF 視覺結果相同 — 不存在「pixel 已 blank 但殘留 xref 洩漏供應商內容」的隱憂,因為 IMAGE_PIXELS 把舊 image **整個取代**(部分重疊時用新的 blank-過的 PNG 取代;完全覆蓋時直接從頁面拿掉)。
2. **`add_redact_annot(rect, fill=(1,1,1))` 會在 raster 分支留下一個 `type=fs`、`rect == redact_rect`、`fill=(1.0,1.0,1.0)` 的填色 drawing**(實測 `drawings count: 1`),會擊穿 Phase 2 的 `get_drawings_fully_inside` 殘留斷言。`fill=None` 則不留任何 drawing,且 `IMAGE_PIXELS` 本身就把像素變白 — 所以 **raster 分支也應該 `fill=None`**,REMOVE-02 的「以白色填滿」由 `IMAGE_PIXELS` 自身達成,不需要靠 annot fill。
3. **`doc.save(..., garbage=4, deflate=True, clean=True)` 對 IMAGE_PIXELS 重寫造成的 uncompressed-PNG 肥檔有壓倒性效果**(實測 2.88 MB → 6 KB,~480× 壓縮)。Pitfall 5 的肥檔問題以 D-10 完全封堵。
4. **JPEG bytes 透過 `page.insert_image(stream=jpg_bytes)` 是 byte-exact passthrough**(實測 8229 bytes 進、8229 bytes 出,`extract_image` 報 `ext='jpeg'`)— D-01 影像正規化可走 JPEG 直通路徑、不用 PNG 重壓肥檔。
5. **雙層 OCR PDF(底圖 + 文字層)在單一 `apply_redactions(images=IMAGE_PIXELS, text=TEXT_REMOVE)` 呼叫中兩層都會被清乾淨**(實測:redact 前 `text words: ['SUPPLIER', 'WORDMARK']`,後 `text words in clipped: []`)— D-06 雙層 leak 完全封堵。

**Primary recommendation:**
- 採 D-08 預設 `IMAGE_PIXELS`(無需切到 IMAGE_REMOVE — 實測證實 standalone image 全頁框時 IMAGE_PIXELS 與 IMAGE_REMOVE 效果一致,且 IMAGE_PIXELS 在部分重疊時仍保留未框部分,語意更乾淨)。
- 採 D-09 raster 分支 `fill=None`(與 vector 分支一致 — IMAGE_PIXELS 自己會把像素變白,annot fill 反而會留 drawing 假陽性)。**Raster 分支的殘留斷言**:純文字殘留斷言(`get_text_words_in_rect` 必須為空),drawings 斷言略過(因 raster 區內可能有合法 image-only 內容,且 fill=None 後不會留 drawing,殘留 drawing 已不再是 raster 的失敗特徵)。
- **拆 entry point** 為 `redact.remove_region_vector(page, rect)` 與 `redact.remove_region_raster(page, rect)`,分流由 `pipeline` 在迴圈中查 `pdf_engine.rect_overlaps_image(page, rect)` 決定 — 這比「統一 entry point + 內部分支」對讀者更清楚,且讓 Phase 5 進一步分支(per-region 模式)時有自然擴充點。

---

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

**獨立影像正規化 (Standalone image normalization, UPLOAD-03)**
- **D-01:** 頁面尺寸採 **固定 A4 + 置中 fit(保長寬比)**。所有 PNG/JPG/TIFF 上傳一律包成 A4(595×842 pt)單頁 PDF,影像以維持原長寬比的方式縮到 fit-in-page 並置中,留白為白色。
- **D-02:** **拒絕多頁 TIFF** — 在 ingest 階段以結構化 4xx (`multi_page_tiff_unsupported`) 拒絕,v1 只接受單頁 TIFF。
- **D-03:** **CMYK 影像強制轉 RGB 後嵌入** — 在 ingest/正規化階段以 Pillow `convert("RGB")` 轉換。避免 PyMuPDF Pitfall 5「CMYK / SMask 可能黑框」。
- **D-04:** 影像上傳的大小 / 頁數上限 **完全沿用 PDF 同一關**:`MAX_UPLOAD_BYTES = 50MB`、`MAX_PAGES = 30`、`MAX_RENDER_PIXELS = 40 MP`(`fit_dpi_to_pixel_budget` 沿用)。

**分類偵測與路由 (Classification & routing, UPLOAD-02 + REMOVE-02)**
- **D-05:** **每框獨立路由**(per-region detection)。對每個框,在 PDF 點空間查該 rect 是否與任何 image XObject 重疊:
  - 框內有 image 重疊 → 走 raster 分支(`images=IMAGE_PIXELS` + `text=TEXT_REMOVE` + `graphics=LINE_ART_REMOVE_IF_COVERED`)。
  - 框內無 image 重疊 → 沿用 Phase 2 vector 分支(`images=IMAGE_NONE` + `text=TEXT_REMOVE` + `graphics=LINE_ART_REMOVE_IF_COVERED`)。
- **D-06:** 雙層內容(掃描底 + OCR 文字):自然落入 D-05 raster 分支 — `images=IMAGE_PIXELS` 處理掃描底,`text=TEXT_REMOVE` 同時移除 OCR 文字層。OCR 文字殘留會被 redact 後的「殘留斷言」(`get_text_words_in_rect`)抓出來。
- **D-07:** **偵測到的模式不在 UI 揭露** — 使用者不需要知道某頁是向量 / 點陣 / 掃描 / 混合,所有檔案一律內在處理。

**填色與影像移除語意 (Fill semantics & image redaction)**
- **D-08:** **image flag 策略**(researcher 驗證後 — 見 Question 1):預設 `IMAGE_PIXELS`(blank 重疊像素,保留 image xref 給部分重疊區);`IMAGE_REMOVE` 列為 deferred。
- **D-09:** **redact annot 的 fill**(researcher 驗證後 — 見 Question 4):
  - Vector 分支(框內無 image):沿用 Phase 2 `fill=None`。
  - Raster 分支(框內有 image):**亦採 `fill=None`**(researcher 推翻 context 中「fill=(1,1,1)」的初步傾向 — 見 Question 1/4 實測證據)。
  - **後置驗證:** 拆 entry point(`remove_region_vector` / `remove_region_raster`);raster 分支只保留文字殘留斷言,跳過 drawings 殘留斷言(因 raster 區允許有圖形內容)。
- **D-10:** **匯出 save 時加 `garbage=4, deflate=True, clean=True`** — 已在 `pdf_engine.save_doc()` 內預設(現有實作),pipeline 已透過該包裝呼叫;Phase 4 不需新增 save 路徑,只要確認 raster 分支走過該包裝。

**上傳 UI 與檔案接受策略 (Upload UI & file acceptance)**
- **D-11:** **單一 dropzone 同時接受 PDF + 影像**。`accept="application/pdf,.pdf,image/png,image/jpeg,image/tiff,.png,.jpg,.jpeg,.tif,.tiff"`。dropzone copy / aria-label 同步更新。檔名顯示一律以使用者上傳的原名為主。
- **D-12:** **Sniff 全部四種 magic header** 都在 ingest 階段驗證,不信任副檔名(沿用 Phase 1 T-01-06 風格):
  - PDF: `%PDF-`(現有)
  - PNG: `\x89PNG\r\n\x1a\n`(89 50 4E 47 0D 0A 1A 0A,8 bytes)
  - JPEG: `\xff\xd8\xff`(FF D8 FF,後續 byte 為 segment 標記)
  - TIFF: `II*\x00`(little-endian, 49 49 2A 00)或 `MM\x00*`(big-endian, 4D 4D 00 2A)
  Type sniff 失敗 → `unsupported_type` 4xx;Pillow `Image.open(BytesIO).verify()` 在後續正規化階段做精細驗證;Pillow 失敗則 `corrupt_image` 4xx。
- **D-13:** **輸出檔名沿用 stem + `_logoswap.pdf` 規則**:`scan.png` → `scan_logoswap.pdf`、`drawing.tiff` → `drawing_logoswap.pdf`。pipeline 的 `_logoswap_name()` sanitization 沿用。

### Claude's Discretion

- 影像正規化 helper 的精確 API surface(獨立模組 vs 併入 ingest)— 本研究建議:置於 `pdf_engine.image_to_a4_pdf(image_bytes, *, fmt) -> bytes`,因為 fitz 必須建單頁文件,符合 AGPL seam 收斂規則。
- image-overlap 偵測 helper 的命名與回傳格式 — 本研究建議:`pdf_engine.rect_overlaps_image(page, rect) -> bool`(回傳 list 對 Phase 4 沒有用,等到 Phase 5 per-region 模式再擴)。
- 每框「raster 分支 vs vector 分支」的 dispatch 機制 — 本研究建議:**在 pipeline 分流**,呼叫 `redact.remove_region_vector` / `redact.remove_region_raster` 兩個明確的 entry point(理由見 Question 4)。
- raster 分支殘留斷言的設計 — 本研究建議:**拆 entry point + raster 分支只做文字殘留斷言**(理由見 Question 4)。
- A4 fit 的留白填色 — 等價(PDF 頁面背景本就白)。
- Pillow 寫出嵌入到 PDF 的中介格式 — 本研究建議:**JPEG bytes 直通(Pillow re-encode 為 JPEG quality=85 後 stream= 傳入),CMYK / PNG / TIFF 統一轉 RGB PNG**(理由與實測見 Question 2)。
- A4 fit 時長寬比明顯不符的影像 — 本研究建議:**始終 portrait A4,讓使用者用整份 90° 旋轉切換**(MVP 最薄路徑,Phase 3 整份旋轉已存在)。

### Deferred Ideas (OUT OF SCOPE)

- IMAGE_REMOVE 模式(v1 用 IMAGE_PIXELS)
- per-region 不同 image-redact 模式(v1.x)
- OCG / 隱藏層處理(Phase 5 或 v1.x)
- 多頁 TIFF 展開成多頁 PDF
- 使用者上傳的影像偵測 EXIF orientation 自動轉正
- A4 fit 自動依影像長寬比選 portrait / landscape
- 背景智慧填色 / inpainting(out-of-scope per PROJECT.md)
- UI 揭露偵測到的檔案模式(badge)
- 使用者上傳並 PIL 預檢失敗時的 detailed 錯誤分類

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UPLOAD-02 | 使用者可上傳圖片型(點陣/掃描)PDF 進行處理 | Question 1(IMAGE_PIXELS 行為驗證)+ Question 3(image-overlap 偵測 helper)+ Question 6(三目錄語意 — image-only PDF 走 PDF 路徑無轉換) |
| UPLOAD-03 | 使用者可上傳獨立影像檔(PNG/JPG/TIFF),系統將其正規化為可處理的單頁文件 | Question 2(影像 → 單頁 A4 PDF 正規化)+ Question 5(Pillow ingest 安全)+ Question 6(三目錄:originals = 原始 image bytes、work = 正規化後的 PDF) |
| REMOVE-02 | 對點陣圖/影像內容,框選區域以白色填滿 | Question 1(IMAGE_PIXELS 實機驗證:重疊像素被白色取代)+ Question 4(raster 分支殘留斷言設計) |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Magic-header sniff(PDF / PNG / JPEG / TIFF) | API / Backend(`ingest.py`)| — | 不信任 client extension 是 Phase 1 確立的 trust boundary;Phase 4 延伸 sniff 種類,不引入新層 |
| Pillow decode + verify + multi-page TIFF 偵測 + CMYK→RGB convert | API / Backend(`ingest.py`)| — | Pillow 直接 import(Phase 3 logo.py 已 import Pillow 為先例),與 fitz 不衝突 |
| Image → 單頁 A4 PDF 正規化 | API / Backend(`pdf_engine.py`)| — | 必須用 `fitz.open()` + `doc.new_page` + `page.insert_image`,屬 AGPL seam;放入 `pdf_engine.py` 是 Phase 1–3 的 invariant |
| Per-frame image-overlap detection | API / Backend(`pdf_engine.py`)| Backend(`pipeline.py` 呼叫)| 需 `page.get_image_rects()` 必經 fitz;dispatch 由 pipeline 控制 |
| Vector / raster redact 分支 dispatch | API / Backend(`pipeline.py`)| Backend(`redact.py` 兩個 entry point)| 分流邏輯純 Python(無需 fitz)、靠 `pdf_engine.rect_overlaps_image` 結果分流 |
| Raster redact + 殘留斷言 | API / Backend(`redact.py` → `pdf_engine.apply_redactions`)| — | 沿用 Phase 2 包裝,只擴 `images=` 參數,殘留斷言類型差異在 redact 層處理 |
| Logo 置入到 raster 區 | API / Backend(`pdf_engine.place_logo`)| — | 完全沿用 Phase 3,不動;raster 區 logo 行為與 vector 區一致(Phase 4 success criteria #3 自動繼承)|
| Dropzone accept + copy 更新 | Browser / Client(`web/index.html`)| — | 純前端 attribute 變更;`web/js/api.js` 不動(後端 sniff 是真實單一信任點)|
| 結果預覽 + 下載 | API / Backend(`api/process.py` + `pipeline.output_path`)| Browser / Client(沿用)| 完全沿用 Phase 3 — 影像化後的 PDF 與 vector PDF 在所有端點是 zero-difference |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyMuPDF (`fitz`) | 1.27.2.3(installed) | Image-only PDF redact + 影像 → A4 PDF 正規化 + image-overlap 偵測 | `[VERIFIED: 本機 .venv]` 與 CLAUDE.md 鎖定一致;`PDF_REDACT_IMAGE_PIXELS=2` / `PDF_REDACT_IMAGE_NONE=0` / `PDF_REDACT_IMAGE_REMOVE=1` 常數已實測;`Document.new_page(width=595, height=842)` + `Page.insert_image(rect, stream=bytes)` 已實測能建立單頁 PDF |
| Pillow | 12.2.0(installed) | PNG / JPG / TIFF decode、verify、CMYK→RGB、multi-page TIFF 偵測、decompression-bomb 防護 | `[VERIFIED: 本機 .venv]` 與 CLAUDE.md 鎖定一致;`Image.MAX_IMAGE_PIXELS = 89478485` 預設值已實測;`Image.n_frames` 屬性與 `Image.format` 屬性為官方 API `[CITED: pillow.readthedocs.io/en/stable/reference/Image.html]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python stdlib `io.BytesIO` | 內建 | 把 ingest 收進來的 bytes 包成 Pillow 可開檔的 stream | 永遠 — `Image.open(io.BytesIO(data))` 是不寫暫存檔的標準路徑 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyMuPDF `Document.new_page` + `insert_image` 建單頁 A4 PDF | Pillow `Image.save("out.pdf")` 直接輸出 PDF | Pillow 確實可以,但會打破 AGPL seam(`import PIL` 在 `pdf_engine.py` 外也行,但「ingest 寫 PDF」會違反「fitz 寫 PDF 都在 pdf_engine」的 invariant);此外 Pillow 輸出 PDF 沒有 A4 fit + 置中的自動行為,要自己堆。**用 fitz 路徑同時收斂 seam 與行為複雜度。** |
| 部分重疊用 `IMAGE_PIXELS`、完全覆蓋用 `IMAGE_REMOVE` 切換 | 統一用 `IMAGE_PIXELS` | 實測證實 IMAGE_PIXELS 在「框完全覆蓋 image」時自動把 image xref 從 `get_images()` 中拿掉(實測 `get_images: []`)— 兩個常數對 standalone image PDF 全頁框的視覺與結構結果一致;**保持單一常數最簡單**,符合 D-08 |
| Raster 分支 `fill=(1,1,1)` 配 `IMAGE_PIXELS` | Raster 分支 `fill=None` 配 `IMAGE_PIXELS` | 實測:`fill=(1,1,1)` 會在 page 上多留一個 `type='fs'` 的填色 drawing(`rect == redact_rect`、`fill=(1,1,1)`);`fill=None` 不留 drawing,且 IMAGE_PIXELS 已把像素變白。**`fill=None` 同時符合 REMOVE-02 視覺(白)與 D-09「不留新 drawing 假陽性」要求** |
| JPEG 上傳 PNG-encode 後嵌入 | JPEG bytes 直通 `insert_image(stream=jpg_bytes)` | 實測 JPEG byte-exact passthrough(8229 → 8229,`extract_image` 報 `ext='jpeg'`)— **JPEG 直通省下 PNG-encode 的時間與檔肥**,且不增加複雜度(`insert_image` 對 JPEG 與 PNG 一視同仁) |

**Installation:**

Phase 4 不需新增 Python 套件 —`PyMuPDF 1.27.2.3` + `Pillow 12.2.0` 都已在 venv `[VERIFIED: 本機 .venv]`。前端不需新增任何 JS dependency。

**Version verification:**

```bash
.venv/Scripts/python.exe -c "import pymupdf; print(pymupdf.__version__)"  # 1.27.2.3
.venv/Scripts/python.exe -c "from PIL import Image; print(Image.__version__)"  # 12.2.0
```

兩者都已固定在 CLAUDE.md 鎖定範圍(`PyMuPDF>=1.27,<1.28`、`Pillow>=12,<13`)。

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────── BROWSER (thin client) ───────────────┐
│  Upload (PDF or PNG/JPG/TIFF, single dropzone)      │
│    │                                                  │
│    ▼                                                  │
│  Preview viewer / region selection (UNCHANGED)        │
└─────────────────────────────────────────────────────┘
          │  multipart POST /sessions
          ▼
┌─────────────── API LAYER (FastAPI) ──────────────────┐
│  POST /sessions  ──► ingest.ingest_upload(name, bytes) │
│  POST /process   ──► pipeline.process_job (UNCHANGED contract) │
│  GET  /pages/{n}/image, /result, ...   (UNCHANGED)    │
└─────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────── SERVICE LAYER ────────────────────────┐
│                                                        │
│  ingest.py  ◄── NEW: dispatch by magic header         │
│    ├─ PDF      → 沿用 (open_pdf + page_count)         │
│    └─ PNG/JPG/TIFF                                    │
│         ├─ Pillow verify (decompression bomb, format) │
│         ├─ Reject multi-page TIFF (n_frames > 1)       │
│         ├─ Convert CMYK → RGB                          │
│         └─► pdf_engine.image_to_a4_pdf(img, fmt)       │
│              (returns single-page A4 PDF bytes)        │
│                                                        │
│  pdf_engine.py  ◄── fitz isolation seam (only place    │
│                    that imports fitz)                  │
│    ├─ NEW: image_to_a4_pdf(image_bytes, fmt) → bytes  │
│    ├─ NEW: rect_overlaps_image(page, rect) → bool     │
│    ├─ NEW: export IMAGE_PIXELS constant               │
│    └─ existing: render / redact wrappers / save        │
│                                                        │
│  redact.py                                            │
│    ├─ remove_region_vector (Phase 2 logic, renamed)    │
│    └─ NEW: remove_region_raster                        │
│         ├─ apply_redactions(images=IMAGE_PIXELS, ...)  │
│         └─ ONLY text-residual assertion (no drawing)   │
│                                                        │
│  pipeline.py  ◄── new dispatch in process_job loop     │
│    for each region:                                    │
│      if pdf_engine.rect_overlaps_image(page, rect):    │
│        redact.remove_region_raster(page, rect)         │
│      else:                                             │
│        redact.remove_region_vector(page, rect)         │
│      place_logo (UNCHANGED)                            │
│                                                        │
└─────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────── STORAGE (UNCHANGED) ──────────────────┐
│  originals/{sid}/{filename}  ← raw upload bytes        │
│                                  (scan.png / 圖紙.tiff │
│                                  / drawing.pdf —      │
│                                  whatever user sent)   │
│  work/{sid}/source.pdf       ← normalized PDF          │
│                                  (image→A4 or copy)    │
│  outputs/{sid}/{stem}_logoswap.pdf  ← final            │
└─────────────────────────────────────────────────────┘
```

### Recommended Project Structure

不變動。**Phase 4 不新增任何模組** — 所有變更落在現有 `ingest.py` / `pdf_engine.py` / `redact.py` / `pipeline.py` / `config.py` / `web/index.html`。

### Pattern 1: Magic-header dispatch in ingest

**What:** 在 `ingest.ingest_upload` 開頭,在現有「PDF magic sniff」之前,擴張為「四 magic 之一」的 sniff。Sniff 通過 PDF 走原路;sniff 為 image 走新 image 路徑;均不通過 → `unsupported_type` 4xx。

**When to use:** 每一次 upload(現有契約 `POST /sessions` multipart `file` field)。

**Example:**
```python
# Source: empirical — 沿用 Phase 1 ingest._looks_like_pdf 風格

_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_TIFF_LE_MAGIC = b"II*\x00"
_TIFF_BE_MAGIC = b"MM\x00*"
_MAGIC_MAX_OFFSET = 8  # tolerate BOM / leading junk


def _sniff_kind(data: bytes) -> str | None:
    head = data[:1024]
    # PDF sniff matches at any offset 0..8 (existing behavior)
    if 0 <= head.find(_PDF_MAGIC) <= _MAGIC_MAX_OFFSET:
        return "pdf"
    # Image magics MUST match at offset 0 — no leading junk for images
    if head.startswith(_PNG_MAGIC):
        return "png"
    if head.startswith(_JPEG_MAGIC):
        return "jpeg"
    if head.startswith(_TIFF_LE_MAGIC) or head.startswith(_TIFF_BE_MAGIC):
        return "tiff"
    return None
```

**注意:** Image magic 必須落在 offset 0(`startswith`),不像 PDF 容許 BOM offset — PNG/JPEG/TIFF spec 不允許 leading bytes。

### Pattern 2: Pillow ingest pipeline(image branch)

**What:** Sniff 為 image 後,呼叫 Pillow 解碼鏈做精細驗證(verify → reopen → n_frames check → format check → mode check)再正規化。

**When to use:** D-12 sniff 通過後,做為 image 路徑 ingest 的內部步驟。

**Example:**
```python
# Source: empirical + [CITED: pillow.readthedocs.io/en/stable/reference/Image.html]
import io
from PIL import Image, UnidentifiedImageError

# Phase 4 ingest sets MAX_IMAGE_PIXELS ONCE at module load(同 Phase 3 logo.py 的 verify 路徑)
# Default 89,478,485 是夠用且 Pillow 12 標準值;不需 override unless 要更嚴 (e.g. 40_000_000 對齊
# MAX_RENDER_PIXELS 邊界,但這會把合理影像也擋掉;建議沿用 Pillow default)。


def _ingest_image(data: bytes, sniff_kind: str) -> bytes:
    """Validate untrusted image bytes; return raw bytes to pass into image_to_a4_pdf."""
    try:
        # Step 1: verify() 跑 header-level sanity check (decompression bomb, broken structure)
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format  # CRITICAL: read BEFORE verify() — verify() invalidates the obj
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise IngestError("corrupt_image", "影像檔案損壞或無法解析。") from exc

    # Step 2: verify() 結束後物件不能再用 — 重新 open 做 multi-page / mode 檢查 + load 像素
    try:
        with Image.open(io.BytesIO(data)) as img:
            # D-02: reject multi-page TIFF
            n_frames = getattr(img, "n_frames", 1)
            if n_frames > 1:
                raise IngestError(
                    "multi_page_tiff_unsupported",
                    "暫不支援多頁 TIFF,請先拆成單頁 TIFF 再上傳。",
                )
            # Format must be one of the allowed set (defence-in-depth: sniff already filtered)
            if fmt not in ("PNG", "JPEG", "TIFF"):
                raise IngestError("unsupported_type", f"不支援的影像格式:{fmt}。")
            # D-03: CMYK → RGB normalization (also covers L / P / LA / RGBA → RGB)
            #   We force RGB to avoid PyMuPDF Pitfall 5 CMYK black-box; alpha is dropped (the
            #   image is composited onto white A4 background anyway via insert_image).
            if img.mode != "RGB":
                img = img.convert("RGB")
            # Step 3: force pixel decode (verify() only checks headers — load actually decodes)
            img.load()
            # Return the normalized bytes — re-encode as JPEG (smaller) if origin was JPEG, else PNG
            # to keep alpha-channel-removed-to-white roundtrip lossless
            buf = io.BytesIO()
            if sniff_kind == "jpeg":
                img.save(buf, format="JPEG", quality=90)
            else:
                img.save(buf, format="PNG")
            return buf.getvalue()
    except IngestError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise IngestError("corrupt_image", "影像檔案損壞或無法解析。") from exc
```

**注意要點:**
1. `verify()` 之後的 image object 無效 — 必須 `Image.open` 第二次。這是 Pillow 已知特性 `[CITED: pillow.readthedocs.io/en/stable/reference/Image.html — Image.verify]`。
2. `img.format` 必須在 `verify()` **之前**讀(同 Phase 3 logo.py 已有的 pattern)。
3. `getattr(img, "n_frames", 1)` 對 PNG/JPEG 安全(它們的 PIL 物件沒有 `n_frames` 屬性 → fallback 1);對 TIFF 才會 > 1。
4. `img.load()` 是真實像素解碼點 — verify() 只 sanity check headers,沒有走 IDAT/JPEG data path;真正的 corrupt-payload 在 load() 時才會 raise。

### Pattern 3: Image → A4 PDF in pdf_engine seam

**What:** 把驗證/正規化後的 image bytes 轉成單頁 A4 PDF bytes。**這是 fitz 的工作 — 必須在 `pdf_engine.py`**(AGPL seam invariant)。

**When to use:** Ingest image 路徑的最後一步 — 產出的 PDF bytes 寫進 `work/{sid}/source.pdf`(走 `storage.write_work_copy`)。

**Example:**
```python
# Source: empirical — 本機實測能跑 (PyMuPDF 1.27.2.3)
# Lives in pdf_engine.py (AGPL seam)

# A4 in PDF points (1 pt = 1/72")
A4_WIDTH_PT = 595.0
A4_HEIGHT_PT = 842.0


def image_to_a4_pdf(image_bytes: bytes) -> bytes:
    """Wrap an already-validated, RGB-normalized image into a single-page A4 PDF.

    Returns PDF bytes ready for storage.write_work_copy. The image is centered and
    fit-in-page (keep_proportion=True), with white background filling the remainder.
    """
    doc = fitz.open()  # empty PDF
    try:
        page = doc.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
        # insert_image with the FULL PAGE rect + keep_proportion=True → centered + contained.
        # PyMuPDF docs: "The image will be inserted centered, normally fully using at least
        # one of width or height of the rectangle but keeping its aspect ratio."
        page.insert_image(page.rect, stream=image_bytes, keep_proportion=True)
        # Save to bytes (not file) so the caller can write_work_copy without an extra tmp file.
        # garbage=4, deflate=True, clean=True keeps the wrapper PDF lean.
        return doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
```

**Verified facts:**
1. `Document.new_page(width=595, height=842)` 接受 A4 點尺寸 `[VERIFIED: 本機實測]`。
2. `page.insert_image(rect, stream=bytes, keep_proportion=True)` 對 PNG / JPEG bytes 都接受;**JPEG 是 byte-exact passthrough**(實測 8229 → 8229 bytes,`extract_image` 回 `ext='jpeg'`)`[VERIFIED: 本機實測]`。
3. `keep_proportion=True` 是「contain + center」語意 — 影像保持長寬比、置中,長寬比與框不符處留白(PDF 頁面背景白)`[CITED: github.com/pymupdf/PyMuPDF/wiki/How-to-Insert-new-PDF-Pages,-Images-and-Text]`。
4. `doc.tobytes()` 接受與 `doc.save()` 相同的 `garbage/deflate/clean` 參數 `[CITED: pymupdf.readthedocs.io/en/latest/document.html]`。

### Pattern 4: Rect-overlaps-image probe in pdf_engine seam

**What:** 對 page 上每個 image XObject 的 placed-bbox 做 AABB 重疊測試,任一重疊就回 True。

**When to use:** `pipeline.process_job` 每框迴圈中,在呼叫 `redact.remove_region_*` 之前。

**Example:**
```python
# Source: empirical — page.get_images() / page.get_image_rects(xref) 為官方 API
# Lives in pdf_engine.py (AGPL seam)


def rect_overlaps_image(page: "fitz.Page", rect: "fitz.Rect") -> bool:
    """True iff ``rect`` (unrotated-page points) overlaps any image XObject on ``page``.

    Uses page.get_images() to enumerate every image xref placed on the page, then
    page.get_image_rects(xref) for each one's placed bbox(es) — an image may appear at
    multiple positions on the same page, so get_image_rects returns a LIST of Rects.
    Any AABB overlap → True; no overlaps → False.

    NOTE: get_image_rects returns Rects in UNROTATED-page space (same space as ``rect``),
    so no rotation matrix is needed here. Both inputs are normalized.
    """
    # rect_normalized so caller can pass a freshly-mapped Rect without worrying about ordering
    q = fitz.Rect(rect)
    q.normalize()
    for entry in page.get_images():
        xref = entry[0]
        for img_rect in page.get_image_rects(xref):
            ir = fitz.Rect(img_rect)
            ir.normalize()
            # AABB overlap, inclusive
            if ir.x0 <= q.x1 and q.x0 <= ir.x1 and ir.y0 <= q.y1 and q.y0 <= ir.y1:
                return True
    return False
```

**Verified facts:**
1. `page.get_images()` 回 tuple list,`entry[0]` = xref `[CITED: pymupdf.readthedocs.io/en/latest/page.html]` + `[VERIFIED: 本機實測,build_pdf() → get_images: [(11, 0, 800, 600, 8, 'ICCBased', '', 'Im1', '')]`。
2. `page.get_image_rects(xref)` 回 `[fitz.Rect, ...]` — 一個 image 可能放在 page 上多個位置(`[CITED: pymupdf.readthedocs.io/en/latest/page.html]`)。實測 single image PDF 回 `[Rect(0.0, 197.875, 595.0, 644.125)]`(因為 keep_proportion 把 800x600 image 在 A4 上 letterbox 到上下各留白)。
3. `get_image_rects` 回傳的 Rect 已在 unrotated-page 空間 — 跟 Phase 2 mapper 產出的 rect 是同一空間,**無需再用 derotation_matrix**。

### Pattern 5: Split redact entry points + raster-only text assertion

**What:** Phase 2 的單一 `redact.remove_region` 拆成兩個 explicit entry point。Pipeline 在 dispatch 時叫對應的。

**When to use:** 每框 redact 時。

**Example:**
```python
# Source: refactor of existing redact.remove_region — split into two named entry points
# Lives in redact.py (still fitz-free; all engine access via pdf_engine wrappers)


def remove_region_vector(page, rect) -> bool:
    """Phase 2 logic, renamed. fill=None + images=IMAGE_NONE.
    Asserts BOTH text-residual AND drawings-fully-inside-residual = empty."""
    # ... existing Phase 2 body unchanged ...


def remove_region_raster(page, rect) -> bool:
    """NEW Phase 4 path. fill=None + images=IMAGE_PIXELS.
    Asserts ONLY text-residual = empty (drawings assertion skipped — see below)."""
    user_rect = (rect.x0, rect.y0, rect.x1, rect.y1)
    if _is_empty(user_rect):
        return False

    # SHORT-CIRCUIT: if nothing extractable AND no image overlap (somehow), nothing to do.
    # The pipeline only routes here when rect_overlaps_image is True, so we assume image
    # overlap exists. We still skip if there's literally no text and no drawings AND we
    # were called by mistake — keeps the contract identical to vector branch's "nothing
    # to remove" notice.
    had_text = bool(pdf_engine.get_text_words_in_rect(page, user_rect))
    # NOTE: had_image is implicit (pipeline only routes here when image overlap exists)
    # We don't probe drawings here — a raster page can have legitimate vector annotations
    # (text layer over a scan) which is exactly the D-06 dual-layer case we DO want redacted.

    # fill=None (NOT (1,1,1)): same justification as vector branch + we proved empirically
    # that fill=(1,1,1) leaves a survivor type='fs' drawing in raster branch too (which
    # would also violate the "no cover, true removal" invariant). IMAGE_PIXELS itself
    # blanks the pixels to white — no annot fill needed.
    padded = _pad(rect, REDACT_PAD_PT)
    padded_fitz = pdf_engine.map_tuple_to_rect(padded)
    pdf_engine.add_redact_annot(page, padded_fitz, fill=None)

    pdf_engine.apply_redactions(
        page,
        text=pdf_engine.TEXT_REMOVE,                          # D-06 dual-layer cleanup
        graphics=pdf_engine.LINE_ART_REMOVE_IF_COVERED,       # keep crossing lines (CR-02)
        images=pdf_engine.IMAGE_PIXELS,                       # NEW — blanks overlap pixels
    )

    # Raster-branch assertion: TEXT ONLY.
    #   - TEXT residual: still the recoverable-content risk (especially OCR layer leaks
    #     under a scan, D-06 / Pitfall 3 dual-layer). Must be empty.
    #   - DRAWINGS residual: in raster mode, legitimate drawings can co-exist (annotations
    #     on a scan, a vector signature on a stamped PDF). LINE_ART_REMOVE_IF_COVERED still
    #     applies, so a drawing fully inside the rect IS removed, but the assertion is
    #     skipped because (a) the "true removal" guarantee for raster mode is the IMAGE_PIXELS
    #     pixel-blank (not the drawing graph), and (b) the raster region is allowed to
    #     contain background graphics that the user didn't intend to remove (e.g. a CAD
    #     border that crosses the scan). Skipping drawings here matches the user-facing
    #     contract for raster: "the visible pixels in the frame are gone."
    residual_words = pdf_engine.get_text_words_in_rect(page, user_rect)
    if residual_words:
        raise RedactError(
            "residual_content",
            "移除後仍偵測到殘留文字,無法保證真正移除。",
        )

    return True
```

**Why split entry points (vs single entry + internal branch):**
1. Reader clarity — `pipeline.process_job` 讀者一眼看到 `if overlaps_image: remove_region_raster else: remove_region_vector`,不需要鑽進 redact 看分支。
2. Different assertions — vector 分支有 text + drawings 兩個斷言,raster 分支只有 text(且 vector 分支的 drawings 斷言不能 raster 沿用,因 raster 區允許合法繪圖)。把不同斷言留在不同 function 裡比「在同一 function 內 if-else 走兩條斷言路徑」乾淨。
3. 未來擴充 — Phase 5 deferred 的 per-region 模式(讓 user 選「整張拔 / 局部白」)很自然地在 raster 那條再拆,vector 那條不動。
4. 測試 — 每個 entry point 可以獨立 fixture(vector PDF / image-only PDF)直跑,不需要 mock dispatch。

### Pattern 6: Pipeline dispatch loop

**What:** `process_job` 在現有「clamp → map → redact」迴圈中,在 redact 前插入 1 行 dispatch。

**Example:**
```python
# Source: pipeline.process_job — additive change in the per-region loop body
for region in job_spec.regions:
    page_no = region.page
    # ... existing validation, clamp, map (UNCHANGED) ...
    page = pdf_engine.get_page(doc, page_no)
    # ... effective_dpi, clamped_px, pdf_rect (UNCHANGED Phase 2 logic) ...

    # NEW (Phase 4): dispatch by image-overlap probe in PDF point space.
    # rect_overlaps_image takes an unrotated-page rect — exactly what pixels_to_pdf_rect
    # produces — so no extra conversion.
    if pdf_engine.rect_overlaps_image(page, pdf_rect):
        removed = redact.remove_region_raster(page, pdf_rect)
    else:
        removed = redact.remove_region_vector(page, pdf_rect)

    # Logo placement, dedup, results.append — UNCHANGED from Phase 3
    # ...
```

### Anti-Patterns to Avoid

- **在 ingest.py 直接 `import fitz`** — 違反 Phase 1–3 已執行的 AGPL seam(`test_fitz_import_confined_to_engine_seam` 會 fail);影像 → A4 PDF 必須走 `pdf_engine.image_to_a4_pdf` 包裝。
- **Raster 分支用 `fill=(1,1,1)` + 同樣的 `get_drawings_fully_inside` 殘留斷言** — 實測會自我打臉(annot 留下的填色 drawing 恰好 `fully_inside` redact rect,直接觸發 RedactError)。
- **Multi-page TIFF 偷偷走 `seek(0)` 只取首頁** — 違反 D-02;且 ingest 不應該對 user 上傳的內容做隱性裁剪。
- **`Image.open(BytesIO).load()` 不先 verify** — verify() 是 decompression-bomb 防護的入口(Pillow header-level sanity check);跳過 verify 直接 load 等於關掉防護。
- **以 user-supplied filename 推斷 image format**(`.png` extension 信任 PNG)— D-12 / Phase 1 T-01-06 已立的原則,extension 不可信。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 整頁掃描 PDF 框選區 pixel blank | 自己用 NumPy 切 pixmap、貼白方塊、寫回 | `apply_redactions(images=PDF_REDACT_IMAGE_PIXELS)` | PyMuPDF 直接在 PDF object 層處理(實測 garbage=4 後 6KB);手切 pixmap 等於把整頁變成新 image 重新嵌(肥且失去 PDF 原有的 image object 結構) |
| Image → A4 PDF 自己包 | 自己算 fit 比例、用 PyMuPDF `draw_rect` 畫白底再 `insert_image` | `Document.new_page(595, 842)` + `page.insert_image(page.rect, stream=..., keep_proportion=True)` | PyMuPDF 的 `keep_proportion=True` 已 "centered + fit-in-page",PDF 頁面背景本就白 — 不需畫白底 |
| Multi-page TIFF 偵測 | 自己讀 TIFF directory bytes(IFD offset chain) | `getattr(img, "n_frames", 1) > 1` | Pillow 已實作,且對所有 TIFF variants(BigTIFF、tiled、stripped)一致 |
| Decompression bomb 防護 | 自己看 pixel dimensions、計算記憶體佔用 | `Image.MAX_IMAGE_PIXELS` + `Image.open(...).verify()` | Pillow 預設 89,478,485 px,> 2× 直接 raise DecompressionBombError;`verify()` 是入口 |
| CMYK → RGB | 自己用 NumPy 跑 CMYK → RGB matrix | `img.convert("RGB")` | 一行,且 Pillow 處理 color profile / ICC tagging 比手刻好 |
| Magic header sniff | regex / 自己寫 byte-by-byte loop | `data.startswith(_MAGIC)` + Phase 1 既有 `_looks_like_pdf` pattern | 已存在的 pattern;Phase 1 已測 |

**Key insight:** Phase 4 的所有「看起來像新功能」的能力,PyMuPDF + Pillow 各佔一半都已實作好。Researcher 實測證實 `apply_redactions(images=IMAGE_PIXELS)` 在所有測試場景(部分重疊 / 全頁覆蓋 / 雙層 OCR)都符合 REMOVE-02 語意 — 沒有任何 case 需要自己跑 numpy 像素操作。Phase 4 的工作量都在「黏接層」(ingest dispatch、pipeline dispatch、entry-point 拆分),不在「PDF 處理本身」。

## Runtime State Inventory

> Phase 4 是純功能擴張,不涉及 rename / refactor / migration。**SKIPPED** — 無相關 runtime state。

## Common Pitfalls

### Pitfall A: Raster 分支 `fill=(1,1,1)` 留下 `type='fs'` 填色 drawing(打臉 Phase 2 殘留斷言)

**What goes wrong:** 沿用 Phase 2 `add_redact_annot(rect, fill=(1,1,1))` 配合新的 `images=IMAGE_PIXELS` — 看起來合理,但 `apply_redactions` 完之後 `get_drawings()` 多了一個 `{type:'fs', rect: 跟 redact_rect 一樣, fill:(1,1,1)}` 的填色 drawing,直接被 `get_drawings_fully_inside` 抓出來,觸發 RedactError("residual_content")。

**Why it happens:** PyMuPDF 把 `add_redact_annot` 的 `fill` 參數翻成「redact 結束後在那塊區域畫一個 filled drawing」— 這個 drawing 是真實的 page content,不是 annotation。`fill=None` 則完全不畫。`[VERIFIED: 本機實測,fill=(1,1,1) → drawings count: 1; fill=None → drawings count: 0]`

**How to avoid:** Raster 分支也用 `fill=None` — `IMAGE_PIXELS` 已經把重疊像素變白(實測),annot fill 完全是多餘的且會引入假陽性。**這是本研究推翻 CONTEXT.md 中「raster 用 fill=(1,1,1) 是 REMOVE-02 字面要求」這條傾向的核心證據。**

**Warning signs:**
- Raster 分支的整合測試在「框內有任何 image overlap」case 一律 RedactError("residual_content")。
- `get_drawings()` 回傳數量在 redact 後反而增加。

### Pitfall B: 把 `fill=(1,1,1)` 跟 `IMAGE_PIXELS` 視為兩個獨立決策

**What goes wrong:** Researcher / planner 看 REMOVE-02 寫「以白色填滿」,直覺認定 raster 區一定要用 `fill=(1,1,1)` annot 才能「白色填滿」— 跟 PyMuPDF 內部 `IMAGE_PIXELS` 已經把像素變白的事實重疊。

**Why it happens:** PyMuPDF 文件對「fill 之於 raster 分支」沒講清楚 — fill 字面是「redact 後畫到 rect 裡的顏色」,但對 image 不是 image pixel,是 page content stream 的填色 drawing。實測 `IMAGE_PIXELS` 自己已經把 image pixels 變白(實測 fill=None 也是白)。

**How to avoid:** 把 D-09 拆成兩個獨立判定:
1. **像素是否要變白?** → `IMAGE_PIXELS` 已負責,REMOVE-02 字面已滿足。
2. **是否要在 page 上多畫一個 fill drawing?** → `fill=None` 不畫(避免假陽性),`fill=(1,1,1)` 會畫(製造殘留斷言失敗)。

### Pitfall C: Multi-page TIFF 矽然走 frame 0

**What goes wrong:** 不檢 `n_frames`,`Image.open(BytesIO(tiff_bytes))` 直接拿到第 0 個 frame 處理 — user 上傳的是 5 頁的 multi-page TIFF,只有第 1 頁被處理,user 不知道其他 4 頁被吞了。

**Why it happens:** Pillow 對 multi-page TIFF 預設只給 frame 0,要顯式 `seek(N)` 才會切到其他 frame。

**How to avoid:** `getattr(img, "n_frames", 1) > 1` 顯式檢查,raise `multi_page_tiff_unsupported` 4xx(D-02)。對 PNG / JPEG 不會 false-positive(它們沒有 n_frames 屬性,getattr fallback 1)。`[CITED: pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#tiff]`

### Pitfall D: CMYK / SMask image black-box

**What goes wrong:** Pitfall 5(專案研究):CMYK TIFF 或 PNG with SMask 走 `IMAGE_PIXELS` 後出現黑框,不是白底。

**Why it happens:** PyMuPDF 對 non-RGB / 帶 alpha mask 的 image 在 redact 重寫時的 fallback path 是「填 0」 — 對 RGB = 黑,對 CMYK 也通常 = 暗。

**How to avoid:** D-03 — ingest 階段強制 `img.convert("RGB")` 後再嵌入。這也是為什麼 image_to_a4_pdf 不直接收原始 bytes、而是收 ingest 已經 convert 過的 bytes — convert 必須在 ingest 完成,不能延後。

### Pitfall E: 整頁掃描 PDF 雙層 OCR 文字殘留

**What goes wrong:** 框選整張 → `images=IMAGE_PIXELS` 把底圖像素變白,但 OCR 文字層還在 PDF object stream,user 還能 Ctrl+A copy 出供應商商標文字。

**Why it happens:** Pitfall 3(雙層 leak)。`IMAGE_PIXELS` 只處理 image XObject;文字物件要靠 `text=TEXT_REMOVE`。

**How to avoid:** Raster 分支必須**同時**設 `images=IMAGE_PIXELS` 與 `text=TEXT_REMOVE`(D-06)。實測證實 PyMuPDF 在單一 `apply_redactions` 呼叫中兩個 flag 一起跑沒問題、文字也清乾淨 `[VERIFIED: 本機實測雙層 OCR fixture]`。Raster 分支保留 text 殘留斷言是這條 leak 的最後一道網。

### Pitfall F: IMAGE_PIXELS 重寫成 uncompressed PNG 導致檔肥

**What goes wrong:** 上傳 50KB 的影像 PDF,redact 後 outputs/ 變 2.88 MB(實測)— PyMuPDF `IMAGE_PIXELS` 重寫 image XObject 時用 uncompressed PNG。

**Why it happens:** Pitfall 5 / PyMuPDF discussion #2644。`IMAGE_PIXELS` 重寫的 image 沒有套用 deflate。

**How to avoid:** D-10 `doc.save(garbage=4, deflate=True, clean=True)` — 實測 2.88 MB → 6 KB(~480× 壓縮)`[VERIFIED: 本機實測]`。**現有 `pdf_engine.save_doc()` 預設已有這三個 flag**(Phase 1–3 已加),Phase 4 不需新增 save call,只要確認 raster 分支經過該 wrapper。

### Pitfall G: PNG transparent 影像觸發 PyMuPDF segfault

**What goes wrong:** Pitfall 5 / issue #1824 — 部分 transparent PNG 在 `apply_redactions` 走 IMAGE_PIXELS 時 segfault(透過 mask 結構造成 MuPDF C 層 crash)。

**Why it happens:** Pillow / PyMuPDF 對 PNG alpha mask 的處理 path 有 known bug。

**How to avoid:** D-03 在 ingest 階段把 alpha drop(`img.convert("RGB")` 從 RGBA 過去等於 alpha 合成到白底);影像進 work/ 之前就已經沒有 alpha,IMAGE_PIXELS 不會走 segfault 的 mask path。

### Pitfall H: 副檔名信任

**What goes wrong:** 把 ELF binary 改名 `.png` 上傳,擴展接受 image 後 Pillow `Image.open` raise UnidentifiedImageError 變 500。

**Why it happens:** Pitfall 11 / Phase 1 T-01-06。trust extension 永遠不安全。

**How to avoid:** D-12 — 全部 4 個 magic 在 ingest **content-sniff**,且 image 路徑 sniff 通過後**再**走 Pillow verify(雙層防護)。任何 Pillow 失敗對應 `corrupt_image` 4xx(typed error)、絕不 escape 為 500。

## Code Examples

### Example 1: ingest dispatch (擴張現有 ingest_upload)

```python
# Source: based on existing app/services/ingest.py — additive change

def ingest_upload(filename: str, data: bytes) -> SessionInfo:
    if not data:
        raise IngestError("empty_file", "檔案是空的,請選擇有內容的 PDF 或影像。")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise IngestError(
            "file_too_large",
            f"檔案過大,超過大小上限 {config.MAX_UPLOAD_MB} MB。",
        )

    kind = _sniff_kind(data)
    if kind is None:
        raise IngestError(
            "unsupported_type",
            "不支援的檔案類型,僅接受 PDF、PNG、JPG、TIFF。",
        )

    if kind == "pdf":
        # Existing Phase 1 path
        return _ingest_pdf(filename, data)  # refactored body
    else:
        # NEW Phase 4 image path
        return _ingest_image_to_pdf(filename, data, kind)


def _ingest_image_to_pdf(filename: str, data: bytes, kind: str) -> SessionInfo:
    """Image → A4 PDF; originals/ stores raw image bytes, work/ stores PDF."""
    # 1. Pillow validate + normalize (CMYK→RGB, reject multi-page TIFF)
    normalized_bytes = _ingest_image(data, kind)  # see Pattern 2

    # 2. Wrap into single-page A4 PDF (fitz seam)
    pdf_bytes = pdf_engine.image_to_a4_pdf(normalized_bytes)

    # 3. Sanity: open the produced PDF to validate + count pages (always 1 here, but DRY)
    doc = None
    try:
        doc = pdf_engine.open_pdf(pdf_bytes)
        n_pages = pdf_engine.page_count(doc)
        # n_pages should be 1; defensive cap is the same MAX_PAGES = 30 sanity gate
        if n_pages < 1 or n_pages > config.MAX_PAGES:
            raise IngestError("corrupt_pdf", "正規化失敗,影像無法產出有效 PDF。")
    finally:
        if doc is not None:
            pdf_engine.close(doc)

    # 4. Persist: originals/ = raw image bytes (D-04 semantics — what user actually sent);
    #    work/ = PDF (normalized) — pipeline / render only ever sees PDF.
    session_id = storage.new_session()
    safe_name = storage.sanitize_filename(filename)
    storage.write_original(session_id, safe_name, data)  # raw image bytes
    storage.write_work_copy(session_id, pdf_bytes)        # A4 PDF bytes
    storage.write_session_meta(session_id, page_count=n_pages, filename=safe_name)

    return SessionInfo(session_id=session_id, page_count=n_pages, filename=safe_name)
```

### Example 2: pdf_engine 新增的兩個 helper + 一個常數

```python
# Source: new additions to app/services/pdf_engine.py (fitz seam)

# --- new constant export (alongside IMAGE_NONE) ---
IMAGE_PIXELS = fitz.PDF_REDACT_IMAGE_PIXELS  # = 2


# --- new helper: image → A4 PDF ---
A4_WIDTH_PT = 595.0
A4_HEIGHT_PT = 842.0


def image_to_a4_pdf(image_bytes: bytes) -> bytes:
    """Wrap validated, RGB-normalized image bytes into a single-page A4 PDF.
    Returns PDF bytes ready for storage.write_work_copy."""
    doc = fitz.open()
    try:
        page = doc.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
        page.insert_image(page.rect, stream=image_bytes, keep_proportion=True)
        return doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


# --- new helper: rect overlaps any image on page ---
def rect_overlaps_image(page: "fitz.Page", rect: "fitz.Rect") -> bool:
    """True iff rect (unrotated-page points) overlaps any image XObject placed on page."""
    q = fitz.Rect(rect)
    q.normalize()
    for entry in page.get_images():
        xref = entry[0]
        for img_rect in page.get_image_rects(xref):
            ir = fitz.Rect(img_rect)
            ir.normalize()
            if ir.x0 <= q.x1 and q.x0 <= ir.x1 and ir.y0 <= q.y1 and q.y0 <= ir.y1:
                return True
    return False
```

### Example 3: pipeline.process_job 迴圈 dispatch(新增 1 行)

```python
# Source: app/services/pipeline.py — minimal change in the per-region loop

for region in job_spec.regions:
    # ... UNCHANGED Phase 2-3 boilerplate: page_no validation, clamp_px_rect,
    #     effective_dpi computation, coords.pixels_to_pdf_rect ...
    pdf_rect = coords.pixels_to_pdf_rect(clamped_px, effective_dpi, page)

    # NEW: dispatch by image-overlap.
    if pdf_engine.rect_overlaps_image(page, pdf_rect):
        removed = redact.remove_region_raster(page, pdf_rect)
    else:
        removed = redact.remove_region_vector(page, pdf_rect)

    # ... UNCHANGED Phase 3 logo placement, results.append ...
```

### Example 4: dropzone copy + accept update

```html
<!-- Source: web/index.html — additive attribute + copy update -->

<h2 class="dropzone__heading">上傳 PDF 或影像以開始</h2>
<p class="dropzone__body">
  選擇或拖曳一個 PDF 或影像檔案(PNG、JPG、TIFF),即可在此預覽並框選要替換的商標。原始檔案不會被更動。
</p>
<button type="button" id="choose-file" class="primary-btn">選擇檔案</button>
<p class="dropzone__hint">支援 PDF、PNG、JPG、TIFF(單一檔案)</p>
<input
  type="file"
  id="file-input"
  class="visually-hidden"
  accept="application/pdf,.pdf,image/png,image/jpeg,image/tiff,.png,.jpg,.jpeg,.tif,.tiff"
/>
```

**aria-label** 同步從「選擇 PDF 檔案」改成「選擇 PDF 或影像檔案」。

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 2:`redact.remove_region` 單一 entry,hard-coded `images=IMAGE_NONE` | Phase 4:`remove_region_vector` / `remove_region_raster` 兩個 entry,dispatch 由 pipeline 控制 | Phase 4 | 讀者直接看 dispatch、不同斷言留在不同 function、未來 per-region 模式自然擴 |
| 影像型 PDF 走 vector 分支(目前 — `IMAGE_NONE`)| 影像型 PDF 框選區走 raster 分支(`IMAGE_PIXELS`)| Phase 4 | 之前對 image-only PDF 框選等於 no-op(redact 跑了但 image pixels 未動,且 `get_drawings_fully_inside` 為空 → 不 raise — 是無聲失敗!**這是 Phase 2 在 image-only PDF 上「假成功」的盲點,Phase 4 才補上 IMAGE_PIXELS path**)|
| 單一 PDF dropzone | PDF + PNG + JPG + TIFF dropzone | Phase 4 | UPLOAD-02 + UPLOAD-03 完成 |
| Phase 1 ingest 只 sniff `%PDF-` | 4-magic sniff(PDF / PNG / JPEG / TIFF)| Phase 4 | image upload 上線;extension 不可信原則延伸 |
| `pdf_engine` 只 export `IMAGE_NONE` | 加 export `IMAGE_PIXELS` | Phase 4 | redact.raster 分支可呼叫該常數而不必 import fitz |

**Deprecated/outdated:**
- ~~Raster 分支「fill=(1,1,1) 配 IMAGE_PIXELS」~~ — 本研究實測證實會留 type=fs 殘留 drawing。Phase 4 兩個分支都用 `fill=None`,白色填滿由 IMAGE_PIXELS 自身達成。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| (none) | — | — | 本研究關鍵宣稱皆已 `[VERIFIED]`(本機 PyMuPDF 1.27.2.3 + Pillow 12.2.0 實測)或 `[CITED]`(PyMuPDF / Pillow 官方 docs);無 `[ASSUMED]` |

**Assumption table 是空的,代表本研究所有事實聲明都已用工具驗證或引用官方文件。**

兩個次要邊角(都不影響 Phase 4 必須做的工作,只影響未來擴充):

1. **OCG / 隱藏層 redaction 行為**:研究不涵蓋(D-07 / deferred — Phase 5)。Phase 4 redact 不對 OCG 層做任何特殊處理 — sole behavior 是 PyMuPDF 預設(對「目前可見的層」做 redact,隱藏層 known rough edge per Pitfall 8)。沒有風險,因為 Phase 4 deferred 列明排除。

2. **TIFF with non-baseline tags / BigTIFF / multi-strip**:研究沒實測 BigTIFF / unusual TIFF variant。Pillow 12 對標準 TIFF / BigTIFF 都支援(`[CITED: pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#tiff]`),但極端 case(e.g. TIFF with custom tag)可能 verify 失敗 → 落到 `corrupt_image` 4xx — 屬可接受 graceful degradation(D-12)。

## Open Questions

1. **影像 ingest 是否需要新 config 常數 `MAX_IMAGE_PIXELS_PER_FRAME`?**
   - What we know:Pillow 預設 `MAX_IMAGE_PIXELS = 89,478,485`(~89 MP);專案現有 `MAX_RENDER_PIXELS = 40 MP`(WR-06 — render 階段的 pixel budget)。
   - What's unclear:應該對齊到 40 MP(更嚴格,跟 render 一致)還是沿用 Pillow default 89 MP(讓 ingest 接收 → render 才 fit_dpi 縮)?
   - Recommendation:**沿用 Pillow default 89 MP** — ingest 拿到 89 MP 影像 → image_to_a4_pdf 把它包成 A4 PDF(影像在 PDF 內仍是 ~89 MP pixmap,但 PDF 物件大小只是 image stream)→ render 階段 `fit_dpi_to_pixel_budget` 把 render DPI 縮到 40 MP 預算內。把 ingest 卡到 40 MP 等於提前拒收(對使用者體驗較差),且 image_to_a4_pdf 沒有 render 那個 pixel budget 問題(它只是嵌入,不展開像素)。Planner 若認為要更保守,可在 config.py 加 `MAX_INGEST_IMAGE_PIXELS = 89_478_485` 顯式化此值。

2. **JPEG 重壓參數 quality=90 是否合適?**
   - What we know:`Image.save(buf, format="JPEG", quality=90)` 是壓縮品質設定;quality=90 是「視覺無損的常見上限」、quality=85 是「web 標準」。
   - What's unclear:本工具的目標 PDF 可能用於簽核 / 印刷預覽,商標清晰度與檔案大小哪個優先?
   - Recommendation:**quality=90**(視覺無損優先,因為下游可能再列印 / 對外簽核;檔肥差不多 ~20% vs quality=85,可接受)。Planner 可在 config.py 加 `JPEG_REENCODE_QUALITY = 90` 顯式化。

3. **`getattr(img, "n_frames", 1)` 對 GIF / WebP / 動畫 PNG 是否會誤通過?**
   - What we know:Phase 4 不支援 GIF / WebP / APNG(magic sniff 沒列入)— 它們在 D-12 sniff 階段就被擋掉(`_sniff_kind` 回 None → unsupported_type 4xx)。
   - What's unclear:N/A — sniff 已防護。
   - Recommendation:無需 action;這條 question 是為了確認 deferred 邏輯正確。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PyMuPDF (`pymupdf`) | image_to_a4_pdf、rect_overlaps_image、apply_redactions(IMAGE_PIXELS) | ✓ | 1.27.2.3 | — |
| Pillow (`PIL`) | image verify / convert / n_frames check | ✓ | 12.2.0 | — |
| Python `io.BytesIO` | image bytes stream | ✓ | stdlib | — |

**Missing dependencies with no fallback:** 無。
**Missing dependencies with fallback:** 無。

`[VERIFIED: 本機 .venv]` — 兩個 lib 都已在 venv,版本與 CLAUDE.md 鎖定一致。

## Validation Architecture

> nyquist_validation 在本專案 config 未明示為 false — 本節提供 plan-checker Dimension 8 的指引依據。

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest(Phase 1–3 已用,沿用)|
| Config file | `pyproject.toml`(若有 `[tool.pytest.ini_options]`)/ 否則 default 配置 |
| Quick run command | `.venv/Scripts/python.exe -m pytest tests/ -x -q` |
| Full suite command | `.venv/Scripts/python.exe -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UPLOAD-02 | 上傳 image-only PDF,session 建立、page_count=1、original 雜湊不變 | integration | `pytest tests/test_ingest.py::test_image_only_pdf_upload -x` | ❌ Wave 0 |
| UPLOAD-02 | image-only PDF 框選後輸出仍能看到供應商內容(reverse) | integration | `pytest tests/test_pipeline.py::test_raster_branch_full_page_no_residual -x` | ❌ Wave 0 |
| UPLOAD-03 | PNG 上傳 → originals/ 是原始 PNG bytes、work/ 是 PDF、session.page_count=1 | integration | `pytest tests/test_ingest.py::test_png_upload_normalizes_to_a4_pdf -x` | ❌ Wave 0 |
| UPLOAD-03 | JPEG 上傳 byte-exact passthrough(work/ PDF 內嵌入仍是 JPEG)| integration | `pytest tests/test_ingest.py::test_jpeg_passthrough -x` | ❌ Wave 0 |
| UPLOAD-03 | TIFF 多頁拒絕(`multi_page_tiff_unsupported` 4xx)| unit | `pytest tests/test_ingest.py::test_multi_page_tiff_rejected -x` | ❌ Wave 0 |
| UPLOAD-03 | CMYK image 強制 → RGB(產出 PDF 對應 image colorspace = DeviceRGB / ICCBased RGB)| unit | `pytest tests/test_ingest.py::test_cmyk_normalized_to_rgb -x` | ❌ Wave 0 |
| UPLOAD-03 | 副檔名與 magic 不符(`.png` 但內容是 ELF)→ `unsupported_type` 4xx | unit | `pytest tests/test_ingest.py::test_extension_not_trusted -x` | ❌ Wave 0 |
| REMOVE-02 | Image-only PDF 框選整張 → 結果頁面 pixel 為白(取樣中心像素 == 255,255,255)| integration | `pytest tests/test_redact.py::test_raster_full_page_blank_to_white -x` | ❌ Wave 0 |
| REMOVE-02 | Image-only PDF 部分框選 → 框內白、框外保留(取樣兩個 pixel 位置)| integration | `pytest tests/test_redact.py::test_raster_partial_redact_inside_white_outside_keep -x` | ❌ Wave 0 |
| REMOVE-02 | 雙層 OCR PDF(scan + text layer)框選後 `get_text("words", clip=rect)` 為空 | integration | `pytest tests/test_redact.py::test_dual_layer_ocr_text_residual_empty -x` | ❌ Wave 0 |
| REMOVE-02 | Raster 分支 redact 後 `get_drawings_fully_inside(rect)` 是「fill=None 留 0 drawing」| unit | `pytest tests/test_redact.py::test_raster_fill_none_no_drawing_residual -x` | ❌ Wave 0 |
| (cross) | 三目錄不動性 — image 上傳後 SHA-256 of originals/ entry == SHA-256 of user-supplied bytes | integration | `pytest tests/test_pipeline.py::test_originals_sha256_unchanged_after_image_run -x` | ❌ Wave 0 |
| (cross) | AGPL seam:`import fitz` 與 `import pymupdf` 只在 pdf_engine.py | unit | `pytest tests/test_architecture.py::test_fitz_import_confined_to_engine_seam` | ✓(已存在,Phase 1)|
| (cross) | Phase 3 logo 流程在 image 路徑同樣可用 — PNG 上傳 + logo 置入後 result 含 logo xref | integration | `pytest tests/test_pipeline.py::test_image_upload_with_logo_placement -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/Scripts/python.exe -m pytest tests/test_ingest.py tests/test_redact.py -x -q`(只跑 Phase 4 直接 touch 的測試集合)
- **Per wave merge:** `.venv/Scripts/python.exe -m pytest tests/ -x -q`(全部測試 — Phase 1–3 既有測試確保 regression-free)
- **Phase gate:** Full suite green before `/gsd-verify-work`,且新增 fixture 受版控

### Wave 0 Gaps
- [ ] `tests/fixtures/image_only.pdf` — 內含一張全頁掃描 image 的 PDF(可用 `fitz` script 自製 — `image_to_a4_pdf` 自己的 sanity test 也可順便產出 fixture)
- [ ] `tests/fixtures/dual_layer_ocr.pdf` — image 底圖 + text overlay 的雙層 PDF(`page.insert_image` + `page.insert_text` 自製)
- [ ] `tests/fixtures/scan.png` — 一張用作 PNG 路徑測試的 RGB PNG
- [ ] `tests/fixtures/scan.jpg` — JPEG 路徑測試
- [ ] `tests/fixtures/scan.tiff` — 單頁 TIFF
- [ ] `tests/fixtures/multipage.tiff` — 多頁 TIFF(D-02 reject 路徑)
- [ ] `tests/fixtures/cmyk.tiff` 或 `tests/fixtures/cmyk.jpg` — CMYK 影像(D-03 convert 路徑)
- [ ] `tests/fixtures/not_an_image.png` — ELF / 隨機 bytes 改名 .png(extension-not-trusted 測試)
- [ ] `tests/test_ingest.py` 新增 test cases(Wave 0)
- [ ] `tests/test_redact.py` 擴充 raster branch test cases(Wave 0)
- [ ] `tests/test_pipeline.py` 擴充 image 路徑 integration(Wave 0)

**所有 fixture 都可以用 PyMuPDF + Pillow 在 conftest.py 或 fixture-gen script 自製 — 不需引入外部資料。** 推薦做法:`tests/fixtures/_make_phase4_fixtures.py` 是一個一次性 script,跑完產出所有需要的 PDF / image,版控 fixture 本身(不版控 script 跑時的 venv);這跟 Phase 2 的 fixture pattern 一致。

## Sources

### Primary (HIGH confidence)
- 本機實測(PyMuPDF 1.27.2.3、Pillow 12.2.0)— Question 1/2/4/5 所有事實宣稱,empirical
- PyMuPDF official docs — `Page.apply_redactions`、`Page.add_redact_annot`、`Page.get_images`、`Page.get_image_rects`、`Document.new_page`、`Page.insert_image`:https://pymupdf.readthedocs.io/en/latest/page.html
- Pillow official docs — `Image.MAX_IMAGE_PIXELS`、`Image.verify`、`Image.n_frames`:https://pillow.readthedocs.io/en/stable/reference/Image.html
- Pillow file formats — TIFF n_frames、multi-frame seek:https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#tiff
- 專案 `.planning/research/PITFALLS.md` Pitfall 3 / 5 / 6 / 11(內部 research artifact,HIGH on this project)
- 專案 `.planning/research/ARCHITECTURE.md` Pattern 3、Build Order(內部 research artifact,HIGH)

### Secondary (MEDIUM confidence)
- PyMuPDF discussion #1819(IMAGE_PIXELS 行為與 transparent image edge cases):https://github.com/pymupdf/PyMuPDF/discussions/1819 — 用於 Pitfall G 透明圖 segfault 論據
- PyMuPDF discussion #4657(Acrobat 對 fill 顏色處理 — 本研究無採用但作為 cross-reference):https://github.com/pymupdf/pymupdf/issues/4657
- PyMuPDF wiki — How to Insert new PDF Pages, Images and Text:https://github.com/pymupdf/PyMuPDF/wiki/How-to-Insert-new-PDF-Pages,-Images-and-Text(用於 keep_proportion=True 語意確認)

### Tertiary (LOW confidence)
- (無 — 所有事實聲明均有 PRIMARY 或 SECONDARY 來源,且關鍵 redact / IMAGE_PIXELS 行為已用本機實機驗證)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyMuPDF + Pillow 版本 已 `[VERIFIED]` 本機 venv;沒有新依賴
- Architecture: HIGH — Phase 4 不引入新模組,所有 dispatch / seam 變更都是 additive,延續 Phase 1–3 已驗證的 invariant
- Pitfalls: HIGH — A / B / E / F 由本機實測直接驗證;C / D / G / H 從專案 PITFALLS.md 沿用 + Pillow / PyMuPDF docs 引用
- Validation: HIGH — 測試框架沿用 pytest;Phase 4 新增 test cases 與 fixtures 都是現有 pattern 的線性擴張

**Research date:** 2026-05-23
**Valid until:** 2026-06-23(stable libs;若 PyMuPDF 升 1.28 或 Pillow 升 13 需 re-verify 一次 redaction 與 multi-page TIFF 行為)
