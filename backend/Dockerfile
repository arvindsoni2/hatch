# ──────────────────────── Stage 1: Builder ────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a local site-packages prefix
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ──────────────────────── Stage 2: Playwright Browser Install ────────────────────────
FROM python:3.12-slim AS playwright-stage

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Install Playwright system dependencies and Chromium browser
# Note: fonts-unifont replaces the deprecated ttf-unifont; ttf-ubuntu-font-family
# does not exist in Debian bookworm — use fonts-ubuntu instead.
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

# Install Playwright Chromium browser only (deps already installed above)
RUN playwright install chromium


# ──────────────────────── Stage 3: Runner ────────────────────────
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy installed Python packages
COPY --from=builder /install /usr/local

# Copy Playwright browser binaries and system libs
COPY --from=playwright-stage /root/.cache/ms-playwright /root/.cache/ms-playwright
COPY --from=playwright-stage /usr/lib /usr/lib
COPY --from=playwright-stage /lib /lib

# Install runtime system dependencies (including Node.js for docx generation)
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

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Create data directory and set ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Entrypoint: run migrations then start the server
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
