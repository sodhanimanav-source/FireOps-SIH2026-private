def classify(p: dict, near: dict, spread: int) -> tuple[str, str]:
    rr = p.get("recurrence_rate", 0)
    nr = p.get("night_ratio", 0)
    sr = p.get("spike_ratio") or 1
    
    if near.get("has_refinery_or_oilgas") and rr >= 0.4 and nr >= 0.3:
        if sr > 4:  return "FLARE_SPIKE", f"Persistent flare ({p['days_active']} days) with {sr:.1f}x FRP spike"
        return "ROUTINE_FLARING", f"Burns {p['days_active']} days, {nr:.0%} at night, oil/gas asset within 1 km"
    
    if near.get("has_power_plant") and rr >= 0.3:
        return "ROUTINE_FLARING", "Recurring heat co-located with power/steel plant"
        
    if near.get("has_mine") and rr >= 0.2 and p.get("frp_median", 0) < 15:
        return "COAL_MINE_FIRE", f"Low-FRP smoldering for {p['days_active']} days inside mine area"
        
    if near.get("has_industry") and (p.get("is_new") or (rr < 0.1 and sr > 4)):
        return "INDUSTRIAL_ACCIDENT", "First-time / sudden high heat in an industrial zone with no history"
        
    if not near.get("has_industry") and spread >= 3:
        return "WILDFIRE", f"Fire spread to {spread} neighbouring cells"
        
    if not near.get("has_industry") and p.get("days_active", 0) <= 3 and nr < 0.2:
        return "AGRICULTURAL_BURNING", "Short daytime burn on non-industrial land"
        
    return "UNCLASSIFIED", "No dominant pattern"
