"""
D1 — 3-month gross inventory forecast by plant.

Logic under test
----------------
three_month_forecast(history, material)  → float
    Simple 3-month moving-average forecast.  Returns the mean of the last
    3 months of consumption for *material*, or 0.0 if no data exists.

gross_inventory_value(df)  → float
    Total inventory value = sum(stock_qty * unit_price).

All tests are pure-pandas; no live SAP HANA connection is required.
Run with: RUN_INTEGRATION_TESTS=0 pytest tests/inventory/test_d1_forecast.py -v
"""
from __future__ import annotations

import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Logic module (self-contained so this file is independently runnable)
# ---------------------------------------------------------------------------

def gross_inventory_value(df: pd.DataFrame) -> float:
    """Return total inventory value: sum(stock_qty * unit_price)."""
    return float((df["stock_qty"] * df["unit_price"]).sum())


def three_month_forecast(history: pd.DataFrame, material: str) -> float:
    """
    Simple 3-month moving-average forecast for *material*.

    Parameters
    ----------
    history : DataFrame with columns: material, period, consumption.
    material : Material code to forecast.

    Returns
    -------
    float
        Mean of the last 3 months of consumption, or 0.0 if no data.
    """
    mat_data = (
        history[history["material"] == material]
        .sort_values("period")
        .tail(3)
    )
    if mat_data.empty:
        return 0.0
    return float(mat_data["consumption"].mean())


