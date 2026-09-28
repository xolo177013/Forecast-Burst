"""Live inference. Fixes: floor() region ids (match training), NaN-safe JSON, strict date-range
checks (no silent nearest-date snapping), KDTree ensemble join (same as Step 1), manual mode."""
import json, numpy as np, pandas as pd, xarray as xr, lightgbm as lgb
from pathlib import Path
from scipy.spatial import cKDTree

AREA=[37,68,6,98]; GRID=1.0; LEADS=list(range(24,241,24)); LEVELS=[500,850]
URL=dict(hres="gs://weatherbench2/datasets/hres/2016-2022-0012-1440x721.zarr",
         era5="gs://weatherbench2/datasets/era5/1959-2022-6h-1440x721.zarr",
         ens="gs://weatherbench2/datasets/ifs_ens/2018-2022-240x121_equiangular_with_poles_conservative.zarr")
FV={"total_precipitation_24hr":"forecast_precip","mean_sea_level_pressure":"forecast_mslp","2m_temperature":"forecast_t2m",
    "10m_u_component_of_wind":"forecast_u10","10m_v_component_of_wind":"forecast_v10"}
TV={k:v.replace("forecast","truth") for k,v in FV.items()}
_ds_cache, _m = {}, {}

def _ds(k):
    if k not in _ds_cache:
        _ds_cache[k]=xr.open_zarr(URL[k],chunks=None,consolidated=True,decode_timedelta=True,storage_options={"token":"anon"})
    return _ds_cache[k]
def _sub(ds):
    n,w,s,e=AREA; lat=ds["latitude"].values
    return ds.sel(latitude=slice(n,s) if lat[0]>lat[-1] else slice(s,n), longitude=slice(w%360,e%360))
def _rid(lat,lon):  # SAME as Step 1 (floor + epsilon)
    a,b=xr.broadcast(np.floor((lat+1e-8)/GRID).astype(int),np.floor((lon+1e-8)/GRID).astype(int))
    r=xr.apply_ufunc(lambda x,y:np.char.add(np.char.add(x.astype(str),"_"),y.astype(str)),a,b); r.name="region_id"; return r
def _reg(ds,names): return ds[names].groupby(_rid(ds["latitude"],ds["longitude"])).mean()

def _load(md):
    md=Path(md)
    if "clf" not in _m:
        meta=json.load(open(md/"model_metadata.json"))
        _m.update(clf=lgb.Booster(model_file=str(md/"bust_classifier.txt")),
                  reg=lgb.Booster(model_file=str(md/"error_regressor.txt")),
                  cols=meta["feature_cols"], thr=meta.get("operating_threshold",0.8))
        p=md/"hist_error_climatology.parquet"
        _m["clim"]=pd.read_parquet(p) if p.exists() else None
    return _m

def _add_time_feats(df,d):
    doy=d.dayofyear; df["doy_sin"]=np.sin(2*np.pi*doy/365.25); df["doy_cos"]=np.cos(2*np.pi*doy/365.25)
    df["is_monsoon_season"]=int(6<=d.month<=9)
    df["forecast_wind_speed_10m"]=np.hypot(df["forecast_u10"],df["forecast_v10"]); return df

def _clim(df,m):
    if m["clim"] is not None:
        df=df.merge(m["clim"],on=["region_id","lead_day"],how="left")
        return df.assign(hist_error_climatology=df["hist_error_climatology"].fillna(m["clim"]["hist_error_climatology"].mean()))
    return df.assign(hist_error_climatology=0.578)

def _predict(df,m):
    X=df.reindex(columns=m["cols"]).astype(float); X=X.fillna(X.median()).fillna(0)
    df["predicted_bust_probability"]=m["clf"].predict(X); df["predicted_confidence"]=1-df["predicted_bust_probability"]
    df["predicted_error_magnitude"]=m["reg"].predict(X); return df

