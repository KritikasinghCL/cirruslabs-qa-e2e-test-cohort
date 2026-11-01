# ─────────────────────────────────────────────────────────────────────────────
# Vedanta Inventory Forecasting & Dashboard
# Multi-stage build: Node 20 (React/Vite) → Python 3.11-slim (FastAPI/uvicorn)
#
# All secrets injected at runtime via environment variables — none baked in.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend

# Copy lockfile + manifest first for layer-cache efficiency
COPY frontend/package.json frontend/package-lock.json ./
# npm ci requires a lockfile and is reproducible; never npm install in CI/Docker
RUN npm ci --prefer-offline

COPY frontend/ ./

# VITE_API_BASE is baked into the JS bundle at build time; override with ARG
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# ── Stage 2: Python backend + static serving ─────────────────────────────────
FROM python:3.11-slim AS backend

WORKDIR /app

# System deps — only curl (healthcheck); clean apt lists immediately
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps — install before copying source for layer-cache efficiency
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY backend/ ./

# Frontend static build
COPY --from=frontend-build /app/frontend/dist ./static

# Fixtures (test/dev only — never loaded when USE_TEST_FIXTURES=false)
COPY fixtures/ ./fixtures/

# ── Non-root user (security hardening) ───────────────────────────────────────
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/sh --no-create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

# ── Runtime config (all secrets via env vars — see .env.example) ─────────────
# GCS_BUCKET, GCS_CONSUMPTION_PATH, GCS_STOCK_MASTER_PATH,
# GCS_PO_HISTORY_PATH, GCS_SHUTDOWN_CALENDAR_PATH,
# GOOGLE_APPLICATION_CREDENTIALS,
# SAP_HOST, SAP_SYSNR, SAP_CLIENT, SAP_USER, SAP_PASSWORD,
# CONTEXTFLOW_MCP_ENDPOINT, CONTEXTFLOW_API_KEY,
# USE_TEST_FIXTURES (default "true" for fixture-based dev)

EXPOSE 8080

# start-period=60s gives the app time to load fixtures/GCS on cold pull
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD curl -sf http://localhost:8080/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
