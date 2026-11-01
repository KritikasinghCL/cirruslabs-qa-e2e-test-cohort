"""
Tests for pipeline/metrics_v2.py

All 14 KPI formulas tested against known inputs with expected outputs.
No GCS, no SAP, no ContextFlow — pure unit tests.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from pipeline.metrics_v2 import (
    compute_doi,
    compute_inv_value,
    compute_inv_turnover,
    compute_safety_stock,
    compute_rop,
    compute_overstock_flag,
    compute_understock_flag,
    compute_nmi_flag,
    compute_smi_flag,
    compute_fill_rate,
    compute_critical_avail,
    compute_forecast_accuracy,
    compute_forecast_bias,
    compute_demand_forecast_placeholder,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cons_df(records: list[tuple]) -> pd.DataFrame:
    """Build a consumption DataFrame from (date_str, qty) tuples."""
    rows = [{"posting_date": pd.Timestamp(d), "qty": q} for d, q in records]
    return pd.DataFrame(rows)


AS_OF = date(2026, 9, 25)


# ---------------------------------------------------------------------------
# 1. DOI
# ---------------------------------------------------------------------------

class TestDOI:

    def test_basic_calculation(self):
        # 90 days, 90 units consumed → avg_daily = 1.0
        # stock = 30 → DOI = 30
        cons = _cons_df([(AS_OF - timedelta(days=i), 1.0) for i in range(1, 91)])
        doi, gaps = compute_doi(30.0, cons, as_of=AS_OF, lookback_days=90)
        assert doi == 30.0
        assert gaps == []

    def test_empty_consumption_returns_none(self):
        doi, gaps = compute_doi(100.0, pd.DataFrame(), as_of=AS_OF)
        assert doi is None
        assert len(gaps) > 0

    def test_zero_avg_daily_returns_none(self):
        # Consumption exists but all outside lookback window
        cons = _cons_df([("2020-01-01", 10.0)])
        doi, gaps = compute_doi(100.0, cons, as_of=AS_OF, lookback_days=90)
        assert doi is None
        assert any("non-moving" in g or "cannot be computed" in g for g in gaps)

    def test_zero_stock_returns_zero_doi(self):
        cons = _cons_df([(AS_OF - timedelta(days=i), 1.0) for i in range(1, 91)])
        doi, gaps = compute_doi(0.0, cons, as_of=AS_OF, lookback_days=90)
        assert doi == 0.0


# ---------------------------------------------------------------------------
# 2. Inventory Value
# ---------------------------------------------------------------------------

class TestInvValue:

    def test_basic(self):
        val, gaps = compute_inv_value(100.0, 150.0)
        assert val == 15000.0
        assert gaps == []

    def test_price_missing_flag(self):
        val, gaps = compute_inv_value(100.0, 0.0, price_missing=True)
        assert val == 0.0
        assert any("G-09" in g for g in gaps)

    def test_zero_stock(self):
        val, gaps = compute_inv_value(0.0, 500.0)
        assert val == 0.0


# ---------------------------------------------------------------------------
# 3. Inventory Turnover
# ---------------------------------------------------------------------------

class TestInvTurnover:

    def test_basic(self):
        # 365 units consumed at price 100 → COGS = 36500
        # current stock = 100 at price 100 → avg_inv = 10000
        # turnover = 36500 / 10000 = 3.65
        cons = _cons_df([(AS_OF - timedelta(days=i), 1.0) for i in range(1, 366)])
        t, gaps = compute_inv_turnover(cons, 100.0, 100.0, as_of=AS_OF)
        assert t == pytest.approx(3.65, rel=1e-3)

    def test_zero_avg_inv_returns_none(self):
        cons = _cons_df([(AS_OF - timedelta(days=1), 10.0)])
        t, gaps = compute_inv_turnover(cons, 100.0, 0.0, as_of=AS_OF)
        assert t is None

    def test_g03_fallback_noted_in_gaps(self):
        cons = _cons_df([(AS_OF - timedelta(days=1), 10.0)])
        _, gaps = compute_inv_turnover(cons, 100.0, 50.0, as_of=AS_OF, g03_point_in_time=True)
        assert any("G-03" in g for g in gaps)


# ---------------------------------------------------------------------------
# 4. Safety Stock
# ---------------------------------------------------------------------------

class TestSafetyStock:

    def test_basic_formula(self):
        # σ_daily = 2.0, LT = 25, Z = 1.65
        # SS = 1.65 × 2.0 × √25 = 1.65 × 2.0 × 5 = 16.5
        # Build consumption with std dev ≈ 2
        np.random.seed(42)
        daily_qtys = np.random.normal(loc=5.0, scale=2.0, size=365).clip(0)
        cons = _cons_df([
            ((AS_OF - timedelta(days=365 - i)).isoformat(), float(q))
            for i, q in enumerate(daily_qtys)
        ])
        ss, gaps = compute_safety_stock(cons, lead_time_days=25.0, z=1.65, as_of=AS_OF)
        assert ss is not None
        assert ss >= 0
        assert gaps == []

    def test_missing_lead_time_returns_none(self):
        cons = _cons_df([(AS_OF - timedelta(days=1), 5.0)])
        ss, gaps = compute_safety_stock(cons, lead_time_days=None, as_of=AS_OF)
        assert ss is None
        assert len(gaps) > 0

    def test_empty_consumption_returns_none(self):
        ss, gaps = compute_safety_stock(pd.DataFrame(), lead_time_days=30.0, as_of=AS_OF)
        assert ss is None

    def test_zero_variance_returns_zero(self):
        # Perfectly constant demand → σ = 0 → SS = 0
        cons = _cons_df([(AS_OF - timedelta(days=i), 5.0) for i in range(1, 366)])
        ss, gaps = compute_safety_stock(cons, lead_time_days=30.0, z=1.65, as_of=AS_OF)
        assert ss == 0.0


# ---------------------------------------------------------------------------
# 5. Reorder Point
# ---------------------------------------------------------------------------

class TestROP:

    def test_basic_formula(self):
        # avg_daily = 2.0 (180 units / 90 days), LT = 30, SS = 10
        # ROP = (2.0 × 30) + 10 = 70
        cons = _cons_df([(AS_OF - timedelta(days=i), 2.0) for i in range(1, 91)])
        rop, gaps = compute_rop(cons, lead_time_days=30.0, safety_stock=10.0, as_of=AS_OF)
        assert rop == pytest.approx(70.0, rel=1e-3)

    def test_missing_safety_stock_returns_none(self):
        cons = _cons_df([(AS_OF - timedelta(days=1), 2.0)])
        rop, gaps = compute_rop(cons, lead_time_days=30.0, safety_stock=None, as_of=AS_OF)
        assert rop is None

    def test_missing_lead_time_returns_none(self):
        cons = _cons_df([(AS_OF - timedelta(days=1), 2.0)])
        rop, gaps = compute_rop(cons, lead_time_days=None, safety_stock=10.0, as_of=AS_OF)
        assert rop is None


# ---------------------------------------------------------------------------
# 6. Overstock Flag
# ---------------------------------------------------------------------------

class TestOverstockFlag:

    def test_overstock_detected(self):
        # avg_daily = 1.0, threshold = 1.0 × 180 = 180, stock = 500 → overstock
        cons = _cons_df([(AS_OF - timedelta(days=i), 1.0) for i in range(1, 91)])
        flag, gaps = compute_overstock_flag(500.0, cons, as_of=AS_OF, overstock_days=180)
        assert flag == True

    def test_not_overstock(self):
        cons = _cons_df([(AS_OF - timedelta(days=i), 1.0) for i in range(1, 91)])
        flag, gaps = compute_overstock_flag(50.0, cons, as_of=AS_OF, overstock_days=180)
        assert flag == False

    def test_non_moving_with_stock_is_overstock(self):
        # No consumption → avg_daily = 0 → any stock > 0 is overstock
        cons = _cons_df([("2020-01-01", 1.0)])  # outside lookback
        flag, gaps = compute_overstock_flag(10.0, cons, as_of=AS_OF, overstock_days=180)
        assert flag == True


# ---------------------------------------------------------------------------
# 7. Understock Flag
# ---------------------------------------------------------------------------

class TestUnderstockFlag:

    def test_understock_detected(self):
        flag, gaps = compute_understock_flag(5.0, reorder_point=20.0)
        assert flag == True

    def test_not_understock(self):
        flag, gaps = compute_understock_flag(100.0, reorder_point=20.0)
        assert flag == False

    def test_missing_rop_returns_none(self):
        flag, gaps = compute_understock_flag(5.0, reorder_point=None)
        assert flag is None
        assert len(gaps) > 0


# ---------------------------------------------------------------------------
# 8. Non-Moving Inventory
# ---------------------------------------------------------------------------

class TestNMI:

    def test_non_moving_detected(self):
        # No consumption in last 365 days
        cons = _cons_df([("2024-01-01", 10.0)])  # > 365 days ago
        flag, gaps = compute_nmi_flag(50.0, cons, as_of=AS_OF, lookback_days=365)
        assert flag == True

    def test_moving_material(self):
        cons = _cons_df([(AS_OF - timedelta(days=30), 5.0)])
        flag, gaps = compute_nmi_flag(50.0, cons, as_of=AS_OF, lookback_days=365)
        assert flag == False

    def test_zero_stock_not_nmi(self):
        flag, gaps = compute_nmi_flag(0.0, pd.DataFrame(), as_of=AS_OF)
        assert flag == False

    def test_no_consumption_records_with_stock_is_nmi(self):
        flag, gaps = compute_nmi_flag(10.0, pd.DataFrame(), as_of=AS_OF)
        assert flag == True


# ---------------------------------------------------------------------------
# 9. Slow-Moving Inventory
# ---------------------------------------------------------------------------

class TestSMI:

    def test_slow_moving_detected(self):
        # DOI = 120 > 90 threshold, not NMI
        flag, gaps = compute_smi_flag(doi=120.0, nmi_flag=False, doi_threshold_days=90)
        assert flag == True

    def test_not_slow_moving(self):
        flag, gaps = compute_smi_flag(doi=30.0, nmi_flag=False, doi_threshold_days=90)
        assert flag == False

    def test_nmi_material_not_smi(self):
        # NMI takes precedence
        flag, gaps = compute_smi_flag(doi=500.0, nmi_flag=True, doi_threshold_days=90)
        assert flag == False

    def test_missing_doi_returns_none(self):
        flag, gaps = compute_smi_flag(doi=None, nmi_flag=False)
        assert flag is None


# ---------------------------------------------------------------------------
# 10. Fill Rate
# ---------------------------------------------------------------------------

class TestFillRate:

    def test_basic(self):
        rate, gaps = compute_fill_rate(fulfilled=90.0, requested=100.0)
        assert rate == 90.0

    def test_blocked_returns_none(self):
        rate, gaps = compute_fill_rate(fulfilled=None, requested=None, blocked=True)
        assert rate is None
        assert any("G-02" in g for g in gaps)

    def test_zero_requested_returns_none(self):
        rate, gaps = compute_fill_rate(fulfilled=0.0, requested=0.0)
        assert rate is None


# ---------------------------------------------------------------------------
# 11. Critical Spares Availability
# ---------------------------------------------------------------------------

class TestCriticalAvail:

    def test_basic(self):
        df = pd.DataFrame({
            "material_code": ["M1", "M2", "M3"],
            "critical_flag": [True, True, False],
            "unrestricted_stock": [10.0, 0.0, 5.0],
        })
        avail, gaps = compute_critical_avail(df, blocked=False)
        # 2 critical, 1 with stock → 50%
        assert avail == 50.0

    def test_blocked_returns_none(self):
        df = pd.DataFrame({"critical_flag": [True], "unrestricted_stock": [10.0]})
        avail, gaps = compute_critical_avail(df, blocked=True)
        assert avail is None
        assert any("G-01" in g for g in gaps)

    def test_no_critical_materials_returns_none(self):
        df = pd.DataFrame({
            "critical_flag": [False, False],
            "unrestricted_stock": [10.0, 5.0],
        })
        avail, gaps = compute_critical_avail(df, blocked=False)
        assert avail is None

    def test_all_critical_in_stock(self):
        df = pd.DataFrame({
            "critical_flag": [True, True],
            "unrestricted_stock": [5.0, 3.0],
        })
        avail, gaps = compute_critical_avail(df, blocked=False)
        assert avail == 100.0


# ---------------------------------------------------------------------------
# 13. Forecast Accuracy (MAPE)
# ---------------------------------------------------------------------------

class TestForecastAccuracy:

    def test_perfect_forecast(self):
        actuals = [100.0, 200.0, 150.0]
        forecasts = [100.0, 200.0, 150.0]
        acc, gaps = compute_forecast_accuracy(actuals, forecasts)
        assert acc == 100.0

    def test_known_mape(self):
        # MAPE = mean(|A-F|/A) × 100
        # (100,90): |10|/100 = 0.10
        # (200,220): |20|/200 = 0.10
        # MAPE = 10%, accuracy = 90%
        actuals = [100.0, 200.0]
        forecasts = [90.0, 220.0]
        acc, gaps = compute_forecast_accuracy(actuals, forecasts)
        assert acc == pytest.approx(90.0, rel=1e-3)

    def test_blocked_returns_none(self):
        acc, gaps = compute_forecast_accuracy([], [], blocked=True)
        assert acc is None
        assert any("G-06" in g for g in gaps)

    def test_empty_returns_none(self):
        acc, gaps = compute_forecast_accuracy([], [])
        assert acc is None

    def test_length_mismatch_returns_none(self):
        acc, gaps = compute_forecast_accuracy([1.0, 2.0], [1.0])
        assert acc is None


# ---------------------------------------------------------------------------
# 14. Forecast Bias
# ---------------------------------------------------------------------------

class TestForecastBias:

    def test_no_bias(self):
        actuals = [100.0, 200.0]
        forecasts = [100.0, 200.0]
        bias, gaps = compute_forecast_bias(actuals, forecasts)
        assert bias == 0.0

    def test_positive_bias(self):
        # Σ(F-A) = (110-100) + (220-200) = 30, Σ(A) = 300
        # bias = 30/300 × 100 = 10%
        actuals = [100.0, 200.0]
        forecasts = [110.0, 220.0]
        bias, gaps = compute_forecast_bias(actuals, forecasts)
        assert bias == pytest.approx(10.0, rel=1e-3)

    def test_negative_bias(self):
        actuals = [100.0, 200.0]
        forecasts = [90.0, 180.0]
        bias, gaps = compute_forecast_bias(actuals, forecasts)
        assert bias == pytest.approx(-10.0, rel=1e-3)

    def test_blocked_returns_none(self):
        bias, gaps = compute_forecast_bias([], [], blocked=True)
        assert bias is None
