# Phase 4: 點陣圖與圖片型檔案支援 - Pattern Map

**Mapped:** 2026-05-23
**Files analyzed:** 7 個既有檔案修改 + 0 新增模組(Phase 4 不新增任何 module)
**Analogs found:** 7 / 7(全數可在 Phase 1–3 既有檔案中找到 1:1 analog,Phase 4 為純擴張)

## File Classification

| 變更檔案 | Role | Data Flow | Closest Analog | Match Quality |
|---------|------|-----------|----------------|---------------|
| `app/services/ingest.py`(擴張) | service / trust-boundary validator | request-response(upload bytes → SessionInfo)| 自身既有 `_looks_like_pdf` + `ingest_upload` | exact(同檔內擴張)|
| `app/services/pdf_engine.py`(新增 helpers + 常數)| engine wrapper(AGPL seam)| transform(fitz API → Python primitives)| 自身既有 `add_redact_annot` / `apply_redactions` / `get_image_rects` 等 wrapper 群 | exact(同檔新增 sibling helper)|
| `app/services/redact.py`(拆分 entry point)| service / redaction orchestrator | transform(rect + page → redacted page)| 自身既有 `remove_region` | exact(rename 後新增 raster sibling)|
| `app/services/pipeline.py`(dispatch + save flag)| service / job orchestrator | batch(JobSpec → outputs PDF)| 自身既有 `process_job` per-region loop | exact(同 function 內加 1 行 dispatch + save flag 已就位)|
| `app/config.py`(可選新增常數)| config | static constants | 自身既有 `MAX_UPLOAD_BYTES` / `MAX_PAGES` / `MAX_RENDER_PIXELS` 命名 pattern | exact |
| `app/main.py`(擴張 `_INGEST_STATUS` 映射)| API / global exception handler | request-response(exception → JSON 4xx)| 自身既有 `_INGEST_STATUS` dict | exact |
| `web/index.html`(dropzone copy/accept/aria)| frontend / static HTML | static markup | 自身既有 `#dropzone` block(line 277–299)| exact |
| `web/js/app.js`(新增三個錯誤碼 + COPY 文案 + switch case)| frontend / error mapping | event-driven(api error → DOM textContent)| 自身既有 `COPY` 字典 + `messageForError` switch | exact |

> 注意:Phase 4 完全不動 `coords.py` / `render.py` / `logo.py` / `api/pages.py` / `api/process.py` / `models.py` / `web/js/viewer.js` / `web/js/regions.js` / `web/js/api.js` / `tokens.css`(CONTEXT `<code_context>` Reusable Assets 列明)。
>
> 注意:`storage.py` 與 `api/sessions.py` 在 planner 拍板「雙寫 pristine_pdf」(解決 reset-from-pristine invariant 衝突)與「sniff dispatch 新增 3 個錯誤碼」後**需要修改**(`storage.py` 新增 `pristine/` 第三目錄與 `write_pristine_copy` helper、`api/sessions.py` 的 `_CODE_STATUS` 同步擴 3 條)。`04-01-PLAN.md` `files_modified` 已涵蓋。

---

## Pattern Assignments

### `app/services/ingest.py`(extend — sniff dispatch + image branch)

**Analog:** 自身既有檔(`app/services/ingest.py` 第 1–119 行)

**Imports pattern**(lines 19–23,沿用)
```python
from __future__ import annotations

from .. import config, storage
from ..models import SessionInfo
from . import pdf_engine
```

> Phase 4 **新增**:`import io`(BytesIO)、`from PIL import Image, UnidentifiedImageError`(同 Phase 3 `logo.py` 第 26 行的 import 形式 — Pillow 直接 import 允許,**不可** `import fitz`)。

**Magic-header sniff pattern**(lines 30–53,直接擴張)
```python
# Existing
_PDF_MAGIC = b"%PDF-"
_PDF_MAGIC_MAX_OFFSET = 8


def _looks_like_pdf(data: bytes) -> bool:
    offset = data[: 1024].find(_PDF_MAGIC)
    return 0 <= offset <= _PDF_MAGIC_MAX_OFFSET
```

> Phase 4 delta:在 `_PDF_MAGIC` 旁加 `_PNG_MAGIC` / `_JPEG_MAGIC` / `_TIFF_LE_MAGIC` / `_TIFF_BE_MAGIC` 四個常數;`_looks_like_pdf` 維持原樣(回 bool),新增 `_sniff_kind(data) -> str | None` 回 `"pdf" | "png" | "jpeg" | "tiff" | None`。
>
> **關鍵差異**:PDF magic 允許 leading offset ≤ 8(現有原因見 docstring 引用 WR-05);image magics 必須 `startswith`(PNG/JPEG/TIFF spec 不允許 leading bytes — RESEARCH Pattern 1)。

**Typed error pattern**(lines 35–41,沿用)
```python
class IngestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
```

> Phase 4 **不新增 Exception class**;新增的錯誤碼字串 `corrupt_image` / `multi_page_tiff_unsupported` 仍 raise `IngestError(code, message)`。沿用既有 typed-error pattern。

