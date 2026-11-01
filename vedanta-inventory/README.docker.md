# Vedanta Inventory Forecasting & Dashboard — Docker Packaging Guide

> **Audience:** DevOps / platform engineers deploying the dashboard from a cold pull.  
> **Image:** `vedanta-inventory:latest` (multi-stage, Node 20 → Python 3.11-slim)  
> **Exposed port:** `8080`

---

## Quick start (fixtures / no live data)

```bash
git clone <repo-url>
cd vedanta-inventory

cp .env.example .env
# No edits needed — USE_TEST_FIXTURES defaults to true

docker-compose up --build
# Dashboard → http://localhost:8080
```

The first build downloads Node 20 Alpine + Python 3.11-slim layers and runs
`npm ci` + `pip install`. Subsequent builds are fast (layers cached).

---

## Cold-pull checklist

| Step | Command | Expected result |
|------|---------|-----------------|
| 1. Clone | `git clone <repo>` | Working tree present |
| 2. Copy env | `cp .env.example .env` | `.env` created |
| 3. Build | `docker-compose build` | Exit 0, image tagged `vedanta-inventory:latest` |
| 4. Start | `docker-compose up -d` | Container `vedanta-inventory-app` starts |
| 5. Health | `curl -sf http://localhost:8080/api/v1/health` | `{"status":"ok"}` |
| 6. Open | Browser → `http://localhost:8080` | Dashboard loads |

---

## Environment variables

All secrets and data paths are injected at runtime — **nothing is baked into the image**.

Copy `.env.example` → `.env` and fill in the values you have.

| Variable | Required for | Default | Notes |
|----------|-------------|---------|-------|
| `USE_TEST_FIXTURES` | Dev/demo | `true` | Set `false` for live GCS data |
| `FIXTURES_DIR` | Dev/demo | `/app/fixtures` | Path inside container |
| `GCS_BUCKET` | Live data | _(blank)_ | e.g. `gs://vedanta-sap-exports` |
| `GCS_CONSUMPTION_PATH` | Live data | _(blank)_ | Path within bucket |
| `GCS_STOCK_MASTER_PATH` | Live data | _(blank)_ | |
| `GCS_PO_HISTORY_PATH` | Live data | _(blank)_ | |
| `GCS_SHUTDOWN_CALENDAR_PATH` | Live data | _(blank)_ | |
| `GOOGLE_APPLICATION_CREDENTIALS` | Live GCS | _(blank)_ | Path inside container |
| `GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH` | Live GCS | _(blank)_ | Host path for volume mount |
| `SAP_HOST` | Live SAP RFC | _(blank)_ | |
| `SAP_SYSNR` | Live SAP RFC | _(blank)_ | |
| `SAP_CLIENT` | Live SAP RFC | _(blank)_ | |
| `SAP_USER` | Live SAP RFC | _(blank)_ | |
| `SAP_PASSWORD` | Live SAP RFC | _(blank)_ | |
| `CONTEXTFLOW_MCP_ENDPOINT` | Forecasting | _(blank)_ | Required for demand forecast |
| `CONTEXTFLOW_API_KEY` | Forecasting | _(blank)_ | |
| `CONTEXTFLOW_TIMEOUT_SECONDS` | Forecasting | `60` | |
| `SMI_USAGE_THRESHOLD_PERCENTILE` | Metrics | `20.0` | Slow-moving threshold |
| `NMI_LOOKBACK_MONTHS` | Metrics | `6` | Non-moving lookback |
| `OVERSTOCK_MARGIN_FACTOR` | Metrics | `1.25` | Overstock buffer multiplier |

---

## Live data (production)

```bash
# 1. Edit .env — fill in GCS_BUCKET, SAP_*, CONTEXTFLOW_* values
# 2. Mount your GCP service account key
export GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH=/path/to/sa-key.json
export GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-sa.json

# 3. Start with live data
USE_TEST_FIXTURES=false docker-compose up -d
```

---

## Local development (hot-reload)

`docker-compose.override.yml` is automatically picked up and enables:
- `uvicorn --reload` (backend hot-reload on source change)
- Bind-mount of `./backend` into the container
- `LOG_LEVEL=debug`

```bash
docker-compose up --build   # override is merged automatically
```

> **Note:** The override is for local dev only. In CI/CD, pass
> `--file docker-compose.yml` explicitly to exclude it.

---

## Production / CI

```bash
# Build with explicit compose file (excludes override)
docker-compose --file docker-compose.yml build

# Or build the image directly
docker build \
  --build-arg VITE_API_BASE=/api \
  -t vedanta-inventory:$(git rev-parse --short HEAD) \
  .

# Push to registry
docker tag vedanta-inventory:<sha> <registry>/vedanta-inventory:<sha>
docker push <registry>/vedanta-inventory:<sha>
```

---

## Healthcheck

The container exposes a health endpoint:

```
GET /api/v1/health  →  {"status": "ok", "mode": "fixtures"|"live", "version": "..."}
```

Docker polls it every 30 s (`--start-period=60s` to allow cold-start).

```bash
docker inspect --format='{{.State.Health.Status}}' vedanta-inventory-app
# → healthy
```

---

## Security notes

- Container runs as **non-root** (`appuser`, uid 1001) — no `--privileged` needed.
- No secrets in the image layers; all via env vars or volume-mounted files.
- `npm ci` (not `npm install`) ensures reproducible, lockfile-verified builds.
- `.dockerignore` excludes `node_modules`, `__pycache__`, `.env*`, test files,
  and credential JSON files from the build context.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `npm ci` fails | `package-lock.json` missing or out of sync | Run `npm install` locally, commit the lockfile |
| Health endpoint 503 | App still starting | Wait for `start_period` (60 s); check `docker logs vedanta-inventory-app` |
| `Data not available` on all metrics | `USE_TEST_FIXTURES=false` but GCS not configured | Set `USE_TEST_FIXTURES=true` or fill in GCS env vars |
| Forecast shows DNA | `CONTEXTFLOW_MCP_ENDPOINT` not set | Provide endpoint + API key in `.env` |
| Permission denied on `/app` | Non-root user can't write | All paths under `/app` are `chown`-ed to `appuser` at build time |
