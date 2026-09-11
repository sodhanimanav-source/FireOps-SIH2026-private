from fastapi import APIRouter, Query
import pandas as pd
import json
from backend.state import state

router = APIRouter(prefix="/api/v1/regions")

@router.get("/summary")
def summary(level: str = Query("state", pattern="^(country|state|district|subdistrict)$"),
            parent: str | None = None, day_index: int | None = None, cumulative: bool = False):
    
    
    df = state.window_df(None if cumulative else day_index)
    if df.empty:
        return {"level": level, "parent": parent, "rows": []}
        
    if parent:
        parent_level = {"state": "country", "district": "state", "subdistrict": "district"}.get(level)
        if parent_level and parent_level in df.columns:
            df = df[df[parent_level] == parent]
            
    if level not in df.columns or df.empty:
        return {"level": level, "parent": parent, "rows": []}
        
    def get_classes(s):
        try:
            return s.value_counts().to_dict()
        except:
            return {}
            
    if "is_anomaly" not in df.columns:
        df["is_anomaly"] = df.get("predicted_class", "UNLABELED") != "UNLABELED"
    
    
    if "country" in df.columns:
        df = df[df["country"].notna()]
        
    
    df[level] = df[level].fillna("Unknown")
    
    if level == "subdistrict" and "district" in df.columns:
        df.loc[(df[level] == "Unknown") & (df["district"] == "Bathinda"), level] = "Talwandi Sabo"
        df.loc[df[level] == "Unknown", level] = df.loc[df[level] == "Unknown", "district"] + " (Rural)"

    g = df.groupby(level).agg(
        objects=("cluster_id", "nunique"), 
        anomalies=("is_anomaly", "sum"),
        frp_total=("frp_mean", "sum"), 
        max_m=("m_score", "max"),
        critical=("priority", lambda s: (s == "CRITICAL").sum()),
        classes=("predicted_class", get_classes),
        center_lat=("latitude", "mean"),
        center_lon=("longitude", "mean")
    ).reset_index().rename(columns={level: "name"})
    
    return {"level": level, "parent": parent, "rows": g.sort_values("anomalies", ascending=False).to_dict("records")}

@router.get("/choropleth")
def choropleth(level: str = "district", day_index: int | None = None):
    
    if level not in state.admin.layers:
        return {"type": "FeatureCollection", "features": []}
        
    gdf, _ = state.admin.layers[level]
    stats = summary(level=level, day_index=day_index)["rows"]
    
    if not stats:
        merged = gdf.copy()
        merged["anomalies"] = 0
    else:
        merged = gdf.merge(pd.DataFrame(stats), on="name", how="left").fillna(0)
        
    
    merged["geometry"] = merged.geometry.simplify(0.01)
    
    
    return json.loads(merged.to_json())

@router.get("/reverse")
def reverse(lat: float, lon: float):
    
    import requests
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        r = requests.get(url, headers={"User-Agent": "FireOpsCommand/4.0"}, timeout=2)
        if r.status_code == 200:
            return r.json().get("address", {})
    except:
        pass
    return {}
