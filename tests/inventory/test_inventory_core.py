"""
Inventory core logic and its test suite.

Functions here mirror the analysis the Inventory & Forecasting Cell runs
against the SAP HANA extract.  They are pure-Python / pandas so they run
in CI without a live HANA connection.

Test coverage:
  - Gross inventory value calculation
  - Days-on-hand (DOH) per material
  - Overstock detection (DOH > threshold)
  - Understock / below-reorder-point detection
  - Non-moving material (NMI) identification
  - Slow-moving material (SMI) identification
  - 3-month demand forecast (simple moving average)
  - PR quantity suggestion
"""
from __future__ import annotations

import pytest
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Production logic (would live in src/ in a larger project)
# ---------------------------------------------------------------------------

def gross_inventory_value(df: pd.DataFrame) -> float:
    """Return total inventory value: sum(stock_qty * unit_price)."""
    return float((df["stock_qty"] * df["unit_price"]).sum())


def days_on_hand(df: pd.DataFrame) -> pd.Series:
    """
    Days-on-hand per row.

    DOH = stock_qty / (avg_monthly_consumption / 30).
    Returns inf where avg_monthly_consumption == 0 (no consumption).
    """
    daily_consumption = df["avg_monthly_consumption"] / 30.0
    # Avoid division by zero — replace 0 with NaN then fill with inf
    safe = daily_consumption.replace(0, np.nan)
    doh = df["stock_qty"] / safe
    return doh.fillna(np.inf)


def flag_overstock(df: pd.DataFrame, doh_threshold: float = 365.0) -> pd.DataFrame:
    """Return rows where DOH exceeds *doh_threshold* days."""
    doh = days_on_hand(df)
    return df[doh > doh_threshold].copy()


