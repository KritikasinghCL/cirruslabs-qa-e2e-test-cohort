"""
/api/v1/connectivity — probes each external data source and reports its status.

This endpoint is the single place to check whether real credentials have been
supplied.  It never reads or returns any data — it only tests reachability and
configuration.  Safe to call at any time; all probes are read-only.

Response shape:
  {
    "overall": "ok" | "degraded" | "offline",
    "sources": {
      "gcs":          { "status": "ok"|"missing_config"|"unreachable", "detail": "..." },
      "sap":          { "status": "ok"|"missing_config"|"unreachable", "detail": "..." },
      "contextflow":  { "status": "ok"|"missing_config"|"unreachable", "detail": "..." }
    },
    "missing_env_vars": ["GCS_BUCKET", ...],
    "metrics_unblocked": ["DOH", "Inventory Value", ...],
    "metrics_blocked":   ["Safety Stock (G-05)", ...]
  }
"""
from __future__ import annotations
import logging
from typing import Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["connectivity"])

SourceStatus = Literal["ok", "missing_config", "unreachable", "error"]


# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------

def _probe_gcs() -> Dict:
    """
    Check GCS configuration and attempt a lightweight bucket metadata call.
    Does NOT download any data.
    """
    required = {
        "GCS_BUCKET": settings.GCS_BUCKET,
        "GCS_CONSUMPTION_PATH": settings.GCS_CONSUMPTION_PATH,
        "GCS_STOCK_MASTER_PATH": settings.GCS_STOCK_MASTER_PATH,
        "GCS_PO_HISTORY_PATH": settings.GCS_PO_HISTORY_PATH,
        "GOOGLE_APPLICATION_CREDENTIALS": settings.GOOGLE_APPLICATION_CREDENTIALS,
    }
    optional = {
        "GCS_SHUTDOWN_CALENDAR_PATH": settings.GCS_SHUTDOWN_CALENDAR_PATH,
        "GCS_DAILY_STOCK_SNAPSHOT_PATH": settings.GCS_DAILY_STOCK_SNAPSHOT_PATH,
        "GCS_RESB_PATH": settings.GCS_RESB_PATH,
    }
    missing_required = [k for k, v in required.items() if not v]
    missing_optional = [k for k, v in optional.items() if not v]

    if missing_required:
        return {
            "status": "missing_config",
            "detail": (
                f"Required env vars not set: {missing_required}. "
                "Set these to connect to GCS. "
                f"Optional (for Fill Rate / Critical Spares Availability): {missing_optional or 'none'}."
            ),
            "missing_required": missing_required,
            "missing_optional": missing_optional,
        }

    # Attempt a lightweight GCS connection test
    try:
        from google.cloud import storage  # type: ignore
        client = storage.Client()
        bucket = client.bucket(settings.GCS_BUCKET)
        # get_bucket raises if bucket doesn't exist or credentials are wrong
        bucket.reload()
        return {
            "status": "ok",
            "detail": f"Connected to gs://{settings.GCS_BUCKET}. "
                      f"Optional paths missing: {missing_optional or 'none'}.",
            "missing_optional": missing_optional,
        }
    except ImportError:
        return {
            "status": "error",
            "detail": "google-cloud-storage package not installed in this environment.",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unreachable",
            "detail": f"GCS credentials set but bucket unreachable: {type(exc).__name__}: {exc}",
        }


