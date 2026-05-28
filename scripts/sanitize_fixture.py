"""一次性 dev 工具:把工程師交付的真實 supplier CAD-glyph PDF 脫敏為可 commit 進 public repo 的 fixture。

用途(Phase 6 D-A4 鎖定):
    供應商 PDF 含商標 + metadata 機密,**不可** commit 進 public repo(AGPL §13 lockfile)。
    本工具讀入 raw supplier PDF,執行 4 件脫敏動作後輸出 sanitized PDF + sidecar JSON manifest:

      Step 1 — Metadata 清空(`/Info` dict + XMP stream 雙清,涵蓋 RESEARCH Pitfall 2 邊界)
      Step 2 — 找原 brand glyph union bbox + 記錄基準 zero-area count(self-assert 用)
      Step 3 — Brand-glyph 整塊 content-stream surgery(`update_stream` multi-stream pattern)
      Step 4 — TESTCO 零面積 wordmark 注入(`Shape.draw_rect(W=0)` + `shape.commit()`,
                Option B verbatim per PATTERNS S4;**不**做 supplier-name find-replace
                主路徑 — 留給 fallback,checker Blocker #1)
      Step 5 — Self-assert(4 條:metadata 空、supplier name 不在 get_text()、
                zero-area count ≥ 0.9 × 原 count、out path 必在 tests/fixtures/cad-glyph/)
      Step 6 — `doc.save(garbage=4, deflate=True, clean=True)`

與 AGPL guard 關係:
    `scripts/` 不在 AGPL fitz guard scope(該 guard 只掃 `app/**/*.py`,參
    `tests/test_redact.py::test_fitz_import_confined_to_engine_seam` AST 實作)。
    本檔直接 `import fitz` 是 PATTERNS Shared Pattern S1 + tests/conftest.py:12 的同一例外。

為何 raw PDF 不可 commit:
    public repo 對外可讀,raw 含原供應商 IP / metadata / 商標字串 + 視覺。Sanitize 後僅保留
    「同型 zero-area type='f' attack 面」(用於 Illustrator-class attack 紅燈 regression),
    視覺、metadata、可 decode 文字皆已洗去。

Sidecar manifest schema:
    本工具產出的 sidecar JSON 採 **split-coordinate schema** — 同時寫
    `region_rect_pdf_points`(供 fitz.Rect / count_zero_area_fills_fully_inside 用)與
    `region_rect_px`(供 RegionMark.px_rect 用,= pdf_points × dpi / 72.0)。此為 Phase 6
    canonical schema,取代 CONTEXT D-B4 範例中的單一 `region_rect`(Claude's Discretion on
    manifest schema per CONTEXT § Claude's Discretion);Phase 7 unit tests / consumer code
    對齊本 schema(PATTERNS Warning #8)。

    Zero-area count fields(WR-01 修復後 — 三欄並存):

    - `expected_zero_area_count_pre_process`(LEGACY,backward-compat):
        real-mode = 原 supplier 在 sanitize 動手前 count;
        synthetic-mode = save 之後 count(兩種模式語義不同 — 保留以免破壞既有 manifest)。
    - `original_supplier_zero_area_count`(NEW;real-mode 才有非 null 值):
        原 supplier 在 sanitize 動手前 count(明確命名)。synthetic 模式為 null。
    - `expected_zero_area_count_post_build`(NEW;real + synthetic 雙模都有):
        sanitized PDF save 後重新讀回的 count。**Phase 7 / future consumer 應優先使用**。

CLI 用法:
    python scripts/sanitize_fixture.py \
        --in raw-supplier.pdf \
        --out tests/fixtures/cad-glyph/text-glyph-01.pdf \
        --supplier-name "ACME_SUPPLIER_INC" \
        --region-rect "602,481,827,511" \
        --page-index 0 \
        --dpi 144

    # Synthesize 模式(fallback;CONTEXT § specifics 工程師延遲交付 contingency):
    python scripts/sanitize_fixture.py \
        --synthesize \
        --out tests/fixtures/cad-glyph/text-glyph-01.pdf \
        --region-rect "100,100,300,200" \
        --dpi 144
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

# Ensure repo root importable when run as `python scripts/sanitize_fixture.py` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Print CJK cleanly on Windows console (cosmetic; avoids mojibake in CLI output).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 — older / non-reconfigurable streams: leave as-is.
    pass

import fitz  # AGPL guard scope = app/**/*.py only — scripts/ is OUT of scope, fitz import here is safe.

# Production helper for self-assert (D-A3 驗證點). Import does NOT count as production-code
# modification — call site is in scripts/, the production file is untouched.
from app.services import pdf_engine  # noqa: E402


# ---------------------------------------------------------------------------
# CLI arg parsing
# ---------------------------------------------------------------------------


def _parse_region_rect(s: str) -> tuple[float, float, float, float]:
    """解析 ``"x0,y0,x1,y1"`` 為 4-tuple of floats。

    失敗時 raise argparse.ArgumentTypeError(由 parser 統一轉成 exit code != 0)。
    此為 V5 ASVS input validation(per PATTERNS L26 + RESEARCH Security Domain)+
    Warning #7 self-assert reachable proof 的 entry point。
    """
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"--region-rect 必須是 4 個逗號分隔的數字(x0,y0,x1,y1);收到 {len(parts)} 個 token: {s!r}"
        )
    try:
        x0, y0, x1, y1 = (float(p) for p in parts)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"--region-rect 解析失敗 — 每個 token 必須是 float;收到 {s!r}({e})"
        )
    if x1 <= x0 or y1 <= y0:
        raise argparse.ArgumentTypeError(
            f"--region-rect 必須是 x1>x0 且 y1>y0 的正向 rect;收到 ({x0},{y0},{x1},{y1})"
        )
    return (x0, y0, x1, y1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Argparse parser — D-A4 的 4 個必要 args + 數個 optional。"""
    parser = argparse.ArgumentParser(
        description="脫敏 supplier CAD-glyph PDF 為 public-repo-safe fixture(Phase 6 TEST-01)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        type=Path,
        default=None,
        help="輸入的 raw supplier PDF 路徑(必要;--synthesize 模式下省略)",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        type=Path,
        required=True,
        help="輸出的 sanitized PDF 路徑(必要;MUST 是 tests/fixtures/cad-glyph/ 底下)",
    )
    parser.add_argument(
        "--supplier-name",
        dest="supplier_name",
        type=str,
        default=None,
        help="原供應商名(必要;用於 self-assert get_text 不含此字串;--synthesize 模式預設 SYNTHETIC_TESTCO)",
    )
    parser.add_argument(
        "--region-rect",
        dest="region_rect",
        type=_parse_region_rect,
        required=True,
        help='框選區 PDF points "x0,y0,x1,y1"(必要;解析失敗 exit 1)',
    )
    parser.add_argument(
        "--page-index",
        dest="page_index",
        type=int,
        default=0,
        help="page index(default 0)",
    )
    parser.add_argument(
        "--dpi",
        dest="dpi",
        type=int,
        default=144,
        help="DPI for sidecar manifest region_rect_px(default 144;對齊 RegionMark.px_rect 慣例)",
    )
    parser.add_argument(
        "--synthesize",
        dest="synthesize",
        action="store_true",
        help="Fallback 合成模式 — 從零建構 PDF(供應商 PDF 延遲交付的 contingency,RESEARCH Open Question 1)",
    )
    args = parser.parse_args(argv)

    # 後驗:若非 synthesize,--in 與 --supplier-name 為必要。
    if not args.synthesize:
        if args.in_path is None:
            parser.error("非 --synthesize 模式必須提供 --in")
        if args.supplier_name is None:
            parser.error("非 --synthesize 模式必須提供 --supplier-name")
    else:
        if args.supplier_name is None:
            args.supplier_name = "SYNTHETIC_TESTCO"

    return args


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_git_sha() -> str:
    """回傳目前 HEAD 短 SHA;若不在 git repo 或 git 不可用,回 'unknown'。"""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        return out.decode("ascii").strip()
    except Exception:  # noqa: BLE001
        return "unknown"


