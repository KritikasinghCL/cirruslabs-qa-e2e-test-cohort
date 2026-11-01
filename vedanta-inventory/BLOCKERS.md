# BLOCKERS.md — Vedanta Inventory Forecasting & Dashboard

> **Maintained by:** Data Enablement Squad  
> **Last updated:** 2026-09-25  
> **Rule:** Every blocker here maps to an env var. Supply the value → pipeline connects automatically. No code changes needed.  
> **Live status:** `GET /api/v1/connectivity` — returns per-source status and the full list of missing env vars.

---

## How to resolve a blocker

1. Copy `.env.example` → `.env` (if not already done)
2. Fill in the values for the blocker you are resolving
3. Restart the container: `docker-compose up --build` (or `docker-compose restart app`)
4. Confirm: `curl http://localhost:8080/api/v1/connectivity | jq .`

---

## Open Blockers

### BLOCKER-001 — GCS Bucket & Service Account Key

| Field | Value |
|-------|-------|
| **Impact** | Live data ingestion (Consumption History, Stock Master, PO History) |
| **Blocked metrics** | M01 DOH, M02 Inventory Value, M03 Turnover, M08 NMI, M09 SMI |
| **Workaround** | `USE_TEST_FIXTURES=true` runs against `fixtures/` CSVs |

**Resolution — set these env vars:**

```bash
GCS_BUCKET=<your-bucket-name>
GCS_CONSUMPTION_PATH=<path/within/bucket/consumption_history.csv>
GCS_STOCK_MASTER_PATH=<path/within/bucket/stock_master.csv>
GCS_PO_HISTORY_PATH=<path/within/bucket/po_history.csv>
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp_sa_key.json
GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH=/path/on/host/to/service_account_key.json
```

**Expected CSV schemas:**

| File | Required columns |
|------|-----------------|
| `consumption_history.csv` | `material_code`, `plant`, `date` (YYYY-MM-DD), `qty` |
| `stock_master.csv` | `material_code`, `plant`, `current_stock`, `unit_price`, `category`, `material_type` (ZSPR/ZSPN), `critical_flag`, `shutdown_flag`, `lead_time_days` |
| `po_history.csv` | `material_code`, `plant`, `po_number`, `pr_date`, `approval_date`, `arrival_date`, `qty_ordered`, `unit_price` |

---

### BLOCKER-001a — G-01: Daily Stock Snapshot (Critical Spares Availability)

| Field | Value |
|-------|-------|
| **Impact** | Critical Spares Availability % = (Days in Stock ÷ Total Days) × 100% |
| **Blocked metric** | M11 Critical Spares Availability % (Page 5) |
| **Workaround** | Page 5 shows all critical materials with DOH and stock value; availability % shows "Data not available" |

**Resolution:**

```bash
GCS_DAILY_STOCK_SNAPSHOT_PATH=<path/within/bucket/daily_stock_snapshot.csv>
```

**Expected CSV schema:** `material_code`, `plant`, `snapshot_date` (YYYY-MM-DD), `stock_qty`

Source: SAP MB52 (unrestricted stock by storage location), extracted daily and landed in GCS.

---

### BLOCKER-001b — G-02: RESB Demand-Met Extract (Fill Rate)

| Field | Value |
|-------|-------|
| **Impact** | Fill Rate = (Demand Met from Stock ÷ Total Demand) × 100% |
| **Blocked metric** | M10 Fill Rate % (Page 2 — Inventory Health) |
| **Workaround** | Shows "Data not available" in UI |

**Resolution:**

```bash
GCS_RESB_PATH=<path/within/bucket/resb_demand.csv>
```

**Expected CSV schema:** `material_code`, `plant`, `requirement_date` (YYYY-MM-DD), `demand_qty`, `met_qty`

Source: SAP RESB (reservation items) or MB25 (open reservations), with `met_qty` derived from goods-issue postings against each reservation.

---

### BLOCKER-002 — SAP RFC/BAPI Credentials

| Field | Value |
|-------|-------|
| **Impact** | Direct SAP extraction via RFC/BAPI connector (`backend/app/services/sap_connector.py`) |
| **Blocked metrics** | Same as BLOCKER-001 — SAP is the upstream source for all four data tables |
| **Workaround** | GCS loader is the primary path; SAP connector is the secondary/fallback stub |

**Resolution — set these env vars:**

