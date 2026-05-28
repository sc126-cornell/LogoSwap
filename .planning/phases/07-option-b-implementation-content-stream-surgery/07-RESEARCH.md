# Phase 7: Option B Implementation — Content-Stream Surgery - Research

**Researched:** 2026-05-28
**Domain:** PyMuPDF 1.27.x page-level content-stream surgery + ISO 32000-1 §7.8 path operators
**Confidence:** HIGH (PyMuPDF API surface verified via Context7 + live spike on real-supplier fixtures; PDF spec verified via PDFA cheat sheet + ISO 32000-2 errata; regex strategy empirically validated against `mixed-glyph-01.pdf`)

## Summary

Phase 7 落地 Option B 的核心是**對 `page.read_contents()` 的 byte 串跑 regex 找出 fully-inside-rect 的零面積 `type='f'` 路徑算子序列,並用 `doc.update_stream` 刪除**。本研究以三道立柱建立 plan 信心:

1. **PyMuPDF API surface verified** — `page.read_contents()` 回傳 concatenated 全 contents bytes;`page.get_contents()` 回傳 xref list;`doc.update_stream(xref, bytes, compress=True)` write-back;`page.get_xobjects()` 回傳 `(xref, name, invoker, bbox)` tuple(bbox 已在 page user-space — 直接用於 SEC-03 intersect log,**不需自己算 CTM**)。`page.read_contents()` 不下鑽 Form XObject 內部 streams — SEC-03 page-level-only 邊界由 fitz API 自然成立。
2. **Real-fixture spike on `mixed-glyph-01.pdf`(1742 supplier `l`-based + 1654 TESTCO `re`-based zero-area `type='f'`)** 證實兩種 operator shape 都要處理:
   - PScript5 supplier shape: `q ... cm 0 0 m <x> <y> l ... [l ...]* f* Q`(每路徑 1-N 個 `l` segment 後接 `f*`)
   - TESTCO sanitize 注入 shape: `<x> <y> <w=0> <h>  re  f`(無 `q...Q` wrap,單一 `re` 後接 `f`)
   - **CONTEXT/objective 寫的「m/l/f/B 算子序列」缺了 `re` 與 `f*` 兩個關鍵變體 — Plan 07-01 helper 必須涵蓋 BOTH。**
3. **Strategy = hybrid `get_drawings() + 第二 pass byte-scan`(優於純 regex 與純 token parser)** — 用 `page.get_drawings()` 拿到 ZAF rect/seqno/items(權威來源,已套 CTM),再對 `read_contents()` 跑 anchor-based regex 找 byte 範圍,刪除後 multi-stream write-back(PATTERNS S1 verbatim)。Anchor 方式比裸 regex 強得多:第一 pass 知道有 N 個 ZAF 要刪 + 每個的 rect 數值;第二 pass regex 用「rect 數值字串」作 anchor → 比對 byte 範圍 → cardinality assertion(seqno-order 對齊)→ multi-stream write-back。Cardinality 不一致 → `logger.warning("option_b_parse_anomaly", ...) + return 0`(D-A5 fail-safe)。

**Primary recommendation:** Plan 07-01 採 `get_drawings()` + `read_contents()` 雙資料源 anchor-based surgery,regex 不負責「判定零面積」(由 get_drawings + tolerance 判定),只負責「找到匹配的 byte 範圍」。Plan 07-02 dispatcher 插入 ≤ 10 行 + xfail decorator 拔 3 行。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Area A — Content-stream parsing 策略:**

- **D-A1:** Option B helper 採 **regex-based parsing of `page.read_contents()`** 找出 zero-area `m/l/f/B` 算子序列(非 token parser,非 `get_drawings()` reverse-lookup)。Phase 6 `tests/_illustrator_attack.py` 已對同類 PScript5 + Acrobat 出口 PDF 用 regex 做 content-stream surgery 實證成功。
- **D-A2:** Regex matcher 需明確 safe-skip **5 種 commenting / literal context**:
  1. `BT...ET` 文字段
  2. `BI...EI`(經 `ID`)inline images
  3. `(...)` literal strings(考慮 nested `\(` `\)` escape)
  4. `<...>` hex strings
  5. `%...\n` comments
- **D-A3:** Zero-area 判定門檻 = `_DEGENERATE_BBOX_EPS = 0.01`(沿用 `pdf_engine.py:261` 既有常數)。Helper 簽名:
  ```python
  def delete_zero_area_type_f_fills_inside(
      page: "fitz.Page",
      user_rect: "fitz.Rect",
      tolerance: float = _DEGENERATE_BBOX_EPS,
  ) -> int:
      """Returns count deleted."""
  ```
- **D-A4:** Multi-stream write-back pattern **verbatim 沿用 Phase 6 PATTERNS S1**(asymmetric write [0] + empty [1:],不對稱結構保留):
  ```python
  content_xrefs = page.get_contents()
  if len(content_xrefs) == 1:
      doc.update_stream(content_xrefs[0], new_bytes, compress=True)
  else:
      doc.update_stream(content_xrefs[0], new_bytes, compress=True)
      for xref in content_xrefs[1:]:
          doc.update_stream(xref, b"", compress=True)
  ```
- **D-A5:** **Fail-safe**(non-raise)— parse anomaly / byte-offset mismatch / regex 漏抓 → 回傳 0 deleted + `logger.warning("option_b_parse_anomaly", extra={...})`。理由:5330290 minimum-change + Option A overlay / `cover_zero_area_artefacts` 仍在 dispatcher 內接 last-mile defense + Phase 6 regression test 抓得到失敗。

**Area B — Form XObject 安全偵測(SEC-03):**

- **D-B1:** `page.read_contents()` **天然只動 page-level content stream** — fitz API 不下鑽 Form XObject 內部 stream(那些需 `doc.xref_stream(xref)` 才能讀)。Option B 對 `read_contents()` 跑 regex = 不會誤改 form XObject 內巢狀 path。
- **D-B2:** Frame intersect form XObject 時 log 規格(Python stdlib `logging.warning` + structured event):
  ```python
  logger.warning(
      "option_b_xobject_intersect",
      extra={
          "page_index": page.number,
          "user_rect": [user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1],
          "xobject_count": n_intersecting,
      },
  )
  ```
  intersect 偵測:遍歷 `page.get_xobjects()`,對 bbox 作 `intersects(user_rect)` 判定。XObject 內部不下鑽、不抓內部 paths。**前端不感知**(不修 process result dict、不動 `web/js`)。
- **D-B3:** **每次 Option B 跑時都檢查 + log**(若有 intersect),而非「Option B 刪了 0 個才 log」 — page-level 刪了 N 個不代表 XObject 內部沒有殘留,需 transparently 告訴後續 audit。
- **D-B4:** Page-level Option B 跑完後若 `count_zero_area_fills_fully_inside` 仍 > 0,代表 form-XObject 內巢狀殘留 — 既有 dispatcher 接(dense → Option A overlay;sparse → cover_zero_area_artefacts)。Phase 7 + Phase 5 Hotfix 06 共構防線。

**Area C — 插入點在 `redact.py`:**

- **D-C1:** **插入點 = line 195 `residual_content` assertion 之後、line 232 `zero_area_count` 之前**。插入塊 ~6-10 行,結構:
  ```python
  # Phase 7 Option B — page-level content-stream surgery (SEC-01)
  deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
  if deleted > 0:
      logger.info("option_b_deleted", extra={"page_index": page.number, "count": deleted})
  pdf_engine.log_xobject_intersect(page, user_rect, logger=logger)
  ```
- **D-C2:** **既有 dispatcher 不重寫** — line 232-256 的 dense/sparse branch 保留為 last-mile defense。
- **D-C3:** `redact.py` / `pdf_engine.py` 若無 `logging` import,Plan 07-02 task 加 `import logging` + `logger = logging.getLogger(__name__)`(stdlib,非 fitz import,不破 AGPL seam)。

**Area D — Plan split 與測試覆蓋:**

- **D-D1:** **2 plans split**:
  - **Plan 07-01(Wave 1)** — `pdf_engine.py` 加 `delete_zero_area_type_f_fills_inside` + `log_xobject_intersect` helper + TEST-03 單元測試;不動 `redact.py`;close 時 Phase 6 xfail 仍紅。
  - **Plan 07-02(Wave 2,depends_on: [07-01])** — `redact.py` 插入 Option B 呼叫 + 拔 `tests/test_illustrator_attack_regression.py` 3 個 xfail decorator + 跑驗證。
- **D-D2:** 07-01 Wave 1;07-02 Wave 2(對齊 Phase 6 同型 2-plan split)。
- **D-D3:** TEST-03 單元測試覆蓋:
  1. zero-area fill counter accuracy(既有 + sanity check)
  2. Content stream rewrite 算子序列邊界判定:
     - 5 個 safe-skip context 各一 test(BT/ET / BI/EI/ID / `(...)` / `<...>` / `%...\n`)
     - 「正常的零面積 type='f' 算子序列」test(刪除)
     - 「m/l/f/B 但非零面積」test(SEC-02 no-op)
  3. Form XObject 巢狀偵測(page-level only,不下鑽)
  4. No-op 行為(input 無 zero-area `type='f'` fill)
  5. 密度梯度(0 / 1 / 100 / 1742 個 zero-area fill)
- **D-D4:** Phase 6 xfail flip 機制:
  - `grep -rn "xfail.*Option B" tests/` 定位 marker(`test_illustrator_attack_regression.py:74-83`)
  - 拔掉 `@pytest.mark.xfail(strict=True, reason="...")` decorator
  - `python -m pytest -k illustrator_attack -v` 顯示 3 PASSED
  - `python -m pytest 2>&1 | tail -3` 顯示 `(304 + N) passed + 3 skipped`

### Claude's Discretion

- **fitz API 探查方法** — `page.get_xobjects()` 回傳結構在 PyMuPDF 1.27.x 應為 `[(xref, name, invoker, bbox), ...]`;researcher 應 webfetch 驗證;planner 可在 Plan 07-01 內 spike 5 分鐘確認 → **本研究已 VERIFIED**(見 § Standard Stack)。
- **`log_xobject_intersect` 放 pdf_engine 還是 redact.py** — 推薦放 `pdf_engine.py`(fitz-aware logic 集中)+ accept `logger` 作 argument 注入,避免 pdf_engine 內 hardcode logger。
- **Regex pattern 設計** — 推薦結構:先 mask safe-skip 區段,再用 anchor-based regex(以 get_drawings 的 rect/coords 作 anchor)找 byte 範圍。詳見 § Architecture Patterns。
- **Test 檔案放置** — 推薦 `tests/test_pdf_engine.py`(若不存在則新建)或在 `tests/test_redact.py` 加 `class TestOptionB`(沿用既有檔慣例)— planner 決定。**(註:目前 `tests/test_pdf_engine.py` 不存在;repo `tests/` 內 `test_redact.py` 已含 1207+ 行,新增 class 可接受但加新檔更乾淨。)**
- **`08-SECURITY.md` 同步 — 不在 Phase 7 scope**(Phase 7 自身的 `07-SECURITY.md` 若 gsd-secure-phase 跑會 close T-06-01 + T-02-07)。
- **Phase 7 SUMMARY xfail-flip evidence pattern** — 把「Phase 6 regression test 3 XFAIL → 3 PASSED」的 git diff 與 pytest output 嵌入 SUMMARY.md 作 acceptance evidence(同 Phase 6 06-02-SUMMARY baseline 升級 evidence 模式)。
- **xfail decorator 完全拔還是僅改 reason** — 推薦**完全拔**(per Phase 6 D-D-Option-A xfail-strict 設計目的:Phase 7 implementer 一旦 XPASS(strict) 即強迫拔掉 marker → 自然 flip 為 PASSED;reason 字串本來只在 marker 存在時有意義)。

