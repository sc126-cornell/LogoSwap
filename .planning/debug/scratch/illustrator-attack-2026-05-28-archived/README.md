# Illustrator attack — 2026-05-28 forensic evidence (archived)

> **狀態**:Archived(原 dir 名 `illustrator-attack-2026-05-28/`,Phase 6 Plan 06-02 Task 4 重命名為 `…-archived/`)。
> **退役**:`.py` 攻擊腳本已刪除(邏輯搬入 `tests/`);保留 4 個 PNG/PDF 證據作審計 cite。

## 1. 為何 archived(v1.1 milestone 啟動 ground-truth)

本目錄保存 **2026-05-28 forensic attack reproduction** 的證據檔。原 scratch 是工程師回報「Illustrator 編輯 LogoSwap 輸出後供應商商標重現」的問題定位 reproduction —— 對 `samples/3013A-13A-C6-XX-3D02-A01-00040.pdf`(real supplier CAD-glyph PDF)跑「LogoSwap process → Illustrator 拔 image XObject overlay → 觀察框選區重新 render」實驗,實證 v1.0 close 時的 deferral 假設「Option A overlay 對使用者實質不可恢復」破滅。

此證據鏈為 **v1.1 milestone 啟動的 ground-truth proof**,將被以下 doc cite:

- `.planning/PROJECT.md` Active 區段(milestone v1.1 啟動理由)
- `.planning/STATE.md` milestone v1.1 啟動歷史
- `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`(T-02-07 RE-OPENED + T-06-01 OPEN 兩條 threat 的 evidence cite)
- 未來 Phase 8 PROJECT.md Key Decisions「Hotfix v1.1 — Option B 落地」決策列(DOC-02)

## 2. `.py` 攻擊腳本退役 — 邏輯已搬入 `tests/`

原 scratch 內含兩個 `.py` 檔已 **刪除**(commit history 仍可 `git log --all --diff-filter=D --follow -- .planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_delete_image_xobject.py` 查回):

- `_attack_delete_image_xobject.py` —— 主攻擊腳本(`q ... /Im Do ... Q` regex 刪 image XObject content-stream block + multi-stream `update_stream` write-back)
- `_check_supplier_removal.py` —— 補強檢查腳本(配合主腳本驗證)

**邏輯落點**:

- **Helper module** `tests/_illustrator_attack.py`:VERBATIM-port 原 scratch lines 40-115 為 3 個可重用 export:
  - `delete_image_xobjects_intersecting(doc, page_index, rect) -> int`
  - `render_region_white_pct(pdf_path, page_index, rect) -> float`
  - `count_zero_area_fills_in_region(pdf_path, page_index, rect) -> int`
- **主測試** `tests/test_illustrator_attack_regression.py`:`@pytest.mark.parametrize` over 3 個 sanitized fixture(`tests/fixtures/cad-glyph/{text|figure|mixed}-glyph-01.pdf`)× `@pytest.mark.xfail(strict=True)` —— Phase 6 期望 3 個 XFAIL;Phase 7 落地 Option B 後變綠(XPASS strict → implementer 拔 marker 為 handoff completion 動作)。

## 3. 保留的 4 個 PNG/PDF 證據用途

| Artefact | 用途 |
|---|---|
| `_attack_proof_supplier_revealed.png` | Illustrator 拔 image XObject 後框選區 render —— **供應商商標重現** 的視覺證據;06-SECURITY.md T-06-01 evidence cite |
| `_attack_target_pre.png` | 攻擊前 LogoSwap 輸出 render —— 框選區乾淨(Option A overlay 視覺有效) |
| `_attack_orig_for_comparison.png` | 原供應商 PDF render —— ground-truth reference(此 PNG 含原供應商 IP,目錄不應對外 publish;`.planning/debug/scratch/` 不會自動同步進 npm / PyPI,但 GitHub clone 可見 —— 留待 AGPL §13 compliance review 時納入評估) |
| `_attack_image_xobject_deleted.pdf` | 攻擊輸出的攻擊後 PDF —— 可作 Phase 6 regression test cross-verify reference 用 |

## 4. Cross-references

- **新 pytest**:
  - `tests/test_illustrator_attack_regression.py`(主測試 —— 3 個 XFAIL)
  - `tests/_illustrator_attack.py`(helper)
- **新 sanitized fixtures**(Plan 06-01 交付):`tests/fixtures/cad-glyph/{text,figure,mixed}-glyph-01.pdf` + `*.json` sidecar manifest + `README.md`
- **威脅模型**:`.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`(T-02-07 RE-OPENED + T-06-01 OPEN 兩條皆 `accept (P0, transition-pending until Phase 7)`)
- **一次性 sanitize 工具**:`scripts/sanitize_fixture.py`(Plan 06-01 交付;`scripts/` 不在 AGPL guard scope 內,可 import fitz)
- **Phase 7 對接**:`.planning/REQUIREMENTS.md` SEC-01 / SEC-02 / SEC-03(Option B 落地後 close T-02-07 + T-06-01);Plan 07-XX 將新增 helper 單元測試(TEST-03)。

## 5. 原始 raw supplier PDF 處置

Phase 6 Plan 06-02 Task 4(本 task)同步完成:

- **`samples/3013A-13A-C6-XX-3D02-A01-00040.pdf`**(tracked 副本)→ `git rm` 從 git index 移除;working tree bytes 物理移動到本目錄(被 `.gitignore` archived-anchored 屏蔽,不再 track)。
- **Repo root `3013A-13A-C6-XX-3D02-A01-00040.pdf`**(untracked 副本)→ 物理 `mv` 到本目錄(`.gitignore` archived-anchored 屏蔽)。
- **本目錄內的 raw `3013A-...pdf`**:`mixed-glyph-01.pdf` fixture 的 raw source,**僅 maintainer 本機可見**(`.gitignore` `/.planning/debug/scratch/illustrator-attack-2026-05-28-archived/3013A-*.pdf` 屏蔽)。

**Repo phase-level invariant 達成**:`git ls-files | grep -E '3013A-13A-C6-XX'` returns empty —— 不再有任何 raw supplier PDF tracked in repo(per Plan 06-02 checker Blocker #2 + Warning #9)。
