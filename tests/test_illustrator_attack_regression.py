"""Phase 6 Illustrator-class editor attacker 紅燈 regression test。

每個 sanitized fixture(``tests/fixtures/cad-glyph/{text|figure|mixed}-glyph-01.pdf``)
跑「ingest → process_job(logo_id=None pure removal)→ attack(拔 image XObject)→
assert 框選區仍 ≥98% 白 AND zero-area type='f' count == 0」四步流程。

**Phase 6 期望紅燈** — Option B(content-stream surgery)尚未落地;Phase 7 落地後
``@pytest.mark.xfail(strict=True)`` 會把 XPASS 報為失敗,強迫 implementer 拔掉 marker
(這就是 Phase 6 → Phase 7 的 binding handoff signal)。

**INVARIANTS**:

- 任何 pytest invocation 不可加 ``--runxfail``(會繞過所有 xfail marker,讓紅燈
  以 FAIL 形式回報而非 XFAIL,破壞 handoff signal — 參 06-RESEARCH Pitfall 4)。
- ``pytest.ini`` 不加 ``strict_xfail`` global default(避免誤傷 future test —
  顯式 ``strict=True`` 在 marker 上;參 06-RESEARCH Pitfall 5)。
- ``@pytest.mark.parametrize`` MUST sit ABOVE ``@pytest.mark.xfail``(Python decorator
  by-下而上 application order;若反置,parametrize 會拿到已-xfail-wrapped 的物件,
  行為不可預期 — 參 06-PATTERNS Risk Callout #3)。

Phase 7 implementer:落地 Option B 後請執行 ``grep -rn "xfail.*Option B" tests/``
一鍵定位本 marker;拔掉 marker + 觀察 ``python -m pytest -k illustrator_attack -v``
應顯示 3 個 PASSED,完成 handoff。
"""

from __future__ import annotations

import json
import pathlib

import fitz  # test harness exception per tests/conftest.py:12
import pytest

from app.models import JobSpec, RegionMark
from app.services import ingest, pipeline
from tests._illustrator_attack import (
    count_zero_area_fills_in_region,
    delete_image_xobjects_intersecting,
    render_region_white_pct,
)


FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "cad-glyph"


def _load_fixtures():
    """Discover all (pdf, manifest) pairs in ``tests/fixtures/cad-glyph/``。

    ``sorted()`` 為必要 — ``pathlib.Path.glob`` 在不同 OS / filesystem 順序不一致
    (參 06-RESEARCH Pitfall 6)。缺對應 ``.json`` sidecar 視為 fixture 集破損,
    直接以 ``pytest.fail`` 中止 collection。
    """
    pairs = []
    for pdf in sorted(FIXTURES_DIR.glob("*.pdf")):
        manifest = pdf.with_suffix(".json")
        if not manifest.exists():
            pytest.fail(
                f"fixture {pdf.name} 缺對應 sidecar manifest {manifest.name};"
                f"請重跑 scripts/sanitize_fixture.py 補上"
            )
        data = json.loads(manifest.read_text(encoding="utf-8"))
        pairs.append(pytest.param(pdf, data, id=pdf.stem))
    return pairs


