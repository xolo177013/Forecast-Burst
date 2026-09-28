# =============================================================================
# SIH 26079 — STEP 3: FastAPI Backend
# Forecast Bust Detection — Dashboard API
#
# Project structure:
#
# bust-detect/
# ├── .env
# ├── models/
# │   ├── confidence_table.parquet
# │   ├── error_prone_regions.parquet
# │   ├── feature_importance.parquet
# │   └── model_metadata.json
# └── dashboard/
#     ├── api.py
#     ├── index.html
#     ├── css/
#     └── js/
#
# Run from dashboard folder:
#     uvicorn api:app --reload --port 8000
#
# Dashboard:
#     http://127.0.0.1:8000/
#
# API docs:
#     http://127.0.0.1:8000/docs
# =============================================================================

import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles


# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# dashboard/api.py
BASE_DIR = Path(__file__).resolve().parent

# dashboard/ -> bust-detect/
PROJECT_DIR = BASE_DIR.parent

# Load the .env from:
# bust-detect/.env
ENV_FILE = PROJECT_DIR / ".env"

load_dotenv(ENV_FILE)

# MODEL_DIR comes from .env.
#
# Example:
# MODEL_DIR=./models
#
# Since .env is in PROJECT_DIR, relative paths are resolved from PROJECT_DIR.
_model_dir_value = os.getenv("MODEL_DIR", "./models").strip()

_model_dir = Path(_model_dir_value).expanduser()

if _model_dir.is_absolute():
    MODEL_DIR = _model_dir.resolve()
else:
    MODEL_DIR = (PROJECT_DIR / _model_dir).resolve()

# Dashboard files
DASHBOARD_HTML = BASE_DIR / "index.html"
CSS_DIR = BASE_DIR / "css"
JS_DIR = BASE_DIR / "js"  

print("=" * 72)
print("SIH 26079 — Forecast Bust Detection API")
print("=" * 72)
print(f"Project directory : {PROJECT_DIR}")
print(f".env              : {ENV_FILE}")
print(f"MODEL_DIR         : {MODEL_DIR}")
print(f"Dashboard         : {DASHBOARD_HTML}")
print("=" * 72)


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Forecast Bust Detection API",
    description=(
        "Region-wise forecast confidence, bust probability, "
        "and explanations for medium-range Day 1–10 NWP forecasts."
    ),
    version="2.1.0",
)


# =============================================================================
# CORS
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# STATIC DASHBOARD FILES
# =============================================================================

if (BASE_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=BASE_DIR / "css"), name="css")
if (BASE_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=BASE_DIR / "js"), name="js")


# =============================================================================
# DATA CONTAINERS
# =============================================================================

_confidence_df: Optional[pd.DataFrame] = None
_region_summary_df: Optional[pd.DataFrame] = None
_importance_df: Optional[pd.DataFrame] = None
_metadata: Optional[dict] = None


# =============================================================================
# REQUIRED COLUMN DEFINITIONS
# =============================================================================

REQUIRED_CONFIDENCE_COLUMNS = {
    "init_date",
    "lead_day",
    "region_id",
    "lat_center",
    "lon_center",
    "forecast_confidence",
    "bust_probability",
}

OPTIONAL_CONFIDENCE_COLUMNS = {
    "top_reasons",
}
# ===== In api.py: REPLACE the old /live-verify block, /bust-probability and /error-prone-regions with these =====
from pydantic import BaseModel
from dashboard.live_predict import run_live_verification, predict_manual

@app.get("/live-verify")
def live_verify(init_date: str = Query(...)):
    try:
        meta, results = run_live_verification(init_date, MODEL_DIR, _confidence_df)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {**meta, "count": len(results), "results": results}

class ManualIn(BaseModel):
    features: dict

@app.post("/predict-manual")
def predict_manual_ep(body: ManualIn):
    try:
        return {"days": predict_manual(body.features, MODEL_DIR)}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/bust-probability")
def bust_probability(region_id: str = Query(...), lead_day: Optional[int] = Query(None, ge=1, le=10),
                     init_date: Optional[str] = Query(None)):
    df = _confidence_df[_confidence_df["region_id"].astype(str) == str(region_id)]
    if init_date: df = df[df["init_date"] == pd.to_datetime(init_date)]
    if lead_day is not None: df = df[df["lead_day"] == lead_day]
    if df.empty: raise HTTPException(404, "No data for this region/date.")
    t = (df.groupby("lead_day").agg(mean_bust_probability=("bust_probability","mean"),
         mean_confidence=("forecast_confidence","mean")).reset_index().sort_values("lead_day"))
    return {"region_id": str(region_id), "by_lead_day": t.to_dict(orient="records")}