**Validation order pattern**(lines 56–78,擴張 step 3–4)
```python
def ingest_upload(filename: str, data: bytes) -> SessionInfo:
    # 1. empty
    if not data:
        raise IngestError("empty_file", "檔案是空的,請選擇有內容的 PDF。")
    # 2. oversize
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise IngestError("file_too_large", f"檔案過大,超過大小上限 {config.MAX_UPLOAD_MB} MB。")
    # 3. type sniff
    if not _looks_like_pdf(data):
        raise IngestError("unsupported_type", "不支援的檔案類型,本階段僅接受向量 PDF。")
    # 4. parse + page-count
    # ...
```

> Phase 4 delta:
> - Step 1 文案:`"請選擇有內容的 PDF。"` → `"請選擇有內容的 PDF 或影像。"`(D-11 多型別措辭)。
> - Step 3 從 `_looks_like_pdf` 改為 `_sniff_kind`;`unsupported_type` 文案改為「請改用 PDF、PNG、JPG、TIFF」(UI-SPEC 鎖定)。
> - Step 4 從「直接 `_ingest_pdf`」拆為 dispatch:`kind == "pdf"` → 既有路徑;`kind in {"png","jpeg","tiff"}` → 新 `_ingest_image_to_pdf`(RESEARCH Example 1)。

**Persist pattern**(lines 106–112,沿用語意,變動參數)
```python
session_id = storage.new_session()
safe_name = storage.sanitize_filename(filename)
storage.write_original(session_id, safe_name, data)     # raw image bytes for image branch
storage.write_work_copy(session_id, data)               # NOTE: image branch writes pdf_bytes here
storage.write_session_meta(session_id, page_count=n_pages, filename=safe_name)
```

> Phase 4 delta(image 分支):
> - `write_original` 傳入的 `data` 是「使用者上傳的原始 image bytes」(D-04:originals 保留實際上傳 bytes、SHA-256 不變)。
> - `write_work_copy` 傳入的是 `pdf_engine.image_to_a4_pdf(normalized_bytes)` 回傳的 PDF bytes。**originals ≠ work**(originals 是 PNG/JPG/TIFF,work 一律是 PDF)。

---

### `app/services/pdf_engine.py`(extend — 新增 1 常數 + 2 helpers)

**Analog:** 自身既有檔(`app/services/pdf_engine.py` 第 1–455 行)

**Constant re-export pattern**(lines 221–223,沿用 + 加 1)
```python
TEXT_REMOVE = fitz.PDF_REDACT_TEXT_REMOVE
LINE_ART_REMOVE_IF_COVERED = fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED
IMAGE_NONE = fitz.PDF_REDACT_IMAGE_NONE
```

> Phase 4 delta:加一行 `IMAGE_PIXELS = fitz.PDF_REDACT_IMAGE_PIXELS  # = 2`,沿用「常數以名字 re-export 讓 redact.py 不必 `import fitz`」的 invariant(docstring 第 213–220 行)。

**fitz seam wrapper pattern**(lines 241–278,sibling helpers 同型)
```python
def add_redact_annot(page, rect, fill=...) -> None:
    page.add_redact_annot(rect, fill=fill)


def apply_redactions(page, *, text, graphics, images) -> None:
    if text == fitz.PDF_REDACT_TEXT_NONE:
        raise PdfEngineError("...拒絕保留文字...")
    page.apply_redactions(text=text, graphics=graphics, images=images)
```

> Phase 4 新 helper #1 `rect_overlaps_image(page, rect) -> bool`:**沿用「fitz API 在內、Python primitives 在外」的形式**。輸入接受 `fitz.Rect`(因 callers `pipeline.process_job` 拿到的 `pdf_rect` 已是 `coords.pixels_to_pdf_rect` 透過 `pdf_engine.map_rect_to_unrotated` 產出的 `fitz.Rect`),內部用 `page.get_images()` + `page.get_image_rects(xref)` + AABB 比較(沿用既有 `_rects_overlap` 第 341–357 行的「inclusive interval overlap」邏輯,**但要單獨寫一份**因 `_rects_overlap` 是 module-private、且要對 `fitz.Rect` 不是 tuple — 也可改為 `_rects_overlap` 加 overload 或統一 normalize 到 tuple)。
>
> **可重用範本**(get_image_rects 已存在於 line 318–325):
```python
def get_image_rects(page: "fitz.Page", xref: int) -> list:
    return page.get_image_rects(xref)
```
> 沿用此 wrapper(已存在,Phase 3 logo placement 已用),`rect_overlaps_image` 內部直接呼叫即可,不需重複包。

**Doc-construction / save pattern**(lines 30–43 + lines 433–447,sibling helper 同型)
```python
def open_pdf(path_or_bytes) -> "fitz.Document":
    try:
        if isinstance(path_or_bytes, (bytes, bytearray)):
            return fitz.open(stream=bytes(path_or_bytes), filetype="pdf")
        return fitz.open(str(path_or_bytes))
    except Exception as exc:
        raise PdfEngineError(f"無法解析 PDF: {exc}") from exc


def save_doc(doc, path, *, garbage=4, deflate=True, clean=True) -> None:
    doc.save(str(path), garbage=garbage, deflate=deflate, clean=clean)
```

