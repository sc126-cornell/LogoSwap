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
