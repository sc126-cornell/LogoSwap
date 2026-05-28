# LogoSwap (PDF 商標替換工具)

## What This Is

一個可部署在 Ubuntu 伺服器的網頁工具,供貿易公司內部使用。供應商提供的產品設計 PDF(含 CAD 設計資料)裡有供應商的商標圖案與文字,本工具讓使用者在瀏覽器中預覽檔案、手動框選要處理的位置,將供應商商標/文字「真正移除」(而非覆蓋),換成本公司的商標,再輸出新的 PDF。

## Core Value

能乾淨地「移除而非覆蓋」供應商的商標圖案與文字,並換上我司商標,產出品牌正確、可對外使用的 PDF。

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- [x] 使用者可上傳單一**向量 PDF**(Phase 1 — UPLOAD-01/04)
- [x] 使用者可在瀏覽器預覽檔案,並在多頁之間切換(Phase 1 — PREVIEW-01/02,含整頁顯示預設縮放、深淺主題、整份文件 90° 旋轉)
- [x] 使用者可在頁面上手動框選一個或多個要處理的區域(可跨頁)(Phase 2 — REGION-01/02)
- [x] 對向量內容,框選區域內的供應商商標物件與文字被真正移除(非覆蓋)(Phase 2 — REMOVE-01/03/04)
- [x] 使用者可下載處理後的 PDF,原始檔案不被破壞(Phase 2 — OUTPUT-01;deferred-mutation 三目錄)
- [x] 系統提供固定的我司商標庫(`logos/` + `manifest.json`),使用者可瀏覽並挑選 logo(Phase 3 — LOGO-01)
- [x] 使用者可將選定的 logo 放到框選位置,維持長寬比、置中、隨頁面旋轉正立;支援「自動依框選形狀」逐區挑選(Phase 3 — LOGO-02)
- [x] 使用者可上傳**圖片型(點陣/掃描)PDF** 與**獨立影像檔**(PNG/JPG/TIFF)(Phase 4 — UPLOAD-02/03;hotfix 收口含 RGBA 合成白底、pristine 預覽資料源、megapixel 硬上限)
- [x] 對點陣圖/影像內容,框選區域以白色填滿(Phase 4 — REMOVE-02;含 Adobe-hairline / CAD-glyph zero-area artefact 物理覆蓋)
- [x] 可以 Docker 部署為網頁服務,處理大型與旋轉頁面、暫存檔自動清理、原始檔 SHA-256 驗證(Phase 5 — DEPLOY-01/02;**live 2026-05-24** at https://logoswap.scottchen0622.com via Zeabur PaaS,Cloudflare DNS,AGPL §13 三件套就位)

### Active

<!-- Current scope. Building toward these. -->

**Milestone v1.1 — Harden against Illustrator-class attacks on CAD-generated PDFs(2026-05-28 啟動)**

Goal:落地 Option B(content-stream surgery 真正刪除零面積 type='f' fills),關閉「Illustrator 拔掉 image XObject overlay 後供應商 CAD glyph 重現」的攻擊面;同步把威脅模型從「內網 CLI 攻擊者」升級為「內網 + 一般 PDF 編輯工具(Illustrator/Acrobat Pro 級)使用者」。

Target features(roadmap 階段細分):

1. **Option B 實作** — `pdf_engine` 新 helper 在 `apply_redactions` 後、Option A overlay 前直接 rewrite content stream 刪除 fully-inside-rect 的零面積 type='f' `m/l/f/B` 算子序列(避開 form XObject 巢狀地雷)
2. **威脅模型重評** — STRIDE 加入「Illustrator-class editor attacker」actor;T-02-07 從 "CLOSED with documented residual" 重新打開,Option B 落地後 close-with-fix
3. **CAD-glyph regression fixture** — 收集工程師手上實際出問題的 supplier PDF 樣本;sanitized fixture 涵蓋 representative shapes(文字 glyph、圖形 glyph)
4. **攻擊腳本變 regression test** — 今天的 `_attack_delete_image_xobject.py` 改寫為 pytest fixture,每次 release 自動跑「拔 image XObject → assert region 仍乾淨」
5. **HANDOFF.md + PROJECT.md 同步** — Option B 落地後更新 Key Decisions、核心領域知識備忘、Deferred 清單

起因:2026-05-28 forensic attack script 實測證實 — 對「正常面積 vector 商標」PDF 安全(`apply_redactions` 真正刪了),但對「CAD-glyph 零面積 fill 商標」PDF,Option A overlay 是唯一防線,Illustrator 可拔。原 v1.0 close 時 Option B deferral 假設(「Option A 對使用者實質不可恢復」)已被證明不成立。證據已歸檔於 `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/`(6 個檔,Plan 06-02 Task 4 已 `git mv` 至 archived 路徑 + .py 退役)。

**Milestone v1.1 進度(2026-05-28):**
- ✓ Phase 6 完成 — 紅燈基線就位(3 個 real-supplier sanitized fixture + xfail-strict regression test + 06-SECURITY.md pre-mortem STRIDE)。三道閘 review/validate/secure 全綠;sanitize_fixture.py 補強 Impl notes C + D 處理 PScript5 + Acrobat 出口 PDF 的 CMap font + Form-XObject stamp annotation 場景
- ✓ Phase 7 完成 — Option B content-stream surgery 落地(`pdf_engine.py::delete_zero_area_type_f_fills_inside` + Shape 1/2 single-pass index locator + redact.py dispatcher upstream defense,既有 dispatcher 0 deletions)。3 plans(含 07-03 gap-closure 修 Shape 1 perf 765s→1.12s + match 14%→100% + `_NUMBER` leading-dot regex bug)。三道閘全綠(deep review 抓 CR-01 over-delete BLOCKER + 6 WR 全修;secure SECURED threats_open:0)。**T-06-01 + T-02-07 CLOSED via Option B**(content-stream gate 真刪驗證,非 Option A overlay 視覺遮蓋)。baseline 338 passed + 3 skipped + 0 xfailed。AGPL seam intact
- ⏳ Phase 8 待跑 — 文件同步(LIMITATION docstring 三處改寫 = THREAT-02 + HANDOFF.md 6.5 = DOC-01 + PROJECT.md Key Decisions「Option B 落地」列 = DOC-02)+ LIVE 部署 + attack-sim 全綠驗證。部署提醒:pin Python 3.12(audit 環境是 3.14,維持 regex/logging parity)

### Deferred (carried forward from v1.0 close)

候選需求,將來 milestone 定義時重新評估優先級:

- **嵌入式整合(colleague approval site)**:v1 已預留 API base path + iframe-friendly 設計;實際整合需求出現時啟動。HANDOFF.md(2026-05-27)已為同事準備好決策樹與領域知識備忘
- **多檔批次處理**:v1 採手動單檔互動;批次須引入 task queue(如 Celery + Redis)
- **`is_raster_fallback_image()` getter**:colleague 整合需要區分 fallback overlay 與真 logo image 時才加
- **超大影像錯誤訊息實機驗證(≥89MP)**:自動測試覆蓋 OK;UI 字串待真檔到手

_2026-05-28 移除:Option B(content-stream surgery)— 已升格為 v1.1 active 第一優先,deferral 假設破滅。_

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- 批次處理多檔 — v1 採手動框選,屬單檔互動;批次延後到後續版本
- 與表單簽核網站整合 — v1 先做可獨立使用的工具,整合延後
- 帳號登入/權限控管 — 僅內網使用,v1 不需要
- 自動偵測商標位置(影像比對/OCR)— 已選擇手動框選,較可靠且有彈性
- 點陣圖背景還原(inpainting)— 移除後填白/底色即可,不還原被蓋住的內容

## Context

- 使用者為貿易公司,供應商會提供含 CAD 設計資料的產品設計 PDF。
- 來源檔案型態多元:向量 PDF、整頁掃描/點陣圖的圖片型 PDF、以及非 PDF 的獨立影像檔(PNG/JPG/TIFF)。
- 目標部署環境為 Ubuntu 伺服器,於公司內部網路使用。
- 未來可能將本工具掛入同事開發的「表單簽核網站」作為小工具。
- 技術上傾向使用 PyMuPDF;其 redaction 機制可在指定矩形區域內真正移除文字/向量物件,並對影像區域填色,正好對應「移除而非覆蓋」的核心需求。

## Constraints

- **Tech stack**: 核心 PDF 處理使用 PyMuPDF(Python)— 使用者指定,且 redaction 功能符合「真正移除」需求
- **Deployment**: 可安裝於 Ubuntu 伺服器的網頁工具 — 內部部署需求
- **Architecture**: v1 為可獨立執行的網頁,未來需能嵌入既有簽核網站 — 設計上預留整合彈性
- **Access**: 內網免登入 — v1 不做帳號權限,降低複雜度
- **Interaction**: 手動框選需要前端能渲染 PDF 並支援矩形框選 — 影響前端技術選型

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 由使用者手動框選決定移除區域(非自動偵測) | 商標樣式多變,手動框選最可靠且有彈性 | ✓ Validated (Phase 2) |
| 點陣圖移除採填白/底色(非 inpainting) | 降低技術複雜度,且符合使用者可接受的結果 | ✓ Validated (Phase 4 UAT) |
| 移除後貼上固定商標庫中的我司 logo 圖檔 | 公司 logo 固定,系統預存最方便挑選 | ✓ Validated (Phase 3) |
| 以 PyMuPDF 為核心 PDF 處理函式庫 | 使用者指定,且 redaction 符合「真正移除」需求 | ✓ Validated (Phase 2);fitz 嚴格限制在 `pdf_engine.py`(AGPL seam) |
| v1 為獨立工具、內網免登入 | 先交付核心價值,整合與權限控管延後 | ✓ Validated |
| Deferred-mutation:處理只動 work 副本,原始檔永不變(SHA-256 驗證) | 預覽 / 對照 / 重做不會破壞原檔,出錯也能恢復 | ✓ Validated (Phase 2/3) |
| Logo 自動依框選形狀挑選(原生長寬比最接近) | 多頁 PDF 上不同形狀的供應商商標,使用者不必逐區手動指定 | ✓ Validated (Phase 3 UAT) |
| 90° 旋轉作用在整份文件(非 per-page) | 供應商 PDF 多半整份方向一致,逐頁旋轉是反向使用情境 | ✓ Validated (Phase 3 UAT) |
| 套用變更後框選鎖定;以「恢復原圖」為唯一重置入口 | 保護跨多頁的變更不被誤動;後續編輯路徑更明確 | ✓ Validated (Phase 3 UAT) |
| 原圖 / 移除結果切換鈕移除(視圖自動切換) | 原圖渲染路徑修好前一直顯示移除結果;UAT 期間使用者選擇取消這組按鈕 | ✓ Validated (Phase 3 UAT) |
| Hotfix 06 — Option A raster overlay(取代 per-artefact white covers) | 1742 per-artefact covers 的 union 重現 dCt logo,re-color attack 可還原;單一 image XObject 無 per-stroke 攻擊面 | ✓ Validated (LIVE-UAT 2026-05-27 LogoSwap (2)) |
| Hotfix 06 / 接受 zero-area sources 仍在 content stream(Option A) | PyMuPDF API 限制無法刪零面積;Option A overlay 對使用者實質不可恢復,符合 v1 內網威脅模型;真正刪除留待 Option B(對外公開時) | ✓ Validated (T-02-07 mitigation,SECURED 5/5) |
| **Hotfix v1.1 — Option B 落地**(content-stream surgery 真正刪除 page-level 零面積 type='f' sources) | 2026-05-28 forensic attack script 實測推翻 v1.0 deferral 的核心假設「Option A overlay 對使用者實質不可恢復」 — Illustrator/Acrobat Pro 級工具可直接拔掉 image XObject overlay 讓底層零面積 CAD-glyph 供應商商標重現(攻擊產物見 `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/`)。因此把 Option B 從 Deferred 升格落地:在 `apply_redactions` 後、Option A overlay 前直接 rewrite page-level content stream 真正刪除零面積 source,overlay 退為 form-XObject 殘留(SEC-03 已 log)+ regex-miss fail-safe 的 last-mile 防線 | ✓ Validated (Phase 7,T-06-01 + T-02-07 CLOSED via Option B;baseline 338 passed + 3 skipped + 0 xfailed) |
| **Hotfix 階段堅守 minimum-change + sufficient-testing**(5330290 教訓) | 5330290 第二輪 push 一次修 9 個 nice-to-have findings(WR/IN polish)觸發 production-only silent fail。Tests passing locally ≠ production safe,跨 module 邊界 + assertion + logging 改動疊在已穩定的修法上會放大 surface area | ⚠️ Revisit — 對任何 hotfix flow 都要套用;nice-to-have polish 應該分開 commit 或留到下個 maintenance sprint |
| Hotfix 07 — UI loader 包住 result-image swap | 套用變更後瀏覽器 `<img>` 繼續顯示舊圖直到新 fetch 完成,使用者誤以為套用沒生效;`showPageLoader(true/false)` 包住 src swap | ✓ Validated (LIVE-UAT 2026-05-27) |
| Hotfix 07 — apply-fail 訊息建議「重新開啟檔案」 | 使用者經驗顯示重開檔常解決 session-state 問題;4 條 COPY 訊息加 escalation path,downloadFailed 維持不變(避免丟失 work copy) | ✓ Validated (LIVE 2026-05-27;真實 LIVE 觸發等下次自然發生) |
| `revert + cherry-pick` 比 `git reset --hard + force push` 更安全(5330290 recovery) | 保留 history;砍掉的失敗 commits 仍在 git log 可審計;不破壞遠端 | ✓ Validated (e5700e5 revert + 0a2fa99..724253a cherry-pick) |
| **Phase 6 — pure test+doc phase 可在不動 production code 下立紅燈基線** | 沒動 `app/**/*.py` 任一行就交付:`tests/fixtures/cad-glyph/` 3 個 real-supplier sanitized fixture、`tests/_illustrator_attack.py` 共用 helper、`tests/test_illustrator_attack_regression.py` 3 個 `xfail(strict=True)` 紅燈、`06-SECURITY.md` 加入 Illustrator-class editor actor。Phase 7 落地 Option B 後 XPASS(strict) 強迫拔 marker = 自動 handoff signal | ✓ Validated (Phase 6 三道閘全綠 2026-05-28) |
| **Sanitize fixture 4-tier fallback chain(Impl notes A → B → C → D)** | A:brand-glyph `q...Q` content-stream block strip;B:latin-1 content-stream find-replace;C(新)`add_redact_annot + apply_redactions(text=PDF_REDACT_TEXT_REMOVE)` glyph-level redaction 處理 CMap-encoded 字型;D(新)`page.delete_annot()` 整塊刪除 Form-XObject stamp annotation。PScript5 + Acrobat Distiller 出口的 PDF 把 supplier 名放在 stamp annotation 的 appearance stream 內(SEC-03 巢狀場景),A/B 抓不到、C 抓不到、D 才能處理 | ✓ Validated (commit 0045c6b;3013A-36A + B-3012IP fixture 升級成功 2026-05-28) |
| **`tests/fixtures/cad-glyph/` 是 conftest「never commit binary」convention 的唯一例外** | v1.1 SEC-03 + Illustrator-class threat model 需要對真實 supplier CAD PDF 跑 regression test;真實 PDF 帶的 corner cases(PScript5 quirk、CMap encoding、Form-XObject stamp、零面積 type='f' 密度梯度)是 in-memory `_build_pdf` 漏掉的;受控例外 + sanitize_fixture.py self-asserts + AGPL §13 README 文件化是合理 trade-off | ✓ Validated (Phase 6 close 2026-05-28) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-28 — Milestone v1.1 started(Illustrator-class threat model + Option B content-stream surgery)。前次更新 2026-05-24 Phase 5 完成 + LIVE 上線(milestone v1.0 完整交付)。*
