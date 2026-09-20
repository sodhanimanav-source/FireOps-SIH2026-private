import json
import os
import requests
import time

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "facilities.json")


CORE_MAJOR_ASSETS = [
    {"name": "Jamnagar Refinery Complex (Reliance)", "type": "Oil & Gas Refinery", "lat": 22.3562, "lng": 69.8686, "buffer_km": 5.0, "baseline_frp": 65.0},
    {"name": "Mundra Thermal Power Station (Adani/Tata)", "type": "Thermal Power", "lat": 22.8242, "lng": 69.5298, "buffer_km": 4.0, "baseline_frp": 45.0},
    {"name": "Bhilai Steel Plant (SAIL)", "type": "Iron & Steel", "lat": 21.1834, "lng": 81.3857, "buffer_km": 4.5, "baseline_frp": 50.0},
    {"name": "Rourkela Steel Plant (SAIL)", "type": "Iron & Steel", "lat": 22.2289, "lng": 84.8728, "buffer_km": 4.5, "baseline_frp": 50.0},
    {"name": "Tata Steel Jamshedpur", "type": "Iron & Steel", "lat": 22.7925, "lng": 86.1950, "buffer_km": 4.5, "baseline_frp": 55.0},
    {"name": "Numaligarh Refinery (NRL)", "type": "Oil & Gas Refinery", "lat": 26.5684, "lng": 93.7719, "buffer_km": 3.5, "baseline_frp": 35.0},
    {"name": "Mangalore Refinery and Petrochemicals (MRPL)", "type": "Oil & Gas Refinery", "lat": 12.9934, "lng": 74.8322, "buffer_km": 4.0, "baseline_frp": 40.0},
    {"name": "Kochi Refinery (BPCL)", "type": "Oil & Gas Refinery", "lat": 9.9577, "lng": 76.3601, "buffer_km": 4.0, "baseline_frp": 40.0},
    {"name": "Paradip Refinery (IOCL)", "type": "Oil & Gas Refinery", "lat": 20.2644, "lng": 86.6433, "buffer_km": 4.5, "baseline_frp": 55.0},
    {"name": "NTPC Vindhyachal Super Thermal", "type": "Thermal Power", "lat": 24.1006, "lng": 82.6719, "buffer_km": 4.0, "baseline_frp": 45.0},
    {"name": "NTPC Singrauli Thermal", "type": "Thermal Power", "lat": 24.1200, "lng": 82.7100, "buffer_km": 3.5, "baseline_frp": 40.0},
    {"name": "NTPC Ramagundam", "type": "Thermal Power", "lat": 18.7564, "lng": 79.4526, "buffer_km": 3.5, "baseline_frp": 40.0},
    {"name": "NTPC Talcher Super Thermal", "type": "Thermal Power", "lat": 20.9500, "lng": 85.0500, "buffer_km": 4.0, "baseline_frp": 40.0},
    {"name": "NTPC Korba Super Thermal", "type": "Thermal Power", "lat": 22.3850, "lng": 82.6820, "buffer_km": 3.5, "baseline_frp": 40.0},
    {"name": "JSW Steel Vijayanagar", "type": "Iron & Steel", "lat": 15.1764, "lng": 76.6719, "buffer_km": 5.0, "baseline_frp": 55.0},
    {"name": "Durgapur Steel Plant", "type": "Iron & Steel", "lat": 23.5500, "lng": 87.2800, "buffer_km": 4.0, "baseline_frp": 45.0},
    {"name": "Bokaro Steel Plant", "type": "Iron & Steel", "lat": 23.6700, "lng": 86.1500, "buffer_km": 4.5, "baseline_frp": 45.0},
    {"name": "Vizag Steel (RINL)", "type": "Iron & Steel", "lat": 17.6322, "lng": 83.1819, "buffer_km": 4.5, "baseline_frp": 50.0},
    {"name": "IOCL Panipat Refinery & Petrochem", "type": "Petrochemical", "lat": 29.4600, "lng": 76.9200, "buffer_km": 4.5, "baseline_frp": 45.0},
    {"name": "IOCL Mathura Refinery", "type": "Oil & Gas Refinery", "lat": 27.4200, "lng": 77.6800, "buffer_km": 3.5, "baseline_frp": 35.0},
    {"name": "IOCL Vadodara (Gujarat Refinery)", "type": "Oil & Gas Refinery", "lat": 22.3600, "lng": 73.1300, "buffer_km": 4.0, "baseline_frp": 40.0},
    {"name": "HPCL Mittal Energy Bathinda Refinery", "type": "Oil & Gas Refinery", "lat": 29.9800, "lng": 75.0200, "buffer_km": 4.0, "baseline_frp": 40.0},
    {"name": "Hazira Industrial & LNG Terminal", "type": "Petrochemical / LNG", "lat": 21.1100, "lng": 72.6500, "buffer_km": 5.0, "baseline_frp": 50.0},
    {"name": "Dahej Petrochemical Complex", "type": "Chemical Hub", "lat": 21.7100, "lng": 72.5800, "buffer_km": 5.0, "baseline_frp": 45.0},
    {"name": "Ankleshwar GIDC Chemical Zone", "type": "Chemical Hub", "lat": 21.6300, "lng": 73.0100, "buffer_km": 4.0, "baseline_frp": 35.0}
]

