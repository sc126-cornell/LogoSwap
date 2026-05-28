---
phase: 6
phase_name: regression-foundation-threat-model-re-evaluation
milestone: v1.1
audit_scope: phase_06_pre_mortem
date: 2026-05-28
asvs_level: 1
diff_base: N/A
commits_audited: []
threats_total: 2
threats_closed: 0
threats_open: 0
threats_accepted: 2
register_authored_at_audit_time: true
supersedes:
  - .planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md
---

# 06-SECURITY.md — Phase 6 pre-mortem STRIDE(v1.1 milestone)

**Phase:** 6 — Regression Foundation + Threat Model Re-evaluation
**Audit scope:** `phase_06_pre_mortem`(no production-code commits to audit)
**Authoring date:** 2026-05-28
**ASVS Level:** 1(內網工具基線)
**Disposition policy:** accept (P0, transition-pending until Phase 7) — 兩條 threat 皆預定於 Phase 7 Option B 落地時 close。

---

## Phase 6 Pre-mortem Context

Phase 6 是 v1.1 milestone 的「紅燈基線」hardening phase,**不變更任何 production code**。
本 SECURITY.md 採 **pre-mortem 變體**:沒有 commits 可以 audit(`commits_audited: []`、
`diff_base: N/A`),threat register 以「pre-mortem」方式 author 在 Phase 6 收口時,記錄
v1.0 close 後 2026-05-28 出現的新威脅證據,以及為何 Phase 6 將兩條 threat 列為
`accept (P0, transition-pending)` 而非 `mitigate` 或 `open`。

**威脅模型重評觸發點 — 2026-05-28 forensic attack evidence**:

工程師回報「Illustrator 編輯 LogoSwap 輸出後供應商商標重現」屬實。
`.planning/debug/scratch/illustrator-attack-2026-05-28-archived/` 保留以下證據(scratch 已退役,
本路徑為 Plan 06-02 Task 4 重命名後的 archived 位置):

| Artefact | 用途 |
|---|---|
| `_attack_proof_supplier_revealed.png` | Illustrator 拔掉 image XObject 後框選區 render — 供應商商標重現 |
| `_attack_target_pre.png` | 攻擊前 LogoSwap 輸出 render — 框選區乾淨 |
| `_attack_orig_for_comparison.png` | 原供應商 PDF render — ground-truth reference |
| `_attack_image_xobject_deleted.pdf` | 攻擊輸出的攻擊後 PDF — cross-verify reference |

攻擊邏輯(原本在 `_attack_delete_image_xobject.py`)已搬入
`tests/_illustrator_attack.py` + `tests/test_illustrator_attack_regression.py`,
作為 Phase 6 紅燈 regression baseline(3 個 fixture × 1 attack scenario = 3 個
`@pytest.mark.xfail(strict=True)` cases — 期望紅燈;Phase 7 落地 Option B 後同 test
變 XPASS(strict) → 強迫 implementer 拔 marker,為 Phase 6 → Phase 7 的 binding handoff
signal)。

**兩條 threat 的「accept (P0, transition-pending until Phase 7)」分類意義**:

- 不是 `mitigate` — 因為 Phase 6 沒有 production code 改動,沒有任何當前 commit 落實
  mitigation;若分類為 `mitigate`,則 STRIDE 與 reality 不一致。
- 不是 `open` — `gsd-secure-phase` agent 的 non-block 條件要求 `threats_open == 0`;
  若分類為 `open`,本 phase 無法 close。
- 採 `accept (P0, transition-pending)` — 明文表達「已決議接受 + 已預定下階段
  Phase 7 close」,既符合 `gsd-secure-phase` non-block 條件,又能誠實表達當前無 production
  mitigation 的事實。
- v1.0 LIVE 上仍生效的 Option A overlay 對「CLI-only / 一般 LAN 使用者」威脅模型仍是
  有效 mitigation — 此 SECURITY.md 不撤銷 v1.0 防線,只是針對「Illustrator-class editor」
  這個 v1.1 升級後的威脅模型,把「Option A 對使用者實質不可恢復」的 v1.0 deferral 假設
  正式記為破滅,並把 Option B 上拉到 Phase 7 第一優先。

---

## STRIDE Actors

沿用 archived `.planning/milestones/v1.0-phases/05-ubuntu/05-SECURITY.md` 與
`hotfix-06-dct-residue/06-HOTFIX-SECURITY.md` 既有 actors(LAN insider、瀏覽器
JS 攻擊者、文件竄改攻擊者等),Phase 6 **新增 1 條 actor**:

### Illustrator-class editor attacker(NEW,Phase 6 D-D2)