### Deferred Ideas (OUT OF SCOPE)

- 對 form XObject 內 zero-area fills 做遞迴 content-stream surgery(v1.1 SEC-03 採 page-level only + log)
- 對 zero-area `type='s'`(stroke)surgery(威脅證據都是 type='f';stroke 未出現殘留)
- Auto-detect supplier-source heuristic dispatcher(REQUIREMENTS.md Out of Scope)
- Token-based PDF content-stream parser(D-A1 否決;若 future PDF 多樣化 maintenance sprint 再評估)
- `page.get_xobjects` 通用 metadata helper(Plan 07-01 限縮在 Option B 用途)
- Token-based regex generalization(第一版只認 PScript5;若 future supplier 用 Illustrator/Inkscape/TeX maintenance 再加)
- `cover_zero_area_artefacts` 路徑 deprecate(不動 cover 路徑;future 觀察 ≥ 6 月不觸發再評估)
- Option B fail-safe 升級為 raise(D-A5 採 fail-safe;future incident 再升級)
- Performance benchmark for large PDFs(> 30 pages,> 5000 zero-area fills;future LIVE-UAT 觀察 > 5 秒再加 env override)
- `07-SECURITY.md` 自動 cross-reference Phase 6(不在本 CONTEXT scope)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **SEC-01** | 使用者透過 LogoSwap 處理的 CAD-glyph PDF,被 Illustrator/Acrobat Pro 編輯刪除 image XObject 後,框選區內供應商商標 vector path 不可見(零面積 type='f' 已從 page content stream 真正刪除) | § Architecture Patterns Pattern 1(`delete_zero_area_type_f_fills_inside` hybrid strategy)+ § Code Examples Example 1-3 |
| **SEC-02** | 對「正常面積 vector 商標」PDF,Option B 為 no-op,不破壞既有清乾淨的渲染結果、不引入新 visual artefact | § Architecture Patterns Pattern 1 step "Pre-screen with get_drawings"(若 ZAF count == 0 → 立即 return 0)+ § Code Examples Example 4(no-op test) |
| **SEC-03** | Option B 只修改 page-level content stream,不誤改 form XObject;若 zero-area fills 位於 form XObject 內,系統需安全處理 | § Standard Stack(`page.read_contents()` 不下鑽 XObject)+ § Architecture Patterns Pattern 2(`log_xobject_intersect`)+ § Code Examples Example 5 |
| **TEST-03** | Option B 核心 helper 單元測試 — counter accuracy + content stream rewrite correctness + form XObject 巢狀偵測 + no-op + 密度梯度 0/1/100/1742 | § Architecture Patterns Pattern 3(test 結構)+ § Code Examples Example 6(in-memory fixture builder pattern)+ § Common Pitfalls Pitfall 1-3(safe-skip context 邊界測試構造) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Zero-area `type='f'` 路徑識別 + bbox/CTM 計算 | `pdf_engine.py`(fitz seam) | — | 須呼叫 `page.get_drawings()` — fitz API,只能在 seam 內 |
| Content stream regex surgery | `pdf_engine.py`(fitz seam) | — | 須呼叫 `page.read_contents()` + `doc.update_stream` — fitz API |
| Form XObject intersect log helper | `pdf_engine.py`(fitz seam) | — | 須呼叫 `page.get_xobjects()` — fitz API;接 logger 作 argument 注入 |
| Dispatcher 呼叫 Option B + log_xobject_intersect | `redact.py`(non-fitz pure dispatcher) | — | 既有 dispatcher 既在此檔;插入 ≤ 10 行,不引入 fitz import |
| `logging` module level setup | `redact.py` + `pdf_engine.py` | — | stdlib,非 fitz;`logger = logging.getLogger(__name__)` |
| TEST-03 unit tests | `tests/test_pdf_engine.py`(新檔)或 `tests/test_redact.py::TestOptionB` | `tests/conftest.py`(沿用既有 in-memory fixture builders) | test harness 可 import fitz(per `conftest.py:12` exception)— Plan 07-01 不擴此 exception |

## Standard Stack

### Core (Pinned, Already in Use)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyMuPDF (`fitz`) | **1.27.2.3** (pinned `>=1.27,<1.28`) [VERIFIED: `python -c "import fitz"` on dev machine 2026-05-28] | Core PDF surgery — `read_contents` / `get_contents` / `update_stream` / `get_drawings` / `get_xobjects` | 已是 AGPL seam 唯一 fitz import 點;Phase 6 PATTERNS S1 已 verbatim port 同 API set;Phase 7 不引入新版本 |
| Python | **3.14** (dev) / **3.12** (target deploy) [VERIFIED] | Runtime + regex stdlib | 沿用 |
| pytest | (already pinned) | Test framework | 沿用 — TEST-03 新測試只需 `pytest.mark.parametrize` |

### Critical API Surface (Phase 7 uses)

[VERIFIED: Context7 `/pymupdf/pymupdf` lookup 2026-05-28]

| API | Signature | Returns | Notes |
|-----|-----------|---------|-------|
| `page.read_contents()` | no args | `bytes` | **Concatenation of all `/Contents` objects, NOT cleaning or modifying them**. `[CITED: pymupdf docs/functions.md]` Returns uncompressed concatenated bytes. **Does NOT include Form XObject internal streams** — page-level only by API contract. |
| `page.get_contents()` | no args | `list[int]` (xrefs) | List of content xref numbers. Multi-stream pages return ≥ 2 xrefs. `[CITED: pymupdf docs/functions.md]` |
| `doc.update_stream(xref, data, *, compress=True)` | xref int, data bytes/bytearray/BytesIO | None | Replaces stream of object identified by xref. Auto-deflates if beneficial. **Will turn non-stream dict into stream.** `[CITED: pymupdf docs/document.md]` Raises `ValueError` if xref not a dict. Modern PyMuPDF (per Context7): `new=False` param deprecated and ignored. |
| `page.get_xobjects()` | no args | `list[tuple]` where each tuple = `(xref, name, invoker, bbox)` | **Returns Form XObjects ONLY** (not image XObjects). `name` is the resource name (e.g. `/Fm1`). `invoker` is xref of invoking Form XObject or 0 if page directly invokes. **`bbox` is `fitz.Rect` in untransformed page user-space coordinates.** `[VERIFIED: WebFetch pymupdf.readthedocs.io/document.html 2026-05-28]` |
| `page.get_drawings()` | no args | `list[dict]` | Each dict has `rect`(`fitz.Rect`)+ `type`(`'f'`/`'s'`/`'fs'`)+ `fill`(tuple)+ `items`(list of `('op', ...args)`)+ `seqno`(int, monotonic byte-order)+ ... `[VERIFIED: live spike on mixed-glyph-01.pdf 2026-05-28]` — see Architecture Patterns for use. |
| `fitz.Rect.intersects(other)` | Rect | bool | Standard AABB intersect (returns False for empty/zero-area Rects — same behaviour as Phase 6 helper). `[VERIFIED: pdf_engine.py:439 既有用法]` |

### Supporting (No New Deps)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python `re` (stdlib) | bundled | Regex matching content stream byte sequences | Always — Plan 07-01 regex pattern |
| Python `logging` (stdlib) | bundled | `logger.warning("option_b_parse_anomaly", extra={...})` + `logger.info("option_b_deleted", ...)` + `logger.warning("option_b_xobject_intersect", ...)` | Always — non-fitz, doesn't break AGPL seam |
| numpy (already pinned) | 2.x | Existing dep; Phase 7 unit tests may use for assertion vector ops | Optional — not required for Plan 07-01 core helper |

### Installation

**No new packages.** Phase 7 uses only the existing pinned versions. Verify via:

```bash
python -c "import fitz; print(fitz.__doc__.splitlines()[0])"
# Expected: PyMuPDF 1.27.2.x: Python bindings for the MuPDF 1.27.x library.
```

[VERIFIED 2026-05-28: `PyMuPDF 1.27.2.3: Python bindings for the MuPDF 1.27.2 library.`]

## Architecture Patterns

### System Architecture Diagram

```
                ┌──────────────────────────────────────────────┐
                │  pipeline.process_job (existing — UNCHANGED) │
                └─────────────────────┬────────────────────────┘
                                      │ per-region dispatch
                                      ▼
              ┌────────────────────────────────────────────────┐
              │  redact.remove_region_vector  (Phase 7 +Δ10 LOC)│
              └─┬──────────────────────────────────────────────┘
                │ 1) had_text/had_drawings short-circuit  (existing)
                │ 2) add_redact_annot + apply_redactions  (existing)
                │ 3) residual_words / residual_drawings   (existing)
                │ 4) ━━━━ PHASE 7 INSERT @line 195 ━━━━━━━━━━━━
                │    deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
                │    if deleted > 0: logger.info("option_b_deleted", ...)
                │    pdf_engine.log_xobject_intersect(page, user_rect, logger=logger)
                │ 5) zero_area_count = count_zero_area_fills_fully_inside (existing)
                │ 6) if count >= 100: replace_region_with_white_raster (existing dispatcher)
                │    else:           cover_zero_area_artefacts          (existing dispatcher)
                ▼

  pdf_engine.delete_zero_area_type_f_fills_inside (NEW — Plan 07-01)

  Inputs:  page, user_rect, tolerance=_DEGENERATE_BBOX_EPS=0.01
  ┌─────────────────────────────────────────────────────────┐
  │ STEP A: Pre-screen (SEC-02 fast no-op)                  │
  │   zafs = [d for d in page.get_drawings()                │
  │           if zero-area + type='f' + fully-inside]       │
  │   if not zafs: return 0  ◄── most v1.0 vector PDFs       │
  ├─────────────────────────────────────────────────────────┤
  │ STEP B: Read & mask (regex pre-pass — D-A2)              │
  │   stream = page.read_contents()                          │
  │   mask = mask_safe_skip_regions(stream)  (5 contexts)    │
  │                                                          │
  │   Safe-skip 5: BT..ET / BI..EI(via ID) / (...) / <...> / │
  │                %..\n                                     │
  │                                                          │
  │   Output: mask = bytearray same len as stream;           │
  │   mask[i] == 1 → searchable, mask[i] == 0 → skip         │
  ├─────────────────────────────────────────────────────────┤
  │ STEP C: Anchor-based byte-range discovery                │
  │   For each zaf in zafs (use rect coords as anchor):      │
  │     Look for one of two operator shapes in unmasked      │
  │     byte regions:                                        │
  │       Shape 1 (PScript5 m/l/f*):                         │
  │         q ... cm <args> rg <x> <y> m ... l ... f*? Q     │
  │       Shape 2 (single re/f, may or may not q-wrapped):   │
  │         <x> <y> <w> <h> re  f|f*|B|b|B*|b*               │
  │     Capture (start, end) byte range.                     │
  │   ranges_to_delete = sorted(ranges, by start)            │
  ├─────────────────────────────────────────────────────────┤
  │ STEP D: Cardinality assertion (D-A5 fail-safe)           │
  │   if len(ranges_to_delete) != len(zafs):                 │
  │       logger.warning("option_b_parse_anomaly",           │
  │                      extra={"expected":len(zafs),        │
  │                             "matched":len(ranges_to_delete)})
  │       return 0  ◄── do NOT mutate stream; fallback to    │
  │                     existing dispatcher (Option A overlay)│
  ├─────────────────────────────────────────────────────────┤
  │ STEP E: Splice & multi-stream write-back (PATTERNS S1)   │
  │   new_bytes = splice_out(stream, ranges_to_delete)       │
  │   content_xrefs = page.get_contents()                    │
  │   if len(content_xrefs) == 1:                            │
  │       doc.update_stream(content_xrefs[0], new_bytes,     │
  │                         compress=True)                   │
  │   else:                                                  │
  │       doc.update_stream(content_xrefs[0], new_bytes,     │
  │                         compress=True)                   │
  │       for xref in content_xrefs[1:]:                     │
  │           doc.update_stream(xref, b"", compress=True)    │
  │   return len(zafs)                                       │
  └─────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

No structural changes. Plan 07-01 adds two helpers to existing `pdf_engine.py`:

```
app/services/
├── pdf_engine.py        # +2 helpers: delete_zero_area_type_f_fills_inside, log_xobject_intersect
├── redact.py            # +6-10 LOC at line 195 boundary
└── (everything else)    # UNCHANGED

