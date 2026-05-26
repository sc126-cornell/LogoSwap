---
phase: 5
phase_name: ubuntu
hotfix_id: 06-dct-residue
audit_scope: hotfix_06_dct_residue
date: 2026-05-26
asvs_level: 1
diff_base: f911139..HEAD
commits_audited:
  - e7e7ca2 chore(06-hotfix): safe-landing investigation helpers (no behavior change)
  - 8352e0d fix(06-hotfix): Option A raster overlay for dense zero-area residue
  - 20974b9 chore(06-hotfix): mark dCt-residue debug session resolved
  - 00a99e4 fix(06-hotfix): address code-review BL-01 + WR-02 + WR-03 (push-blockers)
threats_total: 5
threats_closed: 4
threats_open: 0
threats_accepted: 1
register_authored_at_audit_time: true
---

# Hotfix #06 (dCt-residue) — Security Audit Report

**Audit date:** 2026-05-26
**Auditor:** Claude (gsd-secure-phase)
**Scope:** Hotfix #06 dCt-residue 4 commits on `fix/redaction-graphics-touched-mode`(尚未 push)
**Base milestone:** Phase 5 SECURED(2026-05-24, all 10 phase threats closed)
**Block policy:** `any_open_threat_not_documented_as_accepted`
**ASVS Level:** 1

## Summary

**Verdict: SECURED — 4 closed + 1 accepted-with-documented-rationale。**

此次 hotfix 重新驗證的 5 條 STRIDE 威脅全部結清。Option A raster overlay 的核心架構決策(以 image XObject 覆蓋取代 1742 個 per-artefact white covers)是已知的「OVERLAY-not-DELETE」trade-off,使用者已採決;審計確認此 trade-off 在 source code 三處(`pdf_engine.replace_region_with_white_raster` docstring、`redact.py` 模組層級 `TRUE_REMOVAL_LIMITATION`、`remove_region_vector` dispatcher inline comment)誠實揭露,且新失效路徑(去除 image + per-path bbox surgery)嚴格比舊失效路徑(re-colour 1742 covers)更難。Threshold=100 設計於 production-class CAD 檔案下有明確的單位數 vs 千位數分離,但邊界區(50–100)為 known low-confidence zone,以「P3 accepted, monitor in UAT」處置。

新引入的 `RedactError("residual_whitepaint")` 透過既有 `_PROCESS_STATUS.get(code, 422)` fallback 路徑映射為 422 結構化錯誤(非 bare 500),T-02-08 contract 不退化。

D-01「無 logo_id ⇒ 無 image」契約被此 hotfix 顯式 REVISE(BL-01 已 fix in commit 00a99e4):dense-residue 觸發時將插入 32×32 raster fallback overlay。對「未來 colleague approval site integration」可能造成下游 spoofing/info-disclosure 風險,以「accept (P3, future-integration concern,目前無下游 consumer)」處置。

fitz seam(T-02-03)新 helper 全部位於 `pdf_engine.py` 內,AST-level 守衛測試繼續綠燈。D-05(original byte-exact)守住 —— 灰名單 `originals/` / `pristine_path` 在 redact.py 中為零出現。

