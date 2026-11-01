"""
Gap Updater — S-2 (Devika Rao)

After transformation, checks each field in the clean serving tables against
the null-threshold defined in config.NULL_THRESHOLD.

For every gap in gap_register_v1.json:
  - If the required field is present and null-rate <= threshold → CONFIRMED
  - If the required field is absent or null-rate > threshold → FAILED (with count)

Writes an updated gap register to SERVING_DIR/gap_register_updated.json.

The sentinel value "Data not available" is propagated to the metrics layer
by returning a dict of {gap_id: bool} — True means the metric is blocked.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline import config

logger = logging.getLogger(__name__)

CONTRACTS_DIR = Path(__file__).parent.parent.parent / "vedanta-dashboard" / "contracts"
GAP_REGISTER_SOURCE = CONTRACTS_DIR / "gap_register_v1.json"
SERVING_DIR = Path(config.SERVING_DIR)
UPDATED_GAP_REGISTER = SERVING_DIR / "gap_register_updated.json"


def _null_rate(df: pd.DataFrame, col: str) -> float:
    """Return fraction of null values in a column. Returns 1.0 if column absent."""
    if col not in df.columns:
        return 1.0
    total = len(df)
    if total == 0:
        return 1.0
    return float(df[col].isna().sum()) / total


def _check_field(
    df: pd.DataFrame,
    col: str,
    gap_id: str,
    threshold: float = None,
) -> dict[str, Any]:
    """Check one field against the null threshold."""
    t = threshold if threshold is not None else config.NULL_THRESHOLD
    nr = _null_rate(df, col)
    status = "CONFIRMED" if nr <= t else "FAILED"
    result = {
        "gap_id": gap_id,
        "field": col,
        "null_rate": round(nr, 4),
        "threshold": t,
        "status": status,
    }
    if status == "FAILED":
        logger.warning("Gap %s FAILED: field='%s' null_rate=%.1f%% > threshold=%.1f%%",
                       gap_id, col, nr * 100, t * 100)
    else:
        logger.info("Gap %s CONFIRMED: field='%s' null_rate=%.1f%%", gap_id, col, nr * 100)
    return result


def run_gap_checks(
    stock_master: pd.DataFrame,
    consumption: pd.DataFrame,
    po_history: pd.DataFrame,
    maintenance_cal: pd.DataFrame,
) -> dict[str, Any]:
    """
    Run all gap checks and return updated gap register.
    Returns a dict with gap statuses and a blocked_metrics dict.
    """
    # Load original gap register
    if GAP_REGISTER_SOURCE.exists():
        with open(GAP_REGISTER_SOURCE) as f:
            original = json.load(f)
    else:
        logger.warning("gap_register_v1.json not found at %s — using empty base", GAP_REGISTER_SOURCE)
        original = {"gaps": []}

    checks: list[dict] = []
    blocked: dict[str, bool] = {}

    # G-01: CRITICAL_FLAG / critical_flag
    r = _check_field(stock_master, "critical_flag", "G-01")
    checks.append(r)
    blocked["G-01"] = r["status"] == "FAILED"

    # G-02: RESB data (fill rate) — check if po_history has demand-met proxy
    # RESB is not in the current GCS export; check for reservation columns
    resb_present = any(c in po_history.columns for c in ["BDMNG", "ENMNG", "demand_met", "total_demand"])
    r = {
        "gap_id": "G-02",
        "field": "RESB.BDMNG / RESB.ENMNG",
        "null_rate": 1.0 if not resb_present else 0.0,
        "threshold": config.NULL_THRESHOLD,
        "status": "CONFIRMED" if resb_present else "FAILED",
        "note": "RESB not present in PO history export — Fill Rate will show 'Data not available'",
    }
    checks.append(r)
    blocked["G-02"] = not resb_present

    # G-03: Monthly stock snapshots for turnover
    # Check if stock_master has a snapshot_date or period column
    snapshot_present = any(c in stock_master.columns for c in ["snapshot_date", "period", "BUDAT"])
    r = {
        "gap_id": "G-03",
        "field": "monthly_stock_snapshot",
        "null_rate": 1.0 if not snapshot_present else 0.0,
        "threshold": config.NULL_THRESHOLD,
        "status": "CONFIRMED" if snapshot_present else "FAILED",
        "note": "Point-in-time stock used for turnover (G-03 fallback)",
    }
    checks.append(r)
    blocked["G-03"] = not snapshot_present

    # G-04: SHUTDOWN_FLAG / shutdown_flag
    r = _check_field(maintenance_cal, "shutdown_flag", "G-04")
    checks.append(r)
    blocked["G-04"] = r["status"] == "FAILED"

    # G-05: ContextFlow MCP — checked at runtime by contextflow_client.py
    cf_endpoint = config._optional("CONTEXTFLOW_MCP_ENDPOINT")
    cf_key = config._optional("CONTEXTFLOW_API_KEY")
    cf_ok = bool(cf_endpoint and cf_key)
    r = {
        "gap_id": "G-05",
        "field": "CONTEXTFLOW_MCP_ENDPOINT + CONTEXTFLOW_API_KEY",
        "null_rate": 0.0 if cf_ok else 1.0,
        "threshold": 0.0,
        "status": "CONFIRMED" if cf_ok else "FAILED",
        "note": "ContextFlow MCP credentials not set — forecast metrics will show 'Data not available'",
    }
    checks.append(r)
    blocked["G-05"] = not cf_ok

    # G-06: Historical forecast data — cannot check until ContextFlow runs
    r = {
        "gap_id": "G-06",
        "field": "ContextFlow historical forecast_qty",
        "null_rate": 1.0,
        "threshold": config.NULL_THRESHOLD,
        "status": "PENDING",
        "note": "Forecast Accuracy/Bias available only after first full forecast cycle",
    }
    checks.append(r)
    blocked["G-06"] = True

    # G-07: GCS bucket path
    gcs_ok = bool(config.GCS_BUCKET and config.GCS_CONSUMPTION_PATH)
    r = {
        "gap_id": "G-07",
        "field": "GCS_BUCKET + GCS_*_PATH",
        "null_rate": 0.0 if gcs_ok else 1.0,
        "threshold": 0.0,
        "status": "CONFIRMED" if gcs_ok else "FAILED",
        "note": "Real GCS bucket path required — pipeline cannot run without this",
    }
    checks.append(r)
    blocked["G-07"] = not gcs_ok

    # G-08: BWART movement types
    bwart_present = "movement_type" in consumption.columns
    if bwart_present:
        found_types = set(consumption["movement_type"].dropna().unique())
        expected = set(config.CONSUMPTION_BWART_LIST)
        overlap = found_types & expected
        r = {
            "gap_id": "G-08",
            "field": "BWART / movement_type",
            "null_rate": _null_rate(consumption, "movement_type"),
            "threshold": config.NULL_THRESHOLD,
            "status": "CONFIRMED" if overlap else "FAILED",
            "found_movement_types": sorted(found_types),
            "expected_movement_types": sorted(expected),
            "note": f"Found {len(overlap)}/{len(expected)} expected BWART codes in data",
        }
    else:
        r = {
            "gap_id": "G-08",
            "field": "BWART / movement_type",
            "null_rate": 1.0,
            "threshold": config.NULL_THRESHOLD,
            "status": "FAILED",
            "note": "movement_type column absent from consumption extract",
        }
    checks.append(r)
    blocked["G-08"] = r["status"] == "FAILED"

    # G-09: VERPR / moving_avg_price
    r = _check_field(stock_master, "moving_avg_price", "G-09", threshold=0.5)
    checks.append(r)
    blocked["G-09"] = r["status"] == "FAILED"

    # G-10: Plant names (T001W)
    plant_name_present = "plant_name" in stock_master.columns
    r = {
        "gap_id": "G-10",
        "field": "T001W.plant_name",
        "null_rate": 0.0 if plant_name_present else 1.0,
        "threshold": config.NULL_THRESHOLD,
        "status": "CONFIRMED" if plant_name_present else "FAILED",
        "note": "Plant codes will be shown in filters instead of names (G-10 fallback)",
    }
    checks.append(r)
    blocked["G-10"] = not plant_name_present

    # Build updated gap register
    updated_gaps = []
    check_by_id = {c["gap_id"]: c for c in checks}
    for gap in original.get("gaps", []):
        gid = gap["id"]
        check = check_by_id.get(gid, {})
        updated = dict(gap)
        if check:
            updated["status"] = check["status"]
            updated["null_rate"] = check.get("null_rate")
            updated["checked_at"] = datetime.now(timezone.utc).isoformat()
            if "note" in check:
                updated["check_note"] = check["note"]
        updated_gaps.append(updated)

    result = {
        "version": "1.0.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "blocked_metrics": blocked,
        "gaps": updated_gaps,
        "summary": {
            "total": len(checks),
            "confirmed": sum(1 for c in checks if c["status"] == "CONFIRMED"),
            "failed": sum(1 for c in checks if c["status"] == "FAILED"),
            "pending": sum(1 for c in checks if c["status"] == "PENDING"),
        },
    }

    SERVING_DIR.mkdir(parents=True, exist_ok=True)
    UPDATED_GAP_REGISTER.write_text(json.dumps(result, indent=2, default=str))
    logger.info(
        "Gap register updated: %d confirmed, %d failed, %d pending",
        result["summary"]["confirmed"],
        result["summary"]["failed"],
        result["summary"]["pending"],
    )
    return result