# Decorator order(Python 由下而上應用):
#   1. ``parametrize`` 在外層,先把 function 展開為 3 個 parametrized cases。
#   2. ``xfail(strict=True)`` 在內層,套用到「base function」上,每個 parametrize
#      case 都自帶 xfail marker。
#
# **反置會出問題** — 若 parametrize 在下、xfail 在上,parametrize 會拿到一個
# 已被 xfail-wrapped 的物件展開 → 行為不可預期(06-PATTERNS Risk Callout #3)。
@pytest.mark.parametrize("fixture_pdf,manifest", _load_fixtures())
def test_illustrator_attack_residual_supplier_revealed(
    fixture_pdf,
    manifest,
    isolated_data_dir,
    logo_library,
):
    """RED-LIGHT regression test for v1.1 Illustrator-class editor threat model。

    Steps:

    1. Ingest sanitized fixture PDF via ``app.services.ingest.ingest_upload``。
    2. ``pipeline.process_job(session_id, JobSpec(..., logo_id=None))`` 跑
       pure-removal pipeline(D-01 revised contract — 純移除,Option A raster
       fallback overlay 會在 dense branch 自動觸發)。
    3. ``delete_image_xobjects_intersecting``:模擬 Illustrator-class editor
       拔掉 image XObject overlay,並 save 為 ``*_attacked.pdf``。
    4. 雙閘 assert(D-B5):

       - ``render_region_white_pct(attacked_pdf, ...) >= 98.0``(視覺乾淨閘)
       - ``count_zero_area_fills_in_region(attacked_pdf, ...) == 0``
         (content-stream 乾淨閘 — 抓 fitz 容錯渲染欺騙,參 Pitfall 8)

    **Phase 7 precondition 重設計(SCOPE 2,07-03):** Phase 6 舊前提
    ``assert n_deleted >= 1`` 假設框選區一定有 overlay 可拔。Option B 改變了防禦模型
    (true removal 取代 overlay cover):sparse fixture 不觸發 Option A dense overlay →
    無 overlay 可拔(n_deleted == 0),但 region 因 Option B 真刪已乾淨。故 precondition
    改為「無 overlay 可拔 AND region 仍髒」才失敗(Option B 沒做事又無防護的真實漏洞);
    兩道真實安全閘(white≥98% + count==0)門檻一字不放鬆,僅 precondition 邏輯更新以
    承認 true removal。此為合法 test-design update,非降標準。

    Fixtures (``isolated_data_dir``, ``logo_library``):

    - ``isolated_data_dir``(autouse)— monkeypatch ``config.DATA_DIR`` 到 tmp。
    - ``logo_library`` — 顯式宣告以確保 ``config.LOGOS_DIR`` 在 ``logo_id=None``
      路徑上仍指向 tmp(防 process_job 內任何將來的 lazy logo manifest 讀取意外
      命中真實 ``logos/`` 目錄;對標 ``test_process_api`` D-01 contract test 的
      conservatism)。
    """
    region_pdf_pts = tuple(manifest["region_rect_pdf_points"])
    region_px = manifest["region_rect_px"]
    page_index = manifest["page_index"]
    dpi = manifest["dpi"]

    # Step 1 — ingest sanitized fixture
    session = ingest.ingest_upload(fixture_pdf.name, fixture_pdf.read_bytes())
    session_id = session.session_id

    # Step 2 — process_job(D-01 revised contract:logo_id=None ⇒ pure removal)
    # NOTE: process_job(session_id, job_spec: JobSpec) -> dict per pipeline.py:90
    # (NOT a raw dict — JobSpec instance required;06-PATTERNS Risk Callout #1)
    job_spec = JobSpec(
        dpi=dpi,
        regions=[RegionMark(page=page_index, px_rect=list(region_px))],
        logo_id=None,
    )
    pipeline.process_job(session_id, job_spec)
    output_pdf = pipeline.output_path(session_id)
    assert output_pdf.exists(), "process_job 未產出 output PDF"

    # Step 3 — Illustrator-class attack(in-memory mutate + save as *_attacked.pdf)
    doc = fitz.open(output_pdf)
    try:
        n_deleted = delete_image_xobjects_intersecting(doc, page_index, region_pdf_pts)
        attacked_pdf = output_pdf.with_name(output_pdf.stem + "_attacked.pdf")
        doc.save(attacked_pdf, garbage=4, deflate=True)
    finally:
        doc.close()

    # Phase 7 Option B 改變了防禦模型(true removal 取代 overlay cover)。
    # ----------------------------------------------------------------------------
    # Phase 6 舊前提 ``assert n_deleted >= 1`` 假設「框選區一定有 image XObject
    # overlay 可拔」才算攻擊成立。但 Option B 已在 upstream 真正刪除 page-level 零面積
    # source;sparse fixture(零面積 count 遠低於 ZERO_AREA_RASTER_THRESHOLD)根本
    # 不觸發 Option A dense overlay → 沒有 overlay 可拔(n_deleted == 0),而 region
    # 因 Option B 真刪已乾淨。此時「無 overlay」不是漏洞,而是 true removal 的正確結果。
    #
    # 因此先算兩道**真實安全閘**(white≥98% + count==0,一字不放鬆),再用組合邏輯
    # 判定 precondition:
    #   - 兩道安全閘都過 → region 乾淨 → PASS(無論是否有 overlay 可拔)。
    #   - 無 overlay 可拔(n_deleted == 0)AND region 仍髒(任一安全閘失敗)→
    #     Option B 沒做事、又沒 overlay 防護 = 真實漏洞 → precondition 失敗(誠實 surface)。
    #   - 有 overlay 但拔掉後 region 髒 → 走兩道安全閘 assert 失敗(原 Phase 6 紅燈語義)。
    # 兩道安全閘的數值門檻(white≥98% / count==0)完全保留,非降標準。
    white_pct = render_region_white_pct(attacked_pdf, page_index, region_pdf_pts)
    zero_area_count = count_zero_area_fills_in_region(
        attacked_pdf, page_index, region_pdf_pts
    )
    region_is_clean = white_pct >= 98.0 and zero_area_count == 0

    # Precondition(重設計):只在「無 overlay 可拔 AND region 仍髒」時失敗 —
    # 即 Option B 沒做事又無 overlay 防護的真實漏洞。
    if n_deleted == 0 and not region_is_clean:
        pytest.fail(
            f"真實漏洞:框選區 {region_pdf_pts} 內無 image XObject overlay 可拔"
            f"(n_deleted=0),且 Option B 未把 region 清乾淨"
            f"(白={white_pct:.2f}% / zero-area count={zero_area_count})"
            f"(fixture={fixture_pdf.name})。Option B 漏抓且無 last-mile overlay 接住。"
        )

    # Step 4(a) — 視覺乾淨閘(D-B5,門檻不變)
    assert white_pct >= 98.0, (
        f"視覺乾淨閘失敗 — 框選區白佔比 {white_pct:.2f}% < 98% 門檻;"
        f"Illustrator 拔 image XObject 後供應商商標可能重現"
        f"(fixture={fixture_pdf.name})"
    )

    # Step 4(b) — content-stream 乾淨閘(D-B5,門檻不變)
    assert zero_area_count == 0, (
        f"content stream 乾淨閘失敗 — 框選區內仍有 {zero_area_count} 個 zero-area "
        f"type='f' 路徑;Option B content-stream surgery 未刪除"
        f"(fixture={fixture_pdf.name})"
    )
