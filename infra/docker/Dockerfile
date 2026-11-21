ARG PLAYWRIGHT_VERSION=v1.59.0-noble

FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION} AS builder

ENV PYTHONUSERBASE=/opt/python

WORKDIR /build

COPY requirements.txt ./requirements.txt
COPY backend/requirements.txt ./backend-requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --user -r requirements.txt -r backend-requirements.txt


FROM oven/bun:1.4.4-slim AS bun-binary

FROM node:24-slim AS frontend-build

COPY --from=bun-binary /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build


FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION} AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/python/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONUSERBASE=/opt/python \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8080 \
    UI_HOST=0.0.0.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends jq \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /app/logs \
 && chown -R pwuser:pwuser /app

COPY --from=builder /opt/python /opt/python

WORKDIR /app

COPY --chown=pwuser:pwuser scraper    ./scraper
COPY --chown=pwuser:pwuser mcp_server ./mcp_server
COPY --chown=pwuser:pwuser backend    ./backend
COPY --chown=pwuser:pwuser --from=frontend-build /frontend/dist ./frontend/dist
COPY --chown=pwuser:pwuser infra/scripts/scrape-to-discord.sh ./scripts/scrape-to-discord.sh

USER pwuser

EXPOSE 8080 8090

CMD ["python", "-m", "mcp_server.server"]
