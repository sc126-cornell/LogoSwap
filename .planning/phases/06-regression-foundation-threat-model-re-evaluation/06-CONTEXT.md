# Phase 6: Regression Foundation + Threat Model Re-evaluation - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 6 是 v1.1 milestone 的「紅燈基線」階段 — 純測試 / 文件層交付,**不動任何 production code**。在 Phase 7 落地 Option B(content-stream surgery)之前先把可量化的「紅燈攻擊測試」立起來,讓 Phase 7 有客觀「綠/紅」可驗。

**三項核心交付:**

1. **`tests/fixtures/cad-glyph/` 收 ≥3 個 sanitized supplier CAD-glyph PDF** — 涵蓋「文字 glyph」+「圖形 glyph」+「複合」representative shapes,從工程師手中真實出問題的 supplier PDF 而來,經 `scripts/sanitize_fixture.py` 一次性脫敏(metadata 清空、供應商公司名以 content-stream find-replace 換成 `TESTCO`、bbox-fingerprint 清理、brand glyph 以同型 zero-area `type='f'` 攻擊面的 `TESTCO` wordmark 替換)。
2. **`tests/test_illustrator_attack_regression.py`(或同等檔名)** — 把 `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py` 的攻擊邏輯改寫成 pytest:對每個 fixture 跑「LogoSwap process → 攻擊腳本 content-stream surgery 拔 image XObject → render 框選區」,assert `白佔比 ≥98%` 且 `zero-area type='f' count in REGION == 0`。**用 `pytest.mark.xfail(strict=True, reason="Option B pending in Phase 7")` 標記** — Phase 7 落地 Option B 後 strict=True 會把 XPASS 報為失敗,強迫 implementer 拔掉 marker(自動 phase handoff signal)。
3. **`.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`** — STRIDE 表新增 `Illustrator-class editor attacker` actor;T-02-07 從 archived `06-HOTFIX-SECURITY.md` 的 "CLOSED with documented residual" 標記為 **RE-OPENED 2026-05-28 (v1.1 Phase 6) — pending Option B**,並 cross-reference 至 Phase 7 未來的 `07-SECURITY.md`(將以 CLOSED via Option B 收口)。

**配套清理:** scratch 腳本 `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py` 退役(邏輯已搬入 pytest),目錄改名 `.../illustrator-attack-2026-05-28-archived/` 並保留 4 個 PNG / PDF 作為 forensic 證據(`_attack_proof_supplier_revealed.png` 是 v1.1 啟動的 ground-truth proof,Key Decisions 將會 cite)。

**Carrying forward(前期已鎖定,本階段不重複決定):**

- **AGPL seam** — `import fitz` 嚴格限制在 `app/services/pdf_engine.py`(Phase 1–4 AST-level guard test 持續綠燈)。Phase 6 所有 fitz 操作都在 `tests/conftest.py`(既有「test harness 可直接用 fitz BUILD fixtures」例外)+ 新 `scripts/sanitize_fixture.py`(scripts/ 不在 guard scope 內)+ 新 attack regression test(test 檔內 import fitz 已是既有 pattern)。**production code 完全不動。**
- **5330290 教訓** — minimum-change + sufficient-testing。Phase 6 不夾帶 polish / nice-to-have 改動(任何超出本 phase boundary 的優化推到 maintenance sprint)。
- **conftest.py 既有 in-memory fixture 哲學** — `_build_pdf` / `_build_png` / `_build_*_pdf` builders 全部保留;`tests/fixtures/cad-glyph/` 是 **唯一的 committed-binary 例外**,於 `tests/fixtures/cad-glyph/README.md` 文件化此例外的理由。
- **既有測試基線** — 301 passed + 3 skipped(v1.0 close + hotfix 06+07)。Phase 6 新增的 xfail 測試**不計入 passed**(它們是 expected-failures),故 baseline 保持 301 + 3 skipped + N xfailed。Phase 7 落地後 N xfailed → N passed(strict=True 強制這個轉換)。
- **commit/push 節奏(memory feedback_commit_push_cadence)** — UAT 期間 commit local but never push,hotfix inline;final code-review/fix pass 後才 push。Phase 6 雖然不是 hotfix 而是 hardening,但沿用同節奏 — push 動作留到 Phase 8 LIVE-UAT 通過時統一處理。
- **繁中文案** — 任何使用者面 / docstring 面文字保持繁體中文(N/A 給 Phase 6 — 純測試 + STRIDE 文件,無 user-facing message;但 SECURITY.md 內文 + xfail reason 字串建議仍繁中)。

