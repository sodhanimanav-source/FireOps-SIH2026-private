import os
import pandas as pd

def main():
    osm_pbf = "data/india-latest.osm.pbf"
    out_parquet = "data/osm_industry_india.parquet"
    os.makedirs("data", exist_ok=True)
    
    if not os.path.exists(osm_pbf):
        print(f"Skipping OSM build: {osm_pbf} not found.")
        return

    try:
        from pyrosm import OSM
    except ImportError:
        print("pyrosm not installed.")
        return
        
    osm = OSM(osm_pbf)
    tags = {
        "landuse": ["industrial", "quarry"],
        "power": ["plant"],
        "man_made": ["works", "flare", "chimney", "petroleum_well", "mineshaft", "storage_tank"],
        "industrial": True
    }
    
    gdf = osm.get_data_by_custom_criteria(custom_filter=tags, keep_nodes=True, keep_ways=True, keep_relations=True)
    if gdf is None or gdf.empty:
        return
        
    gdf["geometry"] = gdf.centroid
    
    def assign_category(row):
        mm = str(row.get("man_made", ""))
        ind = str(row.get("industrial", ""))
        lu = str(row.get("landuse", ""))
        
        if mm in ["flare", "petroleum_well"] or ind in ["refinery", "oil", "gas", "lng"]:
            return "oilgas"
        if lu == "quarry" or mm == "mineshaft" or ind == "mine":
            return "mine"
        return "industry"
        
    gdf["category"] = gdf.apply(assign_category, axis=1)
    out_gdf = gdf[["category", "geometry"]].copy()
    out_gdf = out_gdf[~out_gdf.geometry.is_empty]
    out_gdf.to_parquet(out_parquet)

if __name__ == "__main__":
    main()
