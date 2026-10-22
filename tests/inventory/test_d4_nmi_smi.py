"""
D4 — Non-moving (NMI) and slow-moving (SMI) material flagging.

Logic under test
----------------
flag_nmi(df)  → pd.DataFrame
    Non-moving: avg_monthly_consumption == 0 AND stock_qty > 0.

flag_smi(df, low_threshold, high_threshold)  → pd.DataFrame
    Slow-moving: 0 < avg_monthly_consumption < low_threshold AND stock_qty > 0.

nmi_smi_value(df)  → dict
    Returns {"nmi_value": float, "smi_value": float} inventory values.

All tests are pure-pandas; no live SAP HANA connection is required.
Run with: RUN_INTEGRATION_TESTS=0 pytest tests/inventory/test_d4_nmi_smi.py -v
"""
from __future__ import annotations

import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Logic module
# ---------------------------------------------------------------------------

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
    Slow-moving: avg_monthly_consumption is between *high_threshold* (exclusive)
    and *low_threshold* (exclusive), AND stock_qty > 0.
    """
    mask = (
        (df["avg_monthly_consumption"] > high_threshold)
        & (df["avg_monthly_consumption"] < low_threshold)
        & (df["stock_qty"] > 0)
    )
    return df[mask].copy()


def nmi_smi_value(df: pd.DataFrame, smi_threshold: float = 5.0) -> dict:
    """
    Return the total inventory value tied up in NMI and SMI materials.
    """
    nmi = flag_nmi(df)
    smi = flag_smi(df, low_threshold=smi_threshold)
    nmi_val = float((nmi["stock_qty"] * nmi["unit_price"]).sum()) if not nmi.empty else 0.0
    smi_val = float((smi["stock_qty"] * smi["unit_price"]).sum()) if not smi.empty else 0.0
    return {
        "nmi_value": nmi_val,
        "smi_value": smi_val,
        "nmi_count": len(nmi),
        "smi_count": len(smi),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def stock_df() -> pd.DataFrame:
    """Materials spanning NMI, SMI and normal consumption."""
    return pd.DataFrame(
        {
            "material": ["MAT001", "MAT002", "MAT003", "MAT004", "MAT005", "MAT006"],
            "plant": ["HZL_DEMO_01"] * 6,
            "stock_qty": [100, 0, 50, 200, 80, 0],
            "unit_price": [10.0, 25.0, 5.0, 8.0, 15.0, 50.0],
            "avg_monthly_consumption": [0, 0, 2.0, 30.0, 3.5, 10.0],
            "category": ["SPARE", "SPARE", "SPARE", "CONSUMABLE", "SPARE", "CONSUMABLE"],
        }
    )


# ---------------------------------------------------------------------------
# Tests — flag_nmi
# ---------------------------------------------------------------------------

class TestFlagNMI:
    """D4-A: non-moving material identification."""

    def test_returns_dataframe(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(flag_nmi(stock_df), pd.DataFrame)

    def test_all_nmi_have_zero_consumption(self, stock_df: pd.DataFrame) -> None:
        result = flag_nmi(stock_df)
        assert (result["avg_monthly_consumption"] == 0).all()

    def test_all_nmi_have_positive_stock(self, stock_df: pd.DataFrame) -> None:
        result = flag_nmi(stock_df)
        assert (result["stock_qty"] > 0).all()

    def test_zero_stock_zero_consumption_not_nmi(self) -> None:
        df = pd.DataFrame({"stock_qty": [0], "avg_monthly_consumption": [0]})
        assert flag_nmi(df).empty

    def test_known_nmi_count(self, stock_df: pd.DataFrame) -> None:
        result = flag_nmi(stock_df)
        assert len(result) == 1
        assert result.iloc[0]["material"] == "MAT001"

    def test_columns_preserved(self, stock_df: pd.DataFrame) -> None:
        result = flag_nmi(stock_df)
        assert set(stock_df.columns).issubset(set(result.columns))


# ---------------------------------------------------------------------------
# Tests — flag_smi
# ---------------------------------------------------------------------------

class TestFlagSMI:
    """D4-B: slow-moving material identification."""

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

    def test_known_smi_materials(self, stock_df: pd.DataFrame) -> None:
        result = flag_smi(stock_df, low_threshold=5.0)
        assert "MAT003" in result["material"].values
        assert "MAT005" in result["material"].values

    def test_threshold_configurable(self) -> None:
        df = pd.DataFrame({
            "stock_qty": [100, 100],
            "avg_monthly_consumption": [3.0, 8.0],
        })
        result_low = flag_smi(df, low_threshold=5.0)
        result_high = flag_smi(df, low_threshold=10.0)
        assert len(result_low) == 1
        assert len(result_high) == 2

    def test_nmi_and_smi_are_disjoint(self, stock_df: pd.DataFrame) -> None:
        nmi_idx = set(flag_nmi(stock_df).index)
        smi_idx = set(flag_smi(stock_df).index)
        assert nmi_idx.isdisjoint(smi_idx)


# ---------------------------------------------------------------------------
# Tests — nmi_smi_value
# ---------------------------------------------------------------------------

class TestNmiSmiValue:
    """D4-C: inventory value locked in NMI/SMI materials."""

    def test_returns_dict(self, stock_df: pd.DataFrame) -> None:
        assert isinstance(nmi_smi_value(stock_df), dict)

    def test_required_keys_present(self, stock_df: pd.DataFrame) -> None:
        result = nmi_smi_value(stock_df)
        for key in ["nmi_value", "smi_value", "nmi_count", "smi_count"]:
            assert key in result

    def test_values_nonnegative(self, stock_df: pd.DataFrame) -> None:
        result = nmi_smi_value(stock_df)
        assert result["nmi_value"] >= 0.0
        assert result["smi_value"] >= 0.0

    def test_known_nmi_value(self, stock_df: pd.DataFrame) -> None:
        result = nmi_smi_value(stock_df)
        assert result["nmi_value"] == pytest.approx(1000.0)

    def test_counts_match_flag_functions(self, stock_df: pd.DataFrame) -> None:
        result = nmi_smi_value(stock_df)
        assert result["nmi_count"] == len(flag_nmi(stock_df))
        assert result["smi_count"] == len(flag_smi(stock_df))
