"""Tests for app.data_loader — the contract-validated data access layer.

These exercise fixture loading, contract validation, the stubbed gcs/sap
modes, and the guarantee that no public loader ever raises.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import app.data_loader as dl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "data" / "fixtures"
CONTRACTS_DIR = PROJECT_ROOT / "data" / "contracts"

DATASETS = [
    "consumption_history",
    "material_master",
    "po_history",
    "shutdown_calendar",
]

FIXTURE_FILES = {
    "consumption_history": "sap_consumption_history.json",
    "material_master": "sap_material_master.json",
    "po_history": "sap_po_history.json",
    "shutdown_calendar": "sap_shutdown_calendar.json",
}


@pytest.fixture(autouse=True)
def _fixture_mode(monkeypatch):
    """Default every test to fixture mode unless it overrides."""
    monkeypatch.setenv("DATA_SOURCE_MODE", "fixture")


# --------------------------------------------------------------------------- #
# Fixture files on disk
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("dataset", DATASETS)
def test_fixture_file_has_warning_marker_and_15_rows(dataset):
    path = FIXTURES_DIR / FIXTURE_FILES[dataset]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["_fixture_warning"] == "TEST DATA — NOT FOR PRODUCTION"
    assert len(payload["rows"]) == 15


@pytest.mark.parametrize("dataset", DATASETS)
def test_contract_file_is_valid_json_schema(dataset):
    stem = FIXTURE_FILES[dataset]
    contract = json.loads((CONTRACTS_DIR / stem).read_text(encoding="utf-8"))
    assert contract["$schema"].startswith("http://json-schema.org/")
    assert contract["type"] == "object"
    assert "properties" in contract and contract["properties"]


# --------------------------------------------------------------------------- #
# Loading in fixture mode
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("dataset", DATASETS)
def test_load_dataset_returns_dataframe_with_all_rows(dataset):
    df = dl.load_dataset(dataset)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 15


@pytest.mark.parametrize("dataset", DATASETS)
def test_fixture_warning_marker_is_stripped_from_rows(dataset):
    df = dl.load_dataset(dataset)
    assert dl.FIXTURE_WARNING_KEY not in df.columns


def test_convenience_wrappers_match_load_dataset():
    assert len(dl.load_consumption_history()) == 15
    assert len(dl.load_material_master()) == 15
    assert len(dl.load_po_history()) == 15
    assert len(dl.load_shutdown_calendar()) == 15


def test_material_numbers_join_across_master_and_consumption():
    master = dl.load_material_master()
    consumption = dl.load_consumption_history()
    master_mats = set(master["material_number"])
    consumption_mats = set(consumption["material_number"])
    # every consumed material exists in the master
    assert consumption_mats.issubset(master_mats)


def test_load_report_records_counts():
    dl.load_dataset("material_master")
    report = dl.last_load_report("material_master")
    assert report is not None
    assert report["mode"] == "fixture"
    assert report["rows_read"] == 15
    assert report["rows_valid"] == 15
    assert report["rows_dropped"] == 0
    assert report["available"] is True


# --------------------------------------------------------------------------- #
# Failure paths — never raise, always empty frame
# --------------------------------------------------------------------------- #


def test_unknown_dataset_returns_empty_frame_and_does_not_raise():
    df = dl.load_dataset("does_not_exist")
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    report = dl.last_load_report("does_not_exist")
    assert report["available"] is False


def test_gcs_mode_returns_empty_frame_and_does_not_raise(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE_MODE", "gcs")
    for dataset in DATASETS:
        df = dl.load_dataset(dataset)
        assert df.empty
        assert dl.last_load_report(dataset)["available"] is False


def test_sap_mode_returns_empty_frame_and_does_not_raise(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE_MODE", "sap")
    for dataset in DATASETS:
        df = dl.load_dataset(dataset)
        assert df.empty
        assert dl.last_load_report(dataset)["available"] is False


def test_unknown_mode_falls_back_to_fixture(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE_MODE", "banana")
    df = dl.load_dataset("material_master")
    assert len(df) == 15


def test_contract_validation_drops_bad_rows(monkeypatch, tmp_path):
    """A row missing a required field is dropped and counted, not kept."""
    bad = {
        "_fixture_warning": "TEST DATA — NOT FOR PRODUCTION",
        "rows": [
            {
                "material_number": "MAT-X",
                "plant": "VED-ZAM-001",
                "material_type": "SPARE",
                "base_unit": "EA",
            },
            {"plant": "VED-ZAM-001", "material_type": "SPARE", "base_unit": "EA"},
        ],
    }
    fixtures = tmp_path / "data" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "sap_material_master.json").write_text(json.dumps(bad))

    monkeypatch.setattr(dl, "_FIXTURES_DIR", fixtures)
    df = dl.load_dataset("material_master")
    assert len(df) == 1  # the row without material_number was dropped
    report = dl.last_load_report("material_master")
    assert report["rows_read"] == 2
    assert report["rows_dropped"] == 1


def test_available_datasets_lists_the_four():
    assert set(dl.available_datasets()) == set(DATASETS)