_USER_METADATA_FIELDS = (
    "author",
    "producer",
    "title",
    "keywords",
    "subject",
    "creator",
    "creationDate",
    "modDate",
    "trapped",
)

# Allowlist of fields PyMuPDF derives from PDF structure (NOT /Info content); these
# are intentionally non-empty even on a "fully cleared" doc — `set_metadata` does
# not clear them and **should** not. Anything in doc.metadata NOT in this set is
# treated as `/Info` content (potentially leaked supplier IP).
_COMPUTED_METADATA_FIELDS = frozenset({"format", "encryption"})


def _metadata_all_empty(doc: fitz.Document) -> bool:
    """Allow-list check:doc.metadata 中所有非 computed 欄位 MUST 為 None / 空字串 / b""。

    [CR-01 修復 — 2026-05-28] 舊版以 ``_USER_METADATA_FIELDS`` 9-key denylist 逐欄
    ``md.get(field)`` 檢查;若供應商 PDF 帶 hardcoded 9 key 之外的 ``/Info`` key
    (e.g. ``PTEX.Fullbanner``、custom XMP-surface key),denylist 看不到 → self-assert
    成 no-op → leaked supplier IP 可能 commit 進 public repo,違反 README §4 AGPL §13
    statement(``tests/fixtures/cad-glyph/README.md:72-78``)。

    本 allowlist 版本反向:迭代 ``doc.metadata.items()`` 的實際 keys,凡不在
    ``_COMPUTED_METADATA_FIELDS``(``format``、``encryption`` 由 PDF 結構推斷)
    的欄位皆須空。任何 stray supplier-injected key 都會被攔下。
    """
    md = doc.metadata or {}
    for field, value in md.items():
        if field in _COMPUTED_METADATA_FIELDS:
            continue
        if value not in (None, "", b""):
            return False
    return True


