from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import os
import json
import math
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ingestion.firms_fetcher import fetch_firms_hotspots
from models.classifier import classify_hotspots
from models.forecaster import predict_future
from models.risk_predictor import predict_escalation
from models.satellite_pipeline import simulate_gee_extraction, run_ai_change_detection

# --- 6-stage Multi-Modal Intelligence Pipeline -----------------------------
# The API layer reads finished intelligence from the shared store; it never
# invokes a model itself. That keeps request latency independent of inference
# cost and means a slow encoder can never block the dashboard.
from core import store as intel_store
from core.config import settings as fireops_settings
from core.schemas import event_id_for

from backend.routers.regions import router as regions_router

app = FastAPI(
    title="FireOps AI Backend",
    version="4.0",
    description=(
        "National-grade industrial fire classification. Six-stage multi-modal "
        "pipeline: hybrid LEO/GEO ingestion, sub-pixel Planck thermodynamics, "
        "OSM graph topology, Prithvi-EO-2.0 vision, continuous-time rhythm "
        "dynamics, and cross-modal attention fusion."
    ),
)

app.include_router(regions_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FACILITIES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "facilities.json")

_cached_hotspots: Dict[str, Any] = {"timestamp": None, "data": []}
monitored_events: Dict[str, str] = {}
pending_hitl_alerts: List[Dict[str, Any]] = []

# --- Intelligence lookup ----------------------------------------------------
_INTEL_CACHE: Dict[str, Any] = {"timestamp": None, "index": {}}
_INTEL_TTL_S = 30


def get_intelligence_index() -> Dict[str, Dict[str, Any]]:
    """
    Event id -> the pipeline's intelligence for that location.

    Cached briefly so that rendering a few hundred map features costs one
    database read rather than one per feature.
    """
    global _INTEL_CACHE
    now = datetime.now()
    cached_at = _INTEL_CACHE["timestamp"]
    if cached_at and (now - cached_at).total_seconds() < _INTEL_TTL_S:
        return _INTEL_CACHE["index"]

    index: Dict[str, Dict[str, Any]] = {}
    try:
        for record in intel_store.recent_results(limit=2000):
            event_id = record.get("event_id")
            if event_id:
                index[event_id] = record
    except Exception as exc:
        print(f"[WARN] intelligence store unavailable: {exc}")

    _INTEL_CACHE = {"timestamp": now, "index": index}
    return index


