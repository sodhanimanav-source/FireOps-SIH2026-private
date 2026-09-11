import pytest
from models.v2.features_v2 import ContextBuilder, FEATURES
from models.v2.gate import gate
from models.v2.predict_v2 import predict

def test_features_exclude_coordinates():
    assert "lat" not in FEATURES
    assert "lng" not in FEATURES

def test_telangana_field_is_not_industrial():
    f = {
        "frp": 35, "brightness": 330, "is_night": 0.0,
        "dist_industry_m": 8400, "dist_oilgas_m": 99999, "dist_mine_m": 99999,
        "lc_cropland": 0.62, "lc_tree": 0.0,
        "days_active_90d": 1, "night_ratio_90d": 0.0
    }
    assert "lat" not in f
    g = gate(f)
    assert g is not None
    assert g[0] == "AGRICULTURAL_BURNING"

def test_jamnagar_flare():
    f = {
        "frp": 120, "brightness": 350, "is_night": 1.0,
        "dist_industry_m": 100, "dist_oilgas_m": 600, "dist_mine_m": 99999,
        "lc_cropland": 0.0, "lc_tree": 0.0,
        "days_active_90d": 80, "night_ratio_90d": 0.6
    }
    g = gate(f)
    assert g is not None
    assert g[0] == "GAS_FLARE"

def test_jharia_coal():
    f = {
        "frp": 8, "brightness": 310, "is_night": 0.0,
        "dist_industry_m": 99999, "dist_oilgas_m": 99999, "dist_mine_m": 200,
        "lc_cropland": 0.0, "lc_tree": 0.0,
        "days_active_90d": 60, "night_ratio_90d": 0.0
    }
    g = gate(f)
    assert g is not None
    assert g[0] == "COAL_MINE_FIRE"

def test_accident_goes_to_model():
    f = {
        "frp": 120, "brightness": 350, "is_night": 0.0,
        "dist_industry_m": 300, "dist_oilgas_m": 99999, "dist_mine_m": 99999,
        "lc_cropland": 0.0, "lc_tree": 0.0,
        "days_active_90d": 0, "night_ratio_90d": 0.0
    }
    g = gate(f)
    assert g is None

def test_predict_response_shape(monkeypatch):
    def mock_build(self, lat, lng, frp, brightness, daynight):
        return {
            "frp": frp, "brightness": brightness, "is_night": 0.0,
            "dist_industry_m": 8400, "dist_oilgas_m": 99999, "dist_mine_m": 99999,
            "lc_cropland": 0.62, "lc_tree": 0.0,
            "days_active_90d": 1, "night_ratio_90d": 0.0
        }
    monkeypatch.setattr(ContextBuilder, "build", mock_build)
    
    res = predict(17.9, 79.6, 35.0, 330.0)
    assert "label" in res
    assert "confidence" in res
    assert "source" in res
    assert "reason" in res
    assert "features" in res
    assert "probabilities" in res
    assert res["label"] == "AGRICULTURAL_BURNING"
    assert res["source"] == "rule_gate"
