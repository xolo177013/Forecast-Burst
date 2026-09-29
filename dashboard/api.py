# =============================================================================
# SIH 26079 — FastAPI Backend
# Forecast Bust Detection — Dashboard API
#
# Project structure:
#
# bust-detect/
# ├── .env                      (optional)
# ├── models/
# │   ├── confidence_table.parquet
# │   ├── error_prone_regions.parquet
# │   ├── feature_importance.parquet
# │   └── model_metadata.json
# └── dashboard/
#     ├── __init__.py
#     ├── api.py
#     ├── live_predict.py
#     ├── index.html
#     ├── css/
#     └── js/
#
# Run from the PROJECT ROOT (bust-detect/), not from dashboard/:
#     uvicorn dashboard.api:app --reload --port 8000
#
# Dashboard:  http://127.0.0.1:8000/
# API docs:   http://127.0.0.1:8000/docs
#
# Memory notes (for 512 MB hosts such as Render free tier):
#   * Only the small columns of confidence_table.parquet are kept in RAM,
#     stored compactly (int8 / float32 / dictionary-encoded region_id).
#   * The long `top_reasons` text column is NOT loaded; it is read from the
#     parquet file on demand for the single row /explain needs.
#   * live_predict (xarray / dask / gcsfs / zarr) is imported lazily.
# =============================================================================

import json
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# dashboard/api.py
BASE_DIR = Path(__file__).resolve().parent

# dashboard/ -> bust-detect/
PROJECT_DIR = BASE_DIR.parent

# bust-detect/.env  (optional; defaults below work without it)
ENV_FILE = PROJECT_DIR / ".env"
load_dotenv(ENV_FILE)

# MODEL_DIR comes from the environment / .env, default ./models.
# Relative paths are resolved from PROJECT_DIR.
_model_dir_value = os.getenv("MODEL_DIR", "./models").strip()
_model_dir = Path(_model_dir_value).expanduser()

if _model_dir.is_absolute():
    MODEL_DIR = _model_dir.resolve()
else:
    MODEL_DIR = (PROJECT_DIR / _model_dir).resolve()

CONF_PATH = MODEL_DIR / "confidence_table.parquet"

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
# DATA CONTAINERS
# =============================================================================

_confidence_df: Optional[pd.DataFrame] = None
_region_summary_df: Optional[pd.DataFrame] = None
_importance_df: Optional[pd.DataFrame] = None
_metadata: Optional[dict] = None
_forecast_dates: list = []


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

# Columns kept in RAM. `top_reasons` is deliberately excluded.
LIGHT_COLS = [
    "init_date",
    "lead_day",
    "region_id",
    "lat_center",
    "lon_center",
    "forecast_confidence",
    "bust_probability",
    "bust_label",
    "pred_error",
]

FLOAT_COLS = [
    "lat_center",
    "lon_center",
    "forecast_confidence",
    "bust_probability",
    "bust_label",
    "pred_error",
]


# =============================================================================
# LOW-MEMORY PARQUET HELPERS
# =============================================================================

def load_confidence_light(path: Path) -> pd.DataFrame:
    """
    Load only the small columns, converted to compact types *inside Arrow*
    (before pandas) so the peak memory stays low.
    Skips the large `top_reasons` column.
    """
    names = pq.ParquetFile(path).schema_arrow.names
    cols = [c for c in LIGHT_COLS if c in names]

    t = pq.read_table(path, columns=cols)

    for i, name in enumerate(list(t.schema.names)):
        col = t.column(name)

        if name == "region_id":
            # Force string (works for numeric ids too), then dictionary-encode
            new = col.cast(pa.string()).combine_chunks().dictionary_encode()
        elif name == "lead_day":
            new = col.cast(pa.int8())
        elif name in FLOAT_COLS:
            new = col.cast(pa.float32())
        else:
            continue

        t = t.set_column(i, name, new)

    df = t.to_pandas(date_as_object=False)
    del t
    return df


# Per-date explanation files written by split_reasons.py:
#   models/reasons/2021-06-20.parquet  (region_id, lead_day, top_reasons)
# Each file is tiny (~10k rows), so /explain never scans the big table.
REASONS_DIR = MODEL_DIR / "reasons"


@lru_cache(maxsize=8)
def _load_reasons_for_date(date_key: str):
    """Return {(region_id, lead_day): top_reasons} for one forecast date."""
    f = REASONS_DIR / f"{date_key}.parquet"
    if not f.exists():
        return None
    try:
        d = pd.read_parquet(f, columns=["region_id", "lead_day", "top_reasons"])
        return {
            (str(r), int(l)): v
            for r, l, v in zip(d["region_id"], d["lead_day"], d["top_reasons"])
        }
    except Exception as exc:
        print("reasons read failed:", exc)
        return None


