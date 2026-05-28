"""TEST-03 — Phase 7 Option B helper unit tests.

針對 ``app/services/pdf_engine.py`` 的兩個 Phase 7 Option B helper
(``delete_zero_area_type_f_fills_inside`` + ``log_xobject_intersect``)的單元測試。
覆蓋 5 個維度(per 07-CONTEXT D-D3 + 07-PATTERNS Pattern T4 coverage map):

  - 密度梯度(0 / 1 / 100 / 1742 個零面積 type='f' fill,parametrized)
  - SEC-02 no-op(正常面積向量 PDF + re-entrancy)
  - safe-skip 5 context(BT/ET、(...)、<...>、%comment、BI/ID/EI inline image)
  - SEC-03 form-XObject(intersect log + 內部 stream 不被動 + no-xobject-no-log)

所有 fixture 皆 in-memory 構造(per 07-PATTERNS Pattern S2 — 不 commit 新 binary)。
fitz license header 為 project convention(AGPL guard scope 為 app/**/*.py,
tests/ 在 scope 外 — per 07-RESEARCH Pitfall 9)。
"""

from __future__ import annotations

import logging

import fitz  # only the test harness may use fitz directly to BUILD fixtures
import pytest

from app.services import pdf_engine


# --- Density gradient (4 parametrized cases) ------------------------------------------

@pytest.mark.parametrize("n_zaf", [0, 1, 100, 1742])
def test_option_b_density_gradient(n_zaf):
    """TEST-03 密度梯度:0 / 1 / 100 / 1742 個零面積 type='f' fill 全在 user_rect 內。

    沿用 tests/test_redact.py:722-728 的 Shape.draw_rect(W=0) zero-area 注入 pattern。
    驗證 helper 回傳刪除數 == n_zaf,且刪除後 count_zero_area_fills_fully_inside == 0。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        user_rect = fitz.Rect(50.0, 100.0, 350.0, 200.0)

        for i in range(n_zaf):
            x = 55.0 + (i % 290) * 1.0  # spread across rect width
            y_off = (i // 290) * 1.0
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(x, 110.0 + y_off, x, 190.0 + y_off))  # W=0
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()

        count_before = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_before == n_zaf, (
            f"fixture density mismatch: expected {n_zaf}, got {count_before}"
        )

        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == n_zaf, f"expected to delete {n_zaf}, deleted {deleted}"

        count_after = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_after == 0
    finally:
        doc.close()


# --- SEC-02 no-op (2 cases) -----------------------------------------------------------

def test_option_b_no_op_on_normal_vector_pdf():
    """SEC-02:input PDF 無零面積 type='f' fill → Option B 為 no-op。

    正常面積 filled rect(300×100)+ 文字 → STEP A pre-screen short-circuit:
      - 回傳 0(沒刪任何東西)
      - page.read_contents() bytes 一字未改(strict invariant)
      - count_zero_area_fills_fully_inside 前後都 0
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        # Normal-area filled rect — not zero-area.
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 100, 350, 200))  # 300×100 — real area
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()
        # Add some text too (typical vector page).
        page.insert_text((100, 150), "SUPPLIER LOGO", fontsize=10)

        bytes_before = page.read_contents()
        count_before = pdf_engine.count_zero_area_fills_fully_inside(
            page, (50.0, 100.0, 350.0, 200.0)
        )
        assert count_before == 0  # precondition: no ZAFs

        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(
            page, fitz.Rect(50, 100, 350, 200)
        )
        assert deleted == 0  # SEC-02: no-op return

        bytes_after = page.read_contents()
        assert bytes_after == bytes_before, (
            "content stream MUST be unchanged in no-op case (SEC-02)"
        )

        count_after = pdf_engine.count_zero_area_fills_fully_inside(
            page, (50.0, 100.0, 350.0, 200.0)
        )
        assert count_after == 0
    finally:
        doc.close()


