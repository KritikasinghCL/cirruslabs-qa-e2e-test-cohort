#!/usr/bin/env python3
"""SAP HANA extraction pipeline for the Vedanta Inventory Programme.

Connects to SAP HANA via hdbcli, enumerates all 22 in-scope tables, and for
each table:
  1. Captures table name, full schema (column names and data types), and total
     row count.
  2. Fetches the first 10 sample rows for preview.
  3. Exports the full dataset to a Parquet file under
     sap_extraction/parquet/<table_name>.parquet.
  4. Writes a manifest JSON (sap_extraction/manifest.json) listing every table
     with its name, column count, row count, schema, sample rows, and Parquet
     file path.
  5. Validates each Parquet file by re-reading it and asserting the row count
     matches the source.

Connection credentials are read from environment variables (see .env.example):
  SAP_HANA_HOST, SAP_HANA_PORT, SAP_HANA_USER, SAP_HANA_PASSWORD, SAP_HANA_SCHEMA

Read-only: this script NEVER writes to SAP HANA.

Usage:
    python -m sap_extraction.extract          # from the repo root
    python sap_extraction/extract.py          # direct invocation
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

try:
    from hdbcli import dbapi as hdbcli_dbapi
except ImportError:
    hdbcli_dbapi = None  # type: ignore[assignment]

from sap_extraction.tables import TABLES_IN_SCOPE

logger = logging.getLogger("sap_extraction")

_SCRIPT_DIR = Path(__file__).resolve().parent
_PARQUET_DIR = _SCRIPT_DIR / "parquet"
_MANIFEST_PATH = _SCRIPT_DIR / "manifest.json"
_SAMPLE_ROWS = 10


def _get_env(name: str, required: bool = True) -> str:
    """Read an environment variable; raise if required and missing."""
    value = os.environ.get(name, "").strip()
    if required and not value:
        raise EnvironmentError(
            f"Required environment variable {name} is not set. "
            f"Copy .env.example to .env and fill in SAP HANA credentials."
        )
    return value


def connect_sap_hana() -> "hdbcli_dbapi.Connection":
    """Open a read-only connection to SAP HANA."""
    if hdbcli_dbapi is None:
        raise ImportError(
            "hdbcli is not installed. Run: pip install hdbcli\n"
            "See sap_extraction/requirements.txt"
        )

    host = _get_env("SAP_HANA_HOST")
    port = int(_get_env("SAP_HANA_PORT", required=False) or "443")
    user = _get_env("SAP_HANA_USER")
    password = _get_env("SAP_HANA_PASSWORD")

    logger.info("Connecting to SAP HANA at %s:%d as %s ...", host, port, user)

    conn = hdbcli_dbapi.connect(
        address=host, port=port, user=user, password=password,
        encrypt=True, sslValidateCertificate=False,
    )

    cursor = conn.cursor()
    try:
        cursor.execute("SET TRANSACTION READ ONLY")
    except Exception:
        logger.warning("Could not set session to READ ONLY -- proceeding with caution.")
    finally:
        cursor.close()

    logger.info("Connected to SAP HANA successfully.")
    return conn


def get_table_schema(conn, sap_table: str, schema: Optional[str] = None) -> List[Dict[str, str]]:
    """Return column names and data types for a table."""
    schema = schema or _get_env("SAP_HANA_SCHEMA", required=False) or None
    query = """
        SELECT COLUMN_NAME, DATA_TYPE_NAME, LENGTH, IS_NULLABLE
        FROM TABLE_COLUMNS
        WHERE TABLE_NAME = ?
    """
    params: list = [sap_table]
    if schema:
        query += " AND SCHEMA_NAME = ?"
        params.append(schema)
    query += " ORDER BY POSITION"

    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        cursor.close()

    return [
        {"column_name": row[0], "data_type": row[1], "length": row[2], "is_nullable": row[3]}
        for row in rows
    ]


def get_row_count(conn, sap_table: str, schema: Optional[str] = None) -> int:
    """Return the total row count for a table."""
    schema = schema or _get_env("SAP_HANA_SCHEMA", required=False) or None
    qualified = f'"{schema}"."{sap_table}"' if schema else f'"{sap_table}"'
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {qualified}")
        result = cursor.fetchone()
        return int(result[0]) if result else 0
    finally:
        cursor.close()


def get_sample_rows(conn, sap_table: str, n: int = _SAMPLE_ROWS, schema: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the first n rows from a table as a list of dicts."""
    schema = schema or _get_env("SAP_HANA_SCHEMA", required=False) or None
    qualified = f'"{schema}"."{sap_table}"' if schema else f'"{sap_table}"'
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM {qualified} LIMIT {int(n)}")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [
        {col: _serialise_value(val) for col, val in zip(columns, row)}
        for row in rows
    ]


def _serialise_value(val: Any) -> Any:
    """Make a value JSON-serialisable."""
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    if isinstance(val, bytes):
        return val.hex()
    if isinstance(val, (datetime,)):
        return val.isoformat()
    return str(val)


