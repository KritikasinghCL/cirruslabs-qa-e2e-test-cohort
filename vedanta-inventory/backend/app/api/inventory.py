"""
Inventory API routes — returns metrics for all materials.
Reads from GCS (live) or test fixtures (USE_TEST_FIXTURES=true).
"""
from __future__ import annotations
import asyncio
import logging
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Query, HTTPException

from app.core.config import settings
from app.models.schemas import MaterialMetrics, MaterialType
from app.services.metrics_engine import compute_real_data_metrics, wire_forecast_into_metrics
from app.services.fixture_loader import load_fixtures_if_enabled
from app.services.gcs_loader import (
    load_consumption_history, load_stock_master, load_po_history,
    DataSourceUnavailableError,
)
from app.integrations.contextflow_client import (
    request_forecast, ContextFlowUnavailableError,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["inventory"])

# Single gap entry surfaced when ContextFlow is not connected.
_CF_GAP = (
    "G-05 BLOCKER: ContextFlow MCP not configured — "
    "CONTEXTFLOW_MCP_ENDPOINT and/or CONTEXTFLOW_API_KEY env vars missing. "
    "Forecast-dependent metrics (Safety Stock, ROP, Overstock, Understock, "
    "Forecast 3/6/12mo) show null until this is resolved."
)


def _get_data():
    if settings.USE_TEST_FIXTURES:
        return load_fixtures_if_enabled()
    try:
        stock_master = load_stock_master()
        consumption = load_consumption_history()
        po_history = load_po_history()
        return stock_master, consumption, po_history
    except DataSourceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _compute_metrics(
    plant: Optional[str] = None,
    material_type: Optional[str] = None,
    category: Optional[str] = None,
    critical_only: bool = False,
    shutdown_only: bool = False,
) -> List[MaterialMetrics]:
    """
    Core logic shared by the HTTP route and internal callers.
    All parameters are plain Python values — no FastAPI Query objects.
    """
    stock_master, consumption_history, po_history = _get_data()

    # Build lookup maps
    consumption_by_mat: dict = {}
    for r in consumption_history.records:
        key = (r.material_code, r.plant)
        consumption_by_mat.setdefault(key, []).append(r)

    po_by_mat: dict = {}
    for r in po_history.records:
        key = (r.material_code, r.plant)
        po_by_mat.setdefault(key, []).append(r)

    results: List[MaterialMetrics] = []
    for stock in stock_master.records:
        # Apply filters — compare against plain string values
        if plant and stock.plant != plant:
            continue
        mt_val = material_type.value if hasattr(material_type, "value") else material_type
        if mt_val and stock.material_type != mt_val:
            continue
        if category and stock.category != category:
            continue
        if critical_only and not stock.critical_flag:
            continue
        if shutdown_only and not stock.shutdown_flag:
            continue

        key = (stock.material_code, stock.plant)
        m = compute_real_data_metrics(
            stock=stock,
            consumption_records=consumption_by_mat.get(key, []),
            po_records=po_by_mat.get(key, []),
        )
        results.append(m)

    return results


async def _compute_metrics_with_forecast(
    plant: Optional[str] = None,
    material_type: Optional[str] = None,
    category: Optional[str] = None,
    critical_only: bool = False,
    shutdown_only: bool = False,
) -> List[MaterialMetrics]:
    """
    Compute real-data metrics then attempt to wire in ContextFlow forecasts.

    If ContextFlow is not configured, a single G-05 gap entry is appended to
    every material's data_gaps list and all forecast-dependent fields remain None.
    No fabricated data is emitted under any circumstance.
    """
    stock_master, consumption_history, po_history = _get_data()

    consumption_by_mat: dict = {}
    for r in consumption_history.records:
        key = (r.material_code, r.plant)
        consumption_by_mat.setdefault(key, []).append(r)

    po_by_mat: dict = {}
    for r in po_history.records:
        key = (r.material_code, r.plant)
        po_by_mat.setdefault(key, []).append(r)

    # Compute real-data metrics for all materials first
    base_metrics: List[MaterialMetrics] = []
    for stock in stock_master.records:
        if plant and stock.plant != plant:
            continue
        mt_val = material_type.value if hasattr(material_type, "value") else material_type
        if mt_val and stock.material_type != mt_val:
            continue
        if category and stock.category != category:
            continue
        if critical_only and not stock.critical_flag:
            continue
        if shutdown_only and not stock.shutdown_flag:
            continue

        key = (stock.material_code, stock.plant)
        m = compute_real_data_metrics(
            stock=stock,
            consumption_records=consumption_by_mat.get(key, []),
            po_records=po_by_mat.get(key, []),
        )
        base_metrics.append((stock, m, consumption_by_mat.get(key, [])))

    # Attempt ContextFlow forecast for each material concurrently.
    # A single ContextFlowUnavailableError on the first call short-circuits the
    # rest — we add one gap entry per material and return base metrics only.
    results: List[MaterialMetrics] = []
    cf_unavailable_msg: Optional[str] = None

    async def _fetch_and_wire(stock, metrics, cons_recs):
        nonlocal cf_unavailable_msg
        if cf_unavailable_msg is not None:
            # ContextFlow already known unavailable — skip HTTP call
            metrics.data_gaps = list(metrics.data_gaps) + [_CF_GAP]
            return metrics
        try:
            forecast = await request_forecast(
                material_code=stock.material_code,
                plant=stock.plant,
                consumption_records=cons_recs,
            )
            return wire_forecast_into_metrics(
                metrics=metrics,
                forecast_response=forecast,
                current_stock=stock.current_stock,
                consumption_records=cons_recs,
            )
        except ContextFlowUnavailableError as exc:
            cf_unavailable_msg = str(exc)
            logger.warning("ContextFlow unavailable: %s", cf_unavailable_msg)
            metrics.data_gaps = list(metrics.data_gaps) + [_CF_GAP]
            return metrics

    tasks = [_fetch_and_wire(s, m, c) for s, m, c in base_metrics]
    results = await asyncio.gather(*tasks)
    return list(results)


