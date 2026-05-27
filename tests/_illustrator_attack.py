"""Illustrator-class editor 攻擊邏輯 helper module。

本模組封裝「拔 image XObject overlay → 觀察 page content stream 內零面積 type='f'
source 仍會 render 出供應商商標」這個 v1.1 milestone 啟動的 ground-truth 攻擊機制。
邏輯來源:`.planning/debug/scratch/illustrator-attack-2026-05-28/_attack_delete_image_xobject.py`
(2026-05-28 forensic reproduction script,已於該日對 `3013A-13A-C6-XX-3D02-A01-00040.pdf`
證明 Option A raster overlay 可被 Illustrator-class editor 拔除)。

本模組 ``import fitz``。AGPL fitz seam(``app/**/*.py`` AST guard,
``tests/test_redact.py::test_fitz_import_confined_to_engine_seam``)將 ``import fitz``
嚴格限制於 ``app/services/pdf_engine.py``;``tests/`` 目錄不在 guard scope 內,沿用
``tests/conftest.py:12`` 既有 exception(「only the test harness may use fitz
directly to BUILD fixtures」— 此處延伸為「test harness may also use fitz directly
to SIMULATE attack mechanics in regression tests」)。

參 ``.planning/phases/06-regression-foundation-threat-model-re-evaluation/06-PATTERNS.md``
Shared Pattern S1。

Exports
-------

- :func:`delete_image_xobjects_intersecting` — VERBATIM-port 自 scratch lines 40-115;
  in-memory mutate ``fitz.Document`` 拔掉與 rect 相交的 image XObject ``q ... /Im Do
  ... Q`` content-stream block + multi-stream write-back。
- :func:`render_region_white_pct` — VERBATIM-port 自 scratch lines 21-30;
  render 框選區為 pixmap 並回傳白佔比(0.0-100.0,小數 2 位)。
- :func:`count_zero_area_fills_in_region` — open PDF → delegate to production helper
  ``app.services.pdf_engine.count_zero_area_fills_fully_inside``(function-internal
  import,避免 module-load-time 注入 production module 進 tests namespace)。
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # license: test harness exception (mirror tests/conftest.py:12)
import numpy as np


# ----------------------------------------------------------------------------------
# 私有 helpers — VERBATIM-port 自 scratch lines 40-49 + 70-74
# ----------------------------------------------------------------------------------


def _find_image_xrefs_intersecting(page: fitz.Page, rect: fitz.Rect) -> list[int]:
    """回傳該 page 上與 ``rect`` bbox 相交的 image XObject xref 清單。

    VERBATIM 自 ``_attack_delete_image_xobject.py`` lines 40-49 — 邏輯不改寫,以保留
    與 2026-05-28 forensic evidence 的攻擊機制對齊。
    """
    xrefs: list[int] = []
    for img in page.get_images(full=True):
        xref = img[0]
        for bbox in page.get_image_rects(xref):
            if fitz.Rect(bbox).intersects(rect):
                xrefs.append(xref)
                break
    return xrefs


def _resolve_resource_names(page: fitz.Page, xrefs: list[int]) -> set[str]:
    """對 page Resources/XObject map 反查目標 xref 對應的 resource name。

    VERBATIM 自 ``_attack_delete_image_xobject.py`` lines 70-74 — 邏輯不改寫,以保留
    與 2026-05-28 forensic evidence 的攻擊機制對齊。
    """
    names: set[str] = set()
    xref_set = set(xrefs)
    for img_info in page.get_images(full=True):
        xref, _, _, _, _, _, _, name = img_info[:8]
        if xref in xref_set:
            names.add(name)
    return names


# ----------------------------------------------------------------------------------
# Export 1 — Image XObject content-stream surgery
# ----------------------------------------------------------------------------------


def delete_image_xobjects_intersecting(
    doc: fitz.Document,
    page_index: int,
    rect: tuple[float, float, float, float],
) -> int:
    """In-place 拔除 ``doc[page_index]`` 上與 ``rect`` 相交的所有 image XObject。

    攻擊步驟(VERBATIM 自 scratch lines 84-115):

    1. 找與 ``rect`` 相交的 image xrefs(``_find_image_xrefs_intersecting``)。
    2. 解析其 resource names(``_resolve_resource_names``)。
    3. 讀 page content stream(``page.read_contents()``),decode latin-1(byte-preserve)。
    4. 對每個 name 跑兩條 regex 刪除:

       - 主 pattern: ``q\\b[^Q]*?/<name>\\s+Do\\b[^Q]*?Q\\b``(整段 ``q ... Q`` block)
       - bare fallback: ``/<name>\\s+Do\\b``(stray invocations 不在 ``q...Q`` 內)

    5. Multi-stream write-back:single stream → ``update_stream([0])``;multi-stream →
       write modified 至 ``[0]`` + empty 其餘(scratch 不對稱 pattern verbatim,
       per 06-PATTERNS Risk Callout #4)。

    呼叫者保留責任在 mutate 後 ``doc.save(...)`` 落盤;本函式只 mutate in-memory。

    Returns
    -------
    int
        刪除的 image xref 數量(``>= 1`` 才算 attack precondition 成立)。
    """
    rect_obj = fitz.Rect(*rect)
    page = doc[page_index]
    xrefs = _find_image_xrefs_intersecting(page, rect_obj)
    if not xrefs:
        return 0
    names = _resolve_resource_names(page, xrefs)
    if not names:
        return 0

    stream_bytes = page.read_contents()
    stream_text = stream_bytes.decode("latin-1")

    # 主 regex: `q ... /<name> Do ... Q` block — VERBATIM scratch lines 84-94
    for name in names:
        pattern = re.compile(
            r"q\b[^Q]*?/" + re.escape(name.lstrip("/")) + r"\s+Do\b[^Q]*?Q\b",
            re.DOTALL,
        )
        new_text, _n = pattern.subn("", stream_text)
        stream_text = new_text

    # bare fallback: `/<name> Do` 不在 q...Q wrap 內 — VERBATIM scratch lines 96-102
    for name in names:
        bare = re.compile(r"/" + re.escape(name.lstrip("/")) + r"\s+Do\b")
        new_text, _n = bare.subn("", stream_text)
        stream_text = new_text

    # Multi-stream write-back — VERBATIM scratch lines 104-115(不對稱 pattern,
    # 保留兩個 branch 結構而非「整理」為單一 loop,per 06-PATTERNS Risk Callout #4)
    new_bytes = stream_text.encode("latin-1")
    content_xrefs = page.get_contents()
    if len(content_xrefs) == 1:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
    else:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
        for xref in content_xrefs[1:]:
            doc.update_stream(xref, b"", compress=True)

    return len(xrefs)


# ----------------------------------------------------------------------------------
# Export 2 — Region 白佔比 render gate(D-B5 雙閘 (a))
# ----------------------------------------------------------------------------------


def render_region_white_pct(
    pdf_path: Path | str,
    page_index: int,
    rect: tuple[float, float, float, float],
) -> float:
    """Render ``pdf_path`` 第 ``page_index`` 頁上 ``rect`` 區域,回傳白佔比百分比。

    VERBATIM 自 ``_attack_delete_image_xobject.py`` lines 21-30 ``render_region``
    helper 的核心邏輯(scratch 額外存 PNG,此處不需,僅算白佔比)。

    Render 用 ``fitz.Matrix(4, 4)`` 4× zoom + ``clip=rect``(PDF-point rect)+ no
    alpha;白佔比定義為 all-channels ``>= 250`` 的 pixel 數除以總 pixel 數,
    乘 100 + round 2 位小數。

    Returns
    -------
    float
        ``[0.0, 100.0]`` 區間。Phase 6 雙閘 (a):``>= 98.0`` 才算視覺乾淨。
    """
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        pm = page.get_pixmap(
            matrix=fitz.Matrix(4, 4),
            clip=fitz.Rect(*rect),
            alpha=False,
        )
        arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
        return round(100 * np.all(arr >= 250, axis=2).sum() / arr[..., 0].size, 2)
    finally:
        doc.close()


# ----------------------------------------------------------------------------------
# Export 3 — Content-stream 零面積 fill count gate(D-B5 雙閘 (b))
# ----------------------------------------------------------------------------------


def count_zero_area_fills_in_region(
    pdf_path: Path | str,
    page_index: int,
    rect: tuple[float, float, float, float],
) -> int:
    """Open ``pdf_path`` → delegate to production helper
    ``app.services.pdf_engine.count_zero_area_fills_fully_inside``。

    Function-internal import:避免 module-load-time 把 production module 拉進
    tests namespace(也避免 import-order side effect);與 06-PATTERNS Pattern
    Assignments 對齊。

    Returns
    -------
    int
        ``rect`` 內 ``type='f'`` 零面積 fills 數量。Phase 6 雙閘 (b):``== 0`` 才算
        content-stream 乾淨(光看視覺白佔比可能被 fitz 容錯渲染欺騙,參 06-RESEARCH
        Pitfall 8)。
    """
    from app.services import pdf_engine  # 延遲 import — see docstring

    doc = fitz.open(pdf_path)
    try:
        return pdf_engine.count_zero_area_fills_fully_inside(doc[page_index], rect)
    finally:
        doc.close()
