# HANDOFF — 給接手 LogoSwap 的同事

這份文件是寫給「要把 LogoSwap 整合進公司內部簽核網站的開發者」的快速上手與決
策指南。專案的公開文件(部署、環境變數、限制清單)在 [`README.md`](./README.md);
本文件補充 README 沒寫的三件事:**整合路徑的決策樹、AGPL 在不同整合方式下的
含義、核心領域知識備忘**。

---

## 1. 這個工具在做什麼(30 秒版)

供應商提供的產品設計 PDF(含 CAD)裡有他們的商標與文字。LogoSwap 讓使用者在
瀏覽器中手動框選要處理的位置,把那塊區域 **真正移除**(不是覆蓋一個白色矩
形),再貼上本司商標,輸出可對外使用的新 PDF。

**核心價值就是「真正移除」這四個字。** 如果只是用白色矩形蓋掉,供應商的文字
/向量物件仍在 PDF 檔案結構裡,可以被任何 PDF 工具還原。LogoSwap 用 PyMuPDF
的 `apply_redactions` 真正刪除這些底層物件 — 這是整個專案存在的理由,任何替
代實作(換 lib、改流程)都必須維持這個性質。

---

## 2. 三條整合路徑(決策樹)

選哪一條取決於「你想付多少整合工」與「你能接受多少 AGPL 風險」。

### 路徑 A — Microservice 部署(推薦預設)

LogoSwap 維持為獨立服務(沿用現有 Dockerfile),公司主網站只當 reverse proxy
或 iframe host。

- **整合工作量:** 低 — 設個 nginx location、決定 sub-domain 還是 strip-prefix
  (README "Deploy Target 3" 章節已涵蓋)
- **UI 整合度:** iframe 嵌入,樣式融合差;若同事自己做 UI 呼叫 API 則可控
- **AGPL 含義:** **乾淨** — PyMuPDF 的 AGPL 義務止於這個獨立服務,不會感染公
  司主網站 codebase。即使將來決定對外開放,只要這個 service 本身的 source 公
  開即可,公司網站本體不受影響。

### 路徑 B — 前端融入 + 後端獨立

同事在公司主網站重做 LogoSwap 的前端 UI(讓視覺風格一致),後端 FastAPI 維持
獨立部署、透過 REST API 呼叫。

- **整合工作量:** 中 — 前端要重寫(可參考現有 `web/` 的 PDF.js 用法與座標換
  算邏輯),後端不動
- **UI 整合度:** 高 — 跟公司網站樣式完全一致
- **AGPL 含義:** **乾淨** — 前端只是 API client,不引入 PyMuPDF;後端維持獨立
  AGPL 邊界。跟路徑 A 的 AGPL 含義相同。

### 路徑 C — 完全融入公司 codebase

把 LogoSwap 的 Python 程式碼直接搬進公司主網站的 repo,變成一個 module。

- **整合工作量:** 高 — 需要協調依賴(PyMuPDF、Pillow、numpy)、設定、資料目
  錄、路由、測試
- **UI 整合度:** 最高
- **AGPL 含義:** **這條是法律地雷,除非滿足下面任一條件,否則不要走:**
  1. 公司願意把整合後的網站 codebase 也以 AGPL 公開,或
  2. 公司向 Artifex 購買 PyMuPDF 商業授權(按年計費),或
  3. 即使技術上「融入 codebase」,在程式碼結構上仍把 PyMuPDF 的呼叫限縮在一
     個可辨識的子模組裡(例如 `pdf_processing/` 子套件),其他部分透過明確
     的 service interface 呼叫 — 留住未來把該子模組抽出為獨立 service 的退
     路,降低 AGPL 感染範圍的爭議。

**建議:** 走 A 或 B。除非有強烈業務理由,不要走 C。

---

## 3. AGPL 注意事項(必讀)

目前的部署計畫是「公司內網、只有公司員工存取、Zeabur 公開部署即將關閉」。在
這個情境下 **AGPL §13 不會觸發**:同一法人實體內部員工不算 §13 所指的「網路
使用者」。但這個豁免有四個前提,任何一個改變都要重新 review:

| 觸發情境 | 何時會發生 | 重新 review 的內容 |
|---|---|---|
| **外部使用者存取** | 外包工程師、合作廠商、客戶 demo | §13 重新生效,需公開 source 或買商業授權 |
| **子公司 / 關係企業使用** | 跨法人實體存取 | 算 conveying,GPL/AGPL 義務生效 |
| **公司被併購或拆分** | M&A 完成日 | 新法人取得 = conveying,要附 source |
| **改成 SaaS 對外銷售** | 任何商業化決定 | §13 全面生效,實務上必須買商業授權 |

無論走哪條整合路徑,**這三件事不能省**:

1. **保留 `LICENSE` 檔案**(repo 根目錄的 AGPL-3.0 全文)— AGPL §4 最低要求,
   即使內部用、即使不公開 repo 都不能刪。
2. **不要 fork PyMuPDF 內部去改它的 source** — 純粹 `import fitz` 用它的公開
   API 是安全的;一旦 fork 並修改 PyMuPDF 本身,那份修改嚴格說即使內部用也要
   可取得。
3. **在公司內部文件記錄「這個服務用了 AGPL component」** — 未來任何上述觸發情
   境出現時(尤其 M&A 或對外 demo),法務/採購要能快速找到這個事實,不要靠
   口耳相傳。

---

## 4. Docker 部署

沿用既有 Dockerfile,**不需要重 build**。完整步驟見:

- README ["Deploy Target 3 — Ubuntu 公司入口網站功能模組"](./README.md) — Docker
  compose、nginx 反向代理(sub-domain vs strip-prefix)兩種模式都有
- README ["Environment Variables"](./README.md) — 所有可調 env var
- `docker-compose.example.yml` — 起手範本

**內部部署的最小決定清單:**

- Sub-domain 模式還是 strip-prefix 模式 — 推薦 sub-domain(README 已說明 root
  cause:FastAPI `root_path` + StaticFiles 在 strip-prefix 下有 redirect 邊角行為)
- `DATA_DIR` 指到一個 host volume(session 暫存 1 小時自動清,但仍需 persistent
  以承受 container restart)
- `LOGOS_DIR` 指到本司商標庫(read-only mount 即可)
- 是否需要 auth — v1 設計為內網免登入;若公司主網站本身有 SSO,整合在反向代
  理層處理(LogoSwap 不需要自己懂 auth)

---

## 5. API 整合契約

FastAPI 自動產生 OpenAPI schema,**這是最權威的 API 文件,不要手寫一份競爭文
件**:

- **互動式 docs(Swagger UI):** 啟動服務後 `http://<host>/docs`
- **OpenAPI JSON:** `http://<host>/openapi.json`

關鍵 endpoint(細節以 OpenAPI 為準):

| Endpoint | 用途 |
|---|---|
| `POST /upload` | 上傳 PDF,回傳 session id |
| `GET /preview/{session}/{page}` | 取得指定頁的預覽圖(PDF.js fallback) |
| `POST /process` | 提交框選區域 + 商標選擇,執行 redaction + insert_image |
| `GET /download/{session}` | 下載處理後的 PDF |
| `GET /logos` | 列出可用的本司商標 |
| `GET /health` | 五欄位健康檢查(部署 smoke test 用) |

**前端嵌入(若走路徑 B):** README "Embedding Contract" 章節說明
`window.PDFTOOL_API_BASE`(前端 seam)與 `APP_BASE_PATH`(後端 seam)的兩個
knob,**通常只設其一**:走 sub-domain 不設 prefix;走 strip-prefix proxy 才設
`APP_BASE_PATH`。

---

## 6. 核心領域知識備忘(避免踩雷)

接手後若要動到 PDF 處理邏輯、座標系、或考慮換套件,先讀這節。

### 6.1 為何用 PyMuPDF 而非 pypdf / PyPDF2