@router.get("/inventory/metrics", response_model=List[MaterialMetrics])
def get_inventory_metrics(
    plant: Optional[str] = Query(None),
    material_type: Optional[MaterialType] = Query(None),
    category: Optional[str] = Query(None),
    critical_only: bool = Query(False),
    shutdown_only: bool = Query(False),
):
    """
    Returns computed real-data metrics for all ZSPR/ZSPN materials.
    Forecast-dependent fields (safety_stock, rop, overstock_flag, understock_flag)
    will be None until ContextFlow is wired — shown as 'Data not available' in UI.
    """
    return _compute_metrics(
        plant=plant,
        material_type=material_type,
        category=category,
        critical_only=critical_only,
        shutdown_only=shutdown_only,
    )


@router.get("/inventory/metrics/with-forecast", response_model=List[MaterialMetrics])
async def get_inventory_metrics_with_forecast(
    plant: Optional[str] = Query(None),
    material_type: Optional[MaterialType] = Query(None),
    category: Optional[str] = Query(None),
    critical_only: bool = Query(False),
    shutdown_only: bool = Query(False),
):
    """
    Returns metrics with ContextFlow demand forecasts wired in.

    When ContextFlow is configured: Safety Stock, ROP, Overstock, Understock,
    and 3/6/12-month forecast quantities are populated from real MCP data.

    When ContextFlow is NOT configured: all forecast-dependent fields are null
    and a single G-05 gap entry is appended to each material's data_gaps list.
    No fabricated data is emitted.
    """
    return await _compute_metrics_with_forecast(
        plant=plant,
        material_type=material_type,
        category=category,
        critical_only=critical_only,
        shutdown_only=shutdown_only,
    )


@router.get("/inventory/summary")
def get_inventory_summary(
    plant: Optional[str] = Query(None),
    material_type: Optional[MaterialType] = Query(None),
):
    """Executive summary KPIs — real-data metrics only (no ContextFlow)."""
    metrics = _compute_metrics(plant=plant, material_type=material_type)
    return _build_summary(metrics)


@router.get("/inventory/summary/with-forecast")
async def get_inventory_summary_with_forecast(
    plant: Optional[str] = Query(None),
    material_type: Optional[MaterialType] = Query(None),
):
    """Executive summary KPIs with ContextFlow forecast data wired in."""
    metrics = await _compute_metrics_with_forecast(plant=plant, material_type=material_type)
    return _build_summary(metrics)


def _build_summary(metrics: List[MaterialMetrics]) -> dict:
    total_value = sum(m.inventory_value or 0 for m in metrics)
    nmi_count = sum(1 for m in metrics if m.non_moving_flag)
    smi_count = sum(1 for m in metrics if m.slow_moving_flag)
    overstock_count = sum(1 for m in metrics if m.overstock_flag)
    understock_count = sum(1 for m in metrics if m.understock_flag)
    avg_doh_vals = [m.days_of_inventory for m in metrics if m.days_of_inventory is not None]
    avg_doh = round(sum(avg_doh_vals) / len(avg_doh_vals), 1) if avg_doh_vals else None
    acc_vals = [m.forecast_accuracy_pct for m in metrics if m.forecast_accuracy_pct is not None]
    avg_acc = round(sum(acc_vals) / len(acc_vals), 1) if acc_vals else None

    return {
        "total_materials": len(metrics),
        "total_inventory_value": total_value,
        "avg_days_of_inventory": avg_doh,
        "nmi_count": nmi_count,
        "smi_count": smi_count,
        "overstock_count": overstock_count,
        "understock_count": understock_count,
        "forecast_accuracy_pct": avg_acc,
        "data_gaps": ["forecast_accuracy_pct: post-actuals not yet available"] if avg_acc is None else [],
    }
