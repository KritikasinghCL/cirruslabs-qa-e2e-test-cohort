"""
SAP RFC/BAPI Connector Stub.
Credentials read exclusively from environment variables.
pyrfc is the standard SAP RFC library for Python — it requires the SAP NW RFC SDK
to be installed on the host, which is an infrastructure concern outside this codebase.

BLOCKER: SAP_HOST, SAP_SYSNR, SAP_CLIENT, SAP_USER, SAP_PASSWORD not yet provided.
         This stub will raise DataSourceUnavailableError until they are supplied.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

from app.core.config import settings

logger = logging.getLogger(__name__)


class SAPConnectionError(RuntimeError):
    """Raised when SAP credentials are missing or connection fails."""


def _get_connection_params() -> Dict[str, str]:
    required = {
        "ashost": settings.SAP_HOST,
        "sysnr": settings.SAP_SYSNR,
        "client": settings.SAP_CLIENT,
        "user": settings.SAP_USER,
        "passwd": settings.SAP_PASSWORD,
        "lang": settings.SAP_LANGUAGE,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise SAPConnectionError(
            f"BLOCKER: SAP RFC credentials not configured. "
            f"Missing env vars: {[k.upper() for k in missing]}. "
            f"Set SAP_HOST, SAP_SYSNR, SAP_CLIENT, SAP_USER, SAP_PASSWORD."
        )
    return required


def call_bapi(function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call a SAP BAPI/RFC function module.
    Returns the result as a dict.
    Raises SAPConnectionError if credentials are not configured.
    """
    conn_params = _get_connection_params()
    try:
        import pyrfc  # type: ignore  # requires SAP NW RFC SDK
    except ImportError as exc:
        raise SAPConnectionError(
            "pyrfc is not installed or SAP NW RFC SDK is not present on this host. "
            "This is an infrastructure dependency — see BLOCKERS.md."
        ) from exc

    with pyrfc.Connection(**conn_params) as conn:
        logger.info("Calling SAP BAPI: %s", function_name)
        result = conn.call(function_name, **params)
        return result


def extract_consumption_via_bapi(
    plant: str,
    material_types: List[str] = None,
    date_from: str = None,
    date_to: str = None,
) -> List[Dict[str, Any]]:
    """
    Extract consumption history via MB51 equivalent BAPI.
    Placeholder — actual BAPI name and field mapping to be confirmed with SAP team.
    """
    if material_types is None:
        material_types = ["ZSPR", "ZSPN"]
    result = call_bapi(
        "BAPI_MATERIAL_STOCK_REQ_LIST",  # placeholder — confirm with SAP team
        {
            "PLANT": plant,
            "DATEFROM": date_from or "",
            "DATETO": date_to or "",
        },
    )
    return result.get("STOCKREQLIST", [])


def extract_stock_master_via_bapi(
    plant: str,
    material_types: List[str] = None,
) -> List[Dict[str, Any]]:
    """
    Extract stock/material master via MM60 equivalent.
    Placeholder — actual BAPI name to be confirmed.
    """
    if material_types is None:
        material_types = ["ZSPR", "ZSPN"]
    result = call_bapi(
        "BAPI_MATERIAL_GET_ALL",  # placeholder — confirm with SAP team
        {"PLANT": plant},
    )
    return result.get("MATERIALLIST", [])