def test_option_b_reentrant():
    """Re-entrancy(Open Q3 / Risk Callout #8):連續呼叫兩次,第二次為硬 no-op。

    第一次刪 N 個 ZAF,第二次回傳 0;第二次呼叫後 page.read_contents() bytes
    與第一次呼叫後相同(STEP A pre-screen short-circuit,不再動 stream)。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        user_rect = fitz.Rect(50.0, 100.0, 350.0, 200.0)
        n_zaf = 100
        for i in range(n_zaf):
            x = 55.0 + (i % 290) * 1.0
            y_off = (i // 290) * 1.0
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(x, 110.0 + y_off, x, 190.0 + y_off))
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()

        first = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert first == n_zaf
        bytes_after_first = page.read_contents()

        second = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert second == 0, "2nd call must be a hard no-op"
        bytes_after_second = page.read_contents()
        assert bytes_after_second == bytes_after_first, (
            "2nd call must not mutate the content stream"
        )
    finally:
        doc.close()


# --- Safe-skip 5 contexts (5 cases) ---------------------------------------------------
#
# 雙閘策略(per 07-PLAN action + D-A2 + Pitfall 1):
#   (a) end-to-end — 構造含真 ZAF 的 page,assert helper 只刪 ZAF,不誤刪文字字元
#   (b) unit-level — 直接 assert _build_safe_skip_mask 對 crafted byte sequence
#       的 mask 行為(精確 byte-mask assertion)
# hex / comment / inline-image 因 fitz public API 難以直接注入 raw stream,
# 主要靠 (b) unit-level mask correctness 驗證(最 robust 的 D-A2 validation)。

def test_safe_skip_bt_et():
    """safe-skip BT/ET:文字段內含 `m l f` 字元不可被當作 path operator 誤刪。

    雙閘:(a) end-to-end — 文字在 user_rect 外、ZAF 在內,helper 只刪 ZAF 且文字
    可讀;(b) unit-level — _build_safe_skip_mask 對 `BT (...) ET` 段標記為 0。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        # Text containing path-operator-looking chars, OUTSIDE the user_rect.
        page.insert_text((50, 50), "Quality m l f", fontsize=10)
        # A real zero-area fill INSIDE the user_rect.
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(100, 150, 100, 180))  # W=0
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()

        user_rect = fitz.Rect(80, 140, 200, 200)
        assert pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        ) == 1

        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == 1, "Option B should delete the real ZAF, not be confused by text"

        # The text "Quality m l f" must still be present (was outside user_rect).
        assert "Quality" in page.get_text(), "BT/ET text block content must NOT be touched"

        # (b) unit-level mask correctness.
        crafted = b"BT (test) Tj ET m l f"
        mask = pdf_engine._build_safe_skip_mask(crafted)
        bt_et_len = len(b"BT (test) Tj ET")
        assert all(m == 0 for m in mask[:bt_et_len]), "BT...ET must be masked"
        assert all(m == 1 for m in mask[bt_et_len:]), "bytes after ET stay searchable"
    finally:
        doc.close()


def test_safe_skip_paren_string():
    """safe-skip `(...)` literal:literal string 內字元不可被誤刪。

    雙閘:(a) end-to-end via inserted text (fitz encodes show-strings as PDF
    literals);(b) unit-level — `(Quality m l f)` 整段 mask 為 0。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        page.insert_text((50, 50), "some string with m l f", fontsize=10)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(100, 150, 100, 180))  # W=0
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()

        user_rect = fitz.Rect(80, 140, 200, 200)
        assert pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        ) == 1
        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == 1

        # (b) unit-level mask correctness — whole paren literal masked.
        crafted = b"(Quality m l f)"
        mask = pdf_engine._build_safe_skip_mask(crafted)
        assert all(m == 0 for m in mask), "paren literal must be fully masked"
    finally:
        doc.close()


def test_safe_skip_hex_string():
    """safe-skip `<...>` hex string:`<6d6c66>`(m/l/f 的 hex)不可被誤判為 operator。

    主驗證 unit-level mask:`<6d6c66>` 前 9 bytes(含 `<` 與 `>`)mask 為 0。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        # A real ZAF so the end-to-end path runs.
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(100, 150, 100, 180))  # W=0
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()
        user_rect = fitz.Rect(80, 140, 200, 200)
        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == 1

        # unit-level mask correctness.
        crafted = b"<6d6c66> Tj"
        mask = pdf_engine._build_safe_skip_mask(crafted)
        assert all(m == 0 for m in mask[:8]), "<...> hex string must be masked"
    finally:
        doc.close()


