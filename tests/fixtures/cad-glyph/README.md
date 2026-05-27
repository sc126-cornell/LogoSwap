# `tests/fixtures/cad-glyph/` — Committed-binary fixture 例外

**最後更新:** 2026-05-28(milestone v1.1 Phase 6 / Plan 06-01)
**狀態:** ⚠ **PROVISIONAL** — 3 個 fixture 中有 2 個是 synthetic(工程師延遲交付 contingency)。

---

## 1. 為什麼這是 `tests/` 唯一 committed-binary 例外

本專案的 test infrastructure 在 v1.0 起就採「never commit binary fixtures」哲學
(參 `tests/conftest.py:1-6` 模組 docstring 與 `_build_pdf` / `_build_png` /
`_build_*_pdf` builders)。所有測試用 PDF / PNG / TIFF 都在 fixture 階段於記憶體
建構,確保 repo 永遠 binary-free + 跨機 deterministic。

本目錄是**唯一的例外**,scope 嚴格限制在 `tests/fixtures/cad-glyph/`。

**為何需要例外:**
v1.1 Phase 6 引入 Illustrator-class attacker threat model(`T-06-01`)。對應的紅燈
regression test(Plan 06-02 將建)需要對「真實 supplier CAD-glyph PDF」跑攻擊腳本,
驗證 Illustrator 拔 image XObject overlay 後零面積 `type='f'` source 路徑是否
re-render 出供應商商標。**真實 supplier CAD-glyph PDF 帶的 corner cases** —
Illustrator / AutoCAD 出口 PDF 特有的 q…Q wrap 慣例、XObject 命名習慣、content
stream 多 stream 分割 — 是合成 `_build_pdf` 漏掉的(per CONTEXT D-A1)。

因此 Phase 6 設一個受控的例外:**3 個 sanitized supplier PDF fixture** + sidecar
JSON manifest,所有 binary 都先經過 `scripts/sanitize_fixture.py` 洗去原供應商 IP
(metadata 清空、brand glyph 整塊 strip、TESTCO 零面積 wordmark 注入)才 commit。

---

## 2. 每個 fixture 的脫敏記錄

| fixture | original supplier (initial only) | sanitization date (UTC ISO) | script commit sha | coverage slot |
|---|---|---|---|---|
| `text-glyph-01.pdf` | —(synthetic — 工程師延遲交付 contingency;Phase 6 close 為 PROVISIONAL) | 2026-05-28T... | `d671548`(本 plan Task 1 commit;前一個 commit 為 sanitize script 加入) | 文字 glyph 主體 wordmark |
| `figure-glyph-01.pdf` | —(synthetic — 工程師延遲交付 contingency;Phase 6 close 為 PROVISIONAL) | 2026-05-28T... | `d671548` | 圖形 glyph 主體(icon / monogram) |
| `mixed-glyph-01.pdf` | 真實 supplier(初代 = `3013A-13A-C6-XX-3D02-A01-00040.pdf`;Acrobat Distiller / PScript5 出口);author 已洗(原 `RD07`) | 2026-05-28T... | `d671548` | 文字 + 圖形 mixed CAD title block(2026-05-28 attack reproduction file) |

詳細的元資料(`region_rect_pdf_points`、`region_rect_px`、`dpi`、`page_index`、
`expected_zero_area_count_pre_process`、`original_supplier_name_sha256`、
`sanitization_script_commit_sha`、`created_at_iso`、`synthetic` flag)寫入對應的
sidecar `<slot>.json`。pytest 在 collection 時讀 manifest(Plan 06-02 規格 D-B4 +
本 plan canonical split-coordinate schema per Warning #8)。

**PROVISIONAL banner:** 2 / 3 fixture 為 synthetic;Phase 6 close 條件 **PROVISIONAL**
until 工程師交付剩餘 supplier PDF + 重跑 `scripts/sanitize_fixture.py` 替換 synthetic
版本。Tracking blocker:`.planning/STATE.md` 的「Phase 6 fixture replenishment」項。

---

## 3. Immutability rule(D-A6 c)

**任何 fixture 變更必須走 `scripts/sanitize_fixture.py` 重跑。禁止:**

- 手動 hex-edit / vim / Notepad++ 等開檔改 bytes
- `git rebase` 改 fixture commit 內容
- 用 Acrobat / Illustrator / 其他 PDF editor 「微調」 sanitized PDF
- 直接編輯 sidecar `.json` manifest 的 `region_rect_*` / `expected_zero_area_count_pre_process` 欄位

**理由:** sanitize script 結尾跑 4 條 self-assert(metadata 全空 / supplier name 不在
`get_text()` / zero-area count ≥ 0.9 × 原 count / out path 必在
`tests/fixtures/cad-glyph/`),手動編輯會繞過這些保證,且若 PDF 物件 xref table 不一致
會破壞 fixture 結構。

參 `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-RESEARCH.md`
§ Anti-Patterns「手動編輯 sanitized fixture PDF」。

---

## 4. AGPL §13 statement

All fixtures in this directory were sanitized via `scripts/sanitize_fixture.py`
(commit `d671548`+)。**No original supplier IP retained:** the script self-asserts
that (1) all user-supplied metadata fields (author / producer / title / keywords /
subject / creator / creationDate / modDate / trapped) are empty, and (2) the original
supplier name does NOT appear in `page.get_text()` of any sanitized PDF, before
writing the output file (在 doc.save 之前 self-assert,任一失敗 → exit 1 + 不寫
output)。

Synthetic fixtures(2 of 3 in current state)從零建構,本就不含任何 supplier IP。

Public repo(AGPL §13 lockfile per memory `project_deployment_licensing`)receives
only sanitized output — raw supplier PDFs are **never** committed(`.gitignore`
root-anchored + samples-anchored + archived-anchored guards 多重防護)。

---

## 5. Cross-references

- **Sanitization tool:** `scripts/sanitize_fixture.py`(Plan 06-01 Task 1)
- **Attack regression test:** `tests/test_illustrator_attack_regression.py`(Plan 06-02 將建)
- **Production helper invoked by sanitize self-assert:** `app.services.pdf_engine.count_zero_area_fills_fully_inside`(line 699)
- **Threat model:**
  - `.planning/REQUIREMENTS.md` TEST-01(本 fixture 對應的 requirement)
  - `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`(Plan 06-02 將建,STRIDE pre-mortem 含 T-06-01 + T-02-07 RE-OPENED)
  - `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-CONTEXT.md` D-A1..D-A6(fixture 來源、sanitization 策略、coverage 分布、README 5 項必要內容)
- **Raw supplier PDF 處置:**
  - `3013A-13A-C6-XX-3D02-A01-00040.pdf`(repo root,**untracked**)— `mixed-glyph-01.pdf` 的 raw source。已被 `.gitignore` root-anchored pattern `/3013A-13A-C6-XX-*.pdf` 屏蔽。
  - `samples/3013A-13A-C6-XX-3D02-A01-00040.pdf` — **tracked** 副本。**Plan 06-02 Task 4 將用 `git rm` 從 git index 移除 `samples/` 版本**;同時將 root 副本物理移動到 `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/`(`.gitignore` 已 archived-anchored 屏蔽,移入後不被 track)。本 plan 06-01 只負責加 `.gitignore` 防護,實際 `git rm` + 物理移動由 Plan 06-02 處理。
- **Forensic 證據(v1.1 啟動 ground-truth):** `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_proof_supplier_revealed.png`(Plan 06-02 將重命名至 `…-archived/`)