**Phase 6 不含(歸 Phase 7/8 或 out-of-scope):**

- Option B 實作本身(Phase 7 SEC-01/02/03 + TEST-03 單元測試)
- `app/services/pdf_engine.py::replace_region_with_white_raster` docstring、`app/services/redact.py::TRUE_REMOVAL_LIMITATION` 模組層 + dispatcher inline comment 三處 LIMITATION 同步(Phase 8 THREAT-02 + DOC-01)
- `HANDOFF.md` 6.5 小節新增、`PROJECT.md` Key Decisions v1.1 落地列(Phase 8 DOC-01 + DOC-02)
- LIVE 部署 + LIVE-UAT(Phase 8 DEPLOY-01)
- 對 form XObject 內 zero-area fills 做遞迴 surgery(out-of-scope,延到實際樣本出現)
- 對 zero-area `type='s'`(stroke)做 surgery(out-of-scope,無威脅證據)

</domain>

<decisions>
## Implementation Decisions

### Fixture 來源與 sanitization(用戶討論決定)

- **D-A1:** **Fixture 來源 = 工程師手中既有真實 supplier CAD PDF**(STATE.md blocker 中提到的「工程師需提供 ≥3 個出問題的 supplier CAD-glyph PDF」)。一週內可交出 ≥2 個另外的 supplier CAD PDF;repo root 既有的 `3013A-13A-C6-XX-3D02-A01-00040.pdf`(2026-05-28 attack reproduction file)為第 1 個。**不採合成 PDF 作 primary source** — Phase 6 的價值是「STRIDE 加 Illustrator attacker 在真實樣本上驗證」,真實供應商 PDF 帶的 corner cases(例如 Illustrator 出口 PDF 特有的 q...Q wrap 慣例、XObject 命名習慣、content stream 多 stream 分割)是合成 PDF 漏掉的。
- **D-A2:** **Sanitization = 脫敏後 commit 進 public repo(`tests/fixtures/cad-glyph/`)**。重要 trade-off:repo 是 public(AGPL §13 memory project_deployment_licensing 鎖定),不能放真實供應商商標。脫敏動作 4 件:
  1. **Metadata 清空** — `doc.set_metadata({})` 移除 Author/Producer/CreationDate/ModDate/Title/Keywords/Subject(注意 PyMuPDF 1.27 用 `doc.set_metadata(metadata=None)` 或傳空 dict;**researcher / planner 需驗證準確 API 簽名**)。
  2. **Content stream 供應商公司名 → `TESTCO`** — find-replace 在 content stream 與 `/Title` 等 PDF 物件層;若供應商名稱以 ToUnicode + 自訂 font 編碼,需特別處理(可能要 decode CMap),researcher 驗證可行性。
  3. **Brand glyph 替換** — 既有 supplier brand 的 zero-area `type='f'` glyph **整塊以新建的 `TESTCO` wordmark zero-area glyph 取代**(D-A3 詳述)。保留同型 attack 面,但 visual signature 不可識別。
  4. **Bbox / fingerprint cleanup** — 若 PDF 內有 hyperlink、comment annotation、digital signature、accessibility tags 帶供應商識別資訊,一併移除。
- **D-A3:** **Brand glyph 複寫策略:** 原 supplier brand glyph(N 個 zero-area `m/l/f/B` 算子序列)在 content stream 中 **整段刪除**,以 `TESTCO` wordmark 為材料、用 fitz 建構等效的 zero-area `type='f'` 路徑序列(各字元外框以 `moveto/lineto/fill` 拼接,且全部 width=0 或 height=0 確保 area==0)塞回原位置 + 同 ctm。保留同型 attack 面(`count_zero_area_fills_fully_inside` 在框選區內 ≥N)。
  - **驗證:** sanitization script 結尾 assert
    - `len(doc.get_metadata()) == 0` 或所有欄位空
    - 原供應商名(由人提供;script 接受 `--supplier-name "XXX"` arg)不出現在 `page.get_text()` 任何 page
    - `count_zero_area_fills_fully_inside(page, REGION)` 在 sanitized 後 ≥ 原 count 的 90%(允許 finely diff 但保留同密度級別)
