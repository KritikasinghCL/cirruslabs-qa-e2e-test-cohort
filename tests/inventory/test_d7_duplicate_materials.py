"""
D7 — Duplicate material code detection.

Logic under test
----------------
flag_duplicates(df)  → pd.DataFrame
    Returns rows where the (material, plant) pair appears more than once.
    Comparison is case-insensitive on the material code.

duplicate_summary(df)  → pd.DataFrame
    Returns one row per duplicate (material, plant) group with a count column.

All tests are pure-pandas; no live SAP HANA connection is required.
Run with: RUN_INTEGRATION_TESTS=0 pytest tests/inventory/test_d7_duplicate_materials.py -v
"""
from __future__ import annotations

import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Logic module
# ---------------------------------------------------------------------------

def flag_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return rows where the (material, plant) pair appears more than once.

    Comparison is case-insensitive on the material code.
    """
    work = df.copy()
    work["_material_lower"] = work["material"].str.lower()
    dup_mask = work.duplicated(subset=["_material_lower", "plant"], keep=False)
    return df[dup_mask].copy()


def duplicate_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return one row per duplicate (material, plant) group with a ``count`` column.

    Only groups with count > 1 are returned.
    """
    work = df.copy()
    work["_material_lower"] = work["material"].str.lower()
    counts = (
        work.groupby(["_material_lower", "plant"])
        .size()
        .reset_index(name="count")
    )
    dups = counts[counts["count"] > 1].copy()
    dups = dups.rename(columns={"_material_lower": "material_lower"})
    return dups.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def dup_df() -> pd.DataFrame:
    """DataFrame with one duplicate pair and one unique material."""
    return pd.DataFrame({
        "material": ["MAT001", "MAT001", "MAT002"],
        "plant": ["HZL_DEMO_01", "HZL_DEMO_01", "HZL_DEMO_01"],
        "stock_qty": [10, 20, 30],
        "unit_price": [5.0, 5.0, 10.0],
    })


# ---------------------------------------------------------------------------
# Tests — flag_duplicates
# ---------------------------------------------------------------------------

class TestFlagDuplicates:
    """D7-A: duplicate row detection."""

    def test_returns_dataframe(self, dup_df: pd.DataFrame) -> None:
        assert isinstance(flag_duplicates(dup_df), pd.DataFrame)

    def test_same_code_same_plant_flagged(self, dup_df: pd.DataFrame) -> None:
        result = flag_duplicates(dup_df)
        assert len(result) == 2
        assert set(result["material"]) == {"MAT001"}

    def test_unique_code_not_flagged(self, dup_df: pd.DataFrame) -> None:
        result = flag_duplicates(dup_df)
        assert "MAT002" not in result["material"].values

    def test_same_code_different_plant_not_flagged(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001"],
            "plant": ["HZL_DEMO_01", "HZL_DEMO_02"],
            "stock_qty": [10, 20],
        })
        assert flag_duplicates(df).empty

    def test_case_insensitive(self) -> None:
        df = pd.DataFrame({
            "material": ["mat001", "MAT001"],
            "plant": ["HZL_DEMO_01", "HZL_DEMO_01"],
            "stock_qty": [10, 20],
        })
        result = flag_duplicates(df)
        assert len(result) == 2

    def test_columns_preserved(self, dup_df: pd.DataFrame) -> None:
        result = flag_duplicates(dup_df)
        assert set(dup_df.columns).issubset(set(result.columns))

    def test_empty_input_returns_empty(self) -> None:
        df = pd.DataFrame(columns=["material", "plant", "stock_qty"])
        assert flag_duplicates(df).empty

    def test_three_duplicates_all_flagged(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001", "MAT001"],
            "plant": ["HZL_DEMO_01"] * 3,
            "stock_qty": [10, 20, 30],
        })
        result = flag_duplicates(df)
        assert len(result) == 3

    def test_no_extra_columns_added(self, dup_df: pd.DataFrame) -> None:
        result = flag_duplicates(dup_df)
        assert set(result.columns) == set(dup_df.columns)


# ---------------------------------------------------------------------------
# Tests — duplicate_summary
# ---------------------------------------------------------------------------

class TestDuplicateSummary:
    """D7-B: duplicate group summary."""

    def test_returns_dataframe(self, dup_df: pd.DataFrame) -> None:
        assert isinstance(duplicate_summary(dup_df), pd.DataFrame)

    def test_count_column_present(self, dup_df: pd.DataFrame) -> None:
        result = duplicate_summary(dup_df)
        assert "count" in result.columns

    def test_all_counts_greater_than_one(self, dup_df: pd.DataFrame) -> None:
        result = duplicate_summary(dup_df)
        assert (result["count"] > 1).all()

    def test_known_count(self, dup_df: pd.DataFrame) -> None:
        result = duplicate_summary(dup_df)
        assert result.iloc[0]["count"] == 2

    def test_empty_when_no_duplicates(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT001", "MAT002"],
            "plant": ["HZL_DEMO_01", "HZL_DEMO_01"],
            "stock_qty": [10, 20],
        })
        result = duplicate_summary(df)
        assert result.empty
