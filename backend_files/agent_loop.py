import time
import random
import threading
import json
from datetime import datetime

# --- NAYE ARCHITECTURE KE IMPORTS ---
# Note: Ye aapke naye backend folder structure ke hisaab se imports hain
from ingestion.api_loader import fetch_firms_data, fetch_insat_hypertemporal
from ingestion.physics_filter import calculate_subpixel_temperature
from models.gnn_topology import extract_osm_graph
from models.prithvi_vision import run_prithvi_eo
from models.contiformer_time import run_contiformer
from models.cross_modal_fusion import cross_modal_attention

monitored_events = {}
pending_hitl_alerts = []

def autonomous_loop():
    print("[AGENT] Starting Advanced Multi-Modal Geospatial Monitoring Loop...")
    while True:
        try:
            print(f"\n[AGENT] STEP 1: Polling LEO (FIRMS) and GEO (INSAT-3D) streams at {datetime.now().time()}")
            
            # 1. Hybrid Data Ingestion
            firms_hotspots = fetch_firms_data(days=1, sensor='ALL') 
            insat_data = fetch_insat_hypertemporal() 
            
            # Risk score ke hisaab se top 5 anomalies filter kar rahe hain
            high_risk = sorted(firms_hotspots, key=lambda x: x.get('risk_score', 0), reverse=True)[:5]
            
            for hs in high_risk:
                event_id = f"EVT-{hs['lat']}-{hs['lng']}"
                if event_id in monitored_events:
                    continue 
                
                print(f"[AGENT] Detected new anomaly {event_id}. Running Physics Engine...")
                
                # 2. STEP 2: The Physics Filter (Sub-Pixel Thermal Unmixing)
                # Raw radiance par Planck's Law invert karke exact subpixel temperature nikalna
                subpixel_temp, frac_area = calculate_subpixel_temperature(hs)
                
                # Agar aag 1200 K se thandi hai, toh use Forest/Agri fire maankar mute kar do
                if subpixel_temp < 1200:
                    print(f"[AGENT] BIOMASS DETECTED: {event_id} temp is {subpixel_temp}K (< 1200K). Muting and bypassing AI.")
                    monitored_events[event_id] = "MUTED_BIOMASS"
                    continue
                
                print(f"[AGENT] EXTREME HEAT DETECTED: {subpixel_temp}K. Triggering AI Brains...")
                
                # 3. STEP 3, 4, 5: Parallel AI Feature Extraction
                # Zameen ka visual context, graph network, aur time rhythm nikalna
                sat_imagery = hs.get('imagery_data')
                
                gnn_features = extract_osm_graph(hs['lat'], hs['lng'])            # Topo-structure
                vision_features = run_prithvi_eo(sat_imagery)                     # Prithvi-EO foundation model
                time_features = run_contiformer(hs['lat'], hs['lng'], insat_data) # Neural ODEs dynamics
                
                # 4. STEP 6: Multi-Modal Fusion (The Final Brain)
                # Physical temperature ko gating multiplier bana kar charo data ko fuse karna
                fusion_results = cross_modal_attention(
                    temp=subpixel_temp,
                    graph_data=gnn_features,
                    vision_data=vision_features,
                    time_data=time_features
                )
                
                ai_confidence = fusion_results['confidence']
                classification = fusion_results['classification']
                linked_node = fusion_results.get('osm_linked_node', 'None')
                
                # 5. Decision Routing
                if ai_confidence < 0.85:
                    print(f"[AGENT] HITL GATE: {event_id} confidence {ai_confidence:.2f} < 0.85. Routing to operator...")
                    pending_hitl_alerts.append({
                        "id": event_id,
                        "hotspot": hs,
                        "sub_pixel_temp": subpixel_temp,
                        "ai_results": fusion_results,
                        "status": "UNDER_REVIEW",
                        "timestamp": datetime.now().isoformat()
                    })
                    monitored_events[event_id] = "UNDER_REVIEW"
                else:
                    print(f"[AGENT] AUTO-APPROVED: {event_id} -> {classification} (Conf: {ai_confidence:.2f}, Temp: {subpixel_temp}K, Node: {linked_node})")
                    monitored_events[event_id] = "CONFIRMED_INDUSTRIAL"
                    
            time.sleep(15) 
            
        except Exception as e:
            print(f"[AGENT] Error in loop: {e}")
            time.sleep(5)

def start_agent():
    t = threading.Thread(target=autonomous_loop, daemon=True)
    t.start()
