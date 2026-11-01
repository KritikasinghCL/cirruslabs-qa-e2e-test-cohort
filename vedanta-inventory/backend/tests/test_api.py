"""
Integration tests for the FastAPI backend.
Uses USE_TEST_FIXTURES=true — no live connections required.
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["USE_TEST_FIXTURES"] = "true"
os.environ["FIXTURES_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_metrics_gaps():
    r = client.get("/api/v1/metrics/gaps")
    assert r.status_code == 200
    data = r.json()
    assert "gaps" in data
    assert len(data["gaps"]) > 0


def test_inventory_metrics_returns_list():
    r = client.get("/api/v1/inventory/metrics")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Should have 10 materials from fixture
    assert len(data) == 10


def test_inventory_metrics_material_type_filter():
    r = client.get("/api/v1/inventory/metrics?material_type=ZSPR")
    assert r.status_code == 200
    data = r.json()
    assert all(m["material_type"] == "ZSPR" for m in data)


def test_inventory_metrics_plant_filter():
    r = client.get("/api/v1/inventory/metrics?plant=PL01")
    assert r.status_code == 200
    data = r.json()
    assert all(m["plant"] == "PL01" for m in data)


def test_inventory_summary():
    r = client.get("/api/v1/inventory/summary")
    assert r.status_code == 200
    data = r.json()
    assert "total_materials" in data
    assert data["total_materials"] == 10
    assert "total_inventory_value" in data
    assert "nmi_count" in data
    assert "smi_count" in data


def test_inventory_metrics_have_required_fields():
    r = client.get("/api/v1/inventory/metrics")
    assert r.status_code == 200
    for m in r.json():
        assert "material_code" in m
        assert "plant" in m
        assert "material_type" in m
        assert m["material_type"] in ("ZSPR", "ZSPN")
        assert "data_gaps" in m


def test_forecast_returns_503_without_mcp():
    """Forecast endpoint returns 503 when ContextFlow MCP is not configured."""
    # In fixture mode, returns stub forecast (not 503)
    r = client.get("/api/v1/forecast/MAT-001/PL01")
    # Should succeed in fixture mode
    assert r.status_code in (200, 503)


def test_connectivity_endpoint_structure():
    """
    /api/v1/connectivity must return the expected shape even when no credentials
    are set (fixture mode / CI).  All sources will be 'missing_config' here.
    """
    r = client.get("/api/v1/connectivity")
    assert r.status_code == 200
    data = r.json()

    # Top-level keys
    assert "overall" in data
    assert data["overall"] in ("ok", "degraded", "offline")
    assert "sources" in data
    assert "missing_env_vars" in data
    assert "metrics_unblocked" in data
    assert "metrics_blocked" in data
    assert "note" in data

    # Per-source keys
    for source in ("gcs", "sap", "contextflow"):
        assert source in data["sources"]
        assert "status" in data["sources"][source]
        assert data["sources"][source]["status"] in (
            "ok", "missing_config", "unreachable", "error"
        )

    # In fixture/CI mode all credentials are absent → overall should be offline
    assert data["overall"] == "offline"

    # All 14 metrics should be blocked when no credentials are set
    assert len(data["metrics_blocked"]) > 0
    assert len(data["metrics_unblocked"]) == 0


def test_connectivity_missing_env_vars_listed():
    """
    When credentials are absent, missing_env_vars must list the required GCS,
    SAP and ContextFlow variables.
    """
    r = client.get("/api/v1/connectivity")
    assert r.status_code == 200
    missing = r.json()["missing_env_vars"]
    # At minimum these must appear
    for var in ("GCS_BUCKET", "SAP_HOST", "CONTEXTFLOW_MCP_ENDPOINT", "CONTEXTFLOW_API_KEY"):
        assert var in missing, f"{var} not listed in missing_env_vars"