- **D-A4:** **`scripts/sanitize_fixture.py` 一次性工具** — `python scripts/sanitize_fixture.py --in raw.pdf --out tests/fixtures/cad-glyph/text-glyph-01.pdf --supplier-name "...實際供應商名..." --region-rect "x0,y0,x1,y1"` — input raw、output sanitized + 自查 assert。script commit 進 repo(`scripts/` 不在 fitz AGPL guard scope);raw PDF **不進 git**,留在工程師本機或 chmod 受控的 internal share。
- **D-A5:** **Coverage 分布 ≥3 個 fixture:**
  - `tests/fixtures/cad-glyph/text-glyph-01.pdf` — 文字 glyph 主體(供應商商標是文字 wordmark,如「TESTCO Engineering Ltd」)
  - `tests/fixtures/cad-glyph/figure-glyph-01.pdf` — 圖形 glyph 主體(供應商商標是 icon / monogram,純向量幾何形狀)
  - `tests/fixtures/cad-glyph/mixed-glyph-01.pdf` — 文字 + 圖形混合(typical CAD title block)
  - 可選 `…-02.pdf` 第四個若工程師交付能補上 corner case
- **D-A6:** **`tests/fixtures/cad-glyph/README.md` 必須寫入:** (a) 為什麼是 conftest「no committed binary」convention 的唯一例外、(b) 每個 fixture 對應的原供應商 + sanitization 日期 + 用 `scripts/sanitize_fixture.py` 哪個 commit 跑、(c) 任何 fixture 變更必須走 sanitization script 不可手動編輯。

### Attack-simulation pytest 設計

- **D-B1:** **新 test 檔位置 = `tests/test_illustrator_attack_regression.py`** — 不放在 `tests/test_redact.py` 因為它是 cross-module(走 ingest → pipeline → 攻擊腳本 → assert),獨立檔比較好定位 + Phase 7 binary search 時容易找。
- **D-B2:** **Attack helper 函式拆出共用模組 `tests/_illustrator_attack.py`** — 既有 scratch script 的 `_attack_delete_image_xobject.py` 核心邏輯(找 image xrefs、解析 Resources/XObject 命名、regex 重寫 content stream 拔 `q ... /<Name> Do ... Q` block)變成可重用 helper:
  - `delete_image_xobjects_intersecting(doc, page_index, rect) -> int` 回傳被刪 xref 數
  - `render_region_white_pct(pdf_path, page_index, rect) -> float` 回傳白佔比
  - `count_zero_area_fills_in_region(pdf_path, page_index, rect) -> int` 回傳 zero-area type='f' count(包 `app.services.pdf_engine.count_zero_area_fills_fully_inside` — 注意這是 production module,test helper 可正常 import)
  - **此檔 import fitz** — `tests/_illustrator_attack.py` 是 test code,fitz AGPL guard test 只掃 `app/**/*.py`,不影響 seam。
- **D-B3:** **pytest 參數化** — `@pytest.mark.parametrize("fixture_path", [text-glyph-01, figure-glyph-01, mixed-glyph-01])` 對每個 fixture 跑 4-step regression:
  ```python
  @pytest.mark.xfail(strict=True, reason="Option B pending in Phase 7 — zero-area type='f' fills 未從 content stream 真正刪除,Illustrator-class editor 拔 image XObject 後可重現供應商商標")
  @pytest.mark.parametrize("fixture_path,region_rect", [...])
  def test_illustrator_attack_residual_supplier_revealed(fixture_path, region_rect, ...):
      # 1. ingest fixture → session
      # 2. process(LogoSwap 移除 + Option A overlay)
      # 3. delete_image_xobjects_intersecting(output, region_rect)
      # 4. assert render_region_white_pct(output, region_rect) >= 98.0
      # 5. assert count_zero_area_fills_in_region(output, region_rect) == 0
  ```
