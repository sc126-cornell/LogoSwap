# Roadmap: PDF 商標替換工具 (PDF Logo Replacement Tool / LogoSwap)

## Milestones

- ✅ **v1.0 MVP — LogoSwap LIVE** — Phases 1-5 (shipped 2026-05-24,LIVE-UAT verified 2026-05-27 after hotfix 06+07) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- 🚧 **v1.1 — Harden against Illustrator-class attacks on CAD-generated PDFs** — Phases 6-8 (started 2026-05-28)

## Phases

<details>
<summary>✅ v1.0 MVP — LogoSwap LIVE (Phases 1-5) — SHIPPED 2026-05-24 (hotfix 06+07 閉環 2026-05-27)</summary>

- [x] **Phase 1: 輸入與預覽骨幹** (2/2 plans) — 上傳向量 PDF、伺服器端渲染、瀏覽器多頁預覽,原始檔保留 (completed 2026-05-22)
- [x] **Phase 2: 框選與真正移除(向量)+ 下載** (3/3 plans) — 座標對應骨幹、矩形框選、向量/文字真正移除、前後對照、下載 (completed 2026-05-22)
- [x] **Phase 3: 商標置入** (2/2 plans) — 固定商標庫、挑選並置入我司 logo(維持長寬比) (completed 2026-05-23)
- [x] **Phase 4: 點陣圖與圖片型檔案支援** (2/2 plans) — 圖片型 PDF 與獨立影像檔、移除區域填白(243 tests, 17 STRIDE threats closed) (completed 2026-05-23)
- [x] **Phase 5: 部署與穩固化(Ubuntu)** (2/2 plans) — Docker/Zeabur 部署、AGPL §13 三件套、SHA-256 integrity、1h TTL janitor、LIVE 上線(291 tests, 27 STRIDE threats closed) (completed 2026-05-24)

**Post-LIVE hotfixes (driven by real UAT on supplier CAD PDF):**

- [x] **Hotfix 06: dCt-residue Option A** — raster overlay for dense zero-area residue;closes the 1742-cover-union recovers-logo attack;5330290 second-push silent fail incident → revert → cherry-pick recovery (LIVE-UAT verified 2026-05-27)
- [x] **Hotfix 07: loader gap + error-copy UX** — `showResultImage` page loader, 4 apply-fail messages add 「,或重新開啟檔案再操作一次」 (LIVE-UAT verified 2026-05-27)

Final test count: 301 passed, 3 skipped. AGPL fitz seam preserved throughout (single-file import in `app/services/pdf_engine.py`).

</details>

### 🚧 v1.1 — Harden against Illustrator-class attacks (In Progress)

**Milestone Goal:** 落地 Option B(content-stream surgery 真正刪除 page-level 零面積 type='f' fills),把威脅模型從「內網 CLI 攻擊者」升級為「內網 + Illustrator/Acrobat Pro 級編輯者」,並透過 regression fixture + attack-simulation pytest 確保未來不會回退。

**Strategy:** 「先紅燈、再轉綠燈、最後同步文件 + LIVE」三段式 — Phase 6 把今天的 forensic 攻擊腳本變 pytest regression test 並收集 ≥3 個工程師手上實際出問題的 CAD-glyph fixture(此時測試應該是紅的,因為 Option B 還沒寫);Phase 7 在 `pdf_engine.py` 落地 Option B helper(注意 minimum-change 紀律 — 5330290 incident 教訓),Phase 6 的紅燈轉綠;Phase 8 同步 docstring/HANDOFF/PROJECT + LIVE 部署 + attack-sim 全綠驗證。

- [ ] **Phase 6: Regression Foundation + Threat Model Re-evaluation** — CAD-glyph fixture suite + attack-simulation pytest(red-light baseline)+ STRIDE 加入 Illustrator-class attacker (3 reqs)
- [ ] **Phase 7: Option B Implementation — Content-Stream Surgery** — `pdf_engine` helper 真正刪除零面積 type='f' fills + unit tests + Phase 6 攻擊測試轉綠 (4 reqs)
- [ ] **Phase 8: Documentation Sync + LIVE Rollout** — LIMITATION docstring 三處同步 + HANDOFF/PROJECT/STATE 更新 + LIVE 部署 + attack-sim 全綠驗證 (4 reqs)

## Phase Details

<details>
<summary>Phase 1-5 (v1.0 details) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)</summary>

For complete v1.0 phase goals, success criteria, requirements, and plans see the archived v1.0 roadmap. Below this section continues with v1.1 phase details.

</details>

### Phase 6: Regression Foundation + Threat Model Re-evaluation
**Goal**: 在動 Option B 實作之前先把「紅燈」立起來 — 收集 ≥3 個工程師手上實際出問題的 CAD-glyph supplier PDF 作為 sanitized fixture,把今天的 forensic 攻擊腳本(`_attack_delete_image_xobject.py`)改寫為 pytest regression test(此階段預期為紅),並同步更新威脅模型把 Illustrator-class editor attacker 列入 actor 清單。完成後 Phase 7 寫的 Option B 才有客觀「綠/紅」可驗。
**Mode:** hardening
**Depends on**: Phase 5 (v1.0 LIVE baseline,Option A overlay 已存在但對 Illustrator 攻擊不足)
**Requirements**: TEST-01, TEST-02, THREAT-01
**Success Criteria** (what must be TRUE):
  1. `tests/fixtures/cad-glyph/` 含 ≥3 個 sanitized supplier CAD-glyph PDF,涵蓋文字 glyph 與圖形 glyph representative shapes(metadata 已清,可入 git)
  2. 對每個 fixture 跑「LogoSwap process → 攻擊腳本拔 image XObject overlay → render 框選區」的 pytest test 存在且**目前紅燈**(Option B 未實作,Illustrator 攻擊應該成功還原供應商商標)
  3. `_attack_delete_image_xobject.py` 邏輯已搬入 `tests/` 並以 pytest fixture 化呼叫,scratch 腳本可從 `.planning/debug/scratch/` 退役
  4. `.planning/SECURITY.md`(或同等威脅模型文件)STRIDE 表新增 "Illustrator-class editor attacker" actor,T-02-07 從 "CLOSED with documented residual" 改回 "OPEN — Option B 落地後重新關閉"
**Plans**: 2 plans
  - [x] 06-01-PLAN.md — Sanitization tooling + 3 CAD-glyph fixtures + sidecar manifests (TEST-01)
  - [ ] 06-02-PLAN.md — Attack regression test (xfail strict) + 06-SECURITY.md (pre-mortem STRIDE) + scratch retirement (TEST-02, THREAT-01)

### Phase 7: Option B Implementation — Content-Stream Surgery
**Goal**: 在 `app/services/pdf_engine.py`(AGPL seam,fitz 唯一允許 import 的檔案)落地 Option B helper — 在 `apply_redactions` 之後、Option A overlay 之前,直接 rewrite page-level content stream 刪除 fully-inside-rect 的零面積 type='f' `m/l/f/B` 算子序列。對「正常面積 vector 商標」PDF 需 no-op(SEC-02),對 form XObject 內部巢狀 path 需安全處理不誤改(SEC-03,page-level only 策略 + log)。完成後 Phase 6 的紅燈攻擊測試應全綠。**紀律:**5330290 incident 教訓 — minimum-change,nice-to-have polish 留下個 maintenance sprint。
**Mode:** hotfix-class implementation
**Depends on**: Phase 6 (red-light regression test must exist to verify "green" objectively)
**Requirements**: SEC-01, SEC-02, SEC-03, TEST-03
**Success Criteria** (what must be TRUE):
  1. Phase 6 的「Illustrator 拔 image XObject → render 框選區」pytest test 全綠 — render 區 ≥98% 白,zero-area type='f' count 在框選區內 == 0(content stream 真的被刪)
  2. 對 v1.0 既有 fixture(無 zero-area fill 的正常 vector PDF)跑 full test suite 仍綠,Option B 為 no-op,既有 301 passed + 3 skipped baseline 不退步
  3. Option B helper 單元測試覆蓋 zero-area fill counter、content stream rewrite 算子序列邊界判定、form XObject 巢狀偵測(page-level only,不下鑽)、no-op 行為(input 無 zero-area fill)、密度梯度(0 / 1 / 100 / 1742 個 zero-area fill 條件)
  4. `grep -rn "import fitz" app/` 仍只在 `app/services/pdf_engine.py` 一行 — AGPL seam 未破
  5. 框選區若位於 form XObject 內,系統不靜默誤改,以 log 記錄 + safe-skip(SEC-03 page-level only 策略)
**Plans**: TBD

### Phase 8: Documentation Sync + LIVE Rollout
**Goal**: Option B 落地後同步所有面向同事 / 法務 / 維運的決策文件 — 三處「LIMITATION (be honest)」docstring 更新、HANDOFF.md 加 6.5 小節、PROJECT.md Key Decisions 加 v1.1 落地列,把實作推上 Zeabur(或本機 Docker)並對 ≥1 個 CAD-glyph 樣本完成端到端 LIVE-UAT(upload → 框選 → process → download → Illustrator-attack-simulation 全綠)。**紀律:**沿用 v1.0 流程 — UAT 期間 commit local but never push,LIVE-UAT 通過 + final review/fix pass 後才 push;AGPL §13 三件套無變更(僅文件文字調整,GitHub/LICENSE/UI footer 既有就位)。
**Mode:** rollout + docs sync
**Depends on**: Phase 7 (Option B helper must exist and pass Phase 6 regression test)
**Requirements**: THREAT-02, DOC-01, DOC-02, DEPLOY-01
**Success Criteria** (what must be TRUE):
  1. 三處 LIMITATION 段同步更新 — `app/services/pdf_engine.py::replace_region_with_white_raster` docstring、`app/services/redact.py` 模組層級 `TRUE_REMOVAL_LIMITATION`、`app/services/redact.py` dispatcher inline comment「HONEST LIMITATION」— 從「需要 delete image XObject + per-path bbox surgery 攻擊」改為「Option B 已關閉 page-level 零面積 source 路徑;form XObject 內部仍為 Option A overlay-only(已記 log)」
  2. `HANDOFF.md` 第 6 節新增 6.5 小節「Option B content-stream surgery」,描述 apply_redactions + Option A + Option B 三層防線分工與 CAD-glyph vs 一般 vector 商標處理差異;Option A 描述同步調整為「Option A + B 雙層防線」
  3. `PROJECT.md` Key Decisions 新增「Hotfix v1.1 — Option B 落地」決策列,Rationale 引用 2026-05-28 forensic attack 證據;`.planning/STATE.md` Deferred 表的 Option B 條目已最終移除(在 milestone 啟動時改寫 promoted,本階段做 final-clean)
  4. LIVE 環境(Zeabur 或本機 Docker)上跑新版,對 ≥1 個 CAD-glyph 樣本完成 upload → 框選 → process → download,LIVE 檔再跑一次 attack-simulation 腳本,render 結果 ≥98% 白(LIVE-UAT 綠燈)
  5. v1.1 milestone close 前 final code-review pass 跑完,所有 push 已到 origin,git tag `v1.1` 已標
**Plans**: TBD

## Progress

**Execution Order:**
v1.0: 1 → 2 → 3 → 4 → 5 (complete) → v1.1: 6 → 7 → 8

| Phase | Milestone | Plans Complete | Status   | Completed  |
| ----- | --------- | -------------- | -------- | ---------- |
| 1. 輸入與預覽骨幹      | v1.0 | 2/2 | Complete    | 2026-05-22 |
| 2. 框選與真正移除      | v1.0 | 3/3 | Complete    | 2026-05-22 |
| 3. 商標置入            | v1.0 | 2/2 | Complete    | 2026-05-23 |
| 4. 點陣圖與圖片型檔案  | v1.0 | 2/2 | Complete    | 2026-05-23 |
| 5. 部署與穩固化        | v1.0 | 2/2 | Complete    | 2026-05-24 |
| 6. Regression Foundation + Threat Model Re-evaluation | v1.1 | 1/2 | In Progress|  |
| 7. Option B Implementation — Content-Stream Surgery   | v1.1 | 0/TBD | Not started | - |
| 8. Documentation Sync + LIVE Rollout                  | v1.1 | 0/TBD | Not started | - |

## Backlog

候選但未排入當前 milestone 的工作,留待下個 `/gsd-new-milestone` 時考慮:

- **`is_raster_fallback_image(page, xref)` getter**:讓下游 colleague-system integration 區分 raster fallback overlay 與真 logo image。等實際 integration 需求出現再做。
- **`residual_whitepaint` 顯式列入 `_PROCESS_STATUS`**:目前透過 dict.get 預設 422 fallback 正確運作,僅 self-documentation gain。
- **超大影像錯誤訊息實機驗證**(WR-03 megapixel cap UI):自動測試覆蓋 OK,UI 字串待真實 ≥89MP 樣本到手再驗。
- **多檔批次處理**:目前每次只能處理一個 PDF。批次模式須引入 task queue(如 Celery + Redis)。Phase 5 close 時刻意排除。
- **嵌入式整合(colleague approval site)**:v1 預留 API base path + iframe-friendly 設計;實際整合留到下游需求出現。
- **對 form XObject 內 zero-area fills 做遞迴 surgery**:v1.1 SEC-03 採 page-level only + log 策略,真正出現實際樣本再評估遞迴方案。
- **對 zero-area `type='s'`(stroke)做 surgery**:目前威脅證據都是 type='f';stroke 未出現殘留問題。