def read_top_reasons(region_id, lead_day, init_date):
    date_key = str(pd.to_datetime(init_date).date())
    table = _load_reasons_for_date(date_key)
    if not table:
        return None
    return table.get((str(region_id), int(lead_day)))


def _records(df: pd.DataFrame) -> list:
    """DataFrame -> JSON-safe list of dicts (NaN -> None)."""
    return df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")


# =============================================================================
# STARTUP DATA LOADING
# =============================================================================

def load_data():
    """
    Load Step 2 model artifacts into memory.

    Required:  confidence_table.parquet
    Optional:  error_prone_regions.parquet, feature_importance.parquet,
               model_metadata.json
    """

    global _confidence_df
    global _region_summary_df
    global _importance_df
    global _metadata
    global _forecast_dates

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

    if not MODEL_DIR.exists():
        raise RuntimeError(
            f"\nMODEL_DIR does not exist:\n  {MODEL_DIR}\n\n"
            f"Check the MODEL_DIR value in:\n  {ENV_FILE}"
        )

    if not conf_path.exists():
        raise RuntimeError(
            f"\nMissing required model artifact:\n  {conf_path}\n"
        )

    # Git-LFS pointer files are tiny text files, not real parquet
    if conf_path.stat().st_size < 10_000:
        raise RuntimeError(
            f"{conf_path} is only {conf_path.stat().st_size} bytes. "
            "It looks like a Git LFS pointer, not the real file. "
            "Make sure the deploy fetches LFS objects (or store the file "
            "in normal git)."
        )

    try:
        _confidence_df = load_confidence_light(conf_path)
        ram = _confidence_df.memory_usage(deep=True).sum() / 1e6
        print(f"Confidence table in RAM: {ram:.0f} MB")
    except Exception as exc:
        raise RuntimeError(
            f"Could not read:\n  {conf_path}\n\nOriginal error:\n  {exc}"
        ) from exc

    missing_columns = REQUIRED_CONFIDENCE_COLUMNS - set(_confidence_df.columns)
    if missing_columns:
        raise RuntimeError(
            "confidence_table.parquet is missing required columns:\n"
            f"  {sorted(missing_columns)}\n\n"
            f"Available columns:\n  {list(_confidence_df.columns)}"
        )

    # Normalize dates
    _confidence_df["init_date"] = pd.to_datetime(
        _confidence_df["init_date"], errors="coerce"
    )
    invalid_dates = int(_confidence_df["init_date"].isna().sum())
    if invalid_dates:
        print(f"WARNING: {invalid_dates:,} rows have invalid init_date values.")

    invalid_leads = int(_confidence_df["lead_day"].isna().sum())
    if invalid_leads:
        print(f"WARNING: {invalid_leads:,} rows have invalid lead_day values.")

    # Unique forecast dates, computed once (cheap; avoids per-request strftime)
    _forecast_dates = sorted(
        pd.Series(_confidence_df["init_date"].dropna().unique())
        .dt.strftime("%Y-%m-%d")
        .tolist()
    )

    # Optional region summary
    if region_path.exists():
        try:
            _region_summary_df = pd.read_parquet(region_path)
            print(f"Loaded error-prone region summary: {len(_region_summary_df):,} rows.")
        except Exception as exc:
            print("WARNING: Could not read error_prone_regions.parquet:")
            print(f"  {exc}")
            _region_summary_df = pd.DataFrame()
    else:
        print("WARNING: error_prone_regions.parquet not found.")
        _region_summary_df = pd.DataFrame()

    # Optional feature importance
    if importance_path.exists():
        try:
            _importance_df = pd.read_parquet(importance_path)
            print(f"Loaded feature importance: {len(_importance_df):,} rows.")
        except Exception as exc:
            print("WARNING: Could not read feature_importance.parquet:")
            print(f"  {exc}")
            _importance_df = pd.DataFrame()
    else:
        print("WARNING: feature_importance.parquet not found.")
        _importance_df = pd.DataFrame()

    # Optional metadata
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                _metadata = json.load(f)
            print("Loaded model metadata.")
        except Exception as exc:
            print("WARNING: Could not read model_metadata.json:")
            print(f"  {exc}")
            _metadata = {}
    else:
        print("WARNING: model_metadata.json not found.")
        _metadata = {}

    # Summary
    region_count = int(_confidence_df["region_id"].nunique())
    lead_days = sorted(
        _confidence_df["lead_day"].dropna().astype(int).unique().tolist()
    )
    date_min = _confidence_df["init_date"].min()
    date_max = _confidence_df["init_date"].max()

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

    if not REASONS_DIR.exists():
        print("WARNING: models/reasons/ not found - /explain will return no reasons.")
        print("         Run split_reasons.py once and commit the output.")

    # Give temporary load-time memory back to the OS
    import gc
    gc.collect()
    try:
        pa.default_memory_pool().release_unused()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_data()
    yield


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Forecast Bust Detection API",
    description=(
        "Region-wise forecast confidence, bust probability, "
        "and explanations for medium-range Day 1–10 NWP forecasts."
    ),
    version="2.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static dashboard files