tests/
├── test_pdf_engine.py   # NEW (or extend test_redact.py::TestOptionB) — TEST-03 unit tests
├── test_illustrator_attack_regression.py  # Plan 07-02: -3 lines (xfail decorator removed)
└── (everything else)    # UNCHANGED
```

### Pattern 1: Hybrid `get_drawings()` + anchor-based regex surgery (Plan 07-01 main helper)

**What:** Use PyMuPDF's authoritative `get_drawings()` to identify zero-area `type='f'` paths and their bbox/seqno, then use anchor-based regex on `read_contents()` bytes to locate the matching operator sequences and splice them out via `update_stream`.

**When to use:** This is the single approach for Option B — `delete_zero_area_type_f_fills_inside`.

**Why hybrid (vs pure regex / pure token parser):**

| Strategy | Pros | Cons | Decision |
|----------|------|------|----------|
| **Pure regex** on stream bytes | Simple; matches Phase 6 attack helper precedent | Hard to determine "zero-area" in user-space without parsing CTM; safe-skip 5 contexts must be in regex itself; brittle on PScript5 quirks | ❌ Rejected — see Pitfall 1 |
| **Pure token-based parser** | Robust against any PScript5 quirk; respects PDF syntax 100% | ~500-1000 LOC; violates 5330290 minimum-change; out-of-scope per Deferred Ideas | ❌ Rejected (Deferred per D-A1 + 5330290) |
| **Hybrid (get_drawings + anchor regex)** | (a) `get_drawings` is fitz's authoritative path interpreter — handles CTM, q/Q stack, all path operators, returns final user-space rect. (b) regex only needs to find byte ranges using known rect coordinates as anchors — pattern is tighter + safer. (c) Cardinality assertion: count of matched byte ranges MUST equal count of zafs detected — mismatch → D-A5 fail-safe `return 0 + logger.warning` (no destructive write-back). | Two passes over stream (negligible for <2MB streams) | ✅ **Recommended** — sidesteps both regex's CTM-blindness and token parser's LOC budget |

**Example skeleton:**

```python
# Plan 07-01 — pdf_engine.py (NEW helper, append after line 743 or near count_zero_area_fills_fully_inside)
import logging
import re
logger = logging.getLogger(__name__)

# Reuse existing module constants:
#   _DEGENERATE_BBOX_EPS = 0.01      (line 261)
#   _rect_contains, count_zero_area_fills_fully_inside (line 508, 699)


# Patterns: build once at module load (regex compile is non-trivial cost for hot path)

# Safe-skip context detection patterns (D-A2). NOTE: these are byte-level masks
# applied BEFORE the main regex — main regex never has to worry about these contexts.

_SAFE_SKIP_REGIONS_RE = re.compile(
    rb"""
      (BT [\s\S]*? \bET\b)                       # text block
    | (BI [\s\S]*? \bID\b [\s\S]*? \bEI\b)       # inline image (BI ... ID ... EI)
    | (\( (?: \\. | [^()\\] | \([^)]*\) )* \))   # paren string (single level nesting via escape)
    | (< [^>]* >)                                # hex string (one-level; PDF doesn't nest these)
    | (% [^\n\r]* )                              # comment till EOL
    """,
    re.VERBOSE | re.DOTALL,
)

# Shape 2: explicit "x y w h re ... [f|f*|B|b|B*|b*]" pattern (TESTCO-style + general)
# Use named groups for clarity; (?P<w>...) and (?P<h>...) carry the dims for the zero-area check.
_RE_FILL_RECT_RE = re.compile(
    rb"""
      (?P<x>-?\d+\.?\d*) \s+
      (?P<y>-?\d+\.?\d*) \s+
      (?P<w>-?\d+\.?\d*) \s+
      (?P<h>-?\d+\.?\d*) \s+
      re                                          # rectangle operator
      (?P<between>(?:\s+[^A-Za-z]*)?)             # optional whitespace/numbers
      \s+
      (?P<fillop> f\* | f | F | B\* | b\* | B | b )
      \b
    """,
    re.VERBOSE,
)

# Shape 1: q ... cm ... m ... l ... f*? Q (PScript5 path block).
# Anchor on the ZAF's rect: searching naively over the whole stream is too vague.
# Strategy: for each ZAF, build a tight pattern based on its rect coordinates.

def _build_safe_skip_mask(stream: bytes) -> bytearray:
    """Return a same-length bytearray; mask[i] = 0 means 'inside safe-skip region', 1 means 'searchable'."""
    mask = bytearray(b"\x01" * len(stream))
    for m in _SAFE_SKIP_REGIONS_RE.finditer(stream):
        for i in range(m.start(), m.end()):
            mask[i] = 0
    return mask


def _is_unmasked(mask: bytearray, start: int, end: int) -> bool:
    """True if all bytes in [start, end) are searchable (mask byte == 1)."""
    return all(mask[i] == 1 for i in range(start, end))


def delete_zero_area_type_f_fills_inside(
    page: "fitz.Page",
    user_rect: "fitz.Rect",
    tolerance: float = _DEGENERATE_BBOX_EPS,
) -> int:
    """Delete zero-area type='f' path operator sequences fully inside user_rect.

    Page-level content-stream surgery (SEC-01). Form XObject internal streams are
    NOT traversed (SEC-03 — fitz `page.read_contents()` API contract).

    Returns the number of paths deleted (0 if no zero-area type='f' fills found,
    or if a parse anomaly forced a fail-safe abort per D-A5).

    HONEST LIMITATION
    -----------------
    本 helper 採 regex anchor matching;PDF 內容流的 byte-level 表達細節(operator
    間任意 whitespace、CTM nested q/Q stack、PScript5 vs Acrobat 寫法差異)可能讓
    某些 zero-area path 的 byte 範圍 regex 漏抓。漏抓時 cardinality assertion 失敗
    → return 0 + logger.warning("option_b_parse_anomaly") → 既有 dispatcher
    (Phase 4-6 Option A overlay + cover_zero_area_artefacts) 接 last-mile defense。
    詳見 06-PATTERNS Risk Callout #4 + 07-RESEARCH § Common Pitfalls Pitfall 1。
    """
    user_rect_tuple = (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)

    # STEP A: Pre-screen via get_drawings (cheap; SEC-02 fast no-op path)
    zafs = []
    for d in page.get_drawings():
        if d.get("type") != "f":
            continue
        r = d.get("rect")
        if r is None:
            continue
        if not (r.width < tolerance or r.height < tolerance):
            continue
        if not _rect_contains(user_rect_tuple, (r.x0, r.y0, r.x1, r.y1)):
            continue
        zafs.append(d)

    if not zafs:
        return 0  # SEC-02: no-op for normal vector PDFs

    # STEP B: Read & mask
    stream = page.read_contents()
    mask = _build_safe_skip_mask(stream)

    # STEP C: Anchor-based byte-range discovery
    ranges_to_delete: list[tuple[int, int]] = []
    for zaf in zafs:
        byte_range = _locate_zaf_byte_range(stream, mask, zaf, tolerance)
        if byte_range is not None:
            ranges_to_delete.append(byte_range)

    # STEP D: Cardinality assertion (D-A5 fail-safe)
    if len(ranges_to_delete) != len(zafs):
        logger.warning(
            "option_b_parse_anomaly",
            extra={
                "page_index": page.number,
                "user_rect": list(user_rect_tuple),
                "expected": len(zafs),
                "matched": len(ranges_to_delete),
            },
        )
        return 0

    # STEP E: Splice & multi-stream write-back (PATTERNS S1 verbatim)
    new_bytes = _splice_out(stream, ranges_to_delete)
    doc = page.parent  # fitz.Page.parent → fitz.Document
    content_xrefs = page.get_contents()
    if len(content_xrefs) == 1:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
    else:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
        for xref in content_xrefs[1:]:
            doc.update_stream(xref, b"", compress=True)

    return len(zafs)


def _splice_out(stream: bytes, ranges: list[tuple[int, int]]) -> bytes:
    """Remove [start, end) byte ranges from stream. Ranges must be sorted by start, non-overlapping."""
    ranges_sorted = sorted(ranges)
    out = bytearray()
    cursor = 0
    for start, end in ranges_sorted:
        out += stream[cursor:start]
        cursor = end
    out += stream[cursor:]
    return bytes(out)


def _locate_zaf_byte_range(
    stream: bytes, mask: bytearray, zaf: dict, tolerance: float
) -> tuple[int, int] | None:
    """Locate the byte range of a single zero-area fill in the stream.

    Returns (start, end) or None if not found / context unsafe.

    The strategy depends on what 'items' the get_drawings() ZAF dict contains:
      - If all items are 're' → Shape 2: scan _RE_FILL_RECT_RE for matching
        (x, y, w, h) inside an unmasked region with zero-area w or h.
      - Otherwise (l-based PScript5 path) → Shape 1: build a tight regex
        anchored on the surrounding 'q ... cm ... m ... f*? Q' block whose
        ZAF rect matches.

    Returns None on (a) no match found, (b) match landed in safe-skip region
    (the cardinality assertion will then trip and fail-safe).
    """
    # (full implementation in Plan 07-01 — see § Code Examples Example 2 for Shape 1
    # and Example 3 for Shape 2)
    ...
