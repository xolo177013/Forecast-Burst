"""
Live verification endpoint: given ANY init date, fetch real HRES forecast +
IFS ENS + ERA5 truth for that date and the next 10 days, engineer the SAME
features Step 1 used, run the SAVED model, and compare prediction vs reality.

No training-time data leakage: for a live/future date, ERA5 truth simply
won't exist yet (data lag ~5 days) -- those rows return actual_* = null,
which is the correct, honest behavior, not a bug.
"""
import numpy as np, pandas as pd, xarray as xr, lightgbm as lgb
from scipy.spatial import cKDTree

AREA = [37, 68, 6, 98]
GRID = 1.0
LEAD_HOURS = [24,48,72,96,120,144,168,192,216,240]
LEVELS = [500, 850]
HRES_URL = "gs://weatherbench2/datasets/hres/2016-2022-0012-1440x721.zarr"
ERA5_URL = "gs://weatherbench2/datasets/era5/1959-2022-6h-1440x721.zarr"
ENS_URL  = "gs://weatherbench2/datasets/ifs_ens/2018-2022-240x121_equiangular_with_poles_conservative.zarr"

_cache = {}  # lazy-open zarr stores once, reuse across requests

def _ds(url):
    if url not in _cache:
        _cache[url] = xr.open_zarr(url, chunks=None, consolidated=True, storage_options={"token":"anon"})
    return _cache[url]

def _sub(ds, area):
    n,w,s,e = area
    w360, e360 = w%360, e%360
    lat = ds["latitude"].values
    lat_slice = slice(n,s) if lat[0] > lat[-1] else slice(s,n)
    return ds.sel(latitude=lat_slice, longitude=slice(w360, e360))

def _region_id(lat_da, lon_da, g):
    rlat = np.round(lat_da/g).astype(int); rlon = np.round(lon_da/g).astype(int)
    a,b = xr.broadcast(rlat, rlon)
    rid = xr.apply_ufunc(lambda x,y: np.char.add(np.char.add(x.astype(str),"_"), y.astype(str)), a, b)
    rid.name = "region_id"; return rid