def export_table_to_parquet(conn, sap_table: str, output_path: Path, schema: Optional[str] = None) -> int:
    """Export a full table to a Parquet file. Returns the row count written."""
    schema_name = schema or _get_env("SAP_HANA_SCHEMA", required=False) or None
    qualified = f'"{schema_name}"."{sap_table}"' if schema_name else f'"{sap_table}"'
    query = f"SELECT * FROM {qualified}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Exporting %s -> %s ...", sap_table, output_path)

    chunk_size = 50_000
    cursor = conn.cursor()
    try:
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        first_chunk = True
        total_rows = 0
        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break
            df_chunk = pd.DataFrame(rows, columns=columns)
            total_rows += len(df_chunk)
            if first_chunk:
                df_chunk.to_parquet(output_path, engine="pyarrow", index=False)
                first_chunk = False
            else:
                existing = pd.read_parquet(output_path, engine="pyarrow")
                combined = pd.concat([existing, df_chunk], ignore_index=True)
                combined.to_parquet(output_path, engine="pyarrow", index=False)
    finally:
        cursor.close()

    if total_rows == 0:
        pd.DataFrame(columns=columns).to_parquet(output_path, engine="pyarrow", index=False)

    logger.info("  -> %s: %d rows written.", sap_table, total_rows)
    return total_rows


def validate_parquet(parquet_path: Path, expected_row_count: int, table_name: str) -> Tuple[bool, str]:
    """Re-read a Parquet file and assert the row count matches the source."""
    if not parquet_path.exists():
        return (False, f"FAIL: {table_name} -- Parquet file not found at {parquet_path}")
    df = pd.read_parquet(parquet_path, engine="pyarrow")
    actual = len(df)
    if actual != expected_row_count:
        return (False, f"FAIL: {table_name} -- row count mismatch: source={expected_row_count}, parquet={actual}")
    return (True, f"PASS: {table_name} -- {actual} rows verified in {parquet_path.name}")


def write_manifest(entries: List[Dict[str, Any]], output_path: Path) -> None:
    """Write the extraction manifest JSON."""
    manifest = {
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        "tables_in_scope": len(entries),
        "tables": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    logger.info("Manifest written to %s", output_path)


def run_extraction() -> Dict[str, Any]:
    """Run the full extraction pipeline."""
    schema = _get_env("SAP_HANA_SCHEMA", required=False) or None
    logger.info("=" * 72)
    logger.info("SAP HANA Extraction Pipeline -- Vedanta Inventory Programme")
    logger.info("Tables in scope: %d", len(TABLES_IN_SCOPE))
    logger.info("Output directory: %s", _PARQUET_DIR)
    logger.info("=" * 72)

    conn = connect_sap_hana()
    manifest_entries: List[Dict[str, Any]] = []
    validation_results: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        for idx, table_spec in enumerate(TABLES_IN_SCOPE, 1):
            table_label = f"[{idx}/{len(TABLES_IN_SCOPE)}] {table_spec.logical_name} ({table_spec.sap_table})"
            logger.info("-" * 60)
            logger.info("Processing %s", table_label)
            try:
                table_schema = get_table_schema(conn, table_spec.sap_table, schema)
                row_count = get_row_count(conn, table_spec.sap_table, schema)
                sample = get_sample_rows(conn, table_spec.sap_table, _SAMPLE_ROWS, schema)
                parquet_path = _PARQUET_DIR / f"{table_spec.logical_name}.parquet"
                export_table_to_parquet(conn, table_spec.sap_table, parquet_path, schema)
                passed, message = validate_parquet(parquet_path, row_count, table_spec.logical_name)
                validation_results.append({"table": table_spec.logical_name, "passed": passed, "message": message})
                if not passed:
                    errors.append(message)
                manifest_entries.append({
                    "logical_name": table_spec.logical_name,
                    "sap_table": table_spec.sap_table,
                    "description": table_spec.description,
                    "column_count": len(table_schema),
                    "row_count": row_count,
                    "schema": table_schema,
                    "sample_rows": sample,
                    "parquet_file": str(parquet_path.relative_to(_SCRIPT_DIR)),
                })
            except Exception as exc:
                msg = f"ERROR extracting {table_spec.logical_name}: {exc}"
                logger.error(msg, exc_info=True)
                errors.append(msg)
                manifest_entries.append({
                    "logical_name": table_spec.logical_name,
                    "sap_table": table_spec.sap_table,
                    "description": table_spec.description,
                    "column_count": 0, "row_count": 0,
                    "schema": [], "sample_rows": [],
                    "parquet_file": None, "error": str(exc),
                })
    finally:
        conn.close()

    write_manifest(manifest_entries, _MANIFEST_PATH)
    tables_ok = sum(1 for v in validation_results if v["passed"])
    tables_failed = sum(1 for v in validation_results if not v["passed"])
    total_rows = sum(e["row_count"] for e in manifest_entries)

    return {
        "tables_in_scope": len(TABLES_IN_SCOPE),
        "tables_extracted": len(manifest_entries),
        "tables_validated_ok": tables_ok,
        "tables_validated_fail": tables_failed,
        "total_rows": total_rows,
        "errors": errors,
        "manifest_path": str(_MANIFEST_PATH),
        "parquet_dir": str(_PARQUET_DIR),
    }


def main() -> None:
    """CLI entry point with logging setup."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        summary = run_extraction()
    except EnvironmentError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)
    except ImportError as exc:
        logger.error("Dependency error: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Unexpected error: %s", exc, exc_info=True)
        sys.exit(2)

    if summary["tables_validated_fail"] > 0:
        logger.error("Validation failures detected -- review errors above.")
        sys.exit(1)

    logger.info("All %d tables extracted and validated successfully.", summary["tables_in_scope"])


if __name__ == "__main__":
    main()