測試套件快照(per resolution log):**300 passed + 3 platform-skipped**(較 Phase 5 closing 的 291 多 +9,全為 hotfix #06 新增測試,含 6 dense-branch 整合 + 3 safe-landing helpers)。

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence (file:line) |
|-----------|----------|-------------|--------|----------------------|
| T-02-03 | T / I — fitz seam confinement(AGPL §13 defence layer 2) | mitigate | CLOSED | (1) Grep `import fitz` only matches `app/services/pdf_engine.py:19` (the seam) + docstring mentions in `app/services/integrity.py:11`(顯式 "NO ``import fitz``"). (2) `app/services/redact.py` 整檔無 fitz import — confirmed via Grep over `app/`. (3) AST-level guard `tests/test_redact.py:1190-1207 test_fitz_import_confined_to_engine_seam` walks `ast.Import` + `ast.ImportFrom` over all `app/**/*.py`,assert `offenders == ["pdf_engine.py"]`. (4) hotfix #06 新增的兩個 helpers (`count_zero_area_fills_fully_inside` @ `pdf_engine.py:699-743`, `replace_region_with_white_raster` @ `pdf_engine.py:746-810`) + 新常數 `ZERO_AREA_RASTER_THRESHOLD` @ `pdf_engine.py:294` 都在 seam 內。caller `redact.py:232-256` 全部走 `pdf_engine.*` wrapper。 |
| T-02-07 | I — TRUE REMOVAL vs cover(project core threat,hotfix 直接 address) | mitigate(+ documented architectural limitation) | CLOSED with documented residual | **舊攻擊面確實閉合:** 整合測試 `tests/test_redact.py:691-794 test_remove_region_vector_dense_real_zero_area_paths_end_to_end` 在合成 PDF(120 個 zero-area `type='f'` paths,>=THRESHOLD)上 end-to-end 跑 `remove_region_vector`,assert:(a) `page.get_images(full=True) == 1`(raster fallback 觸發);(b) `get_white_fill_drawings_intersecting == []`(per-artefact cover union 攻擊面消失);(c) 5 個取樣 pixel 全部 >=250(視覺乾淨);(d) 函式回傳 True。對 reproduction file `3013A-13A-C6-XX-3D02-A01-00040.pdf` 的手動 PRE/POST 比對於 `06-HOTFIX-REVIEW.md:174-178` 與 `.planning/debug/resolved/redact-whitepaint-residue.md:170-191`。**新限制誠實揭露於三處:**(1) `app/services/pdf_engine.py:776-791 replace_region_with_white_raster` docstring "LIMITATION (be honest)" 區段;(2) `app/services/redact.py:6-36` 模組層級 `TRUE_REMOVAL_LIMITATION` 區段;(3) `app/services/redact.py:220-227` dispatcher inline comment "HONEST LIMITATION"。三處 wording 一致(原 WR-03 已 fix)。新失效路徑(需 (i) delete image XObject + (ii) per-path bbox surgery)在所有三處皆顯式列出,strictly harder than 舊路徑(re-colour 1742 cover drawings,一個 sed 即可)。Post-condition fail-closed:`redact.py:245-250` 抓 `get_white_fill_drawings_intersecting != []` raise `RedactError("residual_whitepaint")`。 |
| T-02-08 | DoS / I — 新 RedactError code 映射為結構化 4xx,非 bare 500 | mitigate | CLOSED | 新 `RedactError("residual_whitepaint")` raise @ `app/services/redact.py:247-250`。映射路徑:`app/main.py:170-176 _handle_redact_error` 透過 `_PROCESS_STATUS.get(exc.code, 422)` fallback 將未列舉 code 映射為 **422 + 結構化 `{detail:{code,message}}` 回應**(非 bare 500 + stack trace)。Body 內僅含 Chinese error message + stable code string,無 internal traceback 或 file path 洩漏。註:`_PROCESS_STATUS` dict (`app/main.py:160-167`) 未顯式列入 `residual_whitepaint`,依靠 default fallback 422 — 此 design 已被既有 pattern (`residual_content` 列入,新 code 預期 fallback)隱式採用,功能正確但有微小可讀性瑕疵(見 ## Notes for follow-up)。 |
| D-05 | T — original PDF byte-exact preservation | mitigate | CLOSED | (1) Grep `originals/|original_path|originals_dir` against `app/services/redact.py` returns **No matches** — hotfix-modified file 從未提及 originals。(2) Grep against `app/services/pdf_engine.py` 僅命中 line 67 註釋字串「never persists to the immutable original」 — 註解非寫操作。新 helpers `replace_region_with_white_raster` + `count_zero_area_fills_fully_inside` 操作對象 only `page` handle(pipeline 已 open-against-work-copy);無檔案 IO。(3) Pipeline (`app/services/pipeline.py:107-150`) 結構不變:reset-from-pristine + work-copy-only mutation。(4) 既有 `test_process_job_leaves_original_unchanged` (`tests/test_redact.py:896-905`)依 SHA-256 對比 pin 此不變式,per resolution log "301 passed" 持續綠燈。 |
| D-01 / S | Spoofing / I — 「無 logo_id ⇒ 無 image」契約被 hotfix 顯式 REVISE | **accept (P3, documented contract revision)** | CLOSED via documented acceptance | **契約變更已透明文件化:** 測試 `tests/test_process_api.py:270-316 test_process_without_logo_is_pure_removal` 的 docstring 已重寫(commit 00a99e4 BL-01 fix),明說「Revised by hotfix #06 (dCt-residue, Option A raster fallback): no logo_id ⇒ no LOGO image; the only image XObject that may appear on a page is a raster fallback overlay placed by `remove_region_vector` when post-redaction zero-area `type='f'` residue density crosses `ZERO_AREA_RASTER_THRESHOLD`」並 cross-reference 到 `test_remove_region_vector_dense_real_zero_area_paths_end_to_end` 作為 dense-branch 行為的 pin。**現況風險評估:**(a) 目前無 documented downstream consumer(per PROJECT.md / CLAUDE.md「v1 為內網 standalone 工具」);(b) 將來「colleague 簽核網站」integration 為 deferred consideration,不阻擋此 hotfix;(c) 32×32 全白 raster 本身無 information payload,但其 PRESENCE 可在 side-channel 上洩漏「此 region 觸發 dense branch ⇒ likely supplier-CAD-glyph logo」 — marginal,記錄但不阻擋。詳見「Accepted Risks Log」 / D-01-r1。 |

**Score: 4 mitigate-CLOSED + 1 accept-CLOSED = 5/5。**

## Threshold Boundary Verification(T-02-07 附帶要求 #3)

審計要求:確認 dispatcher threshold (100) 不會在 50–100 區間靜默重蹈 LIVE bug 的覆轍。

**已知行為:** `app/services/redact.py:232-256` dispatcher 嚴格 `>=`:`zero_area_count >= 100` 走 dense branch,< 100 仍走舊 `cover_zero_area_artefacts` 路徑。

**評估:**
- production-class 已驗證樣本:DC.pdf(single-digit zero-area)與 reproduction file(1742 zero-area)有 ~170× 分離(per `pdf_engine.py:284-293` docstring + debug session metadata)。
- **未驗證的中間區(50–99 zero-area):** 此區間檔案會走 OLD cover 路徑;若這類檔案存在且 cover-union 仍能重現 logo,LIVE bug 仍會發生於該檔案。
- **緩解:** code review WR-01 已 explicit 提出此風險並 deferred(env override + telemetry + sentinel test 為 production-tuning improvement,非 push blocker per `06-HOTFIX-REVIEW.md:24`)。對 ASVS L1 內網工具可接受 — 此區間是 known low-confidence,不是 silent。
- **建議 UAT action(非 push blocker):**(a) 內部交付前對 2–3 個其他 supplier 檔案跑 `count_zero_area_fills_fully_inside` 探測分布;(b) 若有 50–99 區間檔案出現,以 WR-01 fix(env override `LOGOSWAP_ZERO_AREA_RASTER_THRESHOLD`)現場下調閾值。

**Disposition:** marginal residual risk per ASVS L1, **記錄但不阻擋 push**。

## Accepted Risks Log

### D-01-r1 — D-01 「no logo_id ⇒ no embedded image」契約 hotfix-revision

- **Disposition:** accept (P3, v1 internal-LAN, no current downstream consumer)
- **Original contract (Phase 2 D-01):** `POST /process` without `logo_id` ⇒ output PDF 的所有 page 上 `page.get_images() == []`。
- **Revised contract (hotfix #06):** without `logo_id` ⇒ output 上 **無 LOGO image**;但 dense-residue branch(zero-area `type='f'` 數 ≥ `ZERO_AREA_RASTER_THRESHOLD`)觸發時,該 region 會多一個 32×32 solid-white image XObject (raster fallback overlay)。對標準 `valid_pdf_bytes` fixture 此 branch 永不觸發,所以舊測試斷言文字不變,僅 docstring 更新。
- **Spoofing residual risk:** 任何 downstream system 若以 `len(page.get_images()) > 0` 判斷「logo 已置入」,在 dense-residue case 會誤判 — 將「pure removal with fallback」當作「logo placed」。
- **Information-disclosure residual risk:** 32×32 全白 raster 本身無 payload,但其 PRESENCE-OR-ABSENCE 可在 side-channel 上洩漏「此 region 已觸發 dense branch ⇒ very likely supplier-CAD-glyph logo」 — marginal,假設攻擊者已能讀 output PDF。
- **Current consumer surface:** PROJECT.md / CLAUDE.md 明確指出 v1 為「內網免登入 standalone 工具」,**目前無 documented downstream consumer**。「future colleague approval site integration」為 deferred consideration,任何該整合上線前 reviewer 必須讀此 acceptance entry。
- **Upgrade trigger / when to revisit:**
  1. colleague approval site 整合決議落地時,必須在 integration spec 明文宣告「`get_images()` count NOT a reliable logo-presence signal」,並提供 alternative pattern(例:每 logo 寫一筆 region-level metadata 進 result 回應,downstream 以該欄位判斷)。
  2. 或:擴充 `pdf_engine.is_raster_fallback_image(page, xref)` getter(`06-HOTFIX-REVIEW.md` BL-01 option 2)讓 downstream 可區分 fallback overlay 與真 logo image。
- **Documented at:**
  - `tests/test_process_api.py:270-316` test docstring(契約 revision 文字)
  - `app/services/redact.py:6-36 TRUE_REMOVAL_LIMITATION` 區段(技術機制)
  - `app/services/pdf_engine.py:746-791 replace_region_with_white_raster` docstring(實作層 LIMITATION 區段)
  - `06-HOTFIX-REVIEW.md:55-79 BL-01` 條目(原 review 識別)
  - 本檔此節(security-audit acceptance)

## Pitfall / Invariants Cross-Check(positive evidence)

| Invariant | 驗證 | Evidence |
|---|---|---|
| fitz seam(T-02-03)未漏 | Grep `import fitz` 全 `app/` | 僅 `app/services/pdf_engine.py:19` 一處 import,其餘命中皆為 docstring「NO import fitz」聲明或註解 |
| AST-level seam guard 持續綠燈 | `tests/test_redact.py:1190-1207` | `offenders == ["pdf_engine.py"]` |
| Logo z-order 不被破壞(LOGO-02) | `redact.py:235 replace_region_with_white_raster` 先插入 32×32 white image(在 `remove_region_vector` 內);`pipeline.py:287-301 place_logo` 後插入 logo image(在 pipeline,after redact returns);兩者皆 `overlay=True`,後插入 = topmost | logo 落在 white raster 之上,無視覺遮蓋回歸 |
| `apply_redactions` ordering 不變 | `redact.py:174-179 apply_redactions` → `redact.py:189-195` residual assertion → `redact.py:232-256` zero-area dispatcher | dispatcher 跑在 redaction 與 assertion 之後 — 不會 trip 自己 / `get_drawings_fully_inside` 對 zero-area `type='f'` 已 filter |
| Sparse path 不被破壞 | dispatcher else branch `redact.py:251-256` 仍呼叫 `cover_zero_area_artefacts` | DC.pdf-class hairline-suppression intact |
| fitz.Pixmap C-buffer lifecycle | `pdf_engine.py:803-810 replace_region_with_white_raster` try / finally `del pix` | C buffer immediate drop;non-CPython runtime 不保證 immediate 釋放 — WR-05 deferred 為 style issue,不影響安全 |
| `clear_with(255)` colorspace 隱式正確 | `pdf_engine.py:803` `fitz.csRGB, ..., False` → 3 byte/pixel,no alpha → all-byte 255 = (255,255,255) white | WR-04 deferred 為 defence-in-depth future-proofing,非 security gap |

## Open Threats

**None.** 全部 5 條威脅 CLOSED(4 mitigate + 1 accept-with-documented-rationale)。

## Unregistered Flags

**None new.** hotfix 未引入新的 STRIDE 攻擊面:
- 新檔案 IO:**zero**(redact.py 不碰 storage,pdf_engine 新 helpers 僅 mutate in-memory page handle)。
- 新 HTTP route 或 input validator:**zero**(API layer 完全不變)。
- 新 trust boundary 跨越:**zero**(全部變動在 `app/services/{pdf_engine,redact}.py` seam 與 caller 內)。
- 新 dependency:**zero**(只用 PyMuPDF 既有 `fitz.Pixmap` + `page.insert_image` API,已在 Phase 1-4 surface 內)。
- hotfix 不存在 SUMMARY.md(只有 REVIEW.md);無 `## Threat Flags` 區段需驗證。

## Audit Trail

| Item | Result |
|------|--------|
| Required reading loaded | 9/9(05-SECURITY.md, 06-HOTFIX-REVIEW.md, debug/resolved/redact-whitepaint-residue.md, pdf_engine.py, redact.py, pipeline.py, api/process.py, test_redact.py, test_process_api.py) |
| Threats re-verified | 5/5 (T-02-03, T-02-07, T-02-08, D-05, D-01-r1) |
| Closed | 5 (4 mitigate + 1 accept) |
| Open | 0 |
| Escalations | 0 |
| Unregistered flags | 0 |
| Implementation modifications | NONE(audit is read-only per role contract) |
| Test snapshot(reported in resolution log) | 300 passed + 3 platform-skipped(+9 net hotfix #06 tests vs Phase 5 close的 291) |

## Notes for follow-up(non-blocking, post-push)

下列項目原為 maintenance-cycle 候選;**項目 3(WR-01)已在 push 窗口內隨同 code-review 第二輪一併修完**(`LOGOSWAP_ZERO_AREA_RASTER_THRESHOLD` env override + `logger.info("zero_area_dispatch", ...)` telemetry,測試 308 全綠)。其餘仍為良好工程實踐,不阻擋 push:

1. **顯式列入 `residual_whitepaint` 至 `_PROCESS_STATUS`**(`app/main.py:160-167`):目前 code 透過 `dict.get(code, 422)` fallback 正確映射,但顯式 entry `"residual_whitepaint": 422,` 可提高可讀性 + 防未來 reviewer 誤改 default。功能性等效,僅 self-documentation gain。
2. **`is_raster_fallback_image(page, xref)` getter**(`06-HOTFIX-REVIEW.md` BL-01 option 2):若 colleague 簽核網站 integration 上線,需要區分 fallback overlay 與真 logo image — 此時加入 32×32 / 全白 metadata sentinel 比 patch 下游所有 consumer 便宜。
3. **~~WR-01 threshold env override + telemetry~~**:✅ 已修(`app/config.py` 加 `LOGOSWAP_ZERO_AREA_RASTER_THRESHOLD`,`app/services/redact.py` 加 `logger.info("zero_area_dispatch", extra={"zero_area_count", "threshold", "branch"})`,3 個新測試 pin env override + dispatch log)。
4. **內部 UAT 對 2–3 個其他 supplier 檔案探測 `count_zero_area_fills_fully_inside` 分布**(per ## Threshold Boundary Verification 建議):成本低、信息量高,可儘早確認 100 閾值在實際 production 樣本下無中間區檔案落入。**telemetry 已就位**(`zero_area_dispatch` log 含 count + threshold + branch),production 流量自動累積分布資料。

## Verdict

## SECURED

Hotfix #06 (dCt-residue) 在 4 commit `e7e7ca2..00a99e4` 的範圍內,所有 5 條重新驗證的 STRIDE 威脅皆已 CLOSED(4 mitigate + 1 accept-with-documented-rationale)。Option A architectural trade-off(image-overlay vs content-stream-surgery)為使用者已決議的 architectural choice;審計確認此 trade-off 在 source code 三處(engine docstring、redact module docstring、dispatcher inline comment)誠實揭露,且新失效路徑嚴格較舊路徑難。fitz seam 完整、original byte-exactness 守住、新 RedactError 結構化 4xx fallback 正確、D-01 契約 revision 透明文件化。

**Hotfix #06 may be pushed to `master` and deployed to LIVE.**

---

*Audited: 2026-05-26*
*Auditor: Claude (gsd-secure-phase)*
*ASVS Level: 1*
*Scope: hotfix_06_dct_residue(4 commits, local-only, pending push)*
*Output language: 繁體中文(prose)+ English(identifiers / file paths / quoted code)*
