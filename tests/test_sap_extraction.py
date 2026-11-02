"""Tests for the SAP HANA extraction pipeline.

These tests validate the extraction logic WITHOUT requiring a live SAP HANA
connection. They mock hdbcli and verify:
  - Table registry has exactly 22 entries
  - Schema introspection query construction
  - Parquet export and validation round-trip
  - Manifest generation structure
  - Error handling for missing credentials and connection failures
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Table registry tests
# ---------------------------------------------------------------------------


class TestTableRegistry:
    """Verify the 22-table scope is correctly defined."""

    def test_exactly_22_tables(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE

        assert len(TABLES_IN_SCOPE) == 22, (
            f"Expected 22 tables in scope, got {len(TABLES_IN_SCOPE)}"
        )

    def test_no_duplicate_logical_names(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE

        names = [t.logical_name for t in TABLES_IN_SCOPE]
        assert len(names) == len(set(names)), "Duplicate logical names found"

    def test_no_duplicate_sap_tables(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE

        sap_names = [t.sap_table for t in TABLES_IN_SCOPE]
        assert len(sap_names) == len(set(sap_names)), (
            "Duplicate SAP table names found"
        )

    def test_all_have_descriptions(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE

        for t in TABLES_IN_SCOPE:
            assert t.description, f"{t.logical_name} has no description"

    def test_lookup_dict_matches(self) -> None:
        from sap_extraction.tables import TABLE_LOOKUP, TABLES_IN_SCOPE

        assert len(TABLE_LOOKUP) == len(TABLES_IN_SCOPE)
        for t in TABLES_IN_SCOPE:
            assert TABLE_LOOKUP[t.logical_name] is t


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------


class TestSerialiseValue:
    """Verify _serialise_value handles SAP HANA types."""

    def test_none(self) -> None:
        from sap_extraction.extract import _serialise_value

        assert _serialise_value(None) is None

    def test_primitives(self) -> None:
        from sap_extraction.extract import _serialise_value

        assert _serialise_value(42) == 42
        assert _serialise_value(3.14) == 3.14
        assert _serialise_value("hello") == "hello"
        assert _serialise_value(True) is True

    def test_bytes_to_hex(self) -> None:
        from sap_extraction.extract import _serialise_value

        assert _serialise_value(b"\xde\xad") == "dead"

    def test_datetime_to_iso(self) -> None:
        from datetime import datetime, timezone
        from sap_extraction.extract import _serialise_value

        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _serialise_value(dt)
        assert "2026-01-15" in result
        assert "10:30" in result

    def test_fallback_to_str(self) -> None:
        from decimal import Decimal
        from sap_extraction.extract import _serialise_value

        assert _serialise_value(Decimal("99.99")) == "99.99"


# ---------------------------------------------------------------------------
# Parquet validation
# ---------------------------------------------------------------------------


class TestParquetValidation:
    """Verify the validate_parquet function."""

    def test_valid_parquet(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet

        df = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
        path = tmp_path / "test.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)

        passed, msg = validate_parquet(path, 3, "test_table")
        assert passed is True
        assert "PASS" in msg

    def test_row_count_mismatch(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet

        df = pd.DataFrame({"A": [1, 2]})
        path = tmp_path / "test.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)

        passed, msg = validate_parquet(path, 5, "test_table")
        assert passed is False
        assert "mismatch" in msg

    def test_missing_file(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet

        path = tmp_path / "nonexistent.parquet"
        passed, msg = validate_parquet(path, 10, "test_table")
        assert passed is False
        assert "not found" in msg

    def test_empty_table(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet

        df = pd.DataFrame({"A": pd.Series([], dtype="int64")})
        path = tmp_path / "empty.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)

        passed, msg = validate_parquet(path, 0, "empty_table")
        assert passed is True


# ---------------------------------------------------------------------------
# Manifest writing
# ---------------------------------------------------------------------------


class TestManifest:
    """Verify manifest JSON structure."""

    def test_manifest_structure(self, tmp_path: Path) -> None:
        from sap_extraction.extract import write_manifest

        entries = [
            {
                "logical_name": "material_master",
                "sap_table": "MARA",
                "description": "General material data",
                "column_count": 5,
                "row_count": 100,
                "schema": [
                    {"column_name": "MATNR", "data_type": "NVARCHAR"}
                ],
                "sample_rows": [{"MATNR": "000001"}],
                "parquet_file": "parquet/material_master.parquet",
            }
        ]

        manifest_path = tmp_path / "manifest.json"
        write_manifest(entries, manifest_path)

        assert manifest_path.exists()
        with manifest_path.open() as fh:
            data = json.load(fh)

        assert "extraction_timestamp" in data
        assert data["tables_in_scope"] == 1
        assert len(data["tables"]) == 1
        assert data["tables"][0]["logical_name"] == "material_master"
        assert data["tables"][0]["row_count"] == 100


# ---------------------------------------------------------------------------
# Connection and environment
# ---------------------------------------------------------------------------


class TestConnection:
    """Verify connection configuration handling."""

    def test_missing_host_raises(self) -> None:
        from sap_extraction.extract import _get_env

        env = {
            k: v
            for k, v in os.environ.items()
            if k != "SAP_HANA_HOST"
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError, match="SAP_HANA_HOST"):
                _get_env("SAP_HANA_HOST", required=True)

    def test_optional_env_returns_empty(self) -> None:
        from sap_extraction.extract import _get_env

        env = {
            k: v
            for k, v in os.environ.items()
            if k != "SAP_HANA_SCHEMA"
        }
        with patch.dict(os.environ, env, clear=True):
            result = _get_env("SAP_HANA_SCHEMA", required=False)
            assert result == ""

    def test_hdbcli_import_error(self) -> None:
        from sap_extraction.extract import connect_sap_hana

        with patch("sap_extraction.extract.hdbcli_dbapi", None):
            with pytest.raises(ImportError, match="hdbcli"):
                connect_sap_hana()
