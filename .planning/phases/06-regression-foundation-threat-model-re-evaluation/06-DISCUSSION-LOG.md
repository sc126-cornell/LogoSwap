# Phase 6: Regression Foundation + Threat Model Re-evaluation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 6-regression-foundation-threat-model-re-evaluation
**Areas discussed:** Fixture 來源與 sanitization (Area A)
**Mode:** default (interactive) + --chain (auto-advance to plan-phase after CONTEXT.md commit)

---

## Gray Area 選擇

呈現給使用者 5 個 gray areas(multiSelect):

| Option | Description | Selected |
|--------|-------------|----------|
| A. Fixture 來源與 sanitization | ≥3 個 CAD-glyph PDF 從哪來?repo root 已有 1 個;sanitization 做到什麼程度?STATE.md blocker。 | ✓ |
| B. Binary fixtures in git vs 合成 | 破 conftest 「no committed binaries」convention?還是 in-memory synthetic? | (Claude 裁量) |
| C. THREAT-01 文件落點 | 新建 project-level `.planning/SECURITY.md` vs per-phase `06-SECURITY.md` vs 更新 archived Hotfix 06 SECURITY? | (Claude 裁量) |
| D. 紅燈測試標記策略 | `pytest.mark.xfail(strict=True)` vs `mark.skip` vs 不標? | (Claude 裁量) |

**User's choice:** A 單獨討論;B/C/D 交由 Claude 裁量,結論寫進 CONTEXT.md。

---

## Area A: Fixture 來源與 sanitization

### Q1/4 — Fixture 來源

| Option | Description | Selected |
|--------|-------------|----------|
| (a) 手上已有 2+ 個另外的供應商 CAD PDF、一週內可交出 | 真實 supplier PDF 為主要來源,sanitization 為重點工作。STRIDE Illustrator attacker 在真實樣本上驗證。 | ✓ |
| (b) 只手上 1 個真實樣本、剩下由 conftest 合成 zero-area type='f' synthetic PDF | 1 real + 2 synthetic,優點是不被 blocker 拖,缺點是 synthetic 與 Illustrator 出口 PDF 漏掉 corner cases。 | |
| (c) 這週兩個管道平行:詢問工程師 + conftest synthetic 作為 fallback | 兩管道並進,sanitization script 先寫好 unblock test 結構。 | |

**User's choice:** (a) — 手上已有 2+ 個另外的供應商 CAD PDF、一週內可交出。
**Notes:** STATE.md blocker「TEST-01 需要實際樣本」由此 unblock。Phase 6 plan 時 planner 仍須列 contingency(若工程師延遲交付,以 1 real + 2 synthetic placeholder fallback,記入 STATE.md)。

### Q2/4 — Sanitization 標準 + git 儲存策略

| Option | Description | Selected |
|--------|-------------|----------|
| (a) git-LFS 或 external storage 管真實 PDF、不進 public repo | Fixture 走 .gitignore + `${LOGOSWAP_FIXTURE_DIR}` env var;零法律曝險,但 CI 起跳複雜、sample bytes 不在 repo 同步。 | |
| (b) 脫敏 sanitization 後 commit 進 repo:剝 metadata + content-stream find-replace 供應商名為 `TESTCO` + bbox/fingerprint cleanup | Fixture 跟 code 同步,後人 git pull 全套都在。實作複雜,但 reviewer 可審。 | ✓ |
| (c) 公司內部 self-hosted GitLab/Gitea、Phase 6 fixture 只進 internal repo | 公開 repo 只作 AGPL 合規用途;需評估內部 git infra 成本。 | |

**User's choice:** (b) — 脫敏後 commit 進 repo,以 content-stream find-replace 供應商名為 TESTCO + bbox fingerprint cleanup。
**Notes:** 此選擇隱含「Area B = binary fixtures **進** git」已決定。`tests/fixtures/cad-glyph/` 是 conftest「no committed binaries」convention 唯一例外,於 README.md 文件化。

### Q3/4 — Supplier brand glyph(zero-area type='f' 攻擊目標)如何脫敏

| Option | Description | Selected |
|--------|-------------|----------|
| (a) 保留原 glyph 形狀 — 認為 CAD 結構 glyph 不夠 identifying / 商標非著名品牌 | 最快,但 brand visual 公開。僅在 supplier 商標是 generic logotype 時可行。 | |
| (b) 複寫為有同型攻擊面、但不同形狀的 `TESTCO` 商標 glyph | 用 fitz build 新 zero-area type='f' fill 序列(TESTCO 字型外廓以 m/l/f/B 繪製),替換原 supplier glyph。保留 attack 機制、visual 是 testbed 生成 generic wordmark。最嚴謹但實作較重。 | ✓ |
| (c) 從 zero-area glyph 改為不可辨識的 abstract shape 組(隨機多邊形 zero-area fills) | 不模仿 supplier 商標、製造一組「隨機多邊形 zero-area type='f'」作為 representative-shape proxy。最輕鬆但 visual signature 跟實際 CAD-glyph attack vector 較遠。 | |

**User's choice:** (b) — 複寫為 TESTCO wordmark glyph,保留同型 zero-area type='f' 攻擊面。
**Notes:** sanitization script 結尾 assert `count_zero_area_fills_fully_inside(REGION) ≥ 原 count 的 90%` 確保 attack 面密度未流失。

### Q4/4 — Sanitization 操作流程 + Coverage 分布

