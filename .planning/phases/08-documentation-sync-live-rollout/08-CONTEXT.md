# Phase 8: Documentation Sync + LIVE Rollout - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Option B(Phase 7 content-stream surgery)落地後,把所有面向同事 / 法務 / 維運的決策文件同步,並把新版推上 LIVE 做端到端驗證,最後收尾 v1.1 milestone。具體交付(對應 4 reqs):

- **THREAT-02** — 三處「LIMITATION (be honest)」docstring 同步改寫
- **DOC-01** — `HANDOFF.md` 加 6.5 小節「Option B content-stream surgery」
- **DOC-02** — `PROJECT.md` Key Decisions 加 v1.1 落地列 + `STATE.md` Deferred 表 Option B 條目 final-clean
- **DEPLOY-01** — 新版上 LIVE + 對 ≥1 個 CAD-glyph 樣本完成 upload→框選→process→download→attack-sim 全綠

**Not in this phase（scope anchor）:** 任何 production 邏輯改動(Option B 已在 Phase 7 完成)、form XObject 遞迴 surgery、type='s' stroke surgery、AGPL §13 三件套結構變更。本階段只動「文件文字 + 部署 + 驗證 + milestone 收尾」。

</domain>

<decisions>
## Implementation Decisions

### Deploy & UAT ordering
- **D-01:** LIVE-UAT 在 **Zeabur 線上站點**(https://logoswap.scottchen0622.com)跑 — 直接 `git push` 觸發 Zeabur 自動部署。**這是 Phase 8 的 scoped 例外**,刻意覆寫常規「UAT 期間 commit local but never push」cadence。理由:v1.1 只動 2 個 production 檔(`pdf_engine.py` + `redact.py`)+ 文件,且 Phase 7 已三道閘綠。日後一般 phase 仍守原 cadence — 此例外不外溢。
- **D-02:** 上線順序固定為:**(1)** 三處 LIMITATION docstring + HANDOFF 6.5 + PROJECT/STATE 全部改完並 commit local → **(2)** 一次 push 部署到 Zeabur(此 push 帶齊 Phase 6 fixtures + Phase 7 Option B + Phase 8 文件,是 **v1.1 第一次上 production**)→ **(3)** LIVE-UAT → **(4)** 綠燈後 final code-review/fix pass → **(5)** tag v1.1。final code-review 刻意落在 push 之後(接受此取捨,因 Phase 7 已三道閘綠)。

### LIVE-UAT sample & attack verification
- **D-03:** 端到端 LIVE-UAT 用工程師手上**原始(未 sanitized)supplier PDF**,而非 repo 內 sanitized fixture — 最貼近真實使用情境(含完整 supplier 商標)。此檔**不入 repo**(binary/敏感資料,違反 conftest「never commit binary」convention)。⚠️ **前置相依:需工程師再提供一份新鮮真實 supplier CAD-glyph PDF** — planner 應把「樣本取得」列為 UAT 任務的 blocking 前置。
- **D-04:** attack-sim 對 LIVE 下載輸出檔的驗證用**一次性 scratch script**(放 `.planning/debug/scratch/`),import 既有 `tests/_illustrator_attack.py` 邏輯,對下載檔 assert render ≥98% 白 + 框選區 zero-area type='f' count == 0,跑完退役。沿用既有攻擊邏輯、不新增 production/test surface(minimum-change,5330290 紀律)。**否決**了「包成 standalone CLI runner 進 scripts/」(避免新增維護面)。

### Milestone-close boundary
- **D-05:** Phase 8 範圍**一路延伸到 milestone close** — plans 須含 final code-review/fix + push origin + `git tag v1.1` + 跑 `/gsd-complete-milestone`(archive ROADMAP、PROJECT.md milestone audit、prep 下個版本)。一次收乾淨,不留尾巴。

### Carried forward (not re-discussed — 沿用既有標準)
- **三道閘:** 本 phase boundary 照標準跑 review/fix + validate + secure。註:Phase 8 幾乎只動文件文字 + 部署 config,secure 預期接近 no-op(THREAT-02 是 docstring 誠實化,非新 mitigation,無威脅面變動);validate Nyquist 在本 repo config 停用(no-op);review/fix 須跑 — 成功標準 5 的「final code-review pass」即落在此閘。
- **AGPL seam 不動:** `import fitz` 僅 `app/services/pdf_engine.py`;§13 三件套(GitHub public + LICENSE + UI footer source link)既有就位,本階段只調文字。
- **Python 3.12 pin(IN-02):** `Dockerfile` 兩個 stage 都已 `python:3.12-slim-bookworm`,部署層已滿足;LIVE 驗證時順手確認線上 runtime 真的是 3.12(secure audit 環境曾是 3.14,維持 regex/logging parity)。
- **minimum-change 紀律(5330290 教訓):** 文件階段尤其別夾帶 polish;nice-to-have 留 maintenance sprint。

### Claude's Discretion
- HANDOFF 6.5 / PROJECT Key Decisions 列 / 三處 docstring 的**實際措辭**由 planner/executor 依成功標準擬。三處 LIMITATION 的改寫**方向**已由成功標準 1 定死:從「需要 delete image XObject + per-path bbox surgery 攻擊(Option A overlay 為唯一防線)」改為「Option B 已關閉 page-level 零面積 source 路徑;form XObject 內部仍為 Option A overlay-only(已記 log)」。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap & requirements(locked scope）
- `.planning/ROADMAP.md` § Phase 8 — 5 success criteria + 4 reqs(THREAT-02, DOC-01, DOC-02, DEPLOY-01)+ Phase 8 部署提醒(pin 3.12)
- `.planning/REQUIREMENTS.md` § v1.1 — THREAT-02 / DOC-01 / DOC-02 / DEPLOY-01 全文 + Out of Scope 表

### Files to edit（THREAT-02 / DOC-01 / DOC-02 — 改寫目標）
- `app/services/pdf_engine.py:933` — `replace_region_with_white_raster` docstring「LIMITATION (be honest)」（THREAT-02 location 1）
- `app/services/redact.py:6` — 模組層級 `TRUE_REMOVAL_LIMITATION` 字串（THREAT-02 location 2）
- `app/services/redact.py:245` — dispatcher inline comment「HONEST LIMITATION」（THREAT-02 location 3）
- `HANDOFF.md` § 6（核心領域知識備忘）— 加 6.5「Option B content-stream surgery」+ Option A 描述調為「Option A + B 雙層防線」（DOC-01）
- `.planning/PROJECT.md` § Key Decisions — 加「Hotfix v1.1 — Option B 落地」列，Rationale 引用 2026-05-28 forensic attack 證據（DOC-02）
- `.planning/STATE.md` § Deferred Items / Promoted — Option B 條目 final-clean（DOC-02）

### Option B implementation reference（寫準確 docstring 的事實來源）
- `app/services/pdf_engine.py` — `delete_zero_area_type_f_fills_inside` + `count_zero_area_fills_fully_inside` + Shape 1/2 single-pass locator（Phase 7 落地;`_DISALLOWED_IN_BLOCK` fail-safe）
- `app/services/redact.py` — dispatcher Option B wiring（line ~195/197 boundary,既有 dispatcher 0 deletions）

### Attack-sim / LIVE-UAT
- `tests/_illustrator_attack.py` — 攻擊邏輯 helper（D-04 scratch script 會 import）
- `tests/test_illustrator_attack_regression.py` — 3 個 regression PASS（對照 LIVE-UAT 預期結果）

### Deploy
- `Dockerfile` — 已 pin `python:3.12-slim-bookworm`;Zeabur 注入 `$PORT`;build-time `sed` 替換 AGPL §13 `<OWNER>`
- `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/` — 2026-05-28 forensic 攻擊證據（PROJECT Key Decisions Rationale 引用點）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/_illustrator_attack.py`：攻擊模擬邏輯已 helper 化 — LIVE-UAT scratch script 直接 import,不重寫攻擊邏輯。
- `scripts/sanitize_fixture.py`：本階段 UAT 用原始檔不走 sanitize;僅當未來想把工程師的真實檔收成 fixture 才會用到（非本階段）。

### Established Patterns
- **Deferred-mutation**：處理只動 work 副本,原始檔不變 — LIVE-UAT 下載到的是 work 副本輸出。
- **三道閘 at boundary**：review/fix → validate → secure（memory）。
- **commit-local-never-push cadence**：本階段 D-01 為 scoped 例外,僅此 phase 適用。

### Integration Points
- Zeabur git-push 自動部署 → https://logoswap.scottchen0622.com（Cloudflare DNS）。push 即對外可見。
- AGPL §13 三件套既有就位,本階段只調文件文字,不動結構。

</code_context>

<specifics>
## Specific Ideas

- 三處 LIMITATION 改寫方向由成功標準 1 定死（見 Claude's Discretion）。
- HANDOFF 6.5 須描述「apply_redactions + Option A + Option B 三層防線分工」與「CAD-glyph vs 一般 vector 商標的處理差異」。
- PROJECT Key Decisions 新列 Rationale 須引用 2026-05-28 forensic attack 證據點（deferral 假設「Option A 對使用者實質不可恢復」破滅）。

</specifics>

<deferred>
## Deferred Ideas

- **Standalone LIVE-UAT attack runner（`scripts/`）** — 本階段否決,改一次性 scratch（D-04）。若未來 LIVE-UAT 變成常態流程,再評估包成可重複 CLI。

未選討論的「三道閘範圍」沿用既有標準,非 deferred。討論全程在 phase scope 內,無 scope creep。

</deferred>

---

*Phase: 8-Documentation Sync + LIVE Rollout*
*Context gathered: 2026-05-28*