> Phase 4 新 helper #2 `image_to_a4_pdf(image_bytes: bytes) -> bytes`:**沿用「engine-private fitz.open + try/finally close + tobytes/save with garbage=4,deflate=True,clean=True」的形式**。差異:
> - 用 `fitz.open()`(無參、建空文件),不是 `fitz.open(stream=...)`(那是讀 PDF)。
> - 用 `doc.new_page(width=595.0, height=842.0)`(A4 點尺寸常數放本檔 module-level)。
> - 用 `page.insert_image(page.rect, stream=image_bytes, keep_proportion=True)`(沿用 `place_logo` 已驗證的 `keep_proportion=True` 語意,docstring lines 311–313)。
> - 用 `doc.tobytes(garbage=4, deflate=True, clean=True)`(沿用 `save_doc` 預設參數的精神,但回 bytes 而非寫檔)。
> - `try / finally doc.close()` 包裹(沿用 `open_pdf` + `close` 模式)。
>
> **AGPL invariant**:此 helper 必須在 `pdf_engine.py`(因為 `fitz.open()` + `new_page` + `insert_image` 必經 fitz);ingest.py 呼叫此 wrapper、不直接 `import fitz`(CONTEXT 第 122 行 / RESEARCH 第 64 行)。

**Naming convention**:沿用 `app/services/pdf_engine.py` 既有 helper 命名:`map_rect_to_unrotated` / `map_rect_to_displayed` / `unrotated_content_box` / `get_text_words_in_rect` / `get_drawings_intersecting` / `get_drawings_fully_inside` / `get_image_rects` / `place_logo` —— 動詞 + 名詞、不縮寫。
- `rect_overlaps_image` ✓(predicate 命名沿用 `_rects_overlap` style)
- `image_to_a4_pdf` ✓(transform 命名,描述輸入 → 輸出)

---

### `app/services/redact.py`(refactor — 拆分為 vector / raster 兩個 entry point)

**Analog:** 自身既有檔(`app/services/redact.py` 第 1–141 行,單一 `remove_region`)

**Module-level constants + typed error pattern**(lines 28–49,沿用)
```python
from . import pdf_engine

REDACT_PAD_PT = 5.0


class RedactError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
```

> Phase 4 不新增 module constants、不新增 Exception class、不新增 imports。Pure-Python 不 import fitz 的 invariant 沿用(docstring 第 20–25 行)。

**Existing `remove_region` body**(lines 68–140,**拆分為兩個 named entry points**)

當前單一 entry:
```python
def remove_region(page, rect) -> bool:
    user_rect = (rect.x0, rect.y0, rect.x1, rect.y1)
    if _is_empty(user_rect):
        return False

    had_text = bool(pdf_engine.get_text_words_in_rect(page, user_rect))
    had_drawings = bool(pdf_engine.get_drawings_intersecting(page, user_rect))
    if not had_text and not had_drawings:
        return False

    padded = _pad(rect, REDACT_PAD_PT)
    padded_fitz = pdf_engine.map_tuple_to_rect(padded)
    pdf_engine.add_redact_annot(page, padded_fitz, fill=None)

    pdf_engine.apply_redactions(
        page,
        text=pdf_engine.TEXT_REMOVE,
        graphics=pdf_engine.LINE_ART_REMOVE_IF_COVERED,
        images=pdf_engine.IMAGE_NONE,
    )

    residual_words = pdf_engine.get_text_words_in_rect(page, user_rect)
    residual_covered_drawings = pdf_engine.get_drawings_fully_inside(page, user_rect)
    if residual_words or residual_covered_drawings:
        raise RedactError("residual_content", "移除後仍偵測到殘留內容(文字或向量)…")

    return True
```

> Phase 4 delta:
> 1. **Rename** `remove_region` → `remove_region_vector`(body 完全不變;Pipeline call-site 同步改名,見下節)。
> 2. **新增 sibling** `remove_region_raster(page, rect) -> bool`(RESEARCH Pattern 5):
>    - 沿用 `_pad` / `_is_empty` / `pdf_engine.add_redact_annot(fill=None)` / `pdf_engine.map_tuple_to_rect` 全部 helpers(不重複)。
>    - **唯一三點差異**:
>      - `apply_redactions` 傳 `images=pdf_engine.IMAGE_PIXELS`(不是 `IMAGE_NONE`)。
>      - **跳過 `had_drawings` 短路與 `residual_covered_drawings` 殘留斷言**(D-09 / RESEARCH Pitfall A:raster 區允許合法繪圖、IMAGE_PIXELS 自身把 image pixel 變白、不需也不該對 drawings 斷言)。
>      - **保留 text 殘留斷言**(D-06 雙層 OCR leak 防護,RESEARCH Pitfall E)。
>    - `fill=None` 兩分支一致(Pitfall A 實測 fill=(1,1,1) 會自我打臉)。
> 3. **保留** `_pad` / `_is_empty` / `REDACT_PAD_PT` / `RedactError` 不動。