pypdf 只能對 PDF 做結構性操作(merge / split / metadata),**沒有「真正移除指
定區域內容」的能力**。如果用 pypdf 加一個白色矩形,供應商的文字/向量物件仍
在檔案裡,可以被任何 PDF 工具還原 — 這違反專案核心價值。

PyMuPDF 的 `page.add_redact_annot(rect)` + `page.apply_redactions(text=...,
graphics=..., images=...)` 才能真正刪除底層物件。任何「換掉 PyMuPDF」的提案都
必須先回答:替代品如何達成相同的真正移除語意。

### 6.2 Redaction 真正移除原理

```
1. page.add_redact_annot(rect, fill=(1,1,1))   ← 標記要刪的矩形
2. page.apply_redactions(                       ← 這一步才真正刪除
       text=PDF_REDACT_TEXT_REMOVE,             ← 矩形內的文字物件被移除
       graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,  ← 完全被蓋的向量被移除
       images=PDF_REDACT_IMAGE_PIXELS,          ← 重疊像素被塗白
   )
3. page.insert_image(rect, filename=logo_path)  ← 貼上本司商標
4. doc.save(new_path, garbage=4, deflate=True)  ← 永遠存新檔,不覆蓋原檔
```

關鍵在第 2 步:`apply_redactions` 是真正修改 PDF 物件樹,不是繪製覆蓋。
`graphics=` 與 `images=` 的選項可調(`REMOVE_IF_TOUCHED` vs
`REMOVE_IF_COVERED`),影響「碰到邊就刪」還是「完全被蓋才刪」的行為 — milestone
v1.0 hotfix 06 調校過(dCt-residue Option A),動之前先看
`app/services/pdf_engine.py` 的 commit history。

### 6.3 PDF.js viewport 座標換算(前端碰之前必讀)

PDF 內部座標(point, 原點左下)和瀏覽器像素座標(pixel, 原點左上)不一樣,加
上縮放、旋轉,自己手算非常容易錯,**錯了會 redact 到錯誤位置 — 而且因為是
「真正移除」,錯了無法挽回**。

正確做法:用 PDF.js 提供的 `PageViewport.convertToPdfPoint(x, y)` 把使用者拖出
的矩形角點(像素)轉成 PDF point,送到後端;後端拿到的就是可以直接餵給
`add_redact_annot(rect)` 的 PDF point 矩形。反向用 `convertToViewportPoint`。

**絕對不要在前端自己寫 `x / scale - offsetX` 這種手算** — 旋轉頁面就會錯。

### 6.4 「永遠存新檔」是硬性規則

`doc.save()` 永遠寫到新路徑,**從不覆蓋上傳的原檔**。原檔(在 session
`DATA_DIR` 內)只供使用者反悔重做、或 debug 對照。Session TTL 1 小時清掉,不
會無限累積。

這條規則寫進 STRIDE 威脅模型,動 `pdf_engine.py` 或 `app/routes/process.py` 之
前確認不破壞。

---

## 7. 接手後第一週建議

1. **跑起來** — `docker compose up -d`,上傳一個樣本 PDF 走一遍 upload → 框選
   → process → download,確認本機環境 OK
2. **跑測試** — `pytest tests/` 應該 301 passed + 3 skipped(milestone v1.0
   close 時的數字;若有變動先 git log 看是否有後續修改)
3. **讀三個檔** — `app/services/pdf_engine.py`(核心 redaction)、
   `app/routes/process.py`(API entrypoint)、`web/js/main.js`(前端框選 + 座
   標換算)
4. **決定整合路徑** — 參考第 2 節決策樹,跟主網站架構師對齊
5. **法務知會** — 把第 3 節 AGPL 注意事項轉達給法務 / 採購,確認沒有後續觸發
   情境潛伏

---

## 8. 還有問題?

- 部署層問題:看 README
- API 行為:看 `/docs` (OpenAPI Swagger UI)
- 為什麼這樣設計:看 `.planning/PROJECT.md` 和 `.planning/milestones/v1.0-*.md`
  (歷史決策與威脅模型)
- 找不到答案:對接原作者