@app.get("/error-prone-regions")
def error_prone_regions(top_n: int = Query(20, ge=1, le=992), init_date: Optional[str] = Query(None)):
    if init_date:
        d = _confidence_df[_confidence_df["init_date"] == pd.to_datetime(init_date)]
        if d.empty: raise HTTPException(404, "No data for that date.")
        g = (d.groupby(["region_id","lat_center","lon_center"]).agg(actual_bust_rate=("bust_label","mean"),
             mean_bust_probability=("bust_probability","mean"), mean_pred_error=("pred_error","mean"))
             .reset_index().sort_values("mean_bust_probability", ascending=False).head(top_n))
        return {"count": len(g), "regions": g.to_dict(orient="records")}
    out = _region_summary_df.head(top_n).copy()
    return {"count": len(out), "regions": out.to_dict(orient="records")}
# (also delete the old duplicate /live-verify and the old two endpoints above)

# =============================================================================
# STARTUP DATA LOADING
# =============================================================================

@app.on_event("startup")
def load_data():
    """
    Load all Step 2 model artifacts into memory.

    Required:
        confidence_table.parquet

    Optional:
        error_prone_regions.parquet
        feature_importance.parquet
        model_metadata.json
    """

    global _confidence_df
    global _region_summary_df
    global _importance_df
    global _metadata

    # -------------------------------------------------------------------------
    # Artifact paths
    # -------------------------------------------------------------------------

    conf_path = MODEL_DIR / "confidence_table.parquet"
    region_path = MODEL_DIR / "error_prone_regions.parquet"
    importance_path = MODEL_DIR / "feature_importance.parquet"
    metadata_path = MODEL_DIR / "model_metadata.json"

    print()
    print("Loading model artifacts...")
    print(f"  Confidence table : {conf_path}")
    print(f"  Region summary   : {region_path}")
    print(f"  Importance       : {importance_path}")
    print(f"  Metadata         : {metadata_path}")
    print()

    # -------------------------------------------------------------------------
    # Validate model directory
    # -------------------------------------------------------------------------

    if not MODEL_DIR.exists():
        raise RuntimeError(
            f"\nMODEL_DIR does not exist:\n"
            f"  {MODEL_DIR}\n\n"
            f"Check the MODEL_DIR value in:\n"
            f"  {ENV_FILE}"
        )

    # -------------------------------------------------------------------------
    # Required confidence table
    # -------------------------------------------------------------------------

    if not conf_path.exists():
        raise RuntimeError(
            f"\nMissing required model artifact:\n"
            f"  {conf_path}\n\n"
            f"Expected project structure:\n"
            f"  {PROJECT_DIR}\\\n"
            f"  ├── .env\n"
            f"  ├── models\\\n"
            f"  │   └── confidence_table.parquet\n"
            f"  └── dashboard\\\n"
            f"      └── api.py\n"
        )

    try:
        _confidence_df = pd.read_parquet(conf_path)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read:\n"
            f"  {conf_path}\n\n"
            f"Original error:\n"
            f"  {exc}"
        ) from exc

    # -------------------------------------------------------------------------
    # Validate confidence table columns
    # -------------------------------------------------------------------------

    missing_columns = (
        REQUIRED_CONFIDENCE_COLUMNS
        - set(_confidence_df.columns)
    )

    if missing_columns:
        raise RuntimeError(
            "confidence_table.parquet is missing required columns:\n"
            f"  {sorted(missing_columns)}\n\n"
            f"Available columns:\n"
            f"  {list(_confidence_df.columns)}"
        )

    # -------------------------------------------------------------------------
    # Normalize dates
    # -------------------------------------------------------------------------

    _confidence_df["init_date"] = pd.to_datetime(
        _confidence_df["init_date"],
        errors="coerce",
    )

    invalid_dates = _confidence_df["init_date"].isna().sum()

    if invalid_dates:
        print(
            f"WARNING: {invalid_dates:,} rows have invalid init_date values."
        )

    # -------------------------------------------------------------------------
    # Normalize lead day
    # -------------------------------------------------------------------------

    _confidence_df["lead_day"] = pd.to_numeric(
        _confidence_df["lead_day"],
        errors="coerce",
    )

    invalid_leads = _confidence_df["lead_day"].isna().sum()

    if invalid_leads:
        print(
            f"WARNING: {invalid_leads:,} rows have invalid lead_day values."
        )

    # -------------------------------------------------------------------------
    # Optional region summary
    # -------------------------------------------------------------------------

    if region_path.exists():

        try:
            _region_summary_df = pd.read_parquet(region_path)

            print(
                f"Loaded error-prone region summary: "
                f"{len(_region_summary_df):,} rows."
            )

        except Exception as exc:

            print(
                "WARNING: Could not read error_prone_regions.parquet:"
            )
            print(f"  {exc}")

            _region_summary_df = pd.DataFrame()

    else:

        print(
            "WARNING: error_prone_regions.parquet not found."
        )
        print(
            "The /error-prone-regions endpoint will return 404."
        )

        _region_summary_df = pd.DataFrame()

    # -------------------------------------------------------------------------
    # Optional feature importance
    # -------------------------------------------------------------------------

    if importance_path.exists():

        try:
            _importance_df = pd.read_parquet(importance_path)

            print(
                f"Loaded feature importance: "
                f"{len(_importance_df):,} rows."
            )

        except Exception as exc:

            print(
                "WARNING: Could not read feature_importance.parquet:"
            )
            print(f"  {exc}")

            _importance_df = pd.DataFrame()

    else:

        print(
            "WARNING: feature_importance.parquet not found."
        )

        _importance_df = pd.DataFrame()

    # -------------------------------------------------------------------------
    # Optional metadata
    # -------------------------------------------------------------------------

    if metadata_path.exists():

        try:

            with open(
                metadata_path,
                "r",
                encoding="utf-8",
            ) as f:
                _metadata = json.load(f)

            print("Loaded model metadata.")

        except Exception as exc:

            print(
                "WARNING: Could not read model_metadata.json:"
            )
            print(f"  {exc}")

            _metadata = {}

    else:

        print(
            "WARNING: model_metadata.json not found."
        )

        _metadata = {}

    # -------------------------------------------------------------------------
    # Dataset summary
    # -------------------------------------------------------------------------

    region_count = (
        _confidence_df["region_id"].nunique()
        if "region_id" in _confidence_df.columns
        else 0
    )

    lead_days = sorted(
        _confidence_df["lead_day"]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    date_min = (
        _confidence_df["init_date"].min()
        if not _confidence_df.empty
        else None
    )

    date_max = (
        _confidence_df["init_date"].max()
        if not _confidence_df.empty
        else None
    )

    print()
    print("=" * 72)
    print("DATA LOAD COMPLETE")
    print("=" * 72)
    print(f"Confidence rows : {len(_confidence_df):,}")
    print(f"Regions         : {region_count:,}")
    print(f"Lead days       : {lead_days}")
    print(f"Date range      : {date_min} → {date_max}")
    print("=" * 72)
    print()


# =============================================================================
# ROOT / DASHBOARD
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def root():
    """
    Serve the dashboard directly.
    """

    if DASHBOARD_HTML.exists():
        return FileResponse(DASHBOARD_HTML)

    return HTMLResponse(
        """
        <h2>Forecast Bust Detection API</h2>
        <p>Dashboard index.html was not found.</p>
        <p>API is still running.</p>

        <h3>Available endpoints</h3>
        <ul>
            <li>/health</li>
            <li>/confidence-map</li>
            <li>/bust-probability</li>
            <li>/error-prone-regions</li>
            <li>/explain</li>
            <li>/regions</li>
            <li>/model-info</li>
            <li>/forecast-dates</li>
        </ul>

        <p>
            Open <a href="/docs">/docs</a> for the interactive API.
        </p>
        """,
        status_code=200,
    )


# =============================================================================
# API INFORMATION
# =============================================================================

@app.get("/api")
def api_info():
    return {
        "status": "ok",
        "name": "Forecast Bust Detection API",
        "version": "2.1.0",
        "project": "SIH 26079",
        "endpoints": [
            "/health",
            "/forecast-dates",
            "/confidence-map",
            "/bust-probability",
            "/error-prone-regions",
            "/explain",
            "/regions",
            "/model-info",
        ],
    }


# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health")
def health():

    if _confidence_df is None:
        return {
            "status": "starting",
            "rows_loaded": 0,
            "regions_loaded": 0,
        }

    return {
        "status": "ok",
        "rows_loaded": int(len(_confidence_df)),
        "regions_loaded": int(
            _confidence_df["region_id"].nunique()
        ),
        "lead_days": sorted(
            _confidence_df["lead_day"]
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        ),
        "model_dir": str(MODEL_DIR),
    }


# =============================================================================
# FORECAST DATES
# =============================================================================

@app.get("/forecast-dates")
def forecast_dates():

    if _confidence_df is None:
        raise HTTPException(
            status_code=503,
            detail="Confidence data is not loaded.",
        )

    dates = (
        _confidence_df["init_date"]
        .dropna()
        .dt.strftime("%Y-%m-%d")
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    return {
        "count": len(dates),
        "dates": dates,
        "latest": dates[-1] if dates else None,
    }


# =============================================================================
# MODEL INFO
# =============================================================================

@app.get("/model-info")
def model_info():
    """
    Model performance summary and feature importance.
    """

    if _metadata:
        metrics = _metadata
    else:
        metrics = {}

    return {
        "metrics": metrics,
        "feature_importance": (
            _importance_df.to_dict(orient="records")
            if _importance_df is not None
            and not _importance_df.empty
            else []
        ),
    }


# =============================================================================
# REGIONS
# =============================================================================

@app.get("/regions")
def list_regions():
    """
    Return all known regions and their geographic centers.
    """

    if _confidence_df is None:
        raise HTTPException(
            status_code=503,
            detail="Confidence data is not loaded.",
        )

    required = [
        "region_id",
        "lat_center",
        "lon_center",
    ]

    missing = [
        col
        for col in required
        if col not in _confidence_df.columns
    ]

    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Missing region columns: {missing}",
        )

    out = (
        _confidence_df[required]
        .drop_duplicates()
        .sort_values("region_id")
    )

    return {
        "count": len(out),
        "regions": out.to_dict(orient="records"),
    }


# =============================================================================
# CONFIDENCE MAP
# =============================================================================

@app.get("/confidence-map")
def confidence_map(
    lead_day: int = Query(
        ...,
        ge=1,
        le=10,
        description="Forecast lead day, 1–10.",
    ),
    init_date: Optional[str] = Query(
        None,
        description="Optional forecast initialization date YYYY-MM-DD.",
    ),
):
    """
    Return regional confidence and bust probability
    for a particular forecast day.
    """

    if _confidence_df is None:
        raise HTTPException(
            status_code=503,
            detail="Confidence data is not loaded.",
        )

    df = _confidence_df[
        _confidence_df["lead_day"] == lead_day
    ]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data for lead_day={lead_day}.",
        )

    # -------------------------------------------------------------------------
    # Select date
    # -------------------------------------------------------------------------

    if init_date:

        try:
            target = pd.to_datetime(init_date)

        except Exception:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid init_date '{init_date}'. "
                    "Use YYYY-MM-DD."
                ),
            )

    else:

        target = df["init_date"].max()

    df = df[df["init_date"] == target]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No data for lead_day={lead_day} "
                f"on {target.date()}."
            ),
        )

    # -------------------------------------------------------------------------
    # Output
    # -------------------------------------------------------------------------

    columns = [
        "region_id",
        "lat_center",
        "lon_center",
        "forecast_confidence",
        "bust_probability",
    ]

    out = df[columns].copy()

    # Remove accidental NaN values from JSON response
    out = out.where(pd.notnull(out), None)

    return {
        "lead_day": lead_day,
        "init_date": str(target.date()),
        "region_count": len(out),
        "regions": out.to_dict(orient="records"),
    }