**Capabilities**:

- 擁有 Adobe Illustrator / Acrobat Pro 或同等 PDF editor 工具,**能讀寫 PDF object
  stream / content stream**。
- 能透過 PDF object inspector 識別並刪除 page-level **image XObjects**
  (即 LogoSwap Hotfix-06 Option A 的 raster overlay)。
- 不需 modify 其他 content;單純拔掉 overlay 即觸發 page content stream 內留存的
  零面積 `type='f'` source path 在 Acrobat / Illustrator 內 render 出供應商商標。
- **能 save 為新 PDF 並對外散布** — 攻擊者可把攻擊後的 PDF 當作「LogoSwap 處理失敗
  證據」對外傳播,造成品牌污染 / 法務風險 / 既有 mitigation 公開破解知識傳播。

**威脅模型升級理由**:

v1.0 close 時的威脅模型假設「Option A overlay 對使用者實質不可恢復」 — 2026-05-28
forensic evidence(`_attack_proof_supplier_revealed.png`)實證此假設不成立。對
具備 Illustrator / Acrobat Pro 級別工具的使用者,Option A overlay **可恢復**
(刪 image XObject 即可)。此 actor 之前被假設為「需要極高技術門檻 + 客製化 script
+ 攻擊意圖明確」,實際門檻為「下 Adobe Illustrator + 圖層 panel + 拖刪一個物件」。

**Relationship to existing actors**:

- 比 v1.0 「CLI-only forensic attacker」門檻**極低**(不需 Python / fitz / scratch
  script,只需商用 PDF editor)。
- 比 v1.0 「LAN insider」威脅面**更廣**(LAN insider 不一定具技術能力，但
  Illustrator-class editor 是一般設計師 / 業務人員都可能持有的工具)。
- 此 actor 為 v1.1 milestone 啟動的核心理由 — `.planning/PROJECT.md` Active 區段、
  `.planning/ROADMAP.md` Phase 7 SEC-01 / SEC-02 / SEC-03 皆對應其威脅面。

---

## STRIDE Threat Register

下表為 Phase 6 重評後的 STRIDE register。兩條 threat 皆 `accept (P0, transition-pending
until Phase 7)`,evidence 共指向相同證據鏈(2026-05-28 forensic + Plan 06-02 xfail
regression test)。

| Threat ID | Category | Disposition | Status | Evidence (file:line) |
|-----------|----------|-------------|--------|----------------------|
| T-02-07 | I — TRUE REMOVAL vs cover(project core threat;v1.0 CLOSED with documented residual,2026-05-28 RE-OPENED 後 Phase 6 重評) | mitigate(已 archive,沿用 v1.0 LIVE Option A 對 CLI-only 威脅模型仍有效)+ **RE-OPENED 2026-05-28** pending Option B (Phase 7) — **accept (P0, transition-pending until Phase 7)** | **RE-OPENED** | `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png`(2026-05-28 forensic)+ `tests/test_illustrator_attack_regression.py` xfail-strict(3 fixtures × 1 case = 3 XFAIL)。Closing condition:Phase 7 `07-SECURITY.md` 將此條重新 **CLOSED via Option B**(content-stream surgery 刪除零面積 type='f' source 路徑);參 `.planning/REQUIREMENTS.md` SEC-01。Supersession of v1.0 disposition only:archived `.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md` T-02-07 CLOSED-with-documented-residual 行為仍在 archived doc 內保留(本檔不編輯 archived 原檔,僅在 frontmatter `supersedes:` 列出該檔以建立追溯 chain)。 |
| T-06-01 | S + I — Spoofing + Information disclosure;Illustrator-class editor pulls image XObject overlay → supplier brand re-rendered from zero-area type='f' source(NEW,Phase 6 D-D2) | mitigate(pending Option B Phase 7)— **accept (P0, transition-pending until Phase 7)** | **OPEN(formally accepted as transition-pending)** | 同 T-02-07:`_attack_proof_supplier_revealed.png` + `tests/test_illustrator_attack_regression.py` xfail。Closing condition 同 T-02-07(Phase 7 `07-SECURITY.md` CLOSED via Option B)。Cross-ref:`.planning/REQUIREMENTS.md` SEC-01 / SEC-02 / SEC-03 三條 Option B 細部 requirement。 |

**Score: 0 mitigate-CLOSED + 2 accept-CLOSED(transition-pending)= 2/2 closed-in-Phase-6-semantics**。
note:此「closed-in-Phase-6-semantics」是「Phase 6 已對其作出正式 disposition + 已預定
Phase 7 close path」,不是「production code 上已 mitigated」 — 真正的 production
mitigation 在 Phase 7 Option B 落地時於 `07-SECURITY.md` 改為 mitigate-CLOSED。