if CSS_DIR.exists():
    app.mount("/css", StaticFiles(directory=CSS_DIR), name="css")
if JS_DIR.exists():
    app.mount("/js", StaticFiles(directory=JS_DIR), name="js")


def _require_data():
    if _confidence_df is None:
        raise HTTPException(status_code=503, detail="Confidence data is not loaded.")


# =============================================================================
# LIVE VERIFICATION / MANUAL PREDICTION  (heavy imports done lazily)
# =============================================================================

@app.get("/live-verify")
def live_verify(init_date: str = Query(...)):
    _require_data()
    from dashboard.live_predict import run_live_verification

    try:
        meta, results = run_live_verification(init_date, MODEL_DIR, _confidence_df)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {**meta, "count": len(results), "results": results}


class ManualIn(BaseModel):
    features: dict


@app.post("/predict-manual")
def predict_manual_ep(body: ManualIn):
    from dashboard.live_predict import predict_manual

    try:
        return {"days": predict_manual(body.features, MODEL_DIR)}
    except Exception as e:
        raise HTTPException(400, str(e))


# =============================================================================
# ROOT / DASHBOARD
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the dashboard directly."""

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
        <p>Open <a href="/docs">/docs</a> for the interactive API.</p>
        """,
        status_code=200,
    )


@app.get("/api")
def api_info():
    return {
        "status": "ok",
        "name": "Forecast Bust Detection API",
        "version": "2.2.0",
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
            "/live-verify",
            "/predict-manual",
        ],
    }


# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health")
def health():

    if _confidence_df is None:
        return {"status": "starting", "rows_loaded": 0, "regions_loaded": 0}

    return {
        "status": "ok",
        "rows_loaded": int(len(_confidence_df)),
        "regions_loaded": int(_confidence_df["region_id"].nunique()),
        "lead_days": sorted(
            _confidence_df["lead_day"].dropna().astype(int).unique().tolist()
        ),
        "model_dir": str(MODEL_DIR),
    }


# =============================================================================
# FORECAST DATES
# =============================================================================

@app.get("/forecast-dates")
def forecast_dates():
    _require_data()
    return {
        "count": len(_forecast_dates),
        "dates": _forecast_dates,
        "latest": _forecast_dates[-1] if _forecast_dates else None,
    }


# =============================================================================
# MODEL INFO
# =============================================================================

@app.get("/model-info")
def model_info():
    """Model performance summary and feature importance."""

    metrics = _metadata if _metadata else {}

    return {
        "metrics": metrics,
        "feature_importance": (
            _records(_importance_df)
            if _importance_df is not None and not _importance_df.empty
            else []
        ),
    }


# =============================================================================
# REGIONS
# =============================================================================

@app.get("/regions")
def list_regions():
    """Return all known regions and their geographic centers."""
    _require_data()

    required = ["region_id", "lat_center", "lon_center"]
    missing = [c for c in required if c not in _confidence_df.columns]
    if missing:
        raise HTTPException(
            status_code=500, detail=f"Missing region columns: {missing}"
        )

    out = (
        _confidence_df.drop_duplicates(subset="region_id")[required]
        .copy()
    )
    out["region_id"] = out["region_id"].astype(str)
    out = out.sort_values("region_id")

    return {"count": len(out), "regions": _records(out)}


# =============================================================================
# CONFIDENCE MAP
# =============================================================================

@app.get("/confidence-map")
def confidence_map(
    lead_day: int = Query(..., ge=1, le=10, description="Forecast lead day, 1–10."),
    init_date: Optional[str] = Query(
        None, description="Optional forecast initialization date YYYY-MM-DD."
    ),
):
    """Regional confidence and bust probability for one forecast day."""
    _require_data()

    df = _confidence_df[_confidence_df["lead_day"] == lead_day]

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for lead_day={lead_day}.")

    if init_date:
        try:
            target = pd.to_datetime(init_date)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid init_date '{init_date}'. Use YYYY-MM-DD.",
            )
    else:
        target = df["init_date"].max()

    df = df[df["init_date"] == target]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data for lead_day={lead_day} on {target.date()}.",
        )

    columns = [
        "region_id",
        "lat_center",
        "lon_center",
        "forecast_confidence",
        "bust_probability",
    ]
    out = df[columns].copy()
    out["region_id"] = out["region_id"].astype(str)
    for c in ["lat_center", "lon_center", "forecast_confidence", "bust_probability"]:
        out[c] = out[c].astype("float64").round(6)

    return {
        "lead_day": lead_day,
        "init_date": str(target.date()),
        "region_count": len(out),
        "regions": _records(out),
    }


