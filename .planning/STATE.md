---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Harden against Illustrator-class attacks on CAD-generated PDFs
status: executing
stopped_at: Phase 8 context gathered
last_updated: "2026-05-28T15:52:01.261Z"
last_activity: 2026-05-28 -- Phase 8 planning complete
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 9
  completed_plans: 5
  percent: 56
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-28 — milestone v1.1 started)

**Core value:** 能乾淨地「移除而非覆蓋」供應商商標圖案與文字,換上我司商標,產出品牌正確的 PDF。
**Current focus:** Phase 7 完成(2026-05-28)— Option B 落地、verify + 三道閘全綠。下一步:`/gsd-discuss-phase 8 --chain`(文件同步 + LIVE 部署)。

## Current Position

Phase: 7 (Option B Implementation — Content-Stream Surgery) — COMPLETE
Plan: 3 of 3(含 07-03 gap-closure)
Status: Ready to execute
Last activity: 2026-05-28 -- Phase 8 planning complete

Progress: [██████████] 100%(2 / 3 phases complete;Phase 8 待跑)

## Accumulated Context

### Decisions

完整決策日誌在 PROJECT.md Key Decisions 表。最近影響當前工作的決策:

- **2026-05-28** v1.1 啟動:Option B 從 v1.0 Deferred 升格為第一優先,因 forensic attack script 證明 deferral 假設「Option A 對使用者實質不可恢復」不成立
- **v1.0 hotfix-06 教訓**:已穩定的修法上「再加 polish」不是免費的 — Phase 7 落地 Option B 時嚴守 minimum-change,nice-to-have polish 分開 commit 或下次 maintenance sprint
- **AGPL seam**:fitz 嚴格限制在 `app/services/pdf_engine.py` — Option B 新 helper 必須在這個檔案內,不可外溢
- [Phase ?]: Sidecar manifest 採 split-coordinate schema(region_rect_pdf_points + region_rect_px),Phase 6 canonical per Warning #8
- [Phase ?]: PyMuPDF 1.27.2.3: doc.set_metadata({}) 為 no-op;必須傳 per-field empty dict 才會真清空 [Rule 1 deviation]
- [Phase ?]: 2/3 Phase 6 fixtures synthetic — Phase 6 close 為 PROVISIONAL until 工程師交付剩餘 supplier PDF **〔已 RESOLVED 2026-05-28:工程師交付 `3013A-36A-C6-W4.pdf` + `B-3012IP-WM02-T430.pdf`,合計 3 個 fixture 全 real;同步引發 sanitize_fixture.py 補強 Impl notes C(CMap font glyph redaction) + D(Form-XObject stamp annotation 整塊刪除) — commit `0045c6b`〕**
- [Phase ?]: Phase 6 Plan 06-02 完成: VERBATIM-port + xfail-strict baseline + pre-mortem STRIDE + scratch retirement
- [Phase ?]: Phase 6 紅燈基線就位: tests/test_illustrator_attack_regression.py 3 個 XFAIL,pytest baseline 升級為 301 passed + 3 skipped + 3 xfailed;Phase 7 落地 Option B 後 xfail strict 強迫拔 marker 為 handoff completion 動作
- [Phase ?]: Phase 6 Plan 06-02: STRIDE 加入 Illustrator-class editor attacker actor;T-02-07 RE-OPENED + T-06-01 NEW 兩條皆 accept (P0 transition-pending until Phase 7);06-SECURITY.md frontmatter threats_open:0 + threats_accepted:2 滿足 gsd-secure-phase non-block
- [Phase ?]: Phase 6 repo phase-level invariant: git ls-files | grep '3013A-13A-C6-XX' returns empty (samples/ raw supplier PDF 已 git rm + repo root 副本物理 mv 到 archived dir);git mv 保住 history follow for forensic PNG/PDF artefacts
- [Phase 6 close 2026-05-28]: Phase 6 三道閘全綠 — code-review/fix 過(1 Critical + 7 Warnings fixed in 8 atomic commits;5 Info 留作 maintenance);validate-phase Nyquist 為 no-op(`workflow.nyquist_validation=false` 配置停用,等效 phase verification 已由 gsd-verifier 完成);secure-phase 為 THREAT-SECURE(threats_open:0/threats_accepted:2,16/16 critical verifications CLOSED)
- [Phase 6 close 2026-05-28]: PROVISIONAL 已移除 — 工程師交付 2 個額外 supplier PDF(`3013A-36A-C6-W4.pdf` + `B-3012IP-WM02-T430.pdf`,同為 `宁波登骐 / Ningbo Dengqi` 供應商不同 SKU)。3/3 fixture 全 real supplier 來源
- [Phase 6 close 2026-05-28]: `scripts/sanitize_fixture.py` 補強 Impl notes C + D(commit `0045c6b`)— C:`add_redact_annot + apply_redactions(text=PDF_REDACT_TEXT_REMOVE)` glyph-level 處理 CMap-encoded font;D:`page.delete_annot()` 整塊刪除 Form-XObject stamp annotation 內含 supplier_name 的 stamp。對未來其他 PScript5 / Acrobat 來源的 PDF 通用
- [Phase 6 close 2026-05-28]: Phase 6 production code 0 改動驗證 — `git diff --stat c27ffea..HEAD -- app/` empty;AGPL seam(`import fitz` 只在 `app/services/pdf_engine.py`)未被本 phase 任何 commit 動到
- [Phase ?]: Phase 7 Plan 01: Option B helpers (delete_zero_area_type_f_fills_inside + log_xobject_intersect) landed in pdf_engine.py AGPL seam + 14 TEST-03 unit tests; baseline 315 passed + 3 skipped + 3 xfailed; Phase 6 regression stays 3 XFAIL for 07-02 handoff
- [Phase ?]: Phase 7 Plan 01 [Rule 1 deviations]: (1) Shape 1/2 byte-range bboxes need page.transformation_matrix — fitz get_drawings reports MuPDF top-left, stream re/m/l operands are PDF bottom-left; (2) _RE_FILL_RECT_RE between-group widened to absorb h + colour ops because PyMuPDF Shape.draw_rect emits re-h-rg-f not adjacent re-f; (3) page.get_xobjects() bbox is plain tuple not fitz.Rect on 1.27.2.3
- [Phase ?]: [Phase 7 Plan 07-02] Option B wiring landed in redact.py (line 195/197 boundary, 2 LOC import + ~15 LOC dispatcher, existing dispatcher 0 deletions); xfail decorator removed. SEC-01 acceptance gate FAILED (3 regression FAIL not PASS) — upstream scope: mixed-glyph 3396-ZAF helper cardinality fail-safe + figure-glyph existing residual_content raise + text-glyph stale attack precondition. Option B proven to truly delete on text-glyph (count 1->0, 99.59% white). Self-Check FAILED; not advancing plan — orchestrator to decide upstream fix.
- [Phase 7 close 2026-05-28]: Plan 07-03 gap-closure 關閉 SEC-01 — Shape 1 locator 改 single-pass `_build_shape1_candidate_index` + bbox-keyed cardinality(perf 765s→1.12s,match 14%→100%);關鍵 root cause 是潛伏的 `_NUMBER` regex bug(`-?\d+\.?\d*` 解不了 PScript5 leading-dot real `-.061`,改 `[-+]?(?:\d+\.?\d*|\.\d+)`);attack precondition 重設計(Option B 已刪 source → 無 overlay 可拔 → region 乾淨仍 PASS);figure-glyph 重 sanitize 自真實 B-3012IP zero-area cluster。3 attack regression PASS。
- [Phase 7 close 2026-05-28]: 三道閘全綠 — (1) verify PASSED 5 criteria + 4 reqs + 10 invariants;(2) code-review/fix:**deep review 抓 1 BLOCKER(CR-01:Shape 1 splice 整個 q...Q block 會過刪夾帶的 `/Fm0 Do` 等合法內容,D-A5 + regression gate 都抓不到)+ 6 WR 全修**(7 atomic commits,修法:`_DISALLOWED_IN_BLOCK` 偵測 Do/BT/sh/BI 夾帶內容就保守跳過 → fail-safe → Option A last-mile);(3) validate Nyquist no-op;(4) secure SECURED threats_open:0,14/15 CLOSED + 1 accept
- [Phase 7 close 2026-05-28]: **T-06-01 + T-02-07 CLOSED via Option B** — content-stream gate 委派 production `count_zero_area_fills_fully_inside`(讀 content stream 非渲染像素),mixed-glyph 3396 ZAF 過 `count==0` 證明真刪非 Option A overlay 視覺遮蓋;兩道閘(white≥98% AND count==0)unconditional asserts。supersede chain 07→06→archived 06-HOTFIX 已鎖
- [Phase 7 close 2026-05-28]: production code 改動只 `pdf_engine.py`(+helpers)+ `redact.py`(+~15 LOC,0 deletions,既有 dispatcher 一字不改);AGPL seam intact(`import fitz` 只 `pdf_engine.py:21`);baseline 338 passed + 3 skipped + 0 xfailed
- [Phase 8 部署提醒 IN-02]: secure audit 環境是 Python 3.14,CLAUDE.md mandate 是 3.12 — Phase 8 LIVE 部署要確認 pin 3.12 維持 regex/logging 行為 parity(非 source defect)

