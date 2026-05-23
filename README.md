# LogoSwap — PDF 商標替換工具

把供應商 PDF(含 CAD 設計資料)裡的供應商商標與文字 **真正移除**(而非覆蓋),
換上本司商標,輸出可對外使用的新 PDF。內網部署、瀏覽器手動框選、伺服器端
PyMuPDF 處理。

---

## License & Source(AGPL §13 揭露)

LogoSwap 以 **GNU AGPLv3** 授權。當本工具於網路服務形態提供給使用者時(無論
是否限於內網),AGPLv3 §13 要求對網路使用者揭露完整原始碼。本專案以三件套
滿足該義務:

1. 完整原始碼公開於:`https://github.com/<OWNER>/LogoSwap`
   *(部署前必須將 `<OWNER>` 替換為實際的 public GitHub repo owner;同時更新
   `web/index.html` 內 footer 的同一 placeholder。)*
2. AGPL-3.0 全文見專案根目錄 [`LICENSE`](./LICENSE)。
3. 執行中 UI 右下 footer 包含 GitHub 來源連結與 AGPLv3 授權連結。

授權全文以英文為準。

---

## Architecture(極簡)

FastAPI(`app/`)+ PyMuPDF(redaction 真正移除)+ 純前端 SPA(`web/`,無
build pipeline)。三個部署目標(Zeabur PaaS、本機 Python 套裝、Ubuntu 公司入
口模組)共用同一份 code、同一個 Docker image。

AGPL seam:`import fitz` 只在 `app/services/pdf_engine.py`,其他模組透過
stdlib 與服務介面呼叫,維持未來抽換的彈性。

---

## Deploy Target 1 — Zeabur(短期 PaaS)

**前置(AGPL §13):** 推上 public GitHub repo + 確認 LICENSE 已 commit +
README 的 `<OWNER>` 已替換 + UI footer 的 GitHub URL 已替換。

```bash
# 1) 推到 public GitHub repo
git remote add origin https://github.com/<OWNER>/LogoSwap.git
git push -u origin master

# 2) 在 Zeabur 連接此 repo,Zeabur 會自動偵測 Dockerfile 並 build。
#    Dockerfile 透過 build-arg `GITHUB_OWNER` 把 `<OWNER>` 代入 footer + README
#    內的 GitHub 連結。Zeabur build settings 設 `GITHUB_OWNER=<your-handle>`
#    即可(預設值 `sc126-cornell`)。
# 3) 環境變數設定(預設值見表格):
#       APP_BASE_PATH=""            # Zeabur 走 sub-domain,root mount
#       UVICORN_WORKERS=2
#       DATA_DIR=/data              # Zeabur volume mount
# 4) 部署完成後 Zeabur 提供一個 sub-domain;瀏覽器開啟即用。
```

Zeabur 會自動注入 `$PORT`,Dockerfile 的 `CMD` 已用 `${PORT:-8000}` 接住。

---

## Deploy Target 2 — 本機 Python 套裝(桌面工具)

**用途:** 同事下載專案後在自己電腦上跑 LogoSwap,當作桌面工具使用。跨平台
(Windows / macOS / Linux)。

```bash
# Linux / macOS
git clone https://github.com/<OWNER>/LogoSwap.git
cd LogoSwap
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app
# 瀏覽器自動開到 http://127.0.0.1:8000
```

```powershell
# Windows PowerShell
git clone https://github.com/<OWNER>/LogoSwap.git
cd LogoSwap
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app
# 瀏覽器自動開到 http://127.0.0.1:8000
```

**注意事項:**

- 預設 host 為 `127.0.0.1`(loopback only,T-05-09)— 不對外網開放。
- `UVICORN_NO_BROWSER=1` 可關閉自動開瀏覽器(CI / headless 場景)。
- 預設 workers=1(桌面單人使用足夠);需要時 `UVICORN_WORKERS=2 python -m app`。
- 資料目錄預設 `./data/`,即 repo 內;`DATA_DIR=/some/path python -m app` 可改。

---

## Deploy Target 3 — Ubuntu 公司入口網站功能模組

**起點:** `docker-compose.example.yml`。複製為 `docker-compose.yml` 並依環境
調整。

```bash
cp docker-compose.example.yml docker-compose.yml
docker compose up -d
curl http://localhost:8000/health     # 五欄位 JSON
```

公司主 nginx 反向代理選項:

**(a) Strip-prefix 模式(實驗性,Pitfall 5):** 在 LogoSwap 容器設
`APP_BASE_PATH=/pdf-logo`,公司主 nginx 設:

