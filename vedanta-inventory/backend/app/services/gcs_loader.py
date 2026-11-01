"""
GCS Data Loader — reads CSV files from Google Cloud Storage.
Bucket and paths are read exclusively from environment variables.
Credentials via GOOGLE_APPLICATION_CREDENTIALS env var (path to service account JSON).

BLOCKER: GCS_BUCKET, GCS_*_PATH, and GOOGLE_APPLICATION_CREDENTIALS not yet provided.
         This stub will raise DataSourceUnavailableError until they are supplied.
"""
from __future__ import annotations
import io
import logging
from typing import Optional

import pandas as pd

from app.core.config import settings
from app.models.schemas import (
    ConsumptionHistory, ConsumptionRecord,
    StockMaster, StockMasterRecord,
    POHistory, PORecord,
    ShutdownCalendar, ShutdownRecord,
)

logger = logging.getLogger(__name__)


class DataSourceUnavailableError(RuntimeError):
    """Raised when a required data source env var is missing or GCS is unreachable."""


def _gcs_client():
    """Return an authenticated GCS client. Raises if credentials are missing."""
    try:
        from google.cloud import storage  # type: ignore
    except ImportError as exc:
        raise DataSourceUnavailableError("google-cloud-storage not installed") from exc

    if not settings.GCS_BUCKET:
        raise DataSourceUnavailableError(
            "BLOCKER: GCS_BUCKET env var not set. "
            "Provide bucket name and service account credentials to connect."
        )
    return storage.Client()


def _read_gcs_csv(path_env_value: Optional[str], label: str) -> pd.DataFrame:
    """Download a CSV from GCS and return as DataFrame."""
    if not path_env_value:
        raise DataSourceUnavailableError(
            f"BLOCKER: GCS path for '{label}' is not configured. "
            f"Set the corresponding GCS_*_PATH env var."
        )
    client = _gcs_client()
    bucket = client.bucket(settings.GCS_BUCKET)
    blob = bucket.blob(path_env_value)
    content = blob.download_as_bytes()
    logger.info("Loaded %s from gs://%s/%s", label, settings.GCS_BUCKET, path_env_value)
    return pd.read_csv(io.BytesIO(content))


# ---------------------------------------------------------------------------
# Public loader functions
# ---------------------------------------------------------------------------

def load_consumption_history() -> ConsumptionHistory:
    df = _read_gcs_csv(settings.GCS_CONSUMPTION_PATH, "consumption_history")
    # Filter to ZSPR/ZSPN scope — join with stock master required upstream;
    # here we load as-is and let the metrics engine filter.
    records = [
        ConsumptionRecord(
            material_code=str(row["material_code"]),
            plant=str(row["plant"]),
            posting_date=row["date"],
            qty=float(row["qty"]),
        )
        for _, row in df.iterrows()
    ]
    return ConsumptionHistory(records=records)


def load_stock_master() -> StockMaster:
    df = _read_gcs_csv(settings.GCS_STOCK_MASTER_PATH, "stock_master")
    # Enforce material type scope
    df = df[df["material_type"].isin(["ZSPR", "ZSPN"])]
    records = [
        StockMasterRecord(
            material_code=str(row["material_code"]),
            plant=str(row["plant"]),
            current_stock=float(row["current_stock"]),
            unit_price=float(row["unit_price"]),
            category=str(row["category"]),
            material_type=row["material_type"],
            critical_flag=bool(row["critical_flag"]),
            shutdown_flag=bool(row["shutdown_flag"]),
            description=row.get("description"),
            uom=row.get("uom", "EA"),
            lead_time_days=float(row["lead_time_days"]) if pd.notna(row.get("lead_time_days")) else None,
        )
        for _, row in df.iterrows()
    ]
    return StockMaster(records=records)


def load_po_history() -> POHistory:
    df = _read_gcs_csv(settings.GCS_PO_HISTORY_PATH, "po_history")
    records = [
        PORecord(
            material_code=str(row["material_code"]),
            plant=str(row["plant"]),
            po_number=str(row["po_number"]) if pd.notna(row.get("po_number")) else None,
            pr_date=row["pr_date"],
            approval_date=row["approval_date"] if pd.notna(row.get("approval_date")) else None,
            arrival_date=row["arrival_date"] if pd.notna(row.get("arrival_date")) else None,
            qty_ordered=float(row["qty_ordered"]),
            unit_price=float(row["unit_price"]),
        )
        for _, row in df.iterrows()
    ]
    return POHistory(records=records)


def load_daily_stock_snapshot() -> pd.DataFrame:
    """
    Load the daily stock snapshot CSV (G-01) used for Critical Spares Availability.
    Expected columns: material_code, plant, snapshot_date, stock_qty
    Returns an empty DataFrame with the correct columns if the path is not configured.
    """
    if not settings.GCS_DAILY_STOCK_SNAPSHOT_PATH:
        logger.warning(
            "GCS_DAILY_STOCK_SNAPSHOT_PATH not set — Critical Spares Availability will show DNA. "
            "Set this env var to the GCS path of the daily MB52 stock snapshot export."
        )
        return pd.DataFrame(columns=["material_code", "plant", "snapshot_date", "stock_qty"])
    df = _read_gcs_csv(settings.GCS_DAILY_STOCK_SNAPSHOT_PATH, "daily_stock_snapshot")
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


def load_resb_demand() -> pd.DataFrame:
    """
    Load the RESB demand-met extract (G-02) used for Fill Rate.
    Expected columns: material_code, plant, requirement_date, demand_qty, met_qty
    Returns an empty DataFrame with the correct columns if the path is not configured.
    """
    if not settings.GCS_RESB_PATH:
        logger.warning(
            "GCS_RESB_PATH not set — Fill Rate will show DNA. "
            "Set this env var to the GCS path of the RESB/reservation demand extract."
        )
        return pd.DataFrame(columns=["material_code", "plant", "requirement_date", "demand_qty", "met_qty"])
    df = _read_gcs_csv(settings.GCS_RESB_PATH, "resb_demand")
    df["requirement_date"] = pd.to_datetime(df["requirement_date"])
    return df


def load_shutdown_calendar() -> ShutdownCalendar:
    df = _read_gcs_csv(settings.GCS_SHUTDOWN_CALENDAR_PATH, "shutdown_calendar")
    records = []
    for _, row in df.iterrows():
        mats = row["materials"]
        if isinstance(mats, str):
            mats = [m.strip() for m in mats.split("|")]
        else:
            mats = []
        records.append(ShutdownRecord(
            shutdown_id=str(row["shutdown_id"]),
            plant=str(row["plant"]),
            shutdown_date=row["shutdown_date"],
            end_date=row["end_date"] if pd.notna(row.get("end_date")) else None,
            materials=mats,
            seasonal_flag=bool(row.get("seasonal_flag", False)),
            shutdown_type=row.get("shutdown_type"),
        ))
    return ShutdownCalendar(records=records)