def flag_understock(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows where stock_qty < reorder_point."""
    return df[df["stock_qty"] < df["reorder_point"]].copy()


def flag_nmi(df: pd.DataFrame) -> pd.DataFrame:
    """Non-moving: avg_monthly_consumption == 0 AND stock_qty > 0."""
    mask = (df["avg_monthly_consumption"] == 0) & (df["stock_qty"] > 0)
    return df[mask].copy()


def flag_smi(
    df: pd.DataFrame,
    low_threshold: float = 5.0,
    high_threshold: float = 0.0,
) -> pd.DataFrame:
    """
    Slow-moving: avg_monthly_consumption > 0 but below *low_threshold*,
    AND stock_qty > 0.
    """
    mask = (
        (df["avg_monthly_consumption"] > high_threshold)
        & (df["avg_monthly_consumption"] < low_threshold)
        & (df["stock_qty"] > 0)
    )
    return df[mask].copy()


def three_month_forecast(history: pd.DataFrame, material: str) -> float:
    """
    Simple 3-month moving-average forecast for *material*.

    *history* must have columns: material, period, consumption.
    Returns the mean of the last 3 months of consumption, or 0.0 if
    fewer than 1 month of data exists.
    """
    mat_data = (
        history[history["material"] == material]
        .sort_values("period")
        .tail(3)
    )
    if mat_data.empty:
        return 0.0
    return float(mat_data["consumption"].mean())


def suggest_pr_qty(
    df: pd.DataFrame,
    forecast_months: int = 3,
) -> pd.DataFrame:
    """
    Suggest purchase-requisition quantity for understocked materials.

    PR qty = (avg_monthly_consumption * forecast_months) - stock_qty,
    floored at 0.
    """
    result = df.copy()
    raw = (
        result["avg_monthly_consumption"] * forecast_months - result["stock_qty"]
    )
    result["pr_qty"] = raw.clip(lower=0)
    return result


# ---------------------------------------------------------------------------
# Tests — gross inventory value
# ---------------------------------------------------------------------------

class TestGrossInventoryValue:
    def test_positive_stock(self, stock_df: pd.DataFrame) -> None:
        val = gross_inventory_value(stock_df)
        assert val > 0

    def test_known_value(self) -> None:
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


# ---------------------------------------------------------------------------
# Tests — days on hand
# ---------------------------------------------------------------------------

class TestDaysOnHand:
    def test_zero_consumption_is_inf(self, stock_df: pd.DataFrame) -> None:
        doh = days_on_hand(stock_df)
        zero_cons = stock_df["avg_monthly_consumption"] == 0
        assert (doh[zero_cons] == np.inf).all()

    def test_nonzero_consumption_finite(self, stock_df: pd.DataFrame) -> None:
        doh = days_on_hand(stock_df)
        nonzero = stock_df["avg_monthly_consumption"] > 0
        assert np.isfinite(doh[nonzero]).all()

    def test_known_doh(self) -> None:
        df = pd.DataFrame(
            {"stock_qty": [300], "avg_monthly_consumption": [10]}
        )
        # 300 / (10/30) = 900 days
        doh = days_on_hand(df)
        assert doh.iloc[0] == pytest.approx(900.0)

    def test_length_matches_input(self, stock_df: pd.DataFrame) -> None:
        assert len(days_on_hand(stock_df)) == len(stock_df)


# ---------------------------------------------------------------------------
# Tests — overstock
# ---------------------------------------------------------------------------

class TestFlagOverstock:
    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        result = flag_overstock(stock_df)
        assert isinstance(result, pd.DataFrame)

    def test_all_overstock_at_zero_threshold(self, stock_df: pd.DataFrame) -> None:
        # With threshold=0 every material with stock > 0 should appear
        result = flag_overstock(stock_df, doh_threshold=0.0)
        has_stock = stock_df[stock_df["stock_qty"] > 0]
        # Materials with consumption > 0 and DOH > 0 are included
        assert len(result) >= len(has_stock[has_stock["avg_monthly_consumption"] > 0])

    def test_high_threshold_returns_subset(self, stock_df: pd.DataFrame) -> None:
        all_over = flag_overstock(stock_df, doh_threshold=0.0)
        fewer = flag_overstock(stock_df, doh_threshold=500.0)
        assert len(fewer) <= len(all_over)

    def test_columns_preserved(self, stock_df: pd.DataFrame) -> None:
        result = flag_overstock(stock_df)
        assert set(stock_df.columns).issubset(set(result.columns))

    def test_zero_consumption_always_overstock(self, stock_df: pd.DataFrame) -> None:
        # Materials with zero consumption and stock > 0 have infinite DOH
        nmi = stock_df[
            (stock_df["avg_monthly_consumption"] == 0) & (stock_df["stock_qty"] > 0)
        ]
        result = flag_overstock(stock_df, doh_threshold=365.0)
        for mat in nmi["material"]:
            assert mat in result["material"].values


# ---------------------------------------------------------------------------
# Tests — understock
# ---------------------------------------------------------------------------

class TestFlagUnderstock:
    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(flag_understock(stock_df), pd.DataFrame)

    def test_all_below_reorder(self, stock_df: pd.DataFrame) -> None:
        result = flag_understock(stock_df)
        assert (result["stock_qty"] < result["reorder_point"]).all()

    def test_no_false_positives(self, stock_df: pd.DataFrame) -> None:
        result = flag_understock(stock_df)
        for _, row in result.iterrows():
            assert row["stock_qty"] < row["reorder_point"]

    def test_known_understock(self) -> None:
        df = pd.DataFrame(
            {"stock_qty": [5, 50], "reorder_point": [10, 10]}
        )
        result = flag_understock(df)
        assert len(result) == 1
        assert result.iloc[0]["stock_qty"] == 5


# ---------------------------------------------------------------------------
# Tests — NMI
# ---------------------------------------------------------------------------

class TestFlagNMI:
    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(flag_nmi(stock_df), pd.DataFrame)

    def test_all_nmi_have_zero_consumption(self, stock_df: pd.DataFrame) -> None:
        result = flag_nmi(stock_df)
        assert (result["avg_monthly_consumption"] == 0).all()

    def test_all_nmi_have_positive_stock(self, stock_df: pd.DataFrame) -> None:
        result = flag_nmi(stock_df)
        assert (result["stock_qty"] > 0).all()

    def test_known_nmi(self) -> None:
        df = pd.DataFrame(
            {
                "stock_qty": [100, 0, 50],
                "avg_monthly_consumption": [0, 0, 5],
            }
        )
        result = flag_nmi(df)
        assert len(result) == 1
        assert result.iloc[0]["stock_qty"] == 100


# ---------------------------------------------------------------------------
# Tests — SMI
# ---------------------------------------------------------------------------

class TestFlagSMI:
    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(flag_smi(stock_df), pd.DataFrame)

    def test_smi_consumption_in_range(self, stock_df: pd.DataFrame) -> None:
        result = flag_smi(stock_df, low_threshold=5.0)
        if not result.empty:
            assert (result["avg_monthly_consumption"] > 0).all()
            assert (result["avg_monthly_consumption"] < 5.0).all()

    def test_smi_has_positive_stock(self, stock_df: pd.DataFrame) -> None:
        result = flag_smi(stock_df)
        assert (result["stock_qty"] > 0).all()

    def test_known_smi(self) -> None:
        df = pd.DataFrame(
            {
                "stock_qty": [200, 0, 50],
                "avg_monthly_consumption": [2, 2, 10],
            }
        )
        result = flag_smi(df, low_threshold=5.0)
        assert len(result) == 1
        assert result.iloc[0]["stock_qty"] == 200


# ---------------------------------------------------------------------------
# Tests — 3-month forecast
# ---------------------------------------------------------------------------

class TestThreeMonthForecast:
    def test_known_average(
        self, consumption_history_df: pd.DataFrame
    ) -> None:
        # MAT001 base=10, last 3 months: 10+(9%3)=10, 10+(10%3)=11, 10+(11%3)=12
        # mean = (10+11+12)/3 = 11.0
        result = three_month_forecast(consumption_history_df, "MAT001")
        assert result == pytest.approx(11.0)

    def test_unknown_material_returns_zero(
        self, consumption_history_df: pd.DataFrame
    ) -> None:
        assert three_month_forecast(consumption_history_df, "UNKNOWN") == 0.0

    def test_result_is_float(
        self, consumption_history_df: pd.DataFrame
    ) -> None:
        result = three_month_forecast(consumption_history_df, "MAT003")
        assert isinstance(result, float)

    def test_nonnegative(
        self, consumption_history_df: pd.DataFrame
    ) -> None:
        for mat in ["MAT001", "MAT003", "MAT006"]:
            assert three_month_forecast(consumption_history_df, mat) >= 0.0


# ---------------------------------------------------------------------------
# Tests — PR suggestion
# ---------------------------------------------------------------------------

class TestSuggestPRQty:
    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(suggest_pr_qty(stock_df), pd.DataFrame)

    def test_pr_qty_column_present(self, stock_df: pd.DataFrame) -> None:
        result = suggest_pr_qty(stock_df)
        assert "pr_qty" in result.columns

    def test_pr_qty_nonnegative(self, stock_df: pd.DataFrame) -> None:
        result = suggest_pr_qty(stock_df)
        assert (result["pr_qty"] >= 0).all()

    def test_well_stocked_material_zero_pr(self) -> None:
        df = pd.DataFrame(
            {
                "stock_qty": [1000],
                "avg_monthly_consumption": [10],
                "reorder_point": [15],
            }
        )
        result = suggest_pr_qty(df, forecast_months=3)
        assert result.iloc[0]["pr_qty"] == 0

    def test_empty_stock_generates_pr(self) -> None:
        df = pd.DataFrame(
            {
                "stock_qty": [0],
                "avg_monthly_consumption": [20],
                "reorder_point": [30],
            }
        )
        result = suggest_pr_qty(df, forecast_months=3)
        # Expected: 20*3 - 0 = 60
        assert result.iloc[0]["pr_qty"] == pytest.approx(60.0)

    def test_original_df_not_mutated(self, stock_df: pd.DataFrame) -> None:
        original_cols = list(stock_df.columns)
        suggest_pr_qty(stock_df)
        assert list(stock_df.columns) == original_cols
