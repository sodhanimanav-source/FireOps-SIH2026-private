import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import type { Facility, Hotspot, BackendFacilitiesResponse, BackendHotspotsResponse } from '../types';


export const apiClient = axios.create({
  
  baseURL: `${import.meta.env.VITE_API_BASE_URL ?? 'http:
  timeout: 60000, 
});


export const normalizeFacility = (raw: Record<string, unknown>, index = 0): Facility => {
  const lat = Number(raw.latitude ?? raw.lat ?? 0);
  const lng = Number(raw.longitude ?? raw.lng ?? 0);
  const name = String(raw.name ?? `Facility #${index + 1}`);

  return {
    id: String(raw.id ?? `FAC-${index + 1}`),
    name,
    type: String(raw.type ?? 'Industrial Complex'),
    latitude: lat,
    longitude: lng,
    buffer_radius_km: Number(raw.buffer_radius_km ?? raw.buffer_km ?? 5.0),
    baseline_frp: Number(raw.baseline_frp ?? 35.0),
    lat,
    lng,
    buffer_km: Number(raw.buffer_km ?? raw.buffer_radius_km ?? 5.0),
  };
};


export const normalizeHotspot = (raw: Record<string, unknown>, index = 0): Hotspot => {
  const lat = Number(raw.latitude ?? raw.lat ?? 0);
  const lng = Number(raw.longitude ?? raw.lng ?? 0);
  const frp = Number(raw.frp ?? 5.0);
  const tempK = Number(raw.temperature_k ?? raw.brightness ?? 320.0);
  const severity = String(raw.severity ?? (frp > 50.0 || tempK > 360.0 ? 'CRITICAL' : 'LOW'));
  
  
  let zScore = raw.modified_z_score !== undefined ? Number(raw.modified_z_score) : 0;
  if (Number.isNaN(zScore) || zScore === 0) {
    zScore = severity === 'CRITICAL' ? 4.5 : severity === 'MEDIUM' ? 3.6 : 2.1;
  }

  const persistence = Number(raw.persistence_index ?? (severity === 'CRITICAL' ? 0.95 : 0.65));
  const classification = String(
    raw.classification ?? raw.label ?? (severity === 'CRITICAL' ? 'Industrial Flare Anomaly' : 'Routine Thermal Activity')
  );

  return {
    id: String(raw.id ?? `HOT-${raw.date ? `${raw.date}-` : ''}${index + 1}`),
    latitude: lat,
    longitude: lng,
    frp: Math.round(frp * 100) / 100,
    temperature_k: Math.round(tempK * 10) / 10,
    modified_z_score: Math.round(zScore * 10) / 10,
    persistence_index: Math.round(persistence * 100) / 100,
    classification,
    severity,
    facility_name: raw.facility_name ? String(raw.facility_name) : null,
    facility_type: raw.facility_type ? String(raw.facility_type) : undefined,
    distance_km: raw.distance_km !== undefined && raw.distance_km !== null ? Number(raw.distance_km) : null,
    date: raw.date ? String(raw.date) : undefined,
    time: raw.time ? String(raw.time) : undefined,
    brightness: tempK,
  };
};


const fetchFacilities = async (): Promise<Facility[]> => {
  const { data } = await apiClient.get<BackendFacilitiesResponse | Facility[]>('/facilities');

  
  const rawList = Array.isArray(data)
    ? data
    : Array.isArray((data as BackendFacilitiesResponse).facilities)
      ? (data as BackendFacilitiesResponse).facilities
      : [];

  return rawList.map((item, idx) => normalizeFacility(item as Record<string, unknown>, idx));
};

export const useFacilities = () => {
  return useQuery({
    queryKey: ['facilities'],
    queryFn: fetchFacilities,
    staleTime: 1000 * 60 * 10, 
  });
};


const fetchHotspots = async (): Promise<Hotspot[]> => {
  const { data } = await apiClient.get<BackendHotspotsResponse | Hotspot[]>('/hotspots');

  
  const rawList = Array.isArray(data)
    ? data
    : Array.isArray((data as BackendHotspotsResponse).hotspots)
      ? (data as BackendHotspotsResponse).hotspots
      : [];

  return rawList.map((item, idx) => normalizeHotspot(item as Record<string, unknown>, idx));
};

export const useHotspots = () => {
  return useQuery({
    queryKey: ['hotspots'],
    queryFn: fetchHotspots,
    refetchInterval: 1000 * 30, 
  });
};
  export const usePendingAlerts = () => {
    return useQuery({
      queryKey: ['pending-alerts'],
      queryFn: async () => {
        const { data } = await apiClient.get('/alerts/pending');
        return data.alerts;
      },
      refetchInterval: 5000,
    });
  };
  export const resolveAlert = async (alertId: string, action: string) => {
    return apiClient.post(`/alerts/resolve/${alertId}`, { action });
  };

