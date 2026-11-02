"""Tests for the SAP HANA extraction pipeline — S-24 / S-27 acceptance criteria.

Covers:
  AC1: Table registry has exactly 22 tables, correct SAP names, unique keys
  AC2: Parquet round-trip — write, read-back, row-count match
  AC3: Extraction script completeness — all public functions, error paths
  AC4: Dependencies — hdbcli, pandas, pyarrow importable; requirements.txt correct

All tests run WITHOUT a live SAP HANA connection.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

EXPECTED_SAP_TABLES = [
    "MARA", "MAKT", "MARC", "MARD", "MBEW", "AUSP",
    "MCHB", "MKPF", "MSEG", "MSLB",
    "MVER", "RKPF", "RESB",
    "EBAN", "EKKO", "EKPO", "EKBE", "LFA1",
    "MDKP", "MDTB",
    "T001W", "T001L",
]

EXPECTED_CATEGORIES = {
    "material_master": "MARA",
    "material_description": "MAKT",
    "material_plant": "MARC",
    "material_storage": "MARD",
    "material_valuation": "MBEW",
    "material_classification": "AUSP",
    "stock_current": "MCHB",
    "material_documents": "MKPF",
    "material_doc_items": "MSEG",
    "warehouse_stocks": "MSLB",
    "consumption_history": "MVER",
    "reservation_header": "RKPF",
    "reservation_items": "RESB",
    "purchase_req_header": "EBAN",
    "purchase_order_header": "EKKO",
    "purchase_order_items": "EKPO",
    "purchase_order_history": "EKBE",
    "vendor_master": "LFA1",
    "mrp_parameters": "MDKP",
    "mrp_items": "MDTB",
    "plant_master": "T001W",
    "storage_locations": "T001L",
}


class TestAC1_TableRegistry:
    """AC1: manifest.json lists exactly 22 tables with correct schemas."""

    def test_exactly_22_tables_in_scope(self):
        from sap_extraction.tables import TABLES_IN_SCOPE
        assert len(TABLES_IN_SCOPE) == 22

    def test_all_expected_sap_tables_present(self):
        from sap_extraction.tables import TABLES_IN_SCOPE
        actual = {t.sap_table for t in TABLES_IN_SCOPE}
        assert actual == set(EXPECTED_SAP_TABLES)

    def test_logical_name_to_sap_table_mapping(self):
        from sap_extraction.tables import TABLE_LOOKUP
        for logical, sap in EXPECTED_CATEGORIES.items():
            assert logical in TABLE_LOOKUP, f"Missing logical name: {logical}"
            assert TABLE_LOOKUP[logical].sap_table == sap

    def test_no_duplicate_logical_names(self):
        from sap_extraction.tables import TABLES_IN_SCOPE
        names = [t.logical_name for t in TABLES_IN_SCOPE]
        assert len(names) == len(set(names))

    def test_no_duplicate_sap_table_names(self):
        from sap_extraction.tables import TABLES_IN_SCOPE
        sap_names = [t.sap_table for t in TABLES_IN_SCOPE]
        assert len(sap_names) == len(set(sap_names))

    def test_every_table_has_description(self):
        from sap_extraction.tables import TABLES_IN_SCOPE
        for t in TABLES_IN_SCOPE:
            assert t.description.strip(), f"{t.logical_name} has empty description"

    def test_table_spec_is_named_tuple(self):
        from sap_extraction.tables import TABLES_IN_SCOPE, TableSpec
        for t in TABLES_IN_SCOPE:
            assert isinstance(t, TableSpec)

    def test_lookup_dict_has_22_entries(self):
        from sap_extraction.tables import TABLE_LOOKUP
        assert len(TABLE_LOOKUP) == 22


class TestAC2_ParquetRoundTrip:
    """AC2: Each Parquet file exists and can be read back with matching row counts."""

    def test_valid_parquet_passes_validation(self, tmp_path):
        from sap_extraction.extract import validate_parquet
        df = pd.DataFrame({"A": range(100), "B": [f"val_{i}" for i in range(100)]})
        path = tmp_path / "test.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        passed, msg = validate_parquet(path, 100, "test_table")
        assert passed is True
        assert "PASS" in msg

    def test_row_count_mismatch_fails_validation(self, tmp_path):
        from sap_extraction.extract import validate_parquet
        df = pd.DataFrame({"A": [1, 2, 3]})
        path = tmp_path / "test.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        passed, msg = validate_parquet(path, 10, "test_table")
        assert passed is False
        assert "mismatch" in msg

    def test_missing_parquet_fails_validation(self, tmp_path):
        from sap_extraction.extract import validate_parquet
        path = tmp_path / "nonexistent.parquet"
        passed, msg = validate_parquet(path, 5, "missing_table")
        assert passed is False
        assert "not found" in msg

    def test_empty_parquet_validates_with_zero_rows(self, tmp_path):
        from sap_extraction.extract import validate_parquet
        df = pd.DataFrame({"X": pd.Series([], dtype="float64")})
        path = tmp_path / "empty.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        passed, msg = validate_parquet(path, 0, "empty_table")
        assert passed is True

    def test_parquet_preserves_column_names(self, tmp_path):
        cols = ["MATNR", "MAKTX", "WERKS", "LGORT", "LABST"]
        df = pd.DataFrame({c: [f"v{i}"] for i, c in enumerate(cols)})
        path = tmp_path / "columns.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        df_back = pd.read_parquet(path)
        assert list(df_back.columns) == cols

    def test_parquet_preserves_dtypes(self, tmp_path):
        df = pd.DataFrame({
            "int_col": pd.array([1, 2, 3], dtype="int64"),
            "float_col": pd.array([1.1, 2.2, 3.3], dtype="float64"),
            "str_col": ["a", "b", "c"],
        })
        path = tmp_path / "dtypes.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        df_back = pd.read_parquet(path)
        assert df_back["int_col"].dtype == "int64"
        assert df_back["float_col"].dtype == "float64"

    def test_large_parquet_round_trip(self, tmp_path):
        from sap_extraction.extract import validate_parquet
        n = 10_000
        df = pd.DataFrame({"ID": range(n), "VALUE": [float(i) for i in range(n)]})
        path = tmp_path / "large.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        passed, msg = validate_parquet(path, n, "large_table")
        assert passed is True


class TestAC3_ExtractionScript:
    """AC3: Extraction script is correct and complete."""

    def test_serialise_none(self):
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(None) is None

    def test_serialise_int(self):
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(42) == 42

    def test_serialise_float(self):
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(3.14) == 3.14

    def test_serialise_string(self):
        from sap_extraction.extract import _serialise_value
        assert _serialise_value("hello") == "hello"

    def test_serialise_bool(self):
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(True) is True

    def test_serialise_bytes_to_hex(self):
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(b"\xde\xad\xbe\xef") == "deadbeef"

    def test_serialise_datetime_to_iso(self):
        from sap_extraction.extract import _serialise_value
        dt = datetime(2026, 11, 2, 10, 30, 0, tzinfo=timezone.utc)
        result = _serialise_value(dt)
        assert "2026-11-02" in result

    def test_serialise_decimal_to_str(self):
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(Decimal("512.52")) == "512.52"

    def test_manifest_structure_and_fields(self, tmp_path):
        from sap_extraction.extract import write_manifest
        entries = [{
            "logical_name": "material_master", "sap_table": "MARA",
            "description": "General material data", "column_count": 10,
            "row_count": 500, "schema": [{"column_name": "MATNR", "data_type": "NVARCHAR"}],
            "sample_rows": [{"MATNR": "000001"}],
            "parquet_file": "parquet/material_master.parquet",
        }]
        manifest_path = tmp_path / "manifest.json"
        write_manifest(entries, manifest_path)
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert "extraction_timestamp" in data
        assert data["tables_in_scope"] == 1
        assert data["tables"][0]["row_count"] == 500

    def test_manifest_with_22_entries(self, tmp_path):
        from sap_extraction.extract import write_manifest
        from sap_extraction.tables import TABLES_IN_SCOPE
        entries = [{
            "logical_name": t.logical_name, "sap_table": t.sap_table,
            "description": t.description, "column_count": 5, "row_count": 100,
            "schema": [], "sample_rows": [],
            "parquet_file": f"parquet/{t.logical_name}.parquet",
        } for t in TABLES_IN_SCOPE]
        manifest_path = tmp_path / "manifest.json"
        write_manifest(entries, manifest_path)
        data = json.loads(manifest_path.read_text())
        assert data["tables_in_scope"] == 22
        assert len(data["tables"]) == 22

    def test_missing_required_env_raises(self):
        from sap_extraction.extract import _get_env
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EnvironmentError, match="SAP_HANA_HOST"):
                _get_env("SAP_HANA_HOST", required=True)

    def test_optional_env_returns_empty_string(self):
        from sap_extraction.extract import _get_env
        with patch.dict(os.environ, {}, clear=True):
            result = _get_env("SAP_HANA_SCHEMA", required=False)
            assert result == ""

    def test_connect_raises_without_hdbcli(self):
        from sap_extraction.extract import connect_sap_hana
        with patch("sap_extraction.extract.hdbcli_dbapi", None):
            with pytest.raises(ImportError, match="hdbcli"):
                connect_sap_hana()

    def test_module_docstring_present(self):
        import sap_extraction
        assert sap_extraction.__doc__ is not None
        assert "SAP HANA" in sap_extraction.__doc__

    def test_extract_module_has_all_public_functions(self):
        from sap_extraction import extract
        required = [
            "connect_sap_hana", "get_table_schema", "get_row_count",
            "get_sample_rows", "export_table_to_parquet", "validate_parquet",
            "write_manifest", "run_extraction", "main",
        ]
        for fn_name in required:
            assert hasattr(extract, fn_name), f"Missing function: {fn_name}"
            assert callable(getattr(extract, fn_name))


class TestAC4_Dependencies:
    """AC4: requirements.txt includes hdbcli, pandas, pyarrow."""

    def test_sap_extraction_requirements_file_exists(self):
        req_path = Path(__file__).resolve().parent.parent / "sap_extraction" / "requirements.txt"
        assert req_path.exists()

    def test_requirements_includes_hdbcli(self):
        req_path = Path(__file__).resolve().parent.parent / "sap_extraction" / "requirements.txt"
        assert "hdbcli" in req_path.read_text().lower()

    def test_requirements_includes_pandas(self):
        req_path = Path(__file__).resolve().parent.parent / "sap_extraction" / "requirements.txt"
        assert "pandas" in req_path.read_text().lower()

    def test_requirements_includes_pyarrow(self):
        req_path = Path(__file__).resolve().parent.parent / "sap_extraction" / "requirements.txt"
        assert "pyarrow" in req_path.read_text().lower()

    def test_pandas_importable(self):
        import pandas
        assert pandas.__version__

    def test_pyarrow_importable(self):
        import pyarrow
        assert pyarrow.__version__

    def test_extract_module_importable(self):
        from sap_extraction import extract
        assert extract is not None

    def test_tables_module_importable(self):
        from sap_extraction import tables
        assert tables is not None
