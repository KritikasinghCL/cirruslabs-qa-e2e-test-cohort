# cirruslabs-qa-e2e-test-cohort

End-to-end QA test cohort for the Cirruslabs Inventory & Forecasting Cell (VEDANTA POC).

## Purpose

This repository holds the automated test suite that validates all seven monthly insight-pack deliverables:

| Deliverable | Description |
|---|---|
| D1 | 3-month gross inventory forecast by plant |
| D2 | Overstock / high-holdings analysis |
| D3 | Understock / critical spares at risk |
| D4 | Non-moving and slow-moving materials (NMI/SMI) |
| D5 | Prioritised purchase requisition suggestions |
| D6 | MRP eligibility per consumption trend |
| D7 | Duplicate material code detection |

## Test suite

213 tests · 8 skipped · 0 failures (as of 2026-10-22)

Run with:

```bash
python -m pytest tests/ -v
```
