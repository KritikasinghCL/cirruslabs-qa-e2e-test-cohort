"""
Transformer — S-2 (Devika Rao)

Takes raw DataFrames from the extractor and produces clean, typed,
deduplicated Parquet tables in SERVING_DIR/clean/<domain>/.

Rules:
- Maps SAP column names to canonical names (contract §2).
- Enforces ZSPR/ZSPN scope on stock_master and consumption_history.
- Applies BWART filter (G-08) to consumption_history.
- Price cascade: VERPR → STPRS → LAEPR → 0 with 'price_missing' flag (G-09).
- Deduplicates on primary keys defined in the contract.
- Coerces types; records every row dropped and why.
- Never silently drops rows — all drops are logged and counted.
- Returns (clean_df, drop_log) so the reconciler can account for every row.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from pipeline import config

logger = logging.getLogger(__name__)

CLEAN_DIR = Path(config.SERVING_DIR) / "clean"

# ---------------------------------------------------------------------------
# SAP field → canonical name mappings (from data_contract_v1.yaml §2)
# ---------------------------------------------------------------------------

CONS_HIST_RENAME: dict[str, str] = {
    "MBLNR": "doc_number",
    "ZEILE": "doc_line",
    "BUDAT": "posting_date",
    "MATNR": "material_code",
    "WERKS": "plant",
    "LGORT": "storage_location",
    "BWART": "movement_type",
    "MENGE": "qty",
    "MEINS": "uom",
    "DMBTR": "amount_inr",
    "WAERS": "currency",
    "KOSTL": "cost_centre",
    "AUFNR": "order_number",
    "BWTAR": "valuation_type",
}

STOCK_MASTER_RENAME: dict[str, str] = {
    "MATNR": "material_code",
    "MAKTX": "description",
    "MTART": "material_type",
    "MATKL": "category",
    "MEINS": "uom",
    "BRGEW": "gross_weight",
    "GEWEI": "weight_unit",
    "ZEINR": "drawing_number",
    "ERSDA": "creation_date",
    "WERKS": "plant",
    "EKGRP": "purchasing_group",
    "DISMM": "mrp_type",
    "MINBE": "sap_reorder_point",
    "EISBE": "sap_safety_stock",
    "MABST": "max_stock_level",
    "WEBAZ": "gr_processing_days",
    "PLIFZ": "planned_delivery_days",
    "LGPRO": "production_storage_location",
    "CRITICAL_FLAG": "critical_flag",
    "LGORT": "storage_location",
    "LABST": "unrestricted_stock",
    "EINME": "stock_in_transit",
    "INSME": "stock_in_inspection",
    "RETME": "blocked_stock",
    "BWKEY": "valuation_area",
    "STPRS": "standard_price",
    "VERPR": "moving_avg_price",
    "LAEPR": "last_purchase_price",
    "BKLAS": "valuation_class",
}

PO_HIST_RENAME: dict[str, str] = {
    "EBELN": "po_number",
    "BSART": "po_doc_type",
    "LIFNR": "vendor_number",
    "BEDAT": "po_creation_date",
    "WAERS": "currency",
    "EBELP": "po_line",
    "MATNR": "material_code",
    "WERKS": "plant",
    "MENGE": "po_qty",
    "MEINS": "uom",
    "NETPR": "net_price_inr",
    "EINDT": "delivery_date",
    "ELIKZ": "delivery_completed_flag",
    "REPOS": "invoice_receipt_flag",
    "EINDT_SCH": "scheduled_delivery_date",
    "MENGE_SCH": "scheduled_qty",
    "VGABE": "gr_transaction_type",
    "BUDAT_GR": "gr_posting_date",
    "MENGE_GR": "gr_qty",
    "DMBTR_GR": "gr_value_inr",
}

MAINT_CAL_RENAME: dict[str, str] = {
    "AUFNR": "order_number",
    "AUART": "order_type",
    "EQUNR": "equipment_number",
    "TPLNR": "functional_location",
    "WERKS": "plant",
    "GSTRP": "scheduled_start_date",
    "GLTRP": "scheduled_finish_date",
    "ISTAT": "system_status",
    "SHUTDOWN_FLAG": "shutdown_flag",
    "RESB_MATNR": "reserved_material",
    "RESB_BDMNG": "required_qty",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rename_columns(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Rename SAP columns to canonical names; leave unknown columns as-is."""
    present = {k: v for k, v in mapping.items() if k in df.columns}
    return df.rename(columns=present)


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace from all string columns."""
    str_cols = df.select_dtypes(include="object").columns
    df[str_cols] = df[str_cols].apply(lambda s: s.str.strip())
    return df


def _coerce_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _coerce_numeric(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _save_clean(df: pd.DataFrame, domain: str) -> Path:
    out_dir = CLEAN_DIR / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "clean.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Clean table saved: %s (%d rows)", out_path, len(df))
    return out_path


# ---------------------------------------------------------------------------
# Public transform functions
# ---------------------------------------------------------------------------

def transform_consumption_history(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Clean consumption history.

    Steps:
    1. Rename SAP → canonical columns.
    2. Strip strings.
    3. Coerce types (posting_date → date, qty/amount → float).
    4. Filter BWART to consumption movement types (G-08).
    5. Scope to ZSPR/ZSPN materials — requires a join with stock_master;
       we mark the column for downstream join rather than dropping here,
       because MSEG does not carry MTART.
    6. Drop rows with null primary key (doc_number, doc_line).
    7. Deduplicate on (doc_number, doc_line).
    8. Drop rows with qty <= 0 (reversals handled separately).
    """
    drop_log: list[dict] = []
    df = raw.copy()
    original_count = len(df)

    # 1. Rename
    df = _rename_columns(df, CONS_HIST_RENAME)

    # 2. Strip strings
    df = _strip_strings(df)

    # 3. Type coercion
    df = _coerce_date(df, "posting_date")
    for col in ["qty", "amount_inr"]:
        df = _coerce_numeric(df, col)

    # 4. BWART filter (G-08)
    if "movement_type" in df.columns:
        before = len(df)
        df = df[df["movement_type"].isin(config.CONSUMPTION_BWART_LIST)]
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "consumption_history",
                "reason": f"movement_type not in {config.CONSUMPTION_BWART_LIST}",
                "rows_dropped": dropped,
                "gap_ref": "G-08",
            })
            logger.info("BWART filter dropped %d rows (G-08)", dropped)
    else:
        drop_log.append({
            "domain": "consumption_history",
            "reason": "movement_type column absent — BWART filter could not be applied",
            "rows_dropped": 0,
            "gap_ref": "G-08",
        })
        logger.warning("G-08: movement_type column missing — BWART filter not applied")

    # 5. Null primary key
    pk_cols = [c for c in ["doc_number", "doc_line"] if c in df.columns]
    if pk_cols:
        before = len(df)
        df = df.dropna(subset=pk_cols)
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "consumption_history",
                "reason": "null primary key (doc_number / doc_line)",
                "rows_dropped": dropped,
            })

    # 6. Deduplicate
    if pk_cols:
        before = len(df)
        df = df.drop_duplicates(subset=pk_cols, keep="last")
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "consumption_history",
                "reason": "duplicate primary key (doc_number, doc_line) — kept last",
                "rows_dropped": dropped,
            })

    # 7. Drop non-positive qty
    if "qty" in df.columns:
        before = len(df)
        df = df[df["qty"] > 0]
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "consumption_history",
                "reason": "qty <= 0 (reversal or zero-movement line)",
                "rows_dropped": dropped,
            })

    logger.info(
        "consumption_history: %d raw → %d clean (dropped %d)",
        original_count, len(df), original_count - len(df),
    )
    _save_clean(df, "consumption_history")
    return df, drop_log


