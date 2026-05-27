# Phase 5: 部署與穩固化(Ubuntu)- Research

**Researched:** 2026-05-23
**Domain:** Containerized internal web tool deployment — multi-stage Dockerfile + uvicorn workers + sync /process timeout + 4-dir filesystem janitor + SHA-256 baseline + AGPL §13 surface
**Confidence:** HIGH on Dockerfile / HEALTHCHECK / uvicorn workers / asyncio.wait_for + to_thread semantics; MEDIUM on Zeabur free-tier limits (vendor docs vague on RAM/CPU caps); HIGH on AGPL §13 compliance pattern

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**容器拓撲 + 部署形態 (Container topology & deploy targets):**
- **D-A1:** App image 不含 nginx;uvicorn 直接服 static(`web/`)+ API。外部反向代理(Zeabur LB / Ubuntu 公司 nginx)是部署目標自己的事,不在 image 內負擔反向代理 / TLS / supervisor。
- **D-A2:** 預設 root mount;同時支援可選 `APP_BASE_PATH` env var(空字串 = root,否則如 `/pdf-logo`)→ 啟動時帶入 FastAPI `root_path`。前端 `web/js/api.js` 的 `window.PDFTOOL_API_BASE` seam 沿用。
- **D-A3:** 多階段 Dockerfile(`python:3.12-slim` build stage:`pip install --target /install`;runtime stage:COPY /install + app/ + web/ + logos/ + entrypoint)。本機可以不用 Docker 跑。Slim base 已足;不走 distroless / Alpine(PyMuPDF wheel 需 glibc)。
- **D-A4:** 部署順序鎖定:1. Zeabur 短期單容器 PaaS;2. 可下載 Python 套裝;3. Ubuntu 公司入口網站功能模組。

**暫存清理 janitor (Temp file cleanup):**
- **D-B1:** 同步觸發 janitor(三個觸發點:app startup、/sessions POST 結尾、/process 結尾)。不引入 background scheduler / cron / APScheduler / asyncio task。
- **D-B2:** TTL = 1 小時(硬上限,不 touch last-access)。
- **D-B3:** 清乾淨包含 originals + work + pristine + outputs 全 4 個 dir 下的 `{sid}/`。
- **D-B4:** race / concurrency 防護:刪除 session dir 採 `shutil.rmtree(...)` + try/except;若該 session 正在被別的 worker 處理,janitor 對它略過 — 簡單做法是看 `work/{sid}/.lock`(若引入)或單純信任 mtime 1h 比 process timeout 60s 大很多。

