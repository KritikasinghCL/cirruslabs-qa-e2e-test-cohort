"""
Application settings — all credentials and paths from environment variables.
No hardcoded values. Missing env vars are surfaced as blockers at runtime.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # GCS
    GCS_BUCKET: Optional[str] = None
    GCS_CONSUMPTION_PATH: Optional[str] = None
    GCS_STOCK_MASTER_PATH: Optional[str] = None
    GCS_PO_HISTORY_PATH: Optional[str] = None
    GCS_SHUTDOWN_CALENDAR_PATH: Optional[str] = None
    # G-01: daily stock snapshot for Critical Spares Availability
    GCS_DAILY_STOCK_SNAPSHOT_PATH: Optional[str] = None
    # G-02: RESB demand-met extract for Fill Rate
    GCS_RESB_PATH: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # SAP RFC/BAPI
    SAP_HOST: Optional[str] = None
    SAP_SYSNR: Optional[str] = None
    SAP_CLIENT: Optional[str] = None
    SAP_USER: Optional[str] = None
    SAP_PASSWORD: Optional[str] = None
    SAP_LANGUAGE: str = "EN"

    # ContextFlow MCP
    CONTEXTFLOW_MCP_ENDPOINT: Optional[str] = None
    CONTEXTFLOW_API_KEY: Optional[str] = None
    CONTEXTFLOW_TIMEOUT_SECONDS: int = 60

    # App
    ENV: str = "development"
    USE_TEST_FIXTURES: bool = False   # True only in local dev / unit tests
    FIXTURES_DIR: str = "/app/fixtures"

    # SMI threshold (configurable)
    SMI_USAGE_THRESHOLD_PERCENTILE: float = 20.0  # bottom 20th percentile
    NMI_LOOKBACK_MONTHS: int = 6

    # Overstock margin multiplier
    OVERSTOCK_MARGIN_FACTOR: float = 1.25  # stock > 1.25 × (3mo forecast + safety stock)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
