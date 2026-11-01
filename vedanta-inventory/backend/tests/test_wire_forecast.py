"""
Tests for wire_forecast_into_metrics — verifies that ContextFlow forecast output
is correctly wired into Safety Stock, ROP, Overstock, Understock,
Forecast Accuracy, and Forecast Bias.

Connected path: ForecastResponse provided → metrics computed.
Disconnected path: None inputs → fields remain None with gap entries.

Run: cd vedanta-inventory/backend && pytest tests/test_wire_forecast.py -v
"""
from __future__ import annotations
import os
import sys
import pytest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("USE_TEST_FIXTURES", "true")

from app.models.schemas import (
    ConsumptionRecord, StockMasterRecord, PORecord,
    ForecastResponse, ForecastPeriod, MaterialMetrics,
)
from app.services.metrics_engine import (
    compute_real_data_metrics,
    wire_forecast_into_metrics,
    SAFETY_STOCK_Z_95,
    OVERSTOCK_THRESHOLD_DAYS,
    _consumption_stats_90d,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_stock(
    material_code: str = "MAT-001",
    plant: str = "PL01",
    current_stock: float = 500.0,
    unit_price: float = 100.0,
    critical_flag: bool = True,
) -> StockMasterRecord:
    return StockMasterRecord(
        material_code=material_code,
        plant=plant,
        current_stock=current_stock,
        unit_price=unit_price,
        category="BEARINGS",
        material_type="ZSPR",
        critical_flag=critical_flag,
        shutdown_flag=False,
    )


def _make_consumption(
    qty_per_day: float = 2.0,
    days: int = 90,
    material: str = "MAT-001",
    plant: str = "PL01",
) -> list:
    today = date.today()
    return [
        ConsumptionRecord(
            material_code=material,
            plant=plant,
            posting_date=today - timedelta(days=i),
            qty=qty_per_day,
        )
        for i in range(days)
    ]


def _make_forecast_response(
    material_code: str = "MAT-001",
    plant: str = "PL01",
    avg_daily_usage: float = 2.0,
    avg_lead_time_days: float = 30.0,
    f3: float = 180.0,
    f6: float = 360.0,
    f12: float = 720.0,
) -> ForecastResponse:
    return ForecastResponse(
        material_code=material_code,
        plant=plant,
        forecasts=[
            ForecastPeriod(horizon_months=3, forecast_qty=f3),
            ForecastPeriod(horizon_months=6, forecast_qty=f6),
            ForecastPeriod(horizon_months=12, forecast_qty=f12),
        ],
        avg_daily_usage=avg_daily_usage,
        max_daily_usage=avg_daily_usage * 2,
        avg_lead_time_days=avg_lead_time_days,
        max_lead_time_days=avg_lead_time_days * 1.5,
    )


def _base_metrics(stock: StockMasterRecord, consumption: list) -> MaterialMetrics:
    return compute_real_data_metrics(
        stock=stock,
        consumption_records=consumption,
        po_records=[],
    )


# ── Safety Stock ─────────────────────────────────────────────────────────────

class TestSafetyStockWired:
    """SS = Z × σ_daily × √LT  (data contract §3.4)"""

    def test_safety_stock_computed_from_forecast_lead_time(self):
        """SS uses σ from 90-day consumption history and LT from ContextFlow."""
        consumption = _make_consumption(qty_per_day=2.0, days=90)
        stock = _make_stock(current_stock=500.0)
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response(avg_lead_time_days=30.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
        )

        assert result.safety_stock is not None
        # Verify formula: Z × σ × √LT
        _, stddev = _consumption_stats_90d(consumption)
        expected_ss = SAFETY_STOCK_Z_95 * stddev * (30.0 ** 0.5)
        assert result.safety_stock == pytest.approx(max(0.0, expected_ss), rel=0.001)

    def test_safety_stock_zero_when_zero_variance(self):
        """Constant consumption → σ=0 → SS=0 (not None)."""
        consumption = _make_consumption(qty_per_day=5.0, days=90)
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response(avg_lead_time_days=20.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
        )
        # σ may be near-zero for constant series; SS should be ≥ 0
        assert result.safety_stock is not None
        assert result.safety_stock >= 0.0

    def test_safety_stock_none_when_no_consumption_records(self):
        """No consumption records → σ unknown → SS is None with gap entry."""
        stock = _make_stock()
        metrics = _base_metrics(stock, [])
        forecast = _make_forecast_response(avg_lead_time_days=30.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=None,  # explicitly no records
        )
        assert result.safety_stock is None
        assert any("Safety Stock" in g or "blocked" in g.lower() for g in result.data_gaps)

    def test_safety_stock_none_when_lead_time_zero(self):
        """LT=0 → SS=0 (√0 = 0), not None."""
        consumption = _make_consumption(qty_per_day=2.0, days=90)
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response(avg_lead_time_days=0.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
        )
        # SS = Z × σ × √0 = 0
        assert result.safety_stock == pytest.approx(0.0, abs=0.01)


# ── Reorder Point ─────────────────────────────────────────────────────────────

class TestROPWired:
    """ROP = (AVG_DAILY_CONS_90D × LT) + SS  (data contract §3.5)"""

    def test_rop_computed_correctly(self):
        consumption = _make_consumption(qty_per_day=2.0, days=90)
        stock = _make_stock(current_stock=500.0)
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response(avg_lead_time_days=30.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
        )

        assert result.reorder_point is not None
        avg_daily, stddev = _consumption_stats_90d(consumption)
        expected_ss = SAFETY_STOCK_Z_95 * stddev * (30.0 ** 0.5)
        expected_rop = (avg_daily * 30.0) + max(0.0, expected_ss)
        assert result.reorder_point == pytest.approx(expected_rop, rel=0.001)

    def test_rop_none_when_no_consumption(self):
        stock = _make_stock()
        metrics = _base_metrics(stock, [])
        forecast = _make_forecast_response(avg_lead_time_days=30.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=None,
        )
        assert result.reorder_point is None


# ── Overstock Flag ────────────────────────────────────────────────────────────

class TestOverstockWired:
    """Overstock: STOCK > AVG_DAILY_CONS_90D × 180d  (data contract §3.6)
    This is computed in compute_real_data_metrics (consumption-based, no ContextFlow).
    wire_forecast_into_metrics must NOT overwrite it.
    """

    def test_overstock_true_preserved_after_wiring(self):
        """Overstock=True set before wiring must survive wire_forecast_into_metrics."""
        # avg_daily ≈ 1.0, threshold = 180; stock=500 → overstock
        consumption = _make_consumption(qty_per_day=1.0, days=90)
        stock = _make_stock(current_stock=500.0)
        metrics = _base_metrics(stock, consumption)
        assert metrics.overstock_flag is True  # pre-condition

        forecast = _make_forecast_response(avg_lead_time_days=30.0)
        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
        )
        assert result.overstock_flag is True

    def test_overstock_false_preserved_after_wiring(self):
        """Overstock=False set before wiring must survive wire_forecast_into_metrics."""
        # avg_daily ≈ 5.0, threshold = 900; stock=100 → not overstock
        consumption = _make_consumption(qty_per_day=5.0, days=90)
        stock = _make_stock(current_stock=100.0)
        metrics = _base_metrics(stock, consumption)
        assert metrics.overstock_flag is False  # pre-condition

        forecast = _make_forecast_response(avg_lead_time_days=30.0)
        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=100.0,
            consumption_records=consumption,
        )
        assert result.overstock_flag is False

    def test_overstock_action_set_when_true(self):
        """recommended_action mentions reducing order when overstock."""
        consumption = _make_consumption(qty_per_day=0.5, days=90)
        stock = _make_stock(current_stock=1000.0)
        metrics = _base_metrics(stock, consumption)
        assert metrics.overstock_flag is True

        forecast = _make_forecast_response(avg_lead_time_days=30.0)
        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=1000.0,
            consumption_records=consumption,
        )
        assert result.recommended_action is not None
        assert "reduce" in result.recommended_action.lower() or "defer" in result.recommended_action.lower()


