"""
D2 — Overstock / high-holdings detection.

Logic under test
----------------
days_on_hand(df)  → pd.Series
    DOH = stock_qty / (avg_monthly_consumption / 30).
    Returns inf where avg_monthly_consumption == 0.

flag_overstock(df, doh_threshold)  → pd.DataFrame
    Returns rows where DOH > doh_threshold.

All tests are pure-pandas; no live SAP HANA connection is required.
Run with: RUN_INTEGRATION_TESTS=0 pytest tests/inventory/test_d2_overstock.py -v
"""
from __future__ import annotations

import pytest
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Logic module
# ---------------------------------------------------------------------------

def days_on_hand(df: pd.DataFrame) -> pd.Series:
    """
    Days-on-hand per row.

    DOH = stock_qty / (avg_monthly_consumption / 30).
    Returns inf where avg_monthly_consumption == 0 (no consumption).
    """
    daily = df["avg_monthly_consumption"] / 30.0
    safe = daily.replace(0, np.nan)
    doh = df["stock_qty"] / safe
    return doh.fillna(np.inf)


def flag_overstock(df: pd.DataFrame, doh_threshold: float = 365.0) -> pd.DataFrame:
    """Return rows where DOH exceeds *doh_threshold* days."""
    doh = days_on_hand(df)
    return df[doh > doh_threshold].copy()


def high_holdings_value(df: pd.DataFrame, doh_threshold: float = 365.0) -> float:
    """Return total inventory value of overstocked materials."""
    over = flag_overstock(df, doh_threshold)
    if over.empty:
        return 0.0
    return float((over["stock_qty"] * over["unit_price"]).sum())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def stock_df() -> pd.DataFrame:
    """Ten materials across two plants."""
    return pd.DataFrame(
        {
            "material": [f"MAT{i:03d}" for i in range(1, 11)],
            "plant": ["HZL_DEMO_01"] * 5 + ["HZL_DEMO_02"] * 5,
            "stock_qty": [100, 0, 500, 20, 0, 300, 150, 0, 80, 60],
            "unit_price": [10.0, 25.0, 5.0, 100.0, 50.0, 8.0, 15.0, 200.0, 30.0, 45.0],
            "avg_monthly_consumption": [10, 0, 5, 0, 0, 30, 10, 0, 8, 6],
            "lead_time_days": [30, 60, 14, 90, 45, 21, 30, 120, 60, 30],
            "reorder_point": [15, 5, 10, 5, 3, 45, 20, 10, 12, 9],
            "category": ["SPARE"] * 5 + ["CONSUMABLE"] * 5,
        }
    )


# ---------------------------------------------------------------------------
# Tests — days_on_hand
# ---------------------------------------------------------------------------