def test_safe_skip_comment():
    """safe-skip `% ... \\n` comment:註解內的 `m l f` 不可被誤刪。

    主驗證 unit-level mask:`% m l f` 前 7 bytes(到換行前)mask 為 0。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(100, 150, 100, 180))  # W=0
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()
        user_rect = fitz.Rect(80, 140, 200, 200)
        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == 1

        # unit-level mask correctness.
        crafted = b"% m l f\n"
        mask = pdf_engine._build_safe_skip_mask(crafted)
        assert all(m == 0 for m in mask[:7]), "comment to EOL must be masked"
    finally:
        doc.close()


def test_safe_skip_inline_image():
    """safe-skip BI/ID/EI inline image:binary bytes 不可被誤判為 path operator。

    主驗證 unit-level mask:整段 `BI ... ID ... EI` mask 為 0。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(100, 150, 100, 180))  # W=0
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()
        user_rect = fitz.Rect(80, 140, 200, 200)
        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted == 1

        # unit-level mask correctness — whole BI...EI block masked.
        crafted = b"BI /W 1 /H 1 ID some bytes EI"
        mask = pdf_engine._build_safe_skip_mask(crafted)
        assert all(m == 0 for m in mask), "BI...ID...EI inline image must be masked"
    finally:
        doc.close()


# --- SEC-03 form-XObject (3 cases) ----------------------------------------------------

def test_option_b_form_xobject_intersect_logged(caplog):
    """SEC-03:user_rect 與 Form XObject bbox intersect 時,log_xobject_intersect
    emit `option_b_xobject_intersect` warning(含 structured extra dict)。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        nested_doc = fitz.open()
        try:
            nested_page = nested_doc.new_page(width=200, height=150)
            shape = nested_page.new_shape()
            shape.draw_rect(fitz.Rect(50, 60, 50, 100))  # zero-area W=0
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()
            # show_pdf_page wraps the nested page in a Form XObject on the host page.
            page.show_pdf_page(fitz.Rect(50, 100, 250, 250), nested_doc, 0)
        finally:
            nested_doc.close()

        assert len(page.get_xobjects()) >= 1  # precondition

        with caplog.at_level(logging.WARNING, logger="app.services.pdf_engine"):
            n = pdf_engine.log_xobject_intersect(
                page, fitz.Rect(40, 90, 260, 260), logger=None
            )

        assert n >= 1
        matching = [r for r in caplog.records if "option_b_xobject_intersect" in r.message]
        assert matching, "expected 'option_b_xobject_intersect' warning"
        rec = matching[0]
        assert rec.xobject_count >= 1  # extra={"xobject_count": ...} surfaces as attr
        assert rec.page_index == 0
    finally:
        doc.close()


def test_option_b_form_xobject_internal_stream_untouched():
    """SEC-03:Option B 為 page-level only — Form XObject 內部 stream 不被動。

    同 12 構造,記錄 nested XObject xref 的 stream,呼叫 helper 後 assert 不變
    (per D-B1 — page.read_contents() 天然不下鑽 XObject)。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        nested_doc = fitz.open()
        try:
            nested_page = nested_doc.new_page(width=200, height=150)
            shape = nested_page.new_shape()
            shape.draw_rect(fitz.Rect(50, 60, 50, 100))  # zero-area W=0
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
            shape.commit()
            page.show_pdf_page(fitz.Rect(50, 100, 250, 250), nested_doc, 0)
        finally:
            nested_doc.close()

        nested_xref = page.get_xobjects()[0][0]
        stream_before = doc.xref_stream(nested_xref)

        pdf_engine.delete_zero_area_type_f_fills_inside(
            page, fitz.Rect(40, 90, 260, 260)
        )

        stream_after = doc.xref_stream(nested_xref)
        assert stream_after == stream_before, (
            "Form XObject internal stream must NOT be touched (SEC-03)"
        )
    finally:
        doc.close()