#=============================================================================
# EXPLAIN
# =============================================================================

@app.get("/explain")
def explain(
    region_id: str = Query(...),
    lead_day: int = Query(
        ...,
        ge=1,
        le=10,
    ),
    init_date: Optional[str] = Query(None),
):
    """
    Explain a regional forecast confidence/bust prediction.
    """

    if _confidence_df is None:
        raise HTTPException(
            status_code=503,
            detail="Confidence data is not loaded.",
        )

    df = _confidence_df[
        (
            _confidence_df["region_id"].astype(str)
            == str(region_id)
        )
        & (
            _confidence_df["lead_day"]
            == lead_day
        )
    ]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No matching forecast for "
                f"region_id={region_id}, "
                f"lead_day={lead_day}."
            ),
        )

    # -------------------------------------------------------------------------
    # Optional date filter
    # -------------------------------------------------------------------------

    if init_date:

        try:
            target = pd.to_datetime(init_date)

        except Exception:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid init_date '{init_date}'. "
                    "Use YYYY-MM-DD."
                ),
            )

        df = df[df["init_date"] == target]

        if df.empty:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No data for {region_id} "
                    f"on {init_date}, "
                    f"lead_day={lead_day}."
                ),
            )

    # Use the first matching row
    row = df.iloc[0]

    # -------------------------------------------------------------------------
    # Top reasons
    # -------------------------------------------------------------------------

    top_reasons = []

    if "top_reasons" in df.columns:

        value = row.get("top_reasons")

        if value is not None and not pd.isna(value):

            if isinstance(value, (list, tuple)):
                top_reasons = list(value)

            elif isinstance(value, str):

                # Preserve JSON-like lists if Step 2 stored them as strings.
                try:

                    parsed = json.loads(value)

                    if isinstance(parsed, list):
                        top_reasons = parsed
                    else:
                        top_reasons = [value]

                except Exception:

                    top_reasons = [value]

    return {
        "region_id": str(region_id),
        "lead_day": int(lead_day),
        "init_date": str(row["init_date"].date()),
        "bust_probability": float(
            row["bust_probability"]
        ),
        "forecast_confidence": float(
            row["forecast_confidence"]
        ),
        "top_reasons": top_reasons,
    }


# =============================================================================
# LOCAL DEVELOPMENT ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "api:app",
        host=os.getenv(
            "API_HOST",
            "127.0.0.1",
        ),
        port=int(
            os.getenv(
                "API_PORT",
                "8000",
            )
        ),
        reload=True,
    )