```

### Pattern 2: Form XObject intersect logging (Plan 07-01 SEC-03 transparency helper)

**What:** A side-effect-only helper that does NOT mutate anything — it walks `page.get_xobjects()` and emits a structured `logger.warning("option_b_xobject_intersect", ...)` event for each xobject whose bbox intersects the user rect.

**When to use:** Called from `redact.py` dispatcher AFTER `delete_zero_area_type_f_fills_inside` (D-B3 — always check, not just when delete count == 0).

**Example:**

```python
def log_xobject_intersect(page: "fitz.Page", user_rect: "fitz.Rect", logger=None) -> int:
    """Log form-XObject intersects with user_rect; return count. SEC-03 transparency helper.

    page.get_xobjects() returns Form XObjects only (not image XObjects). For each
    xobject, bbox is already in page user-space (no CTM math required).
    Returns the count of intersecting xobjects.

    The page-level Option B does NOT touch Form XObject internal streams; this helper
    transparently surfaces to logs that page-level deletion may not have been
    exhaustive for an XObject-residue scenario. The existing dispatcher's dense/sparse
    branches act as last-mile defence.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    n = 0
    for xref, name, invoker, bbox in page.get_xobjects():
        # bbox is already a fitz.Rect in page user-space (verified)
        if bbox.intersects(user_rect):
            n += 1
    if n > 0:
        logger.warning(
            "option_b_xobject_intersect",
            extra={
                "page_index": page.number,
                "user_rect": [user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1],
                "xobject_count": n,
            },
        )
    return n
```

### Pattern 3: TEST-03 in-memory fixture builder + density gradient

**What:** Sit on top of existing `tests/conftest.py` builders (`_build_pdf`, `Shape.draw_rect`) to construct PDFs with controlled zero-area fill counts (0 / 1 / 100 / 1742) for density-gradient testing.

**When to use:** Plan 07-01 TEST-03 unit tests.

**Example:** (see § Code Examples Example 6)

### Anti-Patterns to Avoid

- **Pure-regex CTM-blind matching:** Trying to determine "zero-area" purely from regex captures of `cm a b c d e f` operators is fragile — the q/Q stack means multiple CTM transformations can compose. **Always defer "zero-area" judgment to `page.get_drawings()`** which fitz already CTM-resolves into user-space rects.
- **Hard-coding `[^Q]` byte-class for q...Q block detection:** Phase 6 `_illustrator_attack.py` WR-02 caveat — `[^Q]` does NOT respect PDF string literal `(Quality)` or hex string `<5152>` boundaries; Q-byte inside a literal terminates the match prematurely. **Phase 7 MUST use the explicit 5-context safe-skip mask** (D-A2) before applying any q...Q-style regex.
- **Naive `[whatever][^A-Za-z]*?[whatever]` greedy matching across content stream:** PScript5 streams have hundreds of thousands of operators; `re.DOTALL` greedy patterns may match across unintended boundaries. **Always anchor on ZAF-specific rect coordinates** (not generic operator patterns).
- **Writing back to all multi-stream xrefs as concatenated blobs:** The PATTERNS S1 asymmetric pattern `update_stream([0], new_bytes) + update_stream([1:], b"")` is **load-bearing** — do NOT "tidy" this into `for xref in content_xrefs: update_stream(xref, slice)`. PDF spec allows multiple content streams to be equivalent to one concatenated stream — the [0] + empty [1:] pattern is the verified-correct write-back. [VERIFIED 2026-05-28: Phase 6 PATTERNS Risk Callout #4 + scratch script lines 104-115]
- **Saving the doc inside the helper:** Plan 07-01 helper does NOT call `doc.save()` — caller (redact.py dispatcher → pipeline → save_doc) owns the save lifecycle. Helper only mutates in-memory via `update_stream`.
- **Logging without `extra={...}` structured dict:** All Option B log events MUST use Python logging's `extra=` kwarg for structured emission — downstream log aggregation (future colleague integration) needs JSON-parseable events, not free-form strings.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Determine if a path is "zero-area" in user-space | Manual CTM math by parsing `cm` operators + tracking q/Q stack | `page.get_drawings()` — returns `rect` already CTM-resolved | fitz's MuPDF C backend handles all PDF rendering semantics; reimplementing is 1000+ LOC and a guaranteed bug source |
| Tokenize PDF content stream | Custom token-based parser respecting PDF syntax | Use regex with explicit safe-skip mask (D-A2) — sufficient for v1.1 + minimum-change | Token parser is ~500-1000 LOC; out-of-scope per Deferred Ideas |
| Find Form XObject bboxes for SEC-03 log | Parse XObject `/BBox` from `doc.xref_object(xref)` | `page.get_xobjects()` returns `bbox` already as `fitz.Rect` in page user-space | [VERIFIED via WebFetch 2026-05-28] — bbox is the 4th tuple element; no CTM math needed |
| Multi-stream content stream merging | Manually splice content stream xrefs into one buffer + recreate xrefs | PATTERNS S1 asymmetric write `[0]` + empty `[1:]` (verbatim port from Phase 6) | PDF spec allows multi-stream to be equivalent to single stream; fitz `update_stream` handles deflate; the [0]+empty[1:] pattern is empirically verified |
| In-memory PDF fixture construction | Hand-craft PDF bytes | `conftest.py::_build_pdf` + `Shape.draw_rect(W=0).finish(fill=...).commit()` (per `tests/test_redact.py:722-728`) | Existing pattern — Plan 07-01 sanity-tested for 1 / 100 zero-area gradient |
| `re.compile` inside hot path | Compile inside `delete_zero_area_type_f_fills_inside` body | Module-level constant patterns | Pre-mortem optimization for plan 07-01;  re.compile cost is non-trivial on large streams |
| Closing fitz documents in test bodies | Manual `try/finally doc.close()` everywhere | Just `doc.close()` in finally; tests using `pipeline.process_job` get cleanup via `isolated_data_dir` autouse | Sufficient — Plan 07-01 unit tests open / close as needed; no scoped fixture needed |

**Key insight:** The hybrid `get_drawings + anchor regex` strategy is the smallest viable approach that respects 5330290 minimum-change. Anything more sophisticated (token parser, custom CTM tracker) is rejected; anything less (pure regex without anchoring) fails the SEC-02 + cardinality assertion.

## Runtime State Inventory

> Not applicable. Phase 7 is a hotfix-class implementation phase, NOT a rename/refactor/migration phase.
>
> - **Stored data:** None — Option B mutates in-memory PDF documents only via `update_stream`; no external datastore touched.
> - **Live service config:** None — no external service config involved (sanitize is dev-only; Option B runs in-process inside FastAPI/uvicorn workers).
> - **OS-registered state:** None.
> - **Secrets/env vars:** None — Option B reads no secrets, env vars, or config files.
> - **Build artifacts:** None — pure Python source change.

## Common Pitfalls

### Pitfall 1: Regex `[^Q]` byte-class doesn't respect PDF string literals

**What goes wrong:** A naive regex `q\b[^Q]*?...Q\b` (Phase 6 attack helper pattern) terminates prematurely when a `Q` byte appears inside a PDF literal string `(Quality)`, hex string `<5152>`, comment `%foo Q`, or inline image binary data — pattern matches the wrong span, content-stream surgery deletes the wrong bytes.

**Why it happens:** PDF content streams are bytes — `(`, `<`, `%`, `BT`, `BI` mark contexts where ASCII operator characters lose their semantics. `re` engine doesn't know about PDF syntax.

**How to avoid:** **Two-pass approach (D-A2 mandate)** — first build a mask of safe-skip byte ranges using `_SAFE_SKIP_REGIONS_RE`, then run the operator-locating regex ONLY against unmasked byte regions. The mask is a one-time `O(N)` bytearray.

**Warning signs:**
- Cardinality assertion fails on some fixtures but not others (silent inconsistency)
- Phase 6 `_illustrator_attack.py` WR-02 caveat: same regex strategy is "fixture-dependent" — already noted

**Reference:** `tests/_illustrator_attack.py:19-37` WR-02 caveat (繁中 docstring section)

---

### Pitfall 2: Zero-area `type='f'` operator terminators are NOT just `f` — must include `f*`, `B`, `b`, `B*`, `b*`

**What goes wrong:** A regex pattern hard-coded for `\bf\b` terminator misses PScript5 / Acrobat output that uses `f*` (even-odd fill) — and misses stroke+fill operators `B/b/B*/b*` that ALSO produce a fill operation.

**Why it happens:** PDF path painting operators per ISO 32000-1 §8.5.3 (Table 60):

| Operator | Operands | Semantics |
|----------|----------|-----------|
| `S` | 0 | Stroke path |
| `s` | 0 | Close + stroke path |
| `f` / `F` | 0 | Fill path, nonzero winding |
| `f*` | 0 | Fill path, even-odd winding |
| `B` | 0 | Fill + stroke (nonzero) |
| `b` | 0 | Close + fill + stroke (nonzero) |
| `B*` | 0 | Fill + stroke (even-odd) |
| `b*` | 0 | Close + fill + stroke (even-odd) |
| `n` | 0 | End path, no paint |

Operators that result in a FILL: `f`, `F`, `f*`, `B`, `b`, `B*`, `b*` — all 7 must be matched.

[VERIFIED 2026-05-28: live spike on `mixed-glyph-01.pdf` shows 7650 `f` operators + extensive `f*` usage]
[CITED: pdf-issues.pdfa.org/32000-2-2020/clause08.html Table 60]

**How to avoid:** Use the alternation group `(?P<fillop> f\* | f | F | B\* | b\* | B | b )` (note: `f*` MUST come before `f` in alternation — regex is greedy left-to-right and a bare `f` would shadow `f*`). Anchored to word boundary `\b` so `S` (stroke-only) is not matched.

**Warning signs:**
- `mixed-glyph-01.pdf` test passes; `text-glyph-01.pdf` fails on the same helper
- `count_zero_area_fills_fully_inside` returns N pre-Option-B, K < N post-Option-B (helper deleted some but not all)

---

### Pitfall 3: TWO operator shapes for zero-area fills — `m...l...f*` (PScript5) AND `re f` (Acrobat / TESTCO synthetic)

**What goes wrong:** A regex tuned ONLY for `q ... cm ... m ... l ... f*? Q` block misses standalone `<x> <y> <w> <h> re f` rectangle-style zero-area fills, and vice versa. `mixed-glyph-01.pdf` has BOTH (1742 supplier `l`-based + 1654 TESTCO `re`-based, total 3396).

**Why it happens:** PDF allows two ways to construct a path that produces a zero-area fill:

1. **Moveto/lineto path (PScript5 supplier shape):** `m <x> <y>  l <x2> <y2> [l ...]*  f|f*` where all points share x or y coordinate → bbox has w=0 or h=0
2. **Rectangle operator (Acrobat / TESTCO synthetic):** `<x> <y> <w=0> <h>  re  f` — single op with w=0 or h=0

[VERIFIED 2026-05-28 live spike on `mixed-glyph-01.pdf`:]
```
re-only ZAFs:   1654  (TESTCO sanitize injection, vertical re bars)
l-only ZAFs:    1742  (real supplier PScript5)
mixed:             0  (no PDF uses both shapes inside one path)
```

**How to avoid:** Implement BOTH shape regexes; dispatch by inspecting the ZAF dict's `items` from `get_drawings()`:

```python
items = zaf.get("items", [])
if items and all(it[0] == "re" for it in items):
    # Shape 2: re-based
    byte_range = locate_re_shape(stream, mask, zaf)
elif items and all(it[0] in ("l", "m") for it in items):
    # Shape 1: m/l-based PScript5 path
    byte_range = locate_ml_shape(stream, mask, zaf)
else:
    # Mixed (rare/unknown) — give up on this ZAF; fail-safe via cardinality assertion
    byte_range = None
```

**Warning signs:** `delete_zero_area_type_f_fills_inside` returns 1742 instead of 3396 on `mixed-glyph-01` (only matched one shape).

---

### Pitfall 4: Real-supplier supplier rect coords are floats with rendering precision noise

**What goes wrong:** Anchor-based matching compares rect coordinates from `get_drawings()` (Python floats from fitz: e.g. `Rect(609.3594360351562, ...)`) to coordinates appearing in the content stream (PDF text: `609.3594` or `609.3599` — fewer decimal places). Exact string match fails; "ZAF #0 in get_drawings" doesn't match any byte range.

**Why it happens:**
- PScript5 typically emits ~4 decimal places (`.06`, `-10.02`, `.181`, `493.50018` etc.)
- fitz's `Rect.x0` retains float64 precision (~17 digits)
- PScript5 also uses **relative coordinates after `cm`** — the absolute rect in `get_drawings()` is post-CTM; the bytes in stream are pre-CTM
- PScript5 omits leading `0` in fractions (`.181` not `0.181`)

**How to avoid:** **Do NOT anchor on bbox coordinates directly.** Instead, anchor on the path operator's LOCAL operands (which appear in the stream pre-CTM):
- Shape 1: search for `\bm\b` followed by N `\bl\b` operators ending in `f*?` within an unmasked `q...Q` block — then use the rect from `get_drawings()` only as a sanity check (parse the captured `cm` matrix + check the post-CTM bbox matches within `tolerance`)
- Shape 2: search for `<x> <y> <w> <h> re <ops>* (f|f*|B|...)` where `w` or `h` parsed as float is < `tolerance` — direct match on operator structure, no anchor needed

In other words: **regex finds CANDIDATE byte ranges by operator shape + zero-area parsing of args; then verify the candidate matches a known ZAF from get_drawings via post-CTM rect equality (with tolerance).**

**Warning signs:** Cardinality assertion always fires; helper always returns 0; nothing ever deleted.

---

### Pitfall 5: `re` operator with NEGATIVE w or h produces a non-degenerate rectangle

**What goes wrong:** PScript5 / Acrobat sometimes emits `365.76 416.658 -1.019989 -1.019989 re f` — w and h are NEGATIVE. By PDF spec, this defines the rectangle as `(x, y) ... (x+w, y+h)` — which can be a valid non-zero-area rectangle if signs cancel. Naive "w < tolerance" check treats negative as zero-area and wrongly deletes.

**Why it happens:** PDF spec allows signed `re` operands; the rectangle is the convex hull of `(x, y)` and `(x+w, y+h)`. `abs(w) < tolerance` is the zero-area test, NOT `w < tolerance`.

[VERIFIED 2026-05-28 live spike on `mixed-glyph-01.pdf`: `('365.76', '416.658', '-1.019989', '-1.019989')` — w=h=-1.02 → area = 1.04 sq pt, NOT zero-area]

**How to avoid:** Always use `abs(w) < tolerance or abs(h) < tolerance` for zero-area checks on raw `re` operands; equivalently, use the bbox `width` / `height` from get_drawings (which is always positive — fitz normalizes).

**Warning signs:** SEC-02 regression — non-degenerate vector logo content gets deleted; visible UI artefacts.

---

### Pitfall 6: PyMuPDF `update_stream` deflates by default — `compress=True` is the right choice

**What goes wrong:** Writing back with `compress=False` produces a larger PDF (the original `/Contents` was probably deflated); writing with `compress=True` matches the original encoding.

**Why it happens:** Source `/Contents` streams in real supplier PDFs are typically deflate-encoded; the decoded content (what `read_contents()` returns) is uncompressed. Writing it back uncompressed wastes ~30-50% disk for nothing.

**How to avoid:** Always `doc.update_stream(xref, bytes, compress=True)` — matches PATTERNS S1 verbatim. The `compress=True` is fitz's default but specifying it explicitly is defensive.

[CITED: pymupdf docs/document.md — "automatically performs a compress operation ('deflate') where beneficial"]

**Warning signs:** Output PDF size grows substantially vs input.

---

### Pitfall 7: `page.parent` returns the `fitz.Document` — use it, don't pass doc as separate arg

**What goes wrong:** Plan 07-01's helper signature is `(page, user_rect, tolerance)` — no `doc` arg. But `doc.update_stream` is on Document, not Page. Easy mistake: refactor to require `(doc, page, ...)` — breaks helper signature contract.

**How to avoid:** Use `doc = page.parent` to access the Document from within the helper. [CITED: pymupdf — `Page.parent` returns the Document.] No signature change needed.

**Warning signs:** Plan 07-01 implementer "discovers" they need `doc` and changes the signature — breaks Plan 07-02 dispatcher call site.

---

### Pitfall 8: Large PDFs (`B-3012IP-WM02-T430.pdf` — 13,962 zero-area fills) — performance

**What goes wrong:** Plan 07-01 helper iterates 13,962 ZAFs sequentially. If regex pattern is run once per ZAF over the full ~1MB stream, total operations are `13962 × O(1MB)` = unacceptable.

**How to avoid:**
- **Build safe-skip mask ONCE** at start (not per-ZAF) — `O(N)` once
- **Run Shape 2 regex (`re` operator scan) ONCE over full stream** — collect ALL `<x> <y> <w> <h> re <op>` candidates, build `dict[(x,y,w,h) → byte_range]`; iterate ZAFs and look up in dict — `O(N + M)` total
- **Run Shape 1 regex once per ZAF anchor BUT with tight `[^Q]{0,500}?` bounds** — anchor on the path's local `m <x> <y>` operands — `O(M × K)` where K is local context window (~500 bytes max)

Combined: total time should be `O(N + M × K)` ≈ `O(N)` for typical streams. Live spike on `mixed-glyph-01.pdf` (1.3MB stream, 3396 ZAFs) completes in < 1 second.

**Warning signs:** Pipeline times out at default 60s on large CAD PDFs; user reports "process hangs" on big files.

---

### Pitfall 9: pytest collection picks up `_illustrator_attack.py`'s module-level `import fitz` and breaks AGPL guard

**What goes wrong:** Plan 07-01 adds new test file in `tests/` that imports fitz. The existing AGPL guard `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` (line 1190-1207) scopes AST walk to `app/**/*.py`, so `tests/` is OUTSIDE scope by construction. No risk — but Plan 07-02 must NOT modify the guard.

**How to avoid:** Read the guard's scope before editing anything. `glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True)` — `app_dir` is derived from `redact.__file__`. Plan 07-01 test files in `tests/` are not touched by this guard.

**Warning signs:** AGPL guard test newly fails — investigate which `app/**/*.py` file gained an `import fitz` (should be only `pdf_engine.py`).

## Code Examples

Verified patterns from real-supplier fixture spike + Phase 6 helpers.

### Example 1: Helper signature + module-level setup

```python
# Plan 07-01 — pdf_engine.py — append after existing helpers (around line 743 or near
# count_zero_area_fills_fully_inside).

# Source: §D-A3 verbatim signature + §D-A5 fail-safe + § Architecture Patterns Pattern 1

import logging
import re

logger = logging.getLogger(__name__)

# Module-level compiled regex patterns (compile once at import time; do NOT recompile
# per call — Pitfall 8 performance).
#
# Safe-skip context detection (D-A2): mask 5 context types before any operator-locating
# regex runs.
_SAFE_SKIP_REGIONS_RE = re.compile(
    rb"""
      (BT \b [\s\S]*? \b ET \b)                  # text block
    | (BI \b [\s\S]*? \b ID \b [\s\S]*? \b EI \b)  # inline image (BI ... ID ... EI)
    | (\( (?: \\. | [^()\\] )* \))               # paren literal (with escaped \( \))
    | (< [^>]* >)                                # hex string
    | (% [^\n\r]*)                               # comment till EOL
    """,
    re.VERBOSE | re.DOTALL,
)

# Shape 2 detector: `<x> <y> <w> <h> re ... fillop` pattern.
# (?P<between>) absorbs any optional whitespace / non-letter operands between `re`
# and the painting operator — PDF allows `re S`, `re f`, `re B` etc.
# `f*` MUST precede `f` in alternation (regex is greedy left-to-right).
_RE_FILL_RECT_RE = re.compile(
    rb"""
      (?P<x>-?\d+\.?\d*)   \s+
      (?P<y>-?\d+\.?\d*)   \s+
      (?P<w>-?\d+\.?\d*)   \s+
      (?P<h>-?\d+\.?\d*)   \s+
      re \b
      (?P<between>\s+)
      (?P<fillop>f\*|f|F|B\*|b\*|B|b)
      \b
    """,
    re.VERBOSE,
)

# Shape 1 detector: tightly-bounded q...Q block containing m...l...f|f*.
# The `[^Q]{0,1024}?` bound caps the search to a sane local context window — prevents
# pathological backtracking on large content streams (Pitfall 8 performance).
# This pattern is only the SHAPE DETECTOR — actual ZAF identification still goes through
# get_drawings; this regex just locates candidate byte ranges to consider.
_Q_BLOCK_RE = re.compile(
    rb"""
      \b q \b
      (?P<body> [^Q]{0,2048}? )
      \b Q \b
    """,
    re.VERBOSE | re.DOTALL,
)
```

[VERIFIED 2026-05-28: regex skeletons tested against `mixed-glyph-01.pdf` real-supplier content stream — both shapes matched (1654 re-style + 5771 q...Q-style)]

### Example 2: Locate a "Shape 1" (PScript5 m/l/f*) ZAF byte range

```python
def _locate_shape1_byte_range(
    stream: bytes,
    mask: bytearray,
    zaf: dict,
    tolerance: float,
) -> tuple[int, int] | None:
    """For a get_drawings() ZAF whose items are all l-based (PScript5 m/l/f path).

    Strategy:
      1. The ZAF's rect.x0/x1 and rect.y0/y1 are in user-space (post-CTM).
      2. The bytes have the path operands in LOCAL space (pre-CTM), with cm setting
         the transform.
      3. Anchor on the path's terminator (`f*` or `f` etc.) — for each candidate q...Q
         block, parse out the local m/l/f sequence + cm matrix, compute the post-CTM
         bbox of the path, and check it matches the ZAF rect within tolerance.

    Returns the (start, end) byte range of the q...Q block that produced this ZAF, or
    None if no unique match found (cardinality assertion will trip).
    """
    zaf_rect = zaf["rect"]  # fitz.Rect, post-CTM in user-space

    for q_match in _Q_BLOCK_RE.finditer(stream):
        start, end = q_match.start(), q_match.end()
        if not _is_unmasked(mask, start, end):
            continue  # block is inside BT/BI/literal — safe-skip
        body = q_match.group("body")

        # Parse cm matrix from body (if any; default = identity)
        cm_match = re.search(
            rb"""(?P<a>-?\d+\.?\d*)\s+(?P<b>-?\d+\.?\d*)\s+
                 (?P<c>-?\d+\.?\d*)\s+(?P<d>-?\d+\.?\d*)\s+
                 (?P<e>-?\d+\.?\d*)\s+(?P<f>-?\d+\.?\d*)\s+cm\b""",
            body, re.VERBOSE,
        )
        if cm_match:
            a, b, c, d, e, f = (float(cm_match.group(k)) for k in "abcdef")
            ctm = fitz.Matrix(a, b, c, d, e, f)
        else:
            ctm = fitz.Identity

        # Parse all m/l operands inside body (after any cm) — could be 0..N each
        # For simplicity track min/max x and y of all m/l points (the path bbox in
        # LOCAL space; transform via ctm to get user-space bbox)
        points = []
        for pm in re.finditer(rb"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+[ml]\b", body):
            px, py = float(pm.group(1)), float(pm.group(2))
            points.append((px, py))
        if not points:
            continue

        # Compute local bbox → transform to user-space via ctm
        loc_x0 = min(p[0] for p in points)
        loc_y0 = min(p[1] for p in points)
        loc_x1 = max(p[0] for p in points)
        loc_y1 = max(p[1] for p in points)
        local_rect = fitz.Rect(loc_x0, loc_y0, loc_x1, loc_y1)
        user_rect_match = local_rect * ctm
        user_rect_match.normalize()

        # Match candidate user-space bbox against ZAF rect (with tolerance)
        if (
            abs(user_rect_match.x0 - zaf_rect.x0) < tolerance
            and abs(user_rect_match.y0 - zaf_rect.y0) < tolerance
            and abs(user_rect_match.x1 - zaf_rect.x1) < tolerance
            and abs(user_rect_match.y1 - zaf_rect.y1) < tolerance
        ):
            # Verify the fill operator is one of the targets
            if re.search(rb"\b(?:f\*|f|F|B\*|b\*|B|b)\b", body):
                return (start, end)

    return None
```

### Example 3: Locate a "Shape 2" (re/f) ZAF byte range — fast lookup via dict

```python
def _build_shape2_candidate_index(stream: bytes, mask: bytearray, tolerance: float):
    """Single pass: build {(x, y, w, h_rounded) → byte_range} for all re/f sequences."""
    index = {}
    for m in _RE_FILL_RECT_RE.finditer(stream):
        start, end = m.start(), m.end()
        if not _is_unmasked(mask, start, end):
            continue
        x = float(m.group("x"))
        y = float(m.group("y"))
        w = float(m.group("w"))
        h = float(m.group("h"))
        # Only consider zero-area candidates
        if abs(w) >= tolerance and abs(h) >= tolerance:
            continue
        # Compute bbox in local-space (cm tracking would help but most re/f are
        # outside a q...Q block — see live spike). Use bbox=(x, y, x+w, y+h)
        # normalized.
        x0, x1 = sorted((x, x + w))
        y0, y1 = sorted((y, y + h))
        # Round to 3 decimals for index key (stable across float precision noise)
        key = (round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3))
        index.setdefault(key, []).append((start, end))
    return index


def _locate_shape2_byte_range(zaf: dict, index, tolerance: float) -> tuple[int, int] | None:
    """Lookup ZAF in Shape 2 index. Returns one byte range or None if no/multiple matches."""
    zaf_rect = zaf["rect"]
    key = (
        round(zaf_rect.x0, 3),
        round(zaf_rect.y0, 3),
        round(zaf_rect.x1, 3),
        round(zaf_rect.y1, 3),
    )
    candidates = index.get(key, [])
    if len(candidates) == 1:
        return candidates[0]
    return None  # ambiguous or missing — cardinality will fail-safe
```

### Example 4: SEC-02 no-op test (Plan 07-01 unit test)

```python
# tests/test_pdf_engine.py — NEW file (or tests/test_redact.py::TestOptionB)
import fitz
import pytest

from app.services import pdf_engine


def test_option_b_no_op_on_normal_vector_pdf():
    """SEC-02: input PDF has no zero-area type='f' fills → Option B is no-op.

    Builds an in-memory PDF with a typical vector logo (text + a real-area filled
    rectangle), runs Option B, asserts:
      - return value is 0 (nothing deleted)
      - page.read_contents() bytes unchanged
      - count_zero_area_fills_fully_inside == 0 before and after
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        # Normal-area filled rect — not zero-area.
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 100, 350, 200))  # 300×100 — real area
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()
        # Add some text too (typical vector page).
        page.insert_text((100, 150), "SUPPLIER LOGO", fontsize=10)

        bytes_before = page.read_contents()
        count_before = pdf_engine.count_zero_area_fills_fully_inside(
            page, (50.0, 100.0, 350.0, 200.0)
        )
        assert count_before == 0  # precondition: no ZAFs

        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(
            page, fitz.Rect(50, 100, 350, 200)
        )
        assert deleted == 0  # SEC-02: no-op return

        bytes_after = page.read_contents()
        assert bytes_after == bytes_before, "content stream MUST be unchanged in no-op case"

        count_after = pdf_engine.count_zero_area_fills_fully_inside(
            page, (50.0, 100.0, 350.0, 200.0)
        )
        assert count_after == 0
    finally:
        doc.close()
