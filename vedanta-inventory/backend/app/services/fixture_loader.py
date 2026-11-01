"""
Fixture loader — used ONLY for local dev and unit tests.
Never called in the live pipeline (USE_TEST_FIXTURES must be True).
"""
from __future__ import annotations
import os
import pandas as pd
from app.core.config import settings
from app.models.schemas import (
    ConsumptionHistory, ConsumptionRecord,
    StockMaster, StockMasterRecord,
    POHistory, PORecord,
    ShutdownCalendar, ShutdownRecord,
    ForecastResponse, ForecastPeriod,
)


def _fixtures_path(filename: str) -> str:
    return os.path.join(settings.FIXTURES_DIR, filename)


def load_fixtures_if_enabled():
    assert settings.USE_TEST_FIXTURES, "load_fixtures_if_enabled called outside test mode"
    stock_master = _load_stock_master_fixture()
    consumption = _load_consumption_fixture()
    po_history = _load_po_history_fixture()
    return stock_master, consumption, po_history


def _load_stock_master_fixture() -> StockMaster:
    df = pd.read_csv(_fixtures_path("test_stock_master.csv"))
    df = df[df["material_type"].isin(["ZSPR", "ZSPN"])]
    records = [
        StockMasterRecord(
            material_code=str(row["material_code"]),
            plant=str(row["plant"]),
            current_stock=float(row["current_stock"]),
            unit_price=float(row["unit_price"]),
            category=str(row["category"]),
            material_type=row["material_type"],
            critical_flag=bool(row["critical_flag"]),
            shutdown_flag=bool(row["shutdown_flag"]),
            description=row.get("description"),
            uom=row.get("uom", "EA"),
            lead_time_days=float(row["lead_time_days"]) if pd.notna(row.get("lead_time_days")) else None,
        )
        for _, row in df.iterrows()
    ]
    return StockMaster(records=records)


def _load_consumption_fixture() -> ConsumptionHistory:
    df = pd.read_csv(_fixtures_path("test_consumption.csv"))
    records = [
        ConsumptionRecord(
            material_code=str(row["material_code"]),
            plant=str(row["plant"]),
            posting_date=row["posting_date"],
            qty=float(row["qty"]),
        )
        for _, row in df.iterrows()
    ]
    return ConsumptionHistory(records=records)


def _load_po_history_fixture() -> POHistory:
    df = pd.read_csv(_fixtures_path("test_po_history.csv"))
    records = [
        PORecord(
            material_code=str(row["material_code"]),
            plant=str(row["plant"]),
            po_number=str(row["po_number"]) if pd.notna(row.get("po_number")) else None,
            pr_date=row["pr_date"],
            approval_date=row["approval_date"] if pd.notna(row.get("approval_date")) else None,
            arrival_date=row["arrival_date"] if pd.notna(row.get("arrival_date")) else None,
            qty_ordered=float(row["qty_ordered"]),
            unit_price=float(row["unit_price"]),
        )
        for _, row in df.iterrows()
    ]
    return POHistory(records=records)


def get_stub_forecast(material_code: str, plant: str) -> ForecastResponse:
    """Returns a clearly-labelled stub forecast for test/dev use only."""
    return ForecastResponse(
        material_code=material_code,
        plant=plant,
        forecasts=[
            ForecastPeriod(horizon_months=3, forecast_qty=0.0, lower_bound=0.0, upper_bound=0.0),
            ForecastPeriod(horizon_months=6, forecast_qty=0.0, lower_bound=0.0, upper_bound=0.0),
            ForecastPeriod(horizon_months=12, forecast_qty=0.0, lower_bound=0.0, upper_bound=0.0),
        ],
        avg_daily_usage=0.0,
        max_daily_usage=0.0,
        avg_lead_time_days=0.0,
        max_lead_time_days=0.0,
    )