def _find_brand_glyph_union_bbox(
    page: fitz.Page, region: tuple[float, float, float, float]
) -> tuple[fitz.Rect, int]:
    """走 page.get_drawings(),取與 region 有交集的 type='f' fill 之 union bbox,
    同時回傳「框選區內 zero-area type='f' fill 的數量」(self-assert 基準)。

    若一個 fill 都沒有 → 回傳 (region 自身 Rect, 0)。
    """
    q = fitz.Rect(*region)
    q.normalize()
    union: fitz.Rect | None = None
    for drawing in page.get_drawings():
        if drawing.get("type") != "f":
            continue
        d_rect = drawing.get("rect")
        if d_rect is None:
            continue
        dr = fitz.Rect(d_rect)
        dr.normalize()
        if not fitz.Rect(*region).intersects(dr):
            continue
        union = dr if union is None else (union | dr)

    if union is None:
        union = q
    # zero-area count via production helper(D-A3 驗證點 + AGPL seam 合法 import 路徑)
    zero_count = pdf_engine.count_zero_area_fills_fully_inside(page, region)
    return union, zero_count


def _inject_testco_zero_area_wordmark(
    page: fitz.Page,
    anchor: fitz.Rect,
    n_target: int,
) -> int:
    """在 anchor 內鋪 n_target 個 zero-width 縱線(W=0 → zero-area type='f' fill)。

    Pattern verbatim per PATTERNS S4 + tests/test_redact.py:722-728。回傳實際 commit 的數量。

    Args:
        page: fitz.Page(已經完成 brand-glyph strip,內部 cache 應在 caller side 重讀)
        anchor: 原 brand glyph union bbox(Step 2 取得)— TESTCO bbox 必須 ⊂ region_rect
                (per RESEARCH Pitfall 7;caller 已保證 anchor ⊂ region)
        n_target: 目標數量(typically 原 zero-area count × 0.95)
    """
    if n_target < 1:
        n_target = 1
    x_start = anchor.x0
    x_end = anchor.x1
    y_top = anchor.y0
    y_bot = anchor.y1
    # 防 anchor degenerate(寬高 0)— 退化的話就在 region 中央放一條
    if x_end <= x_start:
        x_end = x_start + 1.0
    if y_bot <= y_top:
        y_bot = y_top + 1.0

    committed = 0
    span = x_end - x_start
    step = span / max(n_target, 1)
    for i in range(n_target):
        x = x_start + i * step
        # 確保 x 在 anchor 內(防浮點漂移)
        if x >= x_end:
            x = x_end - 1e-6
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x, y_top, x, y_bot))  # W=0 → zero-area type='f' fill
        shape.finish(fill=(0.0, 0.0, 0.0), color=None, width=0)
        shape.commit()
        committed += 1
    return committed


