import type { Feature, FeatureCollection, Point, Polygon, MultiPolygon } from "geojson";

export type ThermalClass =
  | "ROUTINE_FLARING"
  | "FLARE_SPIKE"
  | "INDUSTRIAL_ACCIDENT"
  | "COAL_MINE_FIRE"
  | "WILDFIRE_AGRI"
  | "AGRICULTURAL_BURNING"
  | "WILDFIRE"
  | "UNLABELED";

export type Priority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";


export interface ClusterProperties {
  cluster_id: string;
  predicted_class: ThermalClass;
  probabilities: Record<ThermalClass, number>;
  m_score: number;
  p_idx: number;
  night_frac: number;
  drift_velocity_mpd: number;
  frp_mean: number;
  frp_max: number;
  vnf_temp_k: number | null;
  priority: Priority;
  methane_venting_suspected: boolean;
  color: string;
  n_detections: number;
  scenario_id?: string;
  reason?: string;
}

export type ClusterFeature = Feature<Point, ClusterProperties>;
export type HotspotCollection = FeatureCollection<Point, ClusterProperties>;

export interface InfrastructureProperties {
  name: string;
  category: "refinery" | "power_plant" | "steel" | "lng" | "mine" | "industrial";
}
export type InfrastructureCollection = FeatureCollection<Polygon | MultiPolygon, InfrastructureProperties>;

export interface ShapItem { feature: string; value: number; shap_value: number; }

export interface TelemetryPoint { date: string; frp: number; m_score: number; }


export interface TelemetryData {
  cluster_id: string;
  series: TelemetryPoint[];
  median: number;
  mad: number;
  band_upper: number;
  shap_waterfall: ShapItem[];
  predicted_class: ThermalClass;
  probabilities: Record<ThermalClass, number>;
}

export interface FireStation { name: string; lat: number; lon: number; driving_km: number; eta_min: number; }
export interface ExposedArea { name: string; lat: number; lon: number; distance_m: number; }


export interface DispatchCard {
  cluster_id: string;
  asset_risk_level: Priority;
  recommended_action: string;
  fire_stations: FireStation[];
  downwind_exposure: ExposedArea[];
  wind: { dir_deg: number; speed_ms: number; source: string };
  cryogenic_override: boolean;
}

export interface HealthResponse { status: string; ingest_mode: "live" | "cache" | "fixture"; }

export interface ScenarioMeta {
  id: string;
  name: string;
  center: [number, number]; 
  expected: ThermalClass[];
  wind_dir_deg: number;
}

export interface WindowClusterProperties extends ClusterProperties {
  acq_date: string;      
  day_index: number;     
}
export type WindowFeature = Feature<Point, WindowClusterProperties>;


export interface WindowResponse {
  days: string[];        
  generated_at: string;
  collection: FeatureCollection<Point, WindowClusterProperties>;
}
