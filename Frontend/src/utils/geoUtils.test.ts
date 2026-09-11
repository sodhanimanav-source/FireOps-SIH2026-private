import { describe, it, expect } from 'vitest';
import {
  isValidCoordinate,
  filterHotspots,
  facilitiesToGeoJSON,
  hotspotsToGeoJSON,
} from './geoUtils';
import type { Facility, Hotspot } from '../types';

describe('geoUtils - Parameter Bounds & Data Transforms', () => {
  describe('isValidCoordinate', () => {
    it('should validate standard coordinates', () => {
      expect(isValidCoordinate(0, 0)).toBe(true);
      expect(isValidCoordinate(45.123, -93.456)).toBe(true);
      expect(isValidCoordinate(-90, -180)).toBe(true);
      expect(isValidCoordinate(90, 180)).toBe(true);
    });

    it('should reject out-of-boundary latitudes and longitudes', () => {
      expect(isValidCoordinate(90.0001, 0)).toBe(false);
      expect(isValidCoordinate(-90.0001, 0)).toBe(false);
      expect(isValidCoordinate(0, 180.0001)).toBe(false);
      expect(isValidCoordinate(0, -180.0001)).toBe(false);
    });

    it('should reject invalid types, NaN, and null/undefined values', () => {
      expect(isValidCoordinate(NaN, 0)).toBe(false);
      expect(isValidCoordinate(0, NaN)).toBe(false);
      expect(isValidCoordinate(null as unknown as number, 0)).toBe(false);
      expect(isValidCoordinate(0, undefined as unknown as number)).toBe(false);
      expect(isValidCoordinate('34' as unknown as number, 0)).toBe(false);
    });
  });

  describe('filterHotspots - Anomaly Threshold (modified_z_score > 3.5)', () => {
    const mockHotspots: Hotspot[] = [
      { id: '1', latitude: 10, longitude: 20, frp: 10, temperature_k: 300, modified_z_score: 3.4999, persistence_index: 0.5, classification: 'Low' },
      { id: '2', latitude: 11, longitude: 21, frp: 15, temperature_k: 310, modified_z_score: 3.5, persistence_index: 0.6, classification: 'Med' },
      { id: '3', latitude: 12, longitude: 22, frp: 20, temperature_k: 320, modified_z_score: 3.5001, persistence_index: 0.7, classification: 'High' },
      { id: '4', latitude: 13, longitude: 23, frp: 50, temperature_k: 400, modified_z_score: 8.2, persistence_index: 0.9, classification: 'Severe' },
      { id: '5', latitude: 14, longitude: 24, frp: 5, temperature_k: 290, modified_z_score: -1.2, persistence_index: 0.1, classification: 'Background' },
    ];

    it('should return all hotspots when anomalyFilterActive is false', () => {
      const result = filterHotspots(mockHotspots, false);
      expect(result).toHaveLength(5);
      expect(result).toEqual(mockHotspots);
    });

    it('should strictly return hotspots with modified_z_score > 3.5 when anomalyFilterActive is true', () => {
      const result = filterHotspots(mockHotspots, true);
      
      
      
      expect(result.map((h) => h.id)).toEqual(['3', '4']);
    });

    it('should handle null, undefined, or empty arrays gracefully', () => {
      expect(filterHotspots(null, true)).toEqual([]);
      expect(filterHotspots(undefined, true)).toEqual([]);
      expect(filterHotspots([], true)).toEqual([]);
      expect(filterHotspots([], false)).toEqual([]);
    });

    it('should filter out invalid or NaN z-scores safely', () => {
      const corruptHotspots: Hotspot[] = [
        { id: 'c1', latitude: 10, longitude: 20, frp: 10, temperature_k: 300, modified_z_score: NaN, persistence_index: 0.5, classification: 'Corrupt' },
        { id: 'c2', latitude: 10, longitude: 20, frp: 10, temperature_k: 300, modified_z_score: 4.5, persistence_index: 0.5, classification: 'Valid' },
      ];
      const result = filterHotspots(corruptHotspots, true);
      expect(result.map((h) => h.id)).toEqual(['c2']);
    });
  });

  describe('facilitiesToGeoJSON', () => {
    const mockFacilities: Facility[] = [
      {
        id: 'f-1',
        name: 'Chemical Plant',
        type: 'Petro',
        latitude: 29.5,
        longitude: -95.2,
        buffer_radius_km: 5.0,
        baseline_frp: 10.0,
      },
    ];

    it('should convert facilities to GeoJSON FeatureCollection with [lon, lat] ordering', () => {
      const geojson = facilitiesToGeoJSON(mockFacilities);
      expect(geojson.type).toBe('FeatureCollection');
      expect(geojson.features).toHaveLength(1);

      const feature = geojson.features[0];
      expect(feature.type).toBe('Feature');
      expect(feature.geometry.type).toBe('Point');
      
      expect(feature.geometry.coordinates).toEqual([-95.2, 29.5]);
      expect(feature.properties.id).toBe('f-1');
      expect(feature.properties.name).toBe('Chemical Plant');
    });

    it('should discard invalid coordinate entries from GeoJSON output', () => {
      const invalidFacilities: Facility[] = [
        { id: 'f-bad', name: 'Bad Coords', type: 'Test', latitude: 95.0, longitude: 0, buffer_radius_km: 1, baseline_frp: 1 },
      ];
      const geojson = facilitiesToGeoJSON(invalidFacilities);
      expect(geojson.features).toHaveLength(0);
    });

    it('should handle empty or null facility inputs', () => {
      expect(facilitiesToGeoJSON(null).features).toEqual([]);
      expect(facilitiesToGeoJSON(undefined).features).toEqual([]);
      expect(facilitiesToGeoJSON([]).features).toEqual([]);
    });
  });

  describe('hotspotsToGeoJSON', () => {
    const mockHotspots: Hotspot[] = [
      {
        id: 'h-1',
        latitude: 32.1,
        longitude: -110.5,
        frp: 60.0,
        temperature_k: 350.0,
        modified_z_score: 4.8,
        persistence_index: 0.95,
        classification: 'Flare',
      },
    ];

    it('should convert hotspots to GeoJSON FeatureCollection with [lon, lat] ordering', () => {
      const geojson = hotspotsToGeoJSON(mockHotspots);
      expect(geojson.type).toBe('FeatureCollection');
      expect(geojson.features).toHaveLength(1);

      const feature = geojson.features[0];
      expect(feature.type).toBe('Feature');
      expect(feature.geometry.type).toBe('Point');
      expect(feature.geometry.coordinates).toEqual([-110.5, 32.1]);
      expect(feature.properties.frp).toBe(60.0);
      expect(feature.properties.modified_z_score).toBe(4.8);
    });

    it('should handle empty or null hotspot inputs', () => {
      expect(hotspotsToGeoJSON(null).features).toEqual([]);
      expect(hotspotsToGeoJSON(undefined).features).toEqual([]);
      expect(hotspotsToGeoJSON([]).features).toEqual([]);
    });
  });
});