def transform_stock_master(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Clean stock / material master.

    Steps:
    1. Rename SAP → canonical columns.
    2. Strip strings.
    3. Coerce types.
    4. Scope to ZSPR/ZSPN (G-07 scope rule).
    5. Price cascade: moving_avg_price → standard_price → last_purchase_price → 0
       with price_missing flag (G-09).
    6. Null primary key drop.
    7. Deduplicate on (material_code, plant).
    8. Ensure unrestricted_stock >= 0.
    """
    drop_log: list[dict] = []
    df = raw.copy()
    original_count = len(df)

    # 1. Rename
    df = _rename_columns(df, STOCK_MASTER_RENAME)

    # 2. Strip strings
    df = _strip_strings(df)

    # 3. Type coercion
    df = _coerce_date(df, "creation_date")
    for col in [
        "unrestricted_stock", "stock_in_transit", "stock_in_inspection",
        "blocked_stock", "moving_avg_price", "standard_price",
        "last_purchase_price", "sap_reorder_point", "sap_safety_stock",
        "max_stock_level", "planned_delivery_days", "gr_processing_days",
        "gross_weight",
    ]:
        df = _coerce_numeric(df, col)

    # 4. Scope to ZSPR/ZSPN
    if "material_type" in df.columns:
        before = len(df)
        df = df[df["material_type"].isin(config.MATERIAL_TYPE_SCOPE)]
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "stock_master",
                "reason": f"material_type not in {config.MATERIAL_TYPE_SCOPE} (out of scope)",
                "rows_dropped": dropped,
            })
            logger.info("Scope filter dropped %d rows (non-ZSPR/ZSPN)", dropped)
    else:
        drop_log.append({
            "domain": "stock_master",
            "reason": "material_type column absent — scope filter not applied",
            "rows_dropped": 0,
            "gap_ref": "G-07",
        })
        logger.warning("material_type column missing — ZSPR/ZSPN scope filter not applied")

    # 5. Price cascade (G-09)
    df["unit_price"] = np.nan
    df["price_missing"] = False

    for price_col in ["moving_avg_price", "standard_price", "last_purchase_price"]:
        if price_col in df.columns:
            mask = df["unit_price"].isna() & df[price_col].notna() & (df[price_col] > 0)
            df.loc[mask, "unit_price"] = df.loc[mask, price_col]

    # Fill remaining with 0 and flag
    still_missing = df["unit_price"].isna()
    df.loc[still_missing, "unit_price"] = 0.0
    df.loc[still_missing, "price_missing"] = True
    missing_price_count = int(still_missing.sum())
    if missing_price_count:
        drop_log.append({
            "domain": "stock_master",
            "reason": "unit_price could not be derived (VERPR/STPRS/LAEPR all null/zero) — set to 0, price_missing=True",
            "rows_dropped": 0,
            "rows_flagged": missing_price_count,
            "gap_ref": "G-09",
        })
        logger.warning("G-09: %d materials have price_missing=True", missing_price_count)

    # 6. Null primary key
    pk_cols = [c for c in ["material_code", "plant"] if c in df.columns]
    if pk_cols:
        before = len(df)
        df = df.dropna(subset=pk_cols)
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "stock_master",
                "reason": "null primary key (material_code / plant)",
                "rows_dropped": dropped,
            })

    # 7. Deduplicate on (material_code, plant)
    if pk_cols:
        before = len(df)
        df = df.drop_duplicates(subset=pk_cols, keep="last")
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "stock_master",
                "reason": "duplicate (material_code, plant) — kept last",
                "rows_dropped": dropped,
            })

    # 8. Non-negative stock
    if "unrestricted_stock" in df.columns:
        before = len(df)
        df = df[df["unrestricted_stock"] >= 0]
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "stock_master",
                "reason": "unrestricted_stock < 0 (data quality issue)",
                "rows_dropped": dropped,
            })

    # Ensure critical_flag is boolean
    if "critical_flag" in df.columns:
        df["critical_flag"] = df["critical_flag"].fillna("").astype(str).str.upper().isin(
            ["Y", "YES", "1", "TRUE", "X"]
        )
    else:
        # G-01: critical_flag absent
        df["critical_flag"] = False
        drop_log.append({
            "domain": "stock_master",
            "reason": "critical_flag column absent — defaulted to False",
            "rows_dropped": 0,
            "gap_ref": "G-01",
        })

    # Lead time = planned_delivery_days + gr_processing_days
    plifz = df["planned_delivery_days"] if "planned_delivery_days" in df.columns else pd.Series(dtype=float)
    webaz = df["gr_processing_days"] if "gr_processing_days" in df.columns else pd.Series(dtype=float)
    if "planned_delivery_days" in df.columns and "gr_processing_days" in df.columns:
        df["lead_time_days"] = df["planned_delivery_days"].fillna(0) + df["gr_processing_days"].fillna(0)
    elif "planned_delivery_days" in df.columns:
        df["lead_time_days"] = df["planned_delivery_days"]
    else:
        df["lead_time_days"] = np.nan

    logger.info(
        "stock_master: %d raw → %d clean (dropped %d)",
        original_count, len(df), original_count - len(df),
    )
    _save_clean(df, "stock_master")
    return df, drop_log


def transform_po_history(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Clean PO history.

    Steps:
    1. Rename SAP → canonical columns.
    2. Strip strings.
    3. Coerce types.
    4. Keep only GR transactions (VGABE = '1') for lead-time calculation.
    5. Null primary key drop.
    6. Deduplicate on (po_number, po_line).
    7. Derive actual_lead_time_days = gr_posting_date - po_creation_date.
    """
    drop_log: list[dict] = []
    df = raw.copy()
    original_count = len(df)

    # 1. Rename
    df = _rename_columns(df, PO_HIST_RENAME)

    # 2. Strip strings
    df = _strip_strings(df)

    # 3. Type coercion
    for col in ["po_creation_date", "delivery_date", "scheduled_delivery_date",
                "gr_posting_date"]:
        df = _coerce_date(df, col)
    for col in ["po_qty", "net_price_inr", "scheduled_qty", "gr_qty", "gr_value_inr"]:
        df = _coerce_numeric(df, col)

    # 4. Null primary key
    pk_cols = [c for c in ["po_number", "po_line"] if c in df.columns]
    if pk_cols:
        before = len(df)
        df = df.dropna(subset=pk_cols)
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "po_history",
                "reason": "null primary key (po_number / po_line)",
                "rows_dropped": dropped,
            })

    # 5. Deduplicate
    if pk_cols:
        before = len(df)
        df = df.drop_duplicates(subset=pk_cols, keep="last")
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "po_history",
                "reason": "duplicate (po_number, po_line) — kept last",
                "rows_dropped": dropped,
            })

    # 6. Derive actual lead time (days from PO creation to GR)
    if "gr_posting_date" in df.columns and "po_creation_date" in df.columns:
        df["actual_lead_time_days"] = (
            df["gr_posting_date"] - df["po_creation_date"]
        ).dt.days
        # Negative lead times are data errors — flag but keep
        neg_lt = (df["actual_lead_time_days"] < 0).sum()
        if neg_lt:
            drop_log.append({
                "domain": "po_history",
                "reason": f"{neg_lt} rows have negative actual_lead_time_days (GR before PO creation) — flagged, not dropped",
                "rows_dropped": 0,
                "rows_flagged": int(neg_lt),
            })

    logger.info(
        "po_history: %d raw → %d clean (dropped %d)",
        original_count, len(df), original_count - len(df),
    )
    _save_clean(df, "po_history")
    return df, drop_log


