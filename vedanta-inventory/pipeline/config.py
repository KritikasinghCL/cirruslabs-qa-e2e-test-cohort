"""
Pipeline configuration — all values from environment variables.
No defaults that could silently produce wrong numbers.
"""
from __future__ import annotations
import os
from typing import Optional


def _require(name: str) -> str:
    """Return env var value; raise clearly if absent."""
    v = os.environ.get(name)
    if not v:
        raise EnvironmentError(
            f"BLOCKER: required env var '{name}' is not set. "
            f"See .env.example for the full list."
        )
    return v


def _optional(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


# ---------------------------------------------------------------------------
# GCS
# ---------------------------------------------------------------------------
GCS_BUCKET: Optional[str] = _optional("GCS_BUCKET")
GCS_CONSUMPTION_PATH: Optional[str] = _optional("GCS_CONSUMPTION_PATH")
GCS_STOCK_MASTER_PATH: Optional[str] = _optional("GCS_STOCK_MASTER_PATH")
GCS_PO_HISTORY_PATH: Optional[str] = _optional("GCS_PO_HISTORY_PATH")
GCS_SHUTDOWN_CALENDAR_PATH: Optional[str] = _optional("GCS_SHUTDOWN_CALENDAR_PATH")
GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = _optional("GOOGLE_APPLICATION_CREDENTIALS")

# ---------------------------------------------------------------------------
# Serving layer (local Parquet output directory)
# ---------------------------------------------------------------------------
SERVING_DIR: str = _optional("SERVING_DIR", "/app/serving") or "/app/serving"

# ---------------------------------------------------------------------------
# SAP movement types for consumption (G-08)
# Standard list used until Vedanta SAP team confirms exact codes.
# Override via env var as a comma-separated string.
# ---------------------------------------------------------------------------
_bwart_env = _optional("SAP_CONSUMPTION_BWART_LIST", "201,261,262,551,601")
CONSUMPTION_BWART_LIST: list[str] = [b.strip() for b in (_bwart_env or "").split(",") if b.strip()]

# ---------------------------------------------------------------------------
# Null-threshold for gap detection (fraction, e.g. 0.10 = 10%)
# ---------------------------------------------------------------------------
NULL_THRESHOLD: float = float(_optional("NULL_THRESHOLD", "0.10") or "0.10")

# ---------------------------------------------------------------------------
# Material type scope (never changes — SOW is ZSPR and ZSPN only)
# ---------------------------------------------------------------------------
MATERIAL_TYPE_SCOPE: list[str] = ["ZSPR", "ZSPN"]

# ---------------------------------------------------------------------------
# Safety stock Z-score (configurable; default = 1.65 for 95% service level)
# ---------------------------------------------------------------------------
SAFETY_STOCK_Z: float = float(_optional("SAFETY_STOCK_Z", "1.65") or "1.65")

# ---------------------------------------------------------------------------
# Overstock threshold: stock > AVG_CONS × OVERSTOCK_DAYS
# ---------------------------------------------------------------------------
OVERSTOCK_DAYS: int = int(_optional("OVERSTOCK_DAYS", "180") or "180")

# ---------------------------------------------------------------------------
# Non-moving lookback (days)
# ---------------------------------------------------------------------------
NMI_LOOKBACK_DAYS: int = int(_optional("NMI_LOOKBACK_DAYS", "365") or "365")

# ---------------------------------------------------------------------------
# Slow-moving: DOI threshold (days)
# ---------------------------------------------------------------------------
SMI_DOI_THRESHOLD_DAYS: int = int(_optional("SMI_DOI_THRESHOLD_DAYS", "90") or "90")