class TestDaysOnHand:
    """D2-A: days-on-hand calculation."""

    def test_zero_consumption_is_inf(self, stock_df: pd.DataFrame) -> None:
        doh = days_on_hand(stock_df)
        zero_cons = stock_df["avg_monthly_consumption"] == 0
        assert (doh[zero_cons] == np.inf).all()

    def test_nonzero_consumption_is_finite(self, stock_df: pd.DataFrame) -> None:
        doh = days_on_hand(stock_df)
        nonzero = stock_df["avg_monthly_consumption"] > 0
        assert np.isfinite(doh[nonzero]).all()

    def test_known_doh_calculation(self) -> None:
        # 300 stock / (10 units/month / 30 days) = 900 days
        df = pd.DataFrame({"stock_qty": [300], "avg_monthly_consumption": [10]})
        assert days_on_hand(df).iloc[0] == pytest.approx(900.0)

    def test_length_matches_input(self, stock_df: pd.DataFrame) -> None:
        assert len(days_on_hand(stock_df)) == len(stock_df)

    def test_zero_stock_zero_consumption_is_inf(self) -> None:
        df = pd.DataFrame({"stock_qty": [0], "avg_monthly_consumption": [0]})
        assert days_on_hand(df).iloc[0] == np.inf

    def test_high_consumption_low_doh(self) -> None:
        # 10 stock / (300/30) = 1 day
        df = pd.DataFrame({"stock_qty": [10], "avg_monthly_consumption": [300]})
        assert days_on_hand(df).iloc[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Tests — flag_overstock
# ---------------------------------------------------------------------------

class TestFlagOverstock:
    """D2-B: overstock flagging."""

    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(flag_overstock(stock_df), pd.DataFrame)

    def test_high_doh_material_flagged(self) -> None:
        # DOH = 500 / (10/30) = 1500 days → overstock at 365-day threshold
        df = pd.DataFrame({
            "material": ["MAT_HIGH"],
            "stock_qty": [500],
            "unit_price": [10.0],
            "avg_monthly_consumption": [10],
            "lead_time_days": [30],
            "reorder_point": [15],
            "category": ["SPARE"],
            "plant": ["HZL_DEMO_01"],
        })
        result = flag_overstock(df, doh_threshold=365.0)
        assert "MAT_HIGH" in result["material"].values

    def test_low_doh_material_not_flagged(self) -> None:
        # DOH = 10 / (30/30) = 10 days → not overstock
        df = pd.DataFrame({
            "material": ["MAT_LOW"],
            "stock_qty": [10],
            "unit_price": [5.0],
            "avg_monthly_consumption": [30],
            "lead_time_days": [7],
            "reorder_point": [5],
            "category": ["CONSUMABLE"],
            "plant": ["HZL_DEMO_01"],
        })
        result = flag_overstock(df, doh_threshold=365.0)
        assert result.empty

    def test_zero_consumption_positive_stock_always_overstock(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT_NMI"],
            "stock_qty": [100],
            "unit_price": [20.0],
            "avg_monthly_consumption": [0],
            "lead_time_days": [30],
            "reorder_point": [5],
            "category": ["SPARE"],
            "plant": ["HZL_DEMO_01"],
        })
        result = flag_overstock(df, doh_threshold=365.0)
        assert "MAT_NMI" in result["material"].values

    def test_columns_preserved(self, stock_df: pd.DataFrame) -> None:
        result = flag_overstock(stock_df)
        assert set(stock_df.columns).issubset(set(result.columns))

    def test_higher_threshold_reduces_count(self, stock_df: pd.DataFrame) -> None:
        count_low = len(flag_overstock(stock_df, doh_threshold=100.0))
        count_high = len(flag_overstock(stock_df, doh_threshold=10000.0))
        assert count_high <= count_low

    def test_all_flagged_exceed_threshold(self, stock_df: pd.DataFrame) -> None:
        threshold = 365.0
        result = flag_overstock(stock_df, doh_threshold=threshold)
        if not result.empty:
            doh = days_on_hand(result)
            assert (doh > threshold).all()


# ---------------------------------------------------------------------------
# Tests — high_holdings_value
# ---------------------------------------------------------------------------

class TestHighHoldingsValue:
    """D2-C: total value of overstocked materials."""

    def test_returns_float(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(high_holdings_value(stock_df), float)

    def test_nonnegative(self, stock_df: pd.DataFrame) -> None:
        assert high_holdings_value(stock_df) >= 0.0

    def test_zero_when_nothing_overstocked(self) -> None:
        # All materials have very high consumption → low DOH → no overstock
        df = pd.DataFrame({
            "material": ["MAT001"],
            "stock_qty": [10],
            "unit_price": [5.0],
            "avg_monthly_consumption": [300],
        })
        assert high_holdings_value(df, doh_threshold=365.0) == pytest.approx(0.0)

    def test_known_high_holdings_value(self) -> None:
        # Single material: stock=500, price=10, consumption=1/month → DOH=15000 → overstock
        df = pd.DataFrame({
            "material": ["MAT_OVER"],
            "stock_qty": [500],
            "unit_price": [10.0],
            "avg_monthly_consumption": [1],
        })
        # 500 * 10 = 5000
        assert high_holdings_value(df, doh_threshold=365.0) == pytest.approx(5000.0)
