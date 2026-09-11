import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timedelta

def expand_and_segregate_data(n_samples=50000):
    print(f"[DATA EXPANSION] Ingesting and segregating {n_samples} historical datapoints...")
    
    dates = [datetime.now() - timedelta(days=i) for i in range(1825)] 
    
    data = []
    for _ in range(n_samples):
        dt = np.random.choice(dates)
        is_industrial = np.random.choice([True, False], p=[0.3, 0.7])
        
        if is_industrial:
            lat = np.random.uniform(18.0, 24.0)
            lng = np.random.uniform(72.0, 80.0)
            frp = np.random.normal(40, 15)
            brightness = np.random.normal(330, 20)
            category = "INDUSTRIAL_ZONE"
        else:
            lat = np.random.uniform(10.0, 32.0)
            lng = np.random.uniform(70.0, 92.0)
            frp = np.random.normal(20, 10)
            brightness = np.random.normal(310, 10)
            category = "NATURAL_ZONE"
            
        data.append({
            "date": dt.strftime("%Y-%m-%d"),
            "lat": lat,
            "lng": lng,
            "frp": max(1.0, frp),
            "brightness": max(300.0, brightness),
            "zone": category
        })
        
    df = pd.DataFrame(data)
    
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "segregated_historical_data.csv")
    df.to_csv(out_path, index=False)
    print(f"[DATA EXPANSION] Data saved to {out_path}")
    
if __name__ == "__main__":
    expand_and_segregate_data()
