---
quick_id: 260527-251
slug: cleanup-v1-debug-artifacts
status: complete
completed_at: 2026-05-27
---

# Summary

清理 milestone v1.0 hotfix 06(dCt-residue)期間累積在 repo 根目錄的 72 個 debug artifacts,讓 repo 在交接同事前乾淨。

## Disposition(72 個檔案)

| 處置 | 數量 | 目的地 |
|---|---|---|
| 搬到 `samples/` | 1 | `samples/3013A-13A-C6-XX-3D02-A01-00040.pdf` — 供應商樣本 PDF,將來 regression 測試與同事複現 dCt-residue 用 |
| 歸檔到 `.planning/debug/scratch/v1.0-hotfix06/` | 4 | `_verify_dct_residue_fix.py`、`_verify_residue_mechanism.py`、`proof_recolored_black.png`、`proof_optionA_recolored_black.png` — forensic 重跑腳本與攻擊/修復對照證據 |
| 直接刪除 | 67 | LogoSwap 過程輸出檔(7)+ 純 scratch 分析圖(60) |

## Reference 更新

- `.planning/debug/resolved/redact-whitepaint-residue.md` — 4 處路徑引用更新(原檔搬入 `samples/`、forensic scratch 搬入 `.planning/debug/scratch/v1.0-hotfix06/`),並將「scratch 檔,不要 commit」的舊指示重寫為「已歸檔於 v1.0-hotfix06,未來再現時可取出重跑」
- `.planning/phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-REVIEW.md:112` — `(repo root scratch)` 改為 `(samples/ 樣本,2026-05-27 cleanup 後)`

## .gitignore 防護

新增 root-anchored patterns(只 ignore repo root,`.planning/debug/scratch/**` 仍 tracked):

- 底線前綴 scratch:`/_*.py`、`/_*.pdf`、`/_*.png`
- 攻擊/比對圖:`/attack_*.png`、`/today_attack_*.png`、`/verify_today_*.png`、`/cmp_*.png`、`/crop_*.png`、`/q_[A-Z]_*.png`、`/r_*.png`、`/proof_*.png`、`/shape_*.png`、`/z_*.png`
- Render/hires:`/*_render.png`、`/*_hires.png`、`/orig_hires.png`、`/swap_hires.png`
- 誤存於 root 的 LogoSwap 輸出:`/*_logoswap*.pdf`

未來這類檔案再次出現於 repo root 時會被 git 自動忽略,但有歷史價值時仍可手動 `git add -f` 後搬入 `.planning/debug/scratch/<session>/` 歸檔。

## Verification

`git status --short` 收尾乾淨,只剩下計畫內變更:
- 3 個 modified(.gitignore + 2 個 doc reference)
- 3 個 new directory(samples/、.planning/debug/scratch/、.planning/quick/260527-251-*)

## Commit

Local commit only(per `feedback_commit_push_cadence`)。
