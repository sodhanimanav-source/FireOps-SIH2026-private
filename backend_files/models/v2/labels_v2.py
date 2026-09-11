from .gate import gate

def weak_label(f: dict) -> str | None:
    g = gate(f)
    if g is not None:
        return g[0]
        
    if f["dist_oilgas_m"] < 1500 and f["days_active_90d"] >= 20:
        return "GAS_FLARE"
    if f["dist_industry_m"] < 800 and f["days_active_90d"] <= 2 and f["frp"] > 20:
        return "INDUSTRIAL_ACCIDENT"
    if f["dist_industry_m"] < 800 and f["days_active_90d"] >= 20:
        return "INDUSTRIAL_PERSISTENT"
    if f["lc_cropland"] > 0.5 and f["days_active_90d"] <= 3:
        return "AGRICULTURAL_BURNING"
    if f["lc_tree"] > 0.5:
        return "FOREST_FIRE"
        
    return None
