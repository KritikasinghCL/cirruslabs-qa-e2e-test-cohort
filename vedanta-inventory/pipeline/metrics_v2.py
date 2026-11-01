"""
Metrics v2 — S-2 (Devika Rao)

Implements all 14 KPI formulas exactly as defined in data_contract_v1.yaml §3.
Operates on clean Parquet DataFrames from the serving layer.

Formula source: data_contract_v1.yaml
  DOI           = STOCK_ON_HAND / AVG_DAILY_CONS_90D
  INV_VALUE     = SUM(LABST × VERPR)
  INV_TURNOVER  = COGS_365D / AVG_INV_VALUE
  SAFETY_STOCK  = Z × σ_daily × √LT
  REORDER_POINT = (AVG_CONS × LT) + SAFETY_STOCK
  OVERSTOCK_FLAG = STOCK > AVG_CONS × 180d
  UNDERSTOCK_FLAG = STOCK < REORDER_POINT
  NON_MOVING    = no consumption in 365d AND stock > 0
  SLOW_MOVING   = DOI > 90d AND NOT NON_MOVING
  FILL_RATE     = FULFILLED / REQUESTED × 100  (RESB)
  CRITICAL_AVAIL = COUNT(crit w/ stock) / COUNT(crit) × 100
  DEMAND_FORECAST = ContextFlow MCP (not computed here)
  FORECAST_ACCURACY = 100 − (1/n)×Σ|A−F|/A×100  (MAPE)
  FORECAST_BIAS = Σ(F−A)/Σ(A)×100

Rules:
- If any required input is None/NaN, the metric is None and a gap entry is added.
- Caller must pass blocked_metrics dict from gap_updater to skip blocked metrics.
- No hardcoded data. No fallback to sample values.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd

from pipeline import config

logger = logging.getLogger(__name__)

DATA_NOT_AVAILABLE = None  # sentinel — UI renders "Data not available"


# ---------------------------------------------------------------------------
# 1. Days of Inventory (DOI)
#    DOI = STOCK_ON_HAND / AVG_DAILY_CONS_90D
#    AVG_DAILY_CONS_90D = SUM(qty, last 90 days) / 90
# ---------------------------------------------------------------------------

def compute_doi(
    stock_on_hand: float,
    consumption_df: pd.DataFrame,
    as_of: Optional[date] = None,
    lookback_days: int = 90,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []
    if consumption_df is None or consumption_df.empty:
        gaps.append("DOI: no consumption records — AVG_DAILY_CONS_90D cannot be computed")
        return DATA_NOT_AVAILABLE, gaps

    as_of_ts = pd.Timestamp(as_of or date.today())
    cutoff = as_of_ts - pd.Timedelta(days=lookback_days)
    recent = consumption_df[consumption_df["posting_date"] >= cutoff]

    if recent.empty:
        gaps.append(
            f"DOI: no consumption in last {lookback_days} days — "
            f"AVG_DAILY_CONS_90D cannot be computed (material is non-moving)"
        )
        return DATA_NOT_AVAILABLE, gaps

    avg_daily = float(recent["qty"].sum()) / lookback_days
    if avg_daily == 0:
        gaps.append("DOI: AVG_DAILY_CONS_90D = 0 — material is non-moving, DOI cannot be computed")
        return DATA_NOT_AVAILABLE, gaps

    return round(stock_on_hand / avg_daily, 2), gaps


# ---------------------------------------------------------------------------
# 2. Inventory Value
#    INV_VALUE = SUM(LABST × VERPR)  per (MATNR, WERKS)
# ---------------------------------------------------------------------------

def compute_inv_value(
    unrestricted_stock: float,
    unit_price: float,
    price_missing: bool = False,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []
    if price_missing:
        gaps.append("INV_VALUE: unit_price missing (VERPR/STPRS/LAEPR all null) — value shown as 0 (G-09)")
    return round(unrestricted_stock * unit_price, 2), gaps


# ---------------------------------------------------------------------------
# 3. Inventory Turnover
#    INV_TURNOVER = COGS_365D / AVG_INV_VALUE
#    COGS_365D = SUM(qty × unit_price, last 365 days)
#    AVG_INV_VALUE = current stock × unit_price (G-03 fallback: point-in-time)
# ---------------------------------------------------------------------------

def compute_inv_turnover(
    consumption_df: pd.DataFrame,
    unit_price: float,
    current_stock: float,
    as_of: Optional[date] = None,
    lookback_days: int = 365,
    g03_point_in_time: bool = True,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []
    if consumption_df is None or consumption_df.empty:
        gaps.append("INV_TURNOVER: no consumption records")
        return DATA_NOT_AVAILABLE, gaps

    as_of_ts = pd.Timestamp(as_of or date.today())
    cutoff = as_of_ts - pd.Timedelta(days=lookback_days)
    recent = consumption_df[consumption_df["posting_date"] >= cutoff]

    cogs = float(recent["qty"].sum()) * unit_price
    avg_inv_value = current_stock * unit_price

    if g03_point_in_time:
        gaps.append("INV_TURNOVER: using point-in-time stock as AVG_INV_VALUE (G-03 fallback — monthly snapshots not available)")

    if avg_inv_value == 0:
        gaps.append("INV_TURNOVER: AVG_INV_VALUE = 0 — turnover undefined")
        return DATA_NOT_AVAILABLE, gaps

    return round(cogs / avg_inv_value, 4), gaps


# ---------------------------------------------------------------------------
# 4. Safety Stock
#    SAFETY_STOCK = Z × σ_daily × √LT
#    σ_daily = std dev of daily consumption over lookback period
#    LT = lead_time_days
# ---------------------------------------------------------------------------

def compute_safety_stock(
    consumption_df: pd.DataFrame,
    lead_time_days: Optional[float],
    z: float = None,
    as_of: Optional[date] = None,
    lookback_days: int = 365,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []
    z = z if z is not None else config.SAFETY_STOCK_Z

    if consumption_df is None or consumption_df.empty:
        gaps.append("SAFETY_STOCK: no consumption records — σ_daily cannot be computed")
        return DATA_NOT_AVAILABLE, gaps

    if lead_time_days is None or math.isnan(lead_time_days) or lead_time_days <= 0:
        gaps.append("SAFETY_STOCK: lead_time_days missing or zero — cannot compute")
        return DATA_NOT_AVAILABLE, gaps

    as_of_ts = pd.Timestamp(as_of or date.today())
    cutoff = as_of_ts - pd.Timedelta(days=lookback_days)
    recent = consumption_df[consumption_df["posting_date"] >= cutoff].copy()

    if recent.empty:
        gaps.append(f"SAFETY_STOCK: no consumption in last {lookback_days} days")
        return DATA_NOT_AVAILABLE, gaps

    # Build daily series (fill missing days with 0); exclude as_of day (incomplete)
    recent["posting_date"] = pd.to_datetime(recent["posting_date"])
    daily = recent.groupby("posting_date")["qty"].sum().reindex(
        pd.date_range(cutoff, as_of_ts - pd.Timedelta(days=1), freq="D"), fill_value=0.0
    )
    sigma_daily = float(daily.std())

    if sigma_daily == 0:
        # No variability — safety stock = 0 (deterministic demand)
        return 0.0, gaps

    ss = z * sigma_daily * math.sqrt(lead_time_days)
    return round(max(0.0, ss), 2), gaps


# ---------------------------------------------------------------------------
# 5. Reorder Point (ROP)
#    ROP = (AVG_CONS × LT) + SAFETY_STOCK
#    AVG_CONS = AVG_DAILY_CONS_90D
# ---------------------------------------------------------------------------

def compute_rop(
    consumption_df: pd.DataFrame,
    lead_time_days: Optional[float],
    safety_stock: Optional[float],
    as_of: Optional[date] = None,
    lookback_days: int = 90,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []

    if safety_stock is None:
        gaps.append("ROP: safety_stock not available")
        return DATA_NOT_AVAILABLE, gaps

    if lead_time_days is None or math.isnan(lead_time_days) or lead_time_days <= 0:
        gaps.append("ROP: lead_time_days missing or zero")
        return DATA_NOT_AVAILABLE, gaps

    if consumption_df is None or consumption_df.empty:
        gaps.append("ROP: no consumption records — AVG_CONS cannot be computed")
        return DATA_NOT_AVAILABLE, gaps

    as_of_ts = pd.Timestamp(as_of or date.today())
    cutoff = as_of_ts - pd.Timedelta(days=lookback_days)
    recent = consumption_df[consumption_df["posting_date"] >= cutoff]
    avg_daily = float(recent["qty"].sum()) / lookback_days if not recent.empty else 0.0

    rop = (avg_daily * lead_time_days) + safety_stock
    return round(max(0.0, rop), 2), gaps


# ---------------------------------------------------------------------------
# 6. Overstock Flag
#    OVERSTOCK_FLAG = STOCK > AVG_CONS × 180d
#    AVG_CONS = AVG_DAILY_CONS_90D
# ---------------------------------------------------------------------------

def compute_overstock_flag(
    stock_on_hand: float,
    consumption_df: pd.DataFrame,
    as_of: Optional[date] = None,
    lookback_days: int = 90,
    overstock_days: int = None,
) -> tuple[Optional[bool], list[str]]:
    gaps: list[str] = []
    od = overstock_days if overstock_days is not None else config.OVERSTOCK_DAYS

    if consumption_df is None or consumption_df.empty:
        gaps.append("OVERSTOCK_FLAG: no consumption records — cannot compute threshold")
        return DATA_NOT_AVAILABLE, gaps

    as_of_ts = pd.Timestamp(as_of or date.today())
    cutoff = as_of_ts - pd.Timedelta(days=lookback_days)
    recent = consumption_df[consumption_df["posting_date"] >= cutoff]
    avg_daily = float(recent["qty"].sum()) / lookback_days if not recent.empty else 0.0

    if avg_daily == 0:
        # Non-moving material with stock > 0 is overstock by definition
        return stock_on_hand > 0, gaps

    threshold = avg_daily * od
    return stock_on_hand > threshold, gaps


# ---------------------------------------------------------------------------
# 7. Understock Flag
#    UNDERSTOCK_FLAG = STOCK < REORDER_POINT
# ---------------------------------------------------------------------------

def compute_understock_flag(
    stock_on_hand: float,
    reorder_point: Optional[float],
) -> tuple[Optional[bool], list[str]]:
    gaps: list[str] = []
    if reorder_point is None:
        gaps.append("UNDERSTOCK_FLAG: reorder_point not available")
        return DATA_NOT_AVAILABLE, gaps
    return stock_on_hand < reorder_point, gaps


# ---------------------------------------------------------------------------
# 8. Non-Moving Inventory (NMI)
#    NON_MOVING = no consumption in 365d AND stock > 0
# ---------------------------------------------------------------------------

def compute_nmi_flag(
    stock_on_hand: float,
    consumption_df: pd.DataFrame,
    as_of: Optional[date] = None,
    lookback_days: int = None,
) -> tuple[Optional[bool], list[str]]:
    gaps: list[str] = []
    ld = lookback_days if lookback_days is not None else config.NMI_LOOKBACK_DAYS

    if stock_on_hand <= 0:
        return False, gaps  # No stock — not a non-moving stock problem

    if consumption_df is None or consumption_df.empty:
        gaps.append(f"NMI: no consumption records — flagging as non-moving (stock={stock_on_hand})")
        return True, gaps

    as_of_ts = pd.Timestamp(as_of or date.today())
    cutoff = as_of_ts - pd.Timedelta(days=ld)
    recent = consumption_df[consumption_df["posting_date"] >= cutoff]
    total_qty = float(recent["qty"].sum()) if not recent.empty else 0.0

    return total_qty == 0, gaps


# ---------------------------------------------------------------------------
# 9. Slow-Moving Inventory (SMI)
#    SLOW_MOVING = DOI > 90d AND NOT NON_MOVING
# ---------------------------------------------------------------------------

def compute_smi_flag(
    doi: Optional[float],
    nmi_flag: Optional[bool],
    doi_threshold_days: int = None,
) -> tuple[Optional[bool], list[str]]:
    gaps: list[str] = []
    dt = doi_threshold_days if doi_threshold_days is not None else config.SMI_DOI_THRESHOLD_DAYS

    if doi is None:
        gaps.append("SMI: DOI not available — cannot classify")
        return DATA_NOT_AVAILABLE, gaps

    if nmi_flag:
        return False, gaps  # Non-moving is a separate category

    return doi > dt, gaps


# ---------------------------------------------------------------------------
# 10. Fill Rate
#     FILL_RATE = FULFILLED / REQUESTED × 100  (from RESB)
#     FULFILLED = RESB.ENMNG (quantity withdrawn)
#     REQUESTED = RESB.BDMNG (requirement quantity)
# ---------------------------------------------------------------------------

def compute_fill_rate(
    fulfilled: Optional[float],
    requested: Optional[float],
    blocked: bool = False,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []
    if blocked:
        gaps.append("FILL_RATE: RESB export not available (G-02) — showing 'Data not available'")
        return DATA_NOT_AVAILABLE, gaps
    if fulfilled is None or requested is None:
        gaps.append("FILL_RATE: RESB.BDMNG / RESB.ENMNG not available (G-02)")
        return DATA_NOT_AVAILABLE, gaps
    if requested == 0:
        gaps.append("FILL_RATE: total requested = 0 — undefined")
        return DATA_NOT_AVAILABLE, gaps
    return round((fulfilled / requested) * 100, 2), gaps


# ---------------------------------------------------------------------------
# 11. Critical Spares Availability
#     CRITICAL_AVAIL = COUNT(crit w/ stock > 0) / COUNT(crit) × 100
# ---------------------------------------------------------------------------

def compute_critical_avail(
    stock_master_df: pd.DataFrame,
    blocked: bool = False,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []
    if blocked:
        gaps.append("CRITICAL_AVAIL: critical_flag not available (G-01) — showing 'Data not available'")
        return DATA_NOT_AVAILABLE, gaps

    if "critical_flag" not in stock_master_df.columns:
        gaps.append("CRITICAL_AVAIL: critical_flag column absent (G-01)")
        return DATA_NOT_AVAILABLE, gaps

    critical = stock_master_df[stock_master_df["critical_flag"] == True]
    total_critical = len(critical)
    if total_critical == 0:
        gaps.append("CRITICAL_AVAIL: no materials flagged as critical")
        return DATA_NOT_AVAILABLE, gaps

    stock_col = "unrestricted_stock" if "unrestricted_stock" in critical.columns else None
    if stock_col is None:
        gaps.append("CRITICAL_AVAIL: unrestricted_stock column absent")
        return DATA_NOT_AVAILABLE, gaps

    with_stock = int((critical[stock_col].fillna(0) > 0).sum())
    return round((with_stock / total_critical) * 100, 2), gaps


# ---------------------------------------------------------------------------
# 12. Demand Forecast — ContextFlow MCP (not computed here)
#     Placeholder that returns DATA_NOT_AVAILABLE with a clear gap message.
# ---------------------------------------------------------------------------

def compute_demand_forecast_placeholder(
    material_code: str,
    plant: str,
    blocked: bool = True,
) -> tuple[Optional[dict], list[str]]:
    gaps: list[str] = []
    if blocked:
        gaps.append(
            f"DEMAND_FORECAST: ContextFlow MCP not configured (G-05) — "
            f"showing 'Data not available' for {material_code}/{plant}"
        )
    return DATA_NOT_AVAILABLE, gaps


# ---------------------------------------------------------------------------
# 13. Forecast Accuracy (MAPE-based)
#     FORECAST_ACCURACY = 100 − (1/n) × Σ|A−F|/A × 100
# ---------------------------------------------------------------------------

def compute_forecast_accuracy(
    actuals: list[float],
    forecasts: list[float],
    blocked: bool = False,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []
    if blocked:
        gaps.append("FORECAST_ACCURACY: historical forecasts not available (G-06)")
        return DATA_NOT_AVAILABLE, gaps
    if not actuals or not forecasts:
        gaps.append("FORECAST_ACCURACY: actuals or forecasts list is empty")
        return DATA_NOT_AVAILABLE, gaps
    if len(actuals) != len(forecasts):
        gaps.append("FORECAST_ACCURACY: actuals and forecasts length mismatch")
        return DATA_NOT_AVAILABLE, gaps

    pairs = [(a, f) for a, f in zip(actuals, forecasts) if a != 0]
    if not pairs:
        gaps.append("FORECAST_ACCURACY: all actuals are zero — MAPE undefined")
        return DATA_NOT_AVAILABLE, gaps

    mape = np.mean([abs(a - f) / abs(a) for a, f in pairs]) * 100
    return round(100.0 - mape, 2), gaps


# ---------------------------------------------------------------------------
# 14. Forecast Bias
#     FORECAST_BIAS = Σ(F−A) / Σ(A) × 100
# ---------------------------------------------------------------------------

def compute_forecast_bias(
    actuals: list[float],
    forecasts: list[float],
    blocked: bool = False,
) -> tuple[Optional[float], list[str]]:
    gaps: list[str] = []
    if blocked:
        gaps.append("FORECAST_BIAS: historical forecasts not available (G-06)")
        return DATA_NOT_AVAILABLE, gaps
    if not actuals or not forecasts:
        gaps.append("FORECAST_BIAS: actuals or forecasts list is empty")
        return DATA_NOT_AVAILABLE, gaps
    if len(actuals) != len(forecasts):
        gaps.append("FORECAST_BIAS: actuals and forecasts length mismatch")
        return DATA_NOT_AVAILABLE, gaps

    sum_actuals = sum(actuals)
    if sum_actuals == 0:
        gaps.append("FORECAST_BIAS: sum of actuals = 0 — bias undefined")
        return DATA_NOT_AVAILABLE, gaps

    bias = (sum(f - a for a, f in zip(actuals, forecasts)) / sum_actuals) * 100
    return round(bias, 2), gaps


# ---------------------------------------------------------------------------
# Orchestrator: compute all real-data metrics for one material
# Returns a dict keyed by metric ID (matches data_contract_v1.yaml §3)
# ---------------------------------------------------------------------------

def compute_all_metrics(
    material_code: str,
    plant: str,
    stock_row: pd.Series,
    consumption_df: pd.DataFrame,
    po_df: pd.DataFrame,
    blocked_metrics: dict[str, bool],
    as_of: Optional[date] = None,
    actuals: Optional[list[float]] = None,
    historical_forecasts: Optional[list[float]] = None,
) -> dict[str, Any]:
    """
    Compute all 14 metrics for one (material_code, plant) pair.
    Returns a dict with metric values and a 'data_gaps' list.
    """
    all_gaps: list[str] = []

    stock_on_hand = float(stock_row.get("unrestricted_stock", 0) or 0)
    unit_price = float(stock_row.get("unit_price", 0) or 0)
    price_missing = bool(stock_row.get("price_missing", False))
    lead_time_days = stock_row.get("lead_time_days")
    if lead_time_days is not None:
        try:
            lead_time_days = float(lead_time_days)
        except (TypeError, ValueError):
            lead_time_days = None
    critical_flag = bool(stock_row.get("critical_flag", False))

    # 1. DOI
    doi, g = compute_doi(stock_on_hand, consumption_df, as_of)
    all_gaps.extend(g)

    # 2. INV_VALUE
    inv_value, g = compute_inv_value(stock_on_hand, unit_price, price_missing)
    all_gaps.extend(g)

    # 3. INV_TURNOVER
    turnover, g = compute_inv_turnover(
        consumption_df, unit_price, stock_on_hand, as_of,
        g03_point_in_time=blocked_metrics.get("G-03", True),
    )
    all_gaps.extend(g)

    # 4. SAFETY_STOCK
    safety_stock, g = compute_safety_stock(consumption_df, lead_time_days, as_of=as_of)
    all_gaps.extend(g)

    # 5. REORDER_POINT
    rop, g = compute_rop(consumption_df, lead_time_days, safety_stock, as_of)
    all_gaps.extend(g)

    # 6. OVERSTOCK_FLAG
    overstock, g = compute_overstock_flag(stock_on_hand, consumption_df, as_of)
    all_gaps.extend(g)

    # 7. UNDERSTOCK_FLAG
    understock, g = compute_understock_flag(stock_on_hand, rop)
    all_gaps.extend(g)

    # 8. NON_MOVING
    nmi, g = compute_nmi_flag(stock_on_hand, consumption_df, as_of)
    all_gaps.extend(g)

    # 9. SLOW_MOVING
    smi, g = compute_smi_flag(doi, nmi)
    all_gaps.extend(g)

    # 10. FILL_RATE
    fill_rate, g = compute_fill_rate(
        fulfilled=None, requested=None,
        blocked=blocked_metrics.get("G-02", True),
    )
    all_gaps.extend(g)

    # 11. CRITICAL_AVAIL — computed at population level, not per-material
    # (see compute_critical_avail above; called from run_pipeline.py)

    # 12. DEMAND_FORECAST
    forecast, g = compute_demand_forecast_placeholder(
        material_code, plant,
        blocked=blocked_metrics.get("G-05", True),
    )
    all_gaps.extend(g)

    # 13. FORECAST_ACCURACY
    acc, g = compute_forecast_accuracy(
        actuals or [], historical_forecasts or [],
        blocked=blocked_metrics.get("G-06", True),
    )
    all_gaps.extend(g)

    # 14. FORECAST_BIAS
    bias, g = compute_forecast_bias(
        actuals or [], historical_forecasts or [],
        blocked=blocked_metrics.get("G-06", True),
    )
    all_gaps.extend(g)

    # Last movement date
    last_movement: Optional[date] = None
    if consumption_df is not None and not consumption_df.empty:
        active = consumption_df[consumption_df["qty"] > 0]
        if not active.empty:
            last_movement = active["posting_date"].max()
            if hasattr(last_movement, "date"):
                last_movement = last_movement.date()

    # Value at risk (NMI/SMI materials)
    value_at_risk = inv_value if (nmi or smi) else None

    return {
        "material_code": material_code,
        "plant": plant,
        "material_type": stock_row.get("material_type"),
        "category": stock_row.get("category"),
        "description": stock_row.get("description"),
        "critical_flag": critical_flag,
        "shutdown_flag": bool(stock_row.get("shutdown_flag", False)),
        "uom": stock_row.get("uom", "EA"),
        # Metrics
        "DOI": doi,
        "INV_VALUE": inv_value,
        "INV_TURNOVER": turnover,
        "SAFETY_STOCK": safety_stock,
        "REORDER_POINT": rop,
        "OVERSTOCK_FLAG": overstock,
        "UNDERSTOCK_FLAG": understock,
        "NON_MOVING": nmi,
        "SLOW_MOVING": smi,
        "FILL_RATE": fill_rate,
        "DEMAND_FORECAST": forecast,
        "FORECAST_ACCURACY": acc,
        "FORECAST_BIAS": bias,
        # Supporting fields
        "stock_on_hand": stock_on_hand,
        "unit_price": unit_price,
        "price_missing": price_missing,
        "lead_time_days": lead_time_days,
        "last_movement_date": last_movement,
        "value_at_risk": value_at_risk,
        "data_gaps": list(dict.fromkeys(all_gaps)),  # deduplicate, preserve order
    }
