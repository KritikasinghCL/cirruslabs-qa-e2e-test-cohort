"""
D5 — Purchase requisition (PR) date and quantity suggestions, prioritised.

Logic under test
----------------
suggest_pr_qty(df, forecast_months)  → pd.DataFrame
    PR qty = max(0, avg_monthly_consumption * forecast_months - stock_qty).

prioritise_prs(df, forecast_months)  → pd.DataFrame
    Returns suggest_pr_qty output sorted by pr_qty descending (highest
    urgency first), with a priority_rank column.

suggested_pr_date(lead_time_days, reference_date)  → pd.Timestamp
    Returns reference_date + lead_time_days as the suggested PR date.

All tests are pure-pandas; no live SAP HANA connection is required.
Run with: RUN_INTEGRATION_TESTS=0 pytest tests/inventory/test_d5_pr_suggestions.py -v
"""
from __future__ import annotations

import pytest
import pandas as pd
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Logic module
# ---------------------------------------------------------------------------

def suggest_pr_qty(
    df: pd.DataFrame,
    forecast_months: int = 3,
) -> pd.DataFrame:
    """
    Suggest purchase-requisition quantity for each material.

    PR qty = max(0, avg_monthly_consumption * forecast_months - stock_qty).
    """
    result = df.copy()
    raw = result["avg_monthly_consumption"] * forecast_months - result["stock_qty"]
    result["pr_qty"] = raw.clip(lower=0)
    return result


def prioritise_prs(
    df: pd.DataFrame,
    forecast_months: int = 3,
) -> pd.DataFrame:
    """
    Return PR suggestions sorted by pr_qty descending with a priority_rank column.

    Only rows with pr_qty > 0 are included (no PR needed for overstocked materials).
    """
    result = suggest_pr_qty(df, forecast_months=forecast_months)
    result = result[result["pr_qty"] > 0].copy()
    result = result.sort_values("pr_qty", ascending=False).reset_index(drop=True)
    result["priority_rank"] = result.index + 1
    return result


def suggested_pr_date(
    lead_time_days: int,
    reference_date: date | None = None,
) -> pd.Timestamp:
    """
    Return the suggested PR raise date.

    PR should be raised *lead_time_days* before the stockout date;
    here we return reference_date + lead_time_days as the target delivery
    date (the PR must be raised immediately).
    """
    if reference_date is None:
        reference_date = date.today()
    return pd.Timestamp(reference_date + timedelta(days=lead_time_days))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def stock_df() -> pd.DataFrame:
    """Materials with varying stock levels and consumption rates."""
    return pd.DataFrame(
        {
            "material": ["MAT001", "MAT002", "MAT003", "MAT004"],
            "plant": ["HZL_DEMO_01"] * 4,
            "stock_qty": [10.0, 1000.0, 0.0, 5.0],
            "unit_price": [50.0, 5.0, 200.0, 100.0],
            "avg_monthly_consumption": [20.0, 5.0, 10.0, 8.0],
            "lead_time_days": [30, 14, 60, 45],
            "reorder_point": [15, 10, 10, 10],
            "category": ["SPARE", "CONSUMABLE", "SPARE", "VITAL"],
        }
    )


# ---------------------------------------------------------------------------
# Tests — suggest_pr_qty
# ---------------------------------------------------------------------------

