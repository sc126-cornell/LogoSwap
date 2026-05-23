# syntax=docker/dockerfile:1.7
#
# LogoSwap multi-stage Dockerfile (Phase 5, Plan 05-01).
#
# Stage 1 (builder) installs pinned Python deps into /install; Stage 2 (runtime) copies
# only the wheels + app code. This keeps build toolchain / pip cache out of the runtime
# layer (T-05-01) and lets a code-only change skip the pip layer (Pitfall 10).
#
# Runtime is python:3.12-slim-bookworm (glibc) + non-root user `app` UID 1000 (T-05-02).
# HEALTHCHECK uses stdlib urllib because slim has no curl/wget (Pitfall 2).
# CMD uses sh -c so `${PORT}` (Zeabur injects this) and the optional
# `${APP_BASE_PATH:+--root-path ...}` expand at container start.

FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

# Copy requirements.txt BEFORE app code so a source-only change does not bust the pip
# layer cache (Pitfall 10).
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --target /install -r requirements.txt

# -----------------------------------------------------------------------------------
# Runtime
# -----------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

# Non-root user (T-05-02 — never run the web process as root inside the container).
RUN groupadd -g 1000 app \
 && useradd -u 1000 -g 1000 -m -s /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /install /install

ENV PYTHONPATH=/install \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_BASE_PATH="" \
    UVICORN_WORKERS=2 \
    PROCESS_TIMEOUT_SECONDS=60 \
    SESSION_TTL_SECONDS=3600 \
    DATA_DIR=/data \
    LOGOS_DIR=/app/logos

# Copy app code. LICENSE + README must be inside the image so an operator pulling the
# image alone can locate the AGPL §13 disclosure artifacts.
COPY --chown=app:app app/ /app/app/
COPY --chown=app:app web/ /app/web/
COPY --chown=app:app logos/ /app/logos/
COPY --chown=app:app LICENSE README.md /app/

# Per-session transient state. /data is a VOLUME so the host can mount its own dir;
# chown to the non-root user so writes succeed when the volume is empty/new.
RUN mkdir -p /data && chown -R app:app /data
VOLUME ["/data"]

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"

# sh -c so $PORT (Zeabur injects this) and the conditional root-path flag expand at
# start. ${APP_BASE_PATH:+--root-path ${APP_BASE_PATH}} only emits the flag when
# APP_BASE_PATH is non-empty (root mount stays the default).
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-2} ${APP_BASE_PATH:+--root-path ${APP_BASE_PATH}}"]