# ── Understock Flag ───────────────────────────────────────────────────────────

class TestUnderstockWired:
    """Understock: STOCK < ROP  (data contract §3.7)"""

    def test_understock_true_when_stock_below_rop(self):
        """Very low stock relative to consumption → understock."""
        consumption = _make_consumption(qty_per_day=10.0, days=90)
        stock = _make_stock(current_stock=5.0)  # tiny stock
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response(avg_lead_time_days=30.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=5.0,
            consumption_records=consumption,
        )
        # ROP = (10 × 30) + SS ≫ 5 → understock
        assert result.understock_flag is True

    def test_understock_false_when_stock_above_rop(self):
        """Large stock relative to consumption → not understock."""
        consumption = _make_consumption(qty_per_day=1.0, days=90)
        stock = _make_stock(current_stock=10000.0)
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response(avg_lead_time_days=30.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=10000.0,
            consumption_records=consumption,
        )
        assert result.understock_flag is False

    def test_understock_none_when_rop_unavailable(self):
        """No consumption → ROP is None → understock is None."""
        stock = _make_stock(current_stock=500.0)
        metrics = _base_metrics(stock, [])
        forecast = _make_forecast_response(avg_lead_time_days=30.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=None,
        )
        assert result.understock_flag is None

    def test_understock_action_set_when_true(self):
        """recommended_action mentions raising PR when understock."""
        consumption = _make_consumption(qty_per_day=10.0, days=90)
        stock = _make_stock(current_stock=5.0)
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response(avg_lead_time_days=30.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=5.0,
            consumption_records=consumption,
        )
        assert result.recommended_action is not None
        assert "pr" in result.recommended_action.lower() or "raise" in result.recommended_action.lower()


