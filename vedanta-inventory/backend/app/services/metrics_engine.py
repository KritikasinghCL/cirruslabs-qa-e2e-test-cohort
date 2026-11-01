"""
Metrics Engine — Vedanta Inventory Forecasting Dashboard
Implements all 12 KPI formulas exactly as specified.
Real-data metrics are computed here; forecast-dependent metrics
are wired in after ContextFlow returns its payload.

NO hardcoded data. If inputs are missing, the metric is None
and a gap entry is appended to data_gaps.
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.core.config import settings
from app.models.schemas import (
    ConsumptionRecord, StockMasterRecord, PORecord,
    ForecastResponse, MaterialMetrics,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: build per-material DataFrames
# ---------------------------------------------------------------------------

def _consumption_df(records: List[ConsumptionRecord]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["material_code", "plant", "posting_date", "qty"])
    df = pd.DataFrame([r.model_dump() for r in records])
    df["posting_date"] = pd.to_datetime(df["posting_date"])
    return df


def _po_df(records: List[PORecord]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["material_code", "plant", "pr_date", "approval_date", "arrival_date", "qty_ordered", "unit_price"])
    df = pd.DataFrame([r.model_dump() for r in records])
    for col in ["pr_date", "approval_date", "arrival_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _consumption_stats_90d(
    records: List[ConsumptionRecord],
) -> Tuple[Optional[float], Optional[float]]:
    """
    Returns (avg_daily_cons_90d, stddev_daily_cons_90d) over the last 90 calendar days.
    Builds a daily series (zero-filling days with no consumption) so σ reflects
    the true variability including zero-demand days.
    Returns (None, None) if there are no records at all.
    """
    if not records:
        return None, None
    df = _consumption_df(records)
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=90)
    today = pd.Timestamp.now().normalize()
    df_90 = df[df["posting_date"] >= cutoff].copy()

    # Build a complete daily index for the 90-day window
    all_days = pd.date_range(start=cutoff, end=today, freq="D")
    daily = df_90.groupby(df_90["posting_date"].dt.normalize())["qty"].sum()
    daily = daily.reindex(all_days, fill_value=0.0)

    avg = float(daily.mean())
    std = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    return round(avg, 6), round(std, 6)


# ---------------------------------------------------------------------------
# 1. Days of Inventory (DOH)
# DOH = Current Stock ÷ Average Daily Usage
# ---------------------------------------------------------------------------

def compute_doh(
    current_stock: float,
    consumption_records: List[ConsumptionRecord],
    lookback_days: int = 365,
) -> Tuple[Optional[float], List[str]]:
    gaps: List[str] = []
    if not consumption_records:
        gaps.append("consumption_history: no records — DOH cannot be computed")
        return None, gaps
    df = _consumption_df(consumption_records)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
    df = df[df["posting_date"] >= cutoff]
    if df.empty:
        gaps.append(f"consumption_history: no records in last {lookback_days} days — DOH cannot be computed")
        return None, gaps
    total_qty = df["qty"].sum()
    avg_daily = total_qty / lookback_days
    if avg_daily == 0:
        return None, ["average_daily_usage = 0 — DOH is undefined (non-moving material)"]
    return round(current_stock / avg_daily, 2), gaps


# ---------------------------------------------------------------------------
# 2. Inventory Turnover
# = Total Consumption Value ÷ Average Inventory Value
# ---------------------------------------------------------------------------

def compute_inventory_turnover(
    consumption_records: List[ConsumptionRecord],
    unit_price: float,
    current_stock: float,
    lookback_days: int = 365,
) -> Tuple[Optional[float], List[str]]:
    gaps: List[str] = []
    if not consumption_records:
        gaps.append("consumption_history: no records — Inventory Turnover cannot be computed")
        return None, gaps
    df = _consumption_df(consumption_records)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
    df = df[df["posting_date"] >= cutoff]
    total_consumption_value = df["qty"].sum() * unit_price
    avg_inventory_value = current_stock * unit_price
    if avg_inventory_value == 0:
        gaps.append("average_inventory_value = 0 — Inventory Turnover undefined")
        return None, gaps
    return round(total_consumption_value / avg_inventory_value, 4), gaps


# ---------------------------------------------------------------------------
# 3. Non-Moving Inventory (NMI) Flag
# Data contract v1.0.0 §3.8:
#   NON_MOVING = TRUE if no consumption in last 365 days AND stock_on_hand > 0
# ---------------------------------------------------------------------------

def compute_nmi_flag(
    consumption_records: List[ConsumptionRecord],
    current_stock: float = 0.0,
    lookback_days: int = 365,
) -> Tuple[Optional[bool], List[str]]:
    gaps: List[str] = []
    # Nothing to flag when there is no stock on hand
    if current_stock <= 0:
        return False, gaps
    if not consumption_records:
        gaps.append("consumption_history: no records — NMI flag defaults to True (non-moving)")
        return True, gaps
    df = _consumption_df(consumption_records)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
    recent = df[df["posting_date"] >= cutoff]
    total_qty = recent["qty"].sum()
    return bool(total_qty == 0), gaps


# ---------------------------------------------------------------------------
# 4. Slow-Moving Inventory (SMI) Flag
# Data contract v1.0.0 §3.9:
#   SLOW_MOVING = TRUE if DOI > doi_threshold_days (default 90) AND NOT NON_MOVING
# ---------------------------------------------------------------------------

def compute_smi_flag(
    doi: Optional[float],
    nmi_flag: Optional[bool],
    doi_threshold_days: float = 90.0,
) -> Tuple[Optional[bool], List[str]]:
    gaps: List[str] = []
    if doi is None:
        gaps.append("DOI not available — SMI flag cannot be computed")
        return None, gaps
    # A non-moving material is NOT also slow-moving (mutually exclusive per contract)
    if nmi_flag:
        return False, gaps
    return doi > doi_threshold_days, gaps


# ---------------------------------------------------------------------------
# 5. Fill Rate
# = (Demand Met from Stock ÷ Total Demand) × 100%
# Demand Met = min(current_stock_at_time, demand); requires order-level data
# ---------------------------------------------------------------------------

def compute_fill_rate(
    demand_met: Optional[float],
    total_demand: Optional[float],
) -> Tuple[Optional[float], List[str]]:
    gaps: List[str] = []
    if demand_met is None or total_demand is None:
        gaps.append("demand_met / total_demand not available — Fill Rate cannot be computed")
        return None, gaps
    if total_demand == 0:
        gaps.append("total_demand = 0 — Fill Rate undefined")
        return None, gaps
    return round((demand_met / total_demand) * 100, 2), gaps


# ---------------------------------------------------------------------------
# 6. Critical Spares Availability
# = (Days in Stock ÷ Total Days) × 100%
# Days in Stock = days where current_stock > 0 (requires daily stock snapshot)
# ---------------------------------------------------------------------------

def compute_critical_spares_availability(
    days_in_stock: Optional[int],
    total_days: Optional[int],
) -> Tuple[Optional[float], List[str]]:
    gaps: List[str] = []
    if days_in_stock is None or total_days is None:
        gaps.append("daily_stock_snapshot not available — Critical Spares Availability cannot be computed")
        return None, gaps
    if total_days == 0:
        gaps.append("total_days = 0 — availability undefined")
        return None, gaps
    return round((days_in_stock / total_days) * 100, 2), gaps


# ---------------------------------------------------------------------------
# 7. Safety Stock  [FORECAST-DEPENDENT — requires ContextFlow lead-time output]
# Data contract §3.4:
#   SAFETY_STOCK = Z_score(service_level) × STDDEV_DAILY_CONS × SQRT(LEAD_TIME_DAYS)
#   where:
#     service_level    = 95% default (Z = 1.645); configurable per material class
#     STDDEV_DAILY_CONS = STDDEV of daily consumption over last 90 days
#     LEAD_TIME_DAYS   = MARC.PLIFZ + MARC.WEBAZ (from SAP / ContextFlow)
#   Fallback: use MARC.EISBE (SAP-maintained safety stock) if formula inputs missing
# ---------------------------------------------------------------------------

SAFETY_STOCK_Z_95 = 1.645  # Z-score for 95% service level


def compute_safety_stock(
    stddev_daily_cons: Optional[float],
    lead_time_days: Optional[float],
    z_score: float = SAFETY_STOCK_Z_95,
) -> Tuple[Optional[float], List[str]]:
    gaps: List[str] = []
    missing = []
    if stddev_daily_cons is None:
        missing.append("stddev_daily_cons (90-day σ of daily consumption)")
    if lead_time_days is None:
        missing.append("lead_time_days (MARC.PLIFZ + MARC.WEBAZ)")
    if missing:
        gaps.append(f"Safety Stock blocked — missing: {missing} (requires consumption history + lead time)")
        return None, gaps
    ss = z_score * stddev_daily_cons * (lead_time_days ** 0.5)
    return max(0.0, round(ss, 2)), gaps


# ---------------------------------------------------------------------------
# 8. Reorder Point (ROP)  [REQUIRES lead time + safety stock]
# Data contract §3.5:
#   REORDER_POINT = (AVG_DAILY_CONS_90D × LEAD_TIME_DAYS) + SAFETY_STOCK
#   Fallback: use MARC.MINBE (SAP-maintained reorder point) if formula inputs missing
# ---------------------------------------------------------------------------

def compute_rop(
    avg_daily_usage: Optional[float],
    avg_lead_time_days: Optional[float],
    safety_stock: Optional[float],
) -> Tuple[Optional[float], List[str]]:
    gaps: List[str] = []
    if avg_daily_usage is None or avg_lead_time_days is None or safety_stock is None:
        gaps.append("ROP blocked — requires avg_daily_usage, avg_lead_time_days, safety_stock")
        return None, gaps
    return round((avg_daily_usage * avg_lead_time_days) + safety_stock, 2), gaps


# ---------------------------------------------------------------------------
# 9. Overstock Flag
# Data contract §3.6:
#   OVERSTOCK_FLAG = TRUE IF STOCK_ON_HAND > (AVG_DAILY_CONS_90D × OVERSTOCK_THRESHOLD_DAYS)
#   where OVERSTOCK_THRESHOLD_DAYS = 180 (configurable)
# This is consumption-based — does NOT require ContextFlow forecast.
# ---------------------------------------------------------------------------

OVERSTOCK_THRESHOLD_DAYS = 180  # configurable; matches data contract default


def compute_overstock_flag(
    current_stock: float,
    avg_daily_cons_90d: Optional[float],
    overstock_threshold_days: float = OVERSTOCK_THRESHOLD_DAYS,
) -> Tuple[Optional[bool], List[str]]:
    gaps: List[str] = []
    if avg_daily_cons_90d is None:
        gaps.append(
            "Overstock flag blocked — avg_daily_cons_90d not available "
            "(requires 90-day consumption history)"
        )
        return None, gaps
    if avg_daily_cons_90d == 0:
        # Zero consumption → stock is effectively infinite days of supply → overstock
        return True, gaps
    threshold = avg_daily_cons_90d * overstock_threshold_days
    return current_stock > threshold, gaps


# ---------------------------------------------------------------------------
# 10. Understock Flag  [REQUIRES ROP]
# = Current Stock < ROP
# ---------------------------------------------------------------------------

def compute_understock_flag(
    current_stock: float,
    rop: Optional[float],
) -> Tuple[Optional[bool], List[str]]:
    gaps: List[str] = []
    if rop is None:
        gaps.append("Understock flag blocked — requires ROP (ContextFlow)")
        return None, gaps
    return current_stock < rop, gaps


# ---------------------------------------------------------------------------
# 11. Forecast Accuracy %  [POST-ACTUALS ONLY]
# = 100% − MAPE, where MAPE = avg(|Actual−Forecast| ÷ Actual) × 100%
# ---------------------------------------------------------------------------

def compute_forecast_accuracy(
    actuals: List[float],
    forecasts: List[float],
) -> Tuple[Optional[float], List[str]]:
    gaps: List[str] = []
    if not actuals or not forecasts:
        gaps.append("Forecast Accuracy: actuals not yet available — post-actuals metric")
        return None, gaps
    if len(actuals) != len(forecasts):
        gaps.append("Forecast Accuracy: actuals and forecasts length mismatch")
        return None, gaps
    pairs = [(a, f) for a, f in zip(actuals, forecasts) if a != 0]
    if not pairs:
        gaps.append("Forecast Accuracy: all actuals are zero — MAPE undefined")
        return None, gaps
    mape = np.mean([abs(a - f) / a for a, f in pairs]) * 100
    return round(100 - mape, 2), gaps


# ---------------------------------------------------------------------------
# 12. Forecast Bias  [POST-ACTUALS ONLY]
# = avg((Forecast − Actual) ÷ Actual) × 100%
# ---------------------------------------------------------------------------

def compute_forecast_bias(
    actuals: List[float],
    forecasts: List[float],
) -> Tuple[Optional[float], List[str]]:
    gaps: List[str] = []
    if not actuals or not forecasts:
        gaps.append("Forecast Bias: actuals not yet available — post-actuals metric")
        return None, gaps
    if len(actuals) != len(forecasts):
        gaps.append("Forecast Bias: actuals and forecasts length mismatch")
        return None, gaps
    pairs = [(a, f) for a, f in zip(actuals, forecasts) if a != 0]
    if not pairs:
        gaps.append("Forecast Bias: all actuals are zero — bias undefined")
        return None, gaps
    bias = np.mean([(f - a) / a for a, f in pairs]) * 100
    return round(bias, 2), gaps


# ---------------------------------------------------------------------------
# Orchestrator: compute all real-data metrics for one material
# ---------------------------------------------------------------------------

def compute_real_data_metrics(
    stock: StockMasterRecord,
    consumption_records: List[ConsumptionRecord],
    po_records: List[PORecord],
    demand_met: Optional[float] = None,
    total_demand: Optional[float] = None,
    days_in_stock: Optional[int] = None,
    total_days: Optional[int] = None,
) -> MaterialMetrics:
    """Compute all metrics that do NOT require ContextFlow forecast."""
    gaps: List[str] = []

    # DOH
    doh, g = compute_doh(stock.current_stock, consumption_records)
    gaps.extend(g)

    # Inventory value
    inv_value = round(stock.current_stock * stock.unit_price, 2)

    # Inventory turnover
    turnover, g = compute_inventory_turnover(consumption_records, stock.unit_price, stock.current_stock)
    gaps.extend(g)

    # NMI — 365-day lookback, requires stock > 0 (contract §3.8)
    nmi, g = compute_nmi_flag(consumption_records, current_stock=stock.current_stock)
    gaps.extend(g)

    # SMI — DOI > 90d AND NOT non-moving (contract §3.9)
    smi, g = compute_smi_flag(doi=doh, nmi_flag=nmi)
    gaps.extend(g)

    # Fill rate
    fill_rate, g = compute_fill_rate(demand_met, total_demand)
    gaps.extend(g)

    # Critical spares availability
    csa, g = compute_critical_spares_availability(days_in_stock, total_days)
    gaps.extend(g)

    # 90-day consumption stats (used for Overstock and Safety Stock)
    avg_daily_90d, _stddev_daily_90d = _consumption_stats_90d(consumption_records)

    # Overstock — consumption-based per data contract §3.6
    # STOCK > AVG_DAILY_CONS_90D × 180d
    overstock, g = compute_overstock_flag(stock.current_stock, avg_daily_90d)
    gaps.extend(g)

    # Last movement date
    df_c = _consumption_df(consumption_records)
    last_movement: Optional[date] = None
    if not df_c.empty:
        active = df_c[df_c["qty"] > 0]
        if not active.empty:
            last_movement = active["posting_date"].max().date()

    # Value at risk (for NMI/SMI)
    value_at_risk = inv_value if (nmi or smi) else None

    return MaterialMetrics(
        material_code=stock.material_code,
        plant=stock.plant,
        material_type=stock.material_type,
        category=stock.category,
        critical_flag=stock.critical_flag,
        shutdown_flag=stock.shutdown_flag,
        days_of_inventory=doh,
        inventory_value=inv_value,
        inventory_turnover=turnover,
        non_moving_flag=nmi,
        slow_moving_flag=smi,
        fill_rate_pct=fill_rate,
        critical_spares_availability_pct=csa,
        last_movement_date=last_movement,
        value_at_risk=value_at_risk,
        overstock_flag=overstock,
        # Understock requires ROP which requires lead time — computed in wire_forecast_into_metrics
        data_gaps=gaps,
    )


def wire_forecast_into_metrics(
    metrics: MaterialMetrics,
    forecast_response: ForecastResponse,
    current_stock: float,
    consumption_records: Optional[List[ConsumptionRecord]] = None,
    actuals: Optional[List[float]] = None,
    historical_forecasts: Optional[List[float]] = None,
) -> MaterialMetrics:
    """
    Wire ContextFlow forecast output into a MaterialMetrics object.

    ContextFlow provides: avg_daily_usage, max_daily_usage, avg_lead_time_days,
    max_lead_time_days, and per-horizon forecast_qty.

    Safety Stock uses the Z×σ×√LT formula (data contract §3.4):
      - σ (stddev_daily_cons) is computed from the last 90 days of consumption history
      - LT comes from ContextFlow avg_lead_time_days
    ROP = (AVG_DAILY_CONS_90D × LT) + SS  (data contract §3.5)
    Understock = STOCK < ROP  (data contract §3.7)
    """
    gaps = list(metrics.data_gaps)

    f3 = next((f.forecast_qty for f in forecast_response.forecasts if f.horizon_months == 3), None)
    f6 = next((f.forecast_qty for f in forecast_response.forecasts if f.horizon_months == 6), None)
    f12 = next((f.forecast_qty for f in forecast_response.forecasts if f.horizon_months == 12), None)

    # 90-day stats for SS and ROP
    avg_daily_90d: Optional[float] = None
    stddev_daily_90d: Optional[float] = None
    if consumption_records is not None:
        avg_daily_90d, stddev_daily_90d = _consumption_stats_90d(consumption_records)

    # Safety Stock: Z × σ_daily × √LT  (data contract §3.4)
    # σ from 90-day consumption; LT from ContextFlow
    lt = forecast_response.avg_lead_time_days if forecast_response.avg_lead_time_days is not None else None
    ss, g = compute_safety_stock(stddev_daily_90d, lt)
    gaps.extend(g)

    # ROP: AVG_DAILY_CONS_90D × LT + SS  (data contract §3.5)
    rop, g = compute_rop(avg_daily_90d, lt, ss)
    gaps.extend(g)

    # Understock: STOCK < ROP  (data contract §3.7)
    understock, g = compute_understock_flag(current_stock, rop)
    gaps.extend(g)

    # Forecast-enhanced overstock: STOCK > (3mo_forecast + SS) × OVERSTOCK_MARGIN_FACTOR
    # Supersedes the consumption-based flag when ContextFlow data is available.
    # Data contract §3.6 baseline (consumption-based) is preserved as fallback.
    if f3 is not None and ss is not None:
        forecast_overstock_threshold = (f3 + ss) * settings.OVERSTOCK_MARGIN_FACTOR
        metrics.overstock_flag = current_stock > forecast_overstock_threshold

    # Recommended action
    action: Optional[str] = None
    if metrics.overstock_flag:
        action = "Reduce order / defer next PR"
    elif understock:
        action = "Raise PR immediately"
    elif rop is not None and ss is not None:
        action = "Monitor — within normal range"

    # Post-actuals: Forecast Accuracy and Bias
    # These require historical ContextFlow forecasts vs actual consumption.
    # Gap G-06: only available after first full forecast cycle.
    acc, g = compute_forecast_accuracy(actuals or [], historical_forecasts or [])
    gaps.extend(g)
    bias, g = compute_forecast_bias(actuals or [], historical_forecasts or [])
    gaps.extend(g)

    metrics.safety_stock = ss
    metrics.reorder_point = rop
    metrics.understock_flag = understock
    metrics.forecast_3mo = f3
    metrics.forecast_6mo = f6
    metrics.forecast_12mo = f12
    metrics.recommended_action = action
    metrics.forecast_accuracy_pct = acc
    metrics.forecast_bias_pct = bias
    metrics.data_gaps = gaps
    return metrics
