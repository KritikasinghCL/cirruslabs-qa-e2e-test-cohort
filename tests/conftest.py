"""Shared pytest fixtures for the Inventory & Forecasting Cell test suite.
All fixtures are pure-Python / pandas — no live SAP HANA connection required.
Integration tests that need a real connection are guarded by the ``integration``
marker and are skipped when RUN_INTEGRATION_TESTS != "1".
"""
from __future__ import annotations

import os
import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Skip guard for integration tests
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(
    items: list[pytest.Item],
) -> None:
    """Skip tests marked ``integration`` unless RUN_INTEGRATION_TESTS=1."""
    if os.getenv("RUN_INTEGRATION_TESTS", "0") != "1":
        skip = pytest.mark.skip(reason="RUN_INTEGRATION_TESTS != 1")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Fixture: minimal stock DataFrame
# ---------------------------------------------------------------------------
@pytest.fixture()
def stock_df() -> pd.DataFrame:
    """Ten materials across two plants with stock and consumption data."""
    return pd.DataFrame(
        {
            "material":                [f"MAT{i:03d}" for i in range(1, 11)],
            "plant":                   ["P001"] * 5 + ["P002"] * 5,
            "stock_qty":               [100, 0, 500, 20, 0, 300, 150, 0, 80, 60],
            "unit_price":              [10.0, 25.0, 5.0, 100.0, 50.0, 8.0, 15.0, 200.0, 30.0, 45.0],
            "avg_monthly_consumption": [10, 0, 5, 0, 0, 30, 10, 0, 8, 6],
            "lead_time_days":          [30, 60, 14, 90, 45, 21, 30, 120, 60, 30],
            "reorder_point":           [15, 5, 10, 5, 3, 45, 20, 10, 12, 9],
            "category":                ["SPARE"] * 5 + ["CONSUMABLE"] * 5,
        }
    )


# ---------------------------------------------------------------------------
# Fixture: consumption history (12 months)
# ---------------------------------------------------------------------------
@pytest.fixture()
def consumption_history_df() -> pd.DataFrame:
    """Monthly consumption for three materials over 12 months."""
    months = pd.date_range("2024-01-01", periods=12, freq="MS")
    rows = []
    for mat, base in [("MAT001", 10), ("MAT003", 5), ("MAT006", 30)]:
        for i, m in enumerate(months):
            rows.append(
                {
                    "material":    mat,
                    "period":      m,
                    "consumption": base + (i % 3),
                }
            )
    return pd.DataFrame(rows)
