"""
D3 — Understock and critical spares at risk.

Logic under test
----------------
flag_understock(df)  → pd.DataFrame
    Returns rows where stock_qty < reorder_point.

flag_critical_at_risk(df)  → pd.DataFrame
    Returns rows where stock_qty < reorder_point AND category is a
    critical/vital/insurance spare (ZSPR material type proxy).

All tests are pure-pandas; no live SAP HANA connection is required.
Run with: RUN_INTEGRATION_TESTS=0 pytest tests/inventory/test_d3_understock.py -v
"""
from __future__ import annotations

import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Logic module
# ---------------------------------------------------------------------------

_CRITICAL_CATEGORIES = {"SPARE", "VITAL", "INSURANCE", "ZSPR"}


def flag_understock(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows where stock_qty < reorder_point."""
    return df[df["stock_qty"] < df["reorder_point"]].copy()


def flag_critical_at_risk(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return rows that are both understocked AND in a critical spare category.
    """
    under = flag_understock(df)
    mask = under["category"].str.upper().isin(_CRITICAL_CATEGORIES)
    return under[mask].copy()


def stockout_risk_days(
    df: pd.DataFrame,
    lead_time_col: str = "lead_time_days",
) -> pd.DataFrame:
    """
    Return understocked rows enriched with days_until_stockout.
    """
    under = flag_understock(df).copy()
    if under.empty:
        under["days_until_stockout"] = pd.Series(dtype=float)
        return under
    daily = under["avg_monthly_consumption"] / 30.0
    safe_daily = daily.where(daily > 0, other=float("inf"))
    under["days_until_stockout"] = (under["stock_qty"] / safe_daily).clip(
        upper=under[lead_time_col]
    )
    return under


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def stock_df() -> pd.DataFrame:
    """Mixed stock with some understocked and some critical spares."""
    return pd.DataFrame(
        {
            "material": ["MAT001", "MAT002", "MAT003", "MAT004", "MAT005"],
            "plant": ["HZL_DEMO_01"] * 5,
            "stock_qty": [5, 50, 0, 200, 3],
            "unit_price": [100.0, 10.0, 500.0, 5.0, 250.0],
            "avg_monthly_consumption": [5, 5, 5, 5, 5],
            "lead_time_days": [30, 14, 60, 7, 90],
            "reorder_point": [10, 10, 10, 10, 10],
            "category": ["SPARE", "CONSUMABLE", "SPARE", "CONSUMABLE", "VITAL"],
        }
    )


# ---------------------------------------------------------------------------
# Tests — flag_understock
# ---------------------------------------------------------------------------

class TestFlagUnderstock:
    """D3-A: understock detection."""

    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(flag_understock(stock_df), pd.DataFrame)

    def test_all_flagged_are_below_reorder(self, stock_df: pd.DataFrame) -> None:
        result = flag_understock(stock_df)
        assert (result["stock_qty"] < result["reorder_point"]).all()

    def test_no_false_positives(self, stock_df: pd.DataFrame) -> None:
        result = flag_understock(stock_df)
        for _, row in result.iterrows():
            assert row["stock_qty"] < row["reorder_point"]

    def test_known_understock_count(self, stock_df: pd.DataFrame) -> None:
        # MAT001 (5<10), MAT003 (0<10), MAT005 (3<10) -> 3 understocked
        result = flag_understock(stock_df)
        assert len(result) == 3

    def test_columns_preserved(self, stock_df: pd.DataFrame) -> None:
        result = flag_understock(stock_df)
        assert set(stock_df.columns).issubset(set(result.columns))

    def test_at_reorder_point_not_flagged(self) -> None:
        df = pd.DataFrame({"stock_qty": [10], "reorder_point": [10]})
        assert flag_understock(df).empty

    def test_above_reorder_point_not_flagged(self) -> None:
        df = pd.DataFrame({"stock_qty": [50], "reorder_point": [10]})
        assert flag_understock(df).empty


# ---------------------------------------------------------------------------
# Tests — flag_critical_at_risk
# ---------------------------------------------------------------------------

class TestFlagCriticalAtRisk:
    """D3-B: critical spares at risk."""

    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(flag_critical_at_risk(stock_df), pd.DataFrame)

    def test_only_critical_categories_returned(self, stock_df: pd.DataFrame) -> None:
        result = flag_critical_at_risk(stock_df)
        for _, row in result.iterrows():
            assert row["category"].upper() in _CRITICAL_CATEGORIES

    def test_all_returned_are_understocked(self, stock_df: pd.DataFrame) -> None:
        result = flag_critical_at_risk(stock_df)
        assert (result["stock_qty"] < result["reorder_point"]).all()

    def test_known_critical_at_risk_materials(self, stock_df: pd.DataFrame) -> None:
        result = flag_critical_at_risk(stock_df)
        assert "MAT001" in result["material"].values
        assert "MAT005" in result["material"].values

    def test_consumable_not_in_critical_at_risk(self, stock_df: pd.DataFrame) -> None:
        result = flag_critical_at_risk(stock_df)
        assert "MAT002" not in result["material"].values


# ---------------------------------------------------------------------------
# Tests — stockout_risk_days
# ---------------------------------------------------------------------------

class TestStockoutRiskDays:
    """D3-C: days-until-stockout for understocked materials."""

    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(stockout_risk_days(stock_df), pd.DataFrame)

    def test_days_until_stockout_column_present(self, stock_df: pd.DataFrame) -> None:
        result = stockout_risk_days(stock_df)
        assert "days_until_stockout" in result.columns

    def test_days_until_stockout_nonnegative(self, stock_df: pd.DataFrame) -> None:
        result = stockout_risk_days(stock_df)
        assert (result["days_until_stockout"] >= 0).all()

    def test_capped_at_lead_time(self, stock_df: pd.DataFrame) -> None:
        result = stockout_risk_days(stock_df)
        assert (result["days_until_stockout"] <= result["lead_time_days"]).all()