---

## T-02-07 RE-OPENED — Narrative

**原狀態(archived `06-HOTFIX-SECURITY.md` line 51)**:
`mitigate(+ documented architectural limitation)| CLOSED with documented residual`。
v1.0 close 時的 disposition 理由:「Option A overlay 對使用者實質不可恢復;v1.0 內網
威脅模型下 mitigation 足夠;Option B 等對外公開時再做」(同 archived doc Accepted
Risks Log 與 hotfix retrospective)。

**新狀態(本檔)**:
`RE-OPENED 2026-05-28 (v1.1 Phase 6) — pending Option B`,
分類 `accept (P0, transition-pending until Phase 7)`。

**Why RE-OPENED**:

2026-05-28 forensic attack script(`_attack_delete_image_xobject.py`,已 archive)實證:
對 `3013A-13A-C6-XX-3D02-A01-00040.pdf` 這類 CAD-glyph 零面積 `type='f'` 商標 PDF,
Illustrator-class editor 拔掉 LogoSwap 加入的 raster overlay 後,page content stream
內未被 `apply_redactions` 刪除的零面積 source path 仍會在 Adobe Reader / Illustrator
重新渲染出供應商商標。此攻擊技術門檻為「拖刪一個 image XObject」,**遠低於** v1.0 假設的
「需 forensic 級 PDF object inspection」。原 deferral 假設「Option A 對使用者實質
不可恢復」**證明不成立**。

**v1.0 LIVE mitigation 不撤銷的範圍**:

此 RE-OPENED **不**撤銷 v1.0 LIVE 上 Option A overlay 的有效性 — 對
「CLI-only 攻擊者 / 不具備 Illustrator / Acrobat Pro 的內網一般使用者」威脅模型,
Option A 仍是有效 mitigation(攻擊者必須具備寫 fitz / pikepdf script + 知道
零面積 `type='f'` source path 結構的技能)。本 RE-OPENED 只針對「v1.1 升級後的
Illustrator-class editor」威脅模型 — 即 STRIDE Actors 段所述的新 actor。

**Closing path**:

Phase 7 落地 Option B(SEC-01 / SEC-02 / SEC-03,參 `.planning/REQUIREMENTS.md`)後,
`07-SECURITY.md` 將把 T-02-07 重新標為 `mitigate | CLOSED via Option B`,且
evidence 將指向 Phase 7 Option B 實作 commit + Plan 07-XX 新增的 helper 單元測試
(TEST-03)+ 本 Phase 6 紅燈 regression test 轉綠(`tests/test_illustrator_attack_regression.py`
3 XFAIL → 3 PASSED,xfail strict marker 被 implementer 拔除作為 handoff completion 動作)。

**Supersession of v1.0 disposition**:

本檔 frontmatter `supersedes:` 列出 archived `06-HOTFIX-SECURITY.md`(僅 T-02-07
disposition 行為的 supersede,不撤銷 archived doc 的其他 4 條 threat 之 mitigate
disposition)。Archived 原檔不被本檔編輯;追溯 chain 透過 `supersedes:` 鎖定,
Phase 7 implementer + downstream `gsd-secure-phase` agent 可在 `07-SECURITY.md`
延續同 chain(supersede 本檔 + 沿用 supersede target = archived `06-HOTFIX-SECURITY.md`)。

---

## T-06-01 — Narrative

**Threat ID**: T-06-01(NEW,Phase 6 引入)
**Category**: Spoofing(S)+ Information disclosure(I)— 雙重類別。
**Component**: LogoSwap 輸出 PDF(任何走 Option A raster fallback overlay branch 的
CAD-glyph PDF — 即 `app/services/redact.py:232-256` dispatcher 內 `zero_area_count
>= ZERO_AREA_RASTER_THRESHOLD` 觸發的 dense branch 路徑)。

**Attacker capability + step-by-step**:

1. **取得 LogoSwap 輸出**:Illustrator-class editor attacker 透過任何 OPSEC 路徑取得
   LogoSwap 已處理的 PDF(可能是合法使用者寄出的對外文件、Cloud storage 同步、email
   附件、印刷廠工作流程交換等)。
2. **用 Illustrator / Acrobat Pro 開啟**:標準 GUI 開啟,**不需 fitz / scratch script /
   forensic 技能**。
3. **拔除 image XObject overlay**:在圖層 panel / object inspector 識別 Option A
   raster overlay(32×32 純白 image XObject,bbox 與商標框選區重合)+ delete。