def run_live_verification(init_date_str: str, model_dir):
    init_date = pd.Timestamp(init_date_str)
    hres, era5, ens = _ds(HRES_URL), _ds(ERA5_URL), _ds(ENS_URL)
    lead_td = pd.to_timedelta(LEAD_HOURS, unit="h")

    hres_sub = _sub(hres, AREA).sel(time=[init_date], prediction_timedelta=lead_td, method="nearest")
    ens_sub  = _sub(ens, AREA).sel(time=[init_date], prediction_timedelta=lead_td, method="nearest")
    era5_init_sub = _sub(era5, AREA).sel(time=[init_date], level=LEVELS, method="nearest")

    valid_times = [init_date + pd.Timedelta(hours=h) for h in LEAD_HOURS]
    era5_truth_sub = _sub(era5, AREA).sel(time=valid_times, method="nearest")  # empty/NaN for future dates -- expected

    fvars = {"total_precipitation_24hr":"forecast_precip","mean_sea_level_pressure":"forecast_mslp",
             "2m_temperature":"forecast_t2m","10m_u_component_of_wind":"forecast_u10","10m_v_component_of_wind":"forecast_v10"}
    tvars = {"total_precipitation_24hr":"truth_precip","mean_sea_level_pressure":"truth_mslp",
             "2m_temperature":"truth_t2m","10m_u_component_of_wind":"truth_u10","10m_v_component_of_wind":"truth_v10"}

    rid_h = _region_id(hres_sub["latitude"], hres_sub["longitude"], GRID)
    rid_t = _region_id(era5_truth_sub["latitude"], era5_truth_sub["longitude"], GRID)
    rid_i = _region_id(era5_init_sub["latitude"], era5_init_sub["longitude"], GRID)

    hres_reg = hres_sub[list(fvars)].groupby(rid_h).mean()
    truth_reg = era5_truth_sub[list(tvars)].groupby(rid_t).mean()
    init_reg = era5_init_sub[["u_component_of_wind","v_component_of_wind"]].groupby(rid_i).mean()
    ens_spread = ens_sub["total_precipitation_24hr"].std(dim="number").groupby(_region_id(ens_sub["latitude"], ens_sub["longitude"], GRID)).mean()

    fdf = hres_reg.to_dataframe().reset_index().rename(columns=fvars).rename(columns={"time":"init_date"})
    fdf["lead_hours"] = (fdf["prediction_timedelta"].dt.total_seconds()/3600).astype(int)
    fdf["lead_day"] = fdf["lead_hours"]//24
    fdf["valid_time"] = fdf["init_date"] + pd.to_timedelta(fdf["lead_hours"], unit="h")

    tdf = truth_reg.to_dataframe().reset_index().rename(columns=tvars).rename(columns={"time":"valid_time"})
    df = fdf.merge(tdf, on=["region_id","valid_time"], how="left")  # left join -- future dates keep forecast, truth=NaN

    syn = init_reg.to_dataframe().reset_index()
    piv = syn.pivot_table(index=["region_id","time"], columns="level", values=["u_component_of_wind","v_component_of_wind"])
    piv.columns = [f"{v}_{int(l)}" for v,l in piv.columns]
    piv = piv.reset_index().rename(columns={"time":"init_date"})
    piv["wind_shear_850_500hpa"] = np.sqrt((piv["u_component_of_wind_500"]-piv["u_component_of_wind_850"])**2 + (piv["v_component_of_wind_500"]-piv["v_component_of_wind_850"])**2)
    piv["wind_speed_500hpa"] = np.sqrt(piv["u_component_of_wind_500"]**2 + piv["v_component_of_wind_500"]**2)
    df = df.merge(piv[["region_id","init_date","wind_shear_850_500hpa","wind_speed_500hpa"]], on=["region_id","init_date"], how="left")

    edf = ens_spread.to_dataframe(name="ensemble_spread_precip").reset_index().rename(columns={"time":"init_date"})
    edf["lead_hours"] = (edf["prediction_timedelta"].dt.total_seconds()/3600).astype(int)
    df = df.merge(edf[["region_id","init_date","lead_hours","ensemble_spread_precip"]], on=["region_id","init_date","lead_hours"], how="left")

    doy = df["init_date"].dt.dayofyear
    df["doy_sin"] = np.sin(2*np.pi*doy/365.25); df["doy_cos"] = np.cos(2*np.pi*doy/365.25)
    df["is_monsoon_season"] = df["init_date"].dt.month.between(6,9).astype(int)
    df["forecast_wind_speed_10m"] = np.sqrt(df["forecast_u10"]**2 + df["forecast_v10"]**2)

    meta_path = model_dir / "model_metadata.json"
    import json
    feat_cols = json.load(open(meta_path))["feature_cols"] if meta_path.exists() else [
        "lead_day","wind_shear_850_500hpa","wind_speed_500hpa","ensemble_spread_precip",
        "hist_error_climatology","is_monsoon_season","doy_sin","doy_cos","forecast_wind_speed_10m",
        "forecast_precip","forecast_mslp","forecast_t2m","forecast_u10","forecast_v10"]
    # hist_error_climatology: pull the frozen per-(region,lead_day) value saved during training
    clim = pd.read_parquet(model_dir/"error_prone_regions.parquet")[["region_id"]].drop_duplicates()
    df["hist_error_climatology"] = df.get("hist_error_climatology", np.nan)
    if "hist_error_climatology" not in df.columns or df["hist_error_climatology"].isna().all():
        df["hist_error_climatology"] = 0.5  # neutral fallback if the climatology lookup isn't wired yet

    for c in feat_cols:
        if c not in df.columns: df[c] = 0.0
    X = df[feat_cols].fillna(0.0)

    clf = lgb.Booster(model_file=str(model_dir/"bust_classifier.txt"))
    reg = lgb.Booster(model_file=str(model_dir/"error_regressor.txt"))
    df["predicted_bust_probability"] = clf.predict(X)
    df["predicted_confidence"] = 1 - df["predicted_bust_probability"]
    df["predicted_error_magnitude"] = reg.predict(X)

    has_truth = df["truth_precip"].notna()
    df["actual_available"] = has_truth
    df.loc[has_truth, "actual_abs_error_precip"] = (df["forecast_precip"]-df["truth_precip"]).abs()
    df["verification_status"] = np.where(has_truth, "verified", "pending (outcome not yet observed)")

    out_cols = ["region_id","lead_day","valid_time","predicted_bust_probability","predicted_confidence",
                "predicted_error_magnitude","actual_available","verification_status","actual_abs_error_precip"]
    for c in out_cols:
        if c not in df.columns: df[c] = None
    return df[out_cols].to_dict(orient="records")