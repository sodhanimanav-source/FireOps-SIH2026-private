def classify_hotspot(is_near_facility: bool, is_historical: bool, land_cover: str) -> str:
    
    if is_near_facility and not is_historical:
        return "Industrial Anomaly / Possible Accident"
    
    
    elif is_near_facility and is_historical:
        return "Persistent Industrial Source"
    
    
    elif land_cover == "cropland":
        return "Agricultural Burning"
    
    
    elif land_cover in ["forest", "shrubland"]:
        return "Wildfire / Forest Fire"
    
    return "Unclassified Hotspot"