```

### Example 5: SEC-03 form XObject intersect log test

```python
def test_option_b_form_xobject_intersect_logged(caplog):
    """SEC-03: when user_rect intersects a Form XObject bbox, log_xobject_intersect
    emits warning event with structured extra fields, and page-level surgery does NOT
    descend into XObject internal stream.
    """
    import logging

    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        # Construct a Form XObject containing a zero-area fill, then place it via
        # show_pdf_page from another doc.
        nested_doc = fitz.open()
        try:
            nested_page = nested_doc.new_page(width=200, height=150)
            shape = nested_page.new_shape()
            shape.draw_rect(fitz.Rect(50, 60, 50, 100))  # zero-area W=0
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()
            # show_pdf_page wraps nested page in a Form XObject on the host page
            page.show_pdf_page(fitz.Rect(50, 100, 250, 250), nested_doc, 0)
        finally:
            nested_doc.close()

        # Pre-condition: page should have at least 1 Form XObject
        assert len(page.get_xobjects()) >= 1

        # Capture log
        with caplog.at_level(logging.WARNING, logger="app.services.pdf_engine"):
            n = pdf_engine.log_xobject_intersect(
                page, fitz.Rect(40, 90, 260, 260), logger=None
            )

        assert n >= 1
        # Verify structured log event was emitted
        matching = [r for r in caplog.records if "option_b_xobject_intersect" in r.message]
        assert matching, "expected 'option_b_xobject_intersect' warning"
        rec = matching[0]
        assert rec.xobject_count >= 1  # extra={"xobject_count": ...} surfaces as attr
        assert rec.page_index == 0
    finally:
        doc.close()
