"""
Typed Pydantic schemas for all four SAP data sources.
These are the canonical contracts — all loaders and API responses use these.
Material scope: ZSPR and ZSPN only.
"""
from datetime import date
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Allowed material types (hard scope from SOW)
# ---------------------------------------------------------------------------
MaterialType = Literal["ZSPR", "ZSPN"]


# ---------------------------------------------------------------------------
# (a) Consumption History
# ---------------------------------------------------------------------------
class ConsumptionRecord(BaseModel):
    material_code: str = Field(..., description="SAP material number")
    plant: str = Field(..., description="SAP plant code")
    posting_date: date = Field(..., description="Posting date of consumption")
    qty: float = Field(..., ge=0, description="Quantity consumed (in base UoM)")

    @field_validator("material_code", "plant")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class ConsumptionHistory(BaseModel):
    records: List[ConsumptionRecord]


# ---------------------------------------------------------------------------
# (b) Stock / Material Master
# ---------------------------------------------------------------------------
class StockMasterRecord(BaseModel):
    material_code: str = Field(..., description="SAP material number")
    plant: str = Field(..., description="SAP plant code")
    current_stock: float = Field(..., ge=0, description="Current unrestricted stock (base UoM)")
    unit_price: float = Field(..., ge=0, description="Moving average price / standard price (INR)")
    category: str = Field(..., description="Material category / group (manually defined)")
    material_type: MaterialType = Field(..., description="ZSPR = spare, ZSPN = non-stock spare")
    critical_flag: bool = Field(..., description="True if classified as critical/insurance spare")
    shutdown_flag: bool = Field(..., description="True if material is linked to shutdown/maintenance")
    description: Optional[str] = None
    uom: str = Field(default="EA", description="Base unit of measure")
    lead_time_days: Optional[float] = Field(None, ge=0, description="Procurement lead time in days")

    @field_validator("material_code", "plant")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class StockMaster(BaseModel):
    records: List[StockMasterRecord]


# ---------------------------------------------------------------------------
# (c) PO / PR History
# ---------------------------------------------------------------------------
class PORecord(BaseModel):
    material_code: str
    plant: str
    po_number: Optional[str] = None
    pr_date: date = Field(..., description="Purchase Requisition creation date")
    approval_date: Optional[date] = Field(None, description="PO approval / release date")
    arrival_date: Optional[date] = Field(None, description="Goods receipt date")
    qty_ordered: float = Field(..., ge=0)
    unit_price: float = Field(..., ge=0)

    @property
    def lead_time_days(self) -> Optional[float]:
        """Actual lead time = arrival - pr_date (if both present)."""
        if self.arrival_date and self.pr_date:
            return (self.arrival_date - self.pr_date).days
        return None


class POHistory(BaseModel):
    records: List[PORecord]


# ---------------------------------------------------------------------------
# (d) Shutdown / Maintenance Calendar
# ---------------------------------------------------------------------------
class ShutdownRecord(BaseModel):
    shutdown_id: str = Field(..., description="Unique shutdown event ID")
    plant: str
    shutdown_date: date = Field(..., description="Planned shutdown start date")
    end_date: Optional[date] = None
    materials: List[str] = Field(default_factory=list, description="Material codes required")
    seasonal_flag: bool = Field(default=False, description="True if shutdown is seasonal")
    shutdown_type: Optional[str] = Field(None, description="e.g. planned, emergency, turnaround")


class ShutdownCalendar(BaseModel):
    records: List[ShutdownRecord]


# ---------------------------------------------------------------------------
# ContextFlow forecast payload / response contracts
# ---------------------------------------------------------------------------
class ForecastRequest(BaseModel):
    material_code: str
    plant: str
    consumption_records: List[ConsumptionRecord]
    shutdown_records: List[ShutdownRecord]
    horizon_months: List[Literal[3, 6, 12]]


class ForecastPeriod(BaseModel):
    horizon_months: int
    forecast_qty: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None


class ForecastResponse(BaseModel):
    material_code: str
    plant: str
    forecasts: List[ForecastPeriod]
    avg_daily_usage: float
    max_daily_usage: float
    avg_lead_time_days: float
    max_lead_time_days: float


# ---------------------------------------------------------------------------
# Computed metrics output
# ---------------------------------------------------------------------------
class MaterialMetrics(BaseModel):
    material_code: str
    plant: str
    material_type: MaterialType
    category: str
    critical_flag: bool
    shutdown_flag: bool

    # Real-data metrics
    days_of_inventory: Optional[float] = None
    inventory_value: Optional[float] = None
    inventory_turnover: Optional[float] = None
    non_moving_flag: Optional[bool] = None
    slow_moving_flag: Optional[bool] = None
    fill_rate_pct: Optional[float] = None
    critical_spares_availability_pct: Optional[float] = None
    last_movement_date: Optional[date] = None
    value_at_risk: Optional[float] = None

    # Forecast-dependent metrics (populated after ContextFlow response)
    safety_stock: Optional[float] = None
    reorder_point: Optional[float] = None
    overstock_flag: Optional[bool] = None
    understock_flag: Optional[bool] = None
    forecast_3mo: Optional[float] = None
    forecast_6mo: Optional[float] = None
    forecast_12mo: Optional[float] = None
    recommended_action: Optional[str] = None

    # Post-actuals only
    forecast_accuracy_pct: Optional[float] = None
    forecast_bias_pct: Optional[float] = None

    # Gap tracking
    data_gaps: List[str] = Field(default_factory=list, description="List of missing data items")
