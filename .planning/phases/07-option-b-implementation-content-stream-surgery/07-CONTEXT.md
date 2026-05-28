# Phase 7: Option B Implementation — Content-Stream Surgery - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 7 是 v1.1 milestone 的「轉綠」核心 — 在 `app/services/pdf_engine.py`(AGPL seam,fitz 唯一允許 import 的檔案)落地 **Option B helper**:**真正刪除 page-level 內容串流中 fully-inside-rect 的零面積 `type='f'` `m/l/f/B` 算子序列**。對 Phase 6 紅燈 regression test 形成「真正轉綠」的觀測點 — 三個 xfail-strict test 在 Option B 落地後應產生 `XPASS(strict)` 強迫拔 marker → 升級為 PASSED。

**三項核心交付:**

1. **`app/services/pdf_engine.py::delete_zero_area_type_f_fills_inside(page, user_rect, tolerance=_DEGENERATE_BBOX_EPS) -> int`** — 新 helper,以 regex 解析 page-level content stream(`page.read_contents()`),配合 5 個 commenting/literal-context safe-skip 規則(BT/ET 文字段、BI/EI/ID inline images、`(...)` literal、`<...>` hex、`%...\n` 註解),刪除 fully-inside-rect 的零面積 `m/l/f/B` 算子序列。multi-stream write-back pattern 沿用 Phase 6 PATTERNS S1 的 verbatim 風格(寫到 content_xrefs[0] + 清空 [1:])。

2. **`app/services/redact.py` 內 dispatcher 插入 Option B**:在 line 195 `residual_content` assertion 之後、line 232 `zero_area_count` 之前,呼叫新 helper。Option B 為「upstream defense」— 跑完後 page-level zero-area count 一般歸 0,既有 Phase 4-6 dispatcher(dense → Option A overlay / sparse → cover_zero_area_artefacts)只剩 form-XObject 內巢狀殘留時才會觸發,作 last-mile defense。

3. **`tests/test_pdf_engine.py`(或 `tests/test_redact.py` 新節)TEST-03 單元測試**:zero-area fill counter 已有覆蓋,新增 boundary 判定(safe-skip 5 context 不誤刪)、form-XObject 巢狀偵測(page-level only)、SEC-02 no-op 行為(input 無 zero-area fill)、密度梯度(0/1/100/1742 個 zero-area fill)。**Phase 6 的 3 個 xfail-strict regression test 在 Plan 07-02 中拔 marker 升級為 PASSED**,作 SEC-01 acceptance gate(同步 SEC-02 透過 full pytest suite verify baseline 升級為 `304 passed + 3 skipped`)。

**配套(Phase 7 觸發 / 完成的副效應):**

- Phase 6 SECURITY.md 的 T-06-01 + T-02-07 兩條 `accept (P0, transition-pending until Phase 7 Option B)` 在 Phase 7 close 時,Phase 7 自身的 `07-SECURITY.md` 應將其改為 `CLOSED via Option B`,並 cross-reference Phase 6 06-SECURITY.md
- 既有 Hotfix 06 Option A raster overlay 路徑保留為 form-XObject 殘留的 last-mile defense — 不刪除、不重寫
- `count_zero_area_fills_fully_inside`(line 699)+ `ZERO_AREA_RASTER_THRESHOLD=100`(line 294)+ `_DEGENERATE_BBOX_EPS=0.01`(line 261)沿用 — Option B 與既有 helper 共用 tolerance 對齊(避免 IN-01 drift)

**Carrying forward(前期已鎖定,本階段不重複決定):**

- **AGPL seam** — `import fitz` 嚴格限制 `app/services/pdf_engine.py`(Phase 1-6 AST guard test 持續綠燈)。Phase 7 新 helper 全在 `pdf_engine.py` 內;`redact.py` 的 dispatcher 改動 ≤ 6 行(呼叫新 helper + structured logger.warning),不引入 fitz import
- **5330290 教訓** — minimum-change + sufficient-testing。Phase 7 為 hotfix-class implementation,Option B helper 自身嚴格限縮在 page-level content-stream surgery scope;不夾帶 polish(nice-to-have 改進留下個 maintenance sprint)
- **既有 dispatcher 不拆** — Option B 插在 dispatcher 前作為「upstream defense」,既有 dense-branch(Option A overlay)+ sparse-branch(`cover_zero_area_artefacts`)保留為 last-mile defense
- **既有 `count_zero_area_fills_fully_inside` 與 `_DEGENERATE_BBOX_EPS=0.01` 沿用** — Phase 6 regression test 與 Option B assert 都呼叫此函式,tolerance 對齊不變(IN-01)
- **Test baseline 升級期望** — Phase 6 留下「301 passed + 3 skipped + 3 xfailed」(包含 Phase 6 3 個 xfail-strict)。Option B 落地後 3 個 XPASS(strict) 報失敗 → Plan 07-02 拔 `@pytest.mark.xfail(strict=True)` decorator → 升級為「304 passed + 3 skipped」+ TEST-03 新單元測試 N 條(預期再加 ~6-10 個 case);final baseline 約 `(304 + N) passed + 3 skipped`
- **繁中文案** — error message、`# HONEST LIMITATION` docstring 區段、logger event message 都繁中
- **commit/push 節奏(memory feedback_commit_push_cadence)** — UAT 期間 commit local but never push;Phase 8 final code-review pass 後才 push。Phase 7 每 task atomic commit
- **Phase 6 3 個 sanitized real-supplier fixture + xfail-strict regression test 為驗收 ground truth** — Option B 落地後三個 fixture 都該 XPASS(strict)
- **pytest 與 PyMuPDF 既有 pinned 版本沿用** — 不引入新 runtime / dev 套件

