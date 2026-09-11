import time
import random
import threading
import json
from datetime import datetime

from models.satellite_pipeline import simulate_gee_extraction, run_ai_change_detection


monitored_events = {}
pending_hitl_alerts = []

def autonomous_loop():
    print("[AGENT] Starting Autonomous Geospatial Monitoring Loop...")
    while True:
        try:
            print(f"[AGENT] STEP 1: Polling NASA FIRMS stream at {datetime.now().time()}")
            from backend.main import get_classified_hotspots
            hotspots = get_classified_hotspots(days=1, sensor='ALL')
            
            
            high_risk = sorted(hotspots, key=lambda x: x.get('risk_score', 0), reverse=True)[:5]
            
            for hs in high_risk:
                event_id = f"EVT-{hs['lat']}-{hs['lng']}"
                if event_id in monitored_events:
                    continue 
                
                print(f"[AGENT] Detected new anomaly {event_id}. Extracting bi-temporal satellite data...")
                
                
                sat_data = simulate_gee_extraction(hs['lat'], hs['lng'])
                
                
                initial_conf = float(hs.get('confidence_pct', 50.0)) / 100.0
                ai_results = run_ai_change_detection(sat_data, initial_conf)
                
                
                if ai_results['requires_hitl']:
                    print(f"[AGENT] HITL GATE: {event_id} confidence {ai_results['ai_confidence']:.2f} < 0.85. Routing to operator...")
                    pending_hitl_alerts.append({
                        "id": event_id,
                        "hotspot": hs,
                        "satellite_data": sat_data,
                        "ai_results": ai_results,
                        "status": "UNDER_REVIEW",
                        "timestamp": datetime.now().isoformat()
                    })
                    monitored_events[event_id] = "UNDER_REVIEW"
                else:
                    print(f"[AGENT] AUTO-APPROVED: {event_id} confidence {ai_results['ai_confidence']:.2f}")
                    monitored_events[event_id] = "CONFIRMED"
                    
            
            time.sleep(15) 
            
        except Exception as e:
            print(f"[AGENT] Error in loop: {e}")
            time.sleep(5)

def start_agent():
    t = threading.Thread(target=autonomous_loop, daemon=True)
    t.start()

