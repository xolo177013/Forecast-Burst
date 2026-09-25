# =============================================================================
# SIH 26079 — STEP 3: FastAPI backend (v2)
# New in this version: /health, /regions, /model-info (feeds the dashboard's
# KPI cards and "how the model decides" panel).
#
# Run locally:  uvicorn api:app --reload --port 8000
# Docs UI:      http://localhost:8000/docs
# =============================================================================
import os
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

MODEL_DIR = Path(
    os.getenv("MODEL_DIR", str(BASE_DIR / "models"))
)

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

BASE_DIR = Path(__file__).parent
DASHBOARD_HTML = BASE_DIR / "index.html"

app = FastAPI(
    title="Forecast Bust Detection API",
    description="Region-wise forecast confidence, bust probability, and explanations "
                "for medium-range (Day 1-10) NWP forecasts.",
    version="2.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Serve the dashboard's CSS/JS -- index.html links to these as relative paths
if (BASE_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=BASE_DIR / "css"), name="css")
if (BASE_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=BASE_DIR / "js"), name="js")

_confidence_df: Optional[pd.DataFrame] = None
_region_summary_df: Optional[pd.DataFrame] = None
_importance_df: Optional[pd.DataFrame] = None
_metadata: Optional[dict] = None


@app.on_event("startup")
def load_data():
    global _confidence_df, _region_summary_df, _importance_df, _metadata
    conf_path = os.path.join(MODEL_DIR, "confidence_table.parquet")
    region_path = os.path.join(MODEL_DIR, "error_prone_regions.parquet")
    importance_path = os.path.join(MODEL_DIR, "feature_importance.parquet")
    metadata_path = os.path.join(MODEL_DIR, "model_metadata.json")

    if not os.path.exists(conf_path):
        raise RuntimeError(f"Missing {conf_path} -- run Step 2 (training) first.")

    _confidence_df = pd.read_parquet(conf_path)
    _confidence_df["init_date"] = pd.to_datetime(_confidence_df["init_date"])
    _region_summary_df = pd.read_parquet(region_path)
    _importance_df = pd.read_parquet(importance_path) if os.path.exists(importance_path) else pd.DataFrame()
    _metadata = json.load(open(metadata_path)) if os.path.exists(metadata_path) else {}

    print(f"Loaded {len(_confidence_df):,} confidence rows across "
          f"{_confidence_df['region_id'].nunique()} regions.")


@app.get("/", response_class=HTMLResponse)
def root():
    """Serves the dashboard directly -- open http://localhost:8000 after starting uvicorn."""
    if DASHBOARD_HTML.exists():
        return FileResponse(DASHBOARD_HTML)
    return HTMLResponse(
        "<h3>index.html not found next to api.py.</h3>"
        "<p>Endpoints are still available: /health, /confidence-map, /bust-probability, "
        "/error-prone-regions, /explain, /regions, /model-info</p>"
    )


@app.get("/api")
def api_info():
    return {
        "status": "ok",
        "endpoints": ["/health", "/confidence-map", "/bust-probability",
                      "/error-prone-regions", "/explain", "/regions", "/model-info"],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "rows_loaded": int(len(_confidence_df)) if _confidence_df is not None else 0,
        "regions_loaded": int(_confidence_df["region_id"].nunique()) if _confidence_df is not None else 0,
    }


@app.get("/model-info")
def model_info():
    """Model performance summary + feature importance -- for a 'trust panel' on the dashboard."""
    if not _metadata:
        raise HTTPException(404, "model_metadata.json not found -- re-run Step 2 to generate it.")
    return {
        "metrics": _metadata,
        "feature_importance": _importance_df.to_dict(orient="records") if not _importance_df.empty else [],
    }


@app.get("/regions")
def list_regions():
    """All known region IDs + centers -- for populating a dropdown/selector."""
    out = _confidence_df[["region_id", "lat_center", "lon_center"]].drop_duplicates()
    return {"count": len(out), "regions": out.to_dict(orient="records")}


@app.get("/confidence-map")
def confidence_map(
    lead_day: int = Query(..., ge=1, le=10),
    init_date: Optional[str] = Query(None),
):
    df = _confidence_df[_confidence_df["lead_day"] == lead_day]
    if df.empty:
        raise HTTPException(404, f"No data for lead_day={lead_day}")

    target = pd.to_datetime(init_date) if init_date else df["init_date"].max()
    df = df[df["init_date"] == target]
    if df.empty:
        raise HTTPException(404, f"No data for lead_day={lead_day} on {target.date()}")

    out = df[["region_id", "lat_center", "lon_center", "forecast_confidence", "bust_probability"]]
    return {"lead_day": lead_day, "init_date": str(target.date()), "regions": out.to_dict(orient="records")}


@app.get("/bust-probability")
def bust_probability(region_id: str = Query(...), lead_day: Optional[int] = Query(None, ge=1, le=10)):
    df = _confidence_df[_confidence_df["region_id"] == region_id]
    if lead_day is not None:
        df = df[df["lead_day"] == lead_day]
    if df.empty:
        raise HTTPException(404, f"No data for region_id={region_id}")

    trend = (
        df.groupby("lead_day")
        .agg(mean_bust_probability=("bust_probability", "mean"), mean_confidence=("forecast_confidence", "mean"))
        .reset_index().to_dict(orient="records")
    )
    return {"region_id": region_id, "by_lead_day": trend}


@app.get("/error-prone-regions")
def error_prone_regions(top_n: int = Query(20, ge=1, le=992)):
    out = _region_summary_df.head(top_n)
    return {"count": len(out), "regions": out.to_dict(orient="records")}


@app.get("/explain")
def explain(region_id: str = Query(...), lead_day: int = Query(..., ge=1, le=10), init_date: Optional[str] = Query(None)):
    df = _confidence_df[(_confidence_df["region_id"] == region_id) & (_confidence_df["lead_day"] == lead_day)]
    if df.empty:
        raise HTTPException(404, "No matching forecast found")

    if init_date:
        target = pd.to_datetime(init_date)
        df = df[df["init_date"] == target]
        if df.empty:
            raise HTTPException(404, f"No data for {region_id} on {init_date}, lead_day={lead_day}")
    row = df.iloc[0]

    return {
        "region_id": region_id, "lead_day": lead_day, "init_date": str(row["init_date"].date()),
        "bust_probability": float(row["bust_probability"]),
        "forecast_confidence": float(row["forecast_confidence"]),
        "top_reasons": row["top_reasons"],
    }