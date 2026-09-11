def gate(f: dict) -> tuple[str, str] | None:
    
    
    
    if f["dist_industry_m"] > 1500 and f["dist_oilgas_m"] > 1500 and f["dist_mine_m"] > 1500:
        if f["lc_cropland"] > 0.35:
            return ("AGRICULTURAL_BURNING", "No industrial asset within 1.5 km; cropland dominant")
        elif f["lc_tree"] > 0.4:
            if f.get("frp", 0) > 40:
                return ("WILDFIRE", "High intensity signature in dense forest/shrub area.")
            return ("FOREST_FIRE", "No industrial asset within 1.5 km; forest/shrub dominant")
        else:
            return ("NON_INDUSTRIAL_FIRE", "No industrial asset within 1.5 km")

    
    if f.get("frp", 0) > 100:
        return ("FLARE_SPIKE", "Critical FRP anomaly detected; treating as severe event.")
    if f.get("frp", 0) > 60:
        return ("INDUSTRIAL_ACCIDENT", "High intensity thermal signature; potential asset accident.")

    if f["dist_oilgas_m"] < 1500 and f["days_active_90d"] >= 30 and f["night_ratio_90d"] >= 0.3:
        return ("GAS_FLARE", "Recurs on 30+ days near oil/gas asset, burns at night")
        
    if f["dist_mine_m"] < 1000 and f["days_active_90d"] >= 15 and f["frp"] < 15:
        return ("COAL_MINE_FIRE", "Low-FRP smoldering recurring inside mine/quarry area")
        
    return None
