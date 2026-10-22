"""
D7 — Duplicate material code detection.

A duplicate is defined as the same material code (case-insensitive) appearing
more than once within the same plant.

Functions:
  flag_duplicates(df) -> DataFrame of duplicate rows
"""
from __future__ import annotations

import pandas as pd


def flag_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return rows where the (material, plant) pair appears more than once.

    Comparison is case-insensitive on the material code.

    Parameters
    ----------
    df:
        DataFrame that must contain at least ``material`` and ``plant`` columns.

    Returns
    -------
    pd.DataFrame
        Subset of *df* containing only the duplicate rows, with the original
        column set preserved.
    """
    work = df.copy()
    work["_material_lower"] = work["material"].str.lower()
    dup_mask = work.duplicated(subset=["_material_lower", "plant"], keep=False)
    return df[dup_mask].copy()


# ---------------------------------------------------------------------------
# Tests — duplicate material detection (D7)
# ---------------------------------------------------------------------------

class TestFlagDuplicates:
    def test_same_code_same_plant_flagged(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001", "MAT002"],
            "plant": ["P001", "P001", "P001"],
            "stock_qty": [10, 20, 30],
        })
        result = flag_duplicates(df)
        assert len(result) == 2
        assert set(result["material"]) == {"MAT001"}

    def test_same_code_different_plant_not_flagged(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001"],
            "plant": ["P001", "P002"],
            "stock_qty": [10, 20],
        })
        result = flag_duplicates(df)
        assert result.empty

    def test_unique_codes_not_flagged(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT001", "MAT002", "MAT003"],
            "plant": ["P001", "P001", "P001"],
            "stock_qty": [10, 20, 30],
        })
        result = flag_duplicates(df)
        assert result.empty

    def test_case_insensitive(self) -> None:
        df = pd.DataFrame({
            "material": ["mat001", "MAT001"],
            "plant": ["P001", "P001"],
            "stock_qty": [10, 20],
        })
        result = flag_duplicates(df)
        assert len(result) == 2

    def test_result_preserves_original_columns(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001"],
            "plant": ["P001", "P001"],
            "stock_qty": [10, 20],
            "unit_price": [5.0, 5.0],
        })
        result = flag_duplicates(df)
        assert set(df.columns).issubset(set(result.columns))

    def test_empty_input_returns_empty(self) -> None:
        df = pd.DataFrame(columns=["material", "plant", "stock_qty"])
        result = flag_duplicates(df)
        assert result.empty

    def test_three_duplicates_all_flagged(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001", "MAT001"],
            "plant": ["P001", "P001", "P001"],
            "stock_qty": [10, 20, 30],
        })
        result = flag_duplicates(df)
        assert len(result) == 3
