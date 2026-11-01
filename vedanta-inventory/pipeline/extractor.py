"""
GCS Extractor — S-2 (Devika Rao)

Reads raw Parquet (preferred) or CSV files from GCS for each of the four
SAP source domains defined in data_contract_v1.yaml.

Design rules:
- Lands raw files to SERVING_DIR/raw/<domain>/ before any transformation.
- Raises DataSourceUnavailableError with a clear message when credentials
  or paths are absent — never silently returns empty data.
- Logs row counts and file sizes for every load (reconciliation anchor).
- Does NOT transform or filter — that is transformer.py's job.
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from pipeline import config

logger = logging.getLogger(__name__)

RAW_DIR = Path(config.SERVING_DIR) / "raw"


class DataSourceUnavailableError(RuntimeError):
    """Raised when a required GCS env var is missing or GCS is unreachable."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gcs_client():
    """Return an authenticated GCS storage.Client."""
    if not config.GCS_BUCKET:
        raise DataSourceUnavailableError(
            "BLOCKER G-07: GCS_BUCKET env var is not set. "
            "Replace the placeholder gs://bucket/path with the real bucket name "
            "and set GOOGLE_APPLICATION_CREDENTIALS to the service account key path."
        )
    try:
        from google.cloud import storage  # type: ignore
    except ImportError as exc:
        raise DataSourceUnavailableError(
            "google-cloud-storage is not installed. Run: pip install google-cloud-storage"
        ) from exc
    return storage.Client()


def _list_blobs(client, prefix: str) -> list:
    """List all blobs under a GCS prefix."""
    bucket = client.bucket(config.GCS_BUCKET)
    return list(bucket.list_blobs(prefix=prefix))


def _read_blob(client, blob_name: str, label: str) -> pd.DataFrame:
    """Download one blob and parse as Parquet (preferred) or CSV."""
    bucket = client.bucket(config.GCS_BUCKET)
    blob = bucket.blob(blob_name)
    raw_bytes = blob.download_as_bytes()
    size_kb = len(raw_bytes) / 1024

    if blob_name.endswith(".parquet"):
        df = pd.read_parquet(io.BytesIO(raw_bytes))
    elif blob_name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw_bytes))
    else:
        # Try Parquet first, fall back to CSV
        try:
            df = pd.read_parquet(io.BytesIO(raw_bytes))
        except Exception:
            df = pd.read_csv(io.BytesIO(raw_bytes))

    logger.info(
        "Loaded %s: blob=%s rows=%d size=%.1fKB",
        label, blob_name, len(df), size_kb,
    )
    return df


def _load_domain(path_env_value: Optional[str], label: str) -> pd.DataFrame:
    """
    Load all blobs under a GCS path prefix and concatenate into one DataFrame.
    Raises DataSourceUnavailableError if path is not configured or no blobs found.
    """
    if not path_env_value:
        raise DataSourceUnavailableError(
            f"BLOCKER G-07: GCS path for '{label}' is not configured. "
            f"Set the corresponding GCS_*_PATH env var."
        )

    client = _gcs_client()
    # Strip leading gs://bucket/ if the user set the full URI
    prefix = path_env_value
    if prefix.startswith("gs://"):
        # gs://bucket/path/to/dir  →  path/to/dir
        parts = prefix[5:].split("/", 1)
        prefix = parts[1] if len(parts) > 1 else ""

    blobs = _list_blobs(client, prefix)
    data_blobs = [b for b in blobs if not b.name.endswith("/")]

    if not data_blobs:
        raise DataSourceUnavailableError(
            f"BLOCKER G-07: No files found at gs://{config.GCS_BUCKET}/{prefix} "
            f"for domain '{label}'. Verify the GCS export has run."
        )

    frames = [_read_blob(client, b.name, label) for b in data_blobs]
    df = pd.concat(frames, ignore_index=True)
    logger.info("Domain '%s': total rows=%d from %d file(s)", label, len(df), len(data_blobs))
    return df


def _save_raw(df: pd.DataFrame, domain: str) -> Path:
    """Persist raw DataFrame to SERVING_DIR/raw/<domain>/raw.parquet."""
    out_dir = RAW_DIR / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "raw.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Raw extract saved: %s (%d rows)", out_path, len(df))
    return out_path


# ---------------------------------------------------------------------------
# Public extraction functions
# ---------------------------------------------------------------------------

def extract_consumption_history() -> pd.DataFrame:
    """
    Extract MSEG consumption history from GCS.
    SAP fields: MBLNR, ZEILE, BUDAT, MATNR, WERKS, LGORT, BWART, MENGE,
                MEINS, DMBTR, WAERS, KOSTL, AUFNR, BWTAR
    """
    df = _load_domain(config.GCS_CONSUMPTION_PATH, "consumption_history")
    _save_raw(df, "consumption_history")
    return df


def extract_stock_master() -> pd.DataFrame:
    """
    Extract MARA/MARC/MARD/MBEW stock and material master from GCS.
    SAP fields: MATNR, MAKTX, MTART, MATKL, MEINS, WERKS, EKGRP, DISMM,
                MINBE, EISBE, MABST, WEBAZ, PLIFZ, CRITICAL_FLAG,
                LGORT, LABST, EINME, INSME, RETME,
                BWKEY, STPRS, VERPR, LAEPR, BKLAS
    """
    df = _load_domain(config.GCS_STOCK_MASTER_PATH, "stock_master")
    _save_raw(df, "stock_master")
    return df


def extract_po_history() -> pd.DataFrame:
    """
    Extract EKKO/EKPO/EKET/EKBE PO history from GCS.
    SAP fields: EBELN, BSART, LIFNR, BEDAT, WAERS,
                EBELP, MATNR, WERKS, MENGE, MEINS, NETPR, EINDT, ELIKZ, REPOS,
                EINDT_SCH, MENGE_SCH,
                VGABE, BUDAT_GR, MENGE_GR, DMBTR_GR
    """
    df = _load_domain(config.GCS_PO_HISTORY_PATH, "po_history")
    _save_raw(df, "po_history")
    return df


def extract_maintenance_calendar() -> pd.DataFrame:
    """
    Extract IFLOT/ILOA/VIQMEL/VIAUFKST maintenance calendar from GCS.
    SAP fields: AUFNR, AUART, EQUNR, TPLNR, WERKS, GSTRP, GLTRP,
                ISTAT, SHUTDOWN_FLAG, RESB_MATNR, RESB_BDMNG
    """
    df = _load_domain(config.GCS_SHUTDOWN_CALENDAR_PATH, "maintenance_calendar")
    _save_raw(df, "maintenance_calendar")
    return df