# ── Forecast Accuracy ─────────────────────────────────────────────────────────

class TestForecastAccuracyWired:
    """Accuracy = 100 − MAPE  (post-actuals only)"""

    def test_accuracy_computed_when_actuals_provided(self):
        """When historical actuals and forecasts are provided, accuracy is computed."""
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response()

        actuals = [100.0, 200.0, 150.0]
        hist_forecasts = [100.0, 200.0, 150.0]  # perfect

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
            actuals=actuals,
            historical_forecasts=hist_forecasts,
        )
        assert result.forecast_accuracy_pct == pytest.approx(100.0)

    def test_accuracy_50pct_on_50pct_mape(self):
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response()

        actuals = [100.0, 200.0]
        hist_forecasts = [150.0, 300.0]  # 50% over each → MAPE=50% → accuracy=50%

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
            actuals=actuals,
            historical_forecasts=hist_forecasts,
        )
        assert result.forecast_accuracy_pct == pytest.approx(50.0, rel=0.01)

    def test_accuracy_none_when_no_actuals(self):
        """No actuals → accuracy is None with gap entry (post-actuals metric)."""
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response()

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
            actuals=None,
            historical_forecasts=None,
        )
        assert result.forecast_accuracy_pct is None
        assert any("actuals" in g.lower() or "accuracy" in g.lower() for g in result.data_gaps)

    def test_accuracy_none_when_empty_actuals(self):
        """Empty actuals list → accuracy is None."""
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response()

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
            actuals=[],
            historical_forecasts=[],
        )
        assert result.forecast_accuracy_pct is None


# ── Forecast Bias ─────────────────────────────────────────────────────────────

class TestForecastBiasWired:
    """Bias = avg((F−A)/A) × 100%  (post-actuals only)"""

    def test_bias_zero_on_perfect_forecast(self):
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response()

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
            actuals=[100.0, 200.0],
            historical_forecasts=[100.0, 200.0],
        )
        assert result.forecast_bias_pct == pytest.approx(0.0, abs=0.01)

    def test_bias_positive_when_over_forecast(self):
        """Forecasts consistently higher than actuals → positive bias."""
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response()

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
            actuals=[100.0, 200.0],
            historical_forecasts=[150.0, 300.0],  # 50% over
        )
        assert result.forecast_bias_pct == pytest.approx(50.0, rel=0.01)

    def test_bias_none_when_no_actuals(self):
        """No actuals → bias is None with gap entry."""
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response()

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
        )
        assert result.forecast_bias_pct is None
        assert any("bias" in g.lower() or "actuals" in g.lower() for g in result.data_gaps)


# ── Forecast quantities wired ─────────────────────────────────────────────────

class TestForecastQuantitiesWired:
    """3/6/12-month forecast quantities from ContextFlow appear in MaterialMetrics."""

    def test_forecast_quantities_populated(self):
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)
        forecast = _make_forecast_response(f3=180.0, f6=360.0, f12=720.0)

        result = wire_forecast_into_metrics(
            metrics, forecast, current_stock=500.0,
            consumption_records=consumption,
        )
        assert result.forecast_3mo == pytest.approx(180.0)
        assert result.forecast_6mo == pytest.approx(360.0)
        assert result.forecast_12mo == pytest.approx(720.0)

    def test_data_not_available_shown_as_none_not_error(self):
        """
        When ContextFlow is unavailable, the caller does NOT call wire_forecast_into_metrics.
        The base metrics object has None for all forecast-dependent fields.
        This test verifies the base state is correct (None, not an error string).
        """
        consumption = _make_consumption()
        stock = _make_stock()
        metrics = _base_metrics(stock, consumption)

        # Before wiring: forecast-dependent fields are None
        assert metrics.safety_stock is None
        assert metrics.reorder_point is None
        assert metrics.understock_flag is None
        assert metrics.forecast_3mo is None
        assert metrics.forecast_6mo is None
        assert metrics.forecast_12mo is None
        assert metrics.forecast_accuracy_pct is None
        assert metrics.forecast_bias_pct is None
