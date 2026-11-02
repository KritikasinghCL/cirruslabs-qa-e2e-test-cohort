"""SAP HANA extraction pipeline for the Vedanta Inventory Programme.

Connects to SAP HANA, enumerates the 22 in-scope tables (stores & spares),
captures schema metadata, exports full datasets to Parquet, and writes a
manifest for downstream consumers.

Read-only: this module NEVER writes to SAP HANA.
"""
