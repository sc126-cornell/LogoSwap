# Phase 5: 部署與穩固化(Ubuntu) - Context

**Gathered:** 2026-05-23
**Status:** Ready for planning

<domain>
## Phase Boundary

把現有 FastAPI + PyMuPDF + 純前端 SPA 打包成可在 **三個部署目標**(優先順序 1. Zeabur 短期 PaaS、2. 可下載 Python 套裝給內部使用者本機跑、3. Ubuntu 公司入口網站功能模組,長期)上跑的網頁服務。Phase 5 的核心交付:

1. **多階段 Dockerfile**(app image)+ 本機可不用 Docker 跑(`pip install -r requirements.txt` + uvicorn / `python -m app`)— 三個目標共用同一份程式碼。
2. **暫存清理 janitor**:`data/{originals,work,outputs,pristine}/{sid}/` 1 小時 TTL,同步觸發(/process 結尾 + /sessions 上傳時 + app startup),不引入 background scheduler / cron。
3. **原始檔 SHA-256 雜湊驗證(SC #3)**:ingest 時計算 + 存入 `work/{sid}/meta.json` 的 `original_sha256` 欄位;每次 /process 前驗證 `originals/source.pdf` 雜湊一致;不一致 → 503 `original_tampered` + structured log + 標記 session corrupted。
4. **大型 / 旋轉頁面承載穩固化**:沿用既有 `fit_dpi_to_pixel_budget`(WR-06 pixel ceiling)+ derotation_matrix(0/90/180/270 已 Phase 2 驗證 < 1px 往返);新增 /process timeout(60s default,env `PROCESS_TIMEOUT_SECONDS`)+ uvicorn workers default 2(env `UVICORN_WORKERS`)。
5. **AGPL §13 合規前置**:public GitHub repo + LICENSE(AGPL-3.0)+ UI 提供原始碼連結(memory 鎖定的部署前提)。
6. **API base 嵌入彈性**:預設 root mount;支援可選 `APP_BASE_PATH` env var → FastAPI `root_path`,前端 `window.PDFTOOL_API_BASE` seam(Phase 1 已有)沿用。

**Carrying forward(前期已決定,不再討論):**
- AGPL seam:`import fitz` 僅在 `app/services/pdf_engine.py`(Phase 1–4 enforced by test)。
- Deferred-mutation 三目錄(originals / work / outputs / pristine)+ originals chmod 0o444。
- 既有限額已就位:`MAX_UPLOAD_BYTES=50MB`、`MAX_PAGES=30`、`MAX_REGIONS=200`、`MAX_RENDER_PIXELS=40MP`、`MAX_INGEST_IMAGE_PIXELS≈89MP`、`MIN/MAX_DPI=72/300`、`fit_dpi_to_pixel_budget` 自動降階(WR-06)、JPEG_REENCODE_QUALITY=90。
- `/health` 端點存在(回 `{"status":"ok"}`),Phase 5 加強回傳欄位 + Dockerfile HEALTHCHECK 指向它。
- `web/js/api.js` 唯一 server seam + `window.PDFTOOL_API_BASE` 覆寫(API-first 嵌入契約,Phase 1 鎖定)。
- 雙主題 token + 繁中文案(Phase 1 UI-SPEC)。
- 整份 90° 旋轉(Phase 3 UAT 鎖定)。
- Commit/push 節奏:UAT 期間 local commit、不 push;hotfix inline;最終 code-review 後才推(memory 鎖定)。

**不含(歸其他階段 / out-of-scope):**
- 帳號登入 / 權限控管(v2 AUTH-01,memory 鎖定 v1 內網免登入)。
- 批次多檔處理(v2 BATCH-01)。
- 真正嵌入公司入口網站的整合工作(Phase 5 只預埋 API-first seam;實際嵌入是 v1.x / v2 INTEG-01)。
- 自動偵測商標位置 / OCR / inpainting / per-region 不同模式(明確 out-of-scope)。
- TLS / HTTPS 終結(交給 Zeabur LB / Ubuntu 公司 nginx,不在 app image 內)。
- 結構化監控 / Prometheus / OpenTelemetry(memory 鎖定 v1 不導入)。
- 多容器 Docker compose 在 app image 內預打包(交給部署目標自己編排;repo 可附 docker-compose.yml 範例 — Claude 裁量)。

</domain>

<decisions>
## Implementation Decisions

### 容器拓撲 + 部署形態 (Container topology & deploy targets)
- **D-A1:** **App image 不含 nginx**,uvicorn 直接服 static(`web/`)+ API。外部反向代理(Zeabur LB / Ubuntu 公司 nginx)是部署目標自己的事,**不在 image 內負擔反向代理 / TLS / supervisor**。理由:Zeabur 通常無法部署雙容器、Ubuntu 公司入口網站本來就有主 nginx — 把這個責任留給部署環境最乾淨,維護成本最低。
- **D-A2:** **預設 root mount**;同時支援可選 `APP_BASE_PATH` env var(空字串 = root,否則如 `/pdf-logo`)→ 啟動時帶入 FastAPI `root_path`,OpenAPI / static 路徑同步加上 prefix。前端 `web/js/api.js` 的 `window.PDFTOOL_API_BASE` seam(Phase 1 已有)沿用,**前端零改動**就能配合三種嵌入模式:(a) iframe 獨立 sub-domain、(b) 公司 nginx `location /pdf-logo/ { proxy_pass http://app:8000/; }` 走 strip prefix、(c) FastAPI `root_path` 帶 prefix。整合時都可調整。
- **D-A3:** **多階段 Dockerfile**(`python:3.12-slim` build stage:`pip install --target /install`;runtime stage:COPY /install + app/ + web/ + logos/ + entrypoint)。**本機可以不用 Docker** 跑 — 從 git clone + venv + `pip install -r requirements.txt` + `uvicorn app.main:app` 或 `python -m app`(可能新增一個 `app/__main__.py` 包 uvicorn 啟動 + 自動 `webbrowser.open()` 開瀏覽器)。三個部署目標(Zeabur / 可下載 Python 套裝 / Ubuntu)同一份 code。Slim base 已足;不走 distroless / Alpine(PyMuPDF wheel 需 glibc)。
- **D-A4:** **部署順序鎖定**:1. **Zeabur** 短期單容器 PaaS;2. **可下載 Python 套裝** 給內部使用者本機跑(desktop-style 工具,git tag 標 release + README 含 venv + uvicorn 指令、Windows / macOS / Linux 一致流程);3. **Ubuntu** 公司入口網站功能模組(長期,使用 strip-prefix / iframe / sub-domain 任一種嵌入)。

### 暫存清理 janitor (Temp file cleanup)
- **D-B1:** **同步觸發 janitor**(不引入 background scheduler / cron / APScheduler / asyncio task)。三個觸發點:
  - (a) **app startup** 掃一次 `data/{originals,work,outputs,pristine}/{sid}/` 全部 sid,清過期者;
  - (b) **/sessions POST 結尾**(避免「只預覽不處理」的場景累積);
  - (c) **/process 結尾**(順手清自己 + 一些舊的)。
- **D-B2:** **TTL = 1 小時(硬上限,不 touch last-access)**。mtime > 1h 的 `{sid}/` directory 在四個 kind(originals/work/outputs/pristine)中**統一刪除**。使用者只要 1h 內沒完成下載就要重新上傳 — 內部工具可接受。**前端應在上傳後顯示 session TTL 提示 + 失效時友善 404 訊息**(實作細節 → Plan)。
- **D-B3:** **清乾淨包含 originals + work + pristine + outputs 全 4 個 dir 下的 `{sid}/`**(三目錄同時刪,不保留 outputs 較久)。理由:使用者下載完不需要伺服器保留,外部反向代理 / 公司入口 URL 路由也不會接到已釋放 session id 的下載路由 — 不透明。
- **D-B4:** **race / concurrency 防護**:刪除 session dir 採 `shutil.rmtree(...)` + try/except;若該 session 正在被別的 worker 處理(/process 進行中),janitor 對它略過 — 簡單做法是看 `work/{sid}/.lock`(若引入)或單純信任 mtime 1h 比 process timeout 60s 大很多,race window 不會發生。

### 原始檔 SHA-256 雜湊驗證 (SC #3)
- **D-C1:** **雜湊存於 `work/{sid}/meta.json` 的 `original_sha256` 欄位**(目前已有 `page_count` + `filename`,加一個欄位)。ingest 寫 `originals/source.pdf` 後立即 `hashlib.sha256(data).hexdigest()` 算一次,**寫入 meta.json 同次寫入**(atomic — 不能拆兩個 step,否則中間 crash 沒 baseline)。
- **D-C2:** **驗證點 = 每次 /process 前**,具體在 pipeline `reset-from-pristine` step 前後:讀 `meta['original_sha256']`、`hashlib.sha256(originals/source.pdf.read_bytes()).hexdigest()`、比對。50MB SHA-256 約 100–200ms,可接受。
- **D-C3:** **驗證失敗** → /process 回 **503 `{"detail": {"code": "original_tampered", "message": "..."}}`** + structured log(`session_id` + `expected_hash` + `actual_hash` + `timestamp` + `path`)+ **標記 session corrupted**(寫一個 `work/{sid}/.corrupted` sentinel file;之後該 session 所有 /process、GET /result、GET /pages 都中止)。使用者需重新上傳。
- **D-C4:** **只驗 originals/**(user contract:「原始檔不變」)。**pristine/ 不驗**(internal,信任 chmod 0o444 + storage 隔離 + AGPL seam pdf_engine.py 單一 fitz 進入點)。雙重驗證收益低、複雜度高。
- **D-C5:** **取代既有測試** — 既有 `tests/test_process_api.py` 中 SHA-256 invariant check(test-time only)沿用,但 Phase 5 新增 runtime 驗證後,測試從「程式碼自然成立」改為「驗證機制本身有作用」(改加 `test_original_tampered_returns_503`、`test_corrupted_session_blocked_from_process`、`test_meta_missing_hash_500_or_recompute` 等)。

### 大型 / 旋轉頁面承載穩固化 (Large & rotated pages stabilization)
- **D-D1:** **保持 /process 同步**(不引入 BackgroundTasks + job_id polling 重構 / 不用 ProcessPoolExecutor 子進程隔離)— v1 內部工具、單檔互動、使用人數低。Pitfall 11「isolated worker」風險可接受。
- **D-D2:** **uvicorn workers default 2 + env `UVICORN_WORKERS`**。理由:一個 worker 被 /process 佔住時,另一個還能服 /pages/{n}/image 預覽 / GET /sessions 讀項。本機 Python 套裝實質只需 1(但默 2 不會壞),Zeabur free tier 可 env 降到 1,Ubuntu 公司部署可調 2–4。
- **D-D3:** **/process 加 timeout = 60s default + env `PROCESS_TIMEOUT_SECONDS`**。實作以 `anyio.fail_after(seconds)` 或 `asyncio.wait_for` 包住 `process_job` 呼叫;超過 → **504 `{"detail": {"code": "processing_timeout", "message": "..."}}`**。對齊 nginx default `proxy_read_timeout=60s` + Zeabur 預設 timeout — 避免「app 200 / nginx 504」分裂顯象。
- **D-D4:** **Dockerfile HEALTHCHECK 指向 /health**;`/health` 端點加強回傳:
  ```json
  {
    "status": "ok",
    "uptime_seconds": 12345,
    "active_sessions": 3,
    "data_dir_bytes": 1234567,
    "data_dir_pct": 12.3
  }
  ```
  Zeabur 反向代理 / Ubuntu LB / `docker logs` 都能讀到狀態。**本機 Python 套裝**不跑 Docker 但仍可開瀏覽器到 `/health` 看狀態。

### Claude's Discretion
- **AGPL UI source link** 的位置 + 文案 + GitHub URL — memory 已鎖定「public GitHub + LICENSE + UI source link」三項,Phase 5 必須做。具體建議:右下 footer 一行繁中「本工具為 [LogoSwap](GitHub URL) — 依 AGPLv3 授權」、`LICENSE` 檔放專案 root(直接 cp GNU AGPL-3.0 全文)、`README.md` top 補一段 license + 對應的 GitHub URL — researcher / planner 可確認最終文字與位置。
- **CORS 設定** — root mount + iframe 嵌入 / strip-prefix 反向代理 都不需要 CORS(同源)。若未來 Ubuntu 入口走 cross-origin sub-domain(`pdf-logo.internal` 與 `intranet.internal`),需要加 `fastapi.middleware.cors.CORSMiddleware` allow-list。Phase 5 先預埋環境變數 `CORS_ALLOW_ORIGINS=""`(預設關閉),需要時設環境變數即啟動。
- **本機 Python 套裝啟動腳本** — 建議新增 `app/__main__.py`(`python -m app` 跑 uvicorn + `webbrowser.open("http://127.0.0.1:8000")`)、跨平台 README(uv 或 pip install)、可選 `pyinstaller --onefile` 包一個 exe 給 Windows 使用者(技術上 fitz 套件可能複雜 — 視 researcher 驗證結果)。
- **結構化日誌** — uvicorn 預設 access log 走 stdout,可選擇加 `--log-config` JSON 結構;v1 內部工具可以先用 default,需要時再升級。
- **Pillow 全域 MAX_IMAGE_PIXELS** — 目前 `MAX_INGEST_IMAGE_PIXELS=89_478_485` 是檢查、不 set Pillow 全域(Pillow 12.x 預設值)。Phase 5 可選擇在 app startup `Image.MAX_IMAGE_PIXELS = config.MAX_INGEST_IMAGE_PIXELS` 對齊 — 或不動(交給 Pillow default + 既有顯式檢查)— researcher / planner 決定。
- **docker-compose.yml 範例** — repo 可附一個 `docker-compose.example.yml`(app + nginx + volume mount 範例),不放 default。Ubuntu 部署者照樣搬,Zeabur 部署者用 image 直推。
- **資料 dir 位置** — `DATA_DIR` 已是 env var(預設 `./data`)。Docker 內 `/data` mount 為 volume,本機 Python 套裝走 `~/.logoswap/data` 或當前目錄 `./data`(researcher 視 cross-platform 決定)。
- **Phase 5 切兩個 plan(沿用 roadmap)**:Plan 05-01 = Dockerfile + uvicorn 啟動 + `APP_BASE_PATH` + `/health` 加強 + AGPL UI link / LICENSE;Plan 05-02 = SHA-256 baseline + 驗證 + janitor + /process timeout + corrupted session sentinel + 加強錯誤訊息。Plan 切法可由 planner 細調。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` — Phase 5 對應 Active requirement「可在 Ubuntu 伺服器以 Docker + Nginx 部署,處理大型與旋轉頁面、暫存檔清理」+ Key Decisions 表(AGPL seam、deferred-mutation 三目錄、PyMuPDF 為核心、v1 內網免登入)。
- `.planning/REQUIREMENTS.md` — Phase 5 為跨切面交付,**無新增 v1 需求 ID**(註腳明確說「不對應特定 v1 需求 ID」)。
- `.planning/ROADMAP.md` — Phase 5 success criteria 1/2/3(Docker 在 Ubuntu 安裝 + 大型/旋轉不崩潰 + 暫存清理 + 雜湊驗證);plan 切法建議(05-01 部署、05-02 穩固化)。
- `.planning/STATE.md` — Phase 1–4 累積決定;特別 SHA-256 D-05 invariant、`fit_dpi_to_pixel_budget`(WR-06)、AGPL seam pdf_engine.py 單一檔。

### Project research
- `.planning/research/ARCHITECTURE.md` — **特別** §"Pattern 4: API-First Seam for Future Embedding"(`window.PDFTOOL_API_BASE` 已是契約;Phase 5 加 `APP_BASE_PATH` 對等 backend)、§"Scaling Considerations"(uvicorn + workers + DPI cap + retention/cleanup)、§"Anti-Pattern 5: Coupling the UI directly to server-rendered templates"(已避免;Phase 5 維持靜態 frontend)。
- `.planning/research/STACK.md` — Python 3.12.x、PyMuPDF 1.27.x、FastAPI 0.115+、Uvicorn 0.34+(內建 `--workers` supervisor,不需 Gunicorn)、Pillow 12.x、AGPL 雙授權與 §13 網路條款、Ubuntu 部署 / 容器化 / multi-stage Dockerfile 建議。
- `.planning/research/PITFALLS.md` — **特別** Pitfall 8(大型 / 旋轉 / OCG / huge page)、Pitfall 9(原始檔保留:雜湊驗證屬於這個)、Pitfall 10(AGPL §13 網路條款 — Phase 5 部署前置)、Pitfall 11(上傳安全 / temp lifecycle / janitor / parser isolation)。
- `.planning/research/SUMMARY.md` — 鎖定棧與架構。

### Phase 1–4 artifacts (built — Phase 5 builds on these)
- `app/main.py` — FastAPI app + 路由註冊 + `/health` 端點 + 既有 exception handlers(IngestError / RenderError / RedactError / PipelineError / LogoError / InvalidSessionId 全部已 mapped 到結構化 4xx/5xx)+ `_WEB_DIR` 靜態 mount。**Phase 5 加**:`/health` 加強回傳 + startup janitor sweep + 新 `original_tampered` / `processing_timeout` exception handler / `_PROCESS_STATUS` 擴充。
- `app/config.py` — 既有所有限額常數(`MAX_UPLOAD_BYTES`、`MAX_PAGES`、`MAX_REGIONS`、`MAX_RENDER_PIXELS`、`MAX_INGEST_IMAGE_PIXELS`、`MIN/MAX/DEFAULT_DPI`、`JPEG_REENCODE_QUALITY`、`MAX_LOGO_BYTES`)。**Phase 5 新增**:`SESSION_TTL_SECONDS` (default 3600)、`PROCESS_TIMEOUT_SECONDS` (default 60)、`UVICORN_WORKERS` (default 2)、`APP_BASE_PATH` (default "")、`CORS_ALLOW_ORIGINS` (default "")。所有以 env var override(沿用既有 `_env_int` pattern)。
- `app/storage.py` — 既有 4-kind dir layout(originals/work/outputs/pristine)+ `_SESSION_ID_RE` 防 path traversal + `validate_session_id` + `write_original` 寫完 chmod 0o444 + `write_session_meta` / `read_session_meta`(目前存 `page_count` + `filename`)。**Phase 5 新增**:`write_session_meta` 簽名加 `original_sha256: str`(必填);新 `list_session_ids() -> Iterator[str]` 給 janitor 用;新 `session_age_seconds(sid) -> float`;新 `delete_session(sid)`(rmtree 全 4 kind);新 `mark_session_corrupted(sid)` / `is_session_corrupted(sid)`(`.corrupted` sentinel file 在 work/)。
- `app/services/ingest.py` — 既有 magic-header sniff dispatch + PDF / PNG / JPEG / TIFF + Pillow chain + `_logoswap_name` 命名。**Phase 5 新增**:寫 originals 後 + 寫 meta.json 之間,呼叫 `hashlib.sha256(data).hexdigest()` 並把 hex 字串放進 `write_session_meta(..., original_sha256=...)`。
- `app/services/pipeline.py` — 既有 `process_job` deferred-mutation 流程 + reset-from-pristine + per-region image-overlap dispatch + redact + place_logo + save。**Phase 5 新增**:`process_job` 開頭驗 `meta['original_sha256']` == `hashlib.sha256(originals_path.read_bytes()).hexdigest()` → 不一致 raise `PipelineError("original_tampered", ...)` + 寫 corrupted sentinel + structured log;包整個 `process_job` 在 timeout 內(routing 層或 service 層都可)。
- `app/services/render.py` — 既有 `fit_dpi_to_pixel_budget`(WR-06 pixel ceiling)+ `page_meta` 已就位,**Phase 5 不需要改**。
- `app/services/coords.py` + `app/services/pdf_engine.py` — 既有 derotation 已驗證 Phase 2 < 1px,Phase 5 **不需要改**。旋轉頁面承載穩固化全部是 timeout / workers / pixel cap 配置層級。
- `app/api/sessions.py` — POST /sessions 上傳。**Phase 5 加**:成功後呼叫一次 janitor sweep。
- `app/api/process.py` — POST /sessions/{sid}/process。**Phase 5 加**:(a) 預先檢查 corrupted sentinel(/process、/result 都檢)、(b) 包 timeout、(c) 結尾呼叫 janitor sweep。
- `app/api/pages.py` + `app/api/logos.py` — 不需要改(讀項側不主動驗 SHA-256,不沾 janitor)。
- `web/index.html` + `web/js/app.js` + `web/js/api.js` — **Phase 5 加**:AGPL footer 連結(<footer> 加一行繁中「本工具為 [LogoSwap](repo URL) — AGPLv3 授權」)+ session TTL 提示(上傳後顯示「session 1 小時後失效」)+ 503 `original_tampered` / 504 `processing_timeout` 友善錯誤訊息(沿用既有 alert / banner pattern)。
- `web/js/api.js` 唯一 server seam + `window.PDFTOOL_API_BASE` — **Phase 5 不需要改 code**,只需要驗證 `APP_BASE_PATH` env var 設定時前後端對齊(可能 README 補一段嵌入文件)。
- `tests/test_storage.py` + `tests/test_process_api.py` + `tests/test_ingest.py` — 加新測試:`test_janitor_sweeps_expired_session`、`test_active_session_under_1h_kept`、`test_original_tampered_returns_503`、`test_corrupted_session_blocked_from_process`、`test_meta_original_sha256_written_at_ingest`、`test_process_timeout_returns_504`、`test_health_includes_uptime_and_data_dir`。
- `.planning/phases/01-input-preview/01-CONTEXT.md` — `web/js/api.js` seam + `window.PDFTOOL_API_BASE` 是 Phase 1 的設計鎖定。
- `.planning/phases/04-raster-image-support/04-CONTEXT.md` — pristine/ + write_pristine_copy + SHA-256 invariant strengthening(D-05 因為 pipeline 不再碰 originals 而 STRENGTHENED)— Phase 5 雜湊驗證機制要避免破壞 Phase 4 的 D-05 強化。

### Deployment / packaging refs (Phase 5 新引入,需要驗證)
- `requirements.txt` 既有 — Phase 5 不需要新增 runtime 套件(stdlib 的 `hashlib`、`shutil`、`asyncio`、`anyio` 已有,`webbrowser` 已有)。**可選新增**:`apscheduler`(若 D-B1 走背景週期 — 已否決)、`uv`(若選 uv 取代 pip — Claude 裁量)。
- `Dockerfile`(尚未建立) — 多階段;**Phase 5 必須產出**。
- `docker-compose.example.yml`(尚未建立) — Ubuntu 部署參考;Claude 裁量是否提供。
- `LICENSE`(尚未建立) — AGPL-3.0 全文;**Phase 5 必須產出**。memory「AGPL-compliance (public GitHub + LICENSE + UI source link)」。
- `README.md`(尚未確認狀態) — 部署文件 + 三個 target 的啟動指令 + 嵌入文件 + AGPL 標示 + GitHub URL。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/main.py` 既有 exception handler 樣板(IngestError / RenderError / RedactError / PipelineError / LogoError / InvalidSessionId / PdfEngineError / RequestValidationError 共 8 個)+ 結構化 `{"detail": {"code", "message"}}` 契約 — Phase 5 新增 `original_tampered`(在 PipelineError 既有 dict 加一筆)、`processing_timeout`(可能新一個 `ProcessingTimeoutError` 或塞進 PipelineError),沿用 pattern。
- `app/config.py` 的 `_env_int` 助手 + env var → 常數 pattern — 新增的 `SESSION_TTL_SECONDS` / `PROCESS_TIMEOUT_SECONDS` / `UVICORN_WORKERS` 沿用。Path env vars 走 `Path(os.environ.get(...))` resolve pattern。新增 `APP_BASE_PATH` 走 `os.environ.get("APP_BASE_PATH", "")` 字串 default。
- `app/storage.py` 的 `_SESSION_ID_RE` + `validate_session_id` 防 path traversal 機制 + `subdir(kind, sid)` 抽象 — Phase 5 新的 `list_session_ids` / `delete_session` 都走 `subdir` 一致防護。
- `app/storage.py` 的 `write_original` 寫完 chmod 0o444 — 已是 SHA-256 驗證機制的「結構性」防護(寫不下去),Phase 5 雜湊驗證是「驗證機制」對齊。
- `app/storage.py` 的 `_META_NAME` + `write_session_meta` / `read_session_meta` — Phase 5 加 `original_sha256` 欄位走既有 API。
- `app/services/ingest.py` 寫 originals 的 step(`storage.write_original(session_id, safe_name, data)`)— Phase 5 寫完後立刻 `hashlib.sha256(data).hexdigest()` + `storage.write_session_meta(..., original_sha256=hex)`。`data` 變數已在 scope 內。
- `app/services/pipeline.py` 既有 `process_job` 的 deferred-mutation step 序列(reset-from-pristine → per-region clamp → map → redact → place_logo → save outputs)— Phase 5 在 reset 步驟前驗 SHA-256,失敗丟 PipelineError("original_tampered", ...) 自動走 main.py exception handler → 503。
- `app/main.py` 既有 `/health` endpoint — Phase 5 擴充 return 內容,加 `start_time` 全域變數紀錄 startup 時間 + `time.time() - start_time` 算 uptime。

### Established Patterns
- **Typed `*Error(code, message)` + main.py 對應 4xx/5xx**(IngestError / LogoError / PipelineError / RedactError / RenderError / PdfEngineError / InvalidSessionId)— Phase 5 新增的 `original_tampered`(503)、`processing_timeout`(504)、`session_corrupted`(409 或 410)沿用這個 pattern,加進 `_PROCESS_STATUS` dict。
- **`config.py` 常數命名**:`MAX_X_Y` / `MIN_X` / `DEFAULT_X` — Phase 5 新增的 `SESSION_TTL_SECONDS`、`PROCESS_TIMEOUT_SECONDS`、`UVICORN_WORKERS`、`APP_BASE_PATH`、`CORS_ALLOW_ORIGINS` 沿用單位後綴。
- **`_KINDS` 4-kind dir layout**(originals / work / outputs / pristine)— janitor 一律走 `_KINDS` 來迭代刪除。
- **AGPL seam**:`import fitz` 只在 `pdf_engine.py`(Phase 1–4 enforced by test)— Phase 5 雜湊計算用 `hashlib`(stdlib,無 fitz),janitor 用 `shutil.rmtree` + `Path.iterdir`(無 fitz),完全不破壞 AGPL seam。
- **繁中錯誤訊息**:對使用者顯示的 4xx/5xx message 一律繁中(沿用 Phase 1–4)— `original_tampered`、`processing_timeout`、`session_corrupted` 都要繁中文案。
- **Three-directory deferred-mutation D-05**:Phase 5 雜湊驗證是 D-05 的執行時對等;memory「pristine/ 不驗」+ D-C4 對齊。

### Integration Points
- **新增的 service module**:`app/services/janitor.py`(新檔,沿用 `services/` 命名)— `sweep_expired_sessions(now: float | None = None) -> int` 主函式 + 內部 helpers。被 `main.py startup` / `api/sessions.py POST` / `api/process.py POST` 三處呼叫。
- **新增的 service module**:`app/services/integrity.py`(新檔)— `verify_original_hash(session_id) -> None`(raise `PipelineError("original_tampered", ...)` if mismatch)+ `compute_original_hash(data: bytes) -> str` helper。被 `services/pipeline.py process_job` 開頭呼叫;`services/ingest.py` 也用同 helper。**取代** Phase 5 不需要新 typed error class(沿用 `PipelineError`)。
- **新增的 Dockerfile + entrypoint**:repo root 加 `Dockerfile`、`.dockerignore`、`entrypoint.sh`(可選 — 也可以直接 CMD ["uvicorn", ...])。**新增的 docs**:`README.md` 三個 target 的啟動指令、`LICENSE` AGPL-3.0 全文。
- **本機 Python 套裝啟動**:新 `app/__main__.py`(`python -m app`)— `uvicorn.run("app.main:app", host="127.0.0.1", port=8000, workers=config.UVICORN_WORKERS)` + `webbrowser.open(...)`。
- **前端 footer 加 AGPL UI link**:`web/index.html` 在 footer 加一行(沿用 Phase 1 既有 footer slot 若有,或新增 element)+ 沿用 Phase 1 雙主題 token + 繁中文案。

### What Phase 5 does NOT touch
- `app/services/coords.py` / `app/services/pdf_engine.py` — 既有 derotation + AGPL seam 完全沿用,Phase 5 不改 fitz 程式碼(只用 stdlib + 設定)。
- `app/services/redact.py` / `app/services/logo.py` — 既有 vector / raster / place_logo 完全沿用。
- `app/services/render.py` — fit_dpi_to_pixel_budget 既有,大型頁承載已封閉。
- `app/api/pages.py` / `app/api/logos.py` — 讀項 endpoint 不沾 janitor / 不驗 SHA-256。
- `web/js/regions.js` / `web/js/viewer.js` — 前端核心互動完全沿用 Phase 1–4。

</code_context>

<specifics>
## Specific Ideas

- 核心場景一:**Zeabur 短期 demo / UAT** — 推一份 image 到 Zeabur,內部使用者 LAN 連 sub-domain 試。需有:1. Dockerfile 推得上去、2. AGPL UI link、3. /health 給 Zeabur LB 用、4. janitor 不依賴 cron。
- 核心場景二:**內部使用者本機跑** — 同事下載 git tag / zip,跨平台跑 `pip install + python -m app`,自動開瀏覽器到 `http://127.0.0.1:8000`,當作 desktop tool。需有:1. `app/__main__.py`、2. README 跨平台啟動指令、3. `DATA_DIR` 預設合理的本機位置、4. AGPL link 同樣要在。
- 核心場景三:**Ubuntu 公司入口網站功能模組** — 走公司主 nginx + 反向代理 `/pdf-logo/` 或 sub-domain;**整合時可調整**(D-A2 三條嵌入路徑可選)。需有:1. `APP_BASE_PATH` 支援、2. `CORS_ALLOW_ORIGINS` 預埋(若 cross-origin)、3. docker-compose 範例。
- **使用者體驗:session TTL 1h 的提示** — 上傳完成後 UI 顯示一行繁中提示「⓵ 此次處理 1 小時內完成下載 — 逾時需重新上傳」。失效時 GET /sessions 回 404,前端友善「此次處理已過期,請重新上傳」。
- **SHA-256 失敗的 UX** — 503 `original_tampered` + 結構化 log + UI 顯示「⚠ 系統偵測到原始檔異常,請重新上傳此檔」(語氣不指責使用者,語氣是「系統發現異常」)。
- **大型 CAD 場景** — 50MB / 30 頁 / 100MP image 都已被前期限額包好;Phase 5 只新增 timeout 60s 保證 worker 不被卡死、workers >= 2 保證預覽不阻塞。
- **AGPL §13 合規順序** — 在 Zeabur 公開部署「之前」必須:1. push 到 public GitHub repo、2. repo root 有 `LICENSE`(AGPL-3.0 全文)、3. UI 有 source link。三項必須同時就位 — memory 鎖定。

</specifics>

<deferred>
## Deferred Ideas

- **/process 改背景 + job_id polling**(D-D1 否決;v1 不需要)— 若 UAT 出現「使用者反映等太久 timeout」或 Zeabur 強制 30s,v1.x 再加。
- **ProcessPoolExecutor 子進程隔離 PyMuPDF**(Pitfall 11)— 若內部出現 crafted PDF 把 worker crash,再導入。v1 內部信任。
- **APScheduler / background asyncio task janitor**(D-B1 否決)— 若同步 janitor 不足以清乾淨(例如使用者只 GET 預覽然後關掉),再考慮加 background task。
- **last-access touch / active session 保護**(D-B2 否決)— 若使用者抱怨「我才用一下就被清」,再加 mtime touch on activity。
- **Outputs 保留 24h、originals 1h**(D-B3 否決)— 若使用者抱怨「明天才下載找不到」,可拆 TTL。
- **pristine/ SHA-256 雜湊驗證**(D-C4 否決)— 若 internal incident 出現 pristine 被竄改,再加。
- **POST /admin/verify endpoint 手動驗證**(D-C2 否決方案之一)— 若需要管理者手動巡檢,可加。
- **TLS / HTTPS 終結內建**(D-A1 明確不在 image 內)— 永遠交給部署目標。
- **多容器 docker-compose 預打包**(D-A1 否決,只附 example)— 若 Ubuntu 部署需要更穩定模板,加 README 範例。
- **Distroless / Alpine base image**(D-A3 否決)— v1 內部工具不值得 build / debug 工夫。
- **Prometheus / OpenTelemetry 結構化監控**(out-of-scope memory)— v1 不導入。
- **PyInstaller 把 app 包成 Windows exe**(Claude 裁量,本機 Python 套裝可選)— PyMuPDF wheel 跨平台複雜,researcher 驗證可行性後決定。
- **rate limiting / per-IP cap**(out-of-scope v1)— 內網無需。若公開外網才必要。
- **Pillow Image.MAX_IMAGE_PIXELS 全域 set**(Claude 裁量)— researcher / planner 決定要不要在 startup 對齊 `config.MAX_INGEST_IMAGE_PIXELS`。
- **OCG / hidden layer 處理**(Phase 4 deferred + Pitfall 8)— Phase 5 不沾,若 UAT 反映「Acrobat 看到的 logo 沒被框選到」再加。

</deferred>

---

*Phase: 5-ubuntu*
*Context gathered: 2026-05-23*