| Option | Description | Selected |
|--------|-------------|----------|
| (a) `scripts/sanitize_fixture.py` 一次性工具 + ≥1 文字 / ≥1 圖形 / ≥1 複合 glyph coverage + README.md | script commit 進 repo(可審計、可重現);raw PDF 不進 git。fitz import 不破 AGPL seam(scripts/ 不在 guard scope)。assertion 自查(metadata 空、原 supplier 名不出現、zero-area 保留)。 | ✓(by 「結果好的做法優先」) |
| (b) conftest sanitize-on-collect hook + raw PDF 進 gitignored 本機 dir + 每次 session 生 sanitized cache | 複雜,sanitized fixture 在 git 跟 code 同步(已決)兩件事,矛盾。 | |
| (c) 手化、僅寫 `tests/fixtures/cad-glyph/README.md` 說明、實體 sanitization 由該件者手工跑 | 最輕但不可重現、不可審。不推薦。 | |

**User's choice(freeform):** 「結果好的做法優先」 — delegated to Claude;Claude selected (a).
**Notes:** scripts/sanitize_fixture.py 是 Phase 6 兩個核心新增 file 之一(另一個是 tests/test_illustrator_attack_regression.py)。`fitz` import 在 scripts/ 內不破 AGPL guard test(該 test 只掃 `app/**/*.py`)。Coverage = ≥1 text glyph + ≥1 figure glyph + ≥1 mixed = ≥3,對齊 ROADMAP success criteria #1。

---

## Claude's Discretion(B/C/D — user delegated)

### Area B: Binary fixtures in git vs in-memory(由 Q2 (b) 隱含決定 + 補完細節)

**Decision:** `tests/fixtures/cad-glyph/*.pdf` 是 conftest「no committed binaries」convention 的**唯一例外**。
**Rationale:**
- 既有 `_build_pdf` / `_build_*_pdf` in-memory builders 哲學保留,新 cad-glyph fixtures 走獨立 dir + README.md 明寫「為什麼是例外」
- 真實 supplier PDF 包含 Illustrator 出口 corner cases(q/Q wrap 慣例、XObject 命名、content stream 多 stream 分割),這些 corner cases synthetic builder 漏掉的可能性高
- Phase 6 設計目的是「在真實樣本上紅燈」— in-memory synthetic 不能達到這個信任度

### Area C: THREAT-01 文件落點

**Decision:** 新建 `.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-SECURITY.md`,沿用 v1.0 per-phase SECURITY.md pattern;不另建 top-level `.planning/SECURITY.md`。
**Rationale:**
- v1.0 archived 5 個 per-phase SECURITY.md(每個 phase 一個)已建立 pattern
- `gsd-secure-phase` agent 預期 per-phase 06-SECURITY.md 結構,Phase 7 close 時可平順 cross-reference 並 supersede T-02-07 / T-06-01
- 將來規模增長(v1.2 / future)若需要 project-level 主檔,再合併;v1.1 不擴
- T-02-07 從 archived `06-HOTFIX-SECURITY.md`(在 `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/`)的 `CLOSED with documented residual` 在新 06-SECURITY.md 中 cross-reference + 標 `RE-OPENED 2026-05-28 (v1.1 Phase 6) — pending Option B`
- T-06-01 新 threat(Illustrator-class editor attacker pulls image XObject overlay)在 06-SECURITY.md 設為 `OPEN — pending Option B (Phase 7)`,evidence cite `_attack_proof_supplier_revealed.png` + 新 pytest

### Area D: 紅燈測試標記策略

**Decision:** `pytest.mark.xfail(strict=True, reason="Option B pending in Phase 7 — zero-area type='f' fills 未從 content stream 真正刪除,Illustrator-class editor 拔 image XObject 後可重現供應商商標")`。
**Rationale:**
- **xfail strict=True 是 phase handoff 自動 signal:** Phase 7 implementer 一旦讓測試通過,strict=True 把 XPASS 報為失敗(`[XPASS(strict)]`),強迫 implementer 拔掉 marker → 自然 promote 為 PASSED
- vs (b) `@pytest.mark.skip` — 測試不跑、Phase 7 implementer 無 fast feedback loop、容易忘記拔
- vs (c) 不標、預期 CI fail — 把整個 CI 染紅,其他改動失去 baseline,違反「CI 綠 = 健康」原則
- Reason 字串含繁中 + cross-reference 路徑(SEC-01),Phase 7 implementer grep `xfail.*Option B` 就能找到要拔的 marker
- Test count 影響:Phase 6 baseline 變「301 passed + 3 skipped + 3 xfailed」,Phase 7 落地後變「304 passed + 3 skipped」(strict=True 強制)

---

## Scope creep redirected → Deferred

無 — 使用者在 Area A 討論中沒有提出新的 capability 要加;所有問題都在 Phase 6 boundary 內。

CONTEXT.md `<deferred>` 區段已列既有 deferred items(form XObject 遞迴 surgery、stroke surgery、`is_raster_fallback_image` getter、CMap decoding helper、watermark cleanup 等)— 這些都是 STATE.md / REQUIREMENTS.md 既有 deferred,沿用而非新增。

---

## Discussion meta

- **耗時(estimated):** 4 個 AskUserQuestion 回合,~5 min user-side。
- **沒重複問已答的問題:** AGPL seam、minimum-change、5330290 教訓、conftest in-memory 哲學、繁中文案、commit/push 節奏 — 全部從 PROJECT.md / STATE.md / memory 載入並在 CONTEXT.md `<domain>` § "Carrying forward" 明示。
- **沒被誘導 scope creep:** Phase 6 純測試 / 文件層,使用者也沒嘗試加 Option B 實作或文件同步等屬於 Phase 7/8 的 work。
- **--chain mode:** discussion 完成後 auto-advance 到 `/gsd-plan-phase 6 --auto` 走 plan + execute。