- **D-B4:** **Region rect 來源 = 每個 fixture 的 sidecar JSON manifest** — `tests/fixtures/cad-glyph/text-glyph-01.json` 含 `{"region_rect": [x0, y0, x1, y1], "page_index": 0, "expected_zero_area_count_pre_process": N}` 三欄。pytest 跑時讀 manifest;sanitization script 也順手寫一份(--region-rect arg 同步寫進 manifest)。避免 region rect 硬編碼到 test 內(若 fixture 因 sanitization 微調 region 不一致)。
- **D-B5:** **Assertion 雙閘:** (a) `render_region_white_pct >= 98.0`(視覺乾淨 — ROADMAP success criteria #2 原文)+ (b) `count_zero_area_fills_in_region == 0`(content stream 真的被刪 — 多一層斷言能在「視覺看起來白但 content 還在」這種 Phase 7 incorrect implementation 上抓到)。雙閘 redundant by design — Phase 7 implementation 要兩個都過才算 Option B 落地。
- **D-B6:** **Test count 影響:** 新增 3 個 xfail tests(對應 3 fixtures)。pytest 顯示「301 passed, 3 skipped, 3 xfailed」是 Phase 6 close 的測試 baseline;Phase 7 落地後預期變成「304 passed, 3 skipped」(xfail → passed,strict=True 把「unexpected pass」變成失敗,於是 implementer 必須拔掉 xfail decorator 並 promote 為 passed)。

### Scratch retirement

- **D-C1:** **保留 forensic 證據,退役 .py 腳本** — `.planning/debug/scratch/illustrator-attack-2026-05-28/` 改名為 `…-archived/`,內部:
  - **保留:** `_attack_proof_supplier_revealed.png`, `_attack_target_pre.png`, `_attack_orig_for_comparison.png`, `_attack_image_xobject_deleted.pdf`(這四個是 v1.1 啟動的 ground-truth 證據,將被 PROJECT.md Phase 8 Key Decisions 與 STATE.md milestone 啟動歷史 cite)。
  - **退役 / 刪除:** `_attack_delete_image_xobject.py`, `_check_supplier_removal.py`(邏輯已搬入 `tests/_illustrator_attack.py`,git history 仍可查)。
  - **新增** `…-archived/README.md` 一段繁中 note 指向新 pytest:「攻擊腳本邏輯已搬入 `tests/_illustrator_attack.py` + `tests/test_illustrator_attack_regression.py`;此目錄保留 PNG/PDF 證據以利後續審計 cite。」

### Threat model re-evaluation(THREAT-01 文件落點)

- **D-D1:** **新建 `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`** — 沿用 v1.0 per-phase SECURITY.md pattern,不另建 top-level `.planning/SECURITY.md`(per-milestone 累積已足,project-level 主檔可在 v1.2 / future 規模成長時再合併)。
- **D-D2:** **STRIDE 表新增:**
  - **Actor:** `Illustrator-class editor attacker` — 假設攻擊者擁有 Adobe Illustrator / Acrobat Pro / 等同 PDF editor 工具,能讀寫 PDF object stream / content stream,可:
    - 識別並刪除 page-level image XObjects(LogoSwap Hotfix-06 Option A 的 raster overlay)
    - 不需修改其他 content,單純拔 overlay 即觸發 zero-area `type='f'` source path 在 Acrobat / Illustrator render 出供應商商標
  - **Threat T-06-01:** `Illustrator pulls image XObject overlay → supplier brand re-rendered from zero-area type='f' source`,Spoofing/Information-disclosure 雙重類別。
  - **Disposition:** `OPEN — pending Option B (Phase 7)`,evidence cite `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png` + 新 `tests/test_illustrator_attack_regression.py`(xfail 紅燈本身就是威脅證據)。
- **D-D3:** **T-02-07 重新打開:**
  - 原狀態(archived `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md`):`CLOSED with documented residual`
  - 新狀態(在 06-SECURITY.md 中 cross-reference 並 supersede):`RE-OPENED 2026-05-28 (v1.1 Phase 6) — pending Option B`
  - 06-SECURITY.md 明文寫:`此 RE-OPENED 不撤銷 v1.0 LIVE 的 mitigation 仍有效(對僅有 CLI 攻擊者 / 內網一般使用者威脅模型),但對 v1.1 升級後的 Illustrator-class editor 威脅模型不足。Phase 7 Option B 落地後在 07-SECURITY.md 重新 CLOSED via Option B。`
- **D-D4:** **06-SECURITY.md format = `gsd-secure-phase` 既有 frontmatter + STRIDE 表 + Threat Verification table 風格**(對齊 `06-HOTFIX-SECURITY.md` 既有格式,downstream `gsd-secure-phase` agent 在 Phase 7 close 時可平順接手 cross-reference)。Phase 6 SECURITY.md 是「pre-mortem 風格」(STRIDE actor + threats OPEN 列表 + 預期 Phase 7 close 條件),不是 audit report(因為沒有 production code 變更可審)。

### Claude's Discretion

- **`scripts/sanitize_fixture.py` 內部實作細節** — 完整 CLI args 設計、CMap decoding 邊界、PDF object stream 編輯實作走 fitz API 哪個 method(`doc.update_stream` vs `doc.xref_set_stream` 等),researcher 在 RESEARCH.md 階段驗證後 planner 細調。Phase 6 plan 預期切 plan 06-01(sanitization script + 3 fixtures)+ plan 06-02(attack regression test + 06-SECURITY.md);planner 可微調。
- **xfail reason 字串文案** — 繁中 + 含 cross-reference 路徑(`Option B pending in Phase 7 — 參 .planning/REQUIREMENTS.md SEC-01`)讓 Phase 7 implementer grep `xfail.*Option B` 就能找到要拔的 marker。
- **TESTCO wordmark 字型 / 設計選擇** — sanitization script 可硬編幾組通用幾何路徑(每字元 ~10 個 zero-area `m/l/f/B` 算子),不需追求美觀 — 純為 attack-面積 proxy。
- **Sidecar JSON manifest schema** — Q4 D-B4 列了核心 3 欄,可加 `original_supplier_name_hash`(SHA-256,僅作 audit log)、`sanitization_script_commit_sha`、`created_at_iso` 等元資料。
- **新測試是否需要 isolated `tmp_path`** — 沿用 conftest 既有 `isolated_data_dir` autouse fixture(`DATA_DIR` 自動指向 tmp_path),無需特別處理。
- **既有 attack 腳本中的 `samples/3013A-...pdf` 路徑** — 既有 `samples/` 目錄與 repo root 各有一份;Phase 6 後此檔案的 fixture 角色由 `tests/fixtures/cad-glyph/{text|figure|mixed}-glyph-01.pdf` 之一接手(sanitized 版),原 `samples/` 與 root 副本是否留在 repo 由 planner 評估(scan attack 證據需要、但檔案內含原供應商名 — 不安全留 public repo;建議移到 `.planning/debug/scratch/.../-archived/` 同層,或加 .gitignore;**最終由 planner 決議與 repo state 對齊**)。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level lockfiles
- `.planning/PROJECT.md` — milestone v1.1 Active section + Key Decisions 表(AGPL seam、PyMuPDF 核心、5330290 minimum-change 教訓、Hotfix 06 Option A 既有架構)
- `.planning/REQUIREMENTS.md` — Phase 6 對應 TEST-01 / TEST-02 / THREAT-01(11 reqs 的 traceability 表已填 100%)
- `.planning/ROADMAP.md` § "Phase 6: Regression Foundation + Threat Model Re-evaluation"(goal、4 條 success criteria、depends-on Phase 5)
- `.planning/STATE.md` — milestone v1.1 啟動狀態 + blocker「TEST-01 需要實際樣本」(本 CONTEXT D-A1 已 unblock — 一週內 ≥2 個 supplier PDF 到手)

### v1.0 archived artefacts(supersede 對象)
- `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md` — T-02-07 原 `CLOSED with documented residual` 狀態、Option A raster overlay 設計、3 處 LIMITATION docstring 位置(`pdf_engine.py::replace_region_with_white_raster`、`redact.py::TRUE_REMOVAL_LIMITATION`、`redact.py` dispatcher inline)。**Phase 6 新 06-SECURITY.md 必須 cross-reference 並標 supersede。**
- `.planning/milestones/v1.0-phases/05-ubuntu/05-SECURITY.md` — Phase 5 STRIDE actor 清單原始版本(`Illustrator-class editor attacker` 即將以 D-D2 新增)
- `.planning/milestones/v1.0-phases/05-ubuntu/05-CONTEXT.md` — v1.0 close 時的 AGPL seam / 三目錄 / SHA-256 D-05 整合上下文

### Forensic 證據(v1.1 啟動 ground-truth)
- `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py` — 將搬入 `tests/_illustrator_attack.py` 的 attack 邏輯(regex content-stream rewrite、image xref 定位、Resources/XObject 命名解析)。**Phase 6 退役 = 改名為 `…-archived/` + .py 刪除 + 邏輯遷移到 tests/。**
- `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_proof_supplier_revealed.png` — Illustrator 拔 image XObject 後供應商商標重現的視覺證據(將被 06-SECURITY.md cite 作 T-06-01 threat evidence)
- `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_target_pre.png` / `_attack_orig_for_comparison.png` — 攻擊前 / 原始供應商 PDF render 對照
- `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_image_xobject_deleted.pdf` — 攻擊輸出的攻擊後 PDF(可作為 cross-verify Phase 6 regression test 行為的 reference)
- `.planning/debug/scratch/illustrator-attack-2026-05-28/_check_supplier_removal.py` — 補強檢查腳本(配合 _attack_*.py;同樣搬入 tests 後退役)

### Production code(本 phase **不改動**,但 attack regression test 需 import / 對接)
- `app/services/pdf_engine.py` — `count_zero_area_fills_fully_inside(page, rect, tolerance)` getter(line 699),`ZERO_AREA_RASTER_THRESHOLD=100` 常數(line 294),`replace_region_with_white_raster` Option A 主函式(line 746)— **attack regression test assertion 會 import `count_zero_area_fills_fully_inside`**
- `app/services/redact.py` § dispatcher(line 232-256)— Option A raster overlay 觸發條件;`TRUE_REMOVAL_LIMITATION` 模組層 docstring(line 6-36)+ inline LIMITATION comment(line 220-227)— Phase 6 不改,但 06-SECURITY.md 內文需 cross-reference
- `app/services/pipeline.py` § `process_job`(line 107-150)— Phase 6 regression test 跑 ingest → process pipeline 的標準入口

### Test infrastructure(沿用 / 擴充)
- `tests/conftest.py` — `_build_pdf` / `_build_*_pdf` in-memory builders 哲學(line 12 註解「only the test harness may use fitz directly to BUILD fixtures」即此 phase 的 license);`isolated_data_dir` autouse fixture;`ingested_session` fixture(可重用)
- `tests/test_redact.py` § `test_remove_region_vector_dense_real_zero_area_paths_end_to_end`(line 691-794)— 既有 Option A dense-branch end-to-end test pattern,Phase 6 新 test 可借鏡其「合成 PDF + 跑 pipeline + assert」結構
- `tests/test_redact.py` § `test_fitz_import_confined_to_engine_seam`(line 1190-1207)— AGPL seam AST guard,**Phase 6 不能破壞此 test**(`scripts/sanitize_fixture.py` 與 `tests/_illustrator_attack.py` 因不在 `app/**/*.py` scope 內,不會被 guard 抓)
- `tests/test_process_api.py` § `test_process_without_logo_is_pure_removal`(line 270-316)— D-01 contract revision docstring,Phase 6 regression test 走 `logo_id=None` path 時需確認此 contract 不被破壞

### Research(若 Phase 6 需要 deep-dive PDF object/stream API)
- `.planning/research/STACK.md` — PyMuPDF 1.27.x、fitz `apply_redactions` / `update_stream` / content stream API 範圍
- `.planning/research/PITFALLS.md` — Pitfall 8(大型 / 旋轉 / OCG)、Pitfall 11(parser isolation / tempfile lifecycle)— 對 sanitization script 處理 CMap / 編碼可能相關

### Reference docs / patterns to align with
- `CLAUDE.md` § "GSD Workflow Enforcement"(commit 經 GSD workflow)+ § "Conventions"(本 phase 不破壞既有 convention,新 fixtures dir 例外文件化)
- `HANDOFF.md`(本階段不更新 — DOC-01 Phase 8 才動;但 Phase 6 plan 時可讀 §6 既有「核心領域知識備忘」確認 Option A 描述與本階段 SECURITY.md cross-reference 一致)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `app/services/pdf_engine.py::count_zero_area_fills_fully_inside(page, rect, tolerance=_DEGENERATE_BBOX_EPS) -> int`(line 699)— attack regression test assertion #2「`count_zero_area_fills_in_region == 0`」直接呼叫此 production helper;`tests/_illustrator_attack.py` 的 `count_zero_area_fills_in_region(pdf_path, page_index, rect)` 在內部 open doc 後 delegate 到此函式。
- `app/services/pipeline.py::process_job(session_id, regions, logo_id=None)` — attack regression test step 2「LogoSwap process」直接呼叫;沿用 conftest `ingested_session` fixture 取得 session_id。
- `tests/conftest.py::ingested_session` fixture — 對 `valid_pdf_bytes` 做 ingest 後回傳 SessionInfo;**Phase 6 需新增 `cad_glyph_session(fixture_id)` parametrized fixture**,改讀 `tests/fixtures/cad-glyph/{fixture_id}.pdf` 而非合成 bytes。
- `tests/conftest.py::isolated_data_dir` autouse fixture(line 298-307)— `DATA_DIR` 自動 monkey-patch 到 tmp_path,attack regression test 沿用,不需特別處理。
- `tests/conftest.py::_build_pdf` 內部 `fitz.open()` + `new_page` + `insert_text` + `draw_line` pattern(line 18-32)— `scripts/sanitize_fixture.py` 用同一 fitz API 但反向操作(編輯既有 doc 而非從零 build)。
- 既有 attack script regex `r"q\b[^Q]*?/" + re.escape(name.lstrip("/")) + r"\s+Do\b[^Q]*?Q\b"`(`_attack_delete_image_xobject.py` line 88-92)— Phase 6 搬入 `tests/_illustrator_attack.py` 時保留此 regex,確保 attack 機制與 2026-05-28 證據對齊。
- `samples/3013A-13A-C6-XX-3D02-A01-00040.pdf` / repo root 同檔 — Phase 6 sanitization script 的 raw input 之一(轉為 `tests/fixtures/cad-glyph/mixed-glyph-01.pdf` 或 `text-glyph-01.pdf`,planner 決定對應到哪個 coverage slot)。

### Established Patterns

- **Test 檔命名:** `tests/test_<feature>.py` — Phase 6 新檔 `tests/test_illustrator_attack_regression.py` 沿用。Cross-cutting helper module 以底線開頭:`tests/_illustrator_attack.py`(對齊 v1.0 既有 helper 命名習慣若有)。
- **Fixture parametrize via `@pytest.mark.parametrize`** — 對應 D-B3,沿用 pytest 標準。
- **In-memory fixture bytes return + ingest fixture chain** — Phase 1–4 既有;Phase 6 第一個 committed-binary 例外打破此 pattern,但 scope 嚴格限制在 `tests/fixtures/cad-glyph/`(README.md 文件化)。
- **fitz AGPL seam:** `import fitz` 嚴格限制 `app/services/pdf_engine.py`(AST-level guard test enforces)— Phase 6 所有新 fitz 操作都在 test code(`tests/_illustrator_attack.py`、`scripts/sanitize_fixture.py`)+ `tests/conftest.py` 既有例外,**seam 完全不破壞**。
- **STRIDE table format:** archived `06-HOTFIX-SECURITY.md` § "Threat Verification" 表頭 `| Threat ID | Category | Disposition | Status | Evidence (file:line) |` — 06-SECURITY.md 沿用同欄位 + 同 frontmatter schema(`gsd-secure-phase` 期望)。
- **xfail strict pattern:** v1.0 沒有既有 xfail 使用,Phase 6 是首例;reason 字串 + cross-reference 路徑為 Phase 7 implementer 的入口(grep-friendly)。

### Integration Points

- **新增 `scripts/sanitize_fixture.py`** — repo root `scripts/` 目錄;若 `scripts/` 不存在,planner 建立。fitz import 不破 AGPL seam。
- **新增 `tests/_illustrator_attack.py`** — test helper module;regex content-stream rewrite 邏輯。
- **新增 `tests/test_illustrator_attack_regression.py`** — 主測試檔,parametrized over 3 fixtures。
- **新增 `tests/fixtures/cad-glyph/`** 目錄 + `README.md` + 3 個 sanitized PDF + 3 個 sidecar JSON manifest。
- **新增 `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`**。
- **改動 `.planning/debug/scratch/illustrator-attack-2026-05-28/`** → `…-archived/` 重命名 + .py 刪除 + 新 README.md。
- **保持不變:** `app/**/*.py` 任何檔案(production code 0 改動是 Phase 6 設計目的);`tests/conftest.py`(僅 **可選** 加 `cad_glyph_session` parametrized fixture,planner 決定要不要單獨檔放新 conftest 或寫在主 conftest)。

### What Phase 6 does NOT touch

- `app/services/pdf_engine.py` / `redact.py` / `pipeline.py` / 其他 `app/**/*.py` — production code 0 改動,5330290 minimum-change 教訓嚴守
- `web/**` 前端 — 無 UX 變更
- `app/config.py` — 無新常數
- `Dockerfile` / `LICENSE` / AGPL 三件套 — DEPLOY-01 是 Phase 8;Phase 6 完全不沾部署
- `HANDOFF.md` § 6 — DOC-01 是 Phase 8
- `PROJECT.md` Key Decisions 表 — DOC-02 是 Phase 8
- v1.0 既有 SECURITY.md 檔案(archived)— Phase 6 新建獨立 06-SECURITY.md,不編輯既有 archived 檔

</code_context>

<specifics>
## Specific Ideas

- **核心場景:** Phase 7 implementer 對著 `tests/test_illustrator_attack_regression.py` 跑 `pytest -k illustrator_attack -v` 應看到 3 個 `XFAIL`(預期紅燈),寫完 Option B 後同指令應看到「`XPASS` (strict)」失敗 → 拔掉 `@pytest.mark.xfail` decorator → 3 個 `PASSED`。這就是 Phase 6 → Phase 7 handoff signal,xfail strict 是核心機制。
- **核心場景:** Phase 6 close 後 STATE.md blocker「TEST-01 需要實際樣本」由 D-A1 解除(一週內工程師交付 ≥2 個 supplier PDF),但需追蹤實際交付時間 — 若 plan 走完工程師仍未交付,以「先用 1 個真實 + 2 個 placeholder synthetic CAD-glyph(D-A1 不採但 fallback)」交付,並把這個延遲記入 STATE.md。**這個 fallback 在 Phase 6 plan 階段 planner 需明文寫進 PLAN.md tasks 的 contingency。**
- **使用者體驗(N/A 給 Phase 6):** 純測試 + 文件層交付,無 user-facing 變更。
- **AGPL §13 合規:** Phase 6 不改部署、不改三件套(public GitHub + LICENSE + UI source link 既有就位);新增的 fixtures 即使 commit 進 public repo 也不涉及 AGPL §13(不是 source code,是 test data)。但仍需確認 `tests/fixtures/cad-glyph/README.md` 明說「all fixtures sanitized via scripts/sanitize_fixture.py,no original supplier IP」以利公開 review。
- **追溯路徑:** 06-SECURITY.md 的 T-02-07 RE-OPENED 與 T-06-01 OPEN 兩條 threat,Phase 7 落地後在 `.planning/phases/07-.../07-SECURITY.md` 應同時 CLOSED;Phase 8 LIVE-UAT 通過後在 `08-SECURITY.md` 應有 verifying note。**這個三 phase chain 是 v1.1 milestone 的安全敘事,downstream agents 必須串對。**

</specifics>

<deferred>
## Deferred Ideas

- **對 form XObject 內 zero-area fills 做遞迴 surgery** — v1.1 SEC-03 採 page-level only + log 策略;Phase 6 attack regression test **不涵蓋 form XObject 內巢狀 zero-area fills**(若工程師交付的 supplier PDF 內含此情境,sanitization script 需 log 警示但 fixture 不必特別處理 — Phase 7 SEC-03 已說明 page-level only,Phase 6 攻擊面只測 page-level)。實際樣本出現再評估遞迴方案。(已記 .planning/STATE.md Deferred 表)
- **對 zero-area `type='s'`(stroke)做 surgery** — 目前威脅證據都是 type='f';stroke 在 dCt-residue investigation 中未出現殘留問題。Phase 6 attack regression test 不測 stroke。(已記 STATE.md Deferred 表)
- **新增 `is_raster_fallback_image(page, xref)` getter** — colleague-system integration 需要區分 fallback overlay 與真 logo image 時才加;Phase 6 attack regression test 不依賴此 getter(直接從 `page.get_images()` 拔所有 image XObjects)。(已記 STATE.md Deferred 表)
- **Auto-detect supplier-source heuristic dispatcher** — REQUIREMENTS.md Out of Scope 明列「不偵測 PDF 來源是不是 CAD 做 dispatcher」— Option B 在 SEC-02 為 no-op-safe,加 detection 是過度設計。Phase 6 attack regression test 同此原則:不偵測,直接對 fixture 跑 attack。
- **CMap decoding helper 通用化** — 若 sanitization script 處理供應商名稱時遇到自訂 font + CMap 編碼是 corner case,可能寫一個 `scripts/_pdf_text_decode.py` helper;不通用化、不放 `app/`(避免 fitz AGPL seam 風險)。若三個 fixture 都不需要 CMap decode,則不寫此 helper。
- **xfail → skip 自動切換機制** — 若 Phase 6 close 後 Phase 7 implementer 不能很快接手(milestone 期間延宕),不需要切到 skip;xfail 本身就是 safe baseline(CI 不爆、測試會跑、有可追溯紀錄)。
- **Sanitization script 的 watermark / fingerprint cleanup** — 若 PDF 內含 OCG layer / watermark 帶供應商識別,Phase 6 sanitization script 必要時擴充。**初始 plan 不涵蓋,實際樣本到手再決定是否補強**(可能由 planner 在 06-PLAN.md 內列為 contingency)。
- **commit raw supplier PDF 進 internal git** — 用戶 Q2 否決 (c) 內部 git infra 方案;若 future milestone 需要 raw fixture 共享(例如 cross-team CI integration),再評估自架 GitLab/Gitea。
- **fitz 在 scripts/sanitize_fixture.py 內的長期治理** — 目前 `scripts/` 不在 AGPL guard test scope。若 future repo 規模增長 scripts/ 內容變多,可能需把 AGPL guard 從 `app/**/*.py` 擴大到 `app/**/*.py + scripts/!sanitize_fixture.py` 等更精細的 allowlist;v1.1 不擴。

</deferred>

---

*Phase: 6-regression-foundation-threat-model-re-evaluation*
*Context gathered: 2026-05-28*
