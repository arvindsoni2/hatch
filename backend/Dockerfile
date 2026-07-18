# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS build-base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*


FROM build-base AS core-builder

COPY requirements-core.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements-core.txt


FROM core-builder AS browser-builder

COPY requirements-browser.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --no-cache-dir -r requirements-browser.txt


FROM core-builder AS local-ai-builder

COPY requirements-local-ai.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements-local-ai.txt


FROM core-builder AS observability-builder

COPY requirements-observability.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --no-cache-dir \
        -r requirements-observability.txt


FROM build-base AS full-builder

COPY requirements-core.txt requirements-browser.txt requirements-local-ai.txt requirements-observability.txt requirements-perception.txt requirements-full.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements-full.txt


FROM python:3.12-slim AS playwright-stage

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY --from=browser-builder /install /usr/local

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    fonts-unifont \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN playwright install chromium


FROM python:3.12-slim AS runtime-base

WORKDIR /app

ENV LANGGRAPH_STRICT_MSGPACK=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app /app/data


FROM runtime-base AS core

COPY --from=core-builder /install /usr/local
COPY --chown=appuser:appuser . .
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]


FROM runtime-base AS browser

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY --from=browser-builder /install /usr/local
COPY --from=playwright-stage /ms-playwright /ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    fonts-unifont \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=appuser:appuser . .
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]


FROM runtime-base AS local-ai

COPY --from=local-ai-builder /install /usr/local
COPY --chown=appuser:appuser . .
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]


FROM runtime-base AS observability

COPY --from=observability-builder /install /usr/local
COPY --chown=appuser:appuser . .
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]


FROM runtime-base AS full

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY --from=full-builder /install /usr/local
COPY --from=playwright-stage /ms-playwright /ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    fonts-unifont \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=appuser:appuser . .
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]


FROM core AS default
