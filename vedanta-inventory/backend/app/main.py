"""
Vedanta Inventory Forecasting & Dashboard — Backend
Entry point: uvicorn app.main:app
"""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api import health, inventory, forecast, metrics, export, connectivity
from app.core.config import settings

logger = logging.getLogger(__name__)


def _log_startup_credential_status() -> None:
    """
    Log a clear, structured report of which credentials are set and which are
    missing.  This runs at startup so operators see the blocker list immediately
    in the container logs — no need to hit an endpoint first.
    """
    checks = {
        # GCS — required for all real-data metrics
        "GCS_BUCKET": settings.GCS_BUCKET,
        "GCS_CONSUMPTION_PATH": settings.GCS_CONSUMPTION_PATH,
        "GCS_STOCK_MASTER_PATH": settings.GCS_STOCK_MASTER_PATH,
        "GCS_PO_HISTORY_PATH": settings.GCS_PO_HISTORY_PATH,
        "GOOGLE_APPLICATION_CREDENTIALS": settings.GOOGLE_APPLICATION_CREDENTIALS,
        # GCS optional — for Fill Rate and Critical Spares Availability
        "GCS_DAILY_STOCK_SNAPSHOT_PATH": settings.GCS_DAILY_STOCK_SNAPSHOT_PATH,
        "GCS_RESB_PATH": settings.GCS_RESB_PATH,
        "GCS_SHUTDOWN_CALENDAR_PATH": settings.GCS_SHUTDOWN_CALENDAR_PATH,
        # SAP RFC — secondary/fallback connector
        "SAP_HOST": settings.SAP_HOST,
        "SAP_SYSNR": settings.SAP_SYSNR,
        "SAP_CLIENT": settings.SAP_CLIENT,
        "SAP_USER": settings.SAP_USER,
        "SAP_PASSWORD": settings.SAP_PASSWORD,
        # ContextFlow MCP — demand forecasting
        "CONTEXTFLOW_MCP_ENDPOINT": settings.CONTEXTFLOW_MCP_ENDPOINT,
        "CONTEXTFLOW_API_KEY": settings.CONTEXTFLOW_API_KEY,
    }

    set_vars = [k for k, v in checks.items() if v]
    missing_vars = [k for k, v in checks.items() if not v]

    if missing_vars:
        logger.warning(
            "STARTUP CREDENTIAL CHECK — %d/%d env vars set, %d missing.\n"
            "  SET    : %s\n"
            "  MISSING: %s\n"
            "  ACTION : Set missing vars and restart. "
            "See BLOCKERS.md for the full resolution guide. "
            "Hit GET /api/v1/connectivity for a live per-source status check.\n"
            "  NOTE   : USE_TEST_FIXTURES=%s — "
            "%s",
            len(set_vars),
            len(checks),
            len(missing_vars),
            set_vars or "none",
            missing_vars,
            settings.USE_TEST_FIXTURES,
            "running on fixture CSVs (local dev mode)" if settings.USE_TEST_FIXTURES
            else "LIVE MODE — missing credentials above will cause 503 errors on data endpoints",
        )
    else:
        logger.info(
            "STARTUP CREDENTIAL CHECK — all %d env vars set. "
            "Hit GET /api/v1/connectivity to verify reachability.",
            len(checks),
        )


app = FastAPI(
    title="Vedanta Inventory Forecasting API",
    description="Inventory forecasting and analytics for ZSPR/ZSPN materials",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(inventory.router, prefix="/api/v1")
app.include_router(forecast.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(connectivity.router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    _log_startup_credential_status()


# ── Serve React SPA from /static (built by Dockerfile stage 1) ───────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Catch-all: serve index.html for all non-API routes (SPA routing).
        API routes (/api/...) are registered before this handler and take priority,
        but as a safety net we return 404 for any path that starts with 'api/'.
        """
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"API route not found: /{full_path}")
        index = os.path.join(_STATIC_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return {"detail": "Frontend not built. Run: cd frontend && npm run build"}


# ── Serve React SPA from /static (built by Dockerfile stage 1) ───────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Catch-all: serve index.html for all non-API routes (SPA routing).
        API routes (/api/...) are registered before this handler and take priority,
        but as a safety net we return 404 for any path that starts with 'api/'.
        """
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"API route not found: /{full_path}")
        index = os.path.join(_STATIC_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return {"detail": "Frontend not built. Run: cd frontend && npm run build"}