def _strip_brand_glyph_block(
    doc: fitz.Document, page: fitz.Page, union_bbox: fitz.Rect
) -> int:
    """Step 3 — Brand-glyph 整塊 content-stream surgery。

    最簡可行:採用 Implementation note A 的「最內層 m/l/f/B 算子序列 byte offset 範圍刪除」
    的退路 — 對 CAD-glyph supplier brand,union_bbox 在 content stream 內通常對應到一段
    `q ... <m/l/f ops with coords inside union_bbox> ... Q` 的 block。本實作採保守路徑:

      a) decode content stream 為 latin-1
      b) 找所有 q...Q wrap 區塊(`re.finditer(r"q\\b[^Q]*?Q\\b", text, DOTALL)`)
      c) 對每個 block,看內部是否含「至少一個座標落在 union_bbox 內的 m/l 算子」
      d) 命中 → 把整個 q...Q block 刪掉
      e) 用 PATTERNS S1(scratch lines 104-115)的 multi-stream `update_stream` 寫回

    回傳被刪 block 數;0 代表 surgery 沒命中(Implementation note B fallback 由 caller 觸發)。

    對 multi-stream page:scratch script 已 proven「write modified to [0],write b'' to [1:]」
    pattern(Pitfall 3)。

    **WR-04 已知限制(2026-05-28 documented):**
    本啟發式只比對 ``m`` / ``l`` 算子的「原始操作數」與 ``union_bbox``(page-coord)。
    它**忽略** ``cm``(CTM 變換矩陣)— 若 brand 區塊以
    ``1 0 0 1 700 490 cm 0 0 m 10 0 l ...`` 形式出現(先 translate,再用 local-coord
    繪製),regex 看到的座標是 ``(0, 0)`` / ``(10, 0)``,**不落在** page-coord
    ``union_bbox`` 內 → 該 block **不會被 strip** → fallback 走 CMap supplier-name
    find-replace(對純字串 supplier name 有效;對 glyph-encoded brand 仍可能漏)。

    2026-05-28 的 forensic 樣本 ``3013A-13A-C6-XX-3D02-A01-00040.pdf`` 對此啟發式
    work(N=1),但只要新真實 supplier PDF 用 CTM 變換,就會曝光此限制。

    **未來修復方案(>30 行,故 Phase 6 不實作 — 留 TODO):**
    Option 2 per 06-REVIEW.md WR-04 — 改用 ``page.get_drawings()`` 已給出的
    bbox(已 cm-aware),直接以 bbox intersects union_bbox 作 hit test,不再自行
    parse 算子。需要對齊 ``get_drawings()`` 回傳的 drawing 對應到 content stream
    哪段 byte offset(目前 PyMuPDF 沒直接 expose)— 需 reverse-map,或改用
    bottom-up rebuild(對所有 type='f' fills 中與 union_bbox 不相交者 keep,
    其餘 strip)。實作預估 30-50 行 + 需要對 multi-fixture 樣本驗證;
    Phase 7+ 接手實作。
    """
    stream_bytes = page.read_contents()
    stream_text = stream_bytes.decode("latin-1")
    original_len = len(stream_text)

    # 找所有 q...Q wrap 區塊。CAD-glyph PDF 通常每組 brand 在獨立的 q...Q 內。
    # 用 non-greedy + DOTALL 抓最近的 Q;若有巢狀 q...Q,可能漏抓 — 對 CAD title block
    # supplier brand 已 proven 足夠(scratch script 2026-05-28 在 3013A-...pdf 驗證)。
    q_block_re = re.compile(rb"q\b[^Q]*?Q\b", re.DOTALL)

    # 算子座標 regex:`<float> <float> [m|l]`(moveto / lineto with x y operand)
    # 此 byte-offset 啟發式:若 block 內任一 m/l 座標落在 union_bbox 內(PDF 點座標),
    # 視為 brand-glyph block。
    # WR-04 LIMITATION:此 regex 不解析 `cm`(CTM)— 若 brand block 用 cm 變換 +
    # local-coord m/l,operand 不會落在 union_bbox 內;見上方 docstring「已知限制」。
    coord_re = re.compile(
        rb"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+[ml]\b"
    )

    blocks_to_strip: list[tuple[int, int]] = []  # (start, end) byte ranges
    raw_bytes = stream_text.encode("latin-1")
    for m in q_block_re.finditer(raw_bytes):
        block_bytes = m.group(0)
        hit = False
        for cm in coord_re.finditer(block_bytes):
            try:
                x = float(cm.group(1))
                y = float(cm.group(2))
            except ValueError:
                continue
            if (
                union_bbox.x0 <= x <= union_bbox.x1
                and union_bbox.y0 <= y <= union_bbox.y1
            ):
                hit = True
                break
        if hit:
            blocks_to_strip.append((m.start(), m.end()))

    if not blocks_to_strip:
        return 0

    # 從尾部往前刪以保留前段 offset 有效。
    new_bytes = raw_bytes
    for start, end in reversed(blocks_to_strip):
        new_bytes = new_bytes[:start] + new_bytes[end:]

    # Multi-stream write-back(PATTERNS S1 scratch lines 104-115 verbatim shape)。
    content_xrefs = page.get_contents()
    if len(content_xrefs) == 1:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
    else:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
        for xref in content_xrefs[1:]:
            doc.update_stream(xref, b"", compress=True)
    _ = original_len  # 留作 debug print 對齊 scratch 行為的可選 hook
    return len(blocks_to_strip)


