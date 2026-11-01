"""
Forecast API routes — proxies to ContextFlow MCP.
Returns 'Data not available' gracefully when MCP is not configured.
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from app.models.schemas import ForecastResponse, MaterialType
from app.integrations.contextflow_client import request_forecast, ContextFlowUnavailableError
from app.services.fixture_loader import load_fixtures_if_enabled
from app.core.config import settings

router = APIRouter(tags=["forecast"])


@router.get("/forecast/{material_code}/{plant}", response_model=ForecastResponse)
async def get_forecast(
    material_code: str,
    plant: str,
    horizon_months: List[int] = Query(default=[3, 6, 12]),
):
    """
    Returns 3/6/12-month demand forecast from ContextFlow MCP.
    Returns 503 with blocker detail if MCP is not yet configured.
    """
    if settings.USE_TEST_FIXTURES:
        # Return stub forecast from fixtures
        from app.services.fixture_loader import get_stub_forecast
        return get_stub_forecast(material_code, plant)

    try:
        stock_master, consumption_history, _ = load_fixtures_if_enabled() if settings.USE_TEST_FIXTURES else _load_live()
        recs = [r for r in consumption_history.records
                if r.material_code == material_code and r.plant == plant]
        return await request_forecast(material_code, plant, recs, horizon_months=horizon_months)
    except ContextFlowUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _load_live():
    from app.services.gcs_loader import load_stock_master, load_consumption_history, load_po_history
    return load_stock_master(), load_consumption_history(), load_po_history()
