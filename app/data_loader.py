"""Data access layer for the Vedanta Inventory Forecasting & Dashboard.

The loader hides the data source behind one contract-validated interface. The
source is chosen by the ``DATA_SOURCE_MODE`` environment variable:

    fixture  (default)  -- read labelled local test fixtures from data/fixtures/
    gcs                 -- read from Google Cloud Storage (stub; needs creds)
    sap                 -- read from live SAP extracts (stub; needs creds)

Design rules enforced here:

* Every public ``load_*`` function returns a ``pandas.DataFrame`` (empty on any
  failure) and NEVER raises. The dashboard renders "Data not available" from an
  empty frame; it must not crash because a source is missing or malformed.
* Fixture rows are validated against the JSON Schema contracts in
  data/contracts/. Rows that fail validation are dropped and counted, never
  silently kept — the dropped count is logged and available via
  :func:`last_load_report`.
* The ``_fixture_warning`` marker that labels test data is stripped before the
  frame is returned, so fixture warnings can never surface in the live product.
* ``gcs`` and ``sap`` modes raise ``NotImplementedError`` inside their private
  fetch stubs; the public API catches that, logs a warning, and returns empty —
  so the app stays up with "Data not available" until credentials are wired in.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

try:  # jsonschema is a hard dependency (see requirements.txt); degrade safely.
    from jsonschema import Draft7Validator

    _JSONSCHEMA_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in a broken install
    _JSONSCHEMA_AVAILABLE = False

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Paths and dataset registry
# --------------------------------------------------------------------------- #

# app/ -> project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONTRACTS_DIR = _PROJECT_ROOT / "data" / "contracts"
_FIXTURES_DIR = _PROJECT_ROOT / "data" / "fixtures"

# Marker key that labels a file as test data; stripped before returning.
FIXTURE_WARNING_KEY = "_fixture_warning"

# Logical dataset name -> contract/fixture file stem. One place to add a dataset.
_DATASETS: Dict[str, str] = {
    "consumption_history": "sap_consumption_history",
    "material_master": "sap_material_master",
    "po_history": "sap_po_history",
    "shutdown_calendar": "sap_shutdown_calendar",
}

_VALID_MODES = ("fixture", "gcs", "sap")


def _mode() -> str:
    """Return the configured data source mode, defaulting to 'fixture'."""
    raw = os.environ.get("DATA_SOURCE_MODE", "fixture").strip().lower()
    if raw not in _VALID_MODES:
        logger.warning(
            "DATA_SOURCE_MODE=%r is not one of %s; falling back to 'fixture'.",
            raw,
            _VALID_MODES,
        )
        return "fixture"
    return raw


# --------------------------------------------------------------------------- #
# Load report (observability without raising)
# --------------------------------------------------------------------------- #


@dataclass
class LoadReport:
    """What happened on the most recent load of one dataset."""

    dataset: str
    mode: str
    rows_read: int = 0
    rows_valid: int = 0
    rows_dropped: int = 0
    errors: List[str] = field(default_factory=list)
    available: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dataset": self.dataset,
            "mode": self.mode,
            "rows_read": self.rows_read,
            "rows_valid": self.rows_valid,
            "rows_dropped": self.rows_dropped,
            "errors": list(self.errors),
            "available": self.available,
        }


# Keyed by dataset name; overwritten on each load so callers can inspect it.
_LAST_REPORTS: Dict[str, LoadReport] = {}


def last_load_report(dataset: str) -> Optional[Dict[str, Any]]:
    """Return the report dict for the last load of ``dataset``, or None."""
    report = _LAST_REPORTS.get(dataset)
    return report.as_dict() if report else None


def all_load_reports() -> Dict[str, Dict[str, Any]]:
    """Return every recorded load report, keyed by dataset name."""
    return {name: rep.as_dict() for name, rep in _LAST_REPORTS.items()}


# --------------------------------------------------------------------------- #
# Contract loading / validation
# --------------------------------------------------------------------------- #


def _load_contract(dataset: str) -> Optional[Dict[str, Any]]:
    """Load the JSON Schema contract for a dataset. Returns None on failure."""
    stem = _DATASETS.get(dataset)
    if stem is None:
        logger.error("Unknown dataset %r; no contract to load.", dataset)
        return None
    path = _CONTRACTS_DIR / f"{stem}.json"
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.error("Contract file not found: %s", path)
    except json.JSONDecodeError as exc:
        logger.error("Contract %s is not valid JSON: %s", path, exc)
    except OSError as exc:  # pragma: no cover - unusual IO failure
        logger.error("Could not read contract %s: %s", path, exc)
    return None


def _validate_rows(
    rows: List[Dict[str, Any]],
    contract: Optional[Dict[str, Any]],
    report: LoadReport,
) -> List[Dict[str, Any]]:
    """Validate rows against the contract, dropping (and counting) failures.

    When jsonschema or the contract is unavailable, rows pass through unchanged
    and the condition is logged — degraded but never a crash.
    """
    if contract is None or not _JSONSCHEMA_AVAILABLE:
        if not _JSONSCHEMA_AVAILABLE:
            logger.warning(
                "jsonschema not installed; skipping contract validation for %s.",
                report.dataset,
            )
        report.rows_valid = len(rows)
        return rows

    validator = Draft7Validator(contract)
    valid: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        schema_errors = sorted(validator.iter_errors(row), key=lambda e: e.path)
        if schema_errors:
            report.rows_dropped += 1
            first = schema_errors[0]
            msg = (
                f"row {idx} failed contract: {first.message} "
                f"(at {'/'.join(str(p) for p in first.path) or '<root>'})"
            )
            report.errors.append(msg)
            logger.warning("%s: %s", report.dataset, msg)
        else:
            valid.append(row)
    report.rows_valid = len(valid)
    return valid


# --------------------------------------------------------------------------- #
# Source: fixtures
# --------------------------------------------------------------------------- #


def _read_fixture_rows(dataset: str) -> List[Dict[str, Any]]:
    """Read raw rows from a fixture file, stripping the warning marker.

    Raises on IO/parse errors so the caller can record them; callers never
    propagate the raise to the public API.
    """
    stem = _DATASETS[dataset]
    path = _FIXTURES_DIR / f"{stem}.json"
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if isinstance(payload, dict):
        if FIXTURE_WARNING_KEY in payload:
            logger.info(
                "Loading labelled test fixture for %s (%s).",
                dataset,
                payload[FIXTURE_WARNING_KEY],
            )
        rows = payload.get("rows", [])
    elif isinstance(payload, list):  # tolerate a bare array of rows
        rows = payload
    else:
        raise ValueError(
            f"fixture {path.name} must be an object with a 'rows' array "
            f"or a top-level array; got {type(payload).__name__}"
        )

    if not isinstance(rows, list):
        raise ValueError(f"fixture {path.name} 'rows' must be an array")

    # Defensive: never let the test-data marker leak into a row.
    return [
        {k: v for k, v in row.items() if k != FIXTURE_WARNING_KEY}
        for row in rows
        if isinstance(row, dict)
    ]


# --------------------------------------------------------------------------- #
# Source: GCS (stub)
# --------------------------------------------------------------------------- #


def _read_gcs_rows(dataset: str) -> List[Dict[str, Any]]:
    """Fetch rows from Google Cloud Storage.

    STUB — not implemented. Requires GCS credentials and bucket configuration
    (e.g. GCS_BUCKET, GOOGLE_APPLICATION_CREDENTIALS). Wire in the real client
    here, land the raw extract, then return parsed rows for contract validation.
    """
    # TODO(S-8 follow-up): implement with google-cloud-storage.
    #   1. Read bucket/prefix from env (GCS_BUCKET, GCS_PREFIX).
    #   2. Download the dataset blob for the configured extraction window.
    #   3. Parse (JSON/Parquet/CSV) into a list of dict rows.
    #   4. Return rows; validation happens in the public loader.
    raise NotImplementedError(
        "GCS data source is not implemented yet — set DATA_SOURCE_MODE=fixture "
        "or provide a GCS implementation and credentials."
    )


# --------------------------------------------------------------------------- #
# Source: SAP (stub)
# --------------------------------------------------------------------------- #


def _read_sap_rows(dataset: str) -> List[Dict[str, Any]]:
    """Fetch rows from live SAP extracts.

    STUB — not implemented. Requires SAP connection details and read-only
    credentials. This role READS from SAP and never writes to it. Scope is
    stores and spares material types (ZSPR, ZSPN); the extract must be
    reconciled to source (row counts, stock value, consumption totals) before
    any dataset is marked available.
    """
    # TODO(S-8 follow-up): implement SAP extraction (RFC/OData/table dump).
    #   1. Read connection config from env (SAP_HOST, SAP_CLIENT, SAP_USER...).
    #   2. Land the RAW extract first (append-only, reconcilable), then parse.
    #   3. Restrict to material types ZSPR, ZSPN.
    #   4. Return rows; validation happens in the public loader.
    raise NotImplementedError(
        "SAP data source is not implemented yet — set DATA_SOURCE_MODE=fixture "
        "or provide a SAP implementation and read-only credentials."
    )


_SOURCE_READERS: Dict[str, Callable[[str], List[Dict[str, Any]]]] = {
    "fixture": _read_fixture_rows,
    "gcs": _read_gcs_rows,
    "sap": _read_sap_rows,
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _empty_frame(dataset: str, mode: str, errors: List[str]) -> pd.DataFrame:
    report = LoadReport(
        dataset=dataset,
        mode=mode,
        rows_read=0,
        rows_valid=0,
        rows_dropped=0,
        errors=errors,
        available=False,
    )
    _LAST_REPORTS[dataset] = report
    return pd.DataFrame()


def load_dataset(dataset: str) -> pd.DataFrame:
    """Load one logical dataset as a validated DataFrame.

    Never raises. On any failure (unknown dataset, missing source, malformed
    data, unimplemented mode) it logs the cause, records a LoadReport, and
    returns an empty DataFrame so the dashboard can show "Data not available".
    """
    mode = _mode()

    if dataset not in _DATASETS:
        logger.error("Unknown dataset %r; known datasets: %s", dataset, list(_DATASETS))
        return _empty_frame(dataset, mode, [f"unknown dataset {dataset!r}"])

    reader = _SOURCE_READERS[mode]

    try:
        rows = reader(dataset)
    except NotImplementedError as exc:
        logger.warning("Dataset %s unavailable in %s mode: %s", dataset, mode, exc)
        return _empty_frame(dataset, mode, [str(exc)])
    except FileNotFoundError as exc:
        logger.warning("Dataset %s source file missing: %s", dataset, exc)
        return _empty_frame(dataset, mode, [f"source file missing: {exc}"])
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Dataset %s source is malformed: %s", dataset, exc)
        return _empty_frame(dataset, mode, [f"malformed source: {exc}"])
    except OSError as exc:  # pragma: no cover - unusual IO failure
        logger.error("Dataset %s could not be read: %s", dataset, exc)
        return _empty_frame(dataset, mode, [f"io error: {exc}"])

    report = LoadReport(dataset=dataset, mode=mode, rows_read=len(rows))

    contract = _load_contract(dataset)
    valid_rows = _validate_rows(rows, contract, report)

    report.available = len(valid_rows) > 0
    _LAST_REPORTS[dataset] = report

    if not valid_rows:
        logger.warning(
            "Dataset %s produced no valid rows (%d read, %d dropped).",
            dataset,
            report.rows_read,
            report.rows_dropped,
        )
        return pd.DataFrame()

    if report.rows_dropped:
        logger.info(
            "Dataset %s loaded: %d valid, %d dropped on contract validation.",
            dataset,
            report.rows_valid,
            report.rows_dropped,
        )

    return pd.DataFrame(valid_rows)


# Convenience wrappers — one per logical dataset. Each returns a DataFrame
# (empty when unavailable) and never raises.


def load_consumption_history() -> pd.DataFrame:
    """SAP consumption/movement history (MSEG/MB51)."""
    return load_dataset("consumption_history")


def load_material_master() -> pd.DataFrame:
    """SAP material master (MARA/MARC)."""
    return load_dataset("material_master")


def load_po_history() -> pd.DataFrame:
    """SAP purchase order history (EKKO/EKPO/EKBE)."""
    return load_dataset("po_history")


def load_shutdown_calendar() -> pd.DataFrame:
    """SAP plant-maintenance shutdown calendar."""
    return load_dataset("shutdown_calendar")


def available_datasets() -> List[str]:
    """Return the logical dataset names this loader can serve."""
    return list(_DATASETS)
