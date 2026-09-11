import random
import time
from typing import Dict, Any

def simulate_gee_extraction(lat: float, lng: float, roi_radius_km: float = 1.5) -> Dict[str, Any]:
    
    
    time.sleep(random.uniform(0.5, 1.5))
    
    
    delta_nbr = random.uniform(0.1, 0.8) 
    delta_swir = random.uniform(0.0, 1.0) 
    delta_ndvi = random.uniform(-0.6, -0.1) 
    
    return {
        "roi_bounds": {
            "lat_min": lat - (roi_radius_km / 111.0),
            "lat_max": lat + (roi_radius_km / 111.0),
            "lng_min": lng - (roi_radius_km / 111.0),
            "lng_max": lng + (roi_radius_km / 111.0),
        },
        "spectral_deltas": {
            "dNBR": delta_nbr,
            "dSWIR": delta_swir,
            "dNDVI": delta_ndvi
        },
        "cloud_cover_percent": random.uniform(0.0, 15.0)
    }

def run_ai_change_detection(satellite_data: Dict[str, Any], initial_confidence: float) -> Dict[str, Any]:
    
    time.sleep(random.uniform(0.2, 0.8))
    
    deltas = satellite_data["spectral_deltas"]
    
    
    burn_intensity = deltas["dNBR"] * 0.5 + deltas["dSWIR"] * 0.5
    
    
    final_confidence = (initial_confidence + burn_intensity) / 2.0
    
    
    final_confidence = min(max(final_confidence, 0.0), 1.0)
    
    
    spread_m = int(burn_intensity * 800) 
    
    return {
        "ai_confidence": final_confidence,
        "spatial_spread_m": spread_m,
        "mask_generated": True,
        "requires_hitl": final_confidence < 0.85 or spread_m > 200
    }
