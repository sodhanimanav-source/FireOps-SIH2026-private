import os
import requests
import pandas as pd
from io import StringIO
from dotenv import load_dotenv

load_dotenv()

MAP_KEY = os.getenv("FIRMS_MAP_KEY", "").strip()
BBOX = "68,6,97,37"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "hotspots_backup.csv")

def fetch_firms_hotspots(day_range=5, sensor_choice="ALL"):
    if not MAP_KEY or len(MAP_KEY) < 20:
        if os.path.exists(CACHE_FILE):
            return pd.read_csv(CACHE_FILE)
        return pd.DataFrame()

    sensor_map = {
        "NOAA20": ["VIIRS_NOAA20_NRT"],
        "SNPP": ["VIIRS_SNPP_NRT"],
        "MODIS": ["MODIS_NRT"],
        "ALL": ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"]
    }

    active_sensors = sensor_map.get(sensor_choice, sensor_map["ALL"])
    collected = []

    for sensor in active_sensors:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sensor}/{BBOX}/{day_range}"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200 and "Invalid MAP_KEY" not in res.text:
                df = pd.read_csv(StringIO(res.text.strip()))
                if not df.empty and "latitude" in df.columns:
                    if "bright_ti4" not in df.columns and "brightness" in df.columns:
                        df["bright_ti4"] = df["brightness"]
                    if "frp" not in df.columns:
                        df["frp"] = 5.0
                    df["sensor_source"] = sensor
                    collected.append(df)
        except Exception as e:
            print(f"[WARN] {sensor} fetch failed: {e}")
            continue

    if collected:
        combined = pd.concat(collected, ignore_index=True)
        combined = combined.drop_duplicates(subset=["latitude", "longitude", "acq_date"])
        return combined

    if os.path.exists(CACHE_FILE):
        return pd.read_csv(CACHE_FILE)
    return pd.DataFrame()