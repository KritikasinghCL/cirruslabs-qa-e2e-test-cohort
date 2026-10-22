"""
D6 — MRP eligibility per consumption trend.

Logic under test
----------------
mrp_eligible(history, material, cv_threshold)  → bool
    A material is MRP-eligible when:
      1. It has at least one period of consumption data.
      2. Mean monthly consumption > 0.
      3. Coefficient of variation (std / mean) <= cv_threshold.

mrp_eligibility_df(history, cv_threshold)  → pd.DataFrame
    Returns one row per material with a boolean mrp_eligible column.

All tests are pure-pandas; no live SAP HANA connection is required.
Run with: RUN_INTEGRATION_TESTS=0 pytest tests/inventory/test_d6_mrp_eligibility.py -v
"""
from __future__ import annotations

import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Logic module
# ---------------------------------------------------------------------------

_DEFAULT_CV_THRESHOLD = 0.5


def mrp_eligible(
    history: pd.DataFrame,
    material: str,
    cv_threshold: float = _DEFAULT_CV_THRESHOLD,
) -> bool:
    """
    Return True if *material* is MRP-eligible.

    Parameters
    ----------
    history : DataFrame with columns: material, period, consumption.
    material : Material code to evaluate.
    cv_threshold : Maximum allowed coefficient of variation (default 0.5).
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
    Return a DataFrame with one row per material and a boolean mrp_eligible column.

    Parameters
    ----------
    history : DataFrame with columns: material, period, consumption.
    cv_threshold : Maximum allowed CV (default 0.5).
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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def stable_history() -> pd.DataFrame:
    """Perfectly flat consumption — CV = 0 → always eligible."""
    return pd.DataFrame({
        "material": ["MAT_STABLE"] * 12,
        "period": pd.date_range("2024-01-01", periods=12, freq="MS"),
        "consumption": [10.0] * 12,
    })


@pytest.fixture()
def erratic_history() -> pd.DataFrame:
    """Highly erratic consumption — CV >> 0.5 → not eligible."""
    return pd.DataFrame({
        "material": ["MAT_ERRATIC"] * 12,
        "period": pd.date_range("2024-01-01", periods=12, freq="MS"),
        "consumption": [1, 200, 0, 150, 2, 300, 0, 100, 5, 250, 1, 180],
    })


@pytest.fixture()
def mixed_history() -> pd.DataFrame:
    """Two materials: one stable (eligible), one zero (not eligible)."""
    return pd.DataFrame({
        "material": ["MAT_A"] * 6 + ["MAT_B"] * 6,
        "period": list(pd.date_range("2024-01-01", periods=6, freq="MS")) * 2,
        "consumption": [10.0] * 6 + [0.0] * 6,
    })


# ---------------------------------------------------------------------------
# Tests — mrp_eligible
# ---------------------------------------------------------------------------

class TestMrpEligible:
    """D6-A: single-material eligibility check."""

    def test_flat_consumption_is_eligible(self, stable_history: pd.DataFrame) -> None:
        assert mrp_eligible(stable_history, "MAT_STABLE") is True

    def test_zero_consumption_not_eligible(self) -> None:
        history = pd.DataFrame({
            "material": ["MAT_ZERO"] * 6,
            "period": pd.date_range("2024-01-01", periods=6, freq="MS"),
            "consumption": [0.0] * 6,
        })
        assert mrp_eligible(history, "MAT_ZERO") is False

    def test_unknown_material_not_eligible(self, stable_history: pd.DataFrame) -> None:
        assert mrp_eligible(stable_history, "UNKNOWN_MAT") is False

    def test_erratic_consumption_not_eligible(self, erratic_history: pd.DataFrame) -> None:
        assert mrp_eligible(erratic_history, "MAT_ERRATIC", cv_threshold=0.5) is False

    def test_single_period_nonzero_is_eligible(self) -> None:
        # std = 0 for a single data point → CV = 0 → eligible
        history = pd.DataFrame({
            "material": ["MAT_ONE"],
            "period": [pd.Timestamp("2025-12-01")],
            "consumption": [5.0],
        })
        assert mrp_eligible(history, "MAT_ONE") is True

    def test_cv_threshold_configurable(self) -> None:
        history = pd.DataFrame({
            "material": ["MAT_MID"] * 12,
            "period": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "consumption": [5, 10, 15, 5, 10, 15, 5, 10, 15, 5, 10, 15],
        })
        # Tight threshold → erratic; loose threshold → eligible
        assert mrp_eligible(history, "MAT_MID", cv_threshold=0.2) is False
        assert mrp_eligible(history, "MAT_MID", cv_threshold=1.0) is True

    def test_returns_bool(self, stable_history: pd.DataFrame) -> None:
        result = mrp_eligible(stable_history, "MAT_STABLE")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Tests — mrp_eligibility_df
# ---------------------------------------------------------------------------

class TestMrpEligibilityDf:
    """D6-B: bulk eligibility DataFrame."""

    def test_returns_dataframe(self, mixed_history: pd.DataFrame) -> None:
        assert isinstance(mrp_eligibility_df(mixed_history), pd.DataFrame)

    def test_mrp_eligible_column_present(self, mixed_history: pd.DataFrame) -> None:
        result = mrp_eligibility_df(mixed_history)
        assert "mrp_eligible" in result.columns

    def test_one_row_per_material(self, mixed_history: pd.DataFrame) -> None:
        result = mrp_eligibility_df(mixed_history)
        assert len(result) == mixed_history["material"].nunique()

    def test_stable_material_eligible(self, mixed_history: pd.DataFrame) -> None:
        result = mrp_eligibility_df(mixed_history).set_index("material")
        assert result.loc["MAT_A", "mrp_eligible"] is True

    def test_zero_consumption_material_not_eligible(self, mixed_history: pd.DataFrame) -> None:
        result = mrp_eligibility_df(mixed_history).set_index("material")
        assert result.loc["MAT_B", "mrp_eligible"] is False

    def test_material_column_present(self, mixed_history: pd.DataFrame) -> None:
        result = mrp_eligibility_df(mixed_history)
        assert "material" in result.columns

    def test_bulk_cv_threshold_propagated(self) -> None:
        history = pd.DataFrame({
            "material": ["MAT_MID"] * 12,
            "period": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "consumption": [5, 10, 15, 5, 10, 15, 5, 10, 15, 5, 10, 15],
        })
        tight = mrp_eligibility_df(history, cv_threshold=0.2).set_index("material")
        loose = mrp_eligibility_df(history, cv_threshold=1.0).set_index("material")
        assert tight.loc["MAT_MID", "mrp_eligible"] is False
        assert loose.loc["MAT_MID", "mrp_eligible"] is True
