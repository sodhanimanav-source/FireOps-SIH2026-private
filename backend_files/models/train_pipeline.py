import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import classification_report
import joblib
import os

MODEL_DIR = os.path.dirname(__file__)

CLASSES = [
    "INDUSTRIAL_FIRE",
    "GAS_FLARE",
    "AGRICULTURAL_BURNING",
    "MINING_ACTIVITY",
    "WILDFIRE",
    "PERSISTENT_THERMAL",
]

def generate_synthetic_training_data(n_samples=6000):
    
    np.random.seed(42)
    
    
    n1 = int(n_samples * 0.12)
    d1 = {
        'frp': np.random.normal(120, 35, n1).clip(70, 300),
        'brightness': np.random.normal(380, 20, n1).clip(350, 500),
        'distance': np.random.uniform(0.1, 4.0, n1),
        'hour': np.random.randint(0, 24, n1),
        'persistence': np.random.randint(1, 3, n1),  
        'land_cover': np.full(n1, 4),  
    }
    
    
    n2 = int(n_samples * 0.18)
    d2 = {
        'frp': np.random.normal(40, 12, n2).clip(15, 80),
        'brightness': np.random.normal(340, 12, n2).clip(310, 370),
        'distance': np.random.uniform(0.1, 3.0, n2),
        'hour': np.random.randint(0, 24, n2),
        'persistence': np.random.randint(10, 365, n2),  
        'land_cover': np.full(n2, 4),  
    }
    
    
    n3 = int(n_samples * 0.22)
    d3 = {
        'frp': np.random.normal(12, 6, n3).clip(2, 30),
        'brightness': np.random.normal(312, 8, n3).clip(298, 335),
        'distance': np.random.uniform(8.0, 80.0, n3),
        'hour': np.random.randint(9, 17, n3),  
        'persistence': np.random.randint(1, 5, n3),  
        'land_cover': np.full(n3, 1),  
    }
    
    
    n4 = int(n_samples * 0.10)
    d4 = {
        'frp': np.random.normal(30, 10, n4).clip(10, 60),
        'brightness': np.random.normal(328, 10, n4).clip(310, 355),
        'distance': np.random.uniform(5.0, 40.0, n4),
        'hour': np.random.randint(8, 20, n4),
        'persistence': np.random.randint(30, 365, n4),  
        'land_cover': np.full(n4, 3),  
    }
    
    
    n5 = int(n_samples * 0.20)
    d5 = {
        'frp': np.random.normal(65, 30, n5).clip(15, 200),
        'brightness': np.random.normal(355, 20, n5).clip(320, 420),
        'distance': np.random.uniform(15.0, 100.0, n5),
        'hour': np.random.randint(0, 24, n5),
        'persistence': np.random.randint(1, 14, n5),
        'land_cover': np.full(n5, 2),  
    }
    
    
    n6 = n_samples - (n1 + n2 + n3 + n4 + n5)
    d6 = {
        'frp': np.random.normal(45, 10, n6).clip(20, 75),
        'brightness': np.random.normal(335, 8, n6).clip(315, 360),
        'distance': np.random.uniform(0.2, 5.0, n6),
        'hour': np.random.randint(0, 24, n6),
        'persistence': np.random.randint(100, 365, n6),  
        'land_cover': np.full(n6, 4),  
    }
    
    labels = (
        ["INDUSTRIAL_FIRE"] * n1 +
        ["GAS_FLARE"] * n2 +
        ["AGRICULTURAL_BURNING"] * n3 +
        ["MINING_ACTIVITY"] * n4 +
        ["WILDFIRE"] * n5 +
        ["PERSISTENT_THERMAL"] * n6
    )
    
    all_data = {}
    for key in ['frp', 'brightness', 'distance', 'hour', 'persistence', 'land_cover']:
        all_data[key] = np.concatenate([d1[key], d2[key], d3[key], d4[key], d5[key], d6[key]])
    
    X = np.column_stack([all_data[k] for k in ['frp', 'brightness', 'distance', 'hour', 'persistence', 'land_cover']])
    return X, labels


def train_and_save_pipeline():
    print("[AI PIPELINE] Training 6-class fire classification models...")
    X, y = generate_synthetic_training_data()
    
    
    idx = np.random.permutation(len(y))
    X = X[idx]
    y = [y[i] for i in idx]
    
    
    split = int(len(y) * 0.8)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]
    
    
    clf = RandomForestClassifier(n_estimators=150, max_depth=12, random_state=42, class_weight='balanced')
    clf.fit(X_train, y_train)
    
    
    y_pred = clf.predict(X_val)
    print("\n[AI PIPELINE] Classification Report:")
    print(classification_report(y_val, y_pred))
    
    accuracy = sum(1 for a, b in zip(y_val, y_pred) if a == b) / len(y_val)
    print(f"[AI PIPELINE] Validation Accuracy: {accuracy*100:.1f}%")
    
    
    iso = IsolationForest(n_estimators=120, contamination=0.08, random_state=42)
    iso.fit(X_train)
    
    
    joblib.dump(clf, os.path.join(MODEL_DIR, "fire_classifier_rf.pkl"))
    joblib.dump(iso, os.path.join(MODEL_DIR, "anomaly_detector_iso.pkl"))
    
    
    import json
    meta = {
        "model_type": "RandomForestClassifier + IsolationForest",
        "n_estimators_rf": 150,
        "n_estimators_iso": 120,
        "classes": CLASSES,
        "features": ["frp", "brightness", "distance_to_facility", "hour", "persistence_days", "land_cover_code"],
        "training_samples": len(y_train),
        "validation_accuracy": round(accuracy * 100, 1),
        "feature_importances": {
            name: round(float(imp), 4)
            for name, imp in zip(
                ["frp", "brightness", "distance_to_facility", "hour", "persistence_days", "land_cover_code"],
                clf.feature_importances_
            )
        },
    }
    with open(os.path.join(MODEL_DIR, "model_metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)
    
    print("[AI PIPELINE] ✅ 6-class models + metadata saved to models/")


if __name__ == "__main__":
    train_and_save_pipeline()