**Docstring 更新**:既有 module docstring(lines 1–26)需更新為「兩個 entry point 各自的 invariant」 — vector 分支保留 text + drawings-fully-inside 雙斷言;raster 分支只做 text 斷言。

---

### `app/services/pipeline.py`(extend — per-region dispatch + 確認 save 走 wrapper)

**Analog:** 自身既有檔(`app/services/pipeline.py` 第 201–274 行 per-region loop)

**Per-region loop pattern**(lines 201–274,在 redact 前加 1 個分支)
```python
for region in job_spec.regions:
    page_no = region.page
    # ... validation ...
    page = pdf_engine.get_page(doc, page_no)
    # ... effective_dpi / clamp / map ...
    pdf_rect = coords.pixels_to_pdf_rect(clamped_px, effective_dpi, page)
    removed = redact.remove_region(page, pdf_rect)   # current single entry
    # ... place_logo, results.append ...
```

> Phase 4 delta:把 `redact.remove_region(page, pdf_rect)` 一行改為 dispatch:
```python
if pdf_engine.rect_overlaps_image(page, pdf_rect):
    removed = redact.remove_region_raster(page, pdf_rect)
else:
    removed = redact.remove_region_vector(page, pdf_rect)
```
> 其餘 41 行(clamp / map / place_logo / dedup xref / auto_logo / results.append)**zero-change**。RESEARCH Pattern 6 / Example 3。

**Save pattern**(lines 305–326)
```python
# Step 1: reset rotated pages to intrinsic
for page_idx, intrinsic in intrinsic_by_page.items():
    pdf_engine.set_page_rotation(pdf_engine.get_page(doc, page_idx), intrinsic)

# Step 2: save work copy first
work_tmp = Path(work).with_suffix(".redacted.tmp.pdf")
pdf_engine.save_doc(doc, work_tmp)

# Step 3: re-apply user rotation
# Step 4: save output
out_tmp = out_file.with_suffix(".swap.tmp.pdf")
pdf_engine.save_doc(doc, out_tmp)
```

> Phase 4 delta:**無**(`pdf_engine.save_doc` 預設已是 `garbage=4, deflate=True, clean=True` — pdf_engine.py 第 437–439 行)。**D-10 不需要 pipeline 改動**,只需確認 raster 分支經此包裝(已經過 — pipeline 統一走 `save_doc`)。**Phase 4 對 pipeline.save 的修改 = 0 行**;RESEARCH 結論第 50 行確認:「現有 `pdf_engine.save_doc()` 預設已有這三個 flag」。

**Reset-from-pristine pattern**(lines 123–129,沿用)
```python
if not Path(original).is_file():
    raise PipelineError("work_copy_misconfigured", "...找不到原始檔...")
Path(work).parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(original, work)
```

> 對 image-only 上傳(originals = PNG bytes、work = PDF bytes)**這條會炸**:`shutil.copyfile(原始 PNG → work)` 會把 work 寫成 PNG bytes,後續 `pdf_engine.open_pdf(work)` 失敗。
>
> **Planner 需處理的 invariant 變化**:
> - 選項 A:`originals/` 永遠存 PDF bytes(image 路徑在 ingest 時把 A4 PDF 寫進 originals/,把原始 image bytes 丟棄)— 簡單,但失去「originals = 使用者實際上傳 bytes」的 SHA-256 D-05 語意。
> - 選項 B:`originals/` 存使用者上傳的 raw bytes(PNG/JPG/TIFF/PDF),新增第三個位置 `pristine_work/`(或在 originals/ 旁存 `source.pdf`)專供 reset-from-pristine 用。複雜。
> - 選項 C:`originals/` 存使用者 raw bytes(任何 type)、ingest 同時把 A4 PDF 寫進 work/、reset 改為「從 ingest 階段另存一份 pristine PDF」。
>
> **RESEARCH Example 1 的方案**:`storage.write_original(session_id, safe_name, data)` 寫使用者 raw bytes;`storage.write_work_copy(session_id, pdf_bytes)` 寫 A4 PDF。但 `process_job` 第 129 行 `shutil.copyfile(original, work)` 是 reset-from-pristine,會把 PNG bytes copy 進 work — **這條需要被 Planner 明確設計**(可能改為「reset 改用 ingest 階段另存的 work 副本當 pristine」或「originals/ 對 image 路徑存 normalized PDF + 旁邊一個 `raw.<ext>` 存使用者 bytes」)。
>
> 此為 Phase 4 **planner-decision 點**,patterns 層僅標出 invariant 衝突,不選方案。

---

### `app/config.py`(optional extend — 1 個新常數)

**Analog:** 自身既有檔(`app/config.py` 第 41–61 行)

