import type { Facility, Hotspot } from '../types';

export interface GeoJSONFeature<P = Record<string, unknown>> {
  type: 'Feature';
  geometry: {
    type: 'Point';
    coordinates: [number, number]; 
  };
  properties: P;
}

export interface GeoJSONFeatureCollection<P = Record<string, unknown>> {
  type: 'FeatureCollection';
  features: GeoJSONFeature<P>[];
}


export function isValidCoordinate(latitude: number, longitude: number): boolean {
  if (typeof latitude !== 'number' || typeof longitude !== 'number') return false;
  if (Number.isNaN(latitude) || Number.isNaN(longitude)) return false;
  return latitude >= -90 && latitude <= 90 && longitude >= -180 && longitude <= 180;
}


export function filterHotspots(hotspots: Hotspot[] | null | undefined, anomalyFilterActive: boolean): Hotspot[] {
  if (!hotspots || !Array.isArray(hotspots)) {
    return [];
  }
  if (!anomalyFilterActive) {
    return hotspots;
  }
  return hotspots.filter((h) => typeof h.modified_z_score === 'number' && !Number.isNaN(h.modified_z_score) && h.modified_z_score > 3.5);
}


export function facilitiesToGeoJSON(facilities: Facility[] | null | undefined): GeoJSONFeatureCollection<Facility> {
  if (!facilities || !Array.isArray(facilities)) {
    return {
      type: 'FeatureCollection',
      features: [],
    };
  }

  const validFeatures: GeoJSONFeature<Facility>[] = facilities
    .filter((f) => f && isValidCoordinate(f.latitude, f.longitude))
    .map((f) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [f.longitude, f.latitude],
      },
      properties: { ...f },
    }));

  return {
    type: 'FeatureCollection',
    features: validFeatures,
  };
}


export function hotspotsToGeoJSON(hotspots: Hotspot[] | null | undefined): GeoJSONFeatureCollection<Hotspot> {
  if (!hotspots || !Array.isArray(hotspots)) {
    return {
      type: 'FeatureCollection',
      features: [],
    };
  }

  const validFeatures: GeoJSONFeature<Hotspot>[] = hotspots
    .filter((h) => h && isValidCoordinate(h.latitude, h.longitude))
    .map((h) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [h.longitude, h.latitude],
      },
      properties: { ...h },
    }));

  return {
    type: 'FeatureCollection',
    features: validFeatures,
  };
}