```nginx
location /pdf-logo/ {
    proxy_pass http://app:8000/;            # 結尾 / 表 strip prefix
    proxy_read_timeout 90s;
    proxy_send_timeout 90s;
    client_max_body_size 60m;               # > MAX_UPLOAD_BYTES (50MB)
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

FastAPI 的 `root_path` + StaticFiles(`html=True`) 在某些 strip-prefix 配置
下有 redirect 行為差異(upstream #12151)。**部署前請以實際 proxy 路徑做端
到端測試**,確認上傳、框選、套用、下載四個動線都通。

**(b) Sub-domain 模式(推薦,穩定):** 把 LogoSwap 放在獨立 sub-domain
(例:`pdf-logo.internal`),`APP_BASE_PATH` 保留空字串(root mount)。避免
strip-prefix 的所有 redirect 邊角情境,長期維運成本最低。

---

## Environment Variables

| Variable | Default | 範例 / 說明 |
|----------|---------|-------------|
| `DATA_DIR` | `./data` | Session 暫存目錄;Docker 內 `/data`(VOLUME) |
| `LOGOS_DIR` | `./logos` | 固定商標庫位置;Docker 內 `/app/logos` |
| `APP_BASE_PATH` | `""` | FastAPI `root_path`;`""` = root mount,`/pdf-logo` = 配合 strip-prefix proxy(D-A2) |
| `UVICORN_WORKERS` | `2`(Docker)/ `1`(`python -m app`) | Worker 數;Zeabur free tier 可降到 1 |
| `PROCESS_TIMEOUT_SECONDS` | `60` | /process 超時上限(Plan 05-02 啟用) |
| `SESSION_TTL_SECONDS` | `3600` | Session 暫存壽命(Plan 05-02 janitor 啟用) |
| `CORS_ALLOW_ORIGINS` | `""` | 逗號分隔的 origin 白名單;預設關閉(Plan 05-02 預埋) |
| `MAX_UPLOAD_BYTES` | `52428800` | 上傳檔大小上限(50MB) |
| `MAX_PAGES` | `30` | 上傳 PDF 頁數上限 |
| `PORT` | `8000` | 監聽 port;Zeabur 會注入 |
| `HOST` | `127.0.0.1`(`python -m app`)/ `0.0.0.0`(Docker) | 監聽 host;`python -m app` 永遠 loopback |
| `UVICORN_NO_BROWSER` | unset | 設任意值即不自動開瀏覽器 |

---

## Embedding Contract

LogoSwap 設計為可被既有公司入口網站嵌入。兩個 knob:

- **`window.PDFTOOL_API_BASE`(前端 seam,Phase 1 鎖定)** — 在 host 頁面
  注入此 global 前載入 `js/api.js`,即可將所有 API 呼叫導向不同 base URL。
- **`APP_BASE_PATH`(後端 seam,Phase 5)** — 啟動時設定的 env var,寫入
  FastAPI 的 `root_path`,讓 OpenAPI / 路由皆帶 prefix。

兩個 knob 通常 **只設其一**:走 sub-domain 不設 prefix;走 strip-prefix
proxy 才設 `APP_BASE_PATH`。

---

## Known Limitations

- **AGPL §13 對網路使用者揭露原始碼。** 即使部署在內網,只要透過網路提供服
  務,§13 義務仍然成立。本工具用三件套滿足(LICENSE + public GitHub URL
  + UI footer);外部可達網路部署前必須再次確認 OWNER URL 已替換、repo 為
  public。
- **Session TTL 1 小時(Plan 05-02 啟用)。** 上傳後 1 小時內必須完成下載,
  否則暫存被清理需要重新上傳。
- **/process 60 秒 timeout(Plan 05-02 啟用)。** 大型 / 旋轉頁面採用
  WR-06 自動降 DPI,但極端情況仍可能 timeout。
- **大型 / 旋轉 PDF 自動降 DPI(WR-06)。** 單頁渲染像素總數會被截到
  `MAX_RENDER_PIXELS`(40MP);此為記憶體保護,不影響輸出 PDF 的品質。
- **FastAPI `root_path` + StaticFiles redirect quirk(Pitfall 5)。** 預設
  `APP_BASE_PATH=""`(root mount)為穩定路徑;`/pdf-logo` 等 prefix 模式為
  實驗性,部署前必須以實際 proxy 測過。
- **v1 內網免登入。** 對外網部署前需加 basic auth 或 reverse-proxy 層的存取
  控制(v2 AUTH-01)。

---

## Build & Test

```bash
pytest tests/                              # 全部單元 + 整合測試
docker build -t logoswap .                 # Build image
docker run -p 8000:8000 -v $(pwd)/data:/data logoswap   # 跑 image
curl http://localhost:8000/health          # 五欄位 JSON 健康檢查
```

---

*Phase 1–4 完成於 2026-05-23;Phase 5 為部署與穩固化階段。*