**Constants pattern**(沿用)
```python
DEFAULT_DPI: int = _env_int("DEFAULT_DPI", 200)
MIN_DPI: int = _env_int("MIN_DPI", 72)
MAX_DPI: int = _env_int("MAX_DPI", 300)

MAX_UPLOAD_BYTES: int = _env_int("MAX_UPLOAD_BYTES", 50 * 1024 * 1024)
MAX_PAGES: int = _env_int("MAX_PAGES", 30)
MAX_RENDER_PIXELS: int = _env_int("MAX_RENDER_PIXELS", 40 * 1_000_000)
MAX_REGIONS: int = _env_int("MAX_REGIONS", 200)
```

> Phase 4 **可選**新增(RESEARCH Open Question 1 + Question 2):
> - `MAX_INGEST_IMAGE_PIXELS: int = _env_int("MAX_INGEST_IMAGE_PIXELS", 89_478_485)`(顯式化 Pillow 預設,避免「隱式 Pillow 預設」)。
> - `JPEG_REENCODE_QUALITY: int = _env_int("JPEG_REENCODE_QUALITY", 90)`(視覺無損,RESEARCH Open Question 2)。
>
> 沿用既有 `_env_int(name, default)` helper(第 19–26 行)+ `MAX_X_Y` 命名規則。**若 planner 認為不必顯式化,沿用 Pillow default 也可** — 此為 Claude's discretion(CONTEXT 第 96 行)。

---

### `app/main.py`(extend — `_INGEST_STATUS` 新增三條映射)

**Analog:** 自身既有檔(`app/main.py` 第 43–58 行)

**Error code → status pattern**(lines 43–58,沿用 dict 結構)
```python
_INGEST_STATUS: dict[str, int] = {
    "unsupported_type": 415,
    "file_too_large": 413,
    "too_many_pages": 413,
    "corrupt_pdf": 422,
    "empty_file": 400,
}


@app.exception_handler(IngestError)
async def _handle_ingest_error(_request: Request, exc: IngestError) -> JSONResponse:
    status = _INGEST_STATUS.get(exc.code, 400)
    return JSONResponse(
        status_code=status,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )
```

> Phase 4 delta:在 dict 中加三條(D-12):
> - `"unsupported_image_format": 415`
> - `"multi_page_tiff_unsupported": 415`
> - `"corrupt_image": 422`
>
> **handler 不動**(沿用既有 `_handle_ingest_error`);若新錯誤碼名命中既有路徑(`unsupported_type` / `corrupt_pdf` 已存在),則 Phase 4 沿用既有 status 即可(RESEARCH 中 magic-sniff 失敗仍走 `unsupported_type` 415,Pillow verify 失敗走新 `corrupt_image` 422 — 名字區隔開因 UI 文案不同 / family 一致但詞不同,UI-SPEC 已鎖)。
>
> **api/sessions.py 內 mirror dict 同步**:該檔開頭也有一份 `_INGEST_STATUS`(Grep 確認 line 22 / 25 存在),Phase 4 需**兩邊同步**(或重構為共用 — 此為 planner discretion)。

---

### `web/index.html`(extend — dropzone copy + accept + aria-label)

**Analog:** 自身既有 dropzone block(`web/index.html` 第 277–299 行)

**Existing dropzone**(完整 block)
```html
<div
  id="dropzone"
  class="dropzone"
  role="button"
  tabindex="0"
  aria-label="選擇 PDF 檔案"
>
  <h2 class="dropzone__heading">上傳 PDF 以開始</h2>
  <p class="dropzone__body">
    選擇或拖曳一個供應商 PDF 檔案,即可在此預覽各頁內容。原始檔案不會被更動。
  </p>
  <button type="button" id="choose-file" class="primary-btn">選擇 PDF 檔案</button>
  <p class="dropzone__secondary">或將檔案拖曳到這裡</p>
  <p class="dropzone__hint">支援 PDF 檔(單一檔案)</p>
  <input
    type="file"
    id="file-input"
    class="visually-hidden"
    accept="application/pdf,.pdf"
  />
</div>
```

> Phase 4 delta(UI-SPEC Copywriting 表 + RESEARCH Example 4):
> - `aria-label="選擇 PDF 檔案"` → `"選擇 PDF 或影像檔案"`
> - `<h2>`「上傳 PDF 以開始」 → 「上傳 PDF 或影像以開始」
> - `<p class="dropzone__body">` 文案完整替換(UI-SPEC 鎖定)
> - `<button>`「選擇 PDF 檔案」 → 「選擇檔案」
> - `<p class="dropzone__hint">`「支援 PDF 檔(單一檔案)」 → 「支援 PDF、PNG、JPG、TIFF(單一檔案)」
> - `<input accept="application/pdf,.pdf">` → `accept="application/pdf,.pdf,image/png,image/jpeg,image/tiff,.png,.jpg,.jpeg,.tif,.tiff"`
>
> **不變**:`<p class="dropzone__secondary">`「或將檔案拖曳到這裡」(UI-SPEC 表內 verbatim 保留)。所有 class、id、tabindex、role、結構標籤 zero-change。

---

### `web/js/app.js`(extend — COPY 字典加三條 + switch 加三個 case)

**Analog:** 自身既有檔(`web/js/app.js` 第 18–33 行 + 第 96–113 行)

