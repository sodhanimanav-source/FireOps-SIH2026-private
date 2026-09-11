import os
import numpy as np
import joblib
from sklearn.ensemble import GradientBoostingClassifier

MODEL_DIR = os.path.dirname(__file__)
RISK_MODEL_PATH = os.path.join(MODEL_DIR, "risk_escalation_gb.pkl")


def train_risk_model():
    
    print("[AI PIPELINE] Training Risk Escalation Model (GradientBoosting)...")
    np.random.seed(42)
    
    n = 4000
    frp = np.random.uniform(5, 250, n)
    brightness = np.random.uniform(300, 450, n)
    distance = np.random.uniform(0.1, 100, n)
    anomaly_score = np.random.uniform(-0.5, 0.5, n)
    persistence = np.random.randint(1, 365, n)
    
    
    escalation_prob = (
        (frp / 250) * 0.4 +
        ((450 - brightness) / 150) * 0.1 +  
        (1 / (distance + 1)) * 0.2 +
        ((0.5 - anomaly_score)) * 0.2 +
        (persistence / 365) * 0.1
    )
    will_escalate = (escalation_prob > 0.45).astype(int)
    
    X = np.column_stack([frp, brightness, distance, anomaly_score, persistence])
    
    model = GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=42)
    model.fit(X, will_escalate)
    
    acc = model.score(X, will_escalate)
    print(f"[AI PIPELINE] Risk Model Training Accuracy: {acc*100:.1f}%")
    
    joblib.dump(model, RISK_MODEL_PATH)
    print(f"[AI PIPELINE] ✅ Risk escalation model saved to {RISK_MODEL_PATH}")
    return model


def predict_escalation(hotspots_data):
    
    if not os.path.exists(RISK_MODEL_PATH):
        return hotspots_data
    
    model = joblib.load(RISK_MODEL_PATH)
    
    for h in hotspots_data:
        try:
            X = np.array([[
                h.get("frp", 10),
                h.get("brightness", 310),
                h.get("distance_km", 50) or 50,
                h.get("anomaly_score", 0),
                1,  
            ]])
            prob = model.predict_proba(X)[0]
            h["escalation_probability"] = int(prob[1] * 100) if len(prob) > 1 else h.get("escalation_probability", 10)
        except Exception:
            pass
    
    return hotspots_data


if __name__ == "__main__":
    train_risk_model()
