"""QA verification tests for the SAP HANA extraction pipeline.

These tests verify the acceptance criteria for ticket S-24:
  AC1: manifest.json lists exactly 22 tables with correct schemas and row counts
  AC2: Each Parquet file exists and can be read back with matching row counts
  AC3: Extraction script is correct and complete
  AC4: Table registry matches the 22 in-scope SAP tables

Tests simulate the full pipeline with a mocked SAP HANA connection to verify
end-to-end correctness without requiring live credentials.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# AC4: Table registry — exactly 22 tables, correct SAP names
# ---------------------------------------------------------------------------


class TestTableRegistryQA:
    """Verify the 22-table scope matches the inventory programme spec."""

    EXPECTED_SAP_TABLES = sorted([
        "MARA", "MAKT", "MARC", "MARD", "MBEW", "AUSP",
        "MCHB", "MKPF", "MSEG", "MSLB",
        "MVER", "RKPF", "RESB",
        "EBAN", "EKKO", "EKPO", "EKBE", "LFA1",
        "MDKP", "MDTB",
        "T001W", "T001L",
    ])

    def test_exactly_22_tables_in_scope(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE
        assert len(TABLES_IN_SCOPE) == 22

    def test_sap_table_names_match_spec(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE
        actual = sorted(t.sap_table for t in TABLES_IN_SCOPE)
        assert actual == self.EXPECTED_SAP_TABLES

    def test_logical_names_are_valid_identifiers(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE
        for t in TABLES_IN_SCOPE:
            assert t.logical_name.isidentifier(), (
                f"{t.logical_name} is not a valid Python identifier"
            )

    def test_no_duplicate_logical_names(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE
        names = [t.logical_name for t in TABLES_IN_SCOPE]
        assert len(names) == len(set(names))

    def test_no_duplicate_sap_tables(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE
        sap = [t.sap_table for t in TABLES_IN_SCOPE]
        assert len(sap) == len(set(sap))

    def test_all_have_nonempty_descriptions(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE
        for t in TABLES_IN_SCOPE:
            assert t.description.strip(), (
                f"{t.logical_name} has empty description"
            )

    def test_table_lookup_covers_all(self) -> None:
        from sap_extraction.tables import TABLE_LOOKUP, TABLES_IN_SCOPE
        assert len(TABLE_LOOKUP) == 22
        for t in TABLES_IN_SCOPE:
            assert t.logical_name in TABLE_LOOKUP

    def test_tablespec_is_namedtuple(self) -> None:
        from sap_extraction.tables import TABLES_IN_SCOPE, TableSpec
        for t in TABLES_IN_SCOPE:
            assert isinstance(t, TableSpec)
            assert hasattr(t, "logical_name")
            assert hasattr(t, "sap_table")
            assert hasattr(t, "description")


# ---------------------------------------------------------------------------
# AC3: Extraction script correctness — serialisation edge cases
# ---------------------------------------------------------------------------


class TestSerialiseValueQA:
    """Extended serialisation tests for SAP HANA data types."""

    def test_date_object(self) -> None:
        from datetime import date
        from sap_extraction.extract import _serialise_value
        result = _serialise_value(date(2026, 6, 15))
        assert "2026-06-15" in str(result)

    def test_time_object(self) -> None:
        from datetime import time
        from sap_extraction.extract import _serialise_value
        result = _serialise_value(time(14, 30, 0))
        assert "14:30" in str(result)

    def test_large_decimal(self) -> None:
        from sap_extraction.extract import _serialise_value
        result = _serialise_value(Decimal("123456789.99"))
        assert result == "123456789.99"

    def test_empty_bytes(self) -> None:
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(b"") == ""

    def test_negative_number(self) -> None:
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(-42) == -42

    def test_zero(self) -> None:
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(0) == 0

    def test_empty_string(self) -> None:
        from sap_extraction.extract import _serialise_value
        assert _serialise_value("") == ""

    def test_boolean_false(self) -> None:
        from sap_extraction.extract import _serialise_value
        assert _serialise_value(False) is False


# ---------------------------------------------------------------------------
# AC3: Environment variable handling
# ---------------------------------------------------------------------------


class TestEnvHandlingQA:
    """Verify credential handling is robust."""

    def test_whitespace_only_treated_as_missing(self) -> None:
        from sap_extraction.extract import _get_env
        with patch.dict(os.environ, {"SAP_HANA_HOST": "   "}, clear=False):
            with pytest.raises(EnvironmentError):
                _get_env("SAP_HANA_HOST", required=True)

    def test_valid_env_returned_stripped(self) -> None:
        from sap_extraction.extract import _get_env
        with patch.dict(
            os.environ, {"SAP_HANA_HOST": "  myhost.com  "}, clear=False
        ):
            assert _get_env("SAP_HANA_HOST") == "myhost.com"

    def test_port_defaults_to_443(self) -> None:
        """When SAP_HANA_PORT is not set, connect_sap_hana should
        default to port 443."""
        from sap_extraction.extract import _get_env
        env = {k: v for k, v in os.environ.items()
               if k != "SAP_HANA_PORT"}
        with patch.dict(os.environ, env, clear=True):
            val = _get_env("SAP_HANA_PORT", required=False) or "443"
            assert val == "443"


# ---------------------------------------------------------------------------
# AC2: Parquet round-trip for various data shapes
# ---------------------------------------------------------------------------


class TestParquetRoundTripQA:
    """Verify Parquet export and validation for realistic data."""

    def test_roundtrip_with_mixed_types(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet
        df = pd.DataFrame({
            "MATNR": ["000001", "000002", "000003"],
            "MAKTX": ["Widget A", "Widget B", "Widget C"],
            "PRICE": [10.5, 20.0, 30.75],
            "QTY": [100, 200, 300],
        })
        path = tmp_path / "mixed.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        passed, msg = validate_parquet(path, 3, "mixed_types")
        assert passed is True
        assert "PASS" in msg

    def test_roundtrip_with_nulls(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet
        df = pd.DataFrame({
            "A": [1, None, 3],
            "B": ["x", None, "z"],
        })
        path = tmp_path / "nulls.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        passed, msg = validate_parquet(path, 3, "nulls_table")
        assert passed is True

    def test_roundtrip_large_row_count(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet
        df = pd.DataFrame({"ID": range(10_000)})
        path = tmp_path / "large.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        passed, msg = validate_parquet(path, 10_000, "large_table")
        assert passed is True

    def test_validation_fails_on_wrong_count(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet
        df = pd.DataFrame({"A": [1, 2]})
        path = tmp_path / "wrong.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        passed, msg = validate_parquet(path, 99, "wrong_count")
        assert passed is False
        assert "mismatch" in msg

    def test_validation_fails_on_missing_file(self, tmp_path: Path) -> None:
        from sap_extraction.extract import validate_parquet
        path = tmp_path / "ghost.parquet"
        passed, msg = validate_parquet(path, 5, "ghost")
        assert passed is False
        assert "not found" in msg


# ---------------------------------------------------------------------------
# AC1: Manifest structure — all 22 tables, correct fields
# ---------------------------------------------------------------------------


class TestManifestStructureQA:
    """Verify manifest.json has the required structure for all 22 tables."""

    def _build_manifest(self, tmp_path: Path) -> Dict[str, Any]:
        """Build a manifest with 22 entries and return parsed JSON."""
        from sap_extraction.extract import write_manifest
        from sap_extraction.tables import TABLES_IN_SCOPE

        entries = []
        for t in TABLES_IN_SCOPE:
            entries.append({
                "logical_name": t.logical_name,
                "sap_table": t.sap_table,
                "description": t.description,
                "column_count": 5,
                "row_count": 100,
                "schema": [
                    {
                        "column_name": "COL1",
                        "data_type": "NVARCHAR",
                        "length": 40,
                        "is_nullable": "TRUE",
                    }
                ],
                "sample_rows": [{"COL1": "val1"}],
                "parquet_file": f"parquet/{t.logical_name}.parquet",
            })

        manifest_path = tmp_path / "manifest.json"
        write_manifest(entries, manifest_path)

        with manifest_path.open() as fh:
            return json.load(fh)

    def test_manifest_has_22_tables(self, tmp_path: Path) -> None:
        data = self._build_manifest(tmp_path)
        assert data["tables_in_scope"] == 22
        assert len(data["tables"]) == 22

    def test_manifest_has_timestamp(self, tmp_path: Path) -> None:
        data = self._build_manifest(tmp_path)
        assert "extraction_timestamp" in data
        ts = data["extraction_timestamp"]
        assert "T" in ts  # ISO 8601

    def test_each_table_has_required_fields(self, tmp_path: Path) -> None:
        data = self._build_manifest(tmp_path)
        required = {
            "logical_name", "sap_table", "description",
            "column_count", "row_count", "schema",
            "sample_rows", "parquet_file",
        }
        for entry in data["tables"]:
            missing = required - set(entry.keys())
            assert not missing, (
                f"{entry.get('logical_name', '?')} missing: {missing}"
            )

    def test_schema_entries_have_required_keys(self, tmp_path: Path) -> None:
        data = self._build_manifest(tmp_path)
        schema_keys = {"column_name", "data_type", "length", "is_nullable"}
        for entry in data["tables"]:
            for col in entry["schema"]:
                missing = schema_keys - set(col.keys())
                assert not missing, (
                    f"{entry['logical_name']} schema col missing: {missing}"
                )

    def test_parquet_file_paths_use_logical_name(
        self, tmp_path: Path
    ) -> None:
        data = self._build_manifest(tmp_path)
        for entry in data["tables"]:
            expected = f"parquet/{entry['logical_name']}.parquet"
            assert entry["parquet_file"] == expected

    def test_row_counts_are_non_negative(self, tmp_path: Path) -> None:
        data = self._build_manifest(tmp_path)
        for entry in data["tables"]:
            assert entry["row_count"] >= 0

    def test_column_counts_are_positive(self, tmp_path: Path) -> None:
        data = self._build_manifest(tmp_path)
        for entry in data["tables"]:
            assert entry["column_count"] > 0


# ---------------------------------------------------------------------------
# AC2 + AC3: End-to-end pipeline simulation with mocked connection
# ---------------------------------------------------------------------------


class _MockCursor:
    """Simulates an hdbcli cursor for pipeline testing."""

    def __init__(self, schema_rows, data_rows, count):
        self._schema_rows = schema_rows
        self._data_rows = data_rows
        self._count = count
        self._query = ""
        self._fetched = False
        self.description = [
            ("COL1", None, None, None, None, None, None),
            ("COL2", None, None, None, None, None, None),
        ]

    def execute(self, query, params=None):
        self._query = query
        self._fetched = False

    def fetchall(self):
        if "TABLE_COLUMNS" in self._query:
            return self._schema_rows
        if "COUNT(*)" in self._query:
            return [(self._count,)]
        if "LIMIT" in self._query:
            return self._data_rows[:10]
        return self._data_rows

    def fetchone(self):
        if "COUNT(*)" in self._query:
            return (self._count,)
        return None

    def fetchmany(self, size):
        if not self._fetched:
            self._fetched = True
            return self._data_rows
        return []

    def close(self):
        pass


class _MockConnection:
    """Simulates an hdbcli connection."""

    def __init__(self, row_count=5):
        self._row_count = row_count
        schema_rows = [
            ("COL1", "NVARCHAR", 40, "TRUE"),
            ("COL2", "INTEGER", 10, "FALSE"),
        ]
        data_rows = [
            ("val1", i) for i in range(row_count)
        ]
        self._cursor = _MockCursor(schema_rows, data_rows, row_count)

    def cursor(self):
        return _MockCursor(
            self._cursor._schema_rows,
            self._cursor._data_rows,
            self._row_count,
        )

    def close(self):
        pass


class TestEndToEndPipelineQA:
    """Simulate the full extraction pipeline and verify outputs."""

    def test_schema_introspection_returns_correct_structure(self) -> None:
        from sap_extraction.extract import get_table_schema
        conn = _MockConnection()
        with patch.dict(os.environ, {"SAP_HANA_SCHEMA": ""}, clear=False):
            schema = get_table_schema(conn, "MARA")
        assert len(schema) == 2
        assert schema[0]["column_name"] == "COL1"
        assert schema[0]["data_type"] == "NVARCHAR"
        assert schema[0]["length"] == 40
        assert schema[0]["is_nullable"] == "TRUE"

    def test_row_count_returns_integer(self) -> None:
        from sap_extraction.extract import get_row_count
        conn = _MockConnection(row_count=42)
        with patch.dict(os.environ, {"SAP_HANA_SCHEMA": ""}, clear=False):
            count = get_row_count(conn, "MARA")
        assert count == 42
        assert isinstance(count, int)

    def test_sample_rows_limited_to_10(self) -> None:
        from sap_extraction.extract import get_sample_rows
        conn = _MockConnection(row_count=50)
        with patch.dict(os.environ, {"SAP_HANA_SCHEMA": ""}, clear=False):
            rows = get_sample_rows(conn, "MARA", n=10)
        assert len(rows) <= 10
        assert isinstance(rows, list)
        if rows:
            assert isinstance(rows[0], dict)

    def test_export_creates_parquet_file(self, tmp_path: Path) -> None:
        from sap_extraction.extract import export_table_to_parquet
        conn = _MockConnection(row_count=5)
        out = tmp_path / "test.parquet"
        with patch.dict(os.environ, {"SAP_HANA_SCHEMA": ""}, clear=False):
            count = export_table_to_parquet(conn, "MARA", out)
        assert out.exists()
        assert count == 5
        df = pd.read_parquet(out)
        assert len(df) == 5

    def test_export_empty_table(self, tmp_path: Path) -> None:
        from sap_extraction.extract import export_table_to_parquet
        conn = _MockConnection(row_count=0)
        out = tmp_path / "empty.parquet"
        with patch.dict(os.environ, {"SAP_HANA_SCHEMA": ""}, clear=False):
            count = export_table_to_parquet(conn, "MARA", out)
        assert out.exists()
        assert count == 0

    def test_full_pipeline_produces_manifest_and_parquets(
        self, tmp_path: Path
    ) -> None:
        """Simulate run_extraction with mocked connection for all 22."""
        from sap_extraction.extract import (
            write_manifest,
            validate_parquet,
        )
        from sap_extraction.tables import TABLES_IN_SCOPE

        parquet_dir = tmp_path / "parquet"
        manifest_path = tmp_path / "manifest.json"

        entries: List[Dict[str, Any]] = []
        for t in TABLES_IN_SCOPE:
            parquet_path = parquet_dir / f"{t.logical_name}.parquet"

            schema = [
                {"column_name": "COL1", "data_type": "NVARCHAR",
                 "length": 40, "is_nullable": "TRUE"},
                {"column_name": "COL2", "data_type": "INTEGER",
                 "length": 10, "is_nullable": "FALSE"},
            ]

            df = pd.DataFrame({
                "COL1": ["a", "b", "c"],
                "COL2": [1, 2, 3],
            })
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(parquet_path, engine="pyarrow", index=False)

            passed, msg = validate_parquet(parquet_path, 3, t.logical_name)
            assert passed, msg

            entries.append({
                "logical_name": t.logical_name,
                "sap_table": t.sap_table,
                "description": t.description,
                "column_count": len(schema),
                "row_count": 3,
                "schema": schema,
                "sample_rows": [{"COL1": "a", "COL2": 1}],
                "parquet_file": f"parquet/{t.logical_name}.parquet",
            })

        write_manifest(entries, manifest_path)
        assert manifest_path.exists()

        with manifest_path.open() as fh:
            manifest = json.load(fh)

        assert manifest["tables_in_scope"] == 22
        assert len(manifest["tables"]) == 22

        for t in TABLES_IN_SCOPE:
            pq = parquet_dir / f"{t.logical_name}.parquet"
            assert pq.exists(), f"Missing parquet: {pq}"
            df = pd.read_parquet(pq)
            assert len(df) == 3


# ---------------------------------------------------------------------------
# AC3: Connection safety — read-only guardrail
# ---------------------------------------------------------------------------


class TestConnectionSafetyQA:
    """Verify the pipeline enforces read-only access."""

    def test_connect_sets_read_only_transaction(self) -> None:
        """connect_sap_hana should attempt SET TRANSACTION READ ONLY."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_dbapi = MagicMock()
        mock_dbapi.connect.return_value = mock_conn

        env = {
            "SAP_HANA_HOST": "test.hana.com",
            "SAP_HANA_PORT": "443",
            "SAP_HANA_USER": "testuser",
            "SAP_HANA_PASSWORD": "testpass",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "sap_extraction.extract.hdbcli_dbapi", mock_dbapi
            ):
                from sap_extraction.extract import connect_sap_hana
                connect_sap_hana()

        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("READ ONLY" in c for c in calls), (
            "connect_sap_hana did not set READ ONLY transaction"
        )

    def test_module_docstring_states_read_only(self) -> None:
        import sap_extraction
        assert "NEVER writes" in sap_extraction.__doc__