def _probe_sap() -> Dict:
    """
    Check SAP RFC credential configuration.
    Does NOT attempt an actual RFC call (pyrfc requires the SAP NW RFC SDK binary).
    """
    required = {
        "SAP_HOST": settings.SAP_HOST,
        "SAP_SYSNR": settings.SAP_SYSNR,
        "SAP_CLIENT": settings.SAP_CLIENT,
        "SAP_USER": settings.SAP_USER,
        "SAP_PASSWORD": settings.SAP_PASSWORD,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        return {
            "status": "missing_config",
            "detail": (
                f"SAP RFC credentials not set: {missing}. "
                "SAP is the upstream source for all four data tables. "
                "GCS is the primary ingestion path; SAP RFC is the secondary/fallback connector."
            ),
            "missing": missing,
        }

    # Credentials are present — attempt a lightweight TCP reachability check
    try:
        import socket
        host = settings.SAP_HOST
        # SAP message server port: 3600 + SYSNR; dispatcher: 3200 + SYSNR
        sysnr = int(settings.SAP_SYSNR or "00")
        port = 3200 + sysnr
        with socket.create_connection((host, port), timeout=5):
            pass
        return {
            "status": "ok",
            "detail": f"SAP host {host}:{port} is reachable. RFC credentials are set.",
        }
    except OSError as exc:
        return {
            "status": "unreachable",
            "detail": (
                f"SAP credentials set but host unreachable: {exc}. "
                "Check SAP_HOST, SAP_SYSNR, and network/firewall rules."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "detail": f"SAP probe error: {type(exc).__name__}: {exc}",
        }


async def _probe_contextflow() -> Dict:
    """
    Check ContextFlow MCP configuration and attempt a lightweight HEAD/GET probe.
    Does NOT send any material data.
    """
    required = {
        "CONTEXTFLOW_MCP_ENDPOINT": settings.CONTEXTFLOW_MCP_ENDPOINT,
        "CONTEXTFLOW_API_KEY": settings.CONTEXTFLOW_API_KEY,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        return {
            "status": "missing_config",
            "detail": (
                f"ContextFlow MCP credentials not set: {missing}. "
                "Blocked metrics: Safety Stock, ROP, Overstock (forecast-enhanced), "
                "Understock, Demand Forecast 3/6/12mo, Forecast Accuracy, Forecast Bias."
            ),
            "missing": missing,
        }

    # Attempt a lightweight health/ping call
    try:
        headers = {
            "Authorization": f"Bearer {settings.CONTEXTFLOW_API_KEY}",
            "X-MCP-Version": "1.0",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            # Try /health first; fall back to a HEAD on the base endpoint
            for path in ["/health", "/ping", "/"]:
                try:
                    resp = await client.get(
                        f"{settings.CONTEXTFLOW_MCP_ENDPOINT}{path}",
                        headers=headers,
                    )
                    if resp.status_code < 500:
                        return {
                            "status": "ok",
                            "detail": (
                                f"ContextFlow MCP reachable at "
                                f"{settings.CONTEXTFLOW_MCP_ENDPOINT}{path} "
                                f"(HTTP {resp.status_code})."
                            ),
                        }
                except httpx.RequestError:
                    continue
        return {
            "status": "unreachable",
            "detail": (
                f"ContextFlow MCP endpoint set but unreachable at "
                f"{settings.CONTEXTFLOW_MCP_ENDPOINT}. "
                "Check CONTEXTFLOW_MCP_ENDPOINT and network access."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "detail": f"ContextFlow probe error: {type(exc).__name__}: {exc}",
        }


# ---------------------------------------------------------------------------
# Metric unblock map — which metrics become available when each source is live
# ---------------------------------------------------------------------------

_METRICS_BY_SOURCE = {
    "gcs": [
        "M01 Days of Inventory",
        "M02 Inventory Value",
        "M03 Inventory Turnover",
        "M08 Non-Moving Stock (NMI)",
        "M09 Slow-Moving Stock (SMI)",
    ],
    "gcs_optional_g01": [
        "M11 Critical Spares Availability % (requires GCS_DAILY_STOCK_SNAPSHOT_PATH)",
    ],
    "gcs_optional_g02": [
        "M10 Fill Rate % (requires GCS_RESB_PATH)",
    ],
    "contextflow": [
        "M04 Safety Stock",
        "M05 Reorder Point (ROP)",
        "M06 Overstock Flag (forecast-enhanced)",
        "M07 Understock Flag",
        "M12 Demand Forecast 3/6/12mo",
        "M13 Forecast Accuracy (MAPE) — requires post-actuals after first ContextFlow cycle",
        "M14 Forecast Bias — requires post-actuals after first ContextFlow cycle",
    ],
}


def _classify_metrics(gcs_status: str, cf_status: str, gcs_result: Dict) -> tuple:
    unblocked = []
    blocked = []

    if gcs_status == "ok":
        unblocked.extend(_METRICS_BY_SOURCE["gcs"])
        missing_opt = gcs_result.get("missing_optional", [])
        if "GCS_DAILY_STOCK_SNAPSHOT_PATH" not in missing_opt:
            unblocked.extend(_METRICS_BY_SOURCE["gcs_optional_g01"])
        else:
            blocked.extend(_METRICS_BY_SOURCE["gcs_optional_g01"])
        if "GCS_RESB_PATH" not in missing_opt:
            unblocked.extend(_METRICS_BY_SOURCE["gcs_optional_g02"])
        else:
            blocked.extend(_METRICS_BY_SOURCE["gcs_optional_g02"])
    else:
        blocked.extend(_METRICS_BY_SOURCE["gcs"])
        blocked.extend(_METRICS_BY_SOURCE["gcs_optional_g01"])
        blocked.extend(_METRICS_BY_SOURCE["gcs_optional_g02"])

    if cf_status == "ok":
        unblocked.extend(_METRICS_BY_SOURCE["contextflow"])
    else:
        blocked.extend(_METRICS_BY_SOURCE["contextflow"])

    return unblocked, blocked


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/connectivity")
async def connectivity_check():
    """
    Probe all external data sources and report which metrics are unblocked.
    Read-only — no data is fetched or returned.
    """
    gcs_result = _probe_gcs()
    sap_result = _probe_sap()
    cf_result = await _probe_contextflow()

    gcs_status: SourceStatus = gcs_result["status"]
    sap_status: SourceStatus = sap_result["status"]
    cf_status: SourceStatus = cf_result["status"]

    # Collect all missing env vars across sources
    missing_env_vars: List[str] = []
    for result in [gcs_result, sap_result, cf_result]:
        missing_env_vars.extend(result.get("missing_required", result.get("missing", [])))
    # Add optional GCS paths that are missing
    missing_env_vars.extend(gcs_result.get("missing_optional", []))

    unblocked, blocked = _classify_metrics(gcs_status, cf_status, gcs_result)

    # Overall status: ok if all three are ok; degraded if at least one is ok; offline otherwise
    statuses = {gcs_status, sap_status, cf_status}
    if statuses == {"ok"}:
        overall = "ok"
    elif "ok" in statuses:
        overall = "degraded"
    else:
        overall = "offline"

    return {
        "overall": overall,
        "sources": {
            "gcs": gcs_result,
            "sap": sap_result,
            "contextflow": cf_result,
        },
        "missing_env_vars": sorted(set(missing_env_vars)),
        "metrics_unblocked": unblocked,
        "metrics_blocked": blocked,
        "note": (
            "Set the env vars listed in missing_env_vars and restart the app. "
            "Each source connects automatically — no code changes required. "
            "See BLOCKERS.md for the full resolution guide."
        ),
    }
