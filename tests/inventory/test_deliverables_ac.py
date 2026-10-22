"""
Acceptance-criteria tests for the seven monthly insight-pack deliverables.

Each test class maps directly to one deliverable (D1–D7) as described in the
README.  Tests are named after the acceptance criterion they verify so that a
failing test immediately identifies which criterion is broken.

All tests are pure-pandas — no live SAP HANA connection required.
"""
from __future__ import annotations

import pytest
import pandas as pd

# Re-use the production logic defined in test_inventory_core so there is a
# single implementation under test.
from tests.inventory.test_inventory_core import (
    gross_inventory_value,
    flag_overstock,
    flag_understock,
    flag_nmi,
    flag_smi,
    three_month_forecast,
    suggest_pr_qty,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_stock(overrides: dict | None = None) -> pd.DataFrame:
    """Return a minimal stock DataFrame, optionally with column overrides."""
    base: dict = {
        "material":                ["MAT001", "MAT002", "MAT003"],
        "plant":                   ["P001", "P001", "P002"],
        "stock_qty":               [500, 0, 200],
        "unit_price":              [10.0, 50.0, 5.0],
        "avg_monthly_consumption": [10, 0, 40],
        "lead_time_days":          [30, 60, 14],
        "reorder_point":           [15, 5, 250],
        "category":                ["SPARE", "SPARE", "CONSUMABLE"],
    }
    if overrides:
        base.update(overrides)
    return pd.DataFrame(base)


def _make_history() -> pd.DataFrame:
    """12-month consumption history for two materials."""
    months = pd.date_range("2024-01-01", periods=12, freq="MS")
    rows = []
    for mat, base in [("MAT001", 10), ("MAT003", 40)]:
        for i, m in enumerate(months):
            rows.append({"material": mat, "period": m, "consumption": base + (i % 3)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# D1 — 3-month gross inventory forecast by plant
# AC-D1-1: forecast returns a non-negative numeric value for every material
# AC-D1-2: forecast for a material with no history returns 0
# AC-D1-3: forecast uses only the last 3 months of data
# AC-D1-4: gross inventory value is the sum of stock_qty * unit_price
# AC-D1-5: gross inventory value is non-negative
# ---------------------------------------------------------------------------

class TestD1ForecastAndGrossValue:
    """D1 — 3-month gross inventory forecast by plant."""

    def test_ac_d1_1_forecast_nonnegative_for_all_materials(self) -> None:
        history = _make_history()
        for mat in ["MAT001", "MAT003"]:
            assert three_month_forecast(history, mat) >= 0.0

    def test_ac_d1_2_forecast_zero_for_unknown_material(self) -> None:
        history = _make_history()
        assert three_month_forecast(history, "UNKNOWN_MAT") == 0.0

    def test_ac_d1_3_forecast_uses_last_three_months_only(self) -> None:
        # Build history where the last 3 months differ from earlier months
        months = pd.date_range("2024-01-01", periods=12, freq="MS")
        rows = [
            {"material": "MAT_X", "period": m, "consumption": 1 if i < 9 else 100}
            for i, m in enumerate(months)
        ]
        history = pd.DataFrame(rows)
        # Last 3 months all have consumption=100 → forecast must be 100
        result = three_month_forecast(history, "MAT_X")
        assert result == pytest.approx(100.0)

    def test_ac_d1_4_gross_value_equals_sum_of_stock_times_price(self) -> None:
        df = _make_stock()
        expected = float((df["stock_qty"] * df["unit_price"]).sum())
        assert gross_inventory_value(df) == pytest.approx(expected)

    def test_ac_d1_5_gross_value_nonnegative(self) -> None:
        df = _make_stock()
        assert gross_inventory_value(df) >= 0.0


# ---------------------------------------------------------------------------
# D2 — Overstock / high-holdings analysis
# AC-D2-1: a material with DOH > 365 is flagged as overstock
# AC-D2-2: a material with DOH <= 365 is NOT flagged as overstock
# AC-D2-3: a material with zero consumption and positive stock is always overstock
# AC-D2-4: overstock result preserves all original columns
# AC-D2-5: raising the threshold reduces (or keeps equal) the overstock count
# ---------------------------------------------------------------------------

class TestD2Overstock:
    """D2 — Overstock / high-holdings analysis."""

    def test_ac_d2_1_high_doh_material_is_flagged(self) -> None:
        # DOH = 500 / (10/30) = 1500 days → overstock at 365-day threshold
        df = pd.DataFrame({
            "material": ["MAT_HIGH"],
            "stock_qty": [500],
            "unit_price": [10.0],
            "avg_monthly_consumption": [10],
            "lead_time_days": [30],
            "reorder_point": [15],
            "category": ["SPARE"],
            "plant": ["P001"],
        })
        result = flag_overstock(df, doh_threshold=365.0)
        assert "MAT_HIGH" in result["material"].values

    def test_ac_d2_2_low_doh_material_not_flagged(self) -> None:
        # DOH = 10 / (30/30) = 10 days → not overstock
        df = pd.DataFrame({
            "material": ["MAT_LOW"],
            "stock_qty": [10],
            "unit_price": [5.0],
            "avg_monthly_consumption": [30],
            "lead_time_days": [7],
            "reorder_point": [5],
            "category": ["CONSUMABLE"],
            "plant": ["P001"],
        })
        result = flag_overstock(df, doh_threshold=365.0)
        assert result.empty

    def test_ac_d2_3_zero_consumption_positive_stock_always_overstock(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT_NMI"],
            "stock_qty": [100],
            "unit_price": [20.0],
            "avg_monthly_consumption": [0],
            "lead_time_days": [30],
            "reorder_point": [5],
            "category": ["SPARE"],
            "plant": ["P001"],
        })
        result = flag_overstock(df, doh_threshold=365.0)
        assert "MAT_NMI" in result["material"].values

    def test_ac_d2_4_overstock_preserves_all_columns(self) -> None:
        df = _make_stock()
        result = flag_overstock(df)
        assert set(df.columns).issubset(set(result.columns))

    def test_ac_d2_5_higher_threshold_reduces_overstock_count(self) -> None:
        df = _make_stock()
        count_low = len(flag_overstock(df, doh_threshold=100.0))
        count_high = len(flag_overstock(df, doh_threshold=10000.0))
        assert count_high <= count_low


# ---------------------------------------------------------------------------
# D3 — Understock / critical spares at risk
# AC-D3-1: a material with stock_qty < reorder_point is flagged as understock
# AC-D3-2: a material with stock_qty >= reorder_point is NOT flagged
# AC-D3-3: all flagged rows satisfy stock_qty < reorder_point (no false positives)
# AC-D3-4: understock result preserves all original columns
# ---------------------------------------------------------------------------

class TestD3Understock:
    """D3 — Understock / critical spares at risk."""

    def test_ac_d3_1_below_reorder_point_is_flagged(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT_UNDER"],
            "stock_qty": [3],
            "unit_price": [100.0],
            "avg_monthly_consumption": [5],
            "lead_time_days": [30],
            "reorder_point": [10],
            "category": ["SPARE"],
            "plant": ["P001"],
        })
        result = flag_understock(df)
        assert "MAT_UNDER" in result["material"].values

    def test_ac_d3_2_at_or_above_reorder_point_not_flagged(self) -> None:
        df = pd.DataFrame({
            "material": ["MAT_OK"],
            "stock_qty": [50],
            "unit_price": [10.0],
            "avg_monthly_consumption": [5],
            "lead_time_days": [14],
            "reorder_point": [10],
            "category": ["CONSUMABLE"],
            "plant": ["P002"],
        })
        result = flag_understock(df)
        assert result.empty

    def test_ac_d3_3_no_false_positives(self) -> None:
        df = _make_stock()
        result = flag_understock(df)
        for _, row in result.iterrows():
            assert row["stock_qty"] < row["reorder_point"]

    def test_ac_d3_4_understock_preserves_all_columns(self) -> None:
        df = _make_stock()
        result = flag_understock(df)
        assert set(df.columns).issubset(set(result.columns))


# ---------------------------------------------------------------------------
# D4 — Non-moving and slow-moving materials (NMI / SMI)
# AC-D4-1: NMI requires zero consumption AND positive stock
# AC-D4-2: a material with zero stock is NOT flagged as NMI even if consumption=0
# AC-D4-3: SMI requires consumption > 0 AND consumption < threshold AND stock > 0
# AC-D4-4: NMI and SMI sets are disjoint (a material cannot be both)
# AC-D4-5: SMI threshold is configurable
# ---------------------------------------------------------------------------

class TestD4NmiSmi:
    """D4 — Non-moving and slow-moving materials."""

    def test_ac_d4_1_nmi_requires_zero_consumption_and_positive_stock(self) -> None:
        df = pd.DataFrame({
            "stock_qty": [100, 0, 50],
            "avg_monthly_consumption": [0, 0, 5],
        })
        result = flag_nmi(df)
        assert len(result) == 1
        assert result.iloc[0]["stock_qty"] == 100

    def test_ac_d4_2_zero_stock_not_flagged_as_nmi(self) -> None:
        df = pd.DataFrame({
            "stock_qty": [0],
            "avg_monthly_consumption": [0],
        })
        result = flag_nmi(df)
        assert result.empty

    def test_ac_d4_3_smi_consumption_in_range_with_positive_stock(self) -> None:
        df = pd.DataFrame({
            "stock_qty": [200, 0, 50],
            "avg_monthly_consumption": [2.0, 2.0, 10.0],
        })
        result = flag_smi(df, low_threshold=5.0)
        assert len(result) == 1
        assert result.iloc[0]["stock_qty"] == 200

    def test_ac_d4_4_nmi_and_smi_are_disjoint(self) -> None:
        df = _make_stock()
        nmi_mats = set(flag_nmi(df).index)
        smi_mats = set(flag_smi(df).index)
        assert nmi_mats.isdisjoint(smi_mats)

    def test_ac_d4_5_smi_threshold_is_configurable(self) -> None:
        df = pd.DataFrame({
            "stock_qty": [100, 100],
            "avg_monthly_consumption": [3.0, 8.0],
        })
        result_low = flag_smi(df, low_threshold=5.0)
        result_high = flag_smi(df, low_threshold=10.0)
        assert len(result_low) == 1
        assert len(result_high) == 2


# ---------------------------------------------------------------------------
# D5 — Prioritised purchase requisition suggestions
# AC-D5-1: PR qty = (avg_monthly_consumption * months) - stock_qty, floored at 0
# AC-D5-2: an overstocked material gets PR qty = 0
# AC-D5-3: PR qty column is always present in the result
# AC-D5-4: PR qty is non-negative for every row
# AC-D5-5: forecast_months parameter is honoured
# ---------------------------------------------------------------------------

class TestD5PurchaseRequisition:
    """D5 — Prioritised purchase requisition suggestions."""

    def test_ac_d5_1_pr_qty_formula(self) -> None:
        df = pd.DataFrame({
            "stock_qty": [10],
            "avg_monthly_consumption": [20],
            "reorder_point": [15],
        })
        result = suggest_pr_qty(df, forecast_months=3)
        assert result.iloc[0]["pr_qty"] == pytest.approx(50.0)  # (20*3)-10

    def test_ac_d5_2_overstock_gets_zero_pr_qty(self) -> None:
        df = pd.DataFrame({
            "stock_qty": [1000],
            "avg_monthly_consumption": [5],
            "reorder_point": [10],
        })
        result = suggest_pr_qty(df, forecast_months=3)
        assert result.iloc[0]["pr_qty"] == pytest.approx(0.0)

    def test_ac_d5_3_pr_qty_column_always_present(self) -> None:
        df = _make_stock()
        result = suggest_pr_qty(df)
        assert "pr_qty" in result.columns

    def test_ac_d5_4_pr_qty_nonnegative_for_all_rows(self) -> None:
        df = _make_stock()
        result = suggest_pr_qty(df)
        assert (result["pr_qty"] >= 0).all()

    def test_ac_d5_5_forecast_months_parameter_honoured(self) -> None:
        df = pd.DataFrame({
            "stock_qty": [0],
            "avg_monthly_consumption": [10],
            "reorder_point": [5],
        })
        r3 = suggest_pr_qty(df, forecast_months=3)
        r6 = suggest_pr_qty(df, forecast_months=6)
        assert r6.iloc[0]["pr_qty"] == pytest.approx(2 * r3.iloc[0]["pr_qty"])


# ---------------------------------------------------------------------------
# D6 — MRP eligibility per consumption trend (imported from dedicated module)
# AC-D6-1: a material with consistent consumption is MRP-eligible
# AC-D6-2: a material with zero consumption is NOT MRP-eligible
# AC-D6-3: a material with highly erratic consumption is NOT MRP-eligible
# AC-D6-4: MRP eligibility result contains a boolean/flag column
# AC-D6-5: coefficient-of-variation threshold is configurable
# ---------------------------------------------------------------------------

class TestD6MrpEligibility:
    """D6 — MRP eligibility per consumption trend."""

    def test_ac_d6_1_consistent_consumption_is_mrp_eligible(self) -> None:
        from tests.inventory.test_mrp_eligibility import mrp_eligible
        history = pd.DataFrame({
            "material": ["MAT_STABLE"] * 12,
            "period": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "consumption": [10.0] * 12,  # perfectly flat
        })
        result = mrp_eligible(history, "MAT_STABLE")
        assert result is True

    def test_ac_d6_2_zero_consumption_not_mrp_eligible(self) -> None:
        from tests.inventory.test_mrp_eligibility import mrp_eligible
        history = pd.DataFrame({
            "material": ["MAT_ZERO"] * 12,
            "period": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "consumption": [0.0] * 12,
        })
        result = mrp_eligible(history, "MAT_ZERO")
        assert result is False

    def test_ac_d6_3_erratic_consumption_not_mrp_eligible(self) -> None:
        from tests.inventory.test_mrp_eligibility import mrp_eligible
        history = pd.DataFrame({
            "material": ["MAT_ERRATIC"] * 12,
            "period": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "consumption": [1, 200, 0, 150, 2, 300, 0, 100, 5, 250, 1, 180],
        })
        result = mrp_eligible(history, "MAT_ERRATIC")
        assert result is False

    def test_ac_d6_4_bulk_result_has_mrp_eligible_column(self) -> None:
        from tests.inventory.test_mrp_eligibility import mrp_eligibility_df
        history = pd.DataFrame({
            "material": ["MAT_A"] * 6 + ["MAT_B"] * 6,
            "period": list(pd.date_range("2024-01-01", periods=6, freq="MS")) * 2,
            "consumption": [10.0] * 6 + [0.0] * 6,
        })
        result = mrp_eligibility_df(history)
        assert "mrp_eligible" in result.columns

    def test_ac_d6_5_cv_threshold_is_configurable(self) -> None:
        from tests.inventory.test_mrp_eligibility import mrp_eligible
        history = pd.DataFrame({
            "material": ["MAT_MID"] * 12,
            "period": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "consumption": [5, 10, 15, 5, 10, 15, 5, 10, 15, 5, 10, 15],
        })
        # With a tight threshold this material is erratic; with a loose one it passes
        assert mrp_eligible(history, "MAT_MID", cv_threshold=0.2) is False
        assert mrp_eligible(history, "MAT_MID", cv_threshold=1.0) is True


# ---------------------------------------------------------------------------
# D7 — Duplicate material code detection
# AC-D7-1: identical material codes in the same plant are flagged as duplicates
# AC-D7-2: the same material code in different plants is NOT a duplicate
# AC-D7-3: a material code that appears only once is NOT a duplicate
# AC-D7-4: duplicate result contains the material and plant columns
# AC-D7-5: duplicate detection is case-insensitive on the material code
# ---------------------------------------------------------------------------

class TestD7DuplicateDetection:
    """D7 — Duplicate material code detection."""

    def test_ac_d7_1_same_code_same_plant_is_duplicate(self) -> None:
        from tests.inventory.test_duplicate_detection import flag_duplicates
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001", "MAT002"],
            "plant": ["P001", "P001", "P001"],
            "stock_qty": [10, 20, 30],
        })
        result = flag_duplicates(df)
        assert "MAT001" in result["material"].values

    def test_ac_d7_2_same_code_different_plant_not_duplicate(self) -> None:
        from tests.inventory.test_duplicate_detection import flag_duplicates
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001"],
            "plant": ["P001", "P002"],
            "stock_qty": [10, 20],
        })
        result = flag_duplicates(df)
        assert result.empty

    def test_ac_d7_3_unique_code_not_flagged(self) -> None:
        from tests.inventory.test_duplicate_detection import flag_duplicates
        df = pd.DataFrame({
            "material": ["MAT001", "MAT002", "MAT003"],
            "plant": ["P001", "P001", "P001"],
            "stock_qty": [10, 20, 30],
        })
        result = flag_duplicates(df)
        assert result.empty

    def test_ac_d7_4_result_contains_material_and_plant_columns(self) -> None:
        from tests.inventory.test_duplicate_detection import flag_duplicates
        df = pd.DataFrame({
            "material": ["MAT001", "MAT001"],
            "plant": ["P001", "P001"],
            "stock_qty": [10, 20],
        })
        result = flag_duplicates(df)
        assert "material" in result.columns
        assert "plant" in result.columns

    def test_ac_d7_5_detection_is_case_insensitive(self) -> None:
        from tests.inventory.test_duplicate_detection import flag_duplicates
        df = pd.DataFrame({
            "material": ["mat001", "MAT001"],
            "plant": ["P001", "P001"],
            "stock_qty": [10, 20],
        })
        result = flag_duplicates(df)
        assert not result.empty
