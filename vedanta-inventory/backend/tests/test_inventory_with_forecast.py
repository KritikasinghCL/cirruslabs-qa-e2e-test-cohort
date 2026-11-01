"""
Tests for the /inventory/metrics/with-forecast and /inventory/summary/with-forecast
endpoints — verifying the ContextFlow orchestration layer.

Connected path: ContextFlow env vars set + HTTP mocked → forecast fields populated.
Disconnected path: env vars absent → single G-05 gap entry, all forecast fields null,
  no fabricated data.

Run: cd vedanta-inventory/backend && pytest tests/test_inventory_with_forecast.py -v
"""
from __future__ import annotations
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("USE_TEST_FIXTURES", "true")
os.environ.setdefault("FIXTURES_DIR", "../../fixtures")

FAKE_ENDPOINT = "https://mcp.contextflow.test"
FAKE_API_KEY = "test-key-abc123"


def _valid_cf_response(material_code: str, plant: str) -> dict:
    return {
        "material_code": material_code,
        "plant": plant,
        "forecasts": [
            {"horizon_months": 3, "forecast_qty": 60.0, "lower_bound": 50.0, "upper_bound": 70.0},
            {"horizon_months": 6, "forecast_qty": 120.0, "lower_bound": 100.0, "upper_bound": 140.0},
            {"horizon_months": 12, "forecast_qty": 240.0, "lower_bound": 200.0, "upper_bound": 280.0},
        ],
        "avg_daily_usage": 2.0,
        "max_daily_usage": 5.0,
        "avg_lead_time_days": 30.0,
        "max_lead_time_days": 45.0,
    }


# ── Disconnected path ─────────────────────────────────────────────────────────

class TestWithForecastDisconnected:
    """When ContextFlow is not configured, forecast fields are null and a single
    G-05 gap entry is present. No fabricated data."""

    @pytest.fixture(autouse=True)
    def _clear_cf_env(self, monkeypatch):
        monkeypatch.delenv("CONTEXTFLOW_MCP_ENDPOINT", raising=False)
        monkeypatch.delenv("CONTEXTFLOW_API_KEY", raising=False)
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)
        import app.api.inventory as inv_mod
        importlib.reload(inv_mod)

    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_with_forecast_returns_200(self):
        resp = self._client().get("/api/v1/inventory/metrics/with-forecast")
        assert resp.status_code == 200

    def test_with_forecast_forecast_fields_are_null(self):
        resp = self._client().get("/api/v1/inventory/metrics/with-forecast")
        data = resp.json()
        assert len(data) > 0
        for m in data:
            assert m["forecast_3mo"] is None, f"{m['material_code']}: forecast_3mo should be null"
            assert m["forecast_6mo"] is None
            assert m["forecast_12mo"] is None
            assert m["safety_stock"] is None
            assert m["reorder_point"] is None
            assert m["understock_flag"] is None

    def test_with_forecast_single_gap_entry_per_material(self):
        """Each material must have exactly one G-05 gap entry — not duplicated."""
        resp = self._client().get("/api/v1/inventory/metrics/with-forecast")
        data = resp.json()
        for m in data:
            g05_entries = [g for g in m["data_gaps"] if "G-05" in g or "CONTEXTFLOW_MCP_ENDPOINT" in g]
            assert len(g05_entries) == 1, (
                f"{m['material_code']}: expected 1 G-05 gap entry, got {len(g05_entries)}: {g05_entries}"
            )

    def test_with_forecast_no_fabricated_data(self):
        """No forecast field should contain a non-null value when MCP is absent."""
        resp = self._client().get("/api/v1/inventory/metrics/with-forecast")
        data = resp.json()
        forecast_fields = ["forecast_3mo", "forecast_6mo", "forecast_12mo",
                           "safety_stock", "reorder_point", "understock_flag"]
        for m in data:
            for field in forecast_fields:
                assert m[field] is None, (
                    f"{m['material_code']}.{field} = {m[field]} — should be null when MCP not configured"
                )

    def test_summary_with_forecast_returns_200(self):
        resp = self._client().get("/api/v1/inventory/summary/with-forecast")
        assert resp.status_code == 200

    def test_summary_with_forecast_has_expected_keys(self):
        resp = self._client().get("/api/v1/inventory/summary/with-forecast")
        body = resp.json()
        for key in ["total_materials", "nmi_count", "smi_count", "overstock_count",
                    "understock_count", "data_gaps"]:
            assert key in body, f"Missing key: {key}"

    def test_summary_with_forecast_understock_zero_when_rop_unavailable(self):
        """Understock count must be 0 when ROP cannot be computed (no ContextFlow)."""
        resp = self._client().get("/api/v1/inventory/summary/with-forecast")
        body = resp.json()
        assert body["understock_count"] == 0


# ── Connected path ────────────────────────────────────────────────────────────

