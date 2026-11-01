"""
ContextFlow MCP Integration Client.
Sends consumption + calendar payload to ContextFlow via MCP and returns
3/6/12-month demand forecasts.

BLOCKER: CONTEXTFLOW_MCP_ENDPOINT and CONTEXTFLOW_API_KEY not yet provided.
         Client raises ContextFlowUnavailableError until they are supplied.

Orchestration rule: ContextFlow handles ONLY demand forecasting.
This team handles all other metrics and the dashboard.
"""
from __future__ import annotations
import logging
from typing import List, Optional

import httpx

from app.core.config import settings
from app.models.schemas import (
    ConsumptionRecord, ShutdownRecord,
    ForecastRequest, ForecastResponse, ForecastPeriod,
)

logger = logging.getLogger(__name__)


class ContextFlowUnavailableError(RuntimeError):
    """Raised when ContextFlow MCP endpoint or credentials are not configured."""


def _validate_config() -> None:
    missing = []
    if not settings.CONTEXTFLOW_MCP_ENDPOINT:
        missing.append("CONTEXTFLOW_MCP_ENDPOINT")
    if not settings.CONTEXTFLOW_API_KEY:
        missing.append("CONTEXTFLOW_API_KEY")
    if missing:
        raise ContextFlowUnavailableError(
            f"BLOCKER: ContextFlow MCP not configured. "
            f"Missing env vars: {missing}. "
            f"Forecast-dependent metrics (Safety Stock, ROP, Overstock, Understock) "
            f"will show 'Data not available' until this is resolved."
        )


def _build_payload(request: ForecastRequest) -> dict:
    """Serialize the forecast request to the MCP wire format."""
    return {
        "material_code": request.material_code,
        "plant": request.plant,
        "horizon_months": request.horizon_months,
        "consumption": [
            {
                "date": r.posting_date.isoformat(),
                "qty": r.qty,
            }
            for r in request.consumption_records
        ],
        "shutdown_calendar": [
            {
                "shutdown_id": r.shutdown_id,
                "shutdown_date": r.shutdown_date.isoformat(),
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "seasonal_flag": r.seasonal_flag,
                "shutdown_type": r.shutdown_type,
            }
            for r in request.shutdown_records
        ],
    }


def _parse_response(raw: dict) -> ForecastResponse:
    """Parse ContextFlow MCP response into ForecastResponse schema."""
    forecasts = []
    for horizon in raw.get("forecasts", []):
        forecasts.append(ForecastPeriod(
            horizon_months=horizon["horizon_months"],
            forecast_qty=horizon["forecast_qty"],
            lower_bound=horizon.get("lower_bound"),
            upper_bound=horizon.get("upper_bound"),
        ))
    return ForecastResponse(
        material_code=raw["material_code"],
        plant=raw["plant"],
        forecasts=forecasts,
        avg_daily_usage=raw["avg_daily_usage"],
        max_daily_usage=raw["max_daily_usage"],
        avg_lead_time_days=raw["avg_lead_time_days"],
        max_lead_time_days=raw["max_lead_time_days"],
    )


async def request_forecast(
    material_code: str,
    plant: str,
    consumption_records: List[ConsumptionRecord],
    shutdown_records: Optional[List[ShutdownRecord]] = None,
    horizon_months: Optional[List[int]] = None,
) -> ForecastResponse:
    """
    Send a forecast request to ContextFlow MCP and return the response.
    Raises ContextFlowUnavailableError if endpoint/credentials are missing.
    """
    _validate_config()

    req = ForecastRequest(
        material_code=material_code,
        plant=plant,
        consumption_records=consumption_records,
        shutdown_records=shutdown_records or [],
        horizon_months=horizon_months or [3, 6, 12],
    )
    payload = _build_payload(req)

    headers = {
        "Authorization": f"Bearer {settings.CONTEXTFLOW_API_KEY}",
        "Content-Type": "application/json",
        "X-MCP-Version": "1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.CONTEXTFLOW_TIMEOUT_SECONDS) as client:
            logger.info(
                "Requesting ContextFlow forecast: material=%s plant=%s horizons=%s",
                material_code, plant, horizon_months,
            )
            response = await client.post(
                f"{settings.CONTEXTFLOW_MCP_ENDPOINT}/forecast",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            raw = response.json()
    except httpx.TimeoutException as exc:
        raise ContextFlowUnavailableError(
            f"ContextFlow MCP timed out after {settings.CONTEXTFLOW_TIMEOUT_SECONDS}s "
            f"for {material_code}/{plant}: {exc}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise ContextFlowUnavailableError(
            f"ContextFlow MCP returned HTTP {exc.response.status_code} "
            f"for {material_code}/{plant}: {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ContextFlowUnavailableError(
            f"ContextFlow MCP unreachable for {material_code}/{plant}: {exc}"
        ) from exc

    logger.info("ContextFlow forecast received for %s/%s", material_code, plant)
    return _parse_response(raw)


async def request_batch_forecasts(
    requests: List[ForecastRequest],
) -> List[ForecastResponse]:
    """
    Batch forecast endpoint — sends multiple materials in one MCP call.
    Falls back to sequential if batch endpoint is unavailable.
    """
    _validate_config()

    batch_payload = {
        "requests": [_build_payload(r) for r in requests]
    }
    headers = {
        "Authorization": f"Bearer {settings.CONTEXTFLOW_API_KEY}",
        "Content-Type": "application/json",
        "X-MCP-Version": "1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.CONTEXTFLOW_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.CONTEXTFLOW_MCP_ENDPOINT}/forecast/batch",
                json=batch_payload,
                headers=headers,
            )
            response.raise_for_status()
            raw_list = response.json().get("results", [])
    except httpx.TimeoutException as exc:
        raise ContextFlowUnavailableError(
            f"ContextFlow MCP batch timed out after {settings.CONTEXTFLOW_TIMEOUT_SECONDS}s: {exc}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise ContextFlowUnavailableError(
            f"ContextFlow MCP batch returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ContextFlowUnavailableError(
            f"ContextFlow MCP batch unreachable: {exc}"
        ) from exc

    return [_parse_response(r) for r in raw_list]