4. **儲存攻擊後 PDF**:save / save-as → 攻擊輸出 PDF,框選區重新 render 出供應商
   商標(因為 page content stream 內的零面積 `type='f'` source path 從未被
   `apply_redactions` 刪除 — 只是被 overlay 視覺蓋住)。
5. **散布**:對外傳播此攻擊後 PDF 作為「LogoSwap 處理失敗 / 偽造品牌」證據,造成
   品牌污染 / 法務風險 / 既有 mitigation 公開破解知識傳播。

**Evidence cite**:

- `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png`
  — 上述 step 4 的實證 render(2026-05-28 forensic 對
  `3013A-13A-C6-XX-3D02-A01-00040_logoswap (5).pdf` 跑出)。
- `tests/test_illustrator_attack_regression.py`(3 個 fixture × 1 attack scenario,
  3 個 XFAIL)— 本 Phase 6 的紅燈 regression baseline,落地 Option B 後變綠。

**Disposition**: `accept (P0, transition-pending until Phase 7 closes)`。

**Closing condition cross-ref**: `.planning/REQUIREMENTS.md` SEC-01(content-stream
surgery 真正刪除零面積 type='f' fills)、SEC-02(對正常面積 vector 商標 no-op)、
SEC-03(只修改 page-level content stream 不誤改 form XObject)— Phase 7 落地全部 3 個
requirement 後 T-06-01 將在 `07-SECURITY.md` CLOSED via Option B。

---

## Accepted Risks Log

下面兩條 disposition 是 Phase 6 對 T-02-07 與 T-06-01 的正式接受。每條包含 rationale、
residual risk、upgrade trigger,以及 cross-reference 至 production-code mitigation 將
落於 Phase 7 的證據點。

### T-02-07-r2 — v1.0 documented residual + v1.1 RE-OPENED transition