ZONES = [
    {"name": "West (Gujarat/Maharashtra)", "bbox": (15.0, 68.0, 24.5, 76.0)},
    {"name": "North (NCR/Punjab/Rajasthan/UP)", "bbox": (24.5, 70.0, 32.5, 82.0)},
    {"name": "East (WB/Odisha/Jharkhand)", "bbox": (20.0, 82.0, 27.5, 90.0)},
    {"name": "South (Tamil Nadu/Karnataka/AP/Telangana)", "bbox": (8.0, 74.0, 19.5, 84.0)},
    {"name": "Central (MP/Chhattisgarh)", "bbox": (19.5, 76.0, 25.0, 83.5)}
]

def fetch_zone_facilities(bbox):
    s, w, n, e = bbox

    # NOTE: this query body was truncated in an earlier commit, leaving the
    # module unparseable and the whole `ingestion` package un-importable.
    # Restored to select the heavy-industry features this database is built
    # from, across nodes, ways and relations.
    query = f"""
    [out:json][timeout:60];
    (
      node["man_made"~"works|petroleum_well|storage_tank|flare"]({s},{w},{n},{e});
      way["man_made"~"works|petroleum_well|storage_tank|flare"]({s},{w},{n},{e});
      way["landuse"="industrial"]({s},{w},{n},{e});
      way["industrial"]({s},{w},{n},{e});
      way["power"~"plant|generator"]({s},{w},{n},{e});
      relation["landuse"="industrial"]({s},{w},{n},{e});
      relation["industrial"]({s},{w},{n},{e});
    );
    out center tags;
    """
    url = "https://overpass-api.de/api/interpreter"
    try:
        res = requests.post(url, data={"data": query}, headers={"User-Agent": "IndustrialMonitorBot/3.0"}, timeout=35)
        if res.status_code == 200:
            return res.json().get("elements", [])
    except Exception as e:
        print(f"  [WARN] Request failed for bbox: {e}")
    return []

def build_complete_facility_database():
    print("[INFO] Building full industrial facility database (OSM Areas + Core Heavy Assets)...")
    all_facilities = []
    seen_coords = set()

    
    for idx, asset in enumerate(CORE_MAJOR_ASSETS):
        coord_key = (round(asset["lat"], 2), round(asset["lng"], 2))
        seen_coords.add(coord_key)
        all_facilities.append({
            "id": f"CORE_FAC_{idx+1:03d}",
            "name": asset["name"],
            "type": asset["type"],
            "lat": asset["lat"],
            "lng": asset["lng"],
            "buffer_km": asset["buffer_km"],
            "baseline_frp": asset["baseline_frp"]
        })

    
    for zone in ZONES:
        print(f"[INFO] Fetching {zone['name']}...")
        elements = fetch_zone_facilities(zone["bbox"])
        added = 0
        for el in elements:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if not lat or not lon:
                continue

            coord_key = (round(lat, 2), round(lon, 2))
            if coord_key in seen_coords:
                continue
            seen_coords.add(coord_key)

            tags = el.get("tags", {})
            name = tags.get("name", tags.get("operator", tags.get("description", tags.get("name:en"))))
            if not name:
                # Also truncated in the same commit.
                name = f"{zone['name'].split()[0]} Industrial Cluster {el.get('id')}"

            raw_type = tags.get("industrial", tags.get("plant:source", tags.get("power", tags.get("landuse", "Industrial Facility"))))
            plant_type = str(raw_type).replace("_", " ").capitalize()

            all_facilities.append({
                "id": f"OSM_{el['type'][0].upper()}_{el['id']}",
                "name": str(name),
                "type": plant_type,
                "lat": round(lat, 5),
                "lng": round(lon, 5),
                "buffer_km": 4.5,
                "baseline_frp": 35.0
            })
            added += 1
            
        print(f" -> Added {added} real facilities from {zone['name']}")
        time.sleep(1)

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(all_facilities, f, indent=2, ensure_ascii=False)

    print(f"\n[SUCCESS] Total {len(all_facilities)} real heavy industrial sites saved to data/facilities.json!")

if __name__ == "__main__":
    build_complete_facility_database()