**COPY dictionary pattern**(lines 18–33,沿用)
```js
const COPY = {
  uploading: "正在上傳檔案…",
  processing: "正在處理檔案,準備預覽…",
  errorHeading: "無法開啟此檔案",
  unsupportedType: "此檔案格式不支援。請改用 PDF 檔案後再試一次。",
  corruptPdf: "這個 PDF 檔案無法讀取,可能已損毀。請確認檔案後再試一次。",
  fileTooLarge: (limit) =>
    limit
      ? `檔案超過大小上限(${limit})。請改用較小的檔案。`
      : "檔案超過大小上限。請改用較小的檔案。",
  networkFailure: "上傳失敗,請檢查網路連線後再試一次。",
};
```

> Phase 4 delta(UI-SPEC Inline error block 表):
> - `unsupportedType` 文案更新:「請改用 PDF、PNG、JPG 或 TIFF 檔案後再試一次。」(UI-SPEC 已鎖)
> - 新增三條 key:
>   - `unsupportedImageFormat: "此影像格式不支援。請改用 PDF、PNG、JPG 或 TIFF 檔案後再試一次。"`
>   - `multiPageTiffUnsupported: "暫不支援多頁 TIFF。請先將 TIFF 拆成單頁後再上傳。"`
>   - `corruptImage: "這個影像檔案無法讀取,可能已損毀。請確認檔案後再試一次。"`
> - `errorHeading`(`"無法開啟此檔案"`)沿用 — 三個新 case 共用同一 heading(UI-SPEC 表「沿用 Phase 1」)。

**Switch / messageForError pattern**(lines 96–113,沿用)
```js
function messageForError(err) {
  const code = err && err.code ? err.code : "unknown";
  switch (code) {
    case "unsupported_type":
      return COPY.unsupportedType;
    case "corrupt_pdf":
      return COPY.corruptPdf;
    case "file_too_large":
    case "too_many_pages":
      return COPY.fileTooLarge(extractLimit(err && err.serverMessage));
    case "empty_file":
      return COPY.unsupportedType;
    default:
      return COPY.networkFailure;
  }
}
```

> Phase 4 delta:加三個 `case` 對應後端錯誤碼:
> ```js
> case "unsupported_image_format":
>   return COPY.unsupportedImageFormat;
> case "multi_page_tiff_unsupported":
>   return COPY.multiPageTiffUnsupported;
> case "corrupt_image":
>   return COPY.corruptImage;
> ```
> Switch 結構不變,順序緊鄰既有 `corrupt_pdf` case(視覺上「PDF family + image family」並置)。`showError` / `errorBody.textContent` (lines 115–119) zero-change — `textContent` 注入避免 T-01-14 / T-01-15 XSS,沿用。

**api.js docstring 同步**(`web/js/api.js` line 10–11)
```js
// errors -> 4xx { detail: { code, message } }  code in: unsupported_type | file_too_large |
//                                                  too_many_pages | corrupt_pdf | empty_file
```

> Phase 4 delta:docstring comment 補三個新 code 名,**JS 程式碼本身不動**(api.js 是 transport 層,不做 code-specific 處理 — 它把 detail.code 原樣 throw,由 app.js switch)。

---

## Shared Patterns

### AGPL seam(import fitz 限縮)

**Source:** `app/services/pdf_engine.py` 第 8 行 docstring + 第 19 行唯一 `import fitz`(全 repo Grep 確認 `import fitz` 只出現在 pdf_engine.py)。

**Apply to:** Phase 4 所有後端新增 / 修改的 service 檔。
- `ingest.py` 新增 image 路徑時可 `from PIL import Image, UnidentifiedImageError`(Pillow OK,Phase 3 logo.py 已立先例,line 26),**不可** `import fitz`。
- `redact.py` 不動 imports,新分支透過既有 `pdf_engine.IMAGE_PIXELS` 常數(Phase 4 新 export)操作。
- `pipeline.py` 不動 imports,新 dispatch 一行透過 `pdf_engine.rect_overlaps_image` 呼叫。
- `image_to_a4_pdf` 必須在 `pdf_engine.py` 內(因 `fitz.open() + new_page + insert_image`),ingest.py 透過 wrapper 呼叫。

**Validation:** 既有 `test_fitz_import_confined_to_engine_seam` 測試(CONTEXT 第 122 行提到 enforced by test)會擋下任何 Phase 4 違規。

### Typed `*Error(code, message)` + main.py 4xx 映射

**Source:** 五個 service module 的 Exception class(全部同形,code + message)
- `ingest.py` `IngestError`(line 35–41)
- `pdf_engine.py` `PdfEngineError`(line 22)
- `redact.py` `RedactError`(line 39–49)
- `render.py` `RenderError`
- `logo.py` `LogoError`(line 31–42)
- `pipeline.py` `PipelineError`(line 40–46)

**Apply to:** Phase 4 所有新錯誤碼。
- `corrupt_image` / `multi_page_tiff_unsupported` 沿用 `IngestError(code, message)` 抛出(RESEARCH Example 1 / Pattern 2)。
- 不新增 Exception class。
- `main.py` `_INGEST_STATUS` dict 加三條;`_handle_ingest_error` zero-change。