def test_option_b_no_xobject_no_log(caplog):
    """SEC-03 reverse:page 完全無 form-XObject → log_xobject_intersect 回 0 + 不 log。"""
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        # A plain (non-zero-area) filled rect — no form XObject anywhere.
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 100, 350, 200))
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()

        assert len(page.get_xobjects()) == 0  # precondition

        with caplog.at_level(logging.WARNING, logger="app.services.pdf_engine"):
            n = pdf_engine.log_xobject_intersect(
                page, fitz.Rect(0, 0, 400, 300), logger=None
            )

        assert n == 0
        matching = [r for r in caplog.records if "option_b_xobject_intersect" in r.message]
        assert not matching, "no log should be emitted when there is no form XObject"
    finally:
        doc.close()


# --- Shape 1 rework (07-03 Task 1 行為鎖定:3 cases) -----------------------------------
#
# Shape 1(PScript5 m/l 算子)零面積 fill 的單元測試。注意 Shape API 算子型別
# (07-03 Task 2 spike 確認):
#   - Shape.draw_rect(W=0)  → items [('re', ...)] → Shape 2 路徑
#   - Shape.draw_line(...)   → items [('l',  ...)] → Shape 1 路徑(type='f')
# 故本節 Shape 1 fixture 一律用 draw_line(零面積垂直線 + fill)以命中 m/l 索引。

def test_option_b_shape1_high_density_all_matched():
    """高密度 Shape 1:~500 筆不同 bbox 的 m/l 零面積 fill 全在 user_rect 內 → 全刪。

    鎖定 07-03 Task 1 的 single-pass _build_shape1_candidate_index:取代舊
    per-zaf 全串流 finditer(14% 匹配 / 765s),新索引讓高密度 Shape 1 100% 匹配。
    主斷言為正確性(deleted == N + 刪後 count == 0);附帶 perf soft-assert < 5s。
    """
    import time

    doc = fitz.open()
    try:
        page = doc.new_page(width=700, height=400)
        user_rect = fitz.Rect(50.0, 100.0, 650.0, 300.0)
        n = 500
        for i in range(n):
            x = 55.0 + i * 1.0  # 各不同 x → 各不同 bbox(最大 x=554 < 650,全在框內)
            shape = page.new_shape()
            shape.draw_line(fitz.Point(x, 110.0), fitz.Point(x, 290.0))  # 零寬垂直線
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0, closePath=False)
            shape.commit()

        ds = page.get_drawings()
        assert ds and ds[0].get("items")[0][0] == "l", (
            "fixture 必須命中 Shape 1(m/l)路徑"
        )
        count_before = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_before == n, f"density mismatch: expected {n}, got {count_before}"

        t0 = time.perf_counter()
        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        elapsed = time.perf_counter() - t0

        assert deleted == n, f"high-density Shape 1 應全刪 {n},實際 {deleted}"
        count_after = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_after == 0, "刪除後框選區應無零面積 type='f' 殘留"
        # Perf soft-assert(single-pass 索引):500 筆遠快於 5s。
        assert elapsed < 5.0, f"high-density Shape 1 處理過慢:{elapsed:.3f}s"
    finally:
        doc.close()