**Phase 7 不含(歸 Phase 8 或 out-of-scope):**

- 三處 `LIMITATION (be honest)` docstring 同步更新(Phase 8 THREAT-02 + DOC-01)— Option B 落地後三處 docstring 仍會保留(文字會在 Phase 8 改寫)
- `HANDOFF.md` 6.5 小節新增(Phase 8 DOC-01)
- `PROJECT.md` Key Decisions「Hotfix v1.1 — Option B 落地」決策列(Phase 8 DOC-02)
- LIVE 部署 + LIVE-UAT 端到端驗證(Phase 8 DEPLOY-01)
- **對 form XObject 內 zero-area fills 做遞迴 content-stream surgery**(SEC-03 out-of-scope — page-level only + log;實際樣本出現再評估,deferred items 已記 STATE.md)
- **對 zero-area `type='s'`(stroke)做 surgery**(out-of-scope — 威脅證據都是 type='f',stroke 未出現殘留問題)
- **Auto-detect supplier-source heuristic dispatcher**(REQUIREMENTS.md Out of Scope — Option B 為 no-op-safe,加 detection 過度設計)
- **`cover_zero_area_artefacts` / Option A overlay 路徑重寫**(保留為 last-mile defense)
- 任何 `app/services/redact.py` 之外的 production code 變更(production-code 改動 scope 嚴格限縮在 `pdf_engine.py` 加新 helper + `redact.py` 加 ≤ 6 行 dispatcher 變更)

</domain>

<decisions>
## Implementation Decisions

### Content-stream parsing 策略(Area A)

- **D-A1:** Option B helper 採 **regex-based parsing of `page.read_contents()`** 找出 zero-area `m/l/f/B` 算子序列,而非 token-based parser(規範但重)或 `page.get_drawings()` reverse-lookup(需 fitz API 未證實的 offset 映射)。Phase 6 `tests/_illustrator_attack.py` 已對同類 PScript5 + Acrobat 出口 PDF 用 regex 做 content-stream surgery(刪 `q ... /XObjN Do ... Q` block)實證成功,Option B 採同一套思路;3 個 sanitized fixture 全為 PScript5 + Acrobat 出口,實際風險可控。
- **D-A2:** Regex matcher 需 **明確 safe-skip 5 種 commenting / literal context**,避免假陽性刪除:
  1. **BT...ET 文字段**(text-show 內可能含 m/l 字元的 hex string)— 識別 `BT` 與 `ET` token,跳過內部 byte 範圍
  2. **BI...EI / ID...EI inline images**(`BI ... ID ... EI` 內含任意 binary bytes)— 識別 token,跳過內部 byte 範圍
  3. **`(...)` literal strings**(PostScript-style strings,可能含 `m`/`l`/`f`/`B` 字元)— 進入 `(` 後到匹配的 `)` 為止跳過(考慮 nested `\(` `\)` escape)
  4. **`<...>` hex strings**(可能含 `<6D 6C 66 42>` 看起來像操作子但是 hex data)— 進入 `<` 後到匹配的 `>` 跳過
  5. **`%...\n` comments** — 進入 `%` 後到下一個換行跳過
- **D-A3:** Zero-area 判定門檻 = `_DEGENERATE_BBOX_EPS = 0.01`(沿用 pdf_engine.py:261 既有常數)。**helper 簽名:**
  ```python
  def delete_zero_area_type_f_fills_inside(
      page: "fitz.Page",
      user_rect: "fitz.Rect",
      tolerance: float = _DEGENERATE_BBOX_EPS,
  ) -> int:
      """Returns count deleted."""
  ```
- **D-A4:** **Multi-stream write-back pattern** 沿用 Phase 6 PATTERNS S1(`tests/_illustrator_attack.py` 內 verbatim port from scratch lines 104-115):
  ```python
  content_xrefs = page.get_contents()
  if len(content_xrefs) == 1:
      doc.update_stream(content_xrefs[0], new_bytes, compress=True)
  else:
      doc.update_stream(content_xrefs[0], new_bytes, compress=True)
      for xref in content_xrefs[1:]:
          doc.update_stream(xref, b"", compress=True)
  ```
  Phase 7 不重新發明 — **同樣 asymmetric write [0] + empty [1:] 結構保留,research 引導 planner 沿用**。
- **D-A5(Error handling 之 Claude 裁量):** Option B 採 **fail-safe** 而非 raise — 若 regex parsing 漏抓某 `m/l/f/B` 序列或內部 byte-offset 計算出錯,helper 回傳 0 deleted + 觸發 `logger.warning("option_b_parse_anomaly", extra={...})`,不 raise RedactError。**理由:**(a) 5330290 minimum-change 紀律 — Option B 失敗不該 break v1.0 baseline pipeline;(b) 既有 Hotfix 06 Option A overlay + `cover_zero_area_artefacts` 仍在 dispatcher 內接 last-mile defense;(c) Phase 6 regression test 仍會抓到失敗(Option B 沒刪乾淨 → count > 0 → dispatcher 走 dense/sparse branch → attack test 可能 XFAIL 而非 XPASS,implementer 看到後自然 debug)。