# =============================================================================
# BUST PROBABILITY (per region, by lead day)
# =============================================================================

@app.get("/bust-probability")
def bust_probability(
    region_id: str = Query(...),
    lead_day: Optional[int] = Query(None, ge=1, le=10),
    init_date: Optional[str] = Query(None),
):
    _require_data()

    df = _confidence_df[_confidence_df["region_id"] == str(region_id)]

    if init_date:
        df = df[df["init_date"] == pd.to_datetime(init_date)]
    if lead_day is not None:
        df = df[df["lead_day"] == lead_day]

    if df.empty:
        raise HTTPException(404, "No data for this region/date.")

    t = (
        df.groupby("lead_day", observed=True)
        .agg(
            mean_bust_probability=("bust_probability", "mean"),
            mean_confidence=("forecast_confidence", "mean"),
        )
        .reset_index()
        .sort_values("lead_day")
    )
    t["lead_day"] = t["lead_day"].astype(int)

    return {"region_id": str(region_id), "by_lead_day": _records(t)}


# =============================================================================
# ERROR-PRONE REGIONS
# =============================================================================

@app.get("/error-prone-regions")
def error_prone_regions(
    top_n: int = Query(20, ge=1, le=992),
    init_date: Optional[str] = Query(None),
):
    _require_data()

    if init_date:
        d = _confidence_df[_confidence_df["init_date"] == pd.to_datetime(init_date)]
        if d.empty:
            raise HTTPException(404, "No data for that date.")

        needed = {"bust_label", "pred_error"}
        if not needed.issubset(d.columns):
            raise HTTPException(
                400, f"Columns {sorted(needed - set(d.columns))} not available."
            )

        g = (
            d.groupby(["region_id", "lat_center", "lon_center"], observed=True)
            .agg(
                actual_bust_rate=("bust_label", "mean"),
                mean_bust_probability=("bust_probability", "mean"),
                mean_pred_error=("pred_error", "mean"),
            )
            .reset_index()
            .sort_values("mean_bust_probability", ascending=False)
            .head(top_n)
        )
        g["region_id"] = g["region_id"].astype(str)
        return {"count": len(g), "regions": _records(g)}

    if _region_summary_df is None or _region_summary_df.empty:
        raise HTTPException(404, "Error-prone region summary is not available.")

    out = _region_summary_df.head(top_n).copy()
    return {"count": len(out), "regions": _records(out)}


# =============================================================================
# EXPLAIN
# =============================================================================

@app.get("/explain")
def explain(
    region_id: str = Query(...),
    lead_day: int = Query(..., ge=1, le=10),
    init_date: Optional[str] = Query(None),
):
    """Explain a regional forecast confidence / bust prediction."""
    _require_data()

    df = _confidence_df[
        (_confidence_df["region_id"] == str(region_id))
        & (_confidence_df["lead_day"] == lead_day)
    ]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No matching forecast for region_id={region_id}, lead_day={lead_day}.",
        )

    if init_date:
        try:
            target = pd.to_datetime(init_date)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid init_date '{init_date}'. Use YYYY-MM-DD.",
            )

        df = df[df["init_date"] == target]

        if df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No data for {region_id} on {init_date}, lead_day={lead_day}.",
            )
    else:
        # Default to the latest available date (matches the map's default)
        df = df[df["init_date"] == df["init_date"].max()]

    row = df.iloc[0]

    top_reasons = []
    value = read_top_reasons(region_id, lead_day, row["init_date"])

    if value is not None and not pd.isna(value):
        if isinstance(value, (list, tuple)):
            top_reasons = list(value)
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                top_reasons = parsed if isinstance(parsed, list) else [value]
            except Exception:
                top_reasons = [value]

    return {
        "region_id": str(region_id),
        "lead_day": int(lead_day),
        "init_date": str(row["init_date"].date()),
        "bust_probability": float(row["bust_probability"]),
        "forecast_confidence": float(row["forecast_confidence"]),
        "top_reasons": top_reasons,
    }


# =============================================================================
# LOCAL DEVELOPMENT ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "dashboard.api:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )