# Requirements: PDF 商標替換工具 — Milestone v1.1

**Defined:** 2026-05-28
**Milestone:** v1.1 — Harden against Illustrator-class attacks on CAD-generated PDFs
**Core Value:** 能乾淨地「移除而非覆蓋」供應商的商標圖案與文字,並換上我司商標,產出品牌正確、可對外使用的 PDF。

**起因:** 2026-05-28 forensic attack script 實測證實 — 工程師回報的「Illustrator 編輯 LogoSwap 輸出後供應商商標重現」是真實攻擊面,專門影響 CAD-glyph 零面積 fill 商標的 PDF。v1.0 close 時把 Option B(content-stream surgery 真正刪除 zero-area sources)留在 Deferred,deferral 假設「Option A 對使用者實質不可恢復」已不成立。

## v1.1 Requirements

11 個 requirements 分 5 類,對應到 roadmap 階段(Phase 6/7/8)。

### Option B 核心(SEC)

content-stream surgery 真正刪除零面積 type='f' fills,關閉 Illustrator 拔 image XObject 的攻擊面。

- [ ] **SEC-01**: 使用者透過 LogoSwap 處理的 CAD-glyph PDF,被 Illustrator / Acrobat Pro 級工具編輯刪除 image XObject 圖層後,框選區內供應商商標 vector path 在重新渲染時不可見(零面積 type='f' 已從 page content stream 真正刪除,不只是被 overlay 蓋住)
- [ ] **SEC-02**: 對「正常面積 vector 商標」PDF(`apply_redactions` 已能真正刪除的類型),Option B 為 no-op,不破壞既有清乾淨的渲染結果、不引入新的 visual artefact
- [ ] **SEC-03**: Option B 只修改 page-level content stream,不誤改 form XObject 內容(Illustrator embedded 巢狀 XObject 常見);若 zero-area fills 位於 form XObject 內,系統需安全處理(可選:不處理 + 記 log,或進入 form XObject 內處理 — 由 phase planning 決定)

### 威脅模型重評(THREAT)

把「Illustrator-class editor」加入威脅 actor,更新所有相關安全文件。

- [x] **THREAT-01**: STRIDE 威脅模型新增 "Illustrator-class editor attacker" actor;Hotfix 06 的 T-02-07 從 "CLOSED with documented residual" 重新評估,Option B 落地後重新關閉為 "CLOSED via Option B"
- [ ] **THREAT-02**: 三處「LIMITATION (be honest)」docstring 區段同步更新 — `app/services/pdf_engine.py::replace_region_with_white_raster`、`app/services/redact.py` 模組層級 `TRUE_REMOVAL_LIMITATION`、`app/services/redact.py` dispatcher inline comment「HONEST LIMITATION」— 從「需要 delete image XObject + per-path bbox surgery 攻擊」改為「Option B 已關閉零面積 source 路徑」

### Regression 測試基礎(TEST)

確保 Option B 對真實 CAD-glyph PDF 有效,且未來不會回退。

- [x] **TEST-01**: 收集 ≥3 個工程師手上實際出問題的 CAD-glyph supplier PDF(來源例:AutoCAD / SolidWorks / Catia 匯出),sanitized(去除敏感 metadata)後納入 `tests/fixtures/cad-glyph/` 作為 regression baseline
- [x] **TEST-02**: 攻擊模擬腳本(目前 `.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py`)改寫為 pytest regression test:對每個 fixture 跑「LogoSwap process → 用 content-stream surgery 拔掉 image XObject → assert 框選區 render 仍 ≥98% 白 + zero-area fills count == 0」
- [ ] **TEST-03**: Option B 核心 helper 單元測試 — zero-area fill counter、content stream rewrite correctness(算子序列邊界判定)、form XObject 巢狀偵測、no-op 行為(input 不含 zero-area fill 時)、邊界條件(0 / 1 / 100 / 1742 個 zero-area fill 的密度梯度)

### 文件同步(DOC)

Option B 落地後同步所有面向同事 / 法務 / 維運的決策文件。

- [ ] **DOC-01**: `HANDOFF.md` 第 6 節(核心領域知識備忘)更新 — 加入 6.5 小節「Option B content-stream surgery」,描述「為什麼 apply_redactions + Option A 不夠、Option B 補上的是什麼、CAD-glyph 與一般 vector 商標的處理差異」;Option A 描述同步調整為「Option A + B 雙層防線」
- [ ] **DOC-02**: `PROJECT.md` Key Decisions 加入「Hotfix v1.1 — Option B 落地」決策列,Rationale 記錄 v1.0 deferral 假設破滅的證據點;`.planning/STATE.md` Deferred 表中 Option B 條目移除(已在 v1.1 啟動時改寫,driver phase 完成時 final-clean)

### LIVE 部署收口(DEPLOY)

Option B 上 LIVE 並 LIVE-UAT 驗證(沿用 v1.0 流程)。

- [ ] **DEPLOY-01**: Option B + 新 regression test 推到 Zeabur(若 Zeabur 仍開著)或本機 Docker,LogoSwap 對 ≥1 個 CAD-glyph 樣本完成 upload → 框選 → process → download → Illustrator-attack-simulation 全綠通過

## Future Requirements(deferred)

從 v1.0 帶到下個 milestone,v1.1 不處理:

- **嵌入式整合(colleague approval site)** — HANDOFF.md 已為同事準備好;實際整合需求出現時啟動
- **多檔批次處理** — 須引入 task queue(Celery + Redis);v1 採手動單檔互動
- **`is_raster_fallback_image()` getter** — colleague 整合需要區分 fallback overlay 與真 logo image 時才加
- **`residual_whitepaint` 顯式列入 `_PROCESS_STATUS`** — dict.get fallback 已正確映射 422,純 self-documentation
- **超大影像錯誤訊息實機驗證(≥89MP)** — 自動測試覆蓋 OK,UI 字串待真檔到手

## Out of Scope

明確排除,寫下理由防止 scope creep:

| Feature | Reason |
|---------|--------|
| 對 form XObject 內 zero-area fills 做遞迴 content-stream surgery | 高複雜度、易破壞 Illustrator embed 結構;v1.1 SEC-03 採「page-level only,form XObject 留 log」策略,真正出現實際樣本再評估 |
| 對 zero-area `type='s'`(stroke)做 surgery | 目前威脅證據都是 type='f' fills;stroke 在 dCt-residue investigation 中未出現殘留問題 |
| 在 LogoSwap 內偵測「這個 PDF 來源是不是 CAD」做 dispatcher | Option B 本身就是 no-op-safe(SEC-02);加 source detection 是過度設計 |
| AGPL §13 三件套變更 | 內部部署計畫已確定不觸發(memory project_deployment_licensing);本 milestone 不動 |
| Vector inpainting(把刪掉的供應商商標位置「智能補回背景」)| 與 LogoSwap 核心定位(替換為本司商標)衝突,本來就 out of scope |

## Traceability

每個 v1.1 requirement 對應到一個 phase,100% 映射,無 orphan。

| Requirement | Phase | Status |
|-------------|-------|--------|
| TEST-01    | Phase 6 | Complete |
| TEST-02    | Phase 6 | Complete |
| THREAT-01  | Phase 6 | Complete |
| SEC-01     | Phase 7 | Pending |
| SEC-02     | Phase 7 | Pending |
| SEC-03     | Phase 7 | Pending |
| TEST-03    | Phase 7 | Pending |
| THREAT-02  | Phase 8 | Pending |
| DOC-01     | Phase 8 | Pending |
| DOC-02     | Phase 8 | Pending |
| DEPLOY-01  | Phase 8 | Pending |

**Coverage:**
- v1.1 requirements: 11 total
- Mapped to phases: **11 / 11 ✓**
- Per-phase distribution: Phase 6 = 3 reqs · Phase 7 = 4 reqs · Phase 8 = 4 reqs

---
*Requirements defined: 2026-05-28*
*Last updated: 2026-05-28 — Traceability filled after `/gsd-roadmap` 完成(3 phases / 11 reqs / 100% coverage)*