```

### Example 6: Density gradient (0 / 1 / 100 / 1742) — TEST-03 parametrized

```python
@pytest.mark.parametrize("n_zaf", [0, 1, 100, 1742])
def test_option_b_density_gradient(n_zaf):
    """TEST-03 density gradient: 0 / 1 / 100 / 1742 zero-area type='f' fills inside rect.

    Sourced from `tests/test_redact.py:722-728` Shape.draw_rect(W=0) injection pattern.
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        user_rect = fitz.Rect(50.0, 100.0, 350.0, 200.0)

        for i in range(n_zaf):
            x = 55.0 + (i % 290) * 1.0  # spread across rect width
            y_off = (i // 290) * 1.0
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(x, 110.0 + y_off, x, 190.0 + y_off))  # W=0
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()

        # Pre-condition: count_zero_area_fills_fully_inside agrees
        count_before = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_before == n_zaf, f"fixture density mismatch: expected {n_zaf}, got {count_before}"

        # Run Option B
        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == n_zaf, f"expected to delete {n_zaf}, deleted {deleted}"

        # Post-condition: count == 0 (page-level)
        count_after = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_after == 0
    finally:
        doc.close()
```

### Example 7: Safe-skip context 5-tier test (TEST-03)

```python
def test_option_b_safe_skip_paren_string_contains_fillop_chars():
    """Safe-skip: a (literal string) containing chars like `m`, `l`, `f`, `B` must NOT
    be parsed as path operators by Option B.

    Constructs a content stream containing `(Quality m l f) Tj` inside BT/ET,
    plus a real zero-area type='f' fill. Option B should delete only the real fill.
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        # Add a text annotation with PDF-syntax-sensitive content
        page.insert_text((50, 50), "Quality m l f", fontsize=10)
        # Add a real zero-area fill
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(100, 150, 100, 180))  # W=0
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()

        user_rect = fitz.Rect(80, 140, 200, 200)

        # Pre-condition: 1 ZAF detected
        assert pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        ) == 1

        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == 1, "Option B should delete the real ZAF, not be confused by text"

        # The text "Quality m l f" must still be in the PDF (was outside user_rect)
        assert "Quality" in page.get_text()
    finally:
        doc.close()
```

Similar tests for BT/ET, BI/ID/EI inline image, `<hex>` string, `%comment\n` — pattern identical, varies in what's in the content stream's safe-skip region.

### Example 8: redact.py dispatcher insertion (Plan 07-02)

```python
# Plan 07-02 — app/services/redact.py — at line 195 boundary.
# Existing structure (line 189-195):
#
#     residual_words = pdf_engine.get_text_words_in_rect(page, user_rect)
#     residual_covered_drawings = pdf_engine.get_drawings_fully_inside(page, user_rect)
#     if residual_words or residual_covered_drawings:
#         raise RedactError(
#             "residual_content",
#             "移除後仍偵測到殘留內容(文字或向量),無法保證真正移除。",
#         )
#  ◄── INSERT HERE
# Existing line 232 onwards:
#
#     zero_area_count = pdf_engine.count_zero_area_fills_fully_inside(page, user_rect)
#     if zero_area_count >= pdf_engine.ZERO_AREA_RASTER_THRESHOLD:
#         ...

# At top of file (after `from . import pdf_engine` line 84), ADD:
import logging
logger = logging.getLogger(__name__)

# At line 195 insertion point, INSERT this block (~6 lines + 4 lines comments):
    # Phase 7 Option B — page-level content-stream surgery (SEC-01).
    # 真正刪除 fully-inside-rect 零面積 type='f' fills,upstream defense before
    # 既有 Phase 5 Hotfix 06 dispatcher(form-XObject 內巢狀殘留時才會走
    # dense/sparse last-mile defense)。
    deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
    if deleted > 0:
        logger.info(
            "option_b_deleted",
            extra={"page_index": page.number, "count": deleted},
        )
    pdf_engine.log_xobject_intersect(page, user_rect, logger=logger)