def test_option_b_shape1_duplicate_bbox_all_deleted():
    """重複 bbox Shape 1:N 筆完全相同 bbox 的 m/l 零面積 fill(單一 logo 分解為多筆
    同位置描邊)→ 全刪(Option (ii) cardinality)。

    鎖定 07-03 Task 1 的關鍵修正:value 為 list(setdefault 累加)而非舊「唯一匹配」
    規則。舊規則在重複 bbox 下 len(matches) != 1 → return None → 漏刪;新 bbox-keyed
    索引把同 bbox 的全部 byte-range 收進 list,該 bbox 全部描邊一次刪除。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        user_rect = fitz.Rect(50.0, 100.0, 350.0, 200.0)
        n = 5
        for _ in range(n):
            shape = page.new_shape()
            # 完全相同的零寬垂直線 → 同一 bbox。
            shape.draw_line(fitz.Point(100.0, 110.0), fitz.Point(100.0, 190.0))
            shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0, closePath=False)
            shape.commit()

        count_before = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_before == n, f"duplicate-bbox fixture 應有 {n} 筆,實際 {count_before}"

        deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)
        assert deleted >= 1, "重複 bbox 應被視為覆蓋成功(≥1),不再因唯一匹配規則漏刪"

        count_after = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_after == 0, "同 bbox 的全部 N 筆描邊都應刪除,刪後 count == 0"
    finally:
        doc.close()


def test_option_b_shape1_genuine_miss_failsafe(caplog):
    """genuine-miss fail-safe:get_drawings 偵測到一個 ZAF,但其無法被 shape 定位
    (此處用 items=['c'] 的 mixed/empty-item ZAF — 既非全 re 亦非全 m/l)→
    delete_zero_area_type_f_fills_inside return 0 + content stream 一字未改 +
    caplog 捕獲 option_b_parse_anomaly。

    鎖定 07-03 D-A5 fail-safe 在新 bbox-keyed cardinality 下仍成立:真實漏抓
    (無法定位的 ZAF)絕不破壞性寫回。draw_bezier 產生 items=['c'] 的零面積 type='f'
    ZAF → has_mixed_empty_zaf=True → fail-safe。
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=300)
        user_rect = fitz.Rect(50.0, 100.0, 350.0, 200.0)
        # 零寬 Bezier → 零面積 type='f' ZAF,但 items=['c'](非 re、非 m/l)。
        shape = page.new_shape()
        shape.draw_bezier(
            fitz.Point(100.0, 110.0),
            fitz.Point(100.0, 130.0),
            fitz.Point(100.0, 160.0),
            fitz.Point(100.0, 190.0),
        )
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0, closePath=False)
        shape.commit()

        items_kinds = [it[0] for it in page.get_drawings()[0].get("items")]
        assert "c" in items_kinds and "re" not in items_kinds and "l" not in items_kinds, (
            "fixture 必須是無法被 shape 定位的 mixed/empty-item ZAF"
        )
        count_before = pdf_engine.count_zero_area_fills_fully_inside(
            page, (user_rect.x0, user_rect.y0, user_rect.x1, user_rect.y1)
        )
        assert count_before == 1, "precondition: 1 個被偵測到的 ZAF"

        bytes_before = page.read_contents()
        with caplog.at_level(logging.WARNING, logger="app.services.pdf_engine"):
            deleted = pdf_engine.delete_zero_area_type_f_fills_inside(page, user_rect)

        assert deleted == 0, "genuine-miss 必須走 fail-safe(return 0)"
        bytes_after = page.read_contents()
        assert bytes_after == bytes_before, (
            "fail-safe 絕不破壞性寫回 — content stream bytes 必須一字未改"
        )
        matching = [
            r for r in caplog.records if "option_b_parse_anomaly" in r.message
        ]
        assert matching, "expected 'option_b_parse_anomaly' warning on genuine miss"
        rec = matching[0]
        assert rec.expected >= 1  # extra={"expected": ...} surfaces as attr
        # mixed/empty-item ZAF 觸發 mixed_empty 旗標(新增診斷欄位)。
        assert getattr(rec, "mixed_empty", False) is True
    finally:
        doc.close()


