import sys, os
sys.path.append(r"D:\SIH Competition\my web\backend_files")
import pandas as pd
from models.classifier import classify_hotspots


test_df = pd.DataFrame([
    {
        "latitude": 26.26633,
        "longitude": 74.18793,
        "frp": 12.5,
        "bright_ti4": 325.0,
        "acq_date": "2026-09-10",
        "acq_time": "1430"
    },
    {
        "latitude": 29.92161,
        "longitude": 74.95422,
        "frp": 18.0,
        "bright_ti4": 330.0,
        "acq_date": "2026-09-10",
        "acq_time": "1430"
    },
    {
        "latitude": 27.5,
        "longitude": 80.5,
        "frp": 10.0,
        "bright_ti4": 312.0,
        "acq_date": "2026-09-10",
        "acq_time": "1430"
    }
])

results = classify_hotspots(test_df)
print(f"Total results: {len(results)}")
for r in results:
    print(f"Point ({r['lat']}, {r['lng']}):")
    print(f"  Source Type: {r['source_type']}")
    print(f"  Label: {r['label']}")
    print(f"  Severity: {r['severity']}")
    print(f"  Confidence: {r['confidence_score']}")
    print(f"  Facility: {r['facility_name']}")
    print(f"  Reason: {r['reason']}")
    print("-" * 50)
