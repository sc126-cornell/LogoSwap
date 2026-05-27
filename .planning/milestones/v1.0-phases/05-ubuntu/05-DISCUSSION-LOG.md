# Phase 5: 部署與穩固化(Ubuntu) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-23
**Phase:** 5-ubuntu
**Areas discussed:** 容器拓撲 + Nginx 部署形態、暫存檔清理 (janitor) 機制、原始檔 SHA-256 雜湊驗證 (SC #3)、大型/旋轉頁面 — 同步 vs 背景工作

---

## 容器拓撲 + Nginx 部署形態

### Q1: 灰色地帶選擇(多選)

| Option | Description | Selected |
|--------|-------------|----------|
| 容器拓撲 + Nginx 部署形態 | 單容器 / docker-compose 雙容器 / 雙模式並存,影響 Dockerfile / CORS / TLS / 嵌入 prefix | ✓ |
| 暫存檔清理 (janitor) 機制 | data dir 累積問題,同步 / 背景 / cron 容器 / 啟動掃 | ✓ |
| 原始檔 SHA-256 雜湊驗證 | 雜湊存哪、何時驗、失敗行為 | ✓ |
| 大型/旋轉頁面 — 同步 vs 背景工作 | sync workers vs BackgroundTasks vs process pool | ✓ |

**User's choice:** 全部四個都討論,並補充部署優先順序「1. Zeabur, 2. Python 程式(如果可以的話), 3. Ubuntu」+ Ubuntu 將作為公司入口網站功能模組。

---

### Q2: 「Python 程式」是指?

| Option | Description | Selected |
|--------|-------------|----------|
| uvicorn 直接跑 Python-friendly PaaS / VPS,不打 Docker | 例如 Render / Fly / VM | |
| 提供可下載的 Python 套裝給內部使用者本機跑 | desktop-style 本機工具 | ✓ |
| 在公司現有 Python 伺服器以 venv 跑 | 走 venv,不動 OS 套件 | |

**User's choice:** 可下載的 Python 套裝給內部使用者本機跑。
**Notes:** 這影響後續 Dockerfile 設計 — image 不能是唯一交付物;需有「不裝 Docker 也能跑」的 path。

---

### Q3: Nginx 反向代理安排?

| Option | Description | Selected |
|--------|-------------|----------|
| App image 不含 Nginx — 推薦 | uvicorn 直接 8000 port + static 走 FastAPI mount;Zeabur LB / Ubuntu 公司 nginx 在外面接 | ✓ |
| Ubuntu docker-compose 外加 nginx,Zeabur 不加 | 雙 image 模式 + nginx.conf 範例 | |
| App image 內含 nginx + supervisor 單容器重型 | 重型,debug 麻煩 | |

**User's choice:** App image 不含 nginx(推薦)。
**Notes:** 外部反向代理由部署目標自己處理,image 維持單一責任。

---

### Q4: 嵌入公司入口網站的 URL prefix 策略?

| Option | Description | Selected |
|--------|-------------|----------|
| Root mount + 公司 nginx strip prefix | App 自認在 / | 由 Claude 決定 |
| App 支援 APP_BASE_PATH env var | FastAPI root_path 帶 prefix | 由 Claude 決定 |
| iframe 嵌入獨立 sub-domain | App root mount,host 用 iframe | 由 Claude 決定 |

**User's choice:** 「請你決定」+「後續真的整合的時候,都還可以調整對不對?」
**Notes:** Claude 採折衷方案:**預設 root mount + 可選 `APP_BASE_PATH` env var**(三條嵌入路徑都支援,整合時可調)。確認 API-first seam(`window.PDFTOOL_API_BASE`,Phase 1 已埋)讓未來整合幾乎零改動。

---

### Q5: Docker image 打包結構?

| Option | Description | Selected |
|--------|-------------|----------|
| 多階段 Dockerfile + 本機可不用 Docker — 推薦 | python:3.12-slim build + runtime,~250MB;本機 pip + uvicorn | ✓ |
| 單階段 + slim base | 簡單但稍肥 | |
| Distroless / Alpine | < 100MB 但 PyMuPDF wheel 需 glibc、debug 麻煩 | |

**User's choice:** 多階段 Dockerfile + 本機可以不用 Docker。

---

## 暫存檔清理 (janitor) 機制

### Q1: Janitor 何時觸發?

| Option | Description | Selected |
|--------|-------------|----------|
| App 內建背景定時(asyncio task 或 APScheduler)— 推薦 | startup 起 task 每 X 分鐘掃 | |
| /process 結尾 + 啟動掃 | 同步觸發 + 啟動掃一次 | ✓ |
| 外部 cron 容器 / systemd timer | 部署環境另外設定 | |

**User's choice:** /process 結尾 + 啟動掃。
**Notes:** Claude 補加「/sessions 上傳時也順手掃」避免只預覽不處理的場景累積。

---

### Q2: Session 多久後算「可清」?

| Option | Description | Selected |
|--------|-------------|----------|
| 24 小時 — 推薦 | 一個工作日內完成 | |
| 1 小時 — 縣快狀態 | 處理一本下載一本 | ✓ |
| 7 天 — 寬鬆保留 | 隨時回來;但累積大 | |

**User's choice:** 1 小時。
**Notes:** 內部工具,處理完下載完就不需保留。

---

### Q3: Active session 能不能保護不被清?

| Option | Description | Selected |
|--------|-------------|----------|
| 有活動就 touch — 推薦 | GET / process 都 update mtime,1h 沒動才清 | |
| 硬 1h — 不記 last access | upload 後 1h 不管在不在用,清 | ✓ |

**User's choice:** 硬 1h - 不記 last access。
**Notes:** 簡單透明;前端應在 upload 後顯示 TTL 提示 + 失效時友善 404 訊息(Plan 細節)。

---

### Q4: Janitor 動 session dir 範圍?

| Option | Description | Selected |
|--------|-------------|----------|
| 三個同時刪(originals + work + pristine + outputs)— 推薦 | 1h 後 4 個 kind 全清 | ✓ |
| outputs 保留 24h,其他 1h | 「我明天才來下載」可行 | |
| 刪 originals + pristine,work + outputs 保留 | 複雜,難預期 | |

**User's choice:** 三個同時刪(推薦)。

---

## 原始檔 SHA-256 雜湊驗證 (SC #3)

### Q1: 雜湊存哪、怎麼存?

| Option | Description | Selected |
|--------|-------------|----------|
| work/{sid}/meta.json 多 original_sha256 欄位 — 推薦 | 沿用既有 sidecar,一檔不增 | ✓ |
| 獨立 sidecar originals/{sid}/source.pdf.sha256 | 同位被刪同步刪;多一檔 | |
| /process 時才挑雜湊 + 存 sidecar(不預寫) | lazy,但中間被竄改抓不到 baseline | |

**User's choice:** work/{sid}/meta.json 多一個 original_sha256 欄位。

---

### Q2: Runtime 何時驗證?

| Option | Description | Selected |
|--------|-------------|----------|
| 每次 /process 前 — 推薦 | 定點,50MB SHA-256 ~100–200ms 可接受;不一致 → 503 | ✓ |
| 每次 GET /sessions/{id} 都驗 | 多。讀項都驗 SHA-256 成本上漲 | |
| 只提供 POST /admin/verify 手動 | 隱藏,SC #3「雜湊驗證未被竄改」效力不足 | |

**User's choice:** 每次 /process 前。

---

### Q3: 驗證失敗反應?

| Option | Description | Selected |
|--------|-------------|----------|
| 503 中止 + 結構化 log + 標記 session corrupted — 推薦 | sentinel file 之後所有 op 中止 | ✓ |
| 503 中止 + log,不 quarantine | 下次仍可重試 | |
| 只 log,不中止 | 走 SC #3「未被竄改」保證 | |

**User's choice:** 503 中止 + 結構化 log + 標記 session corrupted。

---

### Q4: pristine/ 也要雜湊驗證嗎?

| Option | Description | Selected |
|--------|-------------|----------|
| 只驗 originals — 推薦 | SC #3 字面偏 user-facing「原始」 | ✓ |
| originals + pristine 都驗 | 防 internal,但低危險 + 程式碼 / sidecar 重複 | |

**User's choice:** 只驗 originals。

---

## 大型 / 旋轉頁面 — 同步 vs 背景工作

### Q1: /process 同步 vs 背景?

| Option | Description | Selected |
|--------|-------------|----------|
| 保持同步,uvicorn workers >= 2 + timeout / pixel 上限 — 推薦 | 最小改動,沿用 fit_dpi_to_pixel_budget,加 timeout + workers | ✓ |
| BackgroundTasks + job_id polling | 大重構;v1 內部工具不需 | |
| 同步 + ProcessPoolExecutor 子進程隔離 | Pitfall 11 推薦但 v1 不值得 | |

**User's choice:** 保持同步 + workers >= 2 + timeout / pixel 上限。

---

### Q2: /process timeout 多少秒?

| Option | Description | Selected |
|--------|-------------|----------|
| 60 秒 + env var — 推薦 | PROCESS_TIMEOUT_SECONDS 可調,對齊 nginx default 60s | ✓ |
| 30 秒 — 炸住 Zeabur 預設 | Zeabur free tier ~30s,app/external 對齊 | |
| 120 秒 — 寬鬆,適合大 CAD | 但 UX 等 2 分鐘不好,且外部代理可能先 504 | |

**User's choice:** 60 秒 + env var(PROCESS_TIMEOUT_SECONDS)。

---

### Q3: uvicorn workers 數量?

| Option | Description | Selected |
|--------|-------------|----------|
| Default = 2 + env var — 推薦 | UVICORN_WORKERS 可調;一個被 /process 佔另一個還能預覽 | ✓ |
| Default = 1 | RAM 低但預覽會被阻塞 | |
| Default = 4 + env var | RAM 多;Zeabur free 不適合 | |

**User's choice:** Default = 2 + env var UVICORN_WORKERS。

---

### Q4: Dockerfile HEALTHCHECK + /health?

| Option | Description | Selected |
|--------|-------------|----------|
| Dockerfile 加 HEALTHCHECK + /health 加強回傳欄位 — 推薦 | 30s interval,/health 回 status + uptime + sessions + disk usage | ✓ |
| 不加 HEALTHCHECK,只保留 /health endpoint | 外部 LB 自己 poll | |

**User's choice:** Dockerfile 加 HEALTHCHECK + /health 加強欄位。

---

## Claude's Discretion

- AGPL UI source link 確切位置與文案、`LICENSE` 檔內容(AGPL-3.0 全文)— memory 已鎖定方向,文案 / 位置 / repo URL 交由 researcher / planner。
- CORS 允許清單:預埋 `CORS_ALLOW_ORIGINS=""` env var,需要時設。
- 本機 Python 套裝啟動腳本(`app/__main__.py` 含 `webbrowser.open()`)+ 跨平台 README + 可選 PyInstaller(視 fitz 套件可行性)。
- 結構化日誌:v1 內部工具可先用 uvicorn default,需要時升級。
- Pillow `Image.MAX_IMAGE_PIXELS` 全域 set(可選 startup 對齊 config)。
- `docker-compose.example.yml` 範例(repo 附 example,不放 default)。
- `DATA_DIR` 在 Docker 走 `/data` volume、本機走 `~/.logoswap/data` 或 `./data`(researcher 視 cross-platform 決定)。
- Phase 5 plan 切法(roadmap 建議 05-01 部署 + 05-02 穩固化,planner 可細調)。

## Deferred Ideas

- /process 改背景 + job_id polling(若 Zeabur 強制 < 60s 或 UAT 反映等太久,v1.x 再做)。
- ProcessPoolExecutor 子進程隔離 PyMuPDF(Pitfall 11)— v1 信任 internal。
- APScheduler / background asyncio task janitor(若同步不足以清)。
- last-access touch / active session 保護(若使用者抱怨被誤清)。
- Outputs TTL 與 originals 拆開(若使用者要明天才下載)。
- pristine/ SHA-256 雜湊驗證(若 internal incident)。
- POST /admin/verify endpoint 手動驗證。
- TLS / HTTPS 終結內建(永遠交給部署環境)。
- Distroless / Alpine base image。
- Prometheus / OpenTelemetry 監控(out-of-scope v1)。
- PyInstaller Windows exe(視 fitz 套件可行性)。
- rate limiting / per-IP cap(內網不需)。
- Pillow MAX_IMAGE_PIXELS 全域 set(Claude 裁量)。
- OCG / hidden layer 處理(Phase 4 deferred / Pitfall 8)。