# --- CR-01 over-delete guard(co-located 合法內容必須存活)----------------------------
#
# Shape 1 索引舊行為:把整個 q...Q block byte-range 當刪除目標。當 block 同時夾帶零面積
# path 與 co-located 合法內容(如 ``/Fm0 Do`` Form-XObject 調用)時,整塊 splice 會把
# ``Do`` 一起刪掉 = silent data loss。修正後採保守 skip:夾帶 ``Do/BT/sh/BI`` 的 block
# 不入索引 → dispatch 視為 missing → D-A5 fail-safe → 既有 overlay 接 last-mile。

def test_shape1_block_with_colocated_do_not_indexed():
    """CR-01:含 co-located ``/Fm0 Do`` 的 q...Q block 不被 index(整塊刪會誤刪 Do)。

    直接對 ``_build_shape1_candidate_index`` 注入 REVIEW.md 重現 byte stream
    ``q 10 20 m 10 100 l f /Fm0 Do Q``。修正後此 block 因夾帶 ``Do`` 而被保守跳過,
    index 不含其 key → dispatch 端視為 missing → fail-safe(絕不破壞性寫回)→ ``Do``
    存活。對照組(純零面積 path,無 ``Do``)仍正常入索引,證明 guard 不過度寬鬆。
    """
    page_transform = fitz.Identity  # raw byte test — no page-space mapping needed

    # (a) block 夾帶 co-located Do → 必須被跳過(不入索引)。
    stream_with_do = b"q 10 20 m 10 100 l f /Fm0 Do Q"
    mask = pdf_engine._build_safe_skip_mask(stream_with_do)
    index = pdf_engine._build_shape1_candidate_index(
        stream_with_do, mask, pdf_engine._DEGENERATE_BBOX_EPS, page_transform
    )
    assert index == {}, (
        "夾帶 /Fm0 Do 的 q...Q block 不可入索引 — 整塊 splice 會誤刪 Do(CR-01 資料遺失)"
    )

    # (b) 對照組:純零面積 path(無 Do/BT/sh/BI)仍正常入索引(guard 不過度寬鬆)。
    stream_pure = b"q 10 20 m 10 100 l f Q"
    mask_pure = pdf_engine._build_safe_skip_mask(stream_pure)
    index_pure = pdf_engine._build_shape1_candidate_index(
        stream_pure, mask_pure, pdf_engine._DEGENERATE_BBOX_EPS, page_transform
    )
    assert len(index_pure) == 1, (
        "純零面積 path block(無 co-located 內容)仍應正常入索引並被刪除"
    )


@pytest.mark.parametrize("disallowed", [b"Do", b"BT", b"sh", b"BI"])
def test_shape1_block_with_any_disallowed_token_not_indexed(disallowed):
    """CR-01:任一 disallowed token(Do/BT/sh/BI)出現於 block body 都觸發保守跳過。"""
    page_transform = fitz.Identity
    stream = b"q 10 20 m 10 100 l f " + disallowed + b" Q"
    mask = pdf_engine._build_safe_skip_mask(stream)
    index = pdf_engine._build_shape1_candidate_index(
        stream, mask, pdf_engine._DEGENERATE_BBOX_EPS, page_transform
    )
    assert index == {}, (
        f"夾帶 {disallowed!r} 的 q...Q block 不可入索引(CR-01 over-delete guard)"
    )


# --- WR-06: Shape 2 fill-operator 變體 + leading-dot reals + 負 w/h ----------------------
#
# 既有 17 個 fixture 全用 PyMuPDF Shape.draw_rect/draw_line,只 emit 平 `f`。沒有任何
# test 觸及 ``f*`` / ``B`` / ``b`` / ``B*`` / ``b*`` 填色算子變體、leading-dot real
# 運算元、或負 w/h(Pitfall 5)。以下對 raw content-stream 直接驗證 Shape 2 detector
# (鎖定 WR-01 leading-dot + WR-02 dangling-* + Pitfall 5 負 w/h 不誤判)。

