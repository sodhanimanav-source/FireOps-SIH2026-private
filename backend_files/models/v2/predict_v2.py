import os
import joblib
from .features_v2 import ContextBuilder, FEATURES
from .gate import gate

_context_builder = None
_model = None
_classes = []

def get_context_builder():
    global _context_builder
    if _context_builder is None:
        _context_builder = ContextBuilder(
            osm_path=os.path.join(os.path.dirname(__file__), "../../data/osm_industry_india.parquet"),
            history_path=os.path.join(os.path.dirname(__file__), "../../data/firms_india_history.parquet"),
            worldcover_path=os.path.join(os.path.dirname(__file__), "../../data/worldcover_india.tif")
        )
    return _context_builder

def get_model():
    global _model, _classes
    if _model is None:
        model_path = os.path.join(os.path.dirname(__file__), "../lgb_v2.pkl")
        if os.path.exists(model_path):
            data = joblib.load(model_path)
            _model = data["model"]
            _classes = data["classes"]
    return _model

def generate_reason(f: dict) -> str:
    parts = []
    if f["dist_industry_m"] < 90000:
        parts.append(f"nearest industry {round(f['dist_industry_m']/1000, 1)} km")
    if f["lc_cropland"] > 0.1:
        parts.append(f"cropland {int(f['lc_cropland']*100)}%")
    if f["lc_tree"] > 0.1:
        parts.append(f"tree cover {int(f['lc_tree']*100)}%")
    if f["days_active_90d"] > 0:
        parts.append(f"burned on {int(f['days_active_90d'])} of last 90 days")
    return ", ".join(parts)

def predict(lat: float, lng: float, frp: float, brightness: float, daynight: str = "D") -> dict:
    builder = get_context_builder()
    f = builder.build(lat, lng, frp, brightness, daynight)
    
    g = gate(f)
    if g is not None:
        label, reason = g
        probs = {c: 0.0 for c in _classes} if _classes else {}
        probs[label] = 0.99
        return {
            "label": label,
            "confidence": 0.99,
            "source": "rule_gate",
            "reason": reason,
            "features": f,
            "probabilities": probs
        }
        
    model = get_model()
    if model is None:
        return {
            "label": "UNCLASSIFIED",
            "confidence": 0.0,
            "source": "lgbm_missing",
            "reason": "Model file missing",
            "features": f,
            "probabilities": {}
        }
        
    x = [[f[k] for k in FEATURES]]
    probs_array = model.predict_proba(x)[0]
    pred_idx = probs_array.argmax()
    label = _classes[pred_idx]
    conf = float(probs_array[pred_idx])
    
    probs_dict = {str(_classes[i]): float(probs_array[i]) for i in range(len(_classes))}
    
    return {
        "label": str(label),
        "confidence": conf,
        "source": "lgbm",
        "reason": generate_reason(f),
        "features": f,
        "probabilities": probs_dict
    }