class TestSuggestPRQty:
    """D5-A: PR quantity formula."""

    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(suggest_pr_qty(stock_df), pd.DataFrame)

    def test_pr_qty_column_present(self, stock_df: pd.DataFrame) -> None:
        assert "pr_qty" in suggest_pr_qty(stock_df).columns

    def test_pr_qty_nonnegative(self, stock_df: pd.DataFrame) -> None:
        result = suggest_pr_qty(stock_df)
        assert (result["pr_qty"] >= 0).all()

    def test_known_pr_qty_formula(self) -> None:
        # (20 * 3) - 10 = 50
        df = pd.DataFrame({"stock_qty": [10], "avg_monthly_consumption": [20]})
        result = suggest_pr_qty(df, forecast_months=3)
        assert result.iloc[0]["pr_qty"] == pytest.approx(50.0)

    def test_overstock_gets_zero_pr_qty(self) -> None:
        df = pd.DataFrame({"stock_qty": [1000], "avg_monthly_consumption": [5]})
        result = suggest_pr_qty(df, forecast_months=3)
        assert result.iloc[0]["pr_qty"] == pytest.approx(0.0)

    def test_forecast_months_parameter_honoured(self) -> None:
        df = pd.DataFrame({"stock_qty": [0], "avg_monthly_consumption": [10]})
        r3 = suggest_pr_qty(df, forecast_months=3)
        r6 = suggest_pr_qty(df, forecast_months=6)
        assert r6.iloc[0]["pr_qty"] == pytest.approx(2 * r3.iloc[0]["pr_qty"])

    def test_zero_stock_full_pr_qty(self) -> None:
        df = pd.DataFrame({"stock_qty": [0], "avg_monthly_consumption": [10]})
        result = suggest_pr_qty(df, forecast_months=3)
        assert result.iloc[0]["pr_qty"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Tests — prioritise_prs
# ---------------------------------------------------------------------------

class TestPrioritisePRs:
    """D5-B: PR prioritisation and ranking."""

    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(prioritise_prs(stock_df), pd.DataFrame)

    def test_priority_rank_column_present(self, stock_df: pd.DataFrame) -> None:
        result = prioritise_prs(stock_df)
        assert "priority_rank" in result.columns

    def test_only_positive_pr_qty_included(self, stock_df: pd.DataFrame) -> None:
        result = prioritise_prs(stock_df)
        assert (result["pr_qty"] > 0).all()

    def test_sorted_descending_by_pr_qty(self, stock_df: pd.DataFrame) -> None:
        result = prioritise_prs(stock_df)
        qtys = result["pr_qty"].tolist()
        assert qtys == sorted(qtys, reverse=True)

    def test_rank_one_is_highest_pr_qty(self, stock_df: pd.DataFrame) -> None:
        result = prioritise_prs(stock_df)
        if not result.empty:
            rank1 = result[result["priority_rank"] == 1]
            assert rank1.iloc[0]["pr_qty"] == result["pr_qty"].max()

    def test_overstocked_material_excluded(self, stock_df: pd.DataFrame) -> None:
        # MAT002 has stock=1000, consumption=5 → pr_qty=0 → excluded
        result = prioritise_prs(stock_df)
        assert "MAT002" not in result["material"].values

    def test_rank_is_sequential(self, stock_df: pd.DataFrame) -> None:
        result = prioritise_prs(stock_df)
        if not result.empty:
            assert list(result["priority_rank"]) == list(range(1, len(result) + 1))


# ---------------------------------------------------------------------------
# Tests — suggested_pr_date
# ---------------------------------------------------------------------------

class TestSuggestedPRDate:
    """D5-C: PR date calculation."""

    def test_returns_timestamp(self) -> None:
        result = suggested_pr_date(30, reference_date=date(2025, 12, 1))
        assert isinstance(result, pd.Timestamp)

    def test_known_date_30_days(self) -> None:
        ref = date(2025, 12, 1)
        result = suggested_pr_date(30, reference_date=ref)
        assert result == pd.Timestamp("2025-12-31")

    def test_known_date_60_days(self) -> None:
        ref = date(2025, 11, 1)
        result = suggested_pr_date(60, reference_date=ref)
        assert result == pd.Timestamp("2025-12-31")

    def test_zero_lead_time_returns_reference_date(self) -> None:
        ref = date(2025, 12, 15)
        result = suggested_pr_date(0, reference_date=ref)
        assert result == pd.Timestamp(ref)

    def test_default_reference_is_today(self) -> None:
        result = suggested_pr_date(30)
        expected = pd.Timestamp(date.today() + timedelta(days=30))
        assert result == expected