class TestWithForecastConnected:
    """When ContextFlow is configured and HTTP is mocked, forecast fields are populated."""

    @pytest.fixture(autouse=True)
    def _set_cf_env(self, monkeypatch):
        monkeypatch.setenv("CONTEXTFLOW_MCP_ENDPOINT", FAKE_ENDPOINT)
        monkeypatch.setenv("CONTEXTFLOW_API_KEY", FAKE_API_KEY)
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)
        import app.api.inventory as inv_mod
        importlib.reload(inv_mod)

    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_with_forecast_populates_forecast_fields(self, respx_mock):
        """When MCP returns valid data, forecast_3mo/6mo/12mo are populated."""
        import httpx
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)

        # Mock all POST calls to the forecast endpoint
        def _mock_response(request):
            body = json.loads(request.content)
            mat = body["material_code"]
            plant = body["plant"]
            return httpx.Response(200, json=_valid_cf_response(mat, plant))

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(side_effect=_mock_response)

        from app.api.inventory import _compute_metrics_with_forecast
        results = await _compute_metrics_with_forecast()

        assert len(results) > 0
        # At least one material should have forecast data
        with_forecast = [m for m in results if m.forecast_3mo is not None]
        assert len(with_forecast) > 0, "Expected at least one material with forecast_3mo populated"

    @pytest.mark.asyncio
    async def test_with_forecast_safety_stock_computed(self, respx_mock):
        """Safety Stock is computed from σ × √LT when ContextFlow provides lead time."""
        import httpx
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)

        def _mock_response(request):
            body = json.loads(request.content)
            return httpx.Response(200, json=_valid_cf_response(body["material_code"], body["plant"]))

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(side_effect=_mock_response)

        from app.api.inventory import _compute_metrics_with_forecast
        results = await _compute_metrics_with_forecast()

        # Materials with consumption history should have safety_stock computed
        with_ss = [m for m in results if m.safety_stock is not None]
        assert len(with_ss) > 0, "Expected at least one material with safety_stock computed"
        for m in with_ss:
            assert m.safety_stock >= 0.0

    @pytest.mark.asyncio
    async def test_with_forecast_rop_computed(self, respx_mock):
        """ROP is computed when avg_daily_usage, lead_time, and safety_stock are available."""
        import httpx
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)

        def _mock_response(request):
            body = json.loads(request.content)
            return httpx.Response(200, json=_valid_cf_response(body["material_code"], body["plant"]))

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(side_effect=_mock_response)

        from app.api.inventory import _compute_metrics_with_forecast
        results = await _compute_metrics_with_forecast()

        with_rop = [m for m in results if m.reorder_point is not None]
        assert len(with_rop) > 0, "Expected at least one material with reorder_point computed"

    @pytest.mark.asyncio
    async def test_with_forecast_no_g05_gap_when_connected(self, respx_mock):
        """When ContextFlow is connected and responds, no G-05 gap entry should appear."""
        import httpx
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)

        def _mock_response(request):
            body = json.loads(request.content)
            return httpx.Response(200, json=_valid_cf_response(body["material_code"], body["plant"]))

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(side_effect=_mock_response)

        from app.api.inventory import _compute_metrics_with_forecast
        results = await _compute_metrics_with_forecast()

        for m in results:
            g05_entries = [g for g in m.data_gaps if "G-05" in g]
            assert len(g05_entries) == 0, (
                f"{m.material_code}: unexpected G-05 gap when ContextFlow is connected: {g05_entries}"
            )

    @pytest.mark.asyncio
    async def test_with_forecast_overstock_uses_forecast_formula(self, respx_mock):
        """When forecast is available, overstock uses (3mo_forecast + SS) × 1.25 formula."""
        import httpx
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)

        def _mock_response(request):
            body = json.loads(request.content)
            return httpx.Response(200, json=_valid_cf_response(body["material_code"], body["plant"]))

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(side_effect=_mock_response)

        from app.api.inventory import _compute_metrics_with_forecast
        results = await _compute_metrics_with_forecast()

        # Materials with forecast_3mo and safety_stock should have overstock_flag set (not None)
        with_forecast_and_ss = [
            m for m in results
            if m.forecast_3mo is not None and m.safety_stock is not None
        ]
        assert len(with_forecast_and_ss) > 0
        for m in with_forecast_and_ss:
            assert m.overstock_flag is not None, (
                f"{m.material_code}: overstock_flag should be set when forecast+SS available"
            )

    @pytest.mark.asyncio
    async def test_with_forecast_understock_set_when_rop_available(self, respx_mock):
        """Understock flag is set (True or False) when ROP is available."""
        import httpx
        import importlib
        import app.core.config as cfg_mod
        importlib.reload(cfg_mod)
        import app.integrations.contextflow_client as cf_mod
        importlib.reload(cf_mod)

        def _mock_response(request):
            body = json.loads(request.content)
            return httpx.Response(200, json=_valid_cf_response(body["material_code"], body["plant"]))

        respx_mock.post(f"{FAKE_ENDPOINT}/forecast").mock(side_effect=_mock_response)

        from app.api.inventory import _compute_metrics_with_forecast
        results = await _compute_metrics_with_forecast()

        with_rop = [m for m in results if m.reorder_point is not None]
        for m in with_rop:
            assert m.understock_flag is not None, (
                f"{m.material_code}: understock_flag should be set when ROP is available"
            )
            assert isinstance(m.understock_flag, bool)
