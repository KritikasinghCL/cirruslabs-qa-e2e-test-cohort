"""
Unit tests for the Vedanta Inventory Metrics Engine.
Uses only fixture data — no live GCS, SAP, or ContextFlow connections.
Run: cd vedanta-inventory/backend && USE_TEST_FIXTURES=true pytest tests/ -v
"""
import os
import sys
import pytest
from datetime import date, timedelta

# Ensure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("USE_TEST_FIXTURES", "true")
os.environ.setdefault("FIXTURES_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "fixtures"))

from app.models.schemas import ConsumptionRecord, StockMasterRecord, PORecord
from app.services.metrics_engine import (
    compute_doh,
    compute_inventory_turnover,
    compute_nmi_flag,
    compute_smi_flag,
    compute_fill_rate,
    compute_critical_spares_availability,
    compute_safety_stock,
    compute_rop,
    compute_overstock_flag,
    compute_understock_flag,
    compute_forecast_accuracy,
    compute_forecast_bias,
    _consumption_stats_90d,
    wire_forecast_into_metrics,
    SAFETY_STOCK_Z_95,
    OVERSTOCK_THRESHOLD_DAYS,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_consumption(qty_per_day: float, days: int = 365, material="MAT-001", plant="PL01"):
    today = date.today()
    return [
        ConsumptionRecord(material_code=material, plant=plant, posting_date=today - timedelta(days=i), qty=qty_per_day)
        for i in range(days)
    ]


# ─── DOH ─────────────────────────────────────────────────────────────────────

def test_doh_basic():
    recs = _make_consumption(2.0, 365)
    doh, gaps = compute_doh(730.0, recs, lookback_days=365)
    assert doh == pytest.approx(365.0, rel=0.01)
    assert gaps == []


def test_doh_no_consumption():
    doh, gaps = compute_doh(100.0, [])
    assert doh is None
    assert any("no records" in g for g in gaps)


def test_doh_zero_usage():
    recs = _make_consumption(0.0, 365)
    doh, gaps = compute_doh(100.0, recs)
    assert doh is None
    assert any("non-moving" in g or "undefined" in g for g in gaps)


# ─── Inventory Turnover ───────────────────────────────────────────────────────

def test_inventory_turnover_basic():
    recs = _make_consumption(1.0, 365)
    # Total consumption = 365 units × 100 = 36500; avg inv = 200 × 100 = 20000
    turnover, gaps = compute_inventory_turnover(recs, unit_price=100.0, current_stock=200.0)
    assert turnover == pytest.approx(365 * 100 / (200 * 100), rel=0.01)
    assert gaps == []


def test_inventory_turnover_zero_stock():
    recs = _make_consumption(1.0, 365)
    turnover, gaps = compute_inventory_turnover(recs, unit_price=100.0, current_stock=0.0)
    assert turnover is None
    assert any("undefined" in g for g in gaps)


# ─── NMI ─────────────────────────────────────────────────────────────────────

def test_nmi_flag_true_no_consumption():
    # No records + stock > 0 → non-moving
    flag, gaps = compute_nmi_flag([], current_stock=10.0)
    assert flag is True


def test_nmi_flag_no_stock():
    # Stock = 0 → never non-moving regardless of consumption history
    flag, gaps = compute_nmi_flag([], current_stock=0.0)
    assert flag is False


def test_nmi_flag_false_recent_consumption():
    recs = _make_consumption(1.0, 30)  # consumed in last 30 days
    flag, gaps = compute_nmi_flag(recs, current_stock=50.0, lookback_days=365)
    assert flag == False  # noqa: E712 — numpy.bool_ returned; use == not is


def test_nmi_flag_true_old_consumption():
    # Consumption only 400 days ago — outside 365-day window
    today = date.today()
    old_recs = [
        ConsumptionRecord(material_code="MAT-001", plant="PL01",
                          posting_date=today - timedelta(days=400), qty=5.0)
    ]
    flag, gaps = compute_nmi_flag(old_recs, current_stock=50.0, lookback_days=365)
    assert flag == True  # noqa: E712 — numpy.bool_ returned; use == not is


# ─── SMI ─────────────────────────────────────────────────────────────────────

def test_smi_flag_true_high_doi():
    # DOI > 90d and NOT non-moving → slow-moving
    flag, gaps = compute_smi_flag(doi=120.0, nmi_flag=False)
    assert flag is True


def test_smi_flag_false_low_doi():
    # DOI ≤ 90d → not slow-moving
    flag, gaps = compute_smi_flag(doi=30.0, nmi_flag=False)
    assert flag is False


def test_smi_flag_false_when_nmi():
    # Non-moving materials are NOT also flagged as slow-moving (mutually exclusive)
    flag, gaps = compute_smi_flag(doi=500.0, nmi_flag=True)
    assert flag is False


def test_smi_flag_none_when_doi_missing():
    flag, gaps = compute_smi_flag(doi=None, nmi_flag=False)
    assert flag is None
    assert any("not available" in g for g in gaps)


# ─── Fill Rate ────────────────────────────────────────────────────────────────

def test_fill_rate_basic():
    rate, gaps = compute_fill_rate(demand_met=80.0, total_demand=100.0)
    assert rate == 80.0
    assert gaps == []


def test_fill_rate_zero_demand():
    rate, gaps = compute_fill_rate(demand_met=0.0, total_demand=0.0)
    assert rate is None
    assert any("undefined" in g for g in gaps)


def test_fill_rate_missing_data():
    rate, gaps = compute_fill_rate(demand_met=None, total_demand=100.0)
    assert rate is None
    assert any("not available" in g for g in gaps)


# ─── Critical Spares Availability ────────────────────────────────────────────

def test_critical_spares_availability():
    avail, gaps = compute_critical_spares_availability(days_in_stock=350, total_days=365)
    assert avail == pytest.approx(350 / 365 * 100, rel=0.01)


def test_critical_spares_availability_missing():
    avail, gaps = compute_critical_spares_availability(None, None)
    assert avail is None
    assert any("not available" in g for g in gaps)


# ─── Safety Stock ─────────────────────────────────────────────────────────────
# Formula: Z × σ_daily × √LT  (data contract §3.4, Z=1.645 for 95% service level)

def test_safety_stock_basic():
    # SS = 1.645 × 2.0 × √25 = 1.645 × 2.0 × 5 = 16.45
    ss, gaps = compute_safety_stock(stddev_daily_cons=2.0, lead_time_days=25.0)
    assert ss == pytest.approx(SAFETY_STOCK_Z_95 * 2.0 * (25.0 ** 0.5), rel=0.001)
    assert gaps == []


def test_safety_stock_zero_stddev():
    # Zero variance → SS = 0 (clamped, never negative)
    ss, gaps = compute_safety_stock(stddev_daily_cons=0.0, lead_time_days=30.0)
    assert ss == 0.0
    assert gaps == []


def test_safety_stock_never_negative():
    # Negative result is impossible with Z×σ×√LT (all non-negative), but clamp is still there
    ss, gaps = compute_safety_stock(stddev_daily_cons=0.0, lead_time_days=0.0)
    assert ss == 0.0


def test_safety_stock_missing_stddev():
    ss, gaps = compute_safety_stock(stddev_daily_cons=None, lead_time_days=30.0)
    assert ss is None
    assert any("blocked" in g.lower() for g in gaps)


def test_safety_stock_missing_lead_time():
    ss, gaps = compute_safety_stock(stddev_daily_cons=2.0, lead_time_days=None)
    assert ss is None
    assert any("blocked" in g.lower() for g in gaps)


def test_safety_stock_missing_both():
    ss, gaps = compute_safety_stock(stddev_daily_cons=None, lead_time_days=None)
    assert ss is None
    assert any("blocked" in g.lower() for g in gaps)


def test_safety_stock_custom_z():
    # Custom Z-score (e.g. 99% service level, Z=2.326)
    ss, gaps = compute_safety_stock(stddev_daily_cons=3.0, lead_time_days=16.0, z_score=2.326)
    assert ss == pytest.approx(2.326 * 3.0 * 4.0, rel=0.001)
    assert gaps == []


# ─── ROP ─────────────────────────────────────────────────────────────────────

def test_rop_basic():
    rop, gaps = compute_rop(avg_daily_usage=5.0, avg_lead_time_days=20.0, safety_stock=100.0)
    # (5 × 20) + 100 = 200
    assert rop == 200.0
    assert gaps == []


def test_rop_missing_safety_stock():
    rop, gaps = compute_rop(avg_daily_usage=5.0, avg_lead_time_days=20.0, safety_stock=None)
    assert rop is None


# ─── Overstock / Understock ───────────────────────────────────────────────────
# Overstock: STOCK > AVG_DAILY_CONS_90D × 180d  (data contract §3.6)

def test_overstock_flag_true():
    # avg_daily=1.0, threshold=180; stock=500 > 180 → True
    flag, gaps = compute_overstock_flag(current_stock=500.0, avg_daily_cons_90d=1.0)
    assert flag is True
    assert gaps == []


def test_overstock_flag_false():
    # avg_daily=2.0, threshold=360; stock=100 < 360 → False
    flag, gaps = compute_overstock_flag(current_stock=100.0, avg_daily_cons_90d=2.0)
    assert flag is False
    assert gaps == []


def test_overstock_flag_zero_consumption():
    # Zero consumption → any stock is overstock
    flag, gaps = compute_overstock_flag(current_stock=1.0, avg_daily_cons_90d=0.0)
    assert flag is True
    assert gaps == []


def test_overstock_flag_missing_avg_daily():
    flag, gaps = compute_overstock_flag(current_stock=100.0, avg_daily_cons_90d=None)
    assert flag is None
    assert any("blocked" in g.lower() for g in gaps)


def test_overstock_flag_custom_threshold():
    # Custom threshold: 90 days
    flag, gaps = compute_overstock_flag(current_stock=100.0, avg_daily_cons_90d=1.0, overstock_threshold_days=90.0)
    assert flag is True   # 100 > 1.0 × 90 = 90


def test_understock_flag_true():
    flag, gaps = compute_understock_flag(current_stock=50.0, rop=200.0)
    assert flag is True


def test_understock_flag_false():
    flag, gaps = compute_understock_flag(current_stock=300.0, rop=200.0)
    assert flag is False


# ─── Forecast Accuracy ────────────────────────────────────────────────────────

def test_forecast_accuracy_perfect():
    acc, gaps = compute_forecast_accuracy([100.0, 200.0, 150.0], [100.0, 200.0, 150.0])
    assert acc == 100.0


def test_forecast_accuracy_50pct_error():
    # MAPE = avg(|100-150|/100, |200-300|/200) = avg(0.5, 0.5) = 0.5 → 50% → accuracy = 50%
    acc, gaps = compute_forecast_accuracy([100.0, 200.0], [150.0, 300.0])
    assert acc == pytest.approx(50.0, rel=0.01)


def test_forecast_accuracy_no_actuals():
    acc, gaps = compute_forecast_accuracy([], [])
    assert acc is None
    assert any("actuals" in g for g in gaps)


# ─── Forecast Bias ────────────────────────────────────────────────────────────

def test_forecast_bias_positive():
    # avg((150-100)/100, (300-200)/200) = avg(0.5, 0.5) = 0.5 → 50%
    bias, gaps = compute_forecast_bias([100.0, 200.0], [150.0, 300.0])
    assert bias == pytest.approx(50.0, rel=0.01)


def test_forecast_bias_zero():
    bias, gaps = compute_forecast_bias([100.0, 200.0], [100.0, 200.0])
    assert bias == pytest.approx(0.0, abs=0.01)


def test_forecast_bias_no_actuals():
    bias, gaps = compute_forecast_bias([], [])
    assert bias is None