def forecast_by_plant(
    stock: pd.DataFrame,
    history: pd.DataFrame,
) -> pd.DataFrame:
    """
    Return a 3-month demand forecast per (plant, material) pair.

    Parameters
    ----------
    stock   : DataFrame with columns: material, plant, stock_qty, unit_price.
    history : DataFrame with columns: material, period, consumption.

    Returns
    -------
    DataFrame with columns: material, plant, forecast_qty, gross_inv_value.
    """
    rows = []
    for _, row in stock.iterrows():
        fcast = three_month_forecast(history, str(row["material"]))
        rows.append(
            {
                "material": row["material"],
                "plant": row["plant"],
                "forecast_qty": fcast,
                "gross_inv_value": float(row["stock_qty"]) * float(row["unit_price"]),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def stock_df() -> pd.DataFrame:
    """Minimal stock snapshot across two plants."""
    return pd.DataFrame(
        {
            "material": ["MAT001", "MAT002", "MAT003", "MAT004"],
            "plant": ["HZL_DEMO_01", "HZL_DEMO_01", "HZL_DEMO_02", "HZL_DEMO_02"],
            "stock_qty": [500.0, 0.0, 200.0, 100.0],
            "unit_price": [10.0, 50.0, 5.0, 20.0],
            "avg_monthly_consumption": [10, 0, 40, 5],
        }
    )


@pytest.fixture()
def history_df() -> pd.DataFrame:
    """12-month consumption history for MAT001 and MAT003."""
    months = pd.date_range("2024-01-01", periods=12, freq="MS")
    rows = []
    for mat, base in [("MAT001", 10), ("MAT003", 40)]:
        for i, m in enumerate(months):
            rows.append({"material": mat, "period": m, "consumption": float(base + (i % 3))})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests — gross_inventory_value
# ---------------------------------------------------------------------------

class TestGrossInventoryValue:
    """D1-A: gross inventory value = sum(stock_qty * unit_price)."""

    def test_known_two_row_value(self) -> None:
        df = pd.DataFrame({"stock_qty": [10, 20], "unit_price": [5.0, 2.5]})
        assert gross_inventory_value(df) == pytest.approx(100.0)

    def test_zero_stock_gives_zero(self) -> None:
        df = pd.DataFrame({"stock_qty": [0, 0], "unit_price": [99.0, 1.0]})
        assert gross_inventory_value(df) == pytest.approx(0.0)

    def test_single_row(self) -> None:
        df = pd.DataFrame({"stock_qty": [7], "unit_price": [3.0]})
        assert gross_inventory_value(df) == pytest.approx(21.0)

    def test_returns_float(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(gross_inventory_value(stock_df), float)

    def test_positive_for_positive_stock(self, stock_df: pd.DataFrame) -> None:
        assert gross_inventory_value(stock_df) > 0.0

    def test_matches_manual_sum(self, stock_df: pd.DataFrame) -> None:
        expected = float((stock_df["stock_qty"] * stock_df["unit_price"]).sum())
        assert gross_inventory_value(stock_df) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tests — three_month_forecast
# ---------------------------------------------------------------------------

class TestThreeMonthForecast:
    """D1-B: 3-month moving-average forecast per material."""

    def test_unknown_material_returns_zero(self, history_df: pd.DataFrame) -> None:
        assert three_month_forecast(history_df, "UNKNOWN") == 0.0

    def test_result_is_float(self, history_df: pd.DataFrame) -> None:
        assert isinstance(three_month_forecast(history_df, "MAT001"), float)

    def test_nonnegative_for_all_materials(self, history_df: pd.DataFrame) -> None:
        for mat in ["MAT001", "MAT003"]:
            assert three_month_forecast(history_df, mat) >= 0.0

    def test_uses_only_last_three_months(self) -> None:
        """Spike in last 3 months must dominate the forecast."""
        months = pd.date_range("2024-01-01", periods=12, freq="MS")
        rows = [
            {"material": "MAT_X", "period": m, "consumption": 1.0 if i < 9 else 100.0}
            for i, m in enumerate(months)
        ]
        hist = pd.DataFrame(rows)
        assert three_month_forecast(hist, "MAT_X") == pytest.approx(100.0)

    def test_single_month_history(self) -> None:
        hist = pd.DataFrame({
            "material": ["MAT_ONE"],
            "period": [pd.Timestamp("2025-12-01")],
            "consumption": [42.0],
        })
        assert three_month_forecast(hist, "MAT_ONE") == pytest.approx(42.0)

    def test_known_average_mat001(self, history_df: pd.DataFrame) -> None:
        # MAT001 base=10; last 3 months (i=9,10,11): 10+(9%3)=10, 10+(10%3)=11, 10+(11%3)=12
        result = three_month_forecast(history_df, "MAT001")
        assert result == pytest.approx(11.0)


# ---------------------------------------------------------------------------
# Tests — forecast_by_plant
# ---------------------------------------------------------------------------

class TestForecastByPlant:
    """D1-C: per-plant forecast DataFrame."""

    def test_returns_dataframe(self, stock_df: pd.DataFrame, history_df: pd.DataFrame) -> None:
        result = forecast_by_plant(stock_df, history_df)
        assert isinstance(result, pd.DataFrame)

    def test_row_count_matches_stock(self, stock_df: pd.DataFrame, history_df: pd.DataFrame) -> None:
        result = forecast_by_plant(stock_df, history_df)
        assert len(result) == len(stock_df)

    def test_required_columns_present(self, stock_df: pd.DataFrame, history_df: pd.DataFrame) -> None:
        result = forecast_by_plant(stock_df, history_df)
        for col in ["material", "plant", "forecast_qty", "gross_inv_value"]:
            assert col in result.columns

    def test_forecast_qty_nonnegative(self, stock_df: pd.DataFrame, history_df: pd.DataFrame) -> None:
        result = forecast_by_plant(stock_df, history_df)
        assert (result["forecast_qty"] >= 0).all()

    def test_gross_inv_value_nonnegative(self, stock_df: pd.DataFrame, history_df: pd.DataFrame) -> None:
        result = forecast_by_plant(stock_df, history_df)
        assert (result["gross_inv_value"] >= 0).all()

    def test_plants_preserved(self, stock_df: pd.DataFrame, history_df: pd.DataFrame) -> None:
        result = forecast_by_plant(stock_df, history_df)
        assert set(result["plant"]) == set(stock_df["plant"])

    def test_zero_stock_gives_zero_gross_inv(self, stock_df: pd.DataFrame, history_df: pd.DataFrame) -> None:
        result = forecast_by_plant(stock_df, history_df)
        zero_stock = stock_df[stock_df["stock_qty"] == 0]["material"].tolist()
        for mat in zero_stock:
            val = result[result["material"] == mat]["gross_inv_value"].iloc[0]
            assert val == pytest.approx(0.0)
