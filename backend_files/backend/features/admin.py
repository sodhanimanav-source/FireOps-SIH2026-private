
from dataclasses import dataclass
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point
from shapely.strtree import STRtree
import pandas as pd

ADM_FILES = {
    "country": "data/admin/geoBoundaries-IND-ADM0.geojson",
    "state": "data/admin/geoBoundaries-IND-ADM1.geojson",
    "district": "data/admin/geoBoundaries-IND-ADM2.geojson",
    "subdistrict": "data/admin/geoBoundaries-IND-ADM3.geojson",
}

@dataclass(frozen=True)
class AdminTags:
    country: str | None
    state: str | None
    district: str | None
    subdistrict: str | None

class AdminIndex:
    def __init__(self, files: dict[str, str] = ADM_FILES):
        self.layers = {}
        for level, path in files.items():
            if not Path(path).exists():
                print(f"[AdminIndex] Missing {level} boundaries: {path}")
                continue
            print(f"[AdminIndex] Loading {level} boundaries from {path}...")
            gdf = gpd.read_file(path)[["shapeName", "geometry"]].rename(columns={"shapeName": "name"})
            self.layers[level] = (gdf, STRtree(gdf.geometry.values))

    def _lookup(self, level: str, p: Point) -> str | None:
        if level not in self.layers:
            return None
        gdf, tree = self.layers[level]
        for i in tree.query(p, predicate="within"):
            return str(gdf.name.iloc[i])
        return None

    def tag(self, lat: float, lon: float) -> AdminTags:
        p = Point(lon, lat)
        return AdminTags(*(self._lookup(l, p) for l in ("country", "state", "district", "subdistrict")))

    def tag_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        
        if df.empty:
            for level in ADM_FILES:
                df[level] = None
            return df
            
        pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude), crs="EPSG:4326")
        for level, (gdf, _) in self.layers.items():
            joined = gpd.sjoin(pts[["geometry"]], gdf.set_crs("EPSG:4326"), how="left", predicate="within")
            df[level] = joined.groupby(level=0).name.first().values
            
        
        for level in ADM_FILES:
            if level not in df.columns:
                df[level] = None
                
        return df
