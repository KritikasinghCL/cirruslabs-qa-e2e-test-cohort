"""Tests for the inventory dashboard data — S-26 / S-27 acceptance criteria.

Validates the 5 dashboard panels against their JSON data files:
  Panel 1: Summary card — all tables with row counts and column counts
  Panel 2: Gross inventory value across plants
  Panel 3: Stock by material category
  Panel 4: Days on hand distribution
  Panel 5: NMI/SMI flag summary

Also validates the prepare_data.py script structure and the dashboard
index.html file existence and basic structure.

All tests run against the pre-generated JSON files in dashboard/data/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
DATA_DIR = DASHBOARD_DIR / "data"


def _load_json(filename: str) -> dict:
    """Load a JSON file from dashboard/data/."""
    path = DATA_DIR / filename
    assert path.exists(), f"Dashboard data file missing: {filename}"
    return json.loads(path.read_text(encoding="utf-8"))


class TestPanel1_TableSummary:
    """Panel 1: Summary card showing all tables with row counts and column counts."""

    def test_manifest_file_exists(self):
        assert (DATA_DIR / "manifest.json").exists()

    def test_manifest_has_tables_key(self):
        data = _load_json("manifest.json")
        assert "tables" in data

    def test_manifest_has_total_tables_count(self):
        data = _load_json("manifest.json")
        assert "total_tables" in data
        assert isinstance(data["total_tables"], int)
        assert data["total_tables"] > 0

    def test_manifest_total_matches_table_list_length(self):
        data = _load_json("manifest.json")
        assert data["total_tables"] == len(data["tables"])

    def test_each_table_has_required_fields(self):
        data = _load_json("manifest.json")
        for tbl in data["tables"]:
            assert "table_name" in tbl, f"Missing table_name in {tbl}"
            assert "row_count" in tbl, f"Missing row_count in {tbl}"
            assert "column_count" in tbl, f"Missing column_count in {tbl}"

    def test_row_counts_are_non_negative_integers(self):
        data = _load_json("manifest.json")
        for tbl in data["tables"]:
            assert isinstance(tbl["row_count"], int)
            assert tbl["row_count"] >= 0

    def test_column_counts_are_positive_integers(self):
        data = _load_json("manifest.json")
        for tbl in data["tables"]:
            assert isinstance(tbl["column_count"], int)
            assert tbl["column_count"] > 0

    def test_table_names_are_unique(self):
        data = _load_json("manifest.json")
        names = [t["table_name"] for t in data["tables"]]
        assert len(names) == len(set(names)), "Duplicate table names"

    def test_manifest_has_extraction_date(self):
        data = _load_json("manifest.json")
        assert "extraction_date" in data

    def test_total_row_count_is_plausible(self):
        data = _load_json("manifest.json")
        total = sum(t["row_count"] for t in data["tables"])
        assert total > 0


class TestPanel2_InventoryByPlant:
    """Panel 2: Gross inventory value across plants."""

    def test_file_exists(self):
        assert (DATA_DIR / "inventory_by_plant.json").exists()

    def test_has_total_value(self):
        data = _load_json("inventory_by_plant.json")
        assert "total_value" in data
        assert isinstance(data["total_value"], (int, float))
        assert data["total_value"] > 0

    def test_has_plants_list(self):
        data = _load_json("inventory_by_plant.json")
        assert "plants" in data
        assert isinstance(data["plants"], list)
        assert len(data["plants"]) > 0

    def test_each_plant_has_required_fields(self):
        data = _load_json("inventory_by_plant.json")
        for plant in data["plants"]:
            assert "plant_id" in plant
            assert "plant_name" in plant
            assert "value" in plant

    def test_plant_values_are_positive(self):
        data = _load_json("inventory_by_plant.json")
        for plant in data["plants"]:
            assert plant["value"] > 0

    def test_plant_values_sum_to_total(self):
        data = _load_json("inventory_by_plant.json")
        plant_sum = sum(p["value"] for p in data["plants"])
        assert abs(plant_sum - data["total_value"]) < 1.0

    def test_currency_is_inr(self):
        data = _load_json("inventory_by_plant.json")
        assert data.get("currency") == "INR"

    def test_gross_value_is_approximately_512_cr(self):
        data = _load_json("inventory_by_plant.json")
        value_cr = data["total_value"] / 1e7
        assert 400 < value_cr < 700

    def test_plant_ids_are_unique(self):
        data = _load_json("inventory_by_plant.json")
        ids = [p["plant_id"] for p in data["plants"]]
        assert len(ids) == len(set(ids))


class TestPanel3_StockByCategory:
    """Panel 3: Stock by material category."""

    def test_file_exists(self):
        assert (DATA_DIR / "stock_by_category.json").exists()

    def test_has_categories_list(self):
        data = _load_json("stock_by_category.json")
        assert "categories" in data
        assert isinstance(data["categories"], list)
        assert len(data["categories"]) > 0

    def test_each_category_has_required_fields(self):
        data = _load_json("stock_by_category.json")
        for cat in data["categories"]:
            assert "category" in cat
            assert "material_count" in cat
            assert "value" in cat

    def test_category_values_are_non_negative(self):
        data = _load_json("stock_by_category.json")
        for cat in data["categories"]:
            assert cat["value"] >= 0
            assert cat["material_count"] >= 0

    def test_category_names_are_unique(self):
        data = _load_json("stock_by_category.json")
        names = [c["category"] for c in data["categories"]]
        assert len(names) == len(set(names))

    def test_categories_sorted_by_value_descending(self):
        data = _load_json("stock_by_category.json")
        values = [c["value"] for c in data["categories"]]
        assert values == sorted(values, reverse=True)

    def test_currency_is_inr(self):
        data = _load_json("stock_by_category.json")
        assert data.get("currency") == "INR"

    def test_total_category_value_is_plausible(self):
        data = _load_json("stock_by_category.json")
        total = sum(c["value"] for c in data["categories"])
        assert total > 0


class TestPanel4_DaysOnHand:
    """Panel 4: Days on hand distribution histogram."""

    def test_file_exists(self):
        assert (DATA_DIR / "days_on_hand.json").exists()

    def test_has_buckets_list(self):
        data = _load_json("days_on_hand.json")
        assert "buckets" in data
        assert isinstance(data["buckets"], list)
        assert len(data["buckets"]) > 0

    def test_has_total_items(self):
        data = _load_json("days_on_hand.json")
        assert "total_items" in data
        assert isinstance(data["total_items"], int)
        assert data["total_items"] > 0

    def test_each_bucket_has_required_fields(self):
        data = _load_json("days_on_hand.json")
        for bucket in data["buckets"]:
            assert "range" in bucket
            assert "count" in bucket
            assert "min" in bucket
            assert "max" in bucket

    def test_bucket_counts_are_non_negative(self):
        data = _load_json("days_on_hand.json")
        for bucket in data["buckets"]:
            assert bucket["count"] >= 0

    def test_bucket_counts_sum_to_total(self):
        data = _load_json("days_on_hand.json")
        bucket_sum = sum(b["count"] for b in data["buckets"])
        assert bucket_sum == data["total_items"]

    def test_has_stockout_bucket(self):
        data = _load_json("days_on_hand.json")
        ranges = [b["range"] for b in data["buckets"]]
        assert any("stockout" in r.lower() or r.startswith("0") for r in ranges)

    def test_has_365_plus_bucket(self):
        data = _load_json("days_on_hand.json")
        ranges = [b["range"] for b in data["buckets"]]
        assert any("365" in r for r in ranges)

    def test_buckets_cover_full_range(self):
        data = _load_json("days_on_hand.json")
        mins = [b["min"] for b in data["buckets"]]
        maxs = [b["max"] for b in data["buckets"]]
        assert 0 in mins
        assert max(maxs) >= 365

    def test_six_histogram_buckets(self):
        data = _load_json("days_on_hand.json")
        assert len(data["buckets"]) == 6


class TestPanel5_NmiSmiSummary:
    """Panel 5: Non-moving / slow-moving inventory flag summary."""

    def test_file_exists(self):
        assert (DATA_DIR / "nmi_smi_summary.json").exists()

    def test_has_flags_list(self):
        data = _load_json("nmi_smi_summary.json")
        assert "flags" in data
        assert isinstance(data["flags"], list)
        assert len(data["flags"]) > 0

    def test_has_total_items(self):
        data = _load_json("nmi_smi_summary.json")
        assert "total_items" in data
        assert data["total_items"] > 0

    def test_each_flag_has_required_fields(self):
        data = _load_json("nmi_smi_summary.json")
        for flag in data["flags"]:
            assert "flag" in flag
            assert "count" in flag
            assert "percentage" in flag
            assert "value" in flag

    def test_flag_counts_are_non_negative(self):
        data = _load_json("nmi_smi_summary.json")
        for flag in data["flags"]:
            assert flag["count"] >= 0
            assert flag["percentage"] >= 0

    def test_flag_counts_sum_to_total(self):
        data = _load_json("nmi_smi_summary.json")
        flag_sum = sum(f["count"] for f in data["flags"])
        assert flag_sum == data["total_items"]

    def test_percentages_sum_to_approximately_100(self):
        data = _load_json("nmi_smi_summary.json")
        pct_sum = sum(f["percentage"] for f in data["flags"])
        assert abs(pct_sum - 100.0) < 1.0

    def test_has_active_flag(self):
        data = _load_json("nmi_smi_summary.json")
        flags = [f["flag"].lower() for f in data["flags"]]
        assert any("active" in f for f in flags)

    def test_has_slow_moving_flag(self):
        data = _load_json("nmi_smi_summary.json")
        flags = [f["flag"].lower() for f in data["flags"]]
        assert any("slow" in f for f in flags)

    def test_has_non_moving_flag(self):
        data = _load_json("nmi_smi_summary.json")
        flags = [f["flag"].lower() for f in data["flags"]]
        assert any("non" in f for f in flags)

    def test_has_semantic_colours(self):
        data = _load_json("nmi_smi_summary.json")
        for flag in data["flags"]:
            assert "semantic" in flag
            assert flag["semantic"] in ("success", "warning", "danger", "info", "neutral")

    def test_currency_is_inr(self):
        data = _load_json("nmi_smi_summary.json")
        assert data.get("currency") == "INR"


class TestDashboardStructure:
    """Verify dashboard file structure and HTML presence."""

    def test_dashboard_index_html_exists(self):
        assert (DASHBOARD_DIR / "index.html").exists()

    def test_dashboard_index_html_is_not_empty(self):
        content = (DASHBOARD_DIR / "index.html").read_text()
        assert len(content) > 1000

    def test_dashboard_references_chart_js(self):
        content = (DASHBOARD_DIR / "index.html").read_text()
        assert "chart" in content.lower()

    def test_dashboard_has_all_five_data_files(self):
        expected = [
            "manifest.json", "inventory_by_plant.json",
            "stock_by_category.json", "days_on_hand.json",
            "nmi_smi_summary.json",
        ]
        for f in expected:
            assert (DATA_DIR / f).exists(), f"Missing: {f}"

    def test_prepare_data_script_exists(self):
        assert (DASHBOARD_DIR / "prepare_data.py").exists()

    def test_prepare_data_has_all_builders(self):
        content = (DASHBOARD_DIR / "prepare_data.py").read_text()
        builders = [
            "build_manifest", "build_inventory_by_plant",
            "build_stock_by_category", "build_days_on_hand",
            "build_nmi_smi_summary",
        ]
        for fn in builders:
            assert fn in content, f"Missing builder: {fn}"

    def test_all_json_files_are_valid_json(self):
        for f in DATA_DIR.glob("*.json"):
            try:
                json.loads(f.read_text())
            except json.JSONDecodeError:
                pytest.fail(f"{f.name} is not valid JSON")


class TestCrossPanelConsistency:
    """Verify data consistency across dashboard panels."""

    def test_nmi_smi_total_matches_days_on_hand_total(self):
        nmi = _load_json("nmi_smi_summary.json")
        doh = _load_json("days_on_hand.json")
        assert nmi["total_items"] == doh["total_items"]

    def test_inventory_value_is_positive_across_panels(self):
        inv = _load_json("inventory_by_plant.json")
        assert inv["total_value"] > 0
        nmi = _load_json("nmi_smi_summary.json")
        total_flag_value = sum(f["value"] for f in nmi["flags"])
        assert total_flag_value > 0

    def test_nmi_smi_value_matches_plant_total(self):
        inv = _load_json("inventory_by_plant.json")
        nmi = _load_json("nmi_smi_summary.json")
        flag_total = sum(f["value"] for f in nmi["flags"])
        ratio = flag_total / inv["total_value"]
        assert 0.99 < ratio < 1.01
