import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { apiClient, useFacilities, useHotspots, normalizeFacility, normalizeHotspot } from './queries';

describe('Data Fetching Layer - apiClient & Normalization Adapter', () => {
  let queryClient: QueryClient;

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    vi.restoreAllMocks();
  });

  it('should have apiClient configured with base URL http:
    expect(apiClient.defaults.baseURL).toBe(`${import.meta.env.VITE_API_BASE_URL ?? 'http:
  });

  it('should normalize backend facility record correctly', () => {
    const rawBackendFacility = {
      id: 'CORE_FAC_001',
      name: 'Jamnagar Refinery Complex (Reliance)',
      type: 'Oil & Gas Refinery',
      lat: 22.3562,
      lng: 69.8686,
      buffer_km: 5.0,
      baseline_frp: 65.0,
    };

    const normalized = normalizeFacility(rawBackendFacility);
    expect(normalized.id).toBe('CORE_FAC_001');
    expect(normalized.name).toBe('Jamnagar Refinery Complex (Reliance)');
    expect(normalized.latitude).toBe(22.3562);
    expect(normalized.longitude).toBe(69.8686);
    expect(normalized.buffer_radius_km).toBe(5.0);
    expect(normalized.baseline_frp).toBe(65.0);
  });

  it('should normalize backend hotspot record with classification and severity', () => {
    const rawBackendHotspot = {
      lat: 22.358,
      lng: 69.871,
      frp: 142.5,
      brightness: 372.4,
      label: 'Industrial Flare Spike / Anomaly @ Jamnagar Refinery',
      severity: 'CRITICAL',
      facility_name: 'Jamnagar Refinery',
      distance_km: 0.35,
      date: '2026-08-30',
      time: '1430',
    };

    const normalized = normalizeHotspot(rawBackendHotspot, 0);
    expect(normalized.latitude).toBe(22.358);
    expect(normalized.longitude).toBe(69.871);
    expect(normalized.frp).toBe(142.5);
    expect(normalized.temperature_k).toBe(372.4);
    expect(normalized.severity).toBe('CRITICAL');
    expect(normalized.modified_z_score).toBe(4.5); 
    expect(normalized.classification).toBe('Industrial Flare Spike / Anomaly @ Jamnagar Refinery');
    expect(normalized.facility_name).toBe('Jamnagar Refinery');
    expect(normalized.distance_km).toBe(0.35);
  });

  it('should fetch and unwrap backend facilities envelope { status, count, facilities }', async () => {
    const backendResponse = {
      status: 'success',
      count: 1,
      facilities: [
        {
          id: 'CORE_FAC_001',
          name: 'Jamnagar Refinery',
          type: 'Refinery',
          lat: 22.35,
          lng: 69.86,
          buffer_km: 5.0,
          baseline_frp: 65.0,
        },
      ],
    };

    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: backendResponse });

    const { result } = renderHook(() => useFacilities(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].latitude).toBe(22.35);
    expect(result.current.data?.[0].name).toBe('Jamnagar Refinery');
  });

  it('should fetch and unwrap backend hotspots envelope { status, count, hotspots }', async () => {
    const backendResponse = {
      status: 'success',
      count: 1,
      hotspots: [
        {
          lat: 22.358,
          lng: 69.871,
          frp: 85.0,
          brightness: 360.0,
          label: 'Industrial Flare Spike',
          severity: 'CRITICAL',
        },
      ],
    };

    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: backendResponse });

    const { result } = renderHook(() => useHotspots(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].latitude).toBe(22.358);
    expect(result.current.data?.[0].frp).toBe(85.0);
    expect(result.current.data?.[0].modified_z_score).toBeGreaterThan(3.5);
  });

  it('should handle API errors gracefully in query hooks', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValueOnce(new Error('Network Error'));

    const { result } = renderHook(() => useFacilities(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeDefined();
    expect(result.current.error?.message).toBe('Network Error');
  });
});
