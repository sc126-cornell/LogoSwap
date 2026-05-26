---
quick_id: 260527-251
slug: cleanup-v1-debug-artifacts
date: 2026-05-27
description: 清理 repo root 的 milestone v1.0 hotfix 06 debug artifacts(72 個檔案)+ 新增 .gitignore 防護 pattern,交給同事前讓 repo 乾淨
status: complete
---

# Quick Task: Cleanup v1.0 Debug Artifacts

## Goal

把 milestone v1.0 hotfix 06(dCt-residue)期間累積在 repo 根目錄的 72 個 debug
artifacts 分類處置,讓接手同事 clone 後看到的是乾淨 repo。

## Decisions(2026-05-27 AskUserQuestion 已確認)

| 類別 | 檔案 | 處置 |
|---|---|---|
| A1 — 供應商樣本 | `3013A-13A-C6-XX-3D02-A01-00040.pdf`(1 個) | 搬到 `samples/` |
| A2 — Forensic 證據 | `_verify_dct_residue_fix.py`、`_verify_residue_mechanism.py`、`proof_recolored_black.png`、`proof_optionA_recolored_black.png`(4 個) | 歸檔到 `.planning/debug/scratch/v1.0-hotfix06/` |
| B — LogoSwap 輸出檔 | `3013A-*_logoswap*.pdf`、`*_render.png`、`3013A-36A-C6-W4_*` 系列(7 個) | 刪 |
| C — 純 scratch 分析圖 | `attack_*` / `cmp_*` / `crop_*` / `q_[A-G]_*` / `r_*` / `shape_*` / `today_*` / `verify_today_*` / `_compare_orig.pdf` / `_verify_*_titleblock.png` / `_verify_optionA_*`(非 proof)/ `_verify_LIVE_*` / `_verify_work_copy.pdf` / `orig_hires.png` / `swap_hires.png` / `z_*.png` / `proof_normal/inverted.png` / `logo.png`(60 個) | 刪 |

## Tasks

- [x] AskUserQuestion 確認三類處置(完成)
- [ ] 建立 `samples/` 與 `.planning/debug/scratch/v1.0-hotfix06/`
- [ ] 移動 A1 + A2(共 5 個檔)
- [ ] 更新 `.planning/debug/resolved/redact-whitepaint-residue.md` — 把指向 root 的路徑改成 samples/ 與 debug/scratch/ 的新路徑
- [ ] 刪除 B + C(共 67 個檔)
- [ ] 更新 `.gitignore` — 加入 root 層 scratch pattern 防護
- [ ] 寫 SUMMARY.md
- [ ] 更新 STATE.md Quick Tasks Completed 表
- [ ] 本地 commit(per feedback_commit_push_cadence:不 push)

## Out of scope

- 不動 `data/`、`logos/`、其他既有 ignored 路徑
- 不動 `.planning/` 內既有 archive 結構(只新增 scratch 子目錄)
- 不 push commit
