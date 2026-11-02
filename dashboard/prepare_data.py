#!/usr/bin/env python3
"""Prepare aggregated JSON data files for the inventory dashboard.

Reads Parquet files produced by the SAP extraction pipeline and generates
the summary JSON files that the dashboard's index.html consumes:

  data/manifest.json           — table summary (name, row count, column count)
  data/inventory_by_plant.json — gross inventory value by plant
  data/stock_by_category.json  — stock value by material category
  data/days_on_hand.json       — days-on-hand distribution histogram
  data/nmi_smi_summary.json    — NMI / SMI / Active / Obsolete flag counts

Usage:
    python dashboard/prepare_data.py --parquet-dir sap_extraction/parquet
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent / "data"


def _load_parquet(path: Path) -> "pd.DataFrame":
    import pandas as pd
    return pd.read_parquet(path)


def _find_parquet_files(parquet_dir: Path) -> Dict[str, Path]:
    files: Dict[str, Path] = {}
    for p in sorted(parquet_dir.glob("*.parquet")):
        files[p.stem] = p
    return files


def build_manifest(parquet_dir: Path) -> List[Dict[str, Any]]:
    import pandas as pd
    tables = []
    for pq_path in sorted(parquet_dir.glob("*.parquet")):
        df = pd.read_parquet(pq_path)
        tables.append({
            "table_name": pq_path.stem.upper(),
            "row_count": len(df),
            "column_count": len(df.columns),
            "description": pq_path.stem.replace("_", " ").title(),
        })
    manifest = {
        "extraction_date": datetime.now(timezone.utc).isoformat(),
        "schema": "VEDANTA_POC",
        "total_tables": len(tables),
        "tables": tables,
    }
    out = OUTPUT_DIR / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    logger.info("Wrote %s (%d tables)", out, len(tables))
    return tables


def build_inventory_by_plant(parquet_dir: Path) -> None:
    import pandas as pd
    ic_path = parquet_dir / "inventory_classification.parquet"
    if not ic_path.exists():
        candidates = list(parquet_dir.glob("*inventory_classification*"))
        if not candidates:
            logger.warning("No inventory_classification Parquet found; skipping.")
            return
        ic_path = candidates[0]
    df = pd.read_parquet(ic_path)
    if "AS_OF_DATE" in df.columns:
        latest = df["AS_OF_DATE"].max()
        df = df[df["AS_OF_DATE"] == latest]
    df["INVENTORY_VALUE_INR"] = pd.to_numeric(df["INVENTORY_VALUE_INR"], errors="coerce").fillna(0)
    by_plant = df.groupby("PLANT_ID")["INVENTORY_VALUE_INR"].sum().sort_values(ascending=False)
    result = {
        "as_of_date": str(latest) if "AS_OF_DATE" in df.columns else "unknown",
        "currency": "INR",
        "total_value": round(float(by_plant.sum()), 2),
        "plants": [{"plant_id": pid, "plant_name": pid.replace("HZL_DEMO_", "Demo Plant "), "value": round(float(val), 2)} for pid, val in by_plant.items()],
    }
    out = OUTPUT_DIR / "inventory_by_plant.json"
    out.write_text(json.dumps(result, indent=2))
    logger.info("Wrote %s", out)


def build_stock_by_category(parquet_dir: Path) -> None:
    import pandas as pd
    ic_path = parquet_dir / "inventory_classification.parquet"
    mat_path = parquet_dir / "dim_material.parquet"
    if not ic_path.exists() or not mat_path.exists():
        logger.warning("Missing Parquet files for stock_by_category; skipping.")
        return
    ic = pd.read_parquet(ic_path)
    mat = pd.read_parquet(mat_path)
    if "AS_OF_DATE" in ic.columns:
        latest = ic["AS_OF_DATE"].max()
        ic = ic[ic["AS_OF_DATE"] == latest]
    ic["INVENTORY_VALUE_INR"] = pd.to_numeric(ic["INVENTORY_VALUE_INR"], errors="coerce").fillna(0)
    merged = ic.merge(mat[["MATERIAL_ID", "MATERIAL_GROUP"]], on="MATERIAL_ID", how="left")
    by_cat = merged.groupby("MATERIAL_GROUP").agg(material_count=("MATERIAL_ID", "nunique"), value=("INVENTORY_VALUE_INR", "sum")).sort_values("value", ascending=False)
    result = {
        "as_of_date": str(latest) if "AS_OF_DATE" in ic.columns else "unknown",
        "currency": "INR",
        "categories": [{"category": cat.replace("_", " ").title(), "material_count": int(row["material_count"]), "value": round(float(row["value"]), 2)} for cat, row in by_cat.iterrows()],
    }
    out = OUTPUT_DIR / "stock_by_category.json"
    out.write_text(json.dumps(result, indent=2))
    logger.info("Wrote %s", out)


def build_days_on_hand(parquet_dir: Path) -> None:
    import pandas as pd
    ic_path = parquet_dir / "inventory_classification.parquet"
    if not ic_path.exists():
        logger.warning("No inventory_classification Parquet found; skipping.")
        return
    df = pd.read_parquet(ic_path)
    if "AS_OF_DATE" in df.columns:
        latest = df["AS_OF_DATE"].max()
        df = df[df["AS_OF_DATE"] == latest]
    df["DAYS_ON_HAND"] = pd.to_numeric(df["DAYS_ON_HAND"], errors="coerce").fillna(0)
    buckets = [
        ("0 (Stockout)", 0, 0),
        ("1\u201330 days", 1, 30),
        ("31\u201390 days", 31, 90),
        ("91\u2013180 days", 91, 180),
        ("181\u2013365 days", 181, 365),
        ("365+ days", 366, 99999),
    ]
    counts = []
    for label, lo, hi in buckets:
        if lo == 0 and hi == 0:
            cnt = int((df["DAYS_ON_HAND"] == 0).sum())
        else:
            cnt = int(((df["DAYS_ON_HAND"] >= lo) & (df["DAYS_ON_HAND"] <= hi)).sum())
        counts.append({"range": label, "min": lo, "max": hi, "count": cnt})
    result = {
        "as_of_date": str(latest) if "AS_OF_DATE" in df.columns else "unknown",
        "total_items": int(len(df)),
        "buckets": counts,
    }
    out = OUTPUT_DIR / "days_on_hand.json"
    out.write_text(json.dumps(result, indent=2))
    logger.info("Wrote %s", out)


def build_nmi_smi_summary(parquet_dir: Path) -> None:
    import pandas as pd
    ic_path = parquet_dir / "inventory_classification.parquet"
    if not ic_path.exists():
        logger.warning("No inventory_classification Parquet found; skipping.")
        return
    df = pd.read_parquet(ic_path)
    if "AS_OF_DATE" in df.columns:
        latest = df["AS_OF_DATE"].max()
        df = df[df["AS_OF_DATE"] == latest]
    df["INVENTORY_VALUE_INR"] = pd.to_numeric(df["INVENTORY_VALUE_INR"], errors="coerce").fillna(0)
    total = len(df)
    by_class = df.groupby("MOVEMENT_CLASS").agg(count=("MATERIAL_ID", "size"), value=("INVENTORY_VALUE_INR", "sum")).sort_values("count", ascending=False)
    label_map = {
        "ACTIVE": ("Normal / Active", "success"),
        "SLOW_MOVING": ("Slow-Moving (SMI)", "warning"),
        "OBSOLETE": ("Obsolete", "danger"),
        "NON_MOVING": ("Non-Moving (NMI)", "info"),
    }
    flags = []
    for cls, row in by_class.iterrows():
        lbl, sem = label_map.get(cls, (cls, "neutral"))
        flags.append({
            "flag": cls.replace("_", " ").title(),
            "label": lbl,
            "count": int(row["count"]),
            "percentage": round(100 * row["count"] / total, 2),
            "value": round(float(row["value"]), 2),
            "semantic": sem,
        })
    result = {
        "as_of_date": str(latest) if "AS_OF_DATE" in df.columns else "unknown",
        "total_items": total,
        "currency": "INR",
        "flags": flags,
    }
    out = OUTPUT_DIR / "nmi_smi_summary.json"
    out.write_text(json.dumps(result, indent=2))
    logger.info("Wrote %s", out)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Generate dashboard JSON from Parquet files.")
    parser.add_argument("--parquet-dir", type=Path, default=Path("sap_extraction/parquet"), help="Directory containing the extracted Parquet files.")
    args = parser.parse_args()
    if not args.parquet_dir.exists():
        logger.error("Parquet directory %s does not exist.", args.parquet_dir)
        sys.exit(1)
    pq_files = _find_parquet_files(args.parquet_dir)
    if not pq_files:
        logger.error("No .parquet files found in %s.", args.parquet_dir)
        sys.exit(1)
    logger.info("Found %d Parquet files in %s", len(pq_files), args.parquet_dir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_manifest(args.parquet_dir)
    build_inventory_by_plant(args.parquet_dir)
    build_stock_by_category(args.parquet_dir)
    build_days_on_hand(args.parquet_dir)
    build_nmi_smi_summary(args.parquet_dir)
    logger.info("All dashboard JSON files written to %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()