**原始檔 SHA-256 雜湊驗證 (SC #3):**
- **D-C1:** 雜湊存於 `work/{sid}/meta.json` 的 `original_sha256` 欄位。ingest 寫 `originals/source.pdf` 後立即 `hashlib.sha256(data).hexdigest()` 算一次,寫入 meta.json 同次寫入(atomic)。
- **D-C2:** 驗證點 = 每次 /process 前,具體在 pipeline `reset-from-pristine` step 前後:讀 `meta['original_sha256']`、`hashlib.sha256(originals/source.pdf.read_bytes()).hexdigest()`、比對。
- **D-C3:** 驗證失敗 → /process 回 **503 `{"detail": {"code": "original_tampered", "message": "..."}}`** + structured log + 標記 session corrupted(寫一個 `work/{sid}/.corrupted` sentinel file;之後該 session 所有 /process、GET /result、GET /pages 都中止)。
- **D-C4:** 只驗 originals/(user contract:「原始檔不變」)。pristine/ 不驗(internal,信任 chmod 0o444 + storage 隔離 + AGPL seam pdf_engine.py 單一 fitz 進入點)。
- **D-C5:** 既有 SHA-256 invariant test 沿用,並加新測試(`test_original_tampered_returns_503`、`test_corrupted_session_blocked_from_process`、`test_meta_missing_hash_500_or_recompute`)。

**大型 / 旋轉頁面承載穩固化 (Large & rotated pages stabilization):**
- **D-D1:** 保持 /process 同步(不引入 BackgroundTasks + job_id polling / 不用 ProcessPoolExecutor 子進程隔離)。
- **D-D2:** uvicorn workers default 2 + env `UVICORN_WORKERS`。
- **D-D3:** /process 加 timeout = 60s default + env `PROCESS_TIMEOUT_SECONDS`。實作以 `anyio.fail_after(seconds)` 或 `asyncio.wait_for` 包住 `process_job` 呼叫;超過 → **504 `{"detail": {"code": "processing_timeout", "message": "..."}}`**。
- **D-D4:** Dockerfile HEALTHCHECK 指向 /health;`/health` 端點加強回傳 `{status, uptime_seconds, active_sessions, data_dir_bytes, data_dir_pct}`。

**AGPL §13(memory locked):** public GitHub repo + LICENSE (AGPL-3.0) + UI source link — Phase 5 必須做。

### Claude's Discretion

- AGPL UI source link 的位置 + 文案 + GitHub URL — Phase 5 必須做,具體建議由 researcher / planner 確認。
- CORS 設定 — Phase 5 先預埋環境變數 `CORS_ALLOW_ORIGINS=""`(預設關閉)。
- 本機 Python 套裝啟動腳本(`app/__main__.py` + `webbrowser.open` + 跨平台 README)— PyInstaller 視 researcher 驗證結果。
- 結構化日誌 — v1 內部工具可以先用 default,需要時再升級。
- Pillow 全域 `MAX_IMAGE_PIXELS` — researcher / planner 決定要不要在 startup 對齊 `config.MAX_INGEST_IMAGE_PIXELS`。
- docker-compose.yml 範例 — repo 可附一個 `docker-compose.example.yml`,不放 default。
- 資料 dir 位置 — Docker 內 `/data` mount,本機走 `~/.logoswap/data` 或當前目錄 `./data`(researcher 視 cross-platform 決定)。
- Phase 5 切兩個 plan:Plan 05-01 = Dockerfile + uvicorn 啟動 + `APP_BASE_PATH` + `/health` 加強 + AGPL UI link / LICENSE;Plan 05-02 = SHA-256 baseline + 驗證 + janitor + /process timeout + corrupted session sentinel + 加強錯誤訊息。

### Deferred Ideas (OUT OF SCOPE)

- /process 改背景 + job_id polling(若 UAT 出現「使用者反映等太久 timeout」或 Zeabur 強制 30s,v1.x 再加)。
- ProcessPoolExecutor 子進程隔離 PyMuPDF(Pitfall 11)。
- APScheduler / background asyncio task janitor。
- last-access touch / active session 保護。
- Outputs 保留 24h、originals 1h(D-B3 否決;若使用者抱怨可拆 TTL)。
- pristine/ SHA-256 雜湊驗證。
- POST /admin/verify 手動驗證端點。
- TLS / HTTPS 終結內建(永遠交給部署目標)。
- 多容器 docker-compose 預打包(只附 example)。
- Distroless / Alpine base image。
- Prometheus / OpenTelemetry。
- PyInstaller Windows exe(待驗證)。
- rate limiting / per-IP cap。
- Pillow `Image.MAX_IMAGE_PIXELS` 全域 set(Claude's discretion)。
- OCG / hidden layer 處理。

</user_constraints>

## Summary

Phase 5 是「把 Phase 1–4 已經跑得起來、測試已 243 passing、UAT 已過的 FastAPI + PyMuPDF + 純前端 SPA,**包成可在三個部署目標跑的成品**」的階段。核心交付物只有六件:多階段 Dockerfile、`APP_BASE_PATH` env var → FastAPI `root_path`、Janitor sweep、SHA-256 baseline + verify + corrupted sentinel、/process 60s timeout、AGPL §13 三件套(public GitHub + LICENSE + UI link)。**沒有任何新的核心功能**;全部都是 stdlib + config + Dockerfile + 一頁 footer。

關鍵的「研究發現會影響 plan 寫法」共 7 件:
1. **`asyncio.wait_for(asyncio.to_thread(process_job, ...))` 在超時後**,Python 線程無法被殺,只能讓 HTTP 回 504、線程繼續跑完。這是「邏輯上 acceptable」(60s timeout × workers=2 + sync /process 內 PyMuPDF 自然會 release 線程)而非「真的 cancel」。Plan 必須白紙黑字寫明這個事實,並且用 `Semaphore(1)` 或設定 `workers=2` 而非 `1` 來確保預覽不被卡住的線程阻塞。
2. **Docker HEALTHCHECK 在 python:3.12-slim 沒有 curl / wget**,必須用 `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"` 形式(verified web search)。
3. **FastAPI `root_path` + `StaticFiles(html=True)` 已知 bug**(GitHub discussion #12151):static mount 在 `root_path` 設定下對 redirect 不友善。Plan 05-01 必須測試三種嵌入路徑(root mount / strip-prefix nginx / pass-through proxy)其中至少前兩種,並且把該坑寫進 README 嵌入文件。
4. **uvicorn `--workers N` 使用 spawn 而非 fork**(verified uvicorn docs),所以 `app/__main__.py` 走 `uvicorn.run(..., workers=N)` 在 Windows 上會跑 — 但必須把所有 module-level state(全域 startup time、cached lists)做成 spawn-safe(每個 worker process 自己初始化,不假設 fork 後繼承)。
5. **`shutil.rmtree` 對 chmod 0o444 originals/** 的 sub-file 在 Windows 上會 PermissionError。必須帶 `onexc` (Python 3.12+) 或 `onerror` (legacy) handler 把檔案 chmod 0o644 後 retry。Linux 對 read-only file 在 read-write dir 下 unlink 沒問題 — 跨平台必須處理 Windows。
6. **`meta.json` schema 遷移**:既有 Phase 1–4 session 的 meta.json 只有 `{page_count, filename}`,沒有 `original_sha256`。Phase 5 的驗證會看不到 baseline。建議:`verify_original_hash` 看到 meta 沒有 `original_sha256` 欄位 → 視為 legacy session,fall back 到「不驗,但 log warning」+ 在 /sessions GET 加 deprecation header,讓使用者用完現有 session 後新 session 自然帶 hash。**或者**簡單做:直接 reject「需要重新上傳」(503 `session_legacy` 或 `original_tampered_unknown_baseline`)— 內部工具,1h TTL 已經保證 legacy session 會在 phase 5 部署 1h 後全部過期。建議走後者(D-C2 簡單)。
7. **AGPL §13 內網誤解**:即便是內網,只要使用者透過 HTTP/網路 interact with 軟體,§13 就觸發。Memory 已鎖定「public GitHub + LICENSE + UI source link」三件套,符合 §13 的 "offer source to network users" 字面要求。Footer wording 建議「本工具為 LogoSwap(GitHub URL),依 AGPLv3 授權」+ /agpl-source endpoint 直接 redirect 到 GitHub repo URL(env var 設定)。

**Primary recommendation:** 兩個 plan 各 3–4 task:
- **Plan 05-01(部署 + AGPL 合規)**:Dockerfile multi-stage、`.dockerignore`、`APP_BASE_PATH` env var → FastAPI(app=FastAPI(root_path=os.environ.get("APP_BASE_PATH",""))), `app/__main__.py`(本機 desktop)、`/health` 加強(uptime + active_sessions + data_dir 用量)、HEALTHCHECK 用 `python -c urllib.request` 形式、`LICENSE`(AGPL-3.0 全文)、`README.md`(三個 deploy target + AGPL 標示)、UI footer AGPL 連結(`web/index.html` + sole inline `<footer>` block,纯文字 + anchor,token 沿用)、`docker-compose.example.yml`、`zeabur.json`(可選 — Zeabur 已 auto-detect Dockerfile,但 zeabur 有 PORT env var 慣例)。
- **Plan 05-02(穩固化)**:`config.py` 新增 5 個常數(`SESSION_TTL_SECONDS=3600`、`PROCESS_TIMEOUT_SECONDS=60`、`UVICORN_WORKERS=2`、`APP_BASE_PATH=""`、`CORS_ALLOW_ORIGINS=""`)、`storage.py` 新增 5 個函式(`list_session_ids`、`session_age_seconds`、`delete_session`、`mark_session_corrupted`、`is_session_corrupted`)+ atomic meta.json write、`services/integrity.py` 新檔(`compute_original_hash`、`verify_original_hash`)、`services/janitor.py` 新檔(`sweep_expired_sessions`)、`ingest.py` 加 `original_sha256` 算 + 寫、`pipeline.py` 開頭 verify + 結尾 janitor、`api/sessions.py` 結尾 janitor、`api/process.py` 包 `asyncio.wait_for(asyncio.to_thread(...))` 60s timeout、`main.py` 啟動 hook 跑一次 janitor + 加 `_PROCESS_STATUS` 新 codes(`original_tampered:503`、`processing_timeout:504`、`session_corrupted:410`)+ `/health` 加強、前端 friendly 錯誤訊息(`web/js/api.js` 既有 `ApiError` 已可承載 — 只要 `app.js` 對新 code 加 mapping)。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Multi-stage build / image packaging | CI / Docker | — | Build-time concern, not runtime. Two-stage keeps runtime layer slim (no pip / build tools) |
| Reverse proxy / TLS termination | External (Zeabur LB / Ubuntu nginx) | — | D-A1 — explicitly outside the app image. Trade managed by deployment target |
| Static file serving (web/) | FastAPI Server | — | D-A1 — uvicorn directly serves static + API; no nginx in image. `StaticFiles(html=True)` already mounted |
| API path prefix handling | FastAPI Server (root_path) + Browser (window.PDFTOOL_API_BASE) | — | D-A2 — frontend seam already exists (Phase 1 lock); Phase 5 adds backend `root_path` to mirror it |
| Process supervision / worker management | uvicorn `--workers N` | OS (container restart policy) | D-D2 — uvicorn 0.30+ has built-in supervisor; no gunicorn needed |
| Sync timeout enforcement | FastAPI handler (`asyncio.wait_for(to_thread)`) | — | D-D3 — handler-layer enforcement; thread itself cannot be killed |
| Filesystem state lifecycle / janitor | Storage layer (services/janitor.py) | API endpoints (trigger points) | D-B1 — synchronous trigger; no background scheduler |
| File integrity verification | Pipeline (entry hook) | Storage (atomic meta write at ingest) | D-C1/D-C2 — verify on every /process; baseline written once at ingest |
| Health check / liveness | FastAPI `/health` endpoint | Docker HEALTHCHECK directive | D-D4 — single endpoint; both Zeabur LB and Docker poll the same URL |
| AGPL §13 source disclosure | Project root (LICENSE + GitHub) + UI footer (anchor) | README.md (deploy docs) | Memory lock — three artifacts in lockstep, all required before public deploy |

## Phase Requirements

Phase 5 is cross-cutting — REQUIREMENTS.md explicitly states "Phase 5(部署與穩固化)為跨切面交付,不對應特定 v1 需求 ID。" Verify against the PROJECT.md Active requirement instead:

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-01 (implicit) | 工具可透過 Docker 在 Ubuntu 伺服器上安裝並執行(Uvicorn + Nginx) | Multi-stage Dockerfile section + uvicorn workers + nginx left to deployment target (D-A1) |
| DEPLOY-02 (implicit) | 大型或含旋轉頁面的 PDF 可正確處理不崩潰(DPI 上限/背景工作) | Existing `fit_dpi_to_pixel_budget` (WR-06) + new 60s timeout (D-D3) + `MAX_RENDER_PIXELS=40MP` (already in config.py) — Phase 5 wraps existing limits in timeout/worker config, no new core logic |
| DEPLOY-03 (implicit) | 暫存檔於處理後被清理,原始檔以雜湊驗證未被竄改 | Janitor section + SHA-256 baseline + verify section + Corrupted Session Sentinel section |
| AGPL-§13 | Memory-locked deployment prerequisite | AGPL §13 Compliance section |

## Standard Stack

### Core (already locked in Phase 1–4)

| Library | Version (verified in venv) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12.x (Docker) / 3.14.4 (dev venv) | Runtime | `[VERIFIED: .venv/Scripts/python.exe --version → Python 3.14.4]` Project runs on 3.14 in dev; Docker image should target **3.12** per `.planning/research/STACK.md` for max wheel compatibility (PyMuPDF 1.27, Pillow 12.x all ship cp310-abi3, so 3.12 vs 3.14 makes no functional difference but 3.12 is the boring choice with 2 years of stability). |
| PyMuPDF (fitz) | 1.27.2.3 | PDF read/render/redact | `[VERIFIED: pip show PyMuPDF → 1.27.2.3]` — unchanged from Phase 4 |
| FastAPI | 0.136.1 | Backend | `[VERIFIED: pip show fastapi → 0.136.1]` Project is already on 0.136.x — STACK.md said `>=0.115,<1.0`, current install is fine. Phase 5 needs `root_path` parameter which is GA in 0.115+ (`[CITED: fastapi.tiangolo.com/advanced/behind-a-proxy/]`). |
| Uvicorn | 0.47.0 | ASGI server | `[VERIFIED: pip show uvicorn → 0.47.0]` STACK.md said `>=0.34`. Phase 5 uses `uvicorn[standard]` (already in requirements.txt) for C-accelerated event loop + `--workers N` built-in supervisor. |
| Pillow | 12.2.0 | Image decode | `[VERIFIED: pip show pillow → 12.2.0]` — unchanged |

### Phase 5 stdlib additions (no new third-party deps)

| Module | Purpose | Use Site |
|--------|---------|----------|
| `hashlib` | SHA-256 baseline + verify | `services/integrity.py` (new), `services/ingest.py` (write baseline) |
| `shutil` | `rmtree` for janitor, `disk_usage` for /health data_dir_pct | `services/janitor.py` (new), `app/main.py` (/health) |
| `tempfile` | atomic meta.json write (write temp + os.replace) | `app/storage.py` (write_session_meta upgrade) |
| `asyncio` (`wait_for`, `to_thread`) | /process 60s timeout enforcement | `app/api/process.py` |
| `os.replace` | atomic file rename for meta.json | `app/storage.py` |
| `time` | `time.time()` for uptime, mtime comparisons | `app/main.py` (start_time global), `services/janitor.py` |
| `webbrowser` | open `http://127.0.0.1:8000` after server starts (desktop pkg) | `app/__main__.py` (new) |
| `threading.Timer` | delayed browser open after uvicorn starts (1s sleep avoid race) | `app/__main__.py` (new) |

**No new packages.** Confirmed: every Phase 5 capability is stdlib + Dockerfile + config + a few new modules.

### Alternatives Considered

| Instead of | Could Use | Tradeoff (Why rejected per D-A1..D-D4 locks) |
|------------|-----------|----------|
| `python:3.12-slim` base | `python:3.12-alpine` | Alpine = musl libc; PyMuPDF wheels are manylinux/glibc → would need source-build MuPDF (slow + fragile). Locked by D-A3. |
| Multi-stage Dockerfile | Single-stage | Single-stage leaves pip / build deps in runtime image (~150MB vs ~80MB). Locked by D-A3. |
| `uvicorn --workers` | `gunicorn -k uvicorn.workers.UvicornWorker` | Gunicorn is a pre-fork supervisor; uvicorn 0.30+ has built-in spawn-based supervisor `[CITED: uvicorn.dev/deployment/]`. No advantage for an internal tool. Locked by D-A3. |
| nginx in image | uvicorn direct | nginx in image = supervisor + multi-process drama in one container; Zeabur typically can't deploy 2-container. Locked by D-A1. |
| `BackgroundTasks` + job_id polling | sync /process | v1 internal, single-file interactive — synchronous is simpler. Locked by D-D1. |
| `ProcessPoolExecutor` sub-process isolation | sync `to_thread` | Sub-process gives crash isolation but adds IPC + lifecycle complexity. Locked by D-D1. |
| APScheduler background sweep | sync janitor at 3 trigger points | Background = another moving part + lifecycle management. Locked by D-B1. |
| `apscheduler` / `celery` dep | stdlib | Avoids dep — Phase 5 stays stdlib-only. Locked by D-D1/D-B1. |

**Installation:** No `pip install` additions. Phase 5 ships exclusively new application code + Dockerfile + LICENSE + README.

**Version verification (already in venv):**

| Package | Verified version | Notes |
|---------|------------------|-------|
| PyMuPDF | 1.27.2.3 | Latest 1.27.x — within `>=1.27,<1.28` pin |
| fastapi | 0.136.1 | Above the STACK.md `>=0.115` floor |
| uvicorn | 0.47.0 | Above the STACK.md `>=0.34` floor |
| Pillow | 12.2.0 | Latest 12.x stable |
| python-multipart | (transitive via FastAPI 0.136) | Auto-pulled |

## Architecture Patterns

### System Architecture Diagram

```
                       THREE DEPLOY TARGETS — same image / same code
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                                                                              │
   │   Target 1 (短期):  [Browser]──HTTPS──[Zeabur LB / TLS]──HTTP──[app container]│
   │                                          │                                    │
   │                                          ▼ polls /health every 30s            │
   │                                                                              │
   │   Target 2 (本機):  [Browser 127.0.0.1:8000]──HTTP──[python -m app]            │
   │                                                       │                       │
   │                                          ▼ auto-opens via webbrowser.open()   │
   │                                                                              │
   │   Target 3 (長期):  [Browser]──HTTPS──[Company nginx]──HTTP──[app container]   │
   │                                       │  strip /pdf-logo/ prefix              │
   │                                       │  or pass-through                       │
   │                                       ▼  → APP_BASE_PATH env var controls    │
   │                                          FastAPI root_path                     │
   │                                                                              │
   └─────────────────────────────────────────────────────────────────────────────┘

                         INSIDE THE APP CONTAINER / PROCESS
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                                                                              │
   │   uvicorn (workers=2, default)                                               │
   │     │                                                                        │
   │     ├─ Worker A ──┐                                                          │
   │     │             │                                                          │
   │     └─ Worker B ──┤                                                          │
   │                   │                                                          │
   │                   ▼                                                          │
   │     FastAPI app — startup hook runs janitor sweep ONCE                       │
   │     │                                                                        │
   │     ├── POST /sessions ──→ ingest.py ──→ storage writes 3 dirs               │
   │     │                            │       (originals/work/pristine)            │
   │     │                            ├──→ hashlib.sha256(data) → meta.json       │
   │     │                            └──→ janitor.sweep() at end                  │
   │     │                                                                        │
   │     ├── POST /sessions/{sid}/process                                          │
   │     │     │                                                                  │
   │     │     ├── check is_session_corrupted(sid) → 410 if true                   │
   │     │     ├── asyncio.wait_for(                                               │
   │     │     │     asyncio.to_thread(process_job, ...),                          │
   │     │     │     timeout=PROCESS_TIMEOUT_SECONDS  # default 60s                │
   │     │     │   ) → TimeoutError → 504 processing_timeout                       │
   │     │     │                                                                  │
   │     │     │   process_job opens work → integrity.verify_original_hash         │
   │     │     │                              → mismatch → mark_corrupted + 503    │
   │     │     │                              → reset-from-pristine, redact, save  │
   │     │     │                                                                  │
   │     │     └── janitor.sweep() at end                                          │
   │     │                                                                        │
   │     ├── GET /health ──→ {status, uptime_seconds, active_sessions,             │
   │     │                    data_dir_bytes, data_dir_pct}                        │
   │     │                                                                        │
   │     └── (other Phase 1–4 endpoints unchanged)                                 │
   │                                                                              │
   │   storage layout (DATA_DIR env, default /data inside container):              │
   │     /data/originals/{sid}/source.pdf   chmod 0o444                            │
   │     /data/work/{sid}/doc.pdf            (work copy)                           │
   │     /data/work/{sid}/meta.json          {page_count, filename,                │
   │                                          original_sha256}  ← Phase 5 +1 field│
   │     /data/work/{sid}/.corrupted         (0-byte sentinel if hash mismatch)    │
   │     /data/pristine/{sid}/doc.pdf        (immutable reset source)              │
   │     /data/outputs/{sid}/{stem}_logoswap.pdf                                   │
   │                                                                              │
   │   AGPL §13 surface (THREE artifacts in lockstep, all required before deploy): │
   │     - public GitHub repo  (memory locked)                                     │
   │     - LICENSE (AGPL-3.0 full text at repo root)                               │
   │     - web/index.html footer:                                                  │
   │       「本工具為 LogoSwap (https://github.com/...) — AGPLv3 授權」              │
   │                                                                              │
   └─────────────────────────────────────────────────────────────────────────────┘
```

### Recommended File Tree (Phase 5 additions only)

```
LogoSwap/                              # repo root
├── Dockerfile                          # NEW — Phase 5 multi-stage
├── .dockerignore                       # NEW — Phase 5
├── docker-compose.example.yml          # NEW — Phase 5 (optional Ubuntu reference)
├── LICENSE                             # NEW — AGPL-3.0 full text (memory lock)
├── README.md                           # NEW (or expand existing) — 3 deploy targets + AGPL
├── zeabur.json                         # NEW — optional Zeabur config (PORT env var)
├── requirements.txt                    # UNCHANGED
├── app/
│   ├── __main__.py                     # NEW — `python -m app` desktop entry
│   ├── main.py                         # MODIFIED — startup hook + /health enhance + new exception handlers
│   ├── config.py                       # MODIFIED — +5 constants (TTL, PROCESS_TIMEOUT, WORKERS, APP_BASE_PATH, CORS_ALLOW_ORIGINS)
│   ├── storage.py                      # MODIFIED — atomic meta.json write + list/age/delete/corrupted helpers
│   ├── services/
│   │   ├── integrity.py                # NEW — compute_original_hash + verify_original_hash
│   │   ├── janitor.py                  # NEW — sweep_expired_sessions
│   │   ├── ingest.py                   # MODIFIED — hash bytes after write, store in meta.json
│   │   ├── pipeline.py                 # MODIFIED — verify_original_hash at /process entry; raise PipelineError if tampered
│   │   └── (others UNCHANGED)
│   └── api/
│       ├── sessions.py                 # MODIFIED — call janitor.sweep() at end of POST
│       └── process.py                  # MODIFIED — asyncio.wait_for + corrupted check + janitor.sweep() at end
├── web/
│   ├── index.html                      # MODIFIED — add <footer> AGPL link block
│   ├── styles/                         # MAYBE MODIFIED — minimal token-aware footer style
│   └── js/                             # UNCHANGED (api.js seam already supports root_path via window.PDFTOOL_API_BASE)
└── tests/
    ├── test_integrity.py               # NEW — hash compute + verify + tampered path
    ├── test_janitor.py                 # NEW — sweep TTL + race protection
    ├── test_health.py                  # NEW — uptime + active_sessions + data_dir fields
    ├── test_process_api.py             # EXTENDED — original_tampered 503 + corrupted 410 + timeout 504
    └── test_storage.py                 # EXTENDED — atomic meta write + new helpers
```

### Pattern 1: Multi-stage Dockerfile for FastAPI + PyMuPDF

**What:** Two-stage Docker build: stage 1 installs Python deps into `/install`, stage 2 copies only the installed packages + app code into a slim runtime layer. Avoids shipping `pip`, build tools, build caches.

**When to use:** Always for production Python containers. Particularly for FastAPI apps where the runtime image should be < 200MB.

**Example:**
```dockerfile
# Source: [CITED: docs.docker.com/build/building/multi-stage/] + [CITED: STACK.md "Containerization" section]
# syntax=docker/dockerfile:1.7

# ─────── Stage 1: builder ───────
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

# Wheels-only install — PyMuPDF, Pillow, FastAPI, uvicorn all ship manylinux wheels for
# 3.12 (verified via PyPI). No system build toolchain required at this stage.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --target /install -r requirements.txt

# ─────── Stage 2: runtime ───────
FROM python:3.12-slim-bookworm

# Run as non-root for defense-in-depth (Pitfall 11 — parser running on untrusted bytes).
# UID/GID 1000 is the conventional non-root default for Debian-based slim images.
RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -m -s /usr/sbin/nologin app

WORKDIR /app

# Copy ONLY the installed packages from builder; never copy pip itself.
COPY --from=builder /install /install
ENV PYTHONPATH=/install \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Phase 5 defaults — overridable per deploy target.
    APP_BASE_PATH="" \
    UVICORN_WORKERS=2 \
    PROCESS_TIMEOUT_SECONDS=60 \
    SESSION_TTL_SECONDS=3600 \
    DATA_DIR=/data \
    LOGOS_DIR=/app/logos

# Application code + assets — owned by the non-root user.
COPY --chown=app:app app/ /app/app/
COPY --chown=app:app web/ /app/web/
COPY --chown=app:app logos/ /app/logos/
COPY --chown=app:app LICENSE README.md /app/

# Per-session storage volume — mount at deploy time.
RUN mkdir -p /data && chown -R app:app /data
VOLUME ["/data"]

USER app

EXPOSE 8000

# Liveness probe — slim has no curl/wget, use stdlib urllib (verified — see Pitfall 2 below).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"

# Exec form, not shell — signals (SIGTERM from container stop) reach uvicorn directly.
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-2} ${APP_BASE_PATH:+--root-path ${APP_BASE_PATH}}"]
```

**Notes on the CMD line:**
- `${PORT:-8000}` honors Zeabur's `$PORT` injection `[CITED: zeabur.com/docs/en-US/deploy/dockerfile]` while defaulting to 8000 for Ubuntu/local.
- `${APP_BASE_PATH:+--root-path ${APP_BASE_PATH}}` — only passes `--root-path` if env is non-empty (avoids `--root-path ""` which is technically valid but confusing).
- `--workers` is parsed by uvicorn at startup; cannot be changed without container restart.
- Using `sh -c "..."` is needed for env-var substitution; exec-form CMD `["uvicorn","app.main:app",...]` cannot do `${PORT:-8000}` expansion. The tradeoff: PID 1 becomes `sh`, which is fine because `sh -c "uvicorn ..."` execs into uvicorn so signals are forwarded correctly. **Alternative (cleaner)**: use an `entrypoint.sh` script and set `ENTRYPOINT ["./entrypoint.sh"]` — Plan-writer's choice.

`.dockerignore` essentials:
```
.git/
.venv/
.venv*/
__pycache__/
**/__pycache__/
*.pyc
.pytest_cache/
.planning/
tests/
data/
*.log
*.tmp.*
CLAUDE.md
.gitignore
.dockerignore
Dockerfile
docker-compose.example.yml
zeabur.json
README.md
```

### Pattern 2: FastAPI `root_path` for prefix mounting (D-A2)

**What:** When deployed behind a strip-prefix reverse proxy (e.g., nginx `location /pdf-logo/ { proxy_pass http://app:8000/; }`), FastAPI's auto-generated docs and OpenAPI routes need to know the external prefix so they emit correct URLs. `root_path` solves this WITHOUT changing route paths — application code still uses `/sessions`, but OpenAPI emits `/pdf-logo/sessions` and Swagger UI knows to call the proxy.

**When to use:** Only when behind a **strip-prefix** proxy (the proxy removes `/pdf-logo` before forwarding). For pass-through proxies (proxy forwards the full path), you need an `APIRouter(prefix="/pdf-logo")` instead — `root_path` doesn't work for pass-through. `[CITED: github.com/fastapi/fastapi/discussions/15430]`

**Example:**
```python
# Source: [CITED: fastapi.tiangolo.com/advanced/behind-a-proxy/]
import os
from fastapi import FastAPI

_APP_BASE_PATH = os.environ.get("APP_BASE_PATH", "")  # e.g. "/pdf-logo" or ""

app = FastAPI(
    title=config.API_TITLE,
    root_path=_APP_BASE_PATH,  # empty string = root mount (current behavior)
)
```

CMD-line equivalent: `uvicorn app.main:app --root-path "$APP_BASE_PATH"` — equivalent to the `root_path=...` constructor arg `[CITED: fastapi.tiangolo.com/advanced/behind-a-proxy/]`. Use ONE or the OTHER, not both (the docs explicitly warn against double-setting).

**Known interaction with StaticFiles(html=True) mounted at "/":**
The existing `app/main.py` mounts the frontend at `/`:
```python
app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
```

Per GitHub discussion #12151 `[CITED: github.com/fastapi/fastapi/discussions/12151]`, mounted StaticFiles routes (especially with `html=True` which serves `index.html` on 404) can mis-redirect to `/<index>` instead of `/<prefix>/<index>` when behind a `root_path`. **Practical mitigation for Phase 5:**

1. Keep `root_path` ONLY for strip-prefix proxy (D-A2's "case b") and document that **for the pass-through case, deploy with `APP_BASE_PATH=""` and use an `APIRouter(prefix=...)` wrapper if and when needed**.
2. The Phase 1 frontend seam `window.PDFTOOL_API_BASE` already handles the browser side — even if the static mount itself doesn't relativize URLs correctly, the JS modules (api.js, viewer.js) all consume `API_BASE` so the frontend HTML can be served at any path and still call the API at the configured prefix.
3. **Test target**: Plan 05-01 should include a smoke test with `APP_BASE_PATH=/pdf-logo` + curl `http://localhost:8000/pdf-logo/health` returns 200, and `http://localhost:8000/health` returns either 200 (FastAPI's `root_path` is a hint, not a route filter — the actual path on the wire is still `/health`) or 404 depending on uvicorn's interpretation.

**The pragmatic call:** For v1 Phase 5, **default everything to `APP_BASE_PATH=""` (root mount)** and document `APP_BASE_PATH=/pdf-logo` as "experimental — test with your proxy before relying on it." This matches D-A2's "預設 root mount" wording.

### Pattern 3: `python -m app` desktop entry point (D-A4 target 2)

**What:** A small `app/__main__.py` that launches uvicorn programmatically and opens the browser automatically — turns the same code base into a desktop-style tool for internal users who can't run Docker.

**Example:**
```python
# app/__main__.py — NEW for Phase 5
"""Desktop entry: `python -m app` boots uvicorn + opens the browser.

Per D-A4, target 2 of Phase 5 is a downloadable Python package for internal users
who run the tool locally (no Docker, no Ubuntu). This entry point is what `python -m
app` invokes. It is a thin wrapper around `uvicorn.run` plus a deferred
`webbrowser.open` — no business logic.

Note on workers on Windows: uvicorn 0.30+ uses `multiprocessing.spawn` (not fork),
which works on Windows; but every module imported in the main process must be
import-safe under spawn (no top-level side effects that don't reproduce in child
processes). All existing app modules already satisfy this — `app/main.py` only
constructs `FastAPI()` at module load, no side-effecting startup.
"""
from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

from . import config


def _open_browser(url: str) -> None:
    """Open the browser AFTER a short delay so uvicorn is listening.

    A bare `webbrowser.open` racing against uvicorn startup can hit the browser
    before the server is ready, giving a connection-refused page that the user
    must refresh. 1 second is generous on a cold start and imperceptible to users.
    """
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    workers = int(os.environ.get("UVICORN_WORKERS", "1"))  # desktop default 1, no need for 2
    url = f"http://{host}:{port}"

    # Open browser only if not in reload mode (which would open it twice).
    if not os.environ.get("UVICORN_NO_BROWSER"):
        _open_browser(url)

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers,
        # NOTE: workers > 1 is incompatible with `reload=True`. Desktop entry
        # doesn't set reload (production-like) so workers > 1 is fine.
    )


if __name__ == "__main__":
    main()
```

**Cross-platform DATA_DIR for desktop:** Default `./data` (current working dir) — simplest, predictable, the user can see where their files are. README documents `DATA_DIR` env var if they want `~/.logoswap/data`. Adding `platformdirs` would buy `user_data_dir()` resolution but adds a dep — **recommended: just document `DATA_DIR=$HOME/.logoswap/data` in README + leave default as `./data`.** No new dep.

### Pattern 4: Sync timeout via `asyncio.wait_for(asyncio.to_thread(...), timeout=...)` (D-D3)

**What:** `process_job` is sync CPU-bound (PyMuPDF holds the GIL during render/redact). The current `app/api/process.py` uses `await run_in_threadpool(pipeline.process_job, session_id, job)` which is non-blocking but unbounded — Phase 5 needs a 60s timeout.

**The semantics that must be in the plan:**

`asyncio.wait_for(asyncio.to_thread(func, ...), timeout=60)` will raise `TimeoutError` after 60s, BUT **the underlying thread keeps running** `[VERIFIED: docs.python.org/3/library/asyncio-task.html + multiple sources]`. Python cannot kill a thread (no `pthread_cancel` analog in CPython for sync code). Consequence: the HTTP response returns 504 promptly, but the worker is still busy doing PyMuPDF work until either it completes naturally OR the entire worker process is restarted.

**Why this is acceptable for v1 (and the plan should write it down):**

1. Workers default to 2 (D-D2) — at most 1 worker can be stuck on a runaway /process; the other still serves /pages preview / /sessions GET / /health.
2. The Phase 4 `MAX_RENDER_PIXELS=40MP` + `MAX_PAGES=30` + `MAX_UPLOAD_BYTES=50MB` ceilings make a real worst-case process much less than infinite — likely 10–30s on a hostile CAD file, not minutes.
3. The 504 response tells the user "處理逾時,請改用較小檔案或重試"; if they retry, the new /process starts on the OTHER worker; meanwhile the stuck thread either finishes (small CPU debt) or the OS eventually OOM-kills the worker process and the container supervisor restarts it.
4. Future v1.x: if real-world abuse appears, `ProcessPoolExecutor` (D-D1 deferred) is the right escalation — sub-processes CAN be killed.

**Example:**
```python
# app/api/process.py — modified section
import asyncio
from fastapi import HTTPException

from .. import config

@router.post("/sessions/{session_id}/process")
async def process_session(session_id: str, job: JobSpec) -> dict:
    _require_session(session_id)

    # Phase 5: corrupted-session sentinel check FIRST (D-C3). If a prior /process
    # detected hash mismatch on originals/, the session is quarantined.
    if storage.is_session_corrupted(session_id):
        raise HTTPException(
            status_code=410,  # Gone — session no longer usable
            detail={
                "code": "session_corrupted",
                "message": "此工作階段已標記為異常,請重新上傳檔案。",
            },
        )

    # Phase 5: bound the sync CPU-bound work in 60s (D-D3). Per docs, the thread
    # itself cannot be killed if the timer fires — the HTTP response returns 504
    # while the thread completes in the background. The TTL janitor sweeps the
    # session later. workers=2 keeps preview/GET unblocked.
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(pipeline.process_job, session_id, job),
            timeout=config.PROCESS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as err:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "processing_timeout",
                "message": f"處理逾時(超過 {config.PROCESS_TIMEOUT_SECONDS} 秒),"
                           "請改用較小檔案或減少框選區域數量。",
            },
        ) from err
    finally:
        # D-B1 trigger point (c): /process end → sweep expired sessions.
        # Wrapped in try/except so a janitor failure NEVER taints the response.
        try:
            janitor.sweep_expired_sessions()
        except Exception:
            pass  # janitor errors logged inside the function; don't escalate.
```

**Why not `anyio.fail_after`?** Functionally equivalent for this case — `anyio` is already a FastAPI transitive dep. `asyncio.wait_for` is stdlib + the more widely-known API. Plan-writer's choice. Recommend `asyncio.wait_for` for stdlib clarity.

**Why not `run_in_threadpool`?** `run_in_threadpool` (currently used) uses Starlette's anyio threadpool, which has the same "can't kill the thread" property. Switching to `asyncio.to_thread` is purely so `asyncio.wait_for` can wrap it cleanly. No semantic change at the worker level.

### Pattern 5: Atomic meta.json write with original_sha256 field (D-C1)

**What:** `write_session_meta` currently uses `json.dump(payload, fh)` — direct write. Phase 5 adds `original_sha256` field. The write must be **atomic** so a crash between "wrote hash, didn't write page_count" can't leave the file half-baked.

**Cross-platform atomic file rename:**

On Linux, `os.replace(src, dst)` is atomic if both paths are on the same filesystem (POSIX `rename(2)`). On Windows, `os.replace` is also atomic since Python 3.3 (uses `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`). Both behaviors are guaranteed `[CITED: docs.python.org/3/library/os.html#os.replace]`.

**Example:**
```python
# app/storage.py — modified
import json
import os
import tempfile
from pathlib import Path

def write_session_meta(
    session_id: str,
    *,
    page_count: int,
    filename: str,
    original_sha256: str,  # Phase 5: NEW required field
) -> Path:
    """Persist ingest-time metadata atomically.

    Phase 5 adds ``original_sha256`` (D-C1). Written via temp-file + os.replace so a
    crash between bytes leaves either the OLD file or the NEW file — never a
    half-written JSON that read_session_meta would parse as missing fields.
    """
    dest = meta_path(session_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "page_count": int(page_count),
        "filename": str(filename),
        "original_sha256": str(original_sha256),  # Phase 5
    }
    # tempfile in the SAME dir as dest so os.replace stays on the same FS.
    fd, tmp_path = tempfile.mkstemp(
        prefix=".meta.", suffix=".json.tmp", dir=str(dest.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp_path, dest)  # atomic on Linux + Windows
    except Exception:
        # Clean up the temp on failure so we don't leave .meta.*.json.tmp litter.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return dest
```

**Reading side:**
```python
def read_session_meta(session_id: str) -> dict | None:
    """Return metadata or None if missing/unreadable."""
    # (existing logic mostly unchanged — but the dict shape is now
    #  {page_count, filename, original_sha256})
    # ...
    if not isinstance(data, dict) or "page_count" not in data:
        return None
    return data
```

**Backward-compat for Phase 1–4 sessions without `original_sha256`:**
Per Open Question 1 below, Phase 5 chooses **option B** (reject as `session_corrupted` / require re-upload). Implementation: `verify_original_hash(session_id)` reads meta, if `original_sha256` field missing → treat as `session_corrupted` (mark + 503 with friendly message "此工作階段為舊版,請重新上傳檔案"). Combined with D-B2's 1-hour TTL, all legacy sessions naturally expire within 1h of Phase 5 deployment.

### Pattern 6: Integrity verification (D-C1..D-C4)

**Example:**
```python
# app/services/integrity.py — NEW for Phase 5
"""SHA-256 baseline + verify for originals/ — runtime enforcement of D-05 invariant.

The deferred-mutation D-05 invariant (Phase 2 lock, Phase 4 STRENGTHENED) says
originals/ is NEVER mutated by the pipeline. Phase 1–4 enforced this STRUCTURALLY
(chmod 0o444 + pipeline reads only from pristine/). Phase 5 adds RUNTIME verification:
every /process re-hashes originals/source.pdf and compares against the baseline
captured at ingest time. If they disagree, the session is quarantined.

D-C4: only originals/ is verified. pristine/ is internal — trusted by the AGPL
seam + storage isolation.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from .. import storage

logger = logging.getLogger(__name__)


def compute_original_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data``.

    Called from ingest after writing the originals/ file but before writing meta.json.
    For a 50MB upload this is ~150–250ms on a typical Ubuntu VM — well below the
    /sessions request budget. We already have the bytes in memory at this point
    (the upload buffer in api/sessions.py), so chunked streaming is unnecessary.
    """
    return hashlib.sha256(data).hexdigest()


def verify_original_hash(session_id: str) -> None:
    """Compare originals/source.pdf against the baseline in meta.json.

    Raises ``IntegrityError("original_tampered", ...)`` if the hashes differ OR
    if the meta sidecar lacks an ``original_sha256`` field (legacy session).
    Side effect on mismatch: writes the corrupted sentinel so subsequent calls
    short-circuit at the API layer.
    """
    meta = storage.read_session_meta(session_id)
    if meta is None or "original_sha256" not in meta:
        # Legacy session (Phase 1–4) or sidecar lost. Per Phase 5 plan choice,
        # treat as corrupted — user re-uploads.
        storage.mark_session_corrupted(session_id)
        raise IntegrityError(
            "session_corrupted",
            "此工作階段為舊版或資料不完整,請重新上傳檔案。",
        )

    expected = meta["original_sha256"]
    original = storage.original_path(session_id)
    actual = hashlib.sha256(Path(original).read_bytes()).hexdigest()

    if actual != expected:
        # Structured log — JSON-ish line format that uvicorn's stdout will pass
        # through unchanged. No CRLF injection risk (we control all fields).
        logger.error(
            "original_tampered",
            extra={
                "session_id": session_id,
                "expected_hash": expected,
                "actual_hash": actual,
                "path": str(original),
                "timestamp": time.time(),
            },
        )
        storage.mark_session_corrupted(session_id)
        raise IntegrityError(
            "original_tampered",
            "系統偵測到原始檔異常,此工作階段已停用,請重新上傳檔案。",
        )


class IntegrityError(Exception):
    """Typed integrity failure — caught by the pipeline and re-raised as PipelineError.

    Plan-writer: this is a thin signal class. The pipeline catches it and converts
    to PipelineError(code, message) so main.py's existing PipelineError handler
    routes it to the right 4xx/5xx (503 for original_tampered, 410 for
    session_corrupted). Keeps integrity logic independent of FastAPI types.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
```

**Plug into pipeline:**
```python
# app/services/pipeline.py — modified entry
def process_job(session_id: str, job_spec) -> dict:
    work = storage.work_path(session_id)
    pristine = storage.pristine_path(session_id)

    # Phase 5: verify originals/ hash BEFORE reset-from-pristine (D-C2). If the
    # baseline is missing or mismatched, raise PipelineError — main.py routes it
    # to 503 original_tampered / 410 session_corrupted.
    try:
        integrity.verify_original_hash(session_id)
    except integrity.IntegrityError as err:
        raise PipelineError(err.code, err.message) from err

    # (existing deferred-mutation reset + redact + save logic continues unchanged)
    # ...
```

**`_PROCESS_STATUS` extension in main.py:**
```python
_PROCESS_STATUS: dict[str, int] = {
    # Phase 2 (unchanged)
    "residual_content": 422,
    "page_out_of_range": 422,
    "work_copy_misconfigured": 500,
    # Phase 5: NEW
    "original_tampered": 503,
    "session_corrupted": 410,
    "processing_timeout": 504,
}
```

### Pattern 7: Synchronous janitor (D-B1..D-B4)

**Example:**
```python
# app/services/janitor.py — NEW for Phase 5
"""Synchronous session-directory janitor (D-B1).

Three trigger points (no background scheduler):
  - app startup (main.py FastAPI startup event)
  - POST /sessions end (api/sessions.py)
  - POST /process end (api/process.py)

Each call sweeps EVERY session whose dir mtime exceeds SESSION_TTL_SECONDS in any
of the four kinds (originals/work/outputs/pristine). A session is deleted as a
whole — all four dirs at once (D-B3).

Race protection (D-B4): mtime TTL (3600s default) is 60x the /process timeout
(60s default), so a session being actively /process'd cannot age out mid-job.
A defensive try/except + best-effort retry handles concurrent rmtree from another
worker (e.g. two /process completing back-to-back, both calling sweep).
"""
from __future__ import annotations

import errno
import logging
import os
import shutil
import stat
import time
from pathlib import Path

from .. import config, storage

logger = logging.getLogger(__name__)

_KINDS = ("originals", "work", "outputs", "pristine")


def _on_rm_error(func, path, exc_info) -> None:
    """rmtree error handler — re-chmod a read-only file then retry.

    originals/source.pdf is chmod 0o444 (write-once guarantee). On Linux this
    only stops modification — unlinking it from a writable parent dir works
    fine. On Windows, however, ``DeleteFile`` on a read-only file fails with
    PermissionError. Re-chmod 0o644 then retry covers both platforms.

    Phase 5 plan: use 3-arg signature (onerror, deprecated in 3.12 but still
    works to 3.14) OR 5-arg signature (onexc, 3.12+ recommended). Pick onexc
    when targeting >= 3.12 only.
    """
    excvalue = exc_info[1] if exc_info else None
    if isinstance(excvalue, PermissionError) and func in (os.unlink, os.rmdir, os.remove):
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            func(path)
            return
        except OSError:
            pass
    logger.warning("janitor: rmtree failed on %s: %s", path, excvalue)


def _safe_rmtree(path: Path) -> bool:
    """Best-effort recursive delete; returns True on success, False on failure."""
    if not path.exists():
        return True
    try:
        # Python 3.12+: onexc (preferred). Python 3.10–3.11: onerror.
        # Use onerror for compatibility — the signature differs but our handler
        # supports the legacy 3-tuple form.
        shutil.rmtree(path, onerror=_on_rm_error)
        return not path.exists()
    except OSError as err:
        if err.errno == errno.ENOTEMPTY:
            # Race: another worker partially deleted; consider success-if-gone.
            return not path.exists()
        logger.warning("janitor: rmtree raised on %s: %s", path, err)
        return False


def _delete_session(session_id: str) -> None:
    """Remove a session's dirs from ALL FOUR KINDS (D-B3)."""
    for kind in _KINDS:
        try:
            target = storage.subdir(kind, session_id)
        except storage.InvalidSessionId:
            # A non-conforming dir name in DATA_DIR/<kind>/ — skip; janitor only
            # deletes well-formed sessions. Stray dirs are an ops concern, not
            # janitor's responsibility.
            return
        _safe_rmtree(target)


def _enumerate_session_ids(data_dir: Path) -> set[str]:
    """Find every session id present in any of the four kinds.

    A session may have dirs in 1..4 of the kinds (e.g. a crash between
    write_original and write_pristine leaves originals/ orphaned without work/).
    Union of all observed IDs covers orphaned remnants too.
    """
    sids: set[str] = set()
    for kind in _KINDS:
        kind_dir = data_dir / kind
        if not kind_dir.is_dir():
            continue
        for entry in kind_dir.iterdir():
            if entry.is_dir() and storage._SESSION_ID_RE.fullmatch(entry.name):
                sids.add(entry.name)
    return sids


def _session_max_mtime(session_id: str) -> float | None:
    """Return the LATEST mtime across the four kind-dirs for a session.

    Latest, not earliest, because activity in any kind (e.g. /process writing a
    new outputs/ file) resets the clock for that session as a whole. Using max
    avoids deleting a session that just produced an output 5 minutes ago because
    its originals/ is 55 minutes old.
    """
    mtimes: list[float] = []
    for kind in _KINDS:
        try:
            target = storage.subdir(kind, session_id)
        except storage.InvalidSessionId:
            continue
        if target.exists():
            try:
                mtimes.append(target.stat().st_mtime)
            except OSError:
                pass
    return max(mtimes) if mtimes else None


def sweep_expired_sessions(now: float | None = None) -> int:
    """Delete every session older than SESSION_TTL_SECONDS in ALL four dirs.

    Returns the count of sessions deleted (for logs / tests). Never raises —
    a janitor failure must not taint the request that triggered it.
    """
    if now is None:
        now = time.time()
    ttl = config.SESSION_TTL_SECONDS
    data_dir = Path(config.DATA_DIR)
    if not data_dir.is_dir():
        return 0

    try:
        sids = _enumerate_session_ids(data_dir)
    except OSError as err:
        logger.warning("janitor: cannot enumerate sessions: %s", err)
        return 0

    deleted = 0
    for sid in sids:
        mtime = _session_max_mtime(sid)
        if mtime is None:
            continue
        age = now - mtime
        if age > ttl:
            _delete_session(sid)
            deleted += 1
    if deleted:
        logger.info("janitor: deleted %d expired session(s)", deleted)
    return deleted
```

**`storage.py` helpers janitor needs:**
```python
# Phase 5 additions to storage.py

def mark_session_corrupted(session_id: str) -> Path:
    """Write a 0-byte .corrupted sentinel under work/{sid}/.

    Subsequent /process / /result calls check this and return 410. The sentinel
    survives janitor's TTL until the whole session expires.
    """
    work_dir = subdir("work", session_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    sentinel = work_dir / ".corrupted"
    sentinel.touch(exist_ok=True)
    return sentinel


def is_session_corrupted(session_id: str) -> bool:
    """True if the session is quarantined (a .corrupted sentinel exists in work/)."""
    try:
        return (subdir("work", session_id) / ".corrupted").is_file()
    except InvalidSessionId:
        return False


def list_session_ids() -> Iterator[str]:
    """Yield every well-formed session id present in any of the four kinds."""
    data_dir = _data_dir()
    seen: set[str] = set()
    for kind in _KINDS:
        kind_dir = data_dir / kind
        if not kind_dir.is_dir():
            continue
        for entry in kind_dir.iterdir():
            if entry.is_dir() and _SESSION_ID_RE.fullmatch(entry.name) and entry.name not in seen:
                seen.add(entry.name)
                yield entry.name


def session_age_seconds(session_id: str) -> float | None:
    """Return seconds since the session was last touched in any kind-dir.

    Uses max-mtime across kinds so /process producing outputs/ refreshes the
    session age as a whole.
    """
    # (implementation parallels janitor._session_max_mtime — share or duplicate)
    ...


def delete_session(session_id: str) -> None:
    """Remove the session's dirs from ALL four kinds. No-op if absent.

    Public helper for the janitor; also useful for test cleanup.
    """
    # (delegate to janitor._delete_session or duplicate logic — plan-writer's choice)
    ...
```

### Pattern 8: Enhanced /health (D-D4)

**Example:**
```python
# app/main.py — replace existing /health
import shutil
import time
from pathlib import Path

from . import config, storage

_START_TIME = time.time()  # captured once per worker process


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Liveness + data-dir telemetry probe.

    Polled by Docker HEALTHCHECK (Dockerfile), Zeabur LB, and Ubuntu nginx upstream
    check. All values are O(1)-ish — disk_usage is a single statfs syscall,
    listing originals/ counts dir entries without opening them.
    """
    uptime = max(0.0, time.time() - _START_TIME)

    # active_sessions = count of well-formed session dirs in originals/ (the
    # canonical 'session exists' indicator per session_exists()).
    originals_root = Path(config.DATA_DIR) / "originals"
    active_sessions = 0
    if originals_root.is_dir():
        try:
            active_sessions = sum(
                1 for entry in originals_root.iterdir()
                if entry.is_dir() and storage._SESSION_ID_RE.fullmatch(entry.name)
            )
        except OSError:
            active_sessions = -1  # unreadable — distinguish from "zero"

    # data_dir usage — best-effort (a network mount may not support statvfs).
    data_dir_bytes = 0
    data_dir_pct = 0.0
    try:
        usage = shutil.disk_usage(str(config.DATA_DIR))
        data_dir_bytes = usage.used
        data_dir_pct = round(100.0 * usage.used / usage.total, 2)
    except (OSError, FileNotFoundError):
        pass  # leave zeros

    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 2),
        "active_sessions": active_sessions,
        "data_dir_bytes": data_dir_bytes,
        "data_dir_pct": data_dir_pct,
    }
```

### Pattern 9: AGPL §13 surface (memory lock)

**The three artifacts (ALL required before any public deploy):**

**Artifact 1: `LICENSE` at repo root (AGPL-3.0 full text).**
Source: `https://www.gnu.org/licenses/agpl-3.0.txt` — copy verbatim into `LICENSE` file. Plan task should `curl` or manually copy the canonical FSF text. Length ≈ 34KB. ASCII only. Do NOT modify (the license itself prohibits modifying the license text).

**Artifact 2: Public GitHub repository.**
Memory-locked: must be public before Zeabur deploy. Plan task should include "push current branch to a public GitHub repo (user to confirm URL)." Once pushed, the URL goes into:
- `README.md` AGPL section.
- `web/index.html` footer (Artifact 3).
- Optionally an env var `AGPL_SOURCE_URL` (default to the hard-coded URL) so a fork can override.

**Artifact 3: UI source link.**
The minimum compliant surface is "a link to the corresponding source code visible to every user who interacts with the network service" `[CITED: opensource.com/article/17/1/providing-corresponding-source-agplv3-license]`.

Recommended footer block to add to `web/index.html`:
```html
<!-- AGPL §13 source disclosure — required for network deployment of AGPL software.
     Link visible to every browser session; no login wall, no JS-conditional rendering. -->
<footer class="app-footer" role="contentinfo">
  <p class="app-footer__text">
    本工具為 <a class="app-footer__link"
                href="https://github.com/&lt;OWNER&gt;/LogoSwap"
                target="_blank" rel="noopener">LogoSwap</a>
    — 依 <a class="app-footer__link"
            href="https://www.gnu.org/licenses/agpl-3.0.html"
            target="_blank" rel="noopener">AGPLv3</a> 授權釋出。
  </p>
</footer>
```

Token-aware styling (`styles/app.css`):
```css
.app-footer {
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--color-border-subtle);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
}
.app-footer__link { color: var(--color-link); text-decoration: underline; }
.app-footer__link:hover { color: var(--color-link-hover); }
```

(Adjust token names to the exact Phase 1 token set — `tokens.css`.)

**Why this configuration satisfies §13:**
- Every user who interacts with the network service sees the link → "prominently offered" requirement met.
- Link points to corresponding source on a public GitHub → "Corresponding Source available" met.
- LICENSE file in the repo identifies the license terms → "license terms must accompany the source" met.

**What we are NOT doing (and don't need to do):**
- Embedding the full LICENSE text in the UI (a link is sufficient).
- Modifying PyMuPDF's source (no modification = no obligation to redistribute modified versions, but we still must offer the source we deploy — which is the unmodified PyMuPDF + our app code).
- Building a `/agpl-source` endpoint that serves the source as a tarball (the GitHub URL is the canonical source).

**`README.md` AGPL section recommended wording:**
```markdown
## License

LogoSwap is licensed under the GNU AGPL-3.0 (see [LICENSE](./LICENSE)). It depends on
[PyMuPDF](https://pymupdf.readthedocs.io/), which is dual-licensed AGPL-3.0 / Artifex
commercial. If you deploy LogoSwap behind a network and want to avoid AGPL obligations
on your users, you must either: (a) make the corresponding source available to those
users (the LogoSwap default), or (b) replace PyMuPDF with a non-AGPL alternative
(or purchase a commercial license from Artifex).

When deployed, LogoSwap displays a source link in the UI footer pointing at this
repository — that satisfies AGPL §13 for unmodified deployments. If you fork and
modify the code, you must update the footer link to point at your fork.
```

### Anti-Patterns to Avoid

- **`HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1`** — `curl` is NOT in `python:3.12-slim`. Use `python -c "import urllib.request; ..."` (Pitfall 2 below).
- **`uvicorn.run("app.main:app", reload=True, workers=2)`** — `reload` and `workers` are mutually exclusive `[CITED: uvicorn.dev/deployment/]`. Desktop entry must not set reload.
- **`shutil.rmtree(path)` without `onerror`/`onexc`** — fails on chmod 0o444 file on Windows; janitor leaves stale dirs forever.
- **`json.dump(payload, fh)` for meta.json under concurrent /process** — non-atomic; corrupted half-write can cause `read_session_meta` to return `None` and trigger false `session_corrupted`. Use temp + os.replace.
- **`asyncio.wait_for(asyncio.to_thread(...), 60)` assumed to KILL the thread** — it does not. Plan must document this and rely on `MAX_RENDER_PIXELS` ceiling + workers=2 to keep the system usable.
- **`StaticFiles(html=True)` + `root_path` + assuming `/` redirects work** — known bug in StaticFiles. Mitigate by defaulting `APP_BASE_PATH=""` (root mount) and documenting prefix mount as experimental.
- **`webbrowser.open(url)` before `uvicorn.run(...)`** — race condition; browser hits before server ready. Use `threading.Timer(1.0, ...)`.
- **Mounting `pip` itself into the runtime image** — keeps build deps in production layer. Multi-stage `COPY --from=builder /install /install` only.
- **AGPL footer link as conditional JS-rendered element** — must be in static HTML so it's visible without JS execution.
- **Setting `Image.MAX_IMAGE_PIXELS = config.MAX_INGEST_IMAGE_PIXELS` globally** — Pillow's default is already 89_478_485 and ingest.py already validates `src.width * src.height > config.MAX_INGEST_IMAGE_PIXELS`. Global set adds nothing. **Recommend skipping** the Pillow global setting (Claude's discretion → `false`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic file write | Manual temp-rename loop | `tempfile.mkstemp` + `os.replace` | `os.replace` is atomic on Linux + Windows since 3.3; rolling your own gets the temp dir wrong (cross-FS = non-atomic) |
| Process supervisor | Custom systemd / supervisord | uvicorn `--workers N` (built-in supervisor) | uvicorn 0.30+ does spawn-based multi-process; gunicorn adds nothing for our scale (Pitfall 8 / D-D2) |
| Background scheduler | APScheduler / Celery / custom asyncio task | Synchronous janitor at 3 trigger points (D-B1) | Internal tool, 1-hour TTL is forgiving — no need for a scheduler |
| Health check HTTP client | Bash `nc localhost 8000` | `python -c "import urllib.request; urllib.request.urlopen(...)"` | urllib is in stdlib (= no curl/wget in slim image); 5-line one-liner |
| Disk usage | `du -sh` shell out | `shutil.disk_usage(path)` | Single statvfs call, cross-platform |
| Random session id | UUID concat / time-based | `secrets.token_urlsafe(16)` (already in storage.py) | Already done; Phase 5 changes nothing |
| Cross-platform browser open | Hard-coded `open` / `xdg-open` / `start` | `webbrowser.open(url)` | stdlib; picks the right command per OS |
| Multi-stage Dockerfile | Single-stage with `RUN apt-get clean` | Two stages: builder COPY → runtime COPY | Single-stage can't strip pip + caches; multi-stage is the canonical pattern |
| AGPL §13 source offer | Source-tarball endpoint at `/source.tar.gz` | Footer link to public GitHub repo | GitHub IS the canonical source distribution; tarball endpoint is more maintenance burden |
| TLS termination | nginx-in-image | External reverse proxy (D-A1) | Zeabur / Ubuntu nginx already do TLS; building it in is wasted ops |

**Key insight:** Phase 5 is **almost entirely stdlib + config + Dockerfile + a single-page footer**. No new dependencies. The most "complex" new code is `janitor.py` and `integrity.py` — both < 100 lines each, both pure I/O + hashlib. Anything that feels like it needs a library (scheduler, supervisor, health checker, TLS) belongs OUTSIDE the image per D-A1/D-B1 locks.

## Runtime State Inventory

Not a rename/refactor phase — Phase 5 introduces deployment infrastructure but does not rename or migrate any existing identifier. The closest concern is the meta.json schema upgrade (adds `original_sha256`), which is addressed in Open Question 1.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | meta.json files for Phase 1–4 sessions (no `original_sha256` field) | Treat legacy sessions as corrupted → re-upload. D-B2's 1h TTL means all legacy sessions disappear within 1h of deployment. Document in Plan 05-02 |
| Live service config | None — Phase 5 is the first deployment; nothing live yet | N/A |
| OS-registered state | None — no systemd / pm2 / Task Scheduler entries from Phase 1–4 | N/A |
| Secrets/env vars | New env vars added (`APP_BASE_PATH`, `UVICORN_WORKERS`, `PROCESS_TIMEOUT_SECONDS`, `SESSION_TTL_SECONDS`, `CORS_ALLOW_ORIGINS`) — all have safe defaults so existing dev runs don't break | None — additive only |
| Build artifacts / installed packages | No PyInstaller / egg-info concerns; pure source distribution | N/A |

**Nothing found in OS-registered / live-service / build-artifact categories** — verified by: no Dockerfile / docker-compose / systemd unit file exists yet in repo (`ls Dockerfile LICENSE docker-compose.yml zeabur.json` returns all 4 not found).

## Common Pitfalls

### Pitfall 1: `asyncio.wait_for(asyncio.to_thread(...), timeout=60)` does NOT kill the thread

**What goes wrong:** /process returns 504 after 60s, but the PyMuPDF work continues until naturally complete. A pathological CAD file could keep one worker busy for minutes after the HTTP timeout.

**Why it happens:** Python cannot kill a running thread executing sync code (no `pthread_cancel` analog). `asyncio.wait_for` only abandons the `await` — the underlying coroutine wrapping `to_thread` raises `CancelledError`, but the thread continues in the background `[VERIFIED: docs.python.org/3/library/asyncio-task.html + multiple stackoverflow + web search]`.

**How to avoid:**
- Accept this limitation explicitly in the plan. Workers default to 2 (D-D2), so at most one worker is stuck.
- Phase 4 `MAX_RENDER_PIXELS=40MP` + `MAX_PAGES=30` already bound the worst-case work to seconds, not minutes.
- Document the behavior in code comments AND in README so future maintainers don't think the timeout is a hard cancel.
- If real abuse appears, escalate to `ProcessPoolExecutor` (D-D1 deferred path) where sub-processes CAN be killed.

**Warning signs:** /health shows /process worker stuck at high CPU for > 60s after a 504 response; concurrent /process requests all going to the same worker because the other is "free" by uvicorn's accounting but actually still running.

### Pitfall 2: `python:3.12-slim` ships without curl / wget — HEALTHCHECK with `curl` silently fails

**What goes wrong:** `HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1` reports "unhealthy" forever because `curl` is not installed in slim images. Docker shows the container as unhealthy → Zeabur LB removes it from routing → container is killed → restart loop.

**Why it happens:** `python:3.12-slim` is intentionally minimal; only Python stdlib + apt essentials. `curl` is ~12MB and not included.

**How to avoid:** Use Python stdlib `urllib.request` for the healthcheck — guaranteed available because the image is Python.
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"
```

**Alternative:** `apt-get install -y --no-install-recommends curl` in the runtime stage (+12MB). Not recommended — stdlib approach has zero footprint.

**Warning signs:** `docker ps` shows `(unhealthy)` status; Zeabur dashboard shows continuous restarts.

### Pitfall 3: `shutil.rmtree` on chmod 0o444 originals/source.pdf on Windows

**What goes wrong:** Janitor tries to delete a session whose `originals/{sid}/source.pdf` is read-only (chmod 0o444 from Phase 1's write-once guarantee). On Windows, `os.unlink` on a read-only file raises `PermissionError`. `shutil.rmtree` propagates → janitor logs warning, session never deleted, disk fills.

**Why it happens:** Phase 1's `write_original` does `os.chmod(dest, 0o444)` to enforce the write-once invariant. POSIX semantics: file readonly ≠ dir readonly, so unlink from a writable parent dir succeeds on Linux. Windows enforces readonly on unlink (consistent with `DeleteFile` rejecting read-only files).

**How to avoid:** `shutil.rmtree(path, onerror=_handler)` where `_handler` chmod's to writable then retries. See `_on_rm_error` in Pattern 7.

**Note on the API drift:** Python 3.12 introduced `onexc` (5-arg signature) and deprecated `onerror` (3-arg). Both still work to 3.14. For broadest compatibility, write the handler to accept the legacy 3-arg form (works on 3.10–3.14).

**Warning signs:** `data/originals/{sid}/` survives 1h+ on Windows; Linux fine; janitor logs "rmtree failed on .../source.pdf: PermissionError".

### Pitfall 4: meta.json schema migration — legacy sessions lack `original_sha256`

**What goes wrong:** Phase 5 deploys; existing Phase 4 sessions on the filesystem (e.g., the UAT session a user kept open in a browser tab) suddenly fail /process with `original_tampered` because the verify step reads `meta['original_sha256']` and gets `KeyError`.

**Why it happens:** Phase 1–4 `write_session_meta` only wrote `{page_count, filename}`. The schema is being upgraded.

**How to avoid:** Per Open Question 1 decision, treat missing `original_sha256` as `session_corrupted` (410) with friendly "舊版工作階段,請重新上傳" message. Combined with D-B2's 1h TTL, all legacy sessions expire within 1h of Phase 5 deploy. Document the 1h window in the Phase 5 deploy runbook (Plan task: "deploy → wait 1h → no more 410s observed").

**Warning signs:** First hour post-deploy: spike in 410 `session_corrupted` for users with stale browser tabs from the pre-Phase-5 era.

### Pitfall 5: `FastAPI(root_path=...)` + `app.mount("/", StaticFiles(html=True))` interaction

**What goes wrong:** Behind `APP_BASE_PATH=/pdf-logo` strip-prefix nginx, the SPA loads at `https://intranet/pdf-logo/`, browser requests `/pdf-logo/js/api.js`, nginx strips to `/js/api.js`, FastAPI tries to serve from `web/js/api.js` — works. BUT, root navigations (`/pdf-logo/`) can trigger a redirect to `/<something>` that drops the prefix → broken SPA. `[CITED: github.com/fastapi/fastapi/discussions/12151]`

**Why it happens:** Starlette's `StaticFiles(html=True)` issues a 307 redirect when serving `index.html` for a directory request. The redirect target uses the unprefixed path (FastAPI's `root_path` is consulted for *outgoing URLs* in OpenAPI but not always for StaticFiles redirects).

**How to avoid:**
- Default `APP_BASE_PATH=""` (root mount) per D-A2's "預設 root mount" — this trivially works.
- For deploy target 3 (Ubuntu nginx prefix), choose pass-through proxy + `APIRouter(prefix="/pdf-logo")` instead of strip-prefix + `root_path` if the static-mount issue bites in practice.
- Document this in Phase 5 README "Embedding behind nginx" section: "If you use a strip-prefix proxy AND see redirect issues, switch to a sub-domain (pdf-logo.intranet) or to a pass-through proxy."
- For Zeabur (target 1), `APP_BASE_PATH` is always empty (Zeabur hosts at a sub-domain) → no issue.

**Warning signs:** `curl -I http://localhost/pdf-logo/` returns `Location: /` (the prefix is dropped); browser shows SPA loaded but JS fails because assets are at `/pdf-logo/js/*` not `/js/*`.

### Pitfall 6: AGPL §13 misunderstanding — internal != exempt

**What goes wrong:** Team assumes "it's internal LAN, AGPL doesn't apply" and skips the source-link. Later the tool gets shown to a vendor / accessed via VPN by a contractor / iframed into the public-facing approval site without a license review → AGPL violation.

**Why it happens:** §13 is triggered by "interacting with the software through a computer network" — any HTTP user, even internal, technically counts. The community consensus is "purely internal LAN is OK in practice" but the safe + memory-locked answer is: just put the source link in the footer, it costs nothing.

**How to avoid:** Memory lock — Plan 05-01 task includes Artifact 1 (LICENSE) + Artifact 2 (GitHub public) + Artifact 3 (UI link) as a single non-negotiable deliverable.

**Warning signs:** Any plan task that says "AGPL link can wait for Phase 6" — reject. Memory: locked.

### Pitfall 7: uvicorn `--workers > 1` on Windows requires spawn-safe top-level modules

**What goes wrong:** `app/__main__.py` runs `uvicorn.run(..., workers=2)` on Windows; uvicorn forks (well, spawns) child processes. Each child re-imports `app.main` from scratch. If `app/main.py` has any module-level side effect that doesn't reproduce under spawn (e.g., reading a file that only exists in the parent process, or assuming an inherited file descriptor), the worker crashes on startup.

**Why it happens:** uvicorn uses `multiprocessing.spawn` (not fork) for cross-platform compat `[VERIFIED: uvicorn docs + web search]`. Spawn re-imports everything — top-level state must be reproducible.

**How to avoid:** Already satisfied — Phase 1–4 `app/main.py` only:
- Imports modules.
- Constructs `FastAPI()` (deterministic).
- Registers exception handlers (deterministic).
- Mounts `StaticFiles` only IF the `web/` dir exists (deterministic — both parent and child have the same dir tree).

Phase 5 additions are also spawn-safe:
- `_START_TIME = time.time()` — captured **per worker**, which is exactly what we want for /health uptime (each worker reports its own uptime).
- Startup janitor sweep — runs in **each worker's** startup, fine for an idempotent cleanup.

**Best practice for the plan:** Use FastAPI's `@app.on_event("startup")` or the modern `lifespan` context manager for the initial janitor sweep, NOT a module-level call to `sweep_expired_sessions()`. Module-level call would run at import time, which on workers=2 means twice — usually fine for an idempotent sweep, but lifespan is the documented idiom.

**Warning signs:** Workers crash on startup with `ImportError` or `OSError` — only on Windows; only with workers > 1.

### Pitfall 8: `shutil.disk_usage` on a Docker volume mount

**What goes wrong:** /health returns `data_dir_pct: 99.9` even when DATA_DIR has plenty of free space, because Docker volume mounts inherit the HOST filesystem's usage, not the volume's allocated quota.

**Why it happens:** `shutil.disk_usage` calls `statvfs` (Linux) on the path, which returns the filesystem's usage. A bind-mount to the host shows the host's filesystem; an anonymous volume shows the Docker storage driver's filesystem.

**How to avoid:** Document the value as "filesystem-level" not "session-level". For per-session usage, sum file sizes under DATA_DIR manually (more expensive but accurate). Phase 5 plan: use `shutil.disk_usage` (cheap, good enough for alerting) and document the semantic in the /health JSON schema.

**Warning signs:** /health pct is misleading on container hosts; mitigate by also exposing `data_dir_bytes` (actual used bytes) which is accurate via `statvfs`.

### Pitfall 9: Zeabur free-tier resource limits

**What goes wrong:** Zeabur free tier has unpublished but real CPU/memory caps. A 50MB PDF + 40MP render budget can OOM-kill the container on a 512MB free-tier instance.

**Why it happens:** Zeabur docs don't publish exact free-tier RAM `[VERIFIED via WebFetch: vendor docs vague on caps]`.

**How to avoid:**
- For target 1 (Zeabur short-term demo), set conservative env vars: `MAX_UPLOAD_BYTES=20*1024*1024` (20MB), `MAX_RENDER_PIXELS=20_000_000` (20MP), `UVICORN_WORKERS=1`. Document in Zeabur deploy section of README.
- Monitor /health `data_dir_bytes` and `data_dir_pct` — janitor's 1h TTL helps.
- Plan-writer's call: add a Zeabur-specific `.env.zeabur` example in repo.

**Warning signs:** Zeabur dashboard shows OOM kill; container restarts in a loop.

### Pitfall 10: Multi-stage build cache invalidation by `requirements.txt`

**What goes wrong:** Every `git push` rebuilds the entire Python dep layer, even when only app code changed. Cold builds take 5+ minutes.

**Why it happens:** `COPY app/ /app/app/` before `RUN pip install` invalidates the pip cache layer.

**How to avoid:** Standard pattern — `COPY requirements.txt .` FIRST, then `RUN pip install`, then `COPY app/` LATER. Already in the Dockerfile example above. Plan-writer: ensure this order is preserved.

**Warning signs:** Builds take > 1 min for app-only changes.

## Code Examples

### Verified pattern: HEALTHCHECK with stdlib urllib

```dockerfile
# Source: [VERIFIED via web search: muratcorlu.com/docker-healthcheck-without-curl-or-wget/
#          + github.com/BerriAI/litellm/pull/17646]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"
```

### Verified pattern: FastAPI root_path

```python
# Source: [CITED: fastapi.tiangolo.com/advanced/behind-a-proxy/]
import os
from fastapi import FastAPI

app = FastAPI(
    title="LogoSwap",
    root_path=os.environ.get("APP_BASE_PATH", ""),  # "" = root mount, "/pdf-logo" = prefix
)
```

### Verified pattern: asyncio.wait_for + to_thread

```python
# Source: [CITED: docs.python.org/3/library/asyncio-task.html]
import asyncio

try:
    result = await asyncio.wait_for(
        asyncio.to_thread(sync_cpu_bound_fn, *args),
        timeout=60.0,
    )
except asyncio.TimeoutError:
    # Thread keeps running in background — accept this for v1.
    raise HTTPException(504, detail={"code": "processing_timeout", ...})
```

### Verified pattern: atomic JSON write (cross-platform)

```python
# Source: [CITED: docs.python.org/3/library/os.html#os.replace
#          + docs.python.org/3/library/tempfile.html#tempfile.mkstemp]
import json, os, tempfile
from pathlib import Path

def atomic_write_json(path: Path, payload: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)  # atomic on Linux + Windows
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
```

### Verified pattern: shutil.rmtree with read-only file handler

```python
# Source: [CITED: docs.python.org/3/library/shutil.html#shutil.rmtree]
import os, stat, shutil

def _on_rm_error(func, path, exc_info):
    """Re-chmod a read-only file then retry (Windows compat for chmod 0o444 files)."""
    exc = exc_info[1] if exc_info else None
    if isinstance(exc, PermissionError):
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            func(path)
        except OSError:
            pass  # give up; logger.warning at caller

shutil.rmtree(path, onerror=_on_rm_error)  # onerror (3-arg) works through 3.14
```

### Verified pattern: programmatic uvicorn.run with workers

```python
# Source: [CITED: uvicorn.dev/deployment/]
# IMPORTANT: workers > 1 requires the import-string form ("module:app"), NOT a direct
# object reference. uvicorn must re-import the app in each worker (spawn semantics).
import uvicorn
uvicorn.run(
    "app.main:app",         # MUST be a string, not `app`
    host="0.0.0.0",
    port=8000,
    workers=2,
    # NOTE: `reload=True` is incompatible with workers > 1 — pick one.
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `python:3.12-slim` + `apt-get install curl` for HEALTHCHECK | `python -c "import urllib.request"` for HEALTHCHECK | Stdlib-only has been preferred since Docker 1.13 (2017); modern best practice | -12MB image size, zero attack surface for curl CVEs |
| Gunicorn + UvicornWorker | `uvicorn --workers N` (built-in spawn supervisor) | uvicorn 0.30 (2024) introduced first-class multi-process | One less dep, identical functionality for our scale |
| `webbrowser.open()` blocking until uvicorn ready | `threading.Timer(1.0, lambda: webbrowser.open(url))` | Pattern stable since Python 3.0 — applies to any "open after server up" desktop tool | Eliminates race |
| `shutil.rmtree(onerror=fn)` (3-arg) | `shutil.rmtree(onexc=fn)` (5-arg) | Python 3.12 introduced `onexc`; `onerror` deprecated but still works | Plan-writer can use either — `onerror` is more portable to 3.10/3.11 |
| `json.dump(p, open(path, 'w'))` | `tempfile.mkstemp` + `os.replace` | Atomic-write idiom stable since Python 3.3 (os.replace cross-platform atomic) | Eliminates half-write corruption |
| `Image.MAX_IMAGE_PIXELS = N` global | Per-call `if w*h > N: reject` (already in ingest.py) | Phase 4 chose explicit check over global mutation — Phase 5 keeps it | No new global state |

**Deprecated/outdated:**
- `shutil.rmtree(onerror=...)` — DEPRECATED in 3.12 but functional through 3.14. Plan can use either.
- `@app.on_event("startup")` — soft-deprecated in favor of `lifespan` async context manager (FastAPI ≥ 0.93). Plan should use `lifespan` for the startup janitor sweep.

## Assumptions Log

> All claims tagged `[ASSUMED]` (training knowledge, not verified in this session).

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Zeabur free tier RAM is in the 256MB–1GB range (exact unpublished) | Pitfall 9 | Conservative env vars in Zeabur deploy section — wrong sizing = OOM, mitigation already advised |
| A2 | A 50MB SHA-256 hex digest takes 150–250ms on a typical Ubuntu VM | Pattern 6 / D-C2 | If actually 500ms+, /process latency budget eats into 60s timeout — still well within budget |
| A3 | `python:3.12-slim-bookworm` ships PyMuPDF 1.27 + Pillow 12 + FastAPI 0.136 manylinux wheels | Pattern 1 (Dockerfile) | If a wheel is missing for 3.12, builder stage fails fast — caught at first build |
| A4 | uvicorn 0.30+ spawn-based supervisor works correctly across Linux + Windows + macOS | Pattern 3 / D-D2 | Cross-platform desktop entry. If broken on Windows, fall back to `workers=1` |
| A5 | Modern FastAPI 0.136 still honors `root_path` constructor arg identically to `--root-path` CLI | Pattern 2 | Documented in fastapi docs but tested versions were earlier — verify in Plan 05-01 smoke test |
| A6 | Pillow 12.2 `Image.MAX_IMAGE_PIXELS` default = 89_478_485 (matches our config) | Anti-Patterns | If Pillow default changed, our explicit check still wins — no risk |
| A7 | `tempfile.mkstemp(dir=...)` on Windows respects the dir arg and creates the tempfile on the SAME drive as the destination (so `os.replace` stays atomic on the same FS) | Pattern 5 | If Windows redirects tempfile to TEMP env var, os.replace crosses drives → non-atomic. Mitigation: explicit `dir=str(dest.parent)` already in example |
| A8 | The existing Phase 1–4 codebase has zero module-level I/O side effects that would break under spawn-based workers > 1 | Pitfall 7 | Verified by reading `app/main.py` + `app/config.py` + `app/storage.py` — all module-level code is constructors / regex compile / pathlib resolve. SAFE. (downgrades from ASSUMED to VERIFIED) |

## Open Questions (RESOLVED)

### Question 1: Legacy session migration strategy

**What we know:**
- Phase 1–4 wrote `meta.json` with `{page_count, filename}` only.
- Phase 5 D-C1 adds `original_sha256` field, REQUIRED at verify time.
- D-B2's TTL = 1h means all legacy sessions naturally expire within 1h of deploy.

**What's unclear:**
- Should `verify_original_hash` on a legacy session (missing `original_sha256`):
  - **Option A: Recompute on first /process** — read originals/, hash it, write back to meta.json, proceed. Pro: no user-visible disruption. Con: defeats the security guarantee (the "baseline" is now from after Phase 5 deploy, not from ingest time — if the file was tampered between Phase 1–4 ingest and Phase 5 deploy, we'd just hash the tampered version).
  - **Option B: Reject as `session_corrupted` → user re-uploads** — clean break; security guarantee remains accurate. Con: any user with a browser tab open across the deploy gets a 410.

**RESOLVED:** **Option B.** Combined with D-B2's 1h TTL, the disruption window is at most 1 hour. The friendly message "此工作階段為舊版,請重新上傳檔案。" covers the UX. Implementation is one line in `verify_original_hash` (already in the example code above).

### Question 2: PyInstaller vs source distribution for desktop target

**What we know:**
- D-A4 target 2 = "可下載 Python 套裝" for internal users.
- PyMuPDF wheel includes a large native MuPDF binary.
- Tkinter / qt / browser embed not needed — we open the system browser.

**What's unclear:**
- Is PyInstaller `--onefile` feasible for a FastAPI + PyMuPDF + Pillow app on Windows?

**RESOLVED:** Skip PyInstaller for v1. Ship as a git tag + README with cross-platform `pip install -r requirements.txt` + `python -m app`. Internal users with Python installed can clone + run; users without can install Python (15 min one-time). PyInstaller is a 1–2 day investigation that the deferred list explicitly tagged.

### Question 3: docker-compose.example.yml for Ubuntu — include or document only?

**What we know:**
- D-A1 explicitly rejects multi-container default.
- Ubuntu deploy needs nginx + app — nginx is external (D-A1).

**What's unclear:**
- Should the repo ship `docker-compose.example.yml` that wires nginx + app for Ubuntu? Or document the nginx config in README only?

**RESOLVED:** **Ship the example file.** It's < 50 lines, shows the canonical pattern (nginx proxy_pass to app:8000, volume mount for /data), and Ubuntu deployers will copy-paste it. Document `docker-compose -f docker-compose.example.yml up` in README. Plan task: Plan 05-01 ships the example + README section "Deploying to Ubuntu".

### Question 4: `CORS_ALLOW_ORIGINS` default — empty or wildcard for v1?

**What we know:**
- D-A2 lists three embed scenarios: (a) iframe sub-domain, (b) strip-prefix proxy (same origin), (c) `root_path` prefix (same origin).
- Only (a) involves cross-origin.
- For (a), the iframe is a sub-domain like `pdf-logo.intranet.company.com` embedded in `intranet.company.com`.

**What's unclear:**
- Default `CORS_ALLOW_ORIGINS=""` (no CORS middleware = no cross-origin) — does that break iframe embedding? Answer: NO, iframe embedding does not need CORS unless the parent page wants to read iframe contents or call its API directly. Same-origin browser fetch is fine inside the iframe.

**RESOLVED:** Default `CORS_ALLOW_ORIGINS=""`. Wire `fastapi.middleware.cors.CORSMiddleware` only if the env var is non-empty. Document in README "Embedding" section: "If the parent page calls the API directly (vs iframe-embed), set `CORS_ALLOW_ORIGINS=https://intranet.company.com`." Same recommendation as D-A2's Claude's discretion paragraph.

### Question 5: zeabur.json file — needed or auto-detect?

**What we know:**
- Zeabur auto-detects Dockerfile presence and deploys via Docker `[CITED: zeabur.com/docs/en-US/deploy/dockerfile]`.
- Zeabur supplies `$PORT` env var that the app must honor.
- `zeabur.json` allows custom start command / health check / env vars.

**What's unclear:**
- Does Phase 5 need a `zeabur.json`?

**RESOLVED:** **Optional.** Without `zeabur.json`, Zeabur uses the Dockerfile's `EXPOSE 8000` + `CMD` line. Our `CMD ["sh","-c","uvicorn ... --port ${PORT:-8000} ..."]` already honors Zeabur's `$PORT`. The HEALTHCHECK directive is respected. **Skip zeabur.json**; if Zeabur surfaces issues during target-1 testing, add it in a follow-up.

## Environment Availability

| Dependency | Required By | Available (dev box) | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All targets | ✓ | 3.14.4 (Docker uses 3.12-slim) | — |
| PyMuPDF | Core | ✓ | 1.27.2.3 | — (project-mandated) |
| FastAPI | Core | ✓ | 0.136.1 | — |
| uvicorn[standard] | Core | ✓ | 0.47.0 | — |
| Pillow | Core | ✓ | 12.2.0 | — |
| Docker / Docker Desktop | Target 1 (Zeabur) + Target 3 (Ubuntu) | (unknown — Windows dev box) | — | Local desktop entry (target 2) works without Docker |
| `curl` (testing only) | Smoke tests | (probably present) | — | `python -c "import urllib.request"` substitute |
| `git` | Source distribution | ✓ | (verified git is in use — see `gitStatus` system info) | — |
| GitHub account | AGPL §13 public repo | (user's) | — | None — required deliverable per memory lock |

**Missing dependencies with no fallback:** None — all v1 deliverables are achievable on the current dev environment + a Zeabur account (free tier).

**Missing dependencies with fallback:** Docker — only needed for testing target 1 + target 3 locally. Target 2 (desktop) is testable today on the dev box (`python -m app`).

## Security Domain

> `security_enforcement` not explicitly set in config → treat as enabled. (Phase 4 hotfix already closed 17 STRIDE threats; Phase 5 must not regress.)

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | NO (v1 内网免登入 per PROJECT.md) | — |
| V3 Session Management | YES (server-issued `secrets.token_urlsafe(16)`, no client trust) | Already in `app/storage.py` (Phase 1) |
| V4 Access Control | partial (path-traversal guard for session_id) | Already in `app/storage.py` `_SESSION_ID_RE` (Phase 1) |
| V5 Input Validation | YES — Phase 5 adds new env vars + JSON meta schema | Pydantic + `_env_int` (config.py); `tempfile + os.replace` for meta.json atomicity |
| V6 Cryptography | YES (SHA-256 for integrity baseline) | stdlib `hashlib.sha256` — never hand-rolled |
| V10 Malicious Code | YES (PyMuPDF parses untrusted PDFs) | Already mitigated: chmod 0o444 + AGPL seam isolation + ProcessPool sub-process isolation **deferred** (D-D1) |
| V14 Configuration | YES — new env vars, secret-free | All new env vars are NON-secret (TTL, workers, paths, base URL); no secrets in image |

### Known Threat Patterns for FastAPI + PyMuPDF + Docker

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Container runs as root | Elevation of Privilege | `USER app` directive in Dockerfile (UID 1000), already in Pattern 1 example |
| HEALTHCHECK exposes internal state | Information Disclosure | /health returns only aggregate counts (active_sessions, data_dir_bytes), no per-session data, no session_ids |
| Concurrent rmtree race | Tampering | mtime TTL (3600s) >> process timeout (60s) gives 60x safety margin; try/except handles concurrent delete |
| Half-written meta.json after crash | Tampering / DoS | tempfile + os.replace atomic write (Pattern 5) |
| AGPL violation via embed | Legal (not STRIDE but as critical) | LICENSE + public GitHub + UI footer link (Pattern 9) |
| Crafted PDF crashes worker | Denial of Service | sub-process isolation **deferred** (D-D1); mitigated by 60s timeout + workers=2 + MAX_RENDER_PIXELS=40MP ceilings |
| CORS bypass on cross-origin embed | Spoofing | Default `CORS_ALLOW_ORIGINS=""` (no middleware) → no cross-origin allowed; opt-in only |
| Path traversal via APP_BASE_PATH | Tampering | `root_path` is metadata (URL prefix hint), not a filesystem path; no traversal vector |
| Source link points to wrong / private fork | Legal | Plan task: AGPL_SOURCE_URL env var with safe default pointing at the canonical public repo |
| Pillow MAX_IMAGE_PIXELS global pollution from other libs | DoS | Already mitigated: explicit `if w*h > MAX_INGEST_IMAGE_PIXELS` in ingest.py (Phase 4) does not rely on global setting |

### Threats specifically introduced by Phase 5

1. **Janitor deletes active session (race) → user sees 404 mid-job.** Mitigated by mtime TTL >> timeout (60x). No mitigation needed beyond best-effort rmtree + log.
2. **`.corrupted` sentinel poisoned by attacker writing the file directly.** Attacker would need filesystem access — already game over. No new threat.
3. **HEALTHCHECK polling overload.** 30s interval → 2 polls/min; negligible. ✓
4. **`/health` reveals active session count to LAN scanners.** Internal-only network, no actionable info from count. Acceptable for v1.
5. **AGPL link points at wrong URL.** Plan-writer must hard-code the canonical public repo URL in HTML AND surface as env var for forks. ✓

## Sources

### Primary (HIGH confidence)

- `[VERIFIED: .venv/Scripts/pip.exe show ...]` — confirmed installed versions: PyMuPDF 1.27.2.3, FastAPI 0.136.1, uvicorn 0.47.0, Pillow 12.2.0, Python 3.14.4
- `[VERIFIED: .planning/STATE.md]` — Phase 1–4 invariants (AGPL seam, deferred-mutation, SHA-256 D-05, fit_dpi_to_pixel_budget)
- `[VERIFIED: .planning/research/STACK.md]` — locked stack (Python 3.12, PyMuPDF 1.27, FastAPI 0.115+, uvicorn 0.34+, Pillow 12, AGPL dual license)
- `[VERIFIED: app/main.py]` — existing FastAPI app structure, /health endpoint, exception handler patterns, StaticFiles mount
- `[VERIFIED: app/config.py]` — existing `_env_int` helper pattern + naming convention
- `[VERIFIED: app/storage.py]` — existing `_SESSION_ID_RE`, `subdir`, `write_session_meta`, write_original chmod 0o444
- `[VERIFIED: app/services/pipeline.py]` — existing `process_job` deferred-mutation flow + reset-from-pristine
- `[CITED: fastapi.tiangolo.com/advanced/behind-a-proxy/]` — FastAPI root_path semantics
- `[CITED: uvicorn.dev/deployment/]` — uvicorn --workers built-in supervisor + spawn semantics
- `[CITED: docs.python.org/3/library/asyncio-task.html]` — asyncio.wait_for + to_thread cancellation semantics
- `[CITED: docs.python.org/3/library/os.html#os.replace]` — cross-platform atomic rename
- `[CITED: docs.python.org/3/library/shutil.html#shutil.rmtree]` — rmtree onerror/onexc signatures
- `[CITED: zeabur.com/docs/en-US/deploy/dockerfile]` — Zeabur Dockerfile auto-detect + $PORT env var
- `[CITED: muratcorlu.com/docker-healthcheck-without-curl-or-wget/]` — HEALTHCHECK stdlib pattern

### Secondary (MEDIUM confidence)

- `[CITED: github.com/fastapi/fastapi/discussions/12151]` — StaticFiles + root_path interaction issue
- `[CITED: github.com/fastapi/fastapi/discussions/15430]` — pass-through vs strip-prefix proxy
- `[CITED: opensource.com/article/17/1/providing-corresponding-source-agplv3-license]` — AGPL §13 source disclosure
- `[CITED: sfconservancy.org/blog/2021/oct/21/trump-group-agplv3/]` — Mastodon AGPL precedent
- `[CITED: oneuptime.com/blog/post/2026-01-23-docker-health-checks-effectively/]` — HEALTHCHECK best practices 2026
- WebSearch results on `asyncio.to_thread` cancellation — multiple consistent sources

### Tertiary (LOW confidence — flag for plan-writer validation)

- Zeabur free-tier RAM caps (unpublished by vendor; deploy will reveal real limit)
- PyInstaller feasibility for PyMuPDF on Windows (deferred per Recommendation 2)
- Whether `StaticFiles(html=True)` mount issues actually bite at `APP_BASE_PATH=/pdf-logo` (Plan 05-01 smoke test will verify)

## Metadata

**Confidence breakdown:**
- Multi-stage Dockerfile: HIGH — standard pattern verified against Docker official docs + STACK.md
- FastAPI root_path: MEDIUM — works in principle but StaticFiles interaction has known issues (Pitfall 5); plan-writer should smoke-test
- uvicorn --workers: HIGH — verified cross-platform (spawn semantics)
- asyncio.wait_for + to_thread: HIGH on semantics, MEDIUM on "acceptable for v1" (plan must document the can't-kill-thread fact)
- SHA-256 baseline + verify: HIGH — stdlib, well-understood
- Janitor: HIGH on design, MEDIUM on cross-platform rmtree (Pitfall 3 requires onerror handler)
- AGPL §13: HIGH on what to do (3 artifacts), MEDIUM on what counts as "compliant enough" (legal nuance, but memory lock decides)
- Desktop entry: HIGH on the pattern, MEDIUM on PyInstaller path (deferred)
- /health enhanced: HIGH

**Research date:** 2026-05-23
**Valid until:** 2026-06-23 (30 days — deployment patterns are stable; Zeabur vendor specifics may shift faster, re-check before final deploy)

---

*Phase 5 research complete. Ready for plan generation.*
*Researcher: gsd-researcher*
