"""
Tests for pipeline/transformer.py

These tests use synthetic DataFrames that mirror the SAP field names
from data_contract_v1.yaml. They do NOT use GCS or any external service.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from pipeline.transformer import (
    transform_consumption_history,
    transform_stock_master,
    transform_po_history,
    transform_maintenance_calendar,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cons_df(**overrides) -> pd.DataFrame:
    base = {
        "MBLNR": ["5000000001", "5000000002", "5000000003"],
        "ZEILE": ["0001", "0001", "0001"],
        "BUDAT": ["2026-01-15", "2026-02-20", "2026-03-10"],
        "MATNR": ["MAT001", "MAT001", "MAT002"],
        "WERKS": ["P001", "P001", "P001"],
        "LGORT": ["0001", "0001", "0001"],
        "BWART": ["261", "261", "201"],
        "MENGE": [10.0, 5.0, 3.0],
        "MEINS": ["EA", "EA", "EA"],
        "DMBTR": [1000.0, 500.0, 300.0],
        "WAERS": ["INR", "INR", "INR"],
        "KOSTL": ["CC001", "CC001", "CC002"],
        "AUFNR": ["ORD001", "ORD001", "ORD002"],
        "BWTAR": ["", "", ""],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _make_stock_df(**overrides) -> pd.DataFrame:
    base = {
        "MATNR": ["MAT001", "MAT002", "MAT003"],
        "MAKTX": ["Bearing 6205", "Seal Kit", "Pump Impeller"],
        "MTART": ["ZSPR", "ZSPN", "ROH"],  # ROH should be filtered out
        "MATKL": ["MECH", "SEAL", "PUMP"],
        "MEINS": ["EA", "EA", "EA"],
        "WERKS": ["P001", "P001", "P001"],
        "PLIFZ": [30, 45, 60],
        "WEBAZ": [5, 5, 5],
        "CRITICAL_FLAG": ["Y", "N", "Y"],
        "LGORT": ["0001", "0001", "0001"],
        "LABST": [100.0, 50.0, 20.0],
        "EINME": [0.0, 0.0, 0.0],
        "INSME": [0.0, 0.0, 0.0],
        "RETME": [0.0, 0.0, 0.0],
        "BWKEY": ["P001", "P001", "P001"],
        "STPRS": [0.0, 0.0, 0.0],
        "VERPR": [150.0, 200.0, 0.0],
        "LAEPR": [0.0, 0.0, 500.0],
        "BKLAS": ["3000", "3000", "3000"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _make_po_df(**overrides) -> pd.DataFrame:
    base = {
        "EBELN": ["4500000001", "4500000002"],
        "BSART": ["NB", "NB"],
        "LIFNR": ["V001", "V002"],
        "BEDAT": ["2026-01-01", "2026-02-01"],
        "WAERS": ["INR", "INR"],
        "EBELP": ["00010", "00010"],
        "MATNR": ["MAT001", "MAT002"],
        "WERKS": ["P001", "P001"],
        "MENGE": [50.0, 30.0],
        "MEINS": ["EA", "EA"],
        "NETPR": [140.0, 190.0],
        "EINDT": ["2026-02-01", "2026-03-01"],
        "ELIKZ": ["", ""],
        "REPOS": ["X", "X"],
        "EINDT_SCH": ["2026-02-01", "2026-03-01"],
        "MENGE_SCH": [50.0, 30.0],
        "VGABE": ["1", "1"],
        "BUDAT_GR": ["2026-02-10", "2026-03-05"],
        "MENGE_GR": [50.0, 30.0],
        "DMBTR_GR": [7000.0, 5700.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _make_maint_df(**overrides) -> pd.DataFrame:
    base = {
        "AUFNR": ["ORD001", "ORD002"],
        "AUART": ["PM03", "PM01"],
        "EQUNR": ["EQ001", "EQ002"],
        "TPLNR": ["FL001", "FL002"],
        "WERKS": ["P001", "P001"],
        "GSTRP": ["2026-04-01", "2026-05-01"],
        "GLTRP": ["2026-04-07", "2026-05-03"],
        "ISTAT": ["REL", "TECO"],
        "SHUTDOWN_FLAG": ["Y", "N"],
        "RESB_MATNR": ["MAT001", "MAT002"],
        "RESB_BDMNG": [10.0, 5.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# Consumption history tests
# ---------------------------------------------------------------------------

class TestTransformConsumptionHistory:

    def test_renames_sap_columns(self):
        df, _ = transform_consumption_history(_make_cons_df())
        assert "posting_date" in df.columns
        assert "material_code" in df.columns
        assert "movement_type" in df.columns
        assert "qty" in df.columns
        # SAP names should be gone
        assert "MBLNR" not in df.columns
        assert "BUDAT" not in df.columns

    def test_bwart_filter_keeps_consumption_types(self):
        df, drops = transform_consumption_history(_make_cons_df())
        # All rows have BWART 261 or 201 — should all pass
        assert len(df) == 3

    def test_bwart_filter_drops_non_consumption(self):
        raw = _make_cons_df(BWART=["261", "101", "501"])  # 101 and 501 not in list
        df, drops = transform_consumption_history(raw)
        assert len(df) == 1
        bwart_drop = next((d for d in drops if d.get("gap_ref") == "G-08"), None)
        assert bwart_drop is not None
        assert bwart_drop["rows_dropped"] == 2

    def test_deduplicates_on_primary_key(self):
        raw = _make_cons_df(
            MBLNR=["5000000001", "5000000001", "5000000002"],
            ZEILE=["0001", "0001", "0001"],
        )
        df, drops = transform_consumption_history(raw)
        assert len(df) == 2  # duplicate removed
        dup_drop = next((d for d in drops if "duplicate" in d.get("reason", "")), None)
        assert dup_drop is not None

    def test_drops_zero_qty(self):
        raw = _make_cons_df(MENGE=[10.0, 0.0, 3.0])
        df, drops = transform_consumption_history(raw)
        assert len(df) == 2
        qty_drop = next((d for d in drops if "qty" in d.get("reason", "")), None)
        assert qty_drop is not None

    def test_posting_date_coerced_to_datetime(self):
        df, _ = transform_consumption_history(_make_cons_df())
        assert pd.api.types.is_datetime64_any_dtype(df["posting_date"])

    def test_drop_log_accounts_for_all_drops(self):
        raw = _make_cons_df(
            BWART=["261", "999", "201"],
            MENGE=[10.0, 0.0, 3.0],
        )
        raw_count = len(raw)
        df, drops = transform_consumption_history(raw)
        explained = sum(d.get("rows_dropped", 0) for d in drops)
        assert raw_count - len(df) == explained


# ---------------------------------------------------------------------------
# Stock master tests
# ---------------------------------------------------------------------------

class TestTransformStockMaster:

    def test_renames_sap_columns(self):
        df, _ = transform_stock_master(_make_stock_df())
        assert "material_code" in df.columns
        assert "unrestricted_stock" in df.columns
        assert "moving_avg_price" in df.columns
        assert "MATNR" not in df.columns

    def test_scope_filter_keeps_zspr_zspn(self):
        df, drops = transform_stock_master(_make_stock_df())
        # ROH should be filtered out
        assert len(df) == 2
        assert set(df["material_type"].unique()).issubset({"ZSPR", "ZSPN"})

    def test_scope_filter_drop_logged(self):
        _, drops = transform_stock_master(_make_stock_df())
        scope_drop = next((d for d in drops if "out of scope" in d.get("reason", "")), None)
        assert scope_drop is not None
        assert scope_drop["rows_dropped"] == 1

    def test_price_cascade_verpr_first(self):
        df, _ = transform_stock_master(_make_stock_df())
        # MAT001: VERPR=150 → unit_price=150
        mat001 = df[df["material_code"] == "MAT001"].iloc[0]
        assert mat001["unit_price"] == 150.0
        assert mat001["price_missing"] == False

    def test_price_cascade_falls_back_to_laepr(self):
        # MAT002: VERPR=200 → unit_price=200 (ZSPN)
        df, _ = transform_stock_master(_make_stock_df())
        mat002 = df[df["material_code"] == "MAT002"].iloc[0]
        assert mat002["unit_price"] == 200.0

    def test_price_missing_flag_when_all_zero(self):
        raw = _make_stock_df(
            MATNR=["MAT001", "MAT002"],
            MAKTX=["Bearing 6205", "Seal Kit"],
            MTART=["ZSPR", "ZSPN"],
            MATKL=["MECH", "SEAL"],
            MEINS=["EA", "EA"],
            WERKS=["P001", "P001"],
            PLIFZ=[30, 45],
            WEBAZ=[5, 5],
            CRITICAL_FLAG=["Y", "N"],
            LGORT=["0001", "0001"],
            LABST=[100.0, 50.0],
            EINME=[0.0, 0.0],
            INSME=[0.0, 0.0],
            RETME=[0.0, 0.0],
            BWKEY=["P001", "P001"],
            STPRS=[0.0, 0.0],
            VERPR=[0.0, 0.0],
            LAEPR=[0.0, 0.0],
            BKLAS=["3000", "3000"],
        )
        # Both rows are ZSPR/ZSPN — all prices zero → price_missing=True
        df, drops = transform_stock_master(raw)
        zspr_zspn = df[df["material_type"].isin(["ZSPR", "ZSPN"])]
        assert zspr_zspn["price_missing"].all()
        price_drop = next((d for d in drops if "G-09" in d.get("gap_ref", "")), None)
        assert price_drop is not None

    def test_critical_flag_parsed_from_y_n(self):
        df, _ = transform_stock_master(_make_stock_df())
        mat001 = df[df["material_code"] == "MAT001"].iloc[0]
        assert mat001["critical_flag"] == True
        mat002 = df[df["material_code"] == "MAT002"].iloc[0]
        assert mat002["critical_flag"] == False

    def test_lead_time_computed(self):
        df, _ = transform_stock_master(_make_stock_df())
        mat001 = df[df["material_code"] == "MAT001"].iloc[0]
        # PLIFZ=30 + WEBAZ=5 = 35
        assert mat001["lead_time_days"] == 35.0

    def test_deduplicates_on_material_plant(self):
        raw = _make_stock_df(
            MATNR=["MAT001", "MAT001", "MAT002"],
            MTART=["ZSPR", "ZSPR", "ZSPN"],
        )
        df, drops = transform_stock_master(raw)
        assert len(df) == 2
        dup_drop = next((d for d in drops if "duplicate" in d.get("reason", "")), None)
        assert dup_drop is not None


# ---------------------------------------------------------------------------
# PO history tests
# ---------------------------------------------------------------------------

class TestTransformPOHistory:

    def test_renames_sap_columns(self):
        df, _ = transform_po_history(_make_po_df())
        assert "po_number" in df.columns
        assert "material_code" in df.columns
        assert "gr_posting_date" in df.columns
        assert "EBELN" not in df.columns

    def test_actual_lead_time_derived(self):
        df, _ = transform_po_history(_make_po_df())
        # MAT001: GR 2026-02-10, PO 2026-01-01 → 40 days
        mat001 = df[df["material_code"] == "MAT001"].iloc[0]
        assert mat001["actual_lead_time_days"] == 40

    def test_deduplicates_on_po_number_line(self):
        raw = _make_po_df(
            EBELN=["4500000001", "4500000001"],
            EBELP=["00010", "00010"],
        )
        df, drops = transform_po_history(raw)
        assert len(df) == 1

    def test_negative_lead_time_flagged_not_dropped(self):
        raw = _make_po_df(
            BEDAT=["2026-03-01", "2026-02-01"],
            BUDAT_GR=["2026-02-10", "2026-03-05"],  # GR before PO for first row
        )
        df, drops = transform_po_history(raw)
        assert len(df) == 2  # not dropped
        neg_flag = next((d for d in drops if "negative" in d.get("reason", "").lower()), None)
        assert neg_flag is not None


# ---------------------------------------------------------------------------
# Maintenance calendar tests
# ---------------------------------------------------------------------------

class TestTransformMaintenanceCalendar:

    def test_renames_sap_columns(self):
        df, _ = transform_maintenance_calendar(_make_maint_df())
        assert "order_number" in df.columns
        assert "scheduled_start_date" in df.columns
        assert "shutdown_flag" in df.columns
        assert "AUFNR" not in df.columns

    def test_shutdown_flag_parsed(self):
        df, _ = transform_maintenance_calendar(_make_maint_df())
        ord1 = df[df["order_number"] == "ORD001"].iloc[0]
        assert ord1["shutdown_flag"] == True
        ord2 = df[df["order_number"] == "ORD002"].iloc[0]
        assert ord2["shutdown_flag"] == False

    def test_shutdown_flag_derived_from_order_type_when_absent(self):
        raw = _make_maint_df()
        raw = raw.drop(columns=["SHUTDOWN_FLAG"])
        df, drops = transform_maintenance_calendar(raw)
        # PM03 → True, PM01 → False
        ord1 = df[df["order_number"] == "ORD001"].iloc[0]
        assert ord1["shutdown_flag"] == True
        g04_drop = next((d for d in drops if "G-04" in d.get("gap_ref", "")), None)
        assert g04_drop is not None

    def test_deduplicates_on_order_number(self):
        raw = _make_maint_df(AUFNR=["ORD001", "ORD001"])
        df, drops = transform_maintenance_calendar(raw)
        assert len(df) == 1