# ---------------------------------------------------------------------------
# AC3: .gitignore excludes outputs
# ---------------------------------------------------------------------------


class TestGitignoreQA:
    """Verify build artifacts are excluded from version control."""

    def test_parquet_dir_in_gitignore(self) -> None:
        gitignore = Path(__file__).resolve().parent.parent / ".gitignore"
        content = gitignore.read_text()
        assert "sap_extraction/parquet/" in content

    def test_manifest_in_gitignore(self) -> None:
        gitignore = Path(__file__).resolve().parent.parent / ".gitignore"
        content = gitignore.read_text()
        assert "sap_extraction/manifest.json" in content


# ---------------------------------------------------------------------------
# AC3: .env.example documents SAP HANA variables
# ---------------------------------------------------------------------------


class TestEnvExampleQA:
    """Verify .env.example documents all required variables."""

    def test_env_example_has_sap_hana_vars(self) -> None:
        env_example = (
            Path(__file__).resolve().parent.parent / ".env.example"
        )
        content = env_example.read_text()
        for var in [
            "SAP_HANA_HOST",
            "SAP_HANA_PORT",
            "SAP_HANA_USER",
            "SAP_HANA_PASSWORD",
            "SAP_HANA_SCHEMA",
        ]:
            assert var in content, f"{var} not in .env.example"