@pytest.mark.parametrize("fillop", [b"f", b"f*", b"F", b"B", b"b", b"B*", b"b*"])
def test_shape2_all_fill_operators_indexed(fillop):
    """WR-06:7 個 ISO 32000-1 §8.5.3 填色算子變體下,零面積 ``re`` fill 皆被索引。

    ``0 80 re`` 為零寬(w=0)→ zero-area;每種 fillop 都應命中 Shape 2 detector 並
    產生一筆 byte-range。``f*`` / ``b*`` / ``B*`` 的 ``*`` 必須被完整 capture(WR-02)。
    """
    stream = b"10 20 0 80 re " + fillop
    mask = pdf_engine._build_safe_skip_mask(stream)
    index = pdf_engine._build_shape2_candidate_index(
        stream, mask, pdf_engine._DEGENERATE_BBOX_EPS, fitz.Identity
    )
    assert len(index) == 1, (
        f"零面積 re fill(fillop={fillop!r})應被 Shape 2 索引,實際 index={index!r}"
    )
    # 取出唯一 byte-range,確認它 cover 到整段(含 fillop 尾端的 `*`,WR-02)。
    (byte_range,) = next(iter(index.values()))
    start, end = byte_range
    assert stream[start:end].rstrip().endswith(fillop), (
        f"byte-range 必須含完整 fillop {fillop!r}(WR-02:`*` 不可被遺漏)"
    )


def test_shape2_star_operator_no_dangling_after_splice():
    """WR-02 end-to-end:splice 掉 ``re f*`` fill 後不可遺留 dangling ``*``。

    REVIEW.md 重現:``q 10 20 0 80 re f* Q`` splice 後不可變成 ``q * Q``。
    """
    stream = b"q 10 20 0 80 re f* Q"
    mask = pdf_engine._build_safe_skip_mask(stream)
    index = pdf_engine._build_shape2_candidate_index(
        stream, mask, pdf_engine._DEGENERATE_BBOX_EPS, fitz.Identity
    )
    assert len(index) == 1
    ranges = [r for rs in index.values() for r in rs]
    spliced = pdf_engine._splice_out(stream, ranges)
    assert b"*" not in spliced, (
        f"splice 後不可遺留 dangling `*`(WR-02);實際 spliced={spliced!r}"
    )


def test_shape2_leading_dot_real_operands_indexed():
    """WR-01:leading-dot real 運算元(.5 .061 0 .0 re f)正確解析 bbox 並索引。

    舊 ``-?\\d+\\.?\\d*`` pattern 對 ``.0`` 高度的 re 整段不 match → byte-range 漏抓。
    修正後 ``_NUMBER`` 同時接受 leading-dot real,此零面積(w=0)fill 應被索引。
    """
    stream = b".5 .061 0 .0 re f"
    mask = pdf_engine._build_safe_skip_mask(stream)
    index = pdf_engine._build_shape2_candidate_index(
        stream, mask, pdf_engine._DEGENERATE_BBOX_EPS, fitz.Identity
    )
    assert len(index) == 1, (
        f"leading-dot real re fill 應被 Shape 2 索引(WR-01),實際 index={index!r}"
    )


def test_shape2_negative_wh_not_zero_area_not_indexed():
    """Pitfall 5:負 w/h 不蘊含零面積 —— ``10 20 -5 -80 re f`` 是 5×80 合法矩形,不索引。

    ``re`` 以 ``-5 -80`` 定義的是有面積矩形(往左下展開),abs(w)=5、abs(h)=80 皆
    遠大於 epsilon → 非零面積 → 不可被當零面積 fill 刪除(WR-06 鎖 Pitfall 5)。
    """
    stream = b"10 20 -5 -80 re f"
    mask = pdf_engine._build_safe_skip_mask(stream)
    index = pdf_engine._build_shape2_candidate_index(
        stream, mask, pdf_engine._DEGENERATE_BBOX_EPS, fitz.Identity
    )
    assert index == {}, (
        f"負 w/h 的非零面積矩形不可被索引刪除(Pitfall 5),實際 index={index!r}"
    )