```bash
SAP_HOST=<sap-application-server-hostname-or-ip>
SAP_SYSNR=<system-number-e.g-00>
SAP_CLIENT=<client-e.g-100>
SAP_USER=<rfc-service-user>
SAP_PASSWORD=<rfc-service-user-password>
```

**Infrastructure note:** `pyrfc` (SAP NW RFC SDK) must also be installed in the container.  
The current `requirements.txt` omits it intentionally to avoid build failures until credentials are available.  
When ready, add `pyrfc` to `requirements.txt` and rebuild the image.

**BAPI confirmation needed (G-08):** The SAP team must confirm the correct BAPI names and BWART movement-type codes for consumption extraction. The current stubs use placeholder names (`BAPI_MATERIAL_STOCK_REQ_LIST`, `BAPI_MATERIAL_GET_ALL`).

---

### BLOCKER-003 — ContextFlow MCP Endpoint & Auth

| Field | Value |
|-------|-------|
| **Impact** | Demand forecasting (3/6/12-month Material Requirement Forecast) |
| **Blocked metrics** | M04 Safety Stock, M05 ROP, M06 Overstock (forecast-enhanced), M07 Understock, M12 Demand Forecast 3/6/12mo, M13 Forecast Accuracy, M14 Forecast Bias |
| **Blocked pages** | Page 3 (Demand Forecast), Page 4 (Stock Actions flags), Page 7 (Forecast Quality) |
| **Workaround** | All blocked metrics display "Data not available". No errors thrown. |
| **Orchestration rule** | ContextFlow handles **only** demand forecasting. This team owns all other metrics and the dashboard. |

**Resolution — set these env vars:**

```bash
CONTEXTFLOW_MCP_ENDPOINT=https://<your-contextflow-mcp-endpoint>
CONTEXTFLOW_API_KEY=<your-contextflow-api-key>
```

**Wire format:** The client sends `POST /forecast` with:
```json
{
  "material_code": "...",
  "plant": "...",
  "horizon_months": [3, 6, 12],
  "consumption": [{"date": "YYYY-MM-DD", "qty": 0.0}, ...],
  "shutdown_calendar": [...]
}
```
And expects back:
```json
{
  "material_code": "...",
  "plant": "...",
  "avg_daily_usage": 0.0,
  "max_daily_usage": 0.0,
  "avg_lead_time_days": 0.0,
  "max_lead_time_days": 0.0,
  "forecasts": [
    {"horizon_months": 3, "forecast_qty": 0.0, "lower_bound": 0.0, "upper_bound": 0.0},
    {"horizon_months": 6, "forecast_qty": 0.0, "lower_bound": 0.0, "upper_bound": 0.0},
    {"horizon_months": 12, "forecast_qty": 0.0, "lower_bound": 0.0, "upper_bound": 0.0}
  ]
}
```

**Note on Forecast Accuracy / Bias (G-06):** These metrics auto-resolve after the first ContextFlow cycle closes and actuals are available. No additional configuration is needed beyond BLOCKER-003.

---

## Resolved Blockers

*(None yet — credentials not yet supplied)*

---

## Connectivity Check

Once credentials are set, verify with:

```bash
curl http://localhost:8080/api/v1/connectivity | jq .
```

Expected response when all sources are live:
```json
{
  "overall": "ok",
  "sources": {
    "gcs":         { "status": "ok", "detail": "Connected to gs://your-bucket." },
    "sap":         { "status": "ok", "detail": "SAP host reachable. RFC credentials set." },
    "contextflow": { "status": "ok", "detail": "ContextFlow MCP reachable (HTTP 200)." }
  },
  "missing_env_vars": [],
  "metrics_unblocked": ["M01 Days of Inventory", "M02 Inventory Value", ...],
  "metrics_blocked": []
}
```

---

## SOW KPI Targets (for reference)

| KPI | Target | Blocked by |
|-----|--------|-----------|
| Gross inventory reduction | ≥10% | BLOCKER-001 (live data) |
| NMI reduction | ≥10% | BLOCKER-001 |
| SMI reduction | ≥20% | BLOCKER-001 |
| Obsolete conversion reduction | ≥5% | BLOCKER-001 |
| Demand qty prediction | 100% | BLOCKER-003 |
| Inventory Forecast accuracy | >90% | BLOCKER-003 + G-06 (post-actuals) |
| Critical spares availability | >95% | BLOCKER-001a (G-01) |
| Fill Rate | — | BLOCKER-001b (G-02) |
| PR date suggestion | 100% | BLOCKER-003 (ROP needed) |
| NOM reduction | 1–7 days | BLOCKER-001 |