def _cmap_fallback_supplier_name_replace(
    doc: fitz.Document, page: fitz.Page, supplier_name: str
) -> bool:
    """Implementation note B(CMap-encoded fallback)。

    若 Step 5 self-assert 發現 supplier_name 仍出現於 page.get_text(),代表 brand-glyph
    block strip 漏掉了文字 run(supplier 可能用 CMap encoding)。最後一道 content-stream
    find-replace pass:`stream_text.replace(supplier_name, "TESTCO")`。

    Returns True iff at least one replacement was made.
    """
    if not supplier_name:
        return False
    stream_bytes = page.read_contents()
    stream_text = stream_bytes.decode("latin-1")
    new_text = stream_text.replace(supplier_name, "TESTCO")
    if new_text == stream_text:
        return False
    new_bytes = new_text.encode("latin-1")
    content_xrefs = page.get_contents()
    if len(content_xrefs) == 1:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
    else:
        doc.update_stream(content_xrefs[0], new_bytes, compress=True)
        for xref in content_xrefs[1:]:
            doc.update_stream(xref, b"", compress=True)
    return True


def _write_manifest(
    out_path: Path,
    region_rect: tuple[float, float, float, float],
    dpi: int,
    page_index: int,
    expected_zero_area_count_pre_process: int,
    supplier_name: str,
    *,
    synthetic: bool,
    original_supplier_zero_area_count: int | None = None,
    expected_zero_area_count_post_build: int | None = None,
) -> Path:
    """寫 sidecar JSON manifest(split-coordinate schema)。

    返回 manifest 路徑。

    Field semantics(WR-01 修復 — 2026-05-28):

    - ``expected_zero_area_count_pre_process``(LEGACY,backward-compat 保留):
      在 real-supplier 模式下 = 原 supplier PDF 在 sanitize 動手前的 zero-area count;
      在 synthetic 模式下 = 從零建構的 PDF 在 save 之後的 zero-area count
      (兩種模式語義不同 — 為避免破壞已 commit 的 manifest schema 而保留)。

    - ``original_supplier_zero_area_count``(NEW,real-mode 才寫):
      原 supplier PDF 在 sanitize 動手前的 zero-area count(明確命名,real-mode only)。
      synthetic 模式下永遠為 ``null``。

    - ``expected_zero_area_count_post_build``(NEW,雙模式都寫):
      sanitized PDF save 之後重新讀回的 zero-area count;Phase 7 / 未來 consumer
      應優先使用此欄位作 "canonical count the test should assert against"。
    """
    x0, y0, x1, y1 = region_rect
    px_scale = dpi / 72.0
    manifest = {
        "region_rect_pdf_points": [x0, y0, x1, y1],
        "region_rect_px": [x0 * px_scale, y0 * px_scale, x1 * px_scale, y1 * px_scale],
        "dpi": dpi,
        "page_index": page_index,
        "expected_zero_area_count_pre_process": int(expected_zero_area_count_pre_process),
        "original_supplier_zero_area_count": (
            int(original_supplier_zero_area_count)
            if original_supplier_zero_area_count is not None
            else None
        ),
        "expected_zero_area_count_post_build": (
            int(expected_zero_area_count_post_build)
            if expected_zero_area_count_post_build is not None
            else None
        ),
        "original_supplier_name_sha256": (
            "sha256:" + hashlib.sha256(supplier_name.encode("utf-8")).hexdigest()[:16]
        ),
        "sanitization_script_commit_sha": _short_git_sha(),
        "created_at_iso": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "synthetic": synthetic,
    }
    manifest_path = out_path.with_suffix(".json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:  # noqa: C901 — linear recipe, deliberately one fn
    args = parse_args(argv)
    out_path: Path = args.out_path
    region_rect: tuple[float, float, float, float] = args.region_rect
    page_index: int = args.page_index
    supplier_name: str = args.supplier_name
    dpi: int = args.dpi

    # Out-path containment guard — V5 + Anti-Pattern「Raw supplier PDF accidentally committed」
    # 同時也是 acceptance criteria 的 hard self-assert(Warning #7)。
    out_str = str(out_path).replace("\\", "/")
    if "tests/fixtures/cad-glyph/" not in out_str:
        print(
            f"錯誤:--out 必須在 tests/fixtures/cad-glyph/ 底下;收到 {out_path}",
            file=sys.stderr,
        )
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.synthesize:
        return _run_synthesize_mode(
            out_path=out_path,
            region_rect=region_rect,
            page_index=page_index,
            supplier_name=supplier_name,
            dpi=dpi,
        )

    # 主路徑(real supplier PDF)
    in_path: Path = args.in_path
    if not in_path.exists():
        print(f"錯誤:--in 檔案不存在:{in_path}", file=sys.stderr)
        return 1

    print(f"開啟 raw supplier PDF: {in_path}")
    doc = fitz.open(in_path)
    try:
        if page_index >= len(doc):
            print(
                f"錯誤:--page-index {page_index} 超出 doc 頁數 {len(doc)}",
                file=sys.stderr,
            )
            return 1
        page = doc[page_index]

        # Step 1 — Metadata 清空(/Info + XMP 雙清)
        # [Rule 1 deviation] PyMuPDF 1.27.2.3 行為:`doc.set_metadata({})` 傳空 dict
        # **不清** 任何欄位(視為 no-op),與 RESEARCH Pattern 1 引用的「1.18.4 起空值不寫」
        # 行為不符 — 1.27 系列要求顯式每個欄位設空字串。下方先呼叫 `doc.set_metadata({})`
        # 為文件化 intent(及 acceptance criteria grep 對齊),再以 per-field 空字串
        # dict 實際清空。實證 verified 2026-05-28 with PyMuPDF 1.27.2.3 on 3013A-...pdf。
        print("步驟 1/6:清空 metadata 與 XMP …")
        doc.set_metadata({})  # intent marker(1.27 上為 no-op;見上方註解)
        doc.set_metadata({k: "" for k in _USER_METADATA_FIELDS})  # 實際清空
        try:
            doc.set_xml_metadata("")
        except Exception as e:  # noqa: BLE001 — 某些 PDF 無 XMP stream,呼叫可能 no-op or raise
            print(f"  (XMP set_xml_metadata 警告 — 視為無 XMP:{e})")
        print(f"  ✓ metadata 清空({len(doc.metadata or {})} 欄)")

        # Step 2 — 找原 brand glyph union bbox + 記錄基準 zero-area count
        print("步驟 2/6:定位原 brand glyph union bbox + 記錄基準 zero-area count …")
        union_bbox, original_zero_area_count = _find_brand_glyph_union_bbox(
            page, region_rect
        )
        print(
            f"  ✓ union bbox = {tuple(round(v, 2) for v in (union_bbox.x0, union_bbox.y0, union_bbox.x1, union_bbox.y1))}; "
            f"原 zero-area count = {original_zero_area_count}"
        )
        # 防 union_bbox 越界 region_rect — clip 至 region 內(per RESEARCH Pitfall 7)
        region_fitz = fitz.Rect(*region_rect)
        clipped = union_bbox & region_fitz
        if clipped.is_empty or not clipped.is_valid:
            # 若交集空,退而求其次:用 region_rect 自身作為 anchor
            union_bbox = region_fitz
        else:
            union_bbox = clipped

        # Step 3 — Brand-glyph 整塊 content-stream surgery
        print("步驟 3/6:Brand-glyph 整塊 content-stream surgery(update_stream)…")
        stripped = _strip_brand_glyph_block(doc, page, union_bbox)
        print(f"  ✓ 已 strip {stripped} 個 q...Q block")

        # 重新讀 page 確保 fitz 內部 cache 與新 content stream 對齊
        page = doc[page_index]

        # Step 4 — TESTCO 零面積 wordmark 注入(Shape API,Option B verbatim)
        print("步驟 4/6:注入 TESTCO 零面積 wordmark(Shape.draw_rect W=0 + shape.commit)…")
        # WR-05 修復:用 math.ceil 而非 int(floor),避免小 count(如 original=2)時
        # int(2 * 0.95) = int(1.9) = 1,而 self-assert 門檻 0.9 * 2 = 1.8 要求 ≥ 2,
        # 導致 reproducible self-assert failure。ceil(2 * 0.95) = ceil(1.9) = 2 → 通過。
        n_target = max(math.ceil(original_zero_area_count * 0.95), 1)
        committed = _inject_testco_zero_area_wordmark(page, union_bbox, n_target)
        print(f"  ✓ 已 commit {committed} 個 zero-area type='f' fill(目標 {n_target})")

        # Step 5 — Self-assert(in-memory,pre-save)
        print("步驟 5/6:Self-assert …")
        if not _metadata_all_empty(doc):
            print(
                f"錯誤:Self-assert metadata-empty 失敗:doc.metadata = {doc.metadata}",
                file=sys.stderr,
            )
            return 1
        print("  ✓ metadata 全空")

        text_after = page.get_text()
        if supplier_name in text_after:
            print(
                f"⚠ supplier name CMap fallback 觸發,正在套用 find-replace ...",
                file=sys.stderr,
            )
            _cmap_fallback_supplier_name_replace(doc, page, supplier_name)
            page = doc[page_index]
            text_after = page.get_text()
            if supplier_name in text_after:
                print(
                    f"錯誤:CMap fallback 後 supplier_name {supplier_name!r} 仍出現於 get_text()",
                    file=sys.stderr,
                )
                return 1
        print(f"  ✓ supplier_name {supplier_name!r} 不在 get_text()")

        post_zero_area_count = pdf_engine.count_zero_area_fills_fully_inside(
            page, region_rect
        )
        # 90% 門檻(per D-A3)— 原 count 為 0 的特殊情況:只要 ≥1 即視為 pass
        # (synthetic-flavoured PDF 例外由 --synthesize 路徑處理,本主路徑不該發生 zero count)
        if original_zero_area_count == 0:
            if post_zero_area_count < 1:
                print(
                    f"錯誤:Self-assert post-zero-area count 失敗:原 0,後 {post_zero_area_count} < 1",
                    file=sys.stderr,
                )
                return 1
        else:
            threshold = 0.9 * original_zero_area_count
            if post_zero_area_count < threshold:
                print(
                    f"錯誤:Self-assert post-zero-area count 失敗:後 {post_zero_area_count} < 0.9 × {original_zero_area_count} = {threshold:.1f}",
                    file=sys.stderr,
                )
                return 1
        print(
            f"  ✓ post zero-area count {post_zero_area_count} ≥ 0.9 × {original_zero_area_count}"
        )

        # Out-path containment 已在前置驗過,但 redundancy 是 safety
        if "tests/fixtures/cad-glyph/" not in out_str:
            print(
                f"錯誤:Self-assert out path 失敗:{out_path} 不在 tests/fixtures/cad-glyph/",
                file=sys.stderr,
            )
            return 1
        print("  ✓ out path 在 tests/fixtures/cad-glyph/")

        # Step 6 — Save + close
        print("步驟 6/6:save(garbage=4, deflate=True, clean=True)…")
        doc.save(str(out_path), garbage=4, deflate=True, clean=True)
        print(f"  ✓ sanitized PDF written: {out_path}")
    finally:
        doc.close()

    # WR-01 修復:real-supplier mode 同時寫 legacy + 明確命名雙欄位。
    # post_zero_area_count 已在 self-assert 區段(line ~565)算過,沿用其值。
    manifest_path = _write_manifest(
        out_path=out_path,
        region_rect=region_rect,
        dpi=dpi,
        page_index=page_index,
        expected_zero_area_count_pre_process=original_zero_area_count,
        supplier_name=supplier_name,
        synthetic=False,
        original_supplier_zero_area_count=original_zero_area_count,
        expected_zero_area_count_post_build=post_zero_area_count,
    )
    print(f"  ✓ sidecar manifest written: {manifest_path}")
    print("完成。")
    return 0


def _run_synthesize_mode(
    *,
    out_path: Path,
    region_rect: tuple[float, float, float, float],
    page_index: int,
    supplier_name: str,
    dpi: int,
) -> int:
    """`--synthesize` 模式 — 從零建構 PDF(contingency only,RESEARCH Open Question 1)。

    D-A1 鎖定不採合成 PDF 作 primary;此模式僅在工程師延遲交付 supplier PDF 時使用,
    且 Phase 6 close 必須標 PROVISIONAL(per Warning #6,由 caller 同步處理 README + STATE + SUMMARY)。
    """
    print(f"⚠ --synthesize 模式(contingency):從零建構 PDF → {out_path}")
    doc = fitz.open()
    try:
        # A4 page
        page = doc.new_page(width=595.0, height=842.0)
        # 確保 page_index 對齊
        for _ in range(page_index):
            doc.new_page(width=595.0, height=842.0)
        page = doc[page_index]

        # Step 1 — Metadata 確保為空
        doc.set_metadata({k: "" for k in _USER_METADATA_FIELDS})
        try:
            doc.set_xml_metadata("")
        except Exception:  # noqa: BLE001
            pass

        # Step 4(skip 2/3 — 無原 brand glyph)— 在 region_rect 內鋪 120 個 zero-area fill
        n_target = 120  # hardcoded — well above ZERO_AREA_RASTER_THRESHOLD(100)
        anchor = fitz.Rect(*region_rect)
        committed = _inject_testco_zero_area_wordmark(page, anchor, n_target)
        print(f"  ✓ 已 commit {committed} 個 zero-area type='f' fill")

        # Self-assert(縮減版 — 無原 supplier name)
        if not _metadata_all_empty(doc):
            print(
                f"錯誤:synthetic mode metadata-empty self-assert 失敗:{doc.metadata}",
                file=sys.stderr,
            )
            return 1

        post_count = pdf_engine.count_zero_area_fills_fully_inside(page, region_rect)
        if post_count < 1:
            print(
                f"錯誤:synthetic mode post zero-area count = {post_count} < 1",
                file=sys.stderr,
            )
            return 1
        print(f"  ✓ synthetic post zero-area count = {post_count}")

        doc.save(str(out_path), garbage=4, deflate=True, clean=True)
        print(f"  ✓ synthetic PDF written: {out_path}")
    finally:
        doc.close()

    # 重新開啟讀回 post_count 以寫入 manifest
    doc = fitz.open(out_path)
    try:
        page = doc[page_index]
        post_count_final = pdf_engine.count_zero_area_fills_fully_inside(
            page, region_rect
        )
    finally:
        doc.close()

    # WR-01 修復:synthetic mode 沒有「pre-process supplier count」概念 — legacy 欄位
    # 沿用 post_count_final(向後相容),original_supplier_zero_area_count=None,
    # expected_zero_area_count_post_build=post_count_final(consumer 應優先看此欄)。
    manifest_path = _write_manifest(
        out_path=out_path,
        region_rect=region_rect,
        dpi=dpi,
        page_index=page_index,
        expected_zero_area_count_pre_process=post_count_final,
        supplier_name=supplier_name,
        synthetic=True,
        original_supplier_zero_area_count=None,
        expected_zero_area_count_post_build=post_count_final,
    )
    print(f"  ✓ synthetic sidecar manifest written: {manifest_path}")
    print("完成(synthetic mode — Phase 6 close 為 PROVISIONAL)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
