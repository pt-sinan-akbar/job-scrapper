ARG PLAYWRIGHT_VERSION=v1.59.0-noble

FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION} AS builder

ENV PYTHONUSERBASE=/opt/python

WORKDIR /build

COPY requirements.txt ./requirements.txt
COPY ui_server/requirements.txt ./ui-requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --user -r requirements.txt -r ui-requirements.txt


FROM oven/bun:1.4.4-slim AS bun-binary

FROM node:24-slim AS ui-build

COPY --from=bun-binary /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /ui
COPY ui/package.json ui/bun.lock ./
RUN bun install --frozen-lockfile
COPY ui/ ./
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

RUN mkdir -p /app/output /app/logs \
 && chown -R pwuser:pwuser /app

COPY --from=builder /opt/python /opt/python

WORKDIR /app

COPY --chown=pwuser:pwuser scraper    ./scraper
COPY --chown=pwuser:pwuser mcp_server ./mcp_server
COPY --chown=pwuser:pwuser ui_server  ./ui_server
COPY --chown=pwuser:pwuser --from=ui-build /ui/dist ./ui/dist

USER pwuser

EXPOSE 8080 8090

CMD ["python", "-m", "mcp_server.server"]