### 繁體中文使用者文案

**Source:** Phase 1–3 既有錯誤訊息(`ingest.py` 第 63 / 70 / 76 / 92 / 97 行;`app.js` `COPY` 字典 line 18–33;UI-SPEC 已鎖文案)。

**Apply to:** Phase 4 三個新錯誤訊息(message field)+ dropzone 五處字串。UI-SPEC 04 已逐條鎖定 verbatim 文案,planner / executor 不得改字。

### Content-sniff 不信任 extension

**Source:** `ingest._looks_like_pdf`(line 44–53 docstring 引用 T-01-06)+ 既有 `_PDF_MAGIC` 比對(line 30)+ `logo.py` `_validate_png`(line 90–)PNG magic 比對。

**Apply to:** Phase 4 新增的 PNG / JPEG / TIFF 三個 magic 比對 — 沿用 `_looks_like_pdf` 的「byte slice + startswith / find」pattern。**Image magic 必須 `startswith`(offset 0),PDF magic 容許 leading offset ≤ 8**(spec 差異,RESEARCH Pattern 1 已說明)。

### Deferred-mutation + reset-from-pristine

**Source:** `pipeline.process_job` 第 107–129 行(work ≠ original assertion + `shutil.copyfile(original, work)`)+ `storage.write_original` 第 173–188 行(chmod 0o444)。

**Apply to:** Phase 4 image 路徑的 originals / work 對應。**Planner 需在 image 路徑明確處理「originals 不再 = work-pristine 來源」的衝突**(見上節 pipeline.py 的 invariant 變化 — 三選一)。SHA-256 D-05 對 originals 的不動性不變;只是 reset 來源可能要另存。

### Pillow ingest pattern(logo.py 已立 — Phase 4 沿用)

**Source:** `app/services/logo.py` 第 90–100 行 `_validate_png`:
```python
from PIL import Image, UnidentifiedImageError

# img.format 必須在 verify() 之前讀
# verify() 之後 image object 無效 — 必須重新 open
# MAX_IMAGE_PIXELS 預設值靠 Pillow,decompression bomb 防護
```

**Apply to:** Phase 4 `ingest.py` 的 image 路徑(RESEARCH Pattern 2 `_ingest_image`)。同樣的 try/except 鏈、同樣的 `(UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError)` 捕捉、同樣的 typed 4xx 抛出 — 不過 raise 的是 `IngestError("corrupt_image", ...)` 而非 `LogoError`。**Pillow import 形式照抄 logo.py 第 26 行**。

### `pdf_engine` wrapper 同型(fitz API 在內、tuple/Rect/primitives 在外)

**Source:** 既有 14 個 wrapper(`open_pdf` / `render_page_to_png` / `page_dimensions` / `page_intrinsic_rotation` / `set_page_rotation` / `get_page` / `map_rect_to_unrotated` / `map_rect_to_displayed` / `unrotated_content_box` / `map_tuple_to_rect` / `add_redact_annot` / `apply_redactions` / `place_logo` / `get_image_rects` / `get_text_words_in_rect` / `get_drawings_intersecting` / `get_drawings_fully_inside` / `save_doc` / `close`)。

**Apply to:** Phase 4 新增的 `rect_overlaps_image(page, rect) -> bool` 與 `image_to_a4_pdf(image_bytes) -> bytes`(RESEARCH Pattern 3、Pattern 4)。沿用既有 docstring 風格(目的 + AGPL 註解 + 任何 verified facts 引用)。

---

## No Analog Found

無。Phase 4 全部新增 / 修改檔案在 Phase 1–3 既有檔案中都有 1:1 結構性 analog(同檔內既有 entry point、sibling helper、命名 convention、docstring 風格、error-class 形式)。Phase 4 為純擴張、無新模組,所以「No Analog Found」表為空。

---

## Phase 4 Success Criteria — 對應 modify list + 既有 analog

> Phase 4 三個 success criteria 來自 REQUIREMENTS UPLOAD-02 / UPLOAD-03 / REMOVE-02 + CONTEXT「影像型檔案同樣可置入 logo」(`<domain>` 第 20 行)。

### SC #1 — UPLOAD-02:使用者可上傳圖片型(點陣 / 掃描)PDF 進行處理
**Modify:**
- `app/services/pdf_engine.py` — 新增 `rect_overlaps_image` + export `IMAGE_PIXELS` 常數
- `app/services/redact.py` — rename `remove_region` → `remove_region_vector`,新增 `remove_region_raster`
- `app/services/pipeline.py` — per-region dispatch(加 1 行 if/else)

**Analog ref:** `redact.remove_region`(現有,第 68–140 行 — 結構 1:1 複製出 `remove_region_raster`,差三點:`images=IMAGE_PIXELS`、跳過 drawings 斷言、跳過 drawings 短路);`pdf_engine.get_image_rects`(現有,line 318–325 — 內部呼叫此 wrapper);`pipeline` per-region loop(現有,line 201–274 — 中間加 1 行 dispatch)。

