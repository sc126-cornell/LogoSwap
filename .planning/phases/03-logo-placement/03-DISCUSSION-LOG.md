# Phase 3: 商標置入 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 3-logo-placement
**Areas discussed:** Logo 對應區域, 區域內貼合對齊, 商標庫內容格式, 選擇器與預覽

---

## Logo 對應區域 (Logo-to-region mapping)

| Option | Description | Selected |
|--------|-------------|----------|
| 全區同一 logo | 套用後所有移除區域都置入同一個選定 logo;JobSpec 加一個全域 logo_id | ✓ |
| 逐區開關/可不同 | 逐一指定哪些區域放、放哪個 logo;regions 需加 per-region logo 欄位,UI 較複雜 | |
| 移除框與置入框分開 | 置入位置獨立於移除框另外框選;最彈性但等於兩套框選流程 | |

**User's choice:** 全區同一 logo(建議)
**Notes:** 符合「移除供應商標 → 在同一位置換我司標」的核心用途;契約改動最小。

---

## 區域內貼合對齊 (Fit & alignment)

| Option | Description | Selected |
|--------|-------------|----------|
| 框內置中、完整顯示 | 維持長寬比縮到框內、置中,不符處自然留白(insert_image keep_proportion 預設) | ✓ |
| 靠左上對齊 | 縮到框內但靠左上角對齊,而非置中 | |
| 置中,細節交給你 | 先用置中;對齊/留白/內距細節由實作決定 | |

**User's choice:** 框內置中、完整顯示(建議)
**Notes:** keep_proportion 為 LOGO-02 鎖定需求。

---

## 商標庫內容格式 (Library content & format)

| Option | Description | Selected |
|--------|-------------|----------|
| PNG 去背、多版本 | PNG 含 alpha;v1 可放多個版本(水平/直式/深淺),manifest.json 帶 id/檔名/顯示名/尺寸 | ✓ |
| 單一 PNG 公司標 | 庫裡只放一個去背 PNG,不分版本 | |
| 需支援 SVG | insert_image 不直接吃 SVG,需先轉點陣,複雜度與相依↑ | |

**User's choice:** PNG 去背、多版本(建議)
**Notes:** SVG 列入 deferred;庫為固定唯讀資產,v1 由管理者放檔。

---

## 選擇器與預覽 (Picker & preview)

| Option | Description | Selected |
|--------|-------------|----------|
| 側欄縮圖 + 預覽含 logo | 選擇器=側欄縮圖網格;下載前在現有「移除結果」對照中就渲染出 logo(原圖 / 移除+置入結果) | ✓ |
| 工具列下拉 + 預覽含 logo | 選擇器改放工具列下拉;預覽一樣顯示已置入的 logo | |
| 預覽不含 logo,僅下載可見 | 結果預覽只顯示移除;logo 只在下載的 PDF 看得到 | |

**User's choice:** 側欄縮圖 + 預覽含 logo(建議)
**Notes:** 延伸現有 after-image,讓使用者下載前確認 logo 位置/大小。

---

## Claude's Discretion

- 縮圖網格版面細節、選取狀態樣式、側欄確切位置
- `manifest.json` 精確 schema/欄位
- 未選 logo 時的行為(預設純移除)與按鈕狀態
- 更換 logo / 變更選取是否使既有結果失效(沿用 Phase 2「編輯使結果失效、需重新套用」模式)
- logo alpha 邊緣渲染細節、商標庫的種子內容(可先放 placeholder)

## Deferred Ideas

- per-region 不同 logo / 逐區開關置入 — v1.x
- 移除框與置入框分開(獨立置入位置)— v1.x
- SVG 向量 logo 支援(需轉點陣)— 視需求再議
- logo 透明度/旋轉/拖曳微調、框內對齊切換 — 目前固定置中 contain
- 商標上傳 UI(自助新增 logo 到庫)— v1 由管理者放檔
- 點陣圖/掃描型 PDF 與獨立影像檔的 logo 置入 — Phase 4
