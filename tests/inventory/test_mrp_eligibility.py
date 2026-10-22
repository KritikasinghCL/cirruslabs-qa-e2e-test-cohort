"""
D6 — MRP eligibility per consumption trend.

A material is MRP-eligible when its consumption history is:
  - non-zero (mean > 0), AND
  - sufficiently regular (coefficient of variation <= cv_threshold).

Functions:
  mrp_eligible(history, material, cv_threshold) -> bool
  mrp_eligibility_df(history, cv_threshold)    -> DataFrame with mrp_eligible column
"""
from __future__ import annotations

import pandas as pd

# Default coefficient-of-variation threshold.
# CV = std / mean; lower = more regular.
_DEFAULT_CV_THRESHOLD = 0.5


def mrp_eligible(
    history: pd.DataFrame,
    material: str,
    cv_threshold: float = _DEFAULT_CV_THRESHOLD,
) -> bool:
    """
    Return True if *material* is MRP-eligible.

    Eligibility criteria:
      1. At least one period of consumption data exists.
      2. Mean monthly consumption > 0.
      3. Coefficient of variation (std / mean) <= cv_threshold.

    Parameters
    ----------
    history:
        DataFrame with columns: material, period, consumption.
    material:
        Material code to evaluate.
    cv_threshold:
        Maximum allowed CV.  Default 0.5.
    """
    mat_data = history[history["material"] == material]["consumption"]
    if mat_data.empty:
        return False
    mean = float(mat_data.mean())
    if mean <= 0:
        return False
    std = float(mat_data.std(ddof=1)) if len(mat_data) > 1 else 0.0
    cv = std / mean
    return cv <= cv_threshold


def mrp_eligibility_df(
    history: pd.DataFrame,
    cv_threshold: float = _DEFAULT_CV_THRESHOLD,
) -> pd.DataFrame:
    """
    Return a DataFrame with one row per material and a boolean *mrp_eligible* column.

    Parameters
    ----------
    history:
        DataFrame with columns: material, period, consumption.
    cv_threshold:
        Maximum allowed CV.  Default 0.5.
    """
    materials = history["material"].unique()
    rows = [
        {
            "material": mat,
            "mrp_eligible": mrp_eligible(history, mat, cv_threshold=cv_threshold),
        }
        for mat in materials
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests — MRP eligibility (D6)
# ---------------------------------------------------------------------------

class TestMrpEligible:
    def test_flat_consumption_eligible(self) -> None:
        history = pd.DataFrame({
            "material": ["M1"] * 6,
            "period": pd.date_range("2024-01-01", periods=6, freq="MS"),
            "consumption": [10.0] * 6,
        })
        assert mrp_eligible(history, "M1") is True

    def test_zero_consumption_not_eligible(self) -> None:
        history = pd.DataFrame({
            "material": ["M2"] * 6,
            "period": pd.date_range("2024-01-01", periods=6, freq="MS"),
            "consumption": [0.0] * 6,
        })
        assert mrp_eligible(history, "M2") is False

    def test_unknown_material_not_eligible(self) -> None:
        history = pd.DataFrame({
            "material": ["M1"] * 3,
            "period": pd.date_range("2024-01-01", periods=3, freq="MS"),
            "consumption": [5.0, 6.0, 7.0],
        })
        assert mrp_eligible(history, "UNKNOWN") is False

    def test_high_cv_not_eligible(self) -> None:
        history = pd.DataFrame({
            "material": ["M3"] * 6,
            "period": pd.date_range("2024-01-01", periods=6, freq="MS"),
            "consumption": [1, 100, 0, 200, 1, 150],
        })
        assert mrp_eligible(history, "M3", cv_threshold=0.5) is False

    def test_single_period_eligible_if_nonzero(self) -> None:
        history = pd.DataFrame({
            "material": ["M4"],
            "period": [pd.Timestamp("2024-01-01")],
            "consumption": [5.0],
        })
        # std is 0 for a single point → CV = 0 → eligible
        assert mrp_eligible(history, "M4") is True

    def test_bulk_df_has_mrp_eligible_column(self) -> None:
        history = pd.DataFrame({
            "material": ["MA"] * 4 + ["MB"] * 4,
            "period": list(pd.date_range("2024-01-01", periods=4, freq="MS")) * 2,
            "consumption": [10.0] * 4 + [0.0] * 4,
        })
        result = mrp_eligibility_df(history)
        assert "mrp_eligible" in result.columns
        assert len(result) == 2

    def test_bulk_df_correct_eligibility(self) -> None:
        history = pd.DataFrame({
            "material": ["MA"] * 4 + ["MB"] * 4,
            "period": list(pd.date_range("2024-01-01", periods=4, freq="MS")) * 2,
            "consumption": [10.0] * 4 + [0.0] * 4,
        })
        result = mrp_eligibility_df(history).set_index("material")
        assert result.loc["MA", "mrp_eligible"] == True  # noqa: E712
        assert result.loc["MB", "mrp_eligible"] == False  # noqa: E712