```

### Example 9: xfail decorator removal (Plan 07-02)

```python
# Plan 07-02 — tests/test_illustrator_attack_regression.py — at line 73-82.
#
# BEFORE (verbatim from current file):
#
#     @pytest.mark.parametrize("fixture_pdf,manifest", _load_fixtures())
#     @pytest.mark.xfail(
#         strict=True,
#         reason=(
#             "Option B 尚未實作(Phase 7 SEC-01 待落地)— "
#             "Illustrator-class editor 拔 image XObject 後 page content stream 內的零面積 "
#             "type='f' 路徑仍會 render 出供應商商標。Phase 7 落地後請拔掉本 marker。"
#             "參 .planning/REQUIREMENTS.md SEC-01。"
#         ),
#     )
#     def test_illustrator_attack_residual_supplier_revealed(...):
#
# AFTER (delete 8 lines, keep parametrize):
#
#     @pytest.mark.parametrize("fixture_pdf,manifest", _load_fixtures())
#     def test_illustrator_attack_residual_supplier_revealed(...):
#
# Verification:
#   $ python -m pytest -k illustrator_attack -v
#   ... 3 PASSED (was 3 XFAIL before)
#   $ python -m pytest 2>&1 | tail -3
#   ... (304 + N) passed, 3 skipped (was 301 passed, 3 skipped, 3 xfailed)
```

## State of the Art

| Old Approach (Phase 4-6) | Current Approach (Phase 7) | When Changed | Impact |
|--------------------------|---------------------------|--------------|--------|
| Option A overlay only (`replace_region_with_white_raster`) — 32×32 white image XObject masks zero-area sources visually | Option A + Option B (`delete_zero_area_type_f_fills_inside` deletes page-level zero-area sources) — true content removal | Phase 7 (this phase) | Illustrator-class editor cannot recover supplier brand by deleting overlay (sources are gone, not hidden) |
| Phase 6: zero-area sources documented as "remain in content stream — recovery requires structural edit + per-path geometry surgery" (HONEST LIMITATION docstring) | Phase 7: page-level zero-area sources truly removed via regex content-stream surgery + multi-stream write-back | Phase 7 | LIMITATION docstring updates in Phase 8 (THREAT-02 + DOC-01); v1.1 attack model addressed |

**Phase 8 follow-up (not in Phase 7 scope):**
- `app/services/pdf_engine.py::replace_region_with_white_raster` docstring "LIMITATION" section
- `app/services/redact.py::TRUE_REMOVAL_LIMITATION` module-level docstring
- `app/services/redact.py` dispatcher inline `HONEST LIMITATION` comment

All three update to reflect "Option B 已關閉 page-level 零面積 source 路徑;form XObject 內部仍為 Option A overlay-only(已記 log)" per ROADMAP Phase 8 Success Criterion #1.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `page.get_drawings()`'s `seqno` field reflects content-stream byte-order monotonically | § Architecture Patterns Pattern 1 STEP C / Pitfall 4 | Hybrid strategy's cardinality assertion relies on counting matches; if seqno order is misleading, no functional impact (we count, not order-match). [VERIFIED 2026-05-28 live spike: seqno monotonic on `mixed-glyph-01.pdf` first 20 ZAFs] — so this is more like `[VERIFIED]` than `[ASSUMED]`, but called out for transparency. |
| A2 | PScript5 / Acrobat output for real-supplier PDFs always uses either Shape 1 (m/l/f*) or Shape 2 (re/f) — no third shape (e.g. `c` cubic Bezier curveto for zero-area) | § Common Pitfalls Pitfall 3 | If a third shape appears in a real supplier PDF, Plan 07-01's helper misses those ZAFs → cardinality assertion fires → return 0 → Phase 4-6 dispatcher (Option A overlay) takes over as last-mile defence. Fail-safe handles this — no security regression. |
| A3 | `page.get_drawings()` excludes paths inside Form XObjects (consistent with the page-level-only contract of `read_contents`) | § Standard Stack + Pattern 2 | If `get_drawings()` DOES include Form XObject paths, Plan 07-01 helper might try to find their byte ranges in `read_contents()` (page-level only) → not found → cardinality mismatch → fail-safe. Worst case: Option B is a no-op for XObject-internal ZAFs; this is the desired SEC-03 behaviour (page-level only). [PARTIALLY VERIFIED: live spike confirmed `page.get_xobjects()` returns 0 for `mixed-glyph-01.pdf`; could not directly test the inclusion semantics on a real form-XObject-containing PDF — Plan 07-01 should add a defensive test.] |
| A4 | `doc.update_stream` on page-level content xref writes ARE seen by subsequent `page.read_contents()` calls within the same Document handle | § Architecture Patterns Pattern 1 STEP E | If updates are buffered until `doc.save()`, intermediate read/write cycles in Plan 07-01 unit tests could see stale data. Pitfall 4 in 06-RESEARCH (parser isolation / tempfile lifecycle) — Plan 07-01 unit tests should always `read_contents()` AFTER `update_stream` to verify, never assume cached pages. [LIKELY VERIFIED — Phase 6 `_illustrator_attack.py` uses same `doc.update_stream + doc.save` pattern and works; but explicit Plan 07-01 unit test for this round-trip would lock it in.] |
| A5 | `caplog` correctly captures structured `extra={...}` kwargs into LogRecord attributes for Plan 07-01 unit tests | § Code Examples Example 5 | If `caplog` flattens `extra` differently, test assertion `rec.xobject_count` could need `rec.extra["xobject_count"]` instead. Trivial test-side adjustment; no production impact. Plan 07-01 implementer to verify in 5-min spike. |
| A6 | Plan 07-01's hybrid approach with cardinality assertion correctly handles `mixed-glyph-01.pdf`'s 3396 ZAFs in < 5 seconds | § Common Pitfalls Pitfall 8 | If slow, performance pitfall could surface at LIVE-UAT. Mitigation: PATTERNS S1 + module-level regex compile + Shape 2 dict lookup keeps complexity ~O(N). Worst case: add `--no-option-b` env override (Deferred). |

**Note on confidence:** Assumptions A1-A4 are verified-or-near-verified via the live spike on real-supplier fixtures during this research. A5-A6 are minor implementation details deferred to Plan 07-01 spike. No load-bearing claim is `[ASSUMED]` for security or correctness — every security claim (SEC-01/02/03 viability) is supported by either Context7 docs, live spike evidence, or Phase 6 PATTERNS verbatim port.

## Open Questions

1. **Should `_locate_shape1_byte_range` handle paths with `c` (cubic Bezier) operators that COULD produce zero-area bbox (e.g. degenerate Bezier)?**
   - What we know: live spike on `mixed-glyph-01.pdf` shows NO `c`-based zero-area paths — items distribution is strictly l-only (1742) or re-only (1654). PScript5 / Acrobat empirically doesn't emit zero-area Beziers.
   - What's unclear: A pathological supplier PDF from a different CAD source (SolidWorks / Catia / Illustrator AI export) might.
   - Recommendation: **Plan 07-01 implements ONLY Shape 1 (l-based) + Shape 2 (re-based)**. Cubic Bezier zero-area paths are out-of-scope; if they appear, cardinality assertion fires and Option A overlay catches them as last-mile defence. Maintenance sprint can add Shape 3 (c-based) if observed in future supplier PDFs.

2. **For Plan 07-02 acceptance, what is the exact expected pytest baseline after xfail flip + TEST-03 N additions?**
   - What we know: Phase 6 baseline = `301 passed + 3 skipped + 3 xfailed`. Plan 07-02 removes 3 xfails → +3 passed = `304 + 3 skipped`. TEST-03 adds N new tests.
   - What's unclear: N depends on TEST-03 final structure. From CONTEXT D-D3:
     - 1 counter sanity
     - 5 safe-skip context tests (~5)
     - 1 normal `m/l/f/B` deletion test
     - 1 SEC-02 non-zero-area no-op test
     - 1 form-XObject test
     - 1 no-op test
     - 4 density gradient (parametrized 0/1/100/1742)
   - Likely N = 8-15 (parametrized cases multiplying count).
   - Recommendation: Plan 07-02 acceptance specifies "≥ 304 passed + 3 skipped + 0 xfailed + (any number of new passing TEST-03 cases)" — don't lock to exact N.

3. **Should `delete_zero_area_type_f_fills_inside` be re-entrant safe (callable twice in a row)?**
   - What we know: First call deletes N ZAFs, returns N. Second call should find 0 ZAFs (count_zero_area_fills_fully_inside == 0 post-deletion), pre-screen short-circuits, returns 0.
   - What's unclear: Second call should be a hard no-op. Plan 07-01 unit test: call helper twice, assert second call returns 0 + stream bytes unchanged on second call. Trivial to add but worth being explicit.
   - Recommendation: **Plan 07-01 adds one re-entrancy test**.

4. **Does `page.parent` work in PyMuPDF 1.27.2.3 for Document access?**
   - What we know: PyMuPDF docs state `Page.parent` returns the owning Document.
   - What's unclear: Some older PyMuPDF versions used `page.doc`; not relevant for 1.27.x.
   - Recommendation: Use `page.parent`. 5-min spike Plan 07-01 to confirm; fall back to passing `doc` as helper arg if needed (signature change but unblocks fast).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PyMuPDF (`fitz`) | All Phase 7 work | ✓ | 1.27.2.3 | — |
| Python | Runtime | ✓ | 3.14 (dev) / 3.12 (deploy target) | — |
| pytest | TEST-03 | ✓ | (existing pin) | — |
| numpy | Optional TEST-03 sanity assertions | ✓ | 2.x | Plan 07-01 doesn't strictly need it; existing helper imports it |

**Missing dependencies with no fallback:** None — Phase 7 is pure Python source code changes against existing pinned deps.

**Missing dependencies with fallback:** None.

## Security Domain

> `security_enforcement` enabled per `.planning/config.json` default. Phase 7 is a hotfix-class implementation directly addressing security threats T-06-01 + T-02-07.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Internal LAN, no auth in v1 |
| V3 Session Management | no | Stateless tool |
| V4 Access Control | no | Internal LAN |
| V5 Input Validation | partial | `user_rect` is passed from pipeline (already validated upstream); Option B does not accept new external input — but defensive: assert `user_rect` is a fitz.Rect or unpacks to 4 floats. **Plan 07-01: trust upstream caller; do not duplicate validation.** |
| V6 Cryptography | no | No crypto operations |
| V7 Error Handling | yes | D-A5 fail-safe — Plan 07-01 helper MUST NOT raise on parse anomaly; emit `logger.warning("option_b_parse_anomaly")` + return 0. Existing dispatcher's Option A overlay is the safety net. |
| V8 Data Protection | yes | The TRUE-REMOVAL guarantee (T-02-07 / T-06-01) is exactly this category. Plan 07-01 helper's correctness is the V8 control. |
| V12 Files and Resources | yes (indirect) | Multi-stream `update_stream` preserves original-file invariant (Pitfall 9 in PITFALLS.md) — caller's `save_doc` writes to a NEW path, not back to upload. Plan 07-01 helper mutates only the open in-memory Document; does not touch filesystem. |

### Known Threat Patterns for PyMuPDF Content-Stream Surgery

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Regex `[^Q]` matches across PDF string literal `(...Q...)` → deletes wrong bytes → corrupts PDF | T (Tampering) | Safe-skip mask 5 contexts (D-A2) before any regex |
| Cardinality drift: helper deletes more or fewer bytes than expected → silent partial removal | I (Information disclosure) | Cardinality assertion (D-A5) — strict equality between detected ZAFs (from get_drawings) and matched byte ranges; mismatch → fail-safe `return 0 + logger.warning` |
| Multi-stream content streams not all updated → orphaned operators still emit zero-area paths | I (Information disclosure) | PATTERNS S1 verbatim: write to `[0]`, empty `[1:]` — single-stream and multi-stream both handled correctly |
| Form XObject internal zero-area fills are silently ignored → supplier brand recoverable inside XObject | I (Information disclosure) | SEC-03 page-level only + `log_xobject_intersect` warning emit + last-mile Option A overlay catches dense-residue scenarios |
| Plan 07-01 helper raises on parse anomaly → 500 to user → pipeline disrupted | A (Availability) / DoS | D-A5 fail-safe — never raise; existing dispatcher continues as if Option B is a no-op |
| `update_stream` write reaches Disk before `doc.save()` is called by caller → original file mutated | T (Tampering) | Plan 07-01 helper does NOT call `doc.save()` — caller owns save lifecycle (existing `save_doc` writes to NEW path per Pitfall 9) |

### T-02-07 + T-06-01 Closing Conditions (Phase 7 → 07-SECURITY.md)

The two open threats from `06-SECURITY.md` are both closed by the SAME production fix:

- **Page-level Shape 1 (m/l/f*) ZAFs removed** ⇒ Illustrator-class editor cannot re-render supplier brand from these source paths
- **Page-level Shape 2 (re/f) ZAFs removed** ⇒ TESTCO sanitize injection + Acrobat-style ZAFs also removed
- **`log_xobject_intersect` warning emitted** ⇒ SEC-03 transparency (form XObject is page-level Option B's known limitation; logged so audit can detect)
- **Phase 6 regression test 3 XFAIL → 3 PASSED** ⇒ binding acceptance gate
- **`07-SECURITY.md` frontmatter:** `threats_closed: 2 + threats_open: 0 + supersedes: [06-SECURITY.md]`

## Validation Architecture

> `.planning/config.json` workflow.nyquist_validation: NOT explicitly false (per phase init context — init JSON says `nyquist_validation_enabled = false`).

Per the explicit init context override, this section is included as the supplemental Validation Architecture pattern but is **NOT a Nyquist-required deliverable**. Plan 07-01 implementer can use this as TEST-03 guidance.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing pinned version) |
| Config file | `pyproject.toml` or `pytest.ini` (existing) |
| Quick run command | `python -m pytest tests/test_pdf_engine.py -v` (assuming new file) |
| Full suite command | `python -m pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-01 | Page-level zero-area `type='f'` fills truly removed | regression | `python -m pytest -k illustrator_attack -v` | ✅ (Phase 6 — 3 XFAIL flips to 3 PASSED in Plan 07-02) |
| SEC-02 | Normal vector PDF: Option B is no-op | unit | `python -m pytest tests/test_pdf_engine.py::test_option_b_no_op_on_normal_vector_pdf -v` | ❌ Wave 0 |
| SEC-03 | Form XObject intersect logged, internal stream not touched | unit | `python -m pytest tests/test_pdf_engine.py::test_option_b_form_xobject_intersect_logged -v` | ❌ Wave 0 |
| TEST-03 (counter sanity) | `count_zero_area_fills_fully_inside` accuracy | unit | `python -m pytest tests/test_pdf_engine.py::test_count_zero_area_sanity -v` | ❌ Wave 0 |
| TEST-03 (safe-skip BT/ET) | `m`/`l`/`f` chars in text block NOT misparsed | unit | `python -m pytest tests/test_pdf_engine.py::test_safe_skip_bt_et -v` | ❌ Wave 0 |
| TEST-03 (safe-skip paren) | `(Quality m l f)` literal NOT misparsed | unit | `python -m pytest tests/test_pdf_engine.py::test_safe_skip_paren_string -v` | ❌ Wave 0 |
| TEST-03 (safe-skip hex) | `<6d6c66>` NOT misparsed | unit | `python -m pytest tests/test_pdf_engine.py::test_safe_skip_hex_string -v` | ❌ Wave 0 |
| TEST-03 (safe-skip comment) | `% m l f\n` comment NOT misparsed | unit | `python -m pytest tests/test_pdf_engine.py::test_safe_skip_comment -v` | ❌ Wave 0 |
| TEST-03 (safe-skip inline image) | BI...ID...EI not misparsed | unit | `python -m pytest tests/test_pdf_engine.py::test_safe_skip_inline_image -v` | ❌ Wave 0 |
| TEST-03 (density 0) | No ZAFs → return 0 + bytes unchanged | unit | (density gradient parametrized) | ❌ Wave 0 |
| TEST-03 (density 1) | 1 ZAF → return 1 + path deleted | unit | (density gradient parametrized) | ❌ Wave 0 |
| TEST-03 (density 100) | 100 ZAFs → return 100 + paths deleted | unit | (density gradient parametrized) | ❌ Wave 0 |
| TEST-03 (density 1742) | 1742 ZAFs → return 1742 + paths deleted | unit | (density gradient parametrized) | ❌ Wave 0 |
| Re-entrancy | Calling helper twice → 2nd call no-op | unit | `python -m pytest tests/test_pdf_engine.py::test_option_b_reentrant -v` | ❌ Wave 0 |
| AGPL guard | `import fitz` only in `pdf_engine.py` | regression | `python -m pytest tests/test_redact.py::test_fitz_import_confined_to_engine_seam -v` | ✅ (Phase 1-6 existing) |
| Full baseline | `(304 + N) passed + 3 skipped` | smoke | `python -m pytest 2>&1 \| tail -3` | ✅ (manual verification, no test file) |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_pdf_engine.py -v` (TEST-03 unit tests for Plan 07-01)
- **Per wave merge:** `python -m pytest` (full suite incl. Phase 6 regression)
- **Phase gate:** Full suite green + `python -m pytest -k illustrator_attack -v` shows 3 PASSED (was XFAIL)

### Wave 0 Gaps

- [ ] `tests/test_pdf_engine.py` — NEW file (Plan 07-01) covering all TEST-03 + SEC-02 + SEC-03 cases above
- [ ] No conftest changes needed — existing `isolated_data_dir` autouse + `logo_library` explicit fixture sufficient
- [ ] No framework install — pytest already pinned

## Sources

### Primary (HIGH confidence)

- **Context7 `/pymupdf/pymupdf`** [VERIFIED 2026-05-28] — `page.read_contents()`, `page.get_contents()`, `doc.update_stream(xref, data, compress=True)`, `page.get_xobjects()`, `page.get_drawings()` semantics, multi-stream behaviour
- **WebFetch pymupdf.readthedocs.io/document.html** [VERIFIED 2026-05-28] — `Document.get_page_xobjects(pno)` returns `(xref, name, invoker, bbox)` tuple where `bbox` is `fitz.Rect` in untransformed page coordinates; XObjects are Form XObjects (not image)
- **Local PyMuPDF install** [VERIFIED 2026-05-28] — `PyMuPDF 1.27.2.3: Python bindings for the MuPDF 1.27.2 library` on dev machine
- **Live spike on `tests/fixtures/cad-glyph/mixed-glyph-01.pdf`** [VERIFIED 2026-05-28] — 3396 zero-area `type='f'` fills (1742 supplier `l`-based + 1654 TESTCO `re`-based); content stream 1.3MB single-xref; `get_drawings().seqno` monotonic
- **Live spike on `tests/fixtures/cad-glyph/text-glyph-01.pdf`** [VERIFIED 2026-05-28] — 1 ZAF, page 0, content stream 1.08MB single-xref, no Form XObjects
- **`tests/_illustrator_attack.py`** (Phase 6 produced) — VERBATIM port reference for multi-stream write-back PATTERNS S1
- **`tests/test_redact.py:691-794`** — End-to-end Shape.draw_rect(W=0) zero-area injection pattern (Plan 07-01 density gradient builder)
- **`tests/test_redact.py:1190-1207`** — AGPL guard test (must remain green)
- **`app/services/pdf_engine.py`** — Existing helpers Plan 07-01 reuses: `_DEGENERATE_BBOX_EPS` (line 261), `_rect_contains` (line 508), `count_zero_area_fills_fully_inside` (line 699), `replace_region_with_white_raster` (line 746), `cover_zero_area_artefacts` (line 635)
- **`app/services/redact.py:122-258`** — Existing `remove_region_vector` dispatcher (Plan 07-02 insertion target line 195 boundary)

### Secondary (MEDIUM confidence — verified with multiple sources)

- **PDF Association cheat sheet** [https://pdfa.org/download-area/cheat-sheets/OperatorsAndOperands.pdf] — Path operators table (binary PDF; content cross-referenced with training knowledge)
- **WebFetch pdf-issues.pdfa.org/32000-2-2020/clause08.html** [CITED 2026-05-28] — ISO 32000-2 §8 path-painting operators table (errata excerpt — full operator list verified via training)
- **WebSearch ISO 32000-1 §7.8 content stream operators** [VERIFIED 2026-05-28 via multiple search results] — `m`/`l`/`c`/`v`/`y`/`h`/`re`/`S`/`s`/`f`/`F`/`f*`/`B`/`b`/`B*`/`b*`/`n` operand counts and semantics
- **`.planning/research/STACK.md`** — PyMuPDF 1.27.x pin verified; FastAPI/Pillow/numpy versions
- **`.planning/research/PITFALLS.md`** — Pitfall 3 (true removal vs cover), Pitfall 4 (vector survivors), Pitfall 8 (CAD-PDF scale), Pitfall 11 (parser isolation)
- **`.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-PATTERNS.md`** — Pattern S1 multi-stream write-back verbatim; Risk Callouts #3 (xfail decorator order) + #4 (multi-stream verbatim)
- **`.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`** — T-02-07 RE-OPENED + T-06-01 NEW (both `accept (P0, transition-pending until Phase 7 closes)`); supersedes chain via frontmatter

### Tertiary (LOW confidence — flagged in Assumptions Log)

- Assumption A1 (seqno monotonicity) — **partially verified** via live spike on 20 ZAFs; full N=3396 not verified
- Assumption A3 (get_drawings excludes Form XObject paths) — **partially verified** via spike (mixed-glyph-01 has 0 xobjects, so direct test not possible); Plan 07-01 should add defensive test
- Assumption A4 (`update_stream` writes visible to subsequent `read_contents` on same Document handle) — likely correct per Phase 6 attack helper precedent; Plan 07-01 should test explicitly

## Metadata

**Confidence breakdown:**
- Standard Stack: **HIGH** — Context7 + WebFetch + local dev verification
- Architecture Patterns: **HIGH** — Hybrid strategy validated via live spike on real-supplier fixtures (`mixed-glyph-01.pdf` 3396 ZAFs)
- Common Pitfalls: **HIGH** — Pitfalls 1-9 empirically observed in spike or carried forward verbatim from Phase 6 (e.g. WR-02 regex caveat)
- Code Examples: **HIGH** — Skeletons compile, regex patterns tested against real content stream
- Security Domain: **HIGH** — T-06-01 + T-02-07 mapping is direct from `06-SECURITY.md` with verified closing condition
- Test coverage: **HIGH** — TEST-03 5 categories covered + density gradient parametrized; xfail flip mechanism documented

**Research date:** 2026-05-28
**Valid until:** Phase 7 implementation completion (no new PyMuPDF releases expected in <30 days that would invalidate the API surface; pinned to 1.27.x). For any future reuse of this research file (e.g. retrospective Phase 8 review), check `python -c "import fitz; print(fitz.version)"` matches 1.27.x.

**Key files referenced (absolute paths):**

- `C:\Users\scott\Dropbox\Working area\code PDF logo\app\services\pdf_engine.py` (production target for Plan 07-01 helpers)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\app\services\redact.py` (production target for Plan 07-02 dispatcher insertion at line 195)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\tests\_illustrator_attack.py` (PATTERNS S1 verbatim reference)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\tests\test_illustrator_attack_regression.py` (Plan 07-02 xfail flip target at lines 73-82)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\tests\test_redact.py` (line 691-794 end-to-end + line 722-728 Shape.draw_rect(W=0) injection pattern; line 1190-1207 AGPL guard)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\tests\conftest.py` (in-memory builders + `isolated_data_dir` + `logo_library` fixtures)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\tests\fixtures\cad-glyph\mixed-glyph-01.pdf` (3396 ZAF spike target)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\tests\fixtures\cad-glyph\text-glyph-01.json` (sidecar manifest schema reference)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\.planning\phases\06-regression-foundation-threat-model-re-evaluation\06-PATTERNS.md` (Pattern S1 + Risk Callouts)
- `C:\Users\scott\Dropbox\Working area\code PDF logo\.planning\phases\06-regression-foundation-threat-model-re-evaluation\06-SECURITY.md` (T-02-07 + T-06-01 closing target)

---

*07-RESEARCH.md authoring complete — Phase 7 Option B implementation hybrid strategy locked.*
*Next step: Planner consumes this research to produce Plan 07-01 (helper + TEST-03) and Plan 07-02 (dispatcher + xfail flip).*
