"""
Tests for ContextFlow MCP client — connected and disconnected paths.

Connected path: CONTEXTFLOW_MCP_ENDPOINT + CONTEXTFLOW_API_KEY set,
  HTTP call mocked with respx to return a valid forecast payload.

Disconnected path: env vars absent → ContextFlowUnavailableError raised
  before any HTTP call is made.

Run: cd vedanta-inventory/backend && pytest tests/test_contextflow_client.py -v
"""
from __future__ import annotations
import os
import sys
import json
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── env must be set BEFORE importing settings ──────────────────────────────
FAKE_ENDPOINT = "https://mcp.contextflow.test"
FAKE_API_KEY = "test-key-abc123"


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_consumption_records(n: int = 30):
    from datetime import date, timedelta
    from app.models.schemas import ConsumptionRecord
    today = date.today()
    return [
        ConsumptionRecord(
            material_code="MAT-001",
            plant="PL01",
            posting_date=today - timedelta(days=i),
            qty=2.0,
        )
        for i in range(n)
    ]


def _valid_cf_response(material_code: str = "MAT-001", plant: str = "PL01") -> dict:
    """Minimal valid ContextFlow MCP response payload."""
    return {
        "material_code": material_code,
        "plant": plant,
        "forecasts": [
            {"horizon_months": 3, "forecast_qty": 180.0, "lower_bound": 150.0, "upper_bound": 210.0},
            {"horizon_months": 6, "forecast_qty": 360.0, "lower_bound": 300.0, "upper_bound": 420.0},
            {"horizon_months": 12, "forecast_qty": 720.0, "lower_bound": 600.0, "upper_bound": 840.0},
        ],
        "avg_daily_usage": 2.0,
        "max_daily_usage": 5.0,
        "avg_lead_time_days": 30.0,
        "max_lead_time_days": 45.0,
    }


# ── disconnected path ────────────────────────────────────────────────────────

class TestContextFlowDisconnected:
    """ContextFlowUnavailableError is raised when env vars are absent."""

    def setup_method(self):
        # Ensure env vars are absent for this test class
        os.environ.pop("CONTEXTFLOW_MCP_ENDPOINT", None)
        os.environ.pop("CONTEXTFLOW_API_KEY", None)
        # Force settings reload
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)

    @pytest.mark.asyncio
    async def test_request_forecast_raises_when_no_endpoint(self):
        from app.integrations.contextflow_client import (
            request_forecast, ContextFlowUnavailableError,
        )
        recs = _make_consumption_records()
        with pytest.raises(ContextFlowUnavailableError) as exc_info:
            await request_forecast("MAT-001", "PL01", recs)
        assert "CONTEXTFLOW_MCP_ENDPOINT" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_forecast_raises_when_no_api_key(self, monkeypatch):
        monkeypatch.setenv("CONTEXTFLOW_MCP_ENDPOINT", FAKE_ENDPOINT)
        monkeypatch.delenv("CONTEXTFLOW_API_KEY", raising=False)
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)
        from app.integrations.contextflow_client import (
            request_forecast, ContextFlowUnavailableError,
        )
        recs = _make_consumption_records()
        with pytest.raises(ContextFlowUnavailableError) as exc_info:
            await request_forecast("MAT-001", "PL01", recs)
        assert "CONTEXTFLOW_API_KEY" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_message_names_missing_vars(self):
        from app.integrations.contextflow_client import (
            request_forecast, ContextFlowUnavailableError,
        )
        recs = _make_consumption_records()
        with pytest.raises(ContextFlowUnavailableError) as exc_info:
            await request_forecast("MAT-001", "PL01", recs)
        msg = str(exc_info.value)
        # Must name what is missing so the operator knows what to set
        assert "CONTEXTFLOW_MCP_ENDPOINT" in msg or "CONTEXTFLOW_API_KEY" in msg

    @pytest.mark.asyncio
    async def test_batch_forecast_raises_when_not_configured(self):
        from app.integrations.contextflow_client import (
            request_batch_forecasts, ContextFlowUnavailableError,
        )
        from app.models.schemas import ForecastRequest, ShutdownRecord
        req = ForecastRequest(
            material_code="MAT-001",
            plant="PL01",
            consumption_records=_make_consumption_records(),
            shutdown_records=[],
            horizon_months=[3, 6, 12],
        )
        with pytest.raises(ContextFlowUnavailableError):
            await request_batch_forecasts([req])


# ── connected path ───────────────────────────────────────────────────────────

