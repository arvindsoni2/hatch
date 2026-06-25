# ──────────────────────── Stage 1: Builder ────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Build-time system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Use CPU-only PyTorch index so sentence-transformers doesn't pull the 2 GB GPU wheel
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

# Perception stack — separate layer so it's cached independently of base requirements
# faster-whisper pulls CTranslate2 (C++ binary wheel, ~50 MB); no PyTorch needed here
COPY requirements-perception.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements-perception.txt


# ──────────────────────── Stage 2: Playwright browser install ─────────────────
FROM python:3.12-slim AS playwright-stage

# All Playwright browser binaries go to /ms-playwright (world-readable).
# This avoids the /root vs /home/appuser lookup mismatch when the app runs as
# a non-root user.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY --from=builder /install /usr/local

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

# Install Chromium into /ms-playwright
RUN playwright install chromium


# ──────────────────────── Stage 3: Runner ────────────────────────
FROM python:3.12-slim AS runner

WORKDIR /app

# Tell every process in the container where to find browser binaries
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    LANGGRAPH_STRICT_MSGPACK=true

# Python packages
COPY --from=builder /install /usr/local

# Playwright browser binaries (world-readable path — accessible by appuser)
COPY --from=playwright-stage /ms-playwright /ms-playwright

# System libs needed by Chromium + Playwright scrapers
COPY --from=playwright-stage /usr/lib /usr/lib
COPY --from=playwright-stage /lib /lib

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    npm \
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
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --create-home --shell /bin/bash appuser

RUN mkdir -p /app/data && chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