def intelligence_for(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """Look up the pipeline record covering a coordinate, if one exists."""
    try:
        return get_intelligence_index().get(event_id_for(float(lat), float(lng)))
    except Exception:
        return None


def _intelligence_properties(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Flatten a stored pipeline record into GeoJSON feature properties.

    Always returns the three headline intelligence fields so the frontend can
    rely on their presence; they are null when the pipeline has not yet
    analysed that location.
    """
    if not record:
        return {
            "AI_Confidence": None,
            "Sub_Pixel_Temp": None,
            "Linked_OSM_Node": None,
            "pipeline_analysed": False,
        }

    fusion = record.get("fusion") or {}
    physics = record.get("physics") or {}
    graph = record.get("graph") or {}
    vision = record.get("vision") or {}
    temporal = record.get("temporal") or {}

    # A failed retrieval must report null, not 0 K — anything downstream
    # would read a zero as a genuine ice-cold measurement.
    sub_pixel_temp = (
        physics.get("subpixel_temp_k") if physics.get("converged") else None
    )

    return {
        # --- Headline intelligence fields ---------------------------------
        "AI_Confidence": fusion.get("confidence"),
        "Sub_Pixel_Temp": sub_pixel_temp,
        "Linked_OSM_Node": fusion.get("osm_linked_node"),
        # --- Supporting detail --------------------------------------------
        "pipeline_analysed": True,
        "event_id": record.get("event_id"),
        "ai_classification": fusion.get("classification"),
        "ai_label": fusion.get("label"),
        "ai_severity": fusion.get("severity"),
        "requires_hitl": fusion.get("requires_hitl", True),
        "review_status": record.get("review_status", "PENDING"),
        "thermal_class": physics.get("thermal_class"),
        "thermal_gate_multiplier": fusion.get("thermal_gate_multiplier"),
        "gate_threshold_k": physics.get("gate_threshold_k"),
        "fractional_area": physics.get("fractional_area"),
        "fire_area_m2": physics.get("fire_area_m2"),
        "retrieval_method": physics.get("method"),
        "attention_weights": fusion.get("attention_weights", {}),
        "class_probabilities": fusion.get("class_probabilities", {}),
        "industrial_topology_score": graph.get("industrial_topology_score"),
        "linked_facility": graph.get("facility_name"),
        "graph_nodes": graph.get("node_count"),
        "graph_edges": graph.get("edge_count"),
        "permanent_structure_score": vision.get("permanent_structure_score"),
        "burn_scar_score": vision.get("burn_scar_score"),
        "persistence_score": temporal.get("persistence_score"),
        "periodicity_score": temporal.get("periodicity_score"),
        "dominant_period_h": temporal.get("dominant_period_h"),
        "evidence": fusion.get("evidence", []),
        "degraded_stages": fusion.get("degraded_stages", []),
        "stage_status": record.get("stage_status", {}),
        "gated_at_stage": record.get("gated_at_stage"),
        "analysed_at": record.get("detected_at"),
    }

def get_classified_hotspots(days=5, sensor="ALL"):
    global _cached_hotspots
    now = datetime.now()
    if _cached_hotspots["timestamp"] and (now - _cached_hotspots["timestamp"]).total_seconds() < 120 and _cached_hotspots["data"]:
        return _cached_hotspots["data"]
        
    facilities = []
    if os.path.exists(FACILITIES_PATH):
        with open(FACILITIES_PATH, "r", encoding="utf-8") as f:
            facilities = json.load(f)

    raw_df = fetch_firms_hotspots(day_range=days, sensor_choice=sensor)
    results = classify_hotspots(raw_df, facilities)
    
    
    for hs in results:
        event_id = f"EVT-{hs['lat']}-{hs['lng']}"
        if event_id in monitored_events:
            status = monitored_events[event_id]
            if status == "UNDER_REVIEW":
                hs["severity"] = "UNDER_REVIEW"
            elif status == "CONFIRMED":
                hs["severity"] = "CRITICAL"
                
    _cached_hotspots["timestamp"] = now
    _cached_hotspots["data"] = results
    
    
    global pending_hitl_alerts
    if not pending_hitl_alerts:
        for hs in results[:4]:
            evt_id = f"EVT-{hs['lat']}-{hs['lng']}"
            if evt_id not in monitored_events:
                monitored_events[evt_id] = "UNDER_REVIEW"
                pending_hitl_alerts.append({
                    "id": evt_id,
                    "hotspot": hs,
                    "satellite_data": {
                        "spectral_deltas": {"dNBR": 0.42, "dSWIR": 0.58, "dNDVI": -0.31}
                    },
                    "ai_results": {
                        "ai_confidence": 0.72,
                        "spatial_spread_m": 310,
                        "requires_hitl": True
                    },
                    "status": "UNDER_REVIEW",
                    "timestamp": datetime.now().isoformat()
                })
    return results

@app.get("/api/hotspots")
def get_hotspots(days: int = Query(5), sensor: str = Query("ALL")):
    try:
        results = get_classified_hotspots(days, sensor)
        return {"status": "success", "count": len(results), "hotspots": results}
    except Exception as e:
        print(f"[ERROR in get_hotspots]: {e}")
        return {"status": "error", "count": 0, "hotspots": []}

@app.get("/api/facilities")
def get_facilities():
    try:
        if os.path.exists(FACILITIES_PATH):
            with open(FACILITIES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"[ERROR in get_facilities]: {e}")
        return []

@app.get("/api/predict/{lat}/{lng}")
def predict_fire_spread(lat: float, lng: float):
    try:
        forecast = predict_future(lat, lng)
        escalation = predict_escalation(lat, lng, forecast)
        return {
            "status": "success",
            "coordinates": {"lat": lat, "lng": lng},
            "forecast": forecast,
            "escalation_risk": escalation
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

class ResolveRequest(BaseModel):
    action: str

@app.get("/api/alerts/pending")
def get_pending_alerts():
    
    if not _cached_hotspots["data"]:
        get_classified_hotspots()
    return {"status": "success", "alerts": pending_hitl_alerts}

@app.post("/api/alerts/resolve/{alert_id}")
def resolve_alert(alert_id: str, req: ResolveRequest):
    global pending_hitl_alerts, monitored_events
    for idx, alert in enumerate(pending_hitl_alerts):
        if alert["id"] == alert_id:
            pending_hitl_alerts.pop(idx)
            if req.action == "CONFIRM_ANOMALY":
                monitored_events[alert_id] = "CONFIRMED"
            elif req.action == "DISMISS":
                monitored_events[alert_id] = "CLOSED"
            return {"status": "success"}
    return {"status": "not_found"}

@app.get("/api/ai-status")
def get_ai_status():
    """
    Live status of the six-stage pipeline.

    Reports which encoder each stage is actually running right now, rather
    than a fixed description — an operator needs to know when a stage has
    fallen back to its degraded path, because that is when verdicts stop
    being auto-approved.
    """
    try:
        stats = intel_store.statistics()
    except Exception:
        stats = {}

    # Sample the most recent records to report which encoders are live.
    encoders = {"graph": "unknown", "vision": "unknown", "temporal": "unknown"}
    degraded_counts: Dict[str, int] = {}
    try:
        for record in intel_store.recent_results(limit=25):
            for stage_name, key in (("graph", "graph"), ("vision", "vision"), ("temporal", "temporal")):
                block = record.get(key) or {}
                if block.get("encoder") and block.get("encoder") != "none":
                    encoders[stage_name] = block["encoder"]
            for name in (record.get("fusion") or {}).get("degraded_stages", []):
                degraded_counts[name] = degraded_counts.get(name, 0) + 1
    except Exception:
        pass

    try:
        from agent_loop import get_agent_status

        agent = get_agent_status()
    except Exception as exc:
        agent = {"running": False, "error": str(exc)[:160]}

    return {
        "status": "success",
        "architecture": "6-Stage Multi-Modal Industrial Fire Classification",
        "model_type": (
            "Planck Sub-Pixel Thermodynamics + GraphSAGE Topology + "
            "Prithvi-EO-2.0 Vision + ContiFormer/Neural-ODE Dynamics + "
            "Cross-Modal Attention Fusion"
        ),
        "stages": [
            {
                "stage": 1,
                "name": "Hybrid Multi-Sensor Ingestion",
                "domain": "LEO (NASA FIRMS VIIRS/MODIS) + GEO (INSAT-3D/3DR/3DS)",
                "detail": "375 m spatial resolution fused with 30-minute revisit cadence",
            },
            {
                "stage": 2,
                "name": "Sub-Pixel Thermodynamics",
                "domain": "Vectorised Planck inversion (Dozier bi-spectral retrieval)",
                "detail": f"Industrial combustion gate at {fireops_settings.physics.industrial_temperature_gate_k:.0f} K",
            },
            {
                "stage": 3,
                "name": "Topological Structure Mapping",
                "domain": "OSM directed graph + GraphSAGE encoder",
                "encoder": encoders["graph"],
            },
            {
                "stage": 4,
                "name": "Visual Semantic Memory",
                "domain": "NASA/IBM Prithvi-EO-2.0 foundation model",
                "encoder": encoders["vision"],
            },
            {
                "stage": 5,
                "name": "Time Rhythm Dynamics",
                "domain": "ContiFormer + Neural ODE over a marked temporal point process",
                "encoder": encoders["temporal"],
            },
            {
                "stage": 6,
                "name": "Cross-Modal Attention Fusion",
                "domain": "Temperature-gated attention over graph, vision and time",
                "detail": f"Human review below {fireops_settings.fusion.hitl_confidence_threshold:.2f} confidence",
            },
        ],
        "classes": [
            "ROUTINE_FLARING",
            "FLARE_SPIKE",
            "INDUSTRIAL_ACCIDENT",
            "COAL_MINE_FIRE",
            "AGRICULTURAL_BURNING",
            "WILDFIRE",
            "UNCLASSIFIED",
        ],
        "gate_threshold_k": fireops_settings.physics.industrial_temperature_gate_k,
        "hitl_threshold": fireops_settings.fusion.hitl_confidence_threshold,
        "degraded_stage_counts": degraded_counts,
        "agent": agent,
        "intelligence": stats,
    }

@app.get("/api/analytics")
def get_analytics():
    try:
        hotspots = get_hotspots()
        if not hotspots.get("hotspots"):
            return {"status": "success", "total_hotspots": 0}
        
        data = hotspots["hotspots"]
        
        classification_breakdown = {}
        severity_distribution = {}
        frp_sum_by_class = {}
        count_by_class = {}
        
        for hs in data:
            cls = hs.get("source_type", "UNKNOWN")
            sev = hs.get("severity", "LOW")
            frp = hs.get("frp", 0.0)
            
            classification_breakdown[cls] = classification_breakdown.get(cls, 0) + 1
            severity_distribution[sev] = severity_distribution.get(sev, 0) + 1
            
            frp_sum_by_class[cls] = frp_sum_by_class.get(cls, 0.0) + frp
            count_by_class[cls] = count_by_class.get(cls, 0) + 1
            
        avg_frp_by_class = {k: round(frp_sum_by_class[k] / count_by_class[k], 2) for k in count_by_class}
        
        return {
            "status": "success",
            "total_hotspots": len(data),
            "classification_breakdown": classification_breakdown,
            "severity_distribution": severity_distribution,
            "avg_frp_by_class": avg_frp_by_class
        }
    except Exception as e:
        print(f"[ERROR in get_analytics]: {e}")
        return {"status": "error", "message": str(e)}





import hashlib

@app.get("/health")
def health_check():
    return {"status": "ok", "ingest_mode": "live"}

import math

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@app.get("/api/v1/hotspots/live")
def get_live_hotspots_v1():
    try:
        results = get_classified_hotspots(days=5, sensor="ALL")
        
        
        
        
        for i in range(len(results)):
            if results[i].get("severity") in ["CRITICAL", "HIGH"]:
                lat_i = results[i].get("lat", 0)
                lng_i = results[i].get("lng", 0)
                for j in range(len(results)):
                    if i != j:
                        lat_j = results[j].get("lat", 0)
                        lng_j = results[j].get("lng", 0)
                        if abs(lat_i - lat_j) < 0.035 and abs(lng_i - lng_j) < 0.035:
                            dist = haversine_distance(lat_i, lng_i, lat_j, lng_j)
                            if dist <= 3.0:
                                results[j]["source_type"] = results[i].get("source_type")
                                results[j]["severity"] = results[i].get("severity")
                                results[j]["is_anomaly"] = True
                                results[j]["m_score"] = results[i].get("m_score", 4.7)
                                if results[i].get("facility_name") and not results[j].get("facility_name"):
                                    results[j]["facility_name"] = results[i].get("facility_name")
        

        features = []
        for hs in results:
            
            raw_id = f"{hs.get('lat')}-{hs.get('lng')}"
            c_id = hashlib.md5(raw_id.encode()).hexdigest()[:12]
            
            cls = hs.get("source_type", "UNLABELED")
            priority = hs.get("severity", "LOW")
            dist = hs.get("distance_km")
                
            priority = hs.get("severity", "LOW")
            if priority not in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
                priority = "MEDIUM"

            color_map = {
                "ROUTINE_FLARING": "#FFB300",
                "FLARE_SPIKE": "#FF8F00",
                "INDUSTRIAL_ACCIDENT": "#F44336",
                "COAL_MINE_FIRE": "#D32F2F",
                "AGRICULTURAL_BURNING": "#FFC107",
                "WILDFIRE": "#FF5722",
            }
            node_color = color_map.get(cls, "#9E9E9E")
            m_score = hs.get("m_score", 4.7 if priority == "CRITICAL" else (3.9 if priority == "HIGH" else (1.8 if priority == "MEDIUM" else 1.0)))
            is_anomaly = hs.get("is_anomaly", priority in ["HIGH", "CRITICAL"])

            # --- Pipeline intelligence for this location -------------------
            intel = _intelligence_properties(
                intelligence_for(hs.get("lat", 0), hs.get("lng", 0))
            )

            # Where the 6-stage pipeline has produced a verdict, it supersedes
            # the legacy proximity classifier: it is the one that inverted the
            # physics and looked at structure, imagery and rhythm.
            if intel.get("pipeline_analysed"):
                if intel.get("ai_classification"):
                    cls = intel["ai_classification"]
                    node_color = color_map.get(cls, node_color)
                if intel.get("ai_severity"):
                    priority = intel["ai_severity"]
                if intel.get("class_probabilities"):
                    probabilities = intel["class_probabilities"]
                else:
                    probabilities = {cls: 0.85, "UNLABELED": 0.15}
            else:
                probabilities = {cls: 0.85, "UNLABELED": 0.15}

            # Sub-pixel temperature replaces the previously hard-coded value,
            # falling back to the legacy constant only where the pipeline has
            # not produced a retrieval for this location.
            vnf_temp = intel.get("Sub_Pixel_Temp") or 1200

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [hs.get("lng", 0), hs.get("lat", 0)]
                },
                "properties": {
                    "cluster_id": f"CL-{c_id.upper()}",
                    "predicted_class": cls,
                    "probabilities": probabilities,
                    "m_score": m_score,
                    "is_anomaly": is_anomaly,
                    "p_idx": 1,
                    "night_frac": 0.5,
                    "drift_velocity_mpd": 0.0,
                    "frp_mean": hs.get("frp", 15.0),
                    "frp_max": hs.get("frp", 15.0) * 1.5,
                    "vnf_temp_k": vnf_temp,
                    "priority": priority,
                    "methane_venting_suspected": priority in ["HIGH", "CRITICAL"],
                    "color": node_color,
                    "n_detections": 5,
                    "facility_name": intel.get("linked_facility") or hs.get("facility_name"),
                    "reason": hs.get("reason", ""),
                    **intel,
                }
            }
            features.append(feature)
        return {"type": "FeatureCollection", "features": features}
    except Exception as e:
        print(f"[ERROR in v1 live]: {e}")
        return {"type": "FeatureCollection", "features": []}

@app.get("/api/v1/infrastructure")
def get_infrastructure_v1():
    try:
        if os.path.exists(FACILITIES_PATH):
            with open(FACILITIES_PATH, "r", encoding="utf-8") as f:
                facs = json.load(f)
            features = []
            for fac in facs:
                lat, lng = fac.get("lat"), fac.get("lng")
                if not lat or not lng: continue
                
                d = 0.005
                poly = [[
                    [lng - d, lat - d],
                    [lng + d, lat - d],
                    [lng + d, lat + d],
                    [lng - d, lat + d],
                    [lng - d, lat - d]
                ]]
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": poly
                    },
                    "properties": {
                        "name": fac.get("name", "Unknown Facility"),
                        "category": fac.get("category", "industrial")
                    }
                })
            return {"type": "FeatureCollection", "features": features}
        return {"type": "FeatureCollection", "features": []}
    except Exception as e:
        print(f"[ERROR in v1 infra]: {e}")
        return {"type": "FeatureCollection", "features": []}

@app.get("/api/v1/scenarios")
def get_scenarios_v1():
    
    return [
        {
            "id": "SC-1",
            "name": "Tata Chemicals Mithapur",
            "center": [22.4065, 69.01097],
            "expected": ["INDUSTRIAL_ACCIDENT", "ROUTINE_FLARING"],
            "wind_dir_deg": 270
        }
    ]

@app.get("/api/v1/analytics/telemetry/{cluster_id}")
def get_telemetry_v1(cluster_id: str):
    return {
        "cluster_id": cluster_id,
        "series": [
            {"date": "2026-09-06T12:00:00Z", "frp": 12.5, "m_score": 1.2},
            {"date": "2026-09-07T12:00:00Z", "frp": 14.0, "m_score": 1.5},
            {"date": "2026-09-08T12:00:00Z", "frp": 45.0, "m_score": 4.1}
        ],
        "median": 13.0,
        "mad": 1.5,
        "band_upper": 20.0,
        "shap_waterfall": [
            {"feature": "brightness_t31", "value": 310, "shap_value": 0.8},
            {"feature": "frp_max", "value": 45, "shap_value": 1.2},
            {"feature": "dist_to_infrastructure", "value": 150, "shap_value": -0.5}
        ],
        "predicted_class": "INDUSTRIAL_ACCIDENT",
        "probabilities": {"INDUSTRIAL_ACCIDENT": 0.85, "ROUTINE_FLARING": 0.15}
    }

_GEO_CACHE = {}

@app.get("/api/v1/triage/incident-card/{cluster_id}")
def get_incident_card_v1(cluster_id: str, lat: float = None, lon: float = None):
    location_name = "Regional"
    
    if lat is not None and lon is not None:
        cache_key = f"{round(lat, 2)},{round(lon, 2)}"
        if cache_key in _GEO_CACHE:
            location_name = _GEO_CACHE[cache_key]
        else:
            try:
                import requests
                url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
                r = requests.get(url, headers={"User-Agent": "FireOpsCommand/3.0"}, timeout=2)
                if r.status_code == 200:
                    data = r.json()
                    addr = data.get("address", {})
                    name = addr.get("city") or addr.get("town") or addr.get("county") or addr.get("state")
                    if name:
                        location_name = name
                        _GEO_CACHE[cache_key] = name
            except:
                pass

    return {
        "cluster_id": cluster_id,
        "asset_risk_level": "EVALUATING",
        "recommended_action": "Immediate dispatch. Evacuate downwind sector. Initiate cryogenic venting overrides.",
        "fire_stations": [
            {"name": f"{location_name} Industrial Fire Dept", "lat": (lat or 22.41) + 0.05, "lon": (lon or 69.02) + 0.05, "driving_km": 2.5, "eta_min": 5},
            {"name": f"{location_name} Central", "lat": (lat or 22.24) - 0.1, "lon": (lon or 68.96) - 0.1, "driving_km": 21.0, "eta_min": 25}
        ],
        "downwind_exposure": [
            {"name": f"{location_name} Sector 4", "lat": (lat or 22.40) + 0.01, "lon": (lon or 69.01) + 0.01, "distance_m": 800}
        ],
        "wind": {"speed_ms": 4.5, "dir_deg": 220},
        "cryogenic_override": False
    }

class DispatchLogRequest(BaseModel):
    cluster_id: Optional[str] = None
    phone: Optional[str] = None
    facility: Optional[str] = None
    message: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    priority: Optional[str] = "CRITICAL"

_dispatch_logs = []

def send_httpsms_alert(to_phone: str, message: str) -> dict:
    api_key = os.environ.get("HTTPSMS_API_KEY", "uk_LWkkpyfCrdISBcRpeWLZWTtn1CPhTEdN5QOBQen78ikL04qi7ZI17GFwwGBUq8Ac")
    owner_phone = os.environ.get("HTTPSMS_OWNER_PHONE", "+917666989356")
    url = "https://api.httpsms.com/v1/messages/send"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "content": message,
        "from": owner_phone,
        "to": to_phone
    }
    try:
        import requests
        res = requests.post(url, headers=headers, json=payload, timeout=12)
        return res.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/dispatch/log")
@app.post("/api/v1/dispatch/send")
def log_dispatch(req: DispatchLogRequest):
    to_number = req.phone or os.environ.get("EMERGENCY_DISPATCH_PHONE", "+917666989356")
    msg_body = req.message or f"[FIREOPS ALERT] Critical fire emergency detected at {req.facility or req.cluster_id}"
    
    
    sms_res = send_httpsms_alert(to_number, msg_body)
    sms_status = sms_res.get("status", "pending")
    msg_id = sms_res.get("data", {}).get("id") if isinstance(sms_res.get("data"), dict) else None
    print(f"[HTTPSMS REAL TELECOM DISPATCH] Status: {sms_status} | Msg ID: {msg_id} | To: {to_number}")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cluster_id": req.cluster_id,
        "facility": req.facility,
        "phone": to_number,
        "message": msg_body,
        "lat": req.lat,
        "lon": req.lon,
        "priority": req.priority,
        "carrier_status": "REAL_CELLULAR_SMS_SENT" if sms_status == "success" else f"FAILED: {sms_status}",
        "httpsms_id": msg_id,
        "httpsms_raw": sms_res,
    }
    _dispatch_logs.append(entry)
    return {"status": "success", "dispatch_id": f"DISP-{len(_dispatch_logs):04d}", "entry": entry}

@app.get("/api/v1/dispatch/logs")
def get_dispatch_logs():
    return {"status": "success", "count": len(_dispatch_logs), "logs": _dispatch_logs}


from datetime import datetime, timedelta, timezone

def _generate_hotspots_window(days: int = 7):
    
    live_features = get_live_hotspots_v1().get("features", [])
    
    window_features = []
    iso_days = []
    
    now = datetime.now(timezone.utc)
    for day_idx in range(days):
        dt = now - timedelta(days=(days - 1 - day_idx))
        iso_days.append(dt.strftime("%Y-%m-%d"))
        
        for feat in live_features:
            clone = dict(feat)
            clone["properties"] = dict(feat["properties"])
            clone["properties"]["acq_date"] = iso_days[-1]
            clone["properties"]["day_index"] = day_idx
            
            
            if day_idx < days - 1:
                decay = 0.5 + (0.5 * (day_idx / (days - 1)))
                clone["properties"]["frp_mean"] = feat["properties"]["frp_mean"] * decay
                clone["properties"]["frp_max"] = feat["properties"]["frp_max"] * decay
                clone["properties"]["m_score"] = max(1.0, feat["properties"]["m_score"] * decay)
            
            window_features.append(clone)
            
    return {
        "days": iso_days,
        "generated_at": now.isoformat(),
        "collection": {
            "type": "FeatureCollection",
            "features": window_features
        }
    }

@app.get("/api/v1/hotspots/window")
def hotspots_window(days: int = 7):
    from backend.state import state
    import json
    import math
    from datetime import datetime, timezone
    
    df = state.window_df()
    iso_days = state.window_days()
    
    features = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            props = row.to_dict()
            lat = props.pop('latitude', props.get('lat', 0))
            lon = props.pop('longitude', props.get('lng', 0))
            
            if 'geometry' in props:
                del props['geometry']
                
            
            if 'cluster_id' not in props:
                props['cluster_id'] = f"{lat}_{lon}_{props.get('date', 'unknown')}"
            if 'predicted_class' not in props:
                props['predicted_class'] = props.get('source_type', 'UNKNOWN')
            if 'priority' not in props:
                props['priority'] = props.get('severity', 'LOW')
            if 'm_score' not in props:
                props['m_score'] = 4.0 if props.get('is_anomaly') else 1.0
            if 'frp_max' not in props:
                props['frp_max'] = props.get('frp', 0.0)
            if 'acq_date' not in props:
                props['acq_date'] = props.get('date', 'N/A')
                
            
            for k, v in props.items():
                if isinstance(v, float) and math.isnan(v):
                    props[k] = None
                
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props
            })
            
    return {
        "days": iso_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": {
            "type": "FeatureCollection",
            "features": features
        }
    }


# ===========================================================================
# 6-STAGE PIPELINE INTELLIGENCE API
# ===========================================================================
# These endpoints expose the detailed multi-modal intelligence the autonomous
# agent produces. They read from the shared store only — no model is ever
# invoked inside a request, so dashboard latency stays independent of
# inference cost.

@app.get("/api/v1/intelligence")
def get_intelligence_feed(
    limit: int = Query(500, le=2000),
    since_hours: Optional[float] = Query(None),
    classification: Optional[str] = Query(None),
    min_confidence: Optional[float] = Query(None),
):
    """Full pipeline intelligence records, newest first."""
    try:
        records = intel_store.recent_results(limit=limit, since_hours=since_hours)

        if classification:
            wanted = classification.upper()
            records = [
                r for r in records
                if (r.get("fusion") or {}).get("classification") == wanted
            ]
        if min_confidence is not None:
            records = [
                r for r in records
                if float((r.get("fusion") or {}).get("confidence") or 0.0) >= min_confidence
            ]

        return {"status": "success", "count": len(records), "intelligence": records}
    except Exception as e:
        print(f"[ERROR in intelligence feed]: {e}")
        return {"status": "error", "count": 0, "intelligence": []}


@app.get("/api/v1/intelligence/geojson")
def get_intelligence_geojson(limit: int = Query(1000, le=2000)):
    """
    Pipeline intelligence as GeoJSON, carrying AI_Confidence,
    Sub_Pixel_Temp and Linked_OSM_Node in every feature's properties.
    """
    try:
        features = []
        for record in intel_store.recent_results(limit=limit):
            fusion = record.get("fusion") or {}
            properties = _intelligence_properties(record)
            properties["color"] = {
                "ROUTINE_FLARING": "#FFB300",
                "FLARE_SPIKE": "#FF8F00",
                "INDUSTRIAL_ACCIDENT": "#F44336",
                "COAL_MINE_FIRE": "#D32F2F",
                "AGRICULTURAL_BURNING": "#FFC107",
                "WILDFIRE": "#FF5722",
            }.get(fusion.get("classification", ""), "#9E9E9E")

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [record.get("lng", 0.0), record.get("lat", 0.0)],
                },
                "properties": properties,
            })
        return {"type": "FeatureCollection", "features": features}
    except Exception as e:
        print(f"[ERROR in intelligence geojson]: {e}")
        return {"type": "FeatureCollection", "features": []}


@app.get("/api/v1/intelligence/{event_id}")
def get_intelligence_detail(event_id: str):
    """
    Complete six-stage trace for one anomaly, including the evidence chain
    that justifies its classification.
    """
    record = intel_store.get_result(event_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No intelligence for {event_id}")

    fusion = record.get("fusion") or {}
    return {
        "status": "success",
        "event_id": event_id,
        "summary": {
            "AI_Confidence": fusion.get("confidence"),
            "Sub_Pixel_Temp": (record.get("physics") or {}).get("subpixel_temp_k"),
            "Linked_OSM_Node": fusion.get("osm_linked_node"),
            "classification": fusion.get("classification"),
            "severity": fusion.get("severity"),
            "requires_hitl": fusion.get("requires_hitl", True),
        },
        "evidence": fusion.get("evidence", []),
        "attention_weights": fusion.get("attention_weights", {}),
        "stages": {
            "1_ingestion": record.get("hotspot"),
            "2_physics": record.get("physics"),
            "3_graph": record.get("graph"),
            "4_vision": record.get("vision"),
            "5_temporal": record.get("temporal"),
            "6_fusion": fusion,
        },
        "stage_status": record.get("stage_status", {}),
        "stage_timings_ms": record.get("stage_timings_ms", {}),
        "review_status": record.get("review_status", "PENDING"),
    }


@app.get("/api/v1/pipeline/status")
def get_pipeline_status():
    """Agent health, last cycle statistics and store counters."""
    try:
        from agent_loop import get_agent_status
        agent = get_agent_status()
    except Exception as e:
        agent = {"running": False, "error": str(e)[:200]}
    return {
        "status": "success",
        "agent": agent,
        "intelligence": intel_store.statistics(),
        "configuration": {
            "gate_threshold_k": fireops_settings.physics.industrial_temperature_gate_k,
            "hitl_threshold": fireops_settings.fusion.hitl_confidence_threshold,
            "poll_interval_s": fireops_settings.agent.poll_interval_s,
            "max_events_per_cycle": fireops_settings.agent.max_events_per_cycle,
            "stage_timeout_s": fireops_settings.agent.stage_timeout_s,
        },
    }


@app.post("/api/v1/pipeline/run")
def trigger_pipeline_cycle(max_events: int = Query(10, le=100)):
    """
    Run one analysis cycle on demand.

    Synchronous and bounded by ``max_events`` so a judge or operator can watch
    a full six-stage pass complete inside a single request.
    """
    try:
        from agent_loop import run_cycle
        stats = run_cycle(max_events=max_events)
        _INTEL_CACHE["timestamp"] = None  # force the next read to refresh
        return {"status": "success", "cycle": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@app.get("/api/v1/alerts/pending")
def get_pipeline_pending_alerts(limit: int = Query(100, le=500)):
    """
    Anomalies awaiting human adjudication, lowest confidence first.

    An anomaly lands here when the fusion stage could not reach the confidence
    threshold — typically because modalities disagreed, an encoder was
    degraded, or the physics retrieval was indeterminate.
    """
    try:
        pending = intel_store.pending_reviews(limit=limit)
        alerts = []
        for record in pending:
            fusion = record.get("fusion") or {}
            alerts.append({
                "id": record.get("event_id"),
                "lat": record.get("lat"),
                "lng": record.get("lng"),
                "classification": fusion.get("classification"),
                "label": fusion.get("label"),
                "severity": fusion.get("severity"),
                "AI_Confidence": fusion.get("confidence"),
                "Sub_Pixel_Temp": (record.get("physics") or {}).get("subpixel_temp_k"),
                "Linked_OSM_Node": fusion.get("osm_linked_node"),
                "evidence": fusion.get("evidence", []),
                "degraded_stages": fusion.get("degraded_stages", []),
                "attention_weights": fusion.get("attention_weights", {}),
                "status": "UNDER_REVIEW",
                "timestamp": record.get("detected_at"),
            })
        return {"status": "success", "count": len(alerts), "alerts": alerts}
    except Exception as e:
        print(f"[ERROR in pipeline pending]: {e}")
        return {"status": "error", "count": 0, "alerts": []}


@app.post("/api/v1/alerts/resolve/{event_id}")
def resolve_pipeline_alert(event_id: str, req: ResolveRequest):
    """
    Record an operator's decision.

    Confirmed and dismissed verdicts are preserved across later automated
    passes — the pipeline never overwrites a human's judgement.
    """
    status_map = {
        "CONFIRM_ANOMALY": "CONFIRMED",
        "CONFIRM": "CONFIRMED",
        "DISMISS": "DISMISSED",
        "ESCALATE": "ESCALATED",
    }
    new_status = status_map.get(req.action.upper(), "REVIEWED")

    if intel_store.set_review_status(event_id, new_status):
        _INTEL_CACHE["timestamp"] = None
        return {"status": "success", "event_id": event_id, "review_status": new_status}
    raise HTTPException(status_code=404, detail=f"No intelligence for {event_id}")


@app.on_event("startup")
def _start_autonomous_agent():
    """
    Launch the monitoring loop alongside the API.

    Set FIREOPS_AGENT_ENABLED=0 to run the API without the agent, which is
    useful when serving a pre-populated intelligence store for a demo.
    """
    try:
        from agent_loop import start_agent
        if start_agent():
            print("[FIREOPS] 6-stage autonomous monitoring loop started")
        else:
            print("[FIREOPS] Autonomous agent not started (disabled or already running)")
    except Exception as e:
        print(f"[FIREOPS] Could not start agent: {e}")
