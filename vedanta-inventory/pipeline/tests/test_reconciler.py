"""
Tests for pipeline/reconciler.py
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Point SERVING_DIR at a temp dir before importing reconciler
_tmp = tempfile.mkdtemp()
os.environ.setdefault("SERVING_DIR", _tmp)

from pipeline.reconciler import (
    reconcile_consumption,
    reconcile_stock_master,
    reconcile_po_history,
    write_report,
)


class TestReconcileConsumption:

    def _raw(self):
        return pd.DataFrame({
            "MBLNR": ["D1", "D2", "D3"],
            "BWART": ["261", "261", "101"],
            "MENGE": [10.0, 5.0, 3.0],
        })

    def _clean(self):
        return pd.DataFrame({
            "doc_number": ["D1", "D2"],
            "movement_type": ["261", "261"],
            "qty": [10.0, 5.0],
        })

    def test_reconciled_when_drops_explained(self):
        raw = self._raw()
        clean = self._clean()
        drops = [{"domain": "consumption_history", "reason": "BWART filter", "rows_dropped": 1}]
        result = reconcile_consumption(raw, clean, drops)
        assert result["status"] == "RECONCILED"
        assert result["unexplained_row_delta"] == 0

    def test_unreconciled_when_unexplained_drop(self):
        raw = self._raw()
        clean = self._clean()
        drops = []  # no drops logged but 1 row missing
        result = reconcile_consumption(raw, clean, drops)
        assert result["status"] == "UNRECONCILED"
        assert result["unexplained_row_delta"] == 1

    def test_qty_totals_reported(self):
        raw = self._raw()
        clean = self._clean()
        drops = [{"domain": "consumption_history", "reason": "BWART filter", "rows_dropped": 1}]
        result = reconcile_consumption(raw, clean, drops)
        # Raw BWART-filtered qty: 10+5 = 15 (101 excluded)
        assert result["raw_total_qty"] == 15.0
        assert result["clean_total_qty"] == 15.0


class TestReconcileStockMaster:

    def test_reconciled(self):
        raw = pd.DataFrame({
            "MATNR": ["M1", "M2", "M3"],
            "MTART": ["ZSPR", "ZSPN", "ROH"],
            "LABST": [100.0, 50.0, 20.0],
            "VERPR": [10.0, 20.0, 5.0],
        })
        clean = pd.DataFrame({
            "material_code": ["M1", "M2"],
            "unrestricted_stock": [100.0, 50.0],
            "unit_price": [10.0, 20.0],
        })
        drops = [{"domain": "stock_master", "reason": "out of scope", "rows_dropped": 1}]
        result = reconcile_stock_master(raw, clean, drops)
        assert result["status"] == "RECONCILED"
        assert result["clean_stock_value_inr"] == 2000.0  # 100×10 + 50×20


class TestWriteReport:

    def test_writes_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pipeline.reconciler.SERVING_DIR", tmp_path)
        monkeypatch.setattr("pipeline.reconciler.REPORT_PATH", tmp_path / "reconciliation_report.json")
        results = [
            {"domain": "consumption_history", "status": "RECONCILED", "raw_rows": 3, "clean_rows": 2,
             "explained_drops": 1, "unexplained_row_delta": 0, "drop_log": []},
        ]
        path = write_report(results)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["overall_status"] == "RECONCILED"
        assert len(data["domains"]) == 1

    def test_overall_unreconciled_if_any_domain_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pipeline.reconciler.SERVING_DIR", tmp_path)
        monkeypatch.setattr("pipeline.reconciler.REPORT_PATH", tmp_path / "reconciliation_report.json")
        results = [
            {"domain": "consumption_history", "status": "RECONCILED", "raw_rows": 3, "clean_rows": 3,
             "explained_drops": 0, "unexplained_row_delta": 0, "drop_log": []},
            {"domain": "stock_master", "status": "UNRECONCILED", "raw_rows": 5, "clean_rows": 3,
             "explained_drops": 1, "unexplained_row_delta": 1, "drop_log": []},
        ]
        path = write_report(results)
        data = json.loads(path.read_text())
        assert data["overall_status"] == "UNRECONCILED"
