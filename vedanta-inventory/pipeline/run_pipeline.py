"""
Pipeline Orchestrator — S-2 (Devika Rao)

Runs the full SAP → GCS → Parquet → metrics pipeline in order:
  1. Extract (GCS → raw Parquet)
  2. Transform (raw → clean Parquet, with drop log)
  3. Reconcile (clean vs raw, write report)
  4. Gap check (null-threshold checks, update gap register)
  5. Compute metrics (all 14 KPIs per material)
  6. Write metrics Parquet to serving layer

Usage:
  python -m pipeline.run_pipeline

Environment variables required:
  GCS_BUCKET, GCS_CONSUMPTION_PATH, GCS_STOCK_MASTER_PATH,
  GCS_PO_HISTORY_PATH, GCS_SHUTDOWN_CALENDAR_PATH,
  GOOGLE_APPLICATION_CREDENTIALS

See .env.example for the full list.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline import config
from pipeline.extractor import (
    extract_consumption_history,
    extract_stock_master,
    extract_po_history,
    extract_maintenance_calendar,
    DataSourceUnavailableError,
)
from pipeline.transformer import (
    transform_consumption_history,
    transform_stock_master,
    transform_po_history,
    transform_maintenance_calendar,
)
from pipeline.reconciler import (
    reconcile_consumption,
    reconcile_stock_master,
    reconcile_po_history,
    reconcile_maintenance_calendar,
    write_report,
)
from pipeline.gap_updater import run_gap_checks
from pipeline.metrics_v2 import compute_all_metrics, compute_critical_avail

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

SERVING_DIR = Path(config.SERVING_DIR)
METRICS_PATH = SERVING_DIR / "metrics.parquet"


def run() -> dict:
    """
    Run the full pipeline. Returns a summary dict.
    Raises DataSourceUnavailableError if GCS is not configured.
    """
    logger.info("=== Vedanta Inventory Pipeline — S-2 START ===")
    logger.info("SERVING_DIR: %s", SERVING_DIR)
    logger.info("GCS_BUCKET: %s", config.GCS_BUCKET or "NOT SET")
    logger.info("BWART filter: %s", config.CONSUMPTION_BWART_LIST)

    # ── Step 1: Extract ──────────────────────────────────────────────────────
    logger.info("Step 1/5: Extracting from GCS...")
    try:
        raw_cons = extract_consumption_history()
        raw_stock = extract_stock_master()
        raw_po = extract_po_history()
        raw_maint = extract_maintenance_calendar()
    except DataSourceUnavailableError as e:
        logger.error("EXTRACTION FAILED: %s", e)
        raise

    # ── Step 2: Transform ────────────────────────────────────────────────────
    logger.info("Step 2/5: Transforming...")
    clean_cons, cons_drops = transform_consumption_history(raw_cons)
    clean_stock, stock_drops = transform_stock_master(raw_stock)
    clean_po, po_drops = transform_po_history(raw_po)
    clean_maint, maint_drops = transform_maintenance_calendar(raw_maint)

    all_drops = cons_drops + stock_drops + po_drops + maint_drops

    # ── Step 3: Reconcile ────────────────────────────────────────────────────
    logger.info("Step 3/5: Reconciling...")
    recon_results = [
        reconcile_consumption(raw_cons, clean_cons, cons_drops),
        reconcile_stock_master(raw_stock, clean_stock, stock_drops),
        reconcile_po_history(raw_po, clean_po, po_drops),
        reconcile_maintenance_calendar(raw_maint, clean_maint, maint_drops),
    ]
    report_path = write_report(recon_results)

    unreconciled = [r for r in recon_results if r["status"] == "UNRECONCILED"]
    if unreconciled:
        domains = [r["domain"] for r in unreconciled]
        logger.error(
            "RECONCILIATION FAILED for: %s — metrics will NOT be published until resolved",
            domains,
        )
        # Do not publish metrics on an unreconciled load
        return {
            "status": "UNRECONCILED",
            "unreconciled_domains": domains,
            "report": str(report_path),
        }

    # ── Step 4: Gap checks ───────────────────────────────────────────────────
    logger.info("Step 4/5: Running gap checks...")
    gap_result = run_gap_checks(clean_stock, clean_cons, clean_po, clean_maint)
    blocked = gap_result["blocked_metrics"]

    # ── Step 5: Compute metrics ──────────────────────────────────────────────
    logger.info("Step 5/5: Computing metrics for %d materials...", len(clean_stock))

    # Build consumption lookup: (material_code, plant) → DataFrame
    cons_lookup: dict[tuple, pd.DataFrame] = {}
    if not clean_cons.empty and "material_code" in clean_cons.columns:
        for key, grp in clean_cons.groupby(["material_code", "plant"]):
            cons_lookup[key] = grp.reset_index(drop=True)

    # Build PO lookup
    po_lookup: dict[tuple, pd.DataFrame] = {}
    if not clean_po.empty and "material_code" in clean_po.columns:
        for key, grp in clean_po.groupby(["material_code", "plant"]):
            po_lookup[key] = grp.reset_index(drop=True)

    metrics_rows = []
    for _, stock_row in clean_stock.iterrows():
        mat = str(stock_row.get("material_code", ""))
        plant = str(stock_row.get("plant", ""))
        key = (mat, plant)

        cons_df = cons_lookup.get(key, pd.DataFrame())
        po_df = po_lookup.get(key, pd.DataFrame())

        m = compute_all_metrics(
            material_code=mat,
            plant=plant,
            stock_row=stock_row,
            consumption_df=cons_df,
            po_df=po_df,
            blocked_metrics=blocked,
        )
        metrics_rows.append(m)

    # Population-level: Critical Spares Availability
    crit_avail, crit_gaps = compute_critical_avail(
        clean_stock, blocked=blocked.get("G-01", False)
    )

    # Serialise data_gaps list to JSON string for Parquet storage
    metrics_df = pd.DataFrame(metrics_rows)
    if "data_gaps" in metrics_df.columns:
        metrics_df["data_gaps"] = metrics_df["data_gaps"].apply(
            lambda g: json.dumps(g) if isinstance(g, list) else g
        )

    SERVING_DIR.mkdir(parents=True, exist_ok=True)
    metrics_df.to_parquet(METRICS_PATH, index=False)
    logger.info("Metrics written: %s (%d rows)", METRICS_PATH, len(metrics_df))

    # Write population-level metrics
    pop_metrics = {
        "CRITICAL_AVAIL": crit_avail,
        "CRITICAL_AVAIL_gaps": crit_gaps,
        "total_materials": len(metrics_df),
        "total_inv_value_inr": float(metrics_df["INV_VALUE"].fillna(0).sum()),
        "nmi_count": int(metrics_df["NON_MOVING"].fillna(False).sum()),
        "smi_count": int(metrics_df["SLOW_MOVING"].fillna(False).sum()),
        "overstock_count": int(metrics_df["OVERSTOCK_FLAG"].fillna(False).sum()),
        "understock_count": int(metrics_df["UNDERSTOCK_FLAG"].fillna(False).sum()),
        "avg_doi": (
            float(metrics_df["DOI"].dropna().mean())
            if metrics_df["DOI"].notna().any() else None
        ),
        "gap_summary": gap_result["summary"],
        "blocked_metrics": blocked,
    }
    pop_path = SERVING_DIR / "population_metrics.json"
    pop_path.write_text(json.dumps(pop_metrics, indent=2, default=str))
    logger.info("Population metrics written: %s", pop_path)

    logger.info("=== Vedanta Inventory Pipeline — S-2 COMPLETE ===")
    return {
        "status": "OK",
        "materials_processed": len(metrics_df),
        "reconciliation_report": str(report_path),
        "metrics_parquet": str(METRICS_PATH),
        "population_metrics": str(pop_path),
        "gap_summary": gap_result["summary"],
        "blocked_metrics": blocked,
    }


if __name__ == "__main__":
    try:
        result = run()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result.get("status") == "OK" else 1)
    except DataSourceUnavailableError as e:
        logger.error("Pipeline cannot run: %s", e)
        sys.exit(2)
    except Exception as e:
        logger.exception("Unexpected pipeline error: %s", e)
        sys.exit(3)