### Pending Todos

無(milestone 啟動初期)。

### Blockers/Concerns

- ~~**TEST-01 需要實際樣本**:工程師需提供 ≥3 個出問題的 supplier CAD-glyph PDF~~ **〔已 RESOLVED 2026-05-28:全 3 個 fixture 為真實 supplier〕**
- [x] ~~**Phase 6 fixture replenishment**~~ **〔已 RESOLVED 2026-05-28:工程師交付 `3013A-36A-C6-W4.pdf` + `B-3012IP-WM02-T430.pdf`,經 `scripts/sanitize_fixture.py`(commit `0045c6b` Impl notes C + D)重跑後,`text-glyph-01.pdf` + `figure-glyph-01.pdf` 升級為 real supplier;Phase 6 PROVISIONAL banner 移除〕**
- Phase 7 Plan 07-02 SEC-01 acceptance gate FAILED: 3 illustrator-attack regression cases fail (not pass). Root cause upstream scope (NOT 07-02 integration bug): mixed-glyph-01 3396-ZAF cardinality fail-safe in 07-01 helper (option_b_parse_anomaly, deletes 0); figure-glyph-01 raises existing residual_content (pre-Option-B Phase 4 behaviour); text-glyph-01 Option B works (count 1 to 0, render 99.59% white) but stale attack precondition (no Option A overlay to pull, N=1 < threshold 100). Per sec_01 acceptance note, did NOT expand 07-02 scope to fix helper/fixture/attack-model. Self-Check FAILED in 07-02-SUMMARY.md.