def transform_maintenance_calendar(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Clean maintenance / shutdown calendar.

    Steps:
    1. Rename SAP → canonical columns.
    2. Strip strings.
    3. Coerce types.
    4. Null primary key drop.
    5. Deduplicate on order_number.
    6. Derive shutdown_flag if absent (G-04).
    """
    drop_log: list[dict] = []
    df = raw.copy()
    original_count = len(df)

    # 1. Rename
    df = _rename_columns(df, MAINT_CAL_RENAME)

    # 2. Strip strings
    df = _strip_strings(df)

    # 3. Type coercion
    for col in ["scheduled_start_date", "scheduled_finish_date"]:
        df = _coerce_date(df, col)
    df = _coerce_numeric(df, "required_qty")

    # 4. Null primary key
    if "order_number" in df.columns:
        before = len(df)
        df = df.dropna(subset=["order_number"])
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "maintenance_calendar",
                "reason": "null order_number",
                "rows_dropped": dropped,
            })

    # 5. Deduplicate
    if "order_number" in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset=["order_number"], keep="last")
        dropped = before - len(df)
        if dropped:
            drop_log.append({
                "domain": "maintenance_calendar",
                "reason": "duplicate order_number — kept last",
                "rows_dropped": dropped,
            })

    # 6. Derive shutdown_flag if absent (G-04)
    # Vedanta uses PM01/PM02/PM03 order types; PM03 = planned shutdown
    if "shutdown_flag" not in df.columns or df["shutdown_flag"].isna().all():
        if "order_type" in df.columns:
            df["shutdown_flag"] = df["order_type"].str.upper().isin(["PM03", "ZPM3", "ZSD"])
            drop_log.append({
                "domain": "maintenance_calendar",
                "reason": "shutdown_flag absent — derived from order_type IN (PM03, ZPM3, ZSD) (G-04 fallback)",
                "rows_dropped": 0,
                "gap_ref": "G-04",
            })
            logger.warning("G-04: shutdown_flag derived from order_type (fallback)")
        else:
            df["shutdown_flag"] = False
            drop_log.append({
                "domain": "maintenance_calendar",
                "reason": "shutdown_flag and order_type both absent — defaulted to False (G-04)",
                "rows_dropped": 0,
                "gap_ref": "G-04",
            })
    else:
        df["shutdown_flag"] = df["shutdown_flag"].fillna("").astype(str).str.upper().isin(
            ["Y", "YES", "1", "TRUE", "X"]
        )

    logger.info(
        "maintenance_calendar: %d raw → %d clean (dropped %d)",
        original_count, len(df), original_count - len(df),
    )
    _save_clean(df, "maintenance_calendar")
    return df, drop_log
