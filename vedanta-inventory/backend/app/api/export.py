"""
Export API — CSV, Excel, and PDF report generation.
"""
from __future__ import annotations
import io
from typing import List, Optional
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
import pandas as pd
from app.api.inventory import get_inventory_metrics
from app.models.schemas import MaterialType

router = APIRouter(tags=["export"])


def _metrics_to_df(metrics) -> pd.DataFrame:
    return pd.DataFrame([m.model_dump() for m in metrics])


@router.get("/export/csv")
def export_csv(
    plant: Optional[str] = Query(None),
    material_type: Optional[MaterialType] = Query(None),
    page: str = Query("inventory_health"),
):
    metrics = get_inventory_metrics(plant=plant, material_type=material_type)
    df = _metrics_to_df(metrics)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=vedanta_{page}.csv"},
    )


@router.get("/export/excel")
def export_excel(
    plant: Optional[str] = Query(None),
    material_type: Optional[MaterialType] = Query(None),
    page: str = Query("inventory_health"),
):
    metrics = get_inventory_metrics(plant=plant, material_type=material_type)
    df = _metrics_to_df(metrics)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Vedanta Inventory")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=vedanta_{page}.xlsx"},
    )