## Deferred Items

延到未來 milestone 再決定優先級:

| Category | Item | Status | Reason |
|---|---|---|---|
| Integration | `is_raster_fallback_image(page, xref)` getter | Deferred 自 v1.0 | colleague-system integration 出現時再加;HANDOFF.md 已交付 |
| Integration | 嵌入式整合(colleague approval site) | Deferred 自 v1.0 | API base path + iframe-friendly 設計已預留;實際整合需求出現時啟動 |
| Self-doc | `residual_whitepaint` 顯式列入 `_PROCESS_STATUS` | Deferred 自 v1.0 | dict.get fallback 已正確映射 422 |
| UAT | 超大影像錯誤訊息實機驗證(WR-03 megapixel cap UI) | Deferred 自 v1.0 | 自動測試覆蓋 OK,UI 字串待 ≥89MP 真檔 |
| Batch | 多檔批次處理 | Deferred 自 v1.0 | 須引入 task queue(Celery + Redis);v1 採手動單檔互動 |
| Security | Form XObject 內 zero-area fills 遞迴 surgery | Deferred from v1.1 SEC-03 | v1.1 採 page-level only + log;實際樣本出現再評估 |
| Security | Zero-area `type='s'`(stroke)surgery | Deferred from v1.1 | 威脅證據都是 type='f';stroke 未出現殘留 |

**Promoted from Deferred to Active(2026-05-28):**

- ~~Option B — content-stream surgery 真正刪除 zero-area sources~~ → **v1.1 active(Phase 7 核心)**。原 deferral 假設「Option A 對使用者實質不可恢復」已被 2026-05-28 forensic attack script 證明不成立(Illustrator 可拔 image XObject overlay)。

## Quick Tasks Completed

Inter-milestone ad-hoc tasks(`/gsd-quick`),不算入 milestone progress:

| Date | Slug | Description | Artifacts |
|---|---|---|---|
| 2026-05-27 | colleague-handoff-doc | 寫 `HANDOFF.md`(整合路徑決策樹 + AGPL 變化情境 + 核心領域知識備忘),供同事接手整合進公司內部簽核網站 | `HANDOFF.md`(新增,repo root);`.planning/quick/260527-1xq-colleague-handoff-doc/` |
| 2026-05-27 | cleanup-v1-debug-artifacts | 清理 milestone v1.0 hotfix 06(dCt-residue)累積的 72 個 root scratch artifacts;`.gitignore` 加入 root-anchored 防護 pattern | `samples/`(新增);`.planning/debug/scratch/v1.0-hotfix06/`(新增);`.gitignore`(modified) |

## Session Continuity

Last session: 2026-05-28T15:24:55.164Z
Stopped at: Phase 8 context gathered
Resume file: .planning/phases/08-documentation-sync-live-rollout/08-CONTEXT.md
