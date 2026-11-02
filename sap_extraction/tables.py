"""Registry of the 22 SAP HANA tables in scope for the inventory programme.

Scope: stores and spares — material types ZSPR and ZSPN.
Anything outside these tables is out of scope.

Each entry maps a logical name to the SAP table name. The logical name is
used for Parquet file naming and manifest keys; the SAP table name is what
the extraction queries against.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple


class TableSpec(NamedTuple):
    """One in-scope SAP table."""

    logical_name: str
    sap_table: str
    description: str


# fmt: off
TABLES_IN_SCOPE: List[TableSpec] = [
    # --- Material master & classification ---
    TableSpec("material_master",         "MARA",   "General material data"),
    TableSpec("material_description",    "MAKT",   "Material descriptions"),
    TableSpec("material_plant",          "MARC",   "Plant data for material"),
    TableSpec("material_storage",        "MARD",   "Storage location data for material"),
    TableSpec("material_valuation",      "MBEW",   "Material valuation"),
    TableSpec("material_classification", "AUSP",   "Characteristic values (classification)"),

    # --- Stock & inventory ---
    TableSpec("stock_current",           "MCHB",   "Batch stocks"),
    TableSpec("material_documents",      "MKPF",   "Material document header"),
    TableSpec("material_doc_items",      "MSEG",   "Material document items (movements)"),
    TableSpec("warehouse_stocks",        "MSLB",   "Special stocks at vendor"),

    # --- Consumption & movements ---
    TableSpec("consumption_history",     "MVER",   "Material consumption (MRP area)"),
    TableSpec("reservation_header",      "RKPF",   "Reservation header"),
    TableSpec("reservation_items",       "RESB",   "Reservation items"),

    # --- Purchasing ---
    TableSpec("purchase_req_header",     "EBAN",   "Purchase requisition"),
    TableSpec("purchase_order_header",   "EKKO",   "Purchasing document header"),
    TableSpec("purchase_order_items",    "EKPO",   "Purchasing document items"),
    TableSpec("purchase_order_history",  "EKBE",   "Purchasing document history"),
    TableSpec("vendor_master",           "LFA1",   "Vendor master (general)"),

    # --- MRP & planning ---
    TableSpec("mrp_parameters",          "MDKP",   "MRP document header"),
    TableSpec("mrp_items",               "MDTB",   "MRP table (individual records)"),

    # --- Plant & org ---
    TableSpec("plant_master",            "T001W",  "Plants / branches"),
    TableSpec("storage_locations",       "T001L",  "Storage locations"),
]
# fmt: on

assert len(TABLES_IN_SCOPE) == 22, (
    f"Expected 22 tables in scope, got {len(TABLES_IN_SCOPE)}"
)

# Quick lookup: logical_name -> TableSpec
TABLE_LOOKUP: Dict[str, TableSpec] = {t.logical_name: t for t in TABLES_IN_SCOPE}
