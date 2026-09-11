import os
import json
import math

FACILITIES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "facilities.json")
_facilities = []
if os.path.exists(FACILITIES_PATH):
    try:
        with open(FACILITIES_PATH, 'r', encoding='utf-8') as f:
            _facilities = json.load(f)
    except Exception:
        pass

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def what_is_nearby(lat: float, lon: float, radius_m: int = 3000) -> dict:
    assets = []
    
    lat_thresh = (radius_m / 111000.0) * 1.5 
    lon_thresh = lat_thresh / max(0.1, math.cos(math.radians(lat)))
    
    for fac in _facilities:
        flat = fac.get("lat", 0)
        flng = fac.get("lng", 0)
        
        
        if abs(flat - lat) > lat_thresh or abs(flng - lon) > lon_thresh:
            continue
            
        dist = haversine(lat, lon, flat, flng) * 1000
        if dist <= radius_m:
            t = fac.get("type", "").lower()
            name = fac.get("name", "Unknown")
            if "refinery" in t or "oil" in t or "gas" in t or "petro" in t:
                kind = "refinery"
            elif "power" in t or "plant" in t:
                kind = "plant"
            elif "mine" in t or "quarry" in t:
                kind = "mine"
            else:
                kind = "industrial"
            assets.append({"kind": kind, "name": name, "operator": "Unknown", "dist_m": dist})
            
    assets.sort(key=lambda x: x["dist_m"])
    
    return {
        "has_industry": bool(assets),
        "has_refinery_or_oilgas": any(a["kind"] in ("refinery", "oil", "gas", "flare", "petroleum_well") for a in assets),
        "has_power_plant": any(a["kind"] == "plant" for a in assets),
        "has_mine": any(a["kind"] in ("quarry", "mine", "mineshaft") for a in assets),
        "assets": assets[:10]
    }
