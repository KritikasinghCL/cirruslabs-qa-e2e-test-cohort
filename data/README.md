# Data interface — contracts and fixtures

This directory defines the **data contract** the whole application is built
against, and ships labelled **test fixtures** so the app runs end-to-end with
no live SAP or GCS access.

## `contracts/` — JSON Schema data contracts

One JSON Schema (Draft-07) per source dataset. These are the agreed shape of
each extract; `app/data_loader.py` validates every incoming row against them
and drops (and counts) rows that do not conform.

| Contract | SAP source | Grain |
|---|---|---|
| `sap_consumption_history.json` | MSEG / MB51 | one material-document line item |
| `sap_material_master.json` | MARA / MARC (+ MAKT, MBEW) | one material/plant |
| `sap_po_history.json` | EKKO / EKPO (+ EKBE, EKET) | one PO line item |
| `sap_shutdown_calendar.json` | PM (orders, equipment) | one shutdown event |

## `fixtures/` — labelled test data

One fixture file per contract, each with **15 Vedanta-plausible rows** and a
top-level `_fixture_warning: "TEST DATA — NOT FOR PRODUCTION"` marker.

- Plant codes: `VED-ZAM-001`, `VED-ZAM-002`, `VED-RSA-001`.
- Material types: `SPARE`, `CONSUMABLE`, `RAW_MAT`.
- Material numbers are shared across files so joins (master ⇄ consumption ⇄ PO)
  resolve.

**Fixtures are test data.** The loader strips the `_fixture_warning` marker and
labels every load, so fixture data is never surfaced as production figures in
the live dashboard. Selected with `DATA_SOURCE_MODE=fixture` (the default).

## How the loader chooses a source

`DATA_SOURCE_MODE` (env) selects `fixture` (default), `gcs`, or `sap`. The
`gcs` and `sap` sources are stubs that raise `NotImplementedError` until
credentials are wired in; the public loader catches that and returns an empty
frame so the dashboard shows **"Data not available"** rather than crashing.