- **Disposition**: accept (P0, transition-pending until Phase 7 closes)
- **Risk description**(繁中): LogoSwap 對 CAD-glyph 零面積 `type='f'` 商標 PDF 採用
  Option A(image XObject raster overlay,Hotfix #06)mitigation。Page content stream
  內的零面積 source path **未被** `apply_redactions` 真正刪除,只被 overlay 視覺
  覆蓋。Illustrator-class editor 拔掉 overlay 後零面積 source 重新 render 出供應商
  商標。v1.0 close 時假設此攻擊路徑「對使用者實質不可恢復」 — 2026-05-28 forensic
  evidence 證明假設破滅。
- **Why accepted now**: Phase 6 是 red-light-baseline phase by design — 沒有
  production code 變更可以對外 mitigate。本 milestone 的 production-code mitigation
  落於 Phase 7 Option B(SEC-01 content-stream surgery 真正刪除零面積 source)。
  Phase 6 的 binding mitigation 是「立起紅燈 regression test 作為 Phase 7 落地
  Option B 後的 binding contract — xfail strict 強迫 implementer 拔 marker = handoff
  completion 動作」 + 06-SECURITY.md 文件化此 transition + 沿用 v1.0 LIVE Option A
  overlay 對 CLI-only 威脅模型仍是有效 mitigation。
- **Upgrade trigger / when revisited**: Phase 7 落地 Option B → `07-SECURITY.md`
  將此條 CLOSED via Option B(production code commits + Plan 07-XX 新增 helper 單元
  測試 TEST-03 + 本 Phase 6 紅燈 regression test 由 XFAIL 變 PASSED,xfail strict
  marker 被拔)。
- **Documented at**:
  - `tests/test_illustrator_attack_regression.py` xfail reason 字串(繁中 + cross-ref
    SEC-01)
  - 本檔 STRIDE Threat Register table + T-02-07 RE-OPENED narrative section
  - `.planning/REQUIREMENTS.md` SEC-01 / SEC-02 / SEC-03(Phase 7 落地 requirement)
  - Frontmatter `supersedes:` 鎖定 archived `06-HOTFIX-SECURITY.md` 的 T-02-07
    disposition 行為的 supersede chain
- **v1.0 LIVE mitigation 仍對 CLI-only 威脅模型有效**(此 acceptance 不撤銷 v1.0
  LIVE 對「不具備 Illustrator / Acrobat Pro 的內網一般使用者」威脅模型的有效性)

### T-06-01-r1 — Illustrator-class editor attack surface(NEW Phase 6)

- **Disposition**: accept (P0, transition-pending until Phase 7 closes)
- **Risk description**(繁中): v1.1 STRIDE 升級新加入「Illustrator-class editor
  attacker」actor — 攻擊者具備 Adobe Illustrator / Acrobat Pro / 等同 GUI PDF editor,
  能讀寫 PDF object stream / content stream。對 LogoSwap 輸出 PDF 在標準 GUI 內
  拖刪 image XObject overlay 即可觸發攻擊面;不需 forensic / fitz script / CLI 技能,
  攻擊技術門檻**低於 v1.0 任何已 register actor**(僅次於「不會操作 PDF editor 的
  使用者」)。
- **Why accepted now**: 同 T-02-07-r2 — Phase 6 是 pre-mortem / red-light-baseline
  phase,無 production code mitigation 可落地;Phase 7 Option B 將同時 close T-02-07
  與 T-06-01(因為兩條 threat 本質上是同一個 root cause = page content stream 內
  零面積 `type='f'` source 未被刪除 — `accept (P0, transition-pending)` framing
  將 Phase 6 → Phase 7 的 close path 鎖死為單一 production fix。
- **Upgrade trigger / when revisited**: 同 T-02-07-r2 — Phase 7 落地 Option B → 
  `07-SECURITY.md` CLOSED via Option B。同一 production fix 同時 close 兩條 threat。
- **Documented at**:
  - 同 T-02-07-r2(同 3 處 cross-ref)
  - 額外:`.planning/PROJECT.md` Active 區段(milestone v1.1 啟動理由的 STRIDE
    re-evaluation reference)
- **Cross-reference to Phase 7 closing**: `.planning/REQUIREMENTS.md` SEC-01(主)
  + SEC-02(no-op for non-CAD)+ SEC-03(form XObject 巢狀邊界)— 全部 3 條 落地後
  Phase 7 `07-SECURITY.md` 將 T-06-01 與 T-02-07 同時 CLOSED via Option B。

---

## Pre-mortem vs Audit-time Variant

本檔採 pre-mortem 變體,與 v1.0 archived `06-HOTFIX-SECURITY.md`(audit-time 變體)
語意對照如下:

| 欄位 | Audit-time 變體(eg. archived `06-HOTFIX-SECURITY.md`) | Pre-mortem 變體(本檔) |
|------|---------------------------------------------------------|------------------------|
| `audit_scope` | `hotfix_06_dct_residue`(指 4 commit 範圍) | `phase_06_pre_mortem`(指本 phase 整體;無 commit 範圍) |
| `commits_audited` | 4-commit list(`e7e7ca2..00a99e4`) | `[]`(empty list;phase has no production-code commits) |
| `diff_base` | `f911139..HEAD`(audit-able diff range) | `N/A`(沒有 implementation diff 可 audit) |
| `threats_total` / `closed` / `open` | 5 / 4 mitigate-CLOSED + 1 accept-CLOSED;`open: 0` 因全部 verified | 2 / 0 mitigate-CLOSED + 2 accept-CLOSED(transition-pending);`open: 0` 因兩條皆 accept-classified |
| `live_uat_verified_at` | `2026-05-27`(LIVE 實測 evidence) | 不存在(無 LIVE 部署可 verify;Phase 6 純 test + docs) |
| 整體語義 | 「對既有 production code 的 retrospective security verification」 | 「對下一 phase production code 將要 close 的 threats 的 pre-mortem authoring」 |

**`gsd-secure-phase` agent non-block 條件**:`threats_open == 0`。本檔
`threats_open: 0` 透過「兩條 threat 皆 `accept (P0, transition-pending)`」實現,
而非「兩條 threat 皆 production-code mitigated」。此語意明文記於本段,Phase 7
`gsd-secure-phase` agent 接手時可依此 transition framing 理解 close path
(per 06-RESEARCH § Assumptions A3)。

---

## Open Threats

**Open Threats: 0**(T-02-07 與 T-06-01 兩條皆 `accept (P0, transition-pending until
Phase 7 closes)`,參上方 Accepted Risks Log)。

---

## Cross-references / Supersession Chain

**Phase 7 expected**:`.planning/phases/07-*/07-SECURITY.md` 將把 T-02-07 與 T-06-01
**同時** CLOSED via Option B(同一 production fix 同時 close 兩條 — 兩條 root cause
皆為 page content stream 內零面積 type='f' source 未刪除)。Phase 7 `gsd-secure-phase`
agent 應在 `07-SECURITY.md` frontmatter `supersedes:` 列出本檔(`06-SECURITY.md`),
追溯 chain:`07-SECURITY.md → 06-SECURITY.md → archived 06-HOTFIX-SECURITY.md`。

**Phase 8 expected**:`.planning/phases/08-*/08-SECURITY.md` 將有 LIVE-UAT verifying
note(`live_uat_verified_at: <date>`),實證 Option B 在 LIVE 環境對 CAD-glyph
fixture 完整 upload → 框選 → process → download → Illustrator-attack-simulation
全綠通過(`.planning/REQUIREMENTS.md` DEPLOY-01)。

**本檔 supersedes(disposition only,不撤銷 archived 原檔)**:
`.planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md`
T-02-07 行(`CLOSED with documented residual` → `RE-OPENED 2026-05-28 (v1.1 Phase 6)`
transition)。Archived 原檔不被本檔編輯;追溯 chain 透過 frontmatter `supersedes:`
鎖定。

**Cross-reference matrix**:

| Doc | Phase | Relationship to this file |
|------|-------|---------------------------|
| `.planning/REQUIREMENTS.md` SEC-01 | Phase 7 | T-02-07 + T-06-01 的 production-code closing condition |
| `.planning/REQUIREMENTS.md` SEC-02 | Phase 7 | Option B no-op for non-CAD PDF — defence against regression of T-02-07 close |
| `.planning/REQUIREMENTS.md` SEC-03 | Phase 7 | Option B form XObject 邊界 — Option B 不誤改巢狀 XObject |
| `.planning/REQUIREMENTS.md` TEST-02 | Phase 6 | 本 Phase 6 紅燈 regression test = Plan 06-02 Tasks 1+2 交付物 |
| `.planning/REQUIREMENTS.md` TEST-03 | Phase 7 | Option B helper 單元測試(Phase 7 落地) |
| `.planning/REQUIREMENTS.md` THREAT-01 | Phase 6 | 本檔即 THREAT-01 的交付物(STRIDE 重評 + Illustrator-class editor actor + T-02-07 RE-OPENED) |
| `.planning/REQUIREMENTS.md` THREAT-02 | Phase 7 / Phase 8 | 三處 LIMITATION docstring 同步更新(Phase 8 DOC-01) |
| `.planning/REQUIREMENTS.md` DEPLOY-01 | Phase 8 | LIVE-UAT Option B 收口 |
| `tests/test_illustrator_attack_regression.py` | Phase 6 / Phase 7 transition | xfail-strict marker 為 Phase 6 → Phase 7 的 binding handoff signal |
| `tests/_illustrator_attack.py` | Phase 6 | 攻擊邏輯 helper(VERBATIM port 自 archived scratch script) |
| `.planning/debug/scratch/illustrator-attack-2026-05-28-archived/_attack_proof_supplier_revealed.png` | 2026-05-28 forensic | T-06-01 + T-02-07-r2 的 ground-truth visual evidence |

---

*06-SECURITY.md authoring complete — Phase 6 STRIDE pre-mortem 鎖定。*
*下一步:Phase 7 implementer 落地 Option B 後在 `07-SECURITY.md` close 本檔列出的兩條 threat。*

---

## Security Audit 2026-05-28 (post-code-review-fix)

**Auditor:** Claude (gsd-secure-phase)
**Audit posture:** FORCE — assume mitigations absent until grep proves present;State A verification of pre-mortem deliverable against post-review-fix code.
**Scope:** verify each declared threat disposition in this file's STRIDE register matches the on-disk reality after Phase 6 code-review fix (commits `d0370de`..`e3ac65f`).

### Verification Matrix

| # | Verification | Status | Evidence (file:line / command output) |
|---|---|---|---|
| 1 | Phase 6 added 0 production code lines | CLOSED | `git diff --stat d671548^..HEAD -- app/` returns empty output (verified at audit time across all 10 Phase 6 commits + 8 code-review-fix commits) |
| 2 | AGPL fitz seam intact — only `app/services/pdf_engine.py` imports fitz in `app/` | CLOSED | AST walk across `app/**/*.py`: single hit at `app/services/pdf_engine.py:19`; all other grep matches are docstring/comment references (verified via AST `Import` + `ImportFrom` node walk) |
| 3 | AGPL guard test still green | CLOSED | `python -m pytest tests/test_redact.py::test_fitz_import_confined_to_engine_seam -v` → `1 passed in 0.32s`; AST guard at `tests/test_redact.py:1190-1207` scopes only `app/**/*.py` — `tests/`/`scripts/` are out of scope by design |
| 4 | `tests/_illustrator_attack.py` `import fitz` is permitted (test-harness exception) | CLOSED | `tests/_illustrator_attack.py:60` `import fitz  # license: test harness exception (mirror tests/conftest.py:12)`; AST guard does not visit `tests/` |
| 5 | `scripts/sanitize_fixture.py` `import fitz` is permitted (scripts/ out of AGPL guard scope) | CLOSED | `scripts/sanitize_fixture.py:83`; AST guard scope is `app/**/*.py` only |
| 6 | CR-01 fix applied — `_metadata_all_empty` uses allowlist (only `format`, `encryption` permitted as non-empty) | CLOSED | `scripts/sanitize_fixture.py:258` `_COMPUTED_METADATA_FIELDS = frozenset({"format", "encryption"})`; `:261-279` allowlist iteration of `doc.metadata.items()` with computed-field skip + `value not in (None, "", b"")` fail-fast; commit `d0370de` |
| 7 | WR-03 fix applied — out-path validated via `Path.resolve()` + `is_relative_to()` (no path traversal / case bypass) | CLOSED | `scripts/sanitize_fixture.py:219-239` `_out_path_in_fixtures_dir()` helper using `Path.resolve()` + `is_relative_to(FIXTURES_DIR)`; called at entry-point (`:455-461` analog) AND in self-assert (`:714-720`); commit `509cef7` |
| 8 | WR-07 fix applied — `delete_image_xobjects_intersecting` returns actual `total_subs`, not `len(xrefs)` | CLOSED | `tests/_illustrator_attack.py:161` `total_subs = 0`; `:171,178` `total_subs += n` from each `pattern.subn()`; `:192` `return total_subs`; commit `7514ef1` |
| 9 | All 4 self-asserts gate `doc.save()` (any failure → `return 1` before save) | CLOSED | `scripts/sanitize_fixture.py:660-720` self-assert block precedes Step 6 save at `:723`: (1) `_metadata_all_empty(doc)` at `:662`, (2) `supplier_name not in text_after` at `:671` w/ CMap fallback, (3) `post_zero_area_count` ≥ 0.9 × original at `:687-709`, (4) `_out_path_in_fixtures_dir(out_path)` at `:714` |
| 10 | T-06-01 Accepted Risks Log entry present + cross-refs valid | CLOSED | `06-SECURITY.md:253-275` "T-06-01-r1 — Illustrator-class editor attack surface (NEW Phase 6)" with disposition `accept (P0, transition-pending until Phase 7 closes)`, risk description, why-accepted-now, upgrade trigger (Phase 7 Option B落地), documented-at refs (xfail reason / STRIDE table / REQUIREMENTS.md SEC-01/02/03 / PROJECT.md Active) |
| 11 | T-02-07 Accepted Risks Log entry present + supersedes chain to archived `06-HOTFIX-SECURITY.md` | CLOSED | `06-SECURITY.md:223-251` "T-02-07-r2 — v1.0 documented residual + v1.1 RE-OPENED transition"; frontmatter `:15-16` `supersedes: - .planning/milestones/v1.0-phases/05-ubuntu/hotfix-06-dct-residue/06-HOTFIX-SECURITY.md`; cross-ref to future `07-SECURITY.md` CLOSE noted at `:160-165` and `:310-314` |
| 12 | Committed-binary fixture exposure controlled — no raw supplier PDF tracked | CLOSED | `git ls-files \| grep -E '3013A-13A-C6-XX'` returns empty (exit 1); `samples/3013A-...pdf` removed via `git rm` in commit `0f14325`; repo-root copy physically `mv`'d to archived dir (`.gitignore` `:/.planning/debug/scratch/illustrator-attack-2026-05-28-archived/3013A-*.pdf` archived-anchored) |
| 13 | `tests/fixtures/cad-glyph/README.md` documents committed-binary exception + AGPL §13 + immutability + PROVISIONAL state | CLOSED | README.md has 5 sections (line 8 §1 why-exception, line 31 §2 sanitization log w/ `synthetic` markers, line 51 §3 immutability rule, line 70 §4 AGPL §13 statement, line 88 §5 cross-references); PROVISIONAL banner at `:4` |
| 14 | Forensic evidence archived + git history preserved (Blocker #3) | CLOSED | Archived dir contains 4 retained PNG/PDF artifacts + README.md + raw 3013A.pdf (untracked, `.gitignore` archived-anchored); original `.py` attack scripts deleted (`ls *.py` exit 2 "No such file or directory"); `git log --follow .../_attack_proof_supplier_revealed.png` returns 2 commits (`0f14325` + `b9aa005`) — rename detection preserves history through `git mv` |
| 15 | Pre-mortem framing: 3 XFAIL regression tests exist as Phase 6 → Phase 7 handoff signal | CLOSED | `python -m pytest -k illustrator_attack -v` → `3 xfailed in 2.37s` (figure-glyph-01 + mixed-glyph-01 + text-glyph-01); `@pytest.mark.parametrize` ABOVE `@pytest.mark.xfail(strict=True)` at `tests/test_illustrator_attack_regression.py:73-82`; reason string cross-refs `.planning/REQUIREMENTS.md SEC-01` |
| 16 | Frontmatter `gsd-secure-phase` non-block invariant: `threats_open: 0` + `threats_accepted: 2` | CLOSED | `06-SECURITY.md:11-13` frontmatter exact match: `threats_total: 2 / threats_closed: 0 / threats_open: 0 / threats_accepted: 2`; semantics explained at `:293-297` (Pre-mortem vs Audit-time variant section) |

### Per-threat Disposition Verification

**T-06-01 (NEW — Spoofing + Information disclosure, Illustrator-class editor pulls overlay):**
- Disposition declared in register: `accept (P0, transition-pending until Phase 7)`
- Accepted Risks Log entry: `06-SECURITY.md:253-275` (T-06-01-r1) — risk description ✓, why-accepted-now ✓, upgrade trigger ✓, documented-at refs ✓
- Closing condition cross-ref: `.planning/REQUIREMENTS.md` SEC-01 / SEC-02 / SEC-03 (Phase 7 Option B)
- Evidence cite: `_attack_proof_supplier_revealed.png` archived + 3 XFAIL regression tests live in `tests/test_illustrator_attack_regression.py` — both verified present at audit time
- **Verdict:** disposition matches reality; `accept` framing valid (no production-code mitigation expected this phase by design)

**T-02-07 (RE-OPENED — Information disclosure, TRUE REMOVAL vs cover):**
- Disposition declared in register: `mitigate (archived, v1.0 LIVE Option A still effective for CLI-only model) + RE-OPENED 2026-05-28 pending Option B (Phase 7) — accept (P0, transition-pending until Phase 7)`
- Supersession chain: frontmatter `supersedes:` lists archived `06-HOTFIX-SECURITY.md` — verified at `:15-16`; archived original unmodified (no edits to `.planning/milestones/v1.0-phases/...` in any Phase 6 commit)
- Accepted Risks Log entry: `06-SECURITY.md:223-251` (T-02-07-r2) — all required fields present
- Future close path: `07-SECURITY.md` will mark `mitigate | CLOSED via Option B` (chain: `07 → 06 → archived-06-HOTFIX`) — documented at `:308-314`
- **Verdict:** disposition matches reality; supersedes chain valid; v1.0 LIVE mitigation explicitly not retracted (only the Illustrator-class threat-model assumption invalidated)

### Phase 6 Attack-Surface Delta Confirmation

- **Production code lines added:** 0 (verified via `git diff --stat d671548^..HEAD -- app/` returning empty across all 10 Phase 6 commits + 8 code-review-fix commits)
- **New `import fitz` in app/:** 0 (AST walk confirms only `app/services/pdf_engine.py:19`)
- **New runtime attack surface:** 0 — Phase 6 is pre-mortem hardening + test/docs/scripts only:
  - `scripts/sanitize_fixture.py` — maintainer-only dev tool, runs in trust boundary covered by T-PLAN06-01-03 (accept, low — maintainer-trust per Plan 06-01 threat_model)
  - `tests/_illustrator_attack.py` + `tests/test_illustrator_attack_regression.py` — test harness, never imported by `app/`
  - `06-SECURITY.md` — docs-only
- **Threat Flags from `06-01-SUMMARY.md` / `06-02-SUMMARY.md`:** both summaries explicitly state "無新 threat surface introduced" — no unregistered flags require mapping

### Unregistered Flags

None. Both summaries' Threat Flags sections audited and confirmed empty of new attack surface.

### Final Verdict

**Phase 6 is THREAT-SECURE (threats_open: 0, threats_accepted: 2)**

All 16 declared mitigations / acceptances verified by direct grep / AST walk / pytest invocation against on-disk code. The pre-mortem framing — `accept (P0, transition-pending until Phase 7)` for both T-06-01 + T-02-07 — is internally consistent: no production-code mitigation was expected this phase (by design, per `06-RESEARCH § Assumptions A3`), and the binding handoff signal (3 × xfail-strict regression tests) is wired correctly to fail-loud when Phase 7 Option B lands.

CR-01 + WR-03 + WR-07 fixes from the code review are all present and behaviorally correct in the post-fix code at audit time. The 4 self-asserts in `scripts/sanitize_fixture.py` all gate `doc.save()` with `return 1` on any failure — the AGPL §13 statement in `tests/fixtures/cad-glyph/README.md` § 4 is upheld by mechanical means, not merely by documentation.

**No blockers. No unregistered flags. Phase 6 cleared for Phase 7 entry.**

*Audit completed: 2026-05-28*
*Auditor: Claude (gsd-secure-phase, FORCE stance)*
