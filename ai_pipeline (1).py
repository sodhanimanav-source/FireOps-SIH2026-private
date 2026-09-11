

import math
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest




STRATEGIC_ASSETS = [
    {"name": "Reliance Jamnagar Refinery Complex", "lat": 22.4707, "lng": 70.0577, "type": "Petroleum Refinery"},
    {"name": "IOCL Paradip Petrochemical Complex", "lat": 20.3164, "lng": 86.6114, "type": "Petrochemical Port"},
    {"name": "NTPC Singrauli Thermal Power Belt", "lat": 24.1997, "lng": 82.6644, "type": "Thermal Energy Hub"},
    {"name": "Nagothane Petrochemical Cluster", "lat": 18.5312, "lng": 73.1311, "type": "Chemical Asset"},
    {"name": "Visakhapatnam Steel and Petroleum Zone", "lat": 17.6868, "lng": 83.2185, "type": "Heavy Industry"},
    {"name": "Hazira LNG and Manufacturing Belt", "lat": 21.1523, "lng": 72.8258, "type": "Industrial Hub"},
    {"name": "Chennai Manali Petrochemical Zone", "lat": 13.1600, "lng": 80.2600, "type": "Petrochemical Plant"},
    {"name": "BPCL Kochi Refinery Complex", "lat": 9.9900, "lng": 76.3600, "type": "Oil Refinery"},
    {"name": "Sapugaskanda Refinery Complex (Sri Lanka)", "lat": 6.9654, "lng": 79.9328, "type": "Sri Lanka Refinery"},
    {"name": "Norochcholai Lakvijaya Power (Sri Lanka)", "lat": 8.0167, "lng": 79.7214, "type": "Thermal Power Complex"},
    {"name": "Hambantota Energy Port (Sri Lanka)", "lat": 6.1248, "lng": 81.1185, "type": "Maritime Energy Port"}
]




def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    
    R = 6371.0  
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def match_nearest_asset(lat: float, lng: float, buffer_km: float = 5.0):
    
    min_dist = float('inf')
    matched_asset = "None (Wildfire / Open Area)"
    is_industrial = False

    for asset in STRATEGIC_ASSETS:
        dist = calculate_haversine_distance(lat, lng, asset['lat'], asset['lng'])
        if dist < min_dist:
            min_dist = dist
            matched_asset = asset['name']

    if min_dist <= buffer_km:
        is_industrial = True

    return {
        "nearest_facility": matched_asset if is_industrial else "None (Wildfire / Open Area)",
        "distance_km": min_dist,
        "classification": "Industrial / Operational" if is_industrial else "Wildfire / Vegetation"
    }




class AnomalyDetector:
    def __init__(self, contamination: float = 0.08):
        self.model = IsolationForest(
            n_estimators=120,
            contamination=contamination,
            random_state=42
        )
        self.is_fitted = False

    def train_baseline(self, df: pd.DataFrame):
        
        features = df[['frp', 'brightness']]
        self.model.fit(features)
        self.is_fitted = True

    def score_telemetry(self, df: pd.DataFrame) -> pd.DataFrame:
        
        if not self.is_fitted:
            self.train_baseline(df)

        features = df[['frp', 'brightness']]
        raw_pred = self.model.predict(features)
        df['anomaly_score'] = self.model.decision_function(features)
        df['is_anomaly'] = (raw_pred == -1) | (df['frp'] > 85.0)

        
        def assign_threat(row):
            if row['frp'] >= 110.0 or (row['is_anomaly'] and row['frp'] >= 80.0):
                return 'CRITICAL'
            elif row['frp'] >= 50.0:
                return 'HIGH'
            else:
                return 'NORMAL'

        df['threat_level'] = df.apply(assign_threat, axis=1)
        return df




if __name__ == '__main__':
    print('=' * 75)
    print('  INDUSTRIAL FIRE & ANOMALY GIS - AI ENGINE DEMO')
    print('=' * 75)

    sample_records = [
        {'latitude': 22.4710, 'longitude': 70.0580, 'frp': 185.4, 'brightness': 365.2, 'satellite': 'VIIRS_NOAA20'},
        {'latitude': 22.4750, 'longitude': 70.0600, 'frp': 45.0,  'brightness': 325.0, 'satellite': 'MODIS_NRT'},
        {'latitude': 30.9000, 'longitude': 75.4000, 'frp': 65.0,  'brightness': 328.0, 'satellite': 'VIIRS_NOAA20'},
        {'latitude': 6.9660,  'longitude': 79.9330, 'frp': 142.8, 'brightness': 358.5, 'satellite': 'VIIRS_NOAA20'},
        {'latitude': 14.8000, 'longitude': 75.3000, 'frp': 25.0,  'brightness': 310.0, 'satellite': 'MODIS_NRT'},
    ]

    df = pd.DataFrame(sample_records)

    
    spatial_results = [match_nearest_asset(r['latitude'], r['longitude']) for _, r in df.iterrows()]
    df['classification'] = [s['classification'] for s in spatial_results]
    df['nearest_facility'] = [s['nearest_facility'] for s in spatial_results]
    df['distance_km'] = [s['distance_km'] for s in spatial_results]

    
    detector = AnomalyDetector()
    df = detector.score_telemetry(df)

    display_cols = ['classification', 'nearest_facility', 'distance_km', 'frp', 'is_anomaly', 'threat_level']
    print(df[display_cols].to_string(index=False))
    print('=' * 75)
    print('Pipeline Executed Successfully!')
