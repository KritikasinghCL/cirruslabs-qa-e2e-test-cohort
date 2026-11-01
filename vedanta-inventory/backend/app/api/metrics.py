from fastapi import APIRouter
router = APIRouter(tags=["metrics"])

@router.get("/metrics/gaps")
def get_data_gaps():
    """Returns the current gap register — items that cannot be computed from available data."""
    return {
        "gaps": [
            {"id": "GCS_BUCKET", "description": "GCS bucket and service account not provided", "affects": ["all data ingestion"], "status": "BLOCKED"},
            {"id": "SAP_RFC", "description": "SAP RFC/BAPI credentials not provided", "affects": ["consumption_history", "stock_master", "po_history"], "status": "BLOCKED"},
            {"id": "CONTEXTFLOW_MCP", "description": "ContextFlow MCP endpoint and API key not provided", "affects": ["safety_stock", "rop", "overstock_flag", "understock_flag", "forecast_3mo", "forecast_6mo", "forecast_12mo"], "status": "BLOCKED"},
            {"id": "DAILY_STOCK_SNAPSHOT", "description": "Daily stock snapshot not in scope of current SAP extraction", "affects": ["critical_spares_availability_pct"], "status": "BLOCKED"},
            {"id": "DEMAND_MET_DATA", "description": "Order-level demand-met data not yet extracted", "affects": ["fill_rate_pct"], "status": "BLOCKED"},
            {"id": "POST_ACTUALS", "description": "Forecast actuals not yet available (post-go-live)", "affects": ["forecast_accuracy_pct", "forecast_bias_pct"], "status": "PENDING"},
        ]
    }
