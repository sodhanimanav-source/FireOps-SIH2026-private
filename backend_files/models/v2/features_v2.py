import os
import math
import numpy as np
import logging
from math import floor
try:
    import pandas as pd
    import geopandas as gpd
    from sklearn.neighbors import BallTree
except ImportError:
    pass

try:
    import rasterio
    from rasterio.windows import from_bounds
except ImportError:
    pass

FEATURES = ["frp", "brightness", "is_night", "dist_industry_m", "dist_oilgas_m",
            "dist_mine_m", "lc_cropland", "lc_tree", "days_active_90d", "night_ratio_90d"]

class ContextBuilder:
    def __init__(self, osm_path="data/osm_industry_india.parquet", 
                 history_path="data/firms_india_history.parquet", 
                 worldcover_path="data/worldcover_india.tif"):
        self.osm_path = osm_path
        self.history_path = history_path
        self.worldcover_path = worldcover_path
        
        self.trees = {}
        self.history_active = {}
        self.history_night = {}
        
        
        if os.path.exists(osm_path):
            try:
                df = gpd.read_parquet(osm_path)
                for cat in ["industry", "oilgas", "mine"]:
                    cat_df = df[df["category"] == cat]
                    if not cat_df.empty:
                        coords = np.radians(np.vstack((cat_df.geometry.y, cat_df.geometry.x)).T)
                        self.trees[cat] = BallTree(coords, metric="haversine")
            except Exception as e:
                logging.warning(f"Failed to load OSM parquet: {e}")
        else:
            logging.warning(f"OSM index missing: {osm_path}. Run build_osm_index.py")

        
        if os.path.exists(history_path):
            try:
                hist_df = pd.read_parquet(history_path)
                hist_df["cell"] = hist_df.apply(lambda r: f"{floor(r.latitude/0.009)}_{floor(r.longitude/0.009)}", axis=1)
                
                grouped = hist_df.groupby("cell")
                self.history_active = grouped["acq_date"].nunique().to_dict()
                
                night_df = hist_df.copy()
                night_df["is_night"] = (night_df["daynight"] == "N").astype(int)
                self.history_night = night_df.groupby("cell")["is_night"].mean().to_dict()
            except Exception as e:
                logging.warning(f"Failed to load history parquet: {e}")
        else:
            logging.warning(f"History missing: {history_path}. Degraded history defaults.")

    def build(self, lat: float, lng: float, frp: float, brightness: float, daynight: str) -> dict:
        is_night = 1.0 if daynight == "N" else 0.0
        
        dist_industry_m = 99999.0
        dist_oilgas_m = 99999.0
        dist_mine_m = 99999.0
        
        query_pt = np.radians([[lat, lng]])
        
        if "industry" in self.trees:
            dist, _ = self.trees["industry"].query(query_pt, k=1)
            dist_industry_m = dist[0][0] * 6371000
        if "oilgas" in self.trees:
            dist, _ = self.trees["oilgas"].query(query_pt, k=1)
            dist_oilgas_m = dist[0][0] * 6371000
        if "mine" in self.trees:
            dist, _ = self.trees["mine"].query(query_pt, k=1)
            dist_mine_m = dist[0][0] * 6371000
            
        
        
        lc_cropland = 0.5
        lc_tree = 0.1
        if os.path.exists(self.worldcover_path):
            try:
                with rasterio.open(self.worldcover_path) as src:
                    window = from_bounds(lng - 0.0045, lat - 0.0045, lng + 0.0045, lat + 0.0045, src.transform)
                    arr = src.read(1, window=window)
                    if arr.size > 0:
                        lc_cropland = float((arr == 40).mean())
                        lc_tree = float(np.isin(arr, [10, 20]).mean())
            except Exception as e:
                logging.debug(f"Rasterio error: {e}")
                
        cell = f"{floor(lat/0.009)}_{floor(lng/0.009)}"
        days_active_90d = float(self.history_active.get(cell, 0))
        night_ratio_90d = float(self.history_night.get(cell, 0.0))
        
        result = {
            "frp": float(frp),
            "brightness": float(brightness),
            "is_night": is_night,
            "dist_industry_m": float(dist_industry_m),
            "dist_oilgas_m": float(dist_oilgas_m),
            "dist_mine_m": float(dist_mine_m),
            "lc_cropland": float(lc_cropland),
            "lc_tree": float(lc_tree),
            "days_active_90d": float(days_active_90d),
            "night_ratio_90d": float(night_ratio_90d)
        }
        
        assert "lat" not in result and "lng" not in result, "lat/lng must not be in features"
        return {k: result[k] for k in FEATURES}