def run_live_verification(init_date, model_dir, conf_df=None):
    d0=pd.Timestamp(init_date).normalize(); m=_load(model_dir); hres,era5,ens=_ds("hres"),_ds("era5"),_ds("ens")
    h0,h1=pd.Timestamp(hres.time.values[0]),pd.Timestamp(hres.time.values[-1])
    if not h0<=d0<=h1: raise ValueError(f"No forecast archive for {d0.date()} (available {h0.date()} to {h1.date()}).")
    lt=pd.to_timedelta(LEADS,unit="h")
    hs=_sub(hres).sel(time=[d0],prediction_timedelta=lt,method="nearest")
    df=_reg(hs,list(FV)).to_dataframe().reset_index().rename(columns=FV).rename(columns={"time":"init_date"})
    df["lead_hours"]=(df["prediction_timedelta"].dt.total_seconds()/3600).astype(int); df["lead_day"]=df["lead_hours"]//24
    df["valid_time"]=df["init_date"]+pd.to_timedelta(df["lead_hours"],unit="h")
    # synoptic (ERA5 at init time)
    ei=_sub(era5).sel(time=[d0],level=LEVELS)
    s=_reg(ei,["u_component_of_wind","v_component_of_wind"]).to_dataframe().reset_index()
    p=s.pivot_table(index="region_id",columns="level",values=["u_component_of_wind","v_component_of_wind"])
    p.columns=[f"{a}_{int(b)}" for a,b in p.columns]; p=p.reset_index()
    p["wind_shear_850_500hpa"]=np.hypot(p["u_component_of_wind_500"]-p["u_component_of_wind_850"],p["v_component_of_wind_500"]-p["v_component_of_wind_850"])
    p["wind_speed_500hpa"]=np.hypot(p["u_component_of_wind_500"],p["v_component_of_wind_500"])
    df=df.merge(p[["region_id","wind_shear_850_500hpa","wind_speed_500hpa"]],on="region_id",how="left")
    # ensemble spread (KDTree, like Step 1) if date inside ENS archive
    e0,e1=pd.Timestamp(ens.time.values[0]),pd.Timestamp(ens.time.values[-1])
    df["ensemble_spread_precip"]=np.nan
    if e0<=d0<=e1:
        es=_sub(ens).sel(time=[d0],prediction_timedelta=lt,method="nearest")
        sp=es["total_precipitation_24hr"].std(dim="number").to_dataframe(name="sp").reset_index()
        sp["lead_hours"]=(sp["prediction_timedelta"].dt.total_seconds()/3600).astype(int)
        pts=sp[["latitude","longitude"]].drop_duplicates().values; rids=df["region_id"].unique()
        cen=np.array([[int(r.split("_")[0])*GRID+GRID/2,int(r.split("_")[1])*GRID+GRID/2] for r in rids])
        ix=cKDTree(pts).query(cen)[1]
        mp=pd.DataFrame({"region_id":rids,"latitude":pts[ix,0],"longitude":pts[ix,1]}).merge(sp,on=["latitude","longitude"])
        df=df.drop(columns="ensemble_spread_precip").merge(mp[["region_id","lead_hours","sp"]].rename(columns={"sp":"ensemble_spread_precip"}),on=["region_id","lead_hours"],how="left")
    df=_predict(_clim(_add_time_feats(df,d0),m),m)
    df["lat_center"]=df["region_id"].str.split("_").str[0].astype(int)*GRID+GRID/2
    df["lon_center"]=df["region_id"].str.split("_").str[1].astype(int)*GRID+GRID/2
    # ---- verification (outcome side only; never fed to the model) ----
    df["actual_available"]=False; df["actual_bust"]=np.nan; df["actual_composite_error"]=np.nan
    val_start=None; in_val=False
    if conf_df is not None and len(conf_df):
        val_start=conf_df["init_date"].min(); sub=conf_df[conf_df["init_date"]==d0]
        in_val=len(sub)>0
        if in_val:
            a=sub[["region_id","lead_day","bust_label","composite_error"]].rename(columns={"bust_label":"ab","composite_error":"ac"})
            df=df.merge(a,on=["region_id","lead_day"],how="left")
            df["actual_available"]=df["ab"].notna(); df["actual_bust"]=df["ab"]; df["actual_composite_error"]=df["ac"]
    meta={"init_date":str(d0.date()),"held_out":bool(in_val),
          "training_period_warning":bool(val_start is not None and d0<val_start),
          "held_out_starts":str(val_start.date()) if val_start is not None else None,"operating_threshold":m["thr"]}
    cols=["region_id","lat_center","lon_center","lead_day","predicted_bust_probability","predicted_confidence",
          "predicted_error_magnitude","actual_available","actual_bust","actual_composite_error"]
    return meta,json.loads(df[cols].to_json(orient="records"))   # NaN -> null (safe JSON)

def predict_manual(feats,model_dir):
    """User-supplied feature snapshot -> Day1..10 bust curve (lead_day varied; other inputs held)."""
    m=_load(model_dir); rows=[]
    d=pd.Timestamp(feats["init_date"]) if feats.get("init_date") else None
    for ld in range(1,11):
        r={k:v for k,v in feats.items() if k!="init_date"}; r["lead_day"]=ld
        r["forecast_wind_speed_10m"]=r.get("forecast_wind_speed_10m",np.hypot(r.get("forecast_u10",0),r.get("forecast_v10",0)))
        if d is not None:
            r.update(doy_sin=np.sin(2*np.pi*d.dayofyear/365.25),doy_cos=np.cos(2*np.pi*d.dayofyear/365.25),is_monsoon_season=int(6<=d.month<=9))
        if "hist_error_climatology" not in r:
            c=m["clim"]; r["hist_error_climatology"]=float(c[c.lead_day==ld]["hist_error_climatology"].mean()) if c is not None else 0.578
        rows.append(r)
    df=_predict(pd.DataFrame(rows),m); t=m["thr"]
    return [{"lead_day":int(r.lead_day),"bust_probability":float(r.predicted_bust_probability),"confidence":float(r.predicted_confidence),
             "expected_error":float(r.predicted_error_magnitude),
             "risk":"High" if r.predicted_bust_probability>=t else "Moderate" if r.predicted_bust_probability>=t*0.7 else "Low"}
            for r in df.itertuples()]