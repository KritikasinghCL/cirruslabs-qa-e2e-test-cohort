# Vedanta Inventory Forecasting & Dashboard — Data Contract v1.0.0

**Ticket:** S-1 | **Owner:** Mia (Data Enablement Squad) | **Date:** 2026-09-25

---

## What is in this folder

| File | Purpose |
|------|---------|
| `data_contract_v1.yaml` | Versioned contract: every SAP source table/field, GCS paths, all 14 metric formulas, dashboard page inventory, filter dimensions, config parameters |
| `gap_register_v1.json` | 10 gaps with severity, owner, and fallback behaviour |

---

## How downstream tasks use this

| Ticket | Uses |
|--------|------|
| S-2 (Devika Rao) | `sources` section — table names, field lists, GCS paths, movement type list |
| S-3 (Arun Menon) | `metrics.DEMAND_FORECAST` (ContextFlow inputs/outputs), `FORECAST_ACCURACY`, `FORECAST_BIAS` |
| S-4 (Kabir Shah) | `dashboard_pages`, `filters`, all metric `formula` and `unit` fields |
| S-5 (Sofia)      | No direct dependency; contract is mounted as `/app/contracts/` in Docker image |
| S-6 (Maya)       | Gap register — spot-check list; all metric formulas for verification |

---

## Amendment process

1. Open a PR against `vedanta-dashboard/contracts/`
2. Bump `contract_version` (semver)
3. Update `last_updated`
4. Record the change on ticket S-1 via `board_record`

---

## Critical blockers (resolve before S-2 can close)

- **G-07** — Real GCS bucket path (currently placeholder `gs://bucket/path`)
- **G-08** — Confirmed BWART consumption movement type list from Vedanta SAP team
