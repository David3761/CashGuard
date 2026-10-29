FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Bucharest

WORKDIR /srv

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY data ./data
COPY keycloak/realm-cashguard.json ./keycloak/realm-cashguard.json

# Run as an unprivileged user (no shell, no home); the venv in /opt/venv stays root-owned and
# read-only for it, the app files are its own.
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /srv
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]
# One worker: the WebSocket manager and the rate limits live in memory (arch 5.2).
# --proxy-headers: trust X-Forwarded-For/-Proto only from FORWARDED_ALLOW_IPS (default 127.0.0.1;
# the hosted overlay sets it for Caddy). No `server` banner, 64 KiB WebSocket frames at most.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" --no-server-header --ws-max-size 65536"]
