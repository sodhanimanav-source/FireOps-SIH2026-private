export interface Facility {
  id: string;
  name: string;
  type: string;
  latitude: number;
  longitude: number;
  buffer_radius_km: number;
  baseline_frp: number;
  
  lat?: number;
  lng?: number;
  buffer_km?: number;
}

export interface Hotspot {
  id: string;
  latitude: number;
  longitude: number;
  frp: number; 
  temperature_k: number;
  modified_z_score: number;
  persistence_index: number;
  classification: string;
  
  severity?: 'CRITICAL' | 'MEDIUM' | 'LOW' | string;
  facility_name?: string | null;
  facility_type?: string;
  distance_km?: number | null;
  date?: string;
  time?: string;
  brightness?: number;
}

export interface BackendFacilitiesResponse {
  status: string;
  count: number;
  facilities: Record<string, unknown>[];
}

export interface BackendHotspotsResponse {
  status: string;
  count: number;
  hotspots: Record<string, unknown>[];
}