class TestContextFlowConnected:
    """
    Connected path: env vars present, HTTP mocked with respx.
    Verifies payload shape, auth header, and response parsing.
    """

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("CONTEXTFLOW_MCP_ENDPOINT", FAKE_ENDPOINT)
        monkeypatch.setenv("CONTEXTFLOW_API_KEY", FAKE_API_KEY)
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)

    @pytest.mark.asyncio
    async def test_request_forecast_returns_forecast_response(self, respx_mock):
        """Happy path: valid MCP response → ForecastResponse with 3 horizons."""
        import respx
        import httpx
        from app.integrations.contextflow_client import request_forecast
        from app.models.schemas import ForecastResponse

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(
            return_value=httpx.Response(200, json=_valid_cf_response())
        )

        recs = _make_consumption_records()
        result = await request_forecast("MAT-001", "PL01", recs)

        assert isinstance(result, ForecastResponse)
        assert result.material_code == "MAT-001"
        assert result.plant == "PL01"
        assert len(result.forecasts) == 3
        horizons = {f.horizon_months for f in result.forecasts}
        assert horizons == {3, 6, 12}

    @pytest.mark.asyncio
    async def test_request_forecast_sends_bearer_auth(self, respx_mock):
        """Authorization header must carry the API key as Bearer token."""
        import httpx
        from app.integrations.contextflow_client import request_forecast

        captured = {}

        def capture(request):
            captured["auth"] = request.headers.get("Authorization", "")
            return httpx.Response(200, json=_valid_cf_response())

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(side_effect=capture)

        await request_forecast("MAT-001", "PL01", _make_consumption_records())
        assert captured["auth"] == f"Bearer {FAKE_API_KEY}"

    @pytest.mark.asyncio
    async def test_request_forecast_sends_correct_payload(self, respx_mock):
        """Payload must include material_code, plant, consumption array."""
        import httpx
        from app.integrations.contextflow_client import request_forecast

        captured = {}

        def capture(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_valid_cf_response())

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(side_effect=capture)

        recs = _make_consumption_records(5)
        await request_forecast("MAT-001", "PL01", recs, horizon_months=[3, 6, 12])

        body = captured["body"]
        assert body["material_code"] == "MAT-001"
        assert body["plant"] == "PL01"
        assert len(body["consumption"]) == 5
        assert body["horizon_months"] == [3, 6, 12]

    @pytest.mark.asyncio
    async def test_request_forecast_parses_forecast_quantities(self, respx_mock):
        """Forecast quantities from MCP response are correctly parsed."""
        import httpx
        from app.integrations.contextflow_client import request_forecast

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(
            return_value=httpx.Response(200, json=_valid_cf_response())
        )

        result = await request_forecast("MAT-001", "PL01", _make_consumption_records())
        f3 = next(f for f in result.forecasts if f.horizon_months == 3)
        f6 = next(f for f in result.forecasts if f.horizon_months == 6)
        f12 = next(f for f in result.forecasts if f.horizon_months == 12)

        assert f3.forecast_qty == pytest.approx(180.0)
        assert f6.forecast_qty == pytest.approx(360.0)
        assert f12.forecast_qty == pytest.approx(720.0)

    @pytest.mark.asyncio
    async def test_request_forecast_parses_lead_time(self, respx_mock):
        """avg_lead_time_days from MCP response is correctly parsed."""
        import httpx
        from app.integrations.contextflow_client import request_forecast

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(
            return_value=httpx.Response(200, json=_valid_cf_response())
        )

        result = await request_forecast("MAT-001", "PL01", _make_consumption_records())
        assert result.avg_lead_time_days == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_request_forecast_raises_on_http_error(self, respx_mock):
        """HTTP 4xx/5xx from MCP → ContextFlowUnavailableError (not a raw HTTPStatusError)."""
        import httpx
        from app.integrations.contextflow_client import (
            request_forecast, ContextFlowUnavailableError,
        )

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )

        with pytest.raises(ContextFlowUnavailableError) as exc_info:
            await request_forecast("MAT-001", "PL01", _make_consumption_records())
        assert "503" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_forecast_raises_on_network_error(self, respx_mock):
        """Network-level failure → ContextFlowUnavailableError."""
        import httpx
        from app.integrations.contextflow_client import (
            request_forecast, ContextFlowUnavailableError,
        )

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with pytest.raises(ContextFlowUnavailableError) as exc_info:
            await request_forecast("MAT-001", "PL01", _make_consumption_records())
        assert "unreachable" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_request_forecast_raises_on_timeout(self, respx_mock):
        """Timeout → ContextFlowUnavailableError."""
        import httpx
        from app.integrations.contextflow_client import (
            request_forecast, ContextFlowUnavailableError,
        )

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(
            side_effect=httpx.TimeoutException("timed out")
        )

        with pytest.raises(ContextFlowUnavailableError) as exc_info:
            await request_forecast("MAT-001", "PL01", _make_consumption_records())
        assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_batch_forecast_returns_list(self, respx_mock):
        """Batch endpoint returns a list of ForecastResponse objects."""
        import httpx
        from app.integrations.contextflow_client import request_batch_forecasts
        from app.models.schemas import ForecastRequest, ForecastResponse

        batch_response = {
            "results": [
                _valid_cf_response("MAT-001", "PL01"),
                _valid_cf_response("MAT-002", "PL01"),
            ]
        }
        respx_mock.post(f"{FAKE_ENDPOINT}/forecast/batch").mock(
            return_value=httpx.Response(200, json=batch_response)
        )

        reqs = [
            ForecastRequest(
                material_code=mc,
                plant="PL01",
                consumption_records=_make_consumption_records(10),
                shutdown_records=[],
                horizon_months=[3, 6, 12],
            )
            for mc in ["MAT-001", "MAT-002"]
        ]
        results = await request_batch_forecasts(reqs)
        assert len(results) == 2
        assert all(isinstance(r, ForecastResponse) for r in results)
        assert {r.material_code for r in results} == {"MAT-001", "MAT-002"}