### SC #2 — UPLOAD-03:使用者可上傳獨立影像檔(PNG/JPG/TIFF),系統將其正規化為單頁文件
**Modify:**
- `app/services/ingest.py` — 新增 `_sniff_kind` + image 三個 magic 常數 + `_ingest_image` Pillow 驗證鏈 + `_ingest_image_to_pdf` 整合
- `app/services/pdf_engine.py` — 新增 `image_to_a4_pdf(image_bytes) -> bytes` + A4 常數
- `web/index.html` — dropzone accept / heading / body / button / hint / aria-label 共六處字串(UI-SPEC 鎖定)
- `web/js/app.js` — COPY 字典加三條 + switch 加三個 case
- `app/main.py` — `_INGEST_STATUS` dict 加三條映射
- `app/api/sessions.py` — 該檔內 mirror dict 同步(planner 決定是否重構為共用)
- `app/config.py` — 可選新增 `MAX_INGEST_IMAGE_PIXELS` / `JPEG_REENCODE_QUALITY`(Claude discretion)

**Analog ref:** `ingest._looks_like_pdf`(現有,第 44–53 行 — `_sniff_kind` 為四 magic 擴張版,結構同型);`ingest.ingest_upload` 主流程(現有,第 56–118 行 — image 路徑接在 step 3 sniff 後做 dispatch);`logo.py` `_validate_png` Pillow 鏈(line 90–100 — `_ingest_image` 結構 1:1 複製,只是 raise `IngestError` 而非 `LogoError`);`pdf_engine.open_pdf` + `save_doc`(line 30–43 + 433–447 — `image_to_a4_pdf` 沿用 try/finally close + `tobytes(garbage=4, deflate=True, clean=True)` 模式);UI-SPEC 04 Copywriting 表(verbatim 文案鎖定)。

### SC #3 — REMOVE-02:對點陣圖 / 影像內容,框選區域以白色填滿(且影像型檔案同樣可置入 logo)
**Modify:**
- `app/services/redact.py` — `remove_region_raster` 的 `apply_redactions(images=IMAGE_PIXELS)` + `fill=None`
- `app/services/pipeline.py` — `place_logo` call zero-change(沿用 Phase 3,line 240–270 對 raster pdf_rect 同樣有效)

**Analog ref:** Phase 2 `redact.remove_region`(現有,第 110–122 行 — `add_redact_annot(fill=None) + apply_redactions` 的順序與 flags 是模板);`pdf_engine.place_logo`(現有,第 281–315 行 — 對 raster pdf_rect zero-change,因 logo 置入語意「同一個 unrotated-page rect」與 vector 區一致,docstring 第 282 行明示);RESEARCH Pitfall A + B 證實「白色填滿」由 `IMAGE_PIXELS` 自身達成、不靠 annot fill(實測 2.88 MB → 6 KB 配合 `save_doc(garbage=4, deflate=True, clean=True)`,line 437–447 已存在)。

---

## Metadata

**Analog search scope:**
- `app/services/`(`ingest.py` / `pdf_engine.py` / `redact.py` / `pipeline.py` / `logo.py` / `storage.py` / `render.py` / `coords.py` — 已掃)
- `app/`(`config.py` / `main.py` / `models.py` / `storage.py` — 已掃)
- `app/api/`(`sessions.py` Grep)
- `web/`(`index.html` / `js/app.js` / `js/api.js` — 已掃 / Grep)
- `.planning/phases/04-raster-image-support/`(CONTEXT / RESEARCH / UI-SPEC 全讀)

**Files scanned:** 12 個既有檔(8 read + 4 grep);2 個 phase artifact 全文(CONTEXT、UI-SPEC);1 個 phase artifact 部分(RESEARCH 第 1–800 行)。

**Pattern extraction date:** 2026-05-23

**Key invariants reinforced for Planner:**
1. AGPL seam — `import fitz` 永遠只在 `pdf_engine.py`(由既有測試強制)。
2. Typed `*Error(code, message)` + `main.py` dict mapping —Phase 4 三個新錯誤碼 100% 沿用此 pattern,不新增 Exception class。
3. Content-sniff not extension —image magic 必須 `startswith`(offset 0),PDF magic 容許 leading offset ≤ 8。
4. 繁體中文使用者文案 — UI-SPEC 04 已逐條鎖定 verbatim,executor 不得改字。
5. Deferred-mutation D-05 / SHA-256 —**Planner 需明確設計「originals 是 raw user bytes、work 是 PDF」時的 reset-from-pristine 來源**(本檔已標出三選一)。
6. `pdf_engine.save_doc(garbage=4, deflate=True, clean=True)` 預設已就位 — D-10 對 pipeline.save 的 modify 行數 = 0。
7. UI delta = dropzone 五處字串 + 三個新錯誤訊息 + `accept` 屬性 — 其他 token / 元件 / 佈局 / overlay / picker / 旋轉 / 鎖框 zero-change(UI-SPEC 04 「Phase 4 deliberately does NOT touch」表)。