### Form XObject 安全偵測(Area B / SEC-03)

- **D-B1:** **「page-level only」自動掉出於 `page.read_contents()` scope** — fitz 的 `page.read_contents()` 只回傳 page 層 content stream(`/Contents` array 串接的 bytes),完全不碰 XObject 內部 content stream(那些獨立 xref + 獨立 `xref_stream()` 呼叫才能讀)。Option B 對 `page.read_contents()` 跑 regex = 天然只動 page-level 算子,不會誤改 form XObject 內部巢狀 path。
- **D-B2:** **Frame intersect form XObject 時 log 規格** — 採 Python stdlib `logging.warning` + structured event:
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
  intersect 偵測 cheap-fast:
  ```python
  n_intersecting = 0
  for xobj in page.get_xobjects():
      xobj_rect = fitz.Rect(...)  # bbox extraction TBD by planner
      if xobj_rect.intersects(user_rect):
          n_intersecting += 1
  ```
  XObject 內部不下鑽、不抓內部 paths。**前端不感知** — 不修改 process result dict、不修改 `web/js`(Phase 8 才考慮 frontend banner;v1.1 不動 frontend)。
- **D-B3:** **Log 觸發條件:每次 Option B 跑時都檢查 + log(若有 intersect)**,而非「Option B 刪了 0 個才 log」 — 因為 form-XObject 內部可能本來就有 zero-area path,Option B 在 page-level 刪了 N 個,但 XObject 內部還剩 M 個,需要 transparently 告訴後續 review/audit 知道 page-level 不是全部攻擊面。
- **D-B4:** **page-level Option B 跑完後若 `count_zero_area_fills_fully_inside` 仍 > 0,代表 form-XObject 內巢狀殘留** — 既有 dispatcher 自然接(若 count ≥ 100 走 Option A overlay;若 < 100 走 cover_zero_area_artefacts)。 **這個邊界是 Phase 7 + 既有 Phase 5 Hotfix 06 共構防線 — 不誤改 form XObject(SEC-03 滿足),又對 form XObject 殘留有 last-mile defense。**

### 插入點在 redact.py(Area C)

- **D-C1:** **`redact.py` 插入點 = line 195 `residual_content` assertion 之後、line 232 `zero_area_count = pdf_engine.count_zero_area_fills_fully_inside` 之前**。插入塊 ~6-10 行,結構大致為:
  ```python
  # Phase 7 Option B — page-level content-stream surgery (SEC-01)
  # 真正刪除 fully-inside-rect 零面積 type='f' fills,upstream defense before
  # existing Phase 5 Hotfix 06 dispatcher(form-XObject 內巢狀殘留時才會
  # 走 dense/sparse last-mile defense)。
  deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
  if deleted > 0:
      logger.info("option_b_deleted", extra={"page_index": page.number, "count": deleted})
  # form-XObject intersect log(SEC-03 page-level only 策略透明化)
  pdf_engine.log_xobject_intersect(page, user_rect, logger=logger)
  ```
  (`log_xobject_intersect` 可放在 pdf_engine.py 作 fitz-internal helper,或在 redact.py 直接呼叫 `page.get_xobjects()` — planner 決定。**注意:** pdf_engine.py 是 fitz seam,把 fitz-aware 邏輯放裡面是正確分層。)
- **D-C2:** **既有 dispatcher 不重寫** — line 232-256 的 `if zero_area_count >= ZERO_AREA_RASTER_THRESHOLD` / `else cover_zero_area_artefacts` 邏輯保留為 last-mile defense。Phase 7 不動 `replace_region_with_white_raster` / `cover_zero_area_artefacts` 任何一行(per 5330290 minimum-change)。
- **D-C3:** **`logger` 從哪來?** — `redact.py` 既有 import 結構若無 `logging` import,Plan 07-02 task 加 `import logging` + `logger = logging.getLogger(__name__)` 一條(non-fitz import,不破 AGPL seam)。**`pdf_engine.py` 亦同**(已有 logging 則沿用)。

### Plan split 與測試覆蓋(Area D)

- **D-D1:** **2 plans split**:
  - **Plan 07-01(Wave 1)** — `pdf_engine.py` 加 `delete_zero_area_type_f_fills_inside` helper + `log_xobject_intersect` helper(if planner 採此分層)+ **TEST-03 單元測試**(下方 D-D3 詳列覆蓋)。Plan 07-01 不動 `redact.py`,只新增 pdf_engine.py 內 function + 新增 test 檔。Plan 07-01 close 時 Phase 6 xfail 仍紅(integration 還沒接)。
  - **Plan 07-02(Wave 2,depends_on: [07-01])** — `redact.py` line 195 後插入 Option B 呼叫 + form-XObject intersect log + 拔 `tests/test_illustrator_attack_regression.py` 3 個 `@pytest.mark.xfail(strict=True)` decorator + pytest 驗證 baseline 升級為「304 passed + 3 skipped + N 個 TEST-03 新 test pass」。Plan 07-02 close 時 Phase 6 三個 xfail flip 為 passed(SEC-01 acceptance gate 通過)。
