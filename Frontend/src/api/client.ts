import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import type {
  DispatchCard, HealthResponse, HotspotCollection, InfrastructureCollection, ScenarioMeta, TelemetryData,
} from "./types";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
  timeout: 15_000,
});

export const endpoints = {
  health: "/health",
  live: "/api/v1/hotspots/live",
  telemetry: (id: string) => `/api/v1/analytics/telemetry/${id}`,
  incidentCard: (id: string, lat?: number, lon?: number) => `/api/v1/triage/incident-card/${id}?lat=${lat}&lon=${lon}`,
  scenarios: "/api/v1/scenarios",
  infrastructure: "/api/v1/infrastructure",
};

const EMPTY_FC: InfrastructureCollection = { type: "FeatureCollection", features: [] };

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.get<HealthResponse>(endpoints.health)).data,
    refetchInterval: 15_000,
  });
}

export function useLiveHotspots() {
  return useQuery({
    queryKey: ["hotspots", "live"],
    queryFn: async () => (await api.get<HotspotCollection>(endpoints.live)).data,
    refetchInterval: 60_000,
  });
}

export function useTelemetry(clusterId: string | null) {
  return useQuery({
    queryKey: ["telemetry", clusterId],
    queryFn: async () => (await api.get<TelemetryData>(endpoints.telemetry(clusterId!))).data,
    enabled: Boolean(clusterId),
  });
}

export function useIncidentCard(clusterId: string | null, lat?: number, lon?: number, enabled = true) {
  return useQuery({
    queryKey: ["incident-card", clusterId],
    queryFn: async () => (await api.get<DispatchCard>(endpoints.incidentCard(clusterId!, lat, lon))).data,
    enabled: Boolean(clusterId) && enabled,
  });
}

export function useScenarios() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: async () => (await api.get<ScenarioMeta[]>(endpoints.scenarios)).data,
    staleTime: Infinity,
  });
}


export function useInfrastructure() {
  return useQuery({
    queryKey: ["infrastructure"],
    queryFn: async () => {
      try {
        return (await api.get<InfrastructureCollection>(endpoints.infrastructure)).data;
      } catch {
        return EMPTY_FC;
      }
    },
    staleTime: Infinity,
  });
}

import type { WindowResponse } from "./types";

export function useWindowHotspots(days = 7) {
  return useQuery({
    queryKey: ["hotspots", "window", days],
    queryFn: async () => (await api.get<WindowResponse>(`/api/v1/hotspots/window`, { params: { days } })).data,
    refetchInterval: 120_000,
  });
}
