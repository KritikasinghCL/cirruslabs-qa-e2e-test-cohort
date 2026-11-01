"""
Reconciler — S-2 (Devika Rao)

Compares clean serving tables against raw extracts on:
  - Row counts (raw vs clean, with drop breakdown)
  - Stock value total (SUM(LABST × unit_price) in clean vs raw)
  - Consumption total (SUM(qty) in clean vs raw for the same BWART filter)

Writes a JSON reconciliation report to SERVING_DIR/reconciliation_report.json.

A load is only marked RECONCILED if:
  - Row count delta is explained entirely by the drop_log.
  - Stock value delta is < 0.01% (floating-point tolerance).
  - Consumption total delta is < 0.01%.

Any unexplained delta is flagged as UNRECONCILED and blocks downstream use.
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

SERVING_DIR = Path(config.SERVING_DIR)
REPORT_PATH = SERVING_DIR / "reconciliation_report.json"

TOLERANCE = 1e-4  # 0.01%


def _pct_delta(a: float, b: float) -> float:
    """Percentage difference of b relative to a. Returns 0 if a == 0."""
    if a == 0:
        return 0.0 if b == 0 else float("inf")
    return abs(b - a) / abs(a)


def reconcile_consumption(
    raw: pd.DataFrame,
    clean: pd.DataFrame,
    drop_log: list[dict],
) -> dict[str, Any]:
    """Reconcile consumption history extract."""
    raw_rows = len(raw)
    clean_rows = len(clean)
    explained_drops = sum(d.get("rows_dropped", 0) for d in drop_log if d.get("domain") == "consumption_history")
    unexplained = raw_rows - clean_rows - explained_drops

    # Consumption total (qty) — compare raw (BWART-filtered) vs clean
    raw_qty_col = next((c for c in ["MENGE", "qty"] if c in raw.columns), None)
    clean_qty_col = "qty" if "qty" in clean.columns else None

    raw_total_qty: float = 0.0
    clean_total_qty: float = 0.0
    qty_delta_pct: float = 0.0

    if raw_qty_col and clean_qty_col:
        # Apply same BWART filter to raw for fair comparison
        bwart_col = next((c for c in ["BWART", "movement_type"] if c in raw.columns), None)
        raw_filtered = raw.copy()
        if bwart_col:
            raw_filtered = raw_filtered[raw_filtered[bwart_col].isin(config.CONSUMPTION_BWART_LIST)]
        raw_total_qty = float(pd.to_numeric(raw_filtered[raw_qty_col], errors="coerce").fillna(0).sum())
        clean_total_qty = float(clean[clean_qty_col].fillna(0).sum())
        qty_delta_pct = _pct_delta(raw_total_qty, clean_total_qty)

    status = "RECONCILED" if unexplained == 0 and qty_delta_pct <= TOLERANCE else "UNRECONCILED"
    if status == "UNRECONCILED":
        logger.error(
            "UNRECONCILED consumption_history: unexplained_row_delta=%d qty_delta_pct=%.4f%%",
            unexplained, qty_delta_pct * 100,
        )

    return {
        "domain": "consumption_history",
        "status": status,
        "raw_rows": raw_rows,
        "clean_rows": clean_rows,
        "explained_drops": explained_drops,
        "unexplained_row_delta": unexplained,
        "raw_total_qty": round(raw_total_qty, 4),
        "clean_total_qty": round(clean_total_qty, 4),
        "qty_delta_pct": round(qty_delta_pct * 100, 6),
        "drop_log": drop_log,
    }


def reconcile_stock_master(
    raw: pd.DataFrame,
    clean: pd.DataFrame,
    drop_log: list[dict],
) -> dict[str, Any]:
    """Reconcile stock master extract."""
    raw_rows = len(raw)
    clean_rows = len(clean)
    explained_drops = sum(d.get("rows_dropped", 0) for d in drop_log if d.get("domain") == "stock_master")
    unexplained = raw_rows - clean_rows - explained_drops

    # Stock value: SUM(LABST × unit_price)
    # Raw: use LABST × VERPR (or STPRS fallback)
    raw_value: float = 0.0
    clean_value: float = 0.0
    value_delta_pct: float = 0.0

    labst_col = next((c for c in ["LABST", "unrestricted_stock"] if c in raw.columns), None)
    verpr_col = next((c for c in ["VERPR", "moving_avg_price"] if c in raw.columns), None)
    stprs_col = next((c for c in ["STPRS", "standard_price"] if c in raw.columns), None)

    if labst_col:
        raw_labst = pd.to_numeric(raw[labst_col], errors="coerce").fillna(0)
        if verpr_col:
            raw_price = pd.to_numeric(raw[verpr_col], errors="coerce").fillna(0)
        elif stprs_col:
            raw_price = pd.to_numeric(raw[stprs_col], errors="coerce").fillna(0)
        else:
            raw_price = pd.Series(0.0, index=raw.index)
        # Scope raw value to ZSPR/ZSPN only — same population as clean table
        mtart_col = next((c for c in ["MTART", "material_type"] if c in raw.columns), None)
        if mtart_col:
            scope_mask = raw[mtart_col].isin(["ZSPR", "ZSPN"])
            raw_value = float((raw_labst[scope_mask] * raw_price[scope_mask]).sum())
        else:
            raw_value = float((raw_labst * raw_price).sum())

    if "unrestricted_stock" in clean.columns and "unit_price" in clean.columns:
        clean_value = float(
            (clean["unrestricted_stock"].fillna(0) * clean["unit_price"].fillna(0)).sum()
        )

    if raw_value > 0 or clean_value > 0:
        value_delta_pct = _pct_delta(raw_value, clean_value)

    status = "RECONCILED" if unexplained == 0 and value_delta_pct <= TOLERANCE else "UNRECONCILED"
    if status == "UNRECONCILED":
        logger.error(
            "UNRECONCILED stock_master: unexplained_row_delta=%d value_delta_pct=%.4f%%",
            unexplained, value_delta_pct * 100,
        )

    return {
        "domain": "stock_master",
        "status": status,
        "raw_rows": raw_rows,
        "clean_rows": clean_rows,
        "explained_drops": explained_drops,
        "unexplained_row_delta": unexplained,
        "raw_stock_value_inr": round(raw_value, 2),
        "clean_stock_value_inr": round(clean_value, 2),
        "value_delta_pct": round(value_delta_pct * 100, 6),
        "drop_log": drop_log,
    }


def reconcile_po_history(
    raw: pd.DataFrame,
    clean: pd.DataFrame,
    drop_log: list[dict],
) -> dict[str, Any]:
    """Reconcile PO history extract."""
    raw_rows = len(raw)
    clean_rows = len(clean)
    explained_drops = sum(d.get("rows_dropped", 0) for d in drop_log if d.get("domain") == "po_history")
    unexplained = raw_rows - clean_rows - explained_drops

    status = "RECONCILED" if unexplained == 0 else "UNRECONCILED"
    return {
        "domain": "po_history",
        "status": status,
        "raw_rows": raw_rows,
        "clean_rows": clean_rows,
        "explained_drops": explained_drops,
        "unexplained_row_delta": unexplained,
        "drop_log": drop_log,
    }


def reconcile_maintenance_calendar(
    raw: pd.DataFrame,
    clean: pd.DataFrame,
    drop_log: list[dict],
) -> dict[str, Any]:
    """Reconcile maintenance calendar extract."""
    raw_rows = len(raw)
    clean_rows = len(clean)
    explained_drops = sum(d.get("rows_dropped", 0) for d in drop_log if d.get("domain") == "maintenance_calendar")
    unexplained = raw_rows - clean_rows - explained_drops

    status = "RECONCILED" if unexplained == 0 else "UNRECONCILED"
    return {
        "domain": "maintenance_calendar",
        "status": status,
        "raw_rows": raw_rows,
        "clean_rows": clean_rows,
        "explained_drops": explained_drops,
        "unexplained_row_delta": unexplained,
        "drop_log": drop_log,
    }


def write_report(results: list[dict[str, Any]]) -> Path:
    """Write the reconciliation report to disk."""
    SERVING_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "RECONCILED" if all(r["status"] == "RECONCILED" for r in results) else "UNRECONCILED",
        "domains": results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    logger.info("Reconciliation report written: %s (overall=%s)", REPORT_PATH, report["overall_status"])
    return REPORT_PATH