- **D-D2:** **Plan dependency 結構** — 07-01 Wave 1(no upstream deps within Phase 7);07-02 Wave 2(`depends_on: [07-01]`,需 helper 存在才能 wire 進 redact.py + 才能 flip xfail)。對齊 Phase 6 同型 2-plan split,執行流程清晰。
- **D-D3:** **TEST-03 單元測試覆蓋(per ROADMAP Success Criteria #3):**
  1. **zero-area fill counter accuracy**(既有 `count_zero_area_fills_fully_inside` 沿用,Phase 4-6 已測;Plan 07-01 加 sanity check 與 Option B 整合的對齊)
  2. **content stream rewrite 算子序列邊界判定**:
     - 5 個 safe-skip context 各一 test:BT/ET / BI/EI/ID / `(...)` / `<...>` / `%...\n` 內的 m/l/f/B 字元不誤刪
     - 「正常的 m/l/f/B 序列」test:確認真實的零面積 type='f' 算子序列被正確刪除
     - 「m/l/f/B 但非零面積」test:確認非零面積(正常 width/height)算子序列不被誤刪(SEC-02 no-op)
  3. **form XObject 巢狀偵測(page-level only,不下鑽)**:
     - 構造一個 page 含 form XObject(內含零面積 type='f' fills),呼叫 Option B
     - assert page.read_contents() 的 page-level 操作子改變(刪了 page-level zero-area)
     - assert form-XObject xref 的 stream **沒變**(XObject 內部不下鑽)
     - assert `logger.warning("option_b_xobject_intersect")` 被觸發
  4. **no-op 行為**:input PDF 完全無 zero-area `type='f'` fill(典型 v1.0 vector 商標 PDF):
     - 跑 Option B → 回傳 0 deleted、page.read_contents() bytes 一字未改、無 logger.warning
     - 對 v1.0 既有 fixture 跑 full pytest suite 仍綠(301 passed → 304 passed 後仍 stable;baseline 不退步)
  5. **密度梯度**:0 / 1 / 100 / 1742 個 zero-area fill 條件(per ROADMAP Success Criteria #3):
     - 0 個:no-op verify(同 #4)
     - 1 個:刪 1 個的 cardinality + bytes-changed boundary
     - 100 個(`ZERO_AREA_RASTER_THRESHOLD` 邊界):Option B 刪到 0 → dispatcher 不觸發 dense branch
     - 1742 個(對齊 `mixed-glyph-01.pdf` 既有 fixture 密度):Option B 刪到 0 → Phase 6 mixed-glyph regression test 預期 XPASS
- **D-D4:** **Phase 6 xfail flip 機制**(Plan 07-02 內):
  - `grep -rn "xfail.*Option B" tests/` 找到 `tests/test_illustrator_attack_regression.py:74-83` 的 marker
  - 拔掉 `@pytest.mark.xfail(strict=True, reason="Option B pending in Phase 7 — ...")` decorator(保留 `@pytest.mark.parametrize`)
  - 把 reason 改寫為(可選)removed 或 comment 為何 flip(audit trail)
  - 跑 `python -m pytest -k illustrator_attack -v` 應顯示 3 PASSED(原 XFAIL 升級)
  - 跑 `python -m pytest 2>&1 | tail -5` 應顯示 `304 passed + 3 skipped` 與 TEST-03 額外 N pass(non-regression)

### Claude's Discretion

- **fitz API 探查方法** — `page.get_xobjects()` 的回傳結構在 PyMuPDF 1.27.x 應為 `[(xref, name, ...), ...]`;對應 `Resources/XObject` 字典 + bounding rect 抽取方法,researcher 應 webfetch 確認;planner 可在 Plan 07-01 內 spike 5 分鐘確認 API surface,失敗 fallback 為 `page.read_contents()` 內部找 `/XObjN Do` operator 出現的 CTM matrix 計算 bbox(更複雜)
- **`log_xobject_intersect` 放 pdf_engine 還是 redact.py?** — 推薦放 `pdf_engine.py`(fitz-aware logic 集中)+ accept `logger` 作 argument 注入(避免 pdf_engine 內 hardcode logger),redact.py 呼叫 + 傳 logger
- **Regex pattern 設計** — 推薦結構:`r"(?P<pos>(?:m|l|c|h)\s+)+(?P<close>f|B)"` 之類找出 path 算子序列,**但需要前置的 safe-skip state machine 跑一輪先 mark 跳過區段** — researcher 可參考 Phase 6 `tests/_illustrator_attack.py` 內 regex `r"q\b[^Q]*?/" + name + r"\s+Do\b[^Q]*?Q\b"` 寫法但不抄(目標 pattern 不同)
- **Test 檔案放置** — 推薦 `tests/test_pdf_engine.py`(若不存在則新建)或在 `tests/test_redact.py` 加新 `class` / `class TestOptionB`(沿用既有檔慣例)— planner 決定
- **`08-SECURITY.md` 同步? — 不在 Phase 7 scope** — Phase 7 自身 `07-SECURITY.md`(若 gsd-secure-phase 跑)會 close T-06-01 + T-02-07;Phase 8 不重寫 07-SECURITY,而是把 T-06-01 + T-02-07 的 close 記入 08-SECURITY 並做 cross-reference
- **Phase 7 SUMMARY.md xfail-flip evidence pattern** — 把 「Phase 6 regression test 3 XFAIL → 3 PASSED」的 git diff 與 pytest output 嵌入 SUMMARY.md 作 acceptance evidence(同 Phase 6 06-02-SUMMARY 對 baseline 升級的 evidence 模式)
- **Plan 07-02 xfail decorator 完全拔還是僅改 reason 字串?** — 推薦**完全拔**(per Phase 6 D-D-Option-A xfail-strict 設計目的:Phase 7 implementer 一旦 XPASS(strict) 即強迫拔掉 marker → 自然 flip 為 PASSED;reason 字串本來只在 marker 存在時有意義)。若要保留歷史可在 commit message 加 cross-reference 但不在 code 內留 reason
- **既有 `logging` import 確認** — `app/main.py` 已用 `logging` (FastAPI 結構),`app/services/` 內各模組是否已有 logger 視情況 — Plan 07-01 task 加 import 時若 redundant 則略過

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level lockfiles
- `.planning/PROJECT.md` — Key Decisions 表 + Active milestone v1.1 進度條(Phase 7 ⏳);特別 Hotfix 06 Option A 既有架構 + 5330290 minimum-change 教訓 + AGPL seam 鎖定
- `.planning/REQUIREMENTS.md` — Phase 7 對應 SEC-01 / SEC-02 / SEC-03 / TEST-03(11 reqs traceability 表已填 100%)
- `.planning/ROADMAP.md` § "Phase 7: Option B Implementation — Content-Stream Surgery"(goal、5 條 success criteria、Mode: hotfix-class implementation、Depends on Phase 6)
- `.planning/STATE.md` — milestone v1.1 進度 + Phase 6 close decisions(包含 Phase 7 接手需要的 baseline state)

### Phase 6 artifacts(Phase 7 依賴 + 對接)
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-CONTEXT.md` — Phase 6 鎖定的 sanitize / fixture / regression-test 設計
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-RESEARCH.md` — § Pattern 3 + § Anti-Patterns + § Open Questions(全 RESOLVED)
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-PATTERNS.md` — **特別 PATTERNS Shared Pattern S1**(multi-stream content-stream write-back verbatim,Plan 07-01 Option B helper 必須遵循同模式)+ Risk Callouts(其中 #4 multi-stream verbatim 對 Phase 7 同樣適用)
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md` — **特別 T-06-01 + T-02-07 兩條 `accept (P0, transition-pending until Phase 7 Option B)`** — Phase 7 close 時 07-SECURITY.md 應 close 此二條為 `CLOSED via Option B`
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-01-SUMMARY.md` — Phase 6 sanitize_fixture.py + fixture 構成(3/3 real supplier);特別 § Provisional → Final 升級記錄 對 Phase 7 implementer 提供 fixture 來源
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-02-SUMMARY.md` — Phase 6 attack helper + xfail-strict regression test 結構;特別 § Known Issues 對 mixed-glyph-01 q...Q wrap quirk 的 note(Plan 07-01 應確認 Option B 的 regex 對 mixed-glyph 也能命中,因為 mixed 沒被 q...Q 包但仍是 m/l/f/B 算子序列)
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-VERIFICATION.md` — Phase 6 verification PASSED status + 10 critical invariants;Phase 7 須維持 production code 0 changes invariant(僅變更 pdf_engine.py + redact.py)

### v1.0 archived artifacts(Phase 7 不 supersede 但需 cross-reference)
- `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md` — 原 T-02-07 `CLOSED with documented residual` 狀態(Phase 6 已 RE-OPENED);Phase 7 Option B 落地後 close 為 `CLOSED via Option B`,並 cross-reference 此檔的 supersede 鏈

### Forensic 證據(Phase 7 acceptance proof)
- `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png` — Illustrator 拔 image XObject 後供應商商標重現的視覺證據;Phase 7 Option B 落地後同等攻擊應 fail(render 區 ≥98% 白 — Phase 6 regression test SEC-01 acceptance gate)
- `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_target_pre.png` / `_attack_orig_for_comparison.png` — Phase 7 implementer 落地後可選地手動跑 attack 重 render 比對(SEC-01 visual acceptance)

### Production code(Phase 7 改動 targets — 嚴格限縮)

**`app/services/pdf_engine.py`(AGPL seam — Plan 07-01 加 helper):**
- `_DEGENERATE_BBOX_EPS = 0.01`(line 261)— Option B helper 沿用此 tolerance
- `ZERO_AREA_RASTER_THRESHOLD = 100`(line 294)— Phase 7 不動;Option B 跑完後若 count > 0 才會接到此 threshold dispatcher
- `count_zero_area_fills_fully_inside(page, rect, tolerance=_DEGENERATE_BBOX_EPS) -> int`(line 699)— Plan 07-01 unit test 用 + Option B 內部可呼叫驗證(non-essential dependency)
- `replace_region_with_white_raster(page, rect)`(line 746)— Phase 7 **不動**,保留為 form-XObject 殘留的 last-mile defense
- `cover_zero_area_artefacts(page, rect)`(line 635 區段)— Phase 7 **不動**,保留為 sparse-residue last-mile defense
- `add_redact_annot`(line 312)+ `apply_redactions`(line 340)— Phase 7 **不動**,既有 Phase 1-4 流程不變

**`app/services/redact.py`(Plan 07-02 dispatcher 插入點 ≤ 6-10 行):**
- Line 174-179:`apply_redactions` 既有 — Phase 7 **不動**
- Line 189-195:`residual_content` 斷言既有 — Phase 7 **不動**
- **Line 195 後 + Line 232 前:Phase 7 新增 Option B 呼叫 + log_xobject_intersect**(Plan 07-02 task)
- Line 232-256:既有 `zero_area_count` dispatcher 與 dense/sparse branch — Phase 7 **不動**,作 last-mile defense

**Phase 7 production-code 改動範圍 audit:**
- `git diff --stat <plan-07-01-base>^..HEAD -- 'app/'` 應只命中 `app/services/pdf_engine.py` 與 `app/services/redact.py` 兩檔
- `grep -rn "import fitz" app/` 仍只在 `app/services/pdf_engine.py:19` 一行(AGPL seam 不破)
- v1.0 既有 fixture 跑 full pytest suite 仍綠(原 301 + 3 skipped → 因 Phase 6 多 3 xfailed = 304 + 3 skipped after Plan 07-02 flip;再加 TEST-03 新 N 個 unit test = (304+N) + 3 skipped)

### Test infrastructure(沿用 + 擴充)

- `tests/conftest.py` § Line 12 註解「only the test harness may use fitz directly to BUILD fixtures」— Plan 07-01 TEST-03 unit tests 可在 conftest 用 fitz 建構 in-memory PDFs(zero-area fills、form XObjects、edge cases),沿用 Phase 4-6 既有 fixture builder pattern
- `tests/test_redact.py` § `test_remove_region_vector_dense_real_zero_area_paths_end_to_end`(line 691-794)— Plan 07-01 unit test 可借鏡同套「合成 PDF → 跑 pipeline → assert」結構;特別 line 722-728 的 `Shape.draw_rect(W=0)` zero-area 注入 pattern 可建構 TEST-03 密度梯度 case(0/1/100/1742)
- `tests/test_redact.py::test_fitz_import_confined_to_engine_seam`(line 1190-1207)— Plan 07-01 + 07-02 不可破壞;AST guard 持續綠燈為 Phase 7 完成的 hard invariant
- `tests/test_illustrator_attack_regression.py`(Phase 6 produced)— Plan 07-02 拔 xfail marker(line 74-83)+ 跑 verify 3 PASSED
- `tests/_illustrator_attack.py`(Phase 6 produced)— Plan 07-02 不動(此檔是 attack helper,不是 Option B mitigation);但 Phase 7 implementer 可參考其 regex pattern + multi-stream write-back 作 Plan 07-01 helper 的設計類比
- `tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.pdf`(Phase 6 produced)— Plan 07-02 regression verification ground truth(3/3 real supplier sanitized fixture)

### Research scope(Plan 07-01 phase-researcher 應 webfetch / 驗證)
- `.planning/research/STACK.md` — PyMuPDF 1.27.x API surface(`page.read_contents` / `page.get_contents` / `doc.update_stream` / `page.get_xobjects` / fitz.Rect 算術)
- `.planning/research/PITFALLS.md` — Pitfall 8(大型 / 旋轉 / OCG)、Pitfall 11(parser isolation / tempfile lifecycle)
- **PyMuPDF docs**(planner / researcher webfetch):`page.get_xobjects()` 回傳結構 + `Resources/XObject` dict 解析方法 + `xref_stream(xref, compressed=True)` write-back behaviour confirmation
- **PDF spec ISO 32000-1**:Section 7.8 content streams + Section 7.8.2 content stream operators(完整 m/l/c/h/f/F/B/b/B*/b* 算子表 + BT/ET BI/ID/EI 段邊界規則)— planner 與 implementer 應參考但不需重寫 parser

### Cross-references
- `CLAUDE.md` § "GSD Workflow Enforcement"(commit 經 GSD workflow)+ "Tech stack" section 對 PyMuPDF redaction confirm 文字 — Phase 7 是這個技術描述的真正落地
- `HANDOFF.md`(Phase 6 produced)— Phase 7 不更新 6.5 小節(Phase 8 DOC-01);但 implementer 應讀 §6 「核心領域知識備忘」確認 Option A overlay 與本 phase Option B 的分工
- README.md(repo root)— Phase 7 不動;AGPL §13 三件套既有就位

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`app/services/pdf_engine.py::count_zero_area_fills_fully_inside(page, rect, tolerance)`** (line 699) — Option B helper 內部可呼叫此函式作 sanity 對齊;TEST-03 unit tests 直接用此函式驗證刪除結果(post-Option-B count 應 = 0)
- **`app/services/pdf_engine.py::_DEGENERATE_BBOX_EPS`**(line 261)— Option B 沿用此 tolerance,test fixtures 構造時用同 epsilon 避免 IN-01 drift
- **`tests/_illustrator_attack.py`**(Phase 6 produced)— **regex content-stream surgery 同套思路的 working example**;Plan 07-01 helper 可借鏡其 q...Q block 刪除 + multi-stream write-back pattern,但 Option B 的目標 pattern 不同(m/l/f/B 算子序列 vs q...Q wrap)
- **`tests/test_redact.py::test_remove_region_vector_dense_real_zero_area_paths_end_to_end`**(line 691-794)— end-to-end 「合成 PDF → 跑 pipeline → assert」pattern;Plan 07-01 unit tests 借鏡其結構但只測 Option B helper,不跑完整 pipeline
- **`tests/conftest.py`** in-memory PDF / image builders — Plan 07-01 unit tests 沿用既有 `_build_pdf` / `_build_*_pdf` builders + `Shape.draw_rect(W=0)` zero-area 注入 pattern
- **`fitz.Rect(...).intersects(other)`**(PyMuPDF 1.27.x 公開 API)— Plan 07-01 form-XObject intersect 偵測直接用

### Established Patterns

- **fitz AGPL seam:** `import fitz` 只在 `app/services/pdf_engine.py:19`,AST-level guard test enforces — Plan 07-01 helper 全在 `pdf_engine.py` 內;Plan 07-02 `redact.py` 改動 ≤ 6-10 行 + 新 `import logging`,不引入 fitz import
- **多 stream write-back asymmetric pattern**(PATTERNS S1 verbatim):`write to [0] + empty [1:]` 結構保留(Plan 07-01 Option B helper 必須沿用)
- **Typed `*Error(code, message)` + main.py 對應 4xx/5xx**(IngestError / LogoError / PipelineError / RedactError / ...)— Phase 7 **不新增** typed error class(per D-A5 fail-safe — Option B parse anomaly 走 logger.warning 而非 raise)
- **繁中錯誤訊息 + docstring** — Plan 07-01 helper docstring 加繁中 `HONEST LIMITATION` 區段或註解
- **In-memory test fixture(`_build_pdf` 系列)**:Plan 07-01 TEST-03 unit tests 沿用,**不 commit 新 binary fixture**;Phase 6 `tests/fixtures/cad-glyph/` 是 commited-binary 唯一例外,Phase 7 不擴充此例外
- **PyMuPDF `Shape.draw_rect(...,W=0).finish(fill=...).commit()` zero-area type='f' 注入**(`tests/test_redact.py:722-728`)— Plan 07-01 unit tests 用此 pattern 構造 TEST-03 密度梯度 fixtures

### Integration Points

- **新增 helper in `app/services/pdf_engine.py`**:
  - `delete_zero_area_type_f_fills_inside(page, user_rect, tolerance=_DEGENERATE_BBOX_EPS) -> int`(core helper)
  - `log_xobject_intersect(page, user_rect, logger) -> int`(form-XObject intersect log helper,亦可 inline 在 redact.py — planner 裁量)
  - 兩個 helper 在 pdf_engine.py 中與既有 `count_zero_area_fills_fully_inside`(line 699)、`replace_region_with_white_raster`(line 746)、`cover_zero_area_artefacts`(line 635 區段)同層;命名與 docstring 風格沿用既有 hotfix 06 pattern
- **`app/services/redact.py` 插入點 line 195 後**:
  - 加 `import logging` + `logger = logging.getLogger(__name__)`(若無)
  - 呼叫 Option B helper + logger.info("option_b_deleted", ...)
  - 呼叫 log_xobject_intersect(page, user_rect, logger)
  - **不動 dispatcher line 232-256**
- **新增測試檔**:`tests/test_pdf_engine.py`(若不存在則 Plan 07-01 task 新建)或在 `tests/test_redact.py` 加新 `class TestOptionB`(planner 決定)— 沿用既有 pytest 結構

### What Phase 7 does NOT touch

- `app/services/pipeline.py` — `process_job` 流程不變;Phase 7 不沾 pipeline 層
- `app/services/coords.py` / `app/services/ingest.py` / `app/services/integrity.py` / `app/services/janitor.py` — 都不動
- `app/api/*.py` — 不動;Phase 7 是內部 service 層改動,API 簽名不變
- `app/main.py` — exception handlers 不變;Option B fail-safe 不新增 error code
- `web/**` — 不動;Phase 7 無 user-facing 變化
- `app/config.py` — 不新增 config 常數;Option B 不需要 config 開關
- `tests/_illustrator_attack.py`(Phase 6 produced)— 不動;此檔是 attack helper,Phase 7 對它的關係是「被它的 attack 機制驗收」
- `tests/fixtures/cad-glyph/` — 不動;Phase 6 produced fixtures 為驗收 ground truth
- 任何 Phase 6 之前 archived 的檔案(`v1.0-phases/` / `illustrator-attack-...-archived/`)
- `scripts/sanitize_fixture.py` — 不動(Phase 6 produced;Impl C+D 後續若有 corner case 再走 maintenance,不算 Phase 7 scope)

</code_context>

<specifics>
## Specific Ideas

- **核心場景:** Phase 7 implementer 接手後流程:
  1. `/clear` 開新 session,讀本 CONTEXT.md + 06-RESEARCH.md(理解 PScript5 出口 PDF 的 content stream 結構)
  2. Plan 07-01 起跑:Spike fitz API(`page.read_contents` 是否含 BI/EI 段、`page.get_xobjects` 結構)— 5 min spike,讀 fitz docs 或寫 throwaway script
  3. Plan 07-01 實作:`pdf_engine.py` 加 `delete_zero_area_type_f_fills_inside`(regex + 5 safe-skip context state machine,~80-150 行)+ TEST-03 unit tests(密度梯度 + safe-skip + no-op + form-XObject 巢狀,~150-250 行)
  4. Plan 07-01 close:全綠 TEST-03 + production code 仍 0 改動(只新增 helper 不改既有 function)
  5. Plan 07-02 實作:`redact.py` 插 Option B 呼叫 + log_xobject_intersect(~6-10 行)+ `tests/test_illustrator_attack_regression.py` 拔 3 xfail decorator(~3 個 single-line delete)
  6. Plan 07-02 close:`python -m pytest -k illustrator_attack -v` 顯示 3 PASSED(原 XFAIL flip)+ `python -m pytest 2>&1 | tail -5` 顯示 `304 + N passed + 3 skipped`(N = TEST-03 新 case 數)
- **核心場景:** Phase 6 attacks 在 Phase 7 落地後的行為:
  - `python -m pytest -k illustrator_attack -v` → 3 PASSED(因 Option B 真刪了 page-level zero-area type='f' source,attack 拔了 image XObject 後 render 仍 ≥98% 白 + zero-area count 在框選區 == 0)
  - 對手動跑 attack 腳本(從 archived 還原):`python .planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_delete_image_xobject.py` 應顯示「attack did not visibly reveal supplier content」(原本顯示「ATTACK SUCCEEDED」)
- **使用者體驗(N/A 給 Phase 7):** 純 service-層改動,無 user-facing 變更
- **AGPL §13 合規:** Phase 7 不改 deploy / LICENSE / UI source link;production code 改動只在 `app/services/pdf_engine.py` 與 `app/services/redact.py` 兩檔,在 public GitHub 上公開源碼自動合規
- **追溯路徑:** Phase 7 close 後 `07-SECURITY.md`(若 gsd-secure-phase 跑)應將 Phase 6 06-SECURITY.md 中的 T-06-01 + T-02-07 close 為 `CLOSED via Option B`;`08-SECURITY.md`(Phase 8 produced)應 cross-reference Phase 7 07-SECURITY.md 作為 close evidence。**這個三 phase chain 是 v1.1 milestone 的安全敘事,downstream agents 必須串對。**
- **AGPL seam 不變:** `import fitz` 仍只在 `app/services/pdf_engine.py:19`;新 helper 全在此檔內;`redact.py` 新 `import logging` 不破 seam(stdlib,非 fitz)。Phase 7 完成後 AST guard test 仍綠

</specifics>

<deferred>
## Deferred Ideas

- **對 form XObject 內 zero-area fills 做遞迴 surgery** — v1.1 SEC-03 採 page-level only + log;Phase 7 不下鑽。實際樣本出現 + colleague 整合需求 + 完成 risk assessment 後再評估遞迴方案。(已記 STATE.md Deferred 表)
- **對 zero-area `type='s'`(stroke)做 surgery** — 目前威脅證據都是 type='f';stroke 在 dCt-residue investigation 中未出現殘留問題。Phase 7 不沾。(已記 STATE.md Deferred 表)
- **Auto-detect supplier-source heuristic dispatcher** — REQUIREMENTS.md Out of Scope 明列「不偵測 PDF 來源是不是 CAD 做 dispatcher」— Option B 為 no-op-safe,加 detection 是過度設計
- **Token-based PDF content-stream parser** — D-A1 否決(規範但重 + 5330290 minimum-change);若 future PDF 來源多樣化(非 PScript5 / 非 Acrobat)導致 regex 漏抓率 > 10%,maintenance sprint 再評估升級
- **`pdf_engine.py::page.get_xobjects` 內部 bbox 抽取 helper 通用化** — Plan 07-01 task 限縮在 Option B 用途;若 future 需要 XObject 詳細 metadata（colleague 整合需求）再 promote 為公用 helper
- **Token-based regex pattern generalization** — 第一版 regex 只認 PScript5 風格;若 future supplier PDF 用 Illustrator / Inkscape / TeX 來源,maintenance 再加 pattern variant
- **Option B 跑完之後對 Phase 4 `cover_zero_area_artefacts` 路徑 deprecate** — Phase 7 不動 cover 路徑;若 future 觀察 Option B 落地後 cover 路徑從不觸發 ≥ 6 個月,maintenance sprint 評估 deprecation
- **Option B fail-safe 升級為 raise + caller-side recovery** — D-A5 採 fail-safe;若 future 出現「Option B 漏抓但 dispatcher 也沒接住」的 incident,升級為 raise + 在 pipeline.py 做 graceful recovery
- **Performance benchmark for large PDFs(> 30 pages,> 5000 zero-area fills)** — Phase 7 不沾;若 future LIVE-UAT 觀察 Option B 跑 > 5 秒,加 `--no-option-b` env override 或 background task offload(per Pitfall 8)
- **`07-SECURITY.md` 自動 cross-reference Phase 6 06-SECURITY.md** — Phase 7 close 時 gsd-secure-phase 應產出 07-SECURITY.md;不在本 CONTEXT scope,planner 與 verifier 視需要納入

</deferred>

---

*Phase: 7-option-b-implementation-content-stream-surgery*
*Context gathered: 2026-05-28*
