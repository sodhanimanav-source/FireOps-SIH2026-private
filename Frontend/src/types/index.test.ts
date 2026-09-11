import { describe, it, expect } from 'vitest';
import type { Facility, Hotspot } from './index';

describe('Type Definitions & Schema Boundaries', () => {
  it('should instantiate valid Facility object with all required properties', () => {
    const facility: Facility = {
      id: 'fac-101',
      name: 'Refinery Alpha',
      type: 'Petrochemical',
      latitude: 29.7604,
      longitude: -95.3698,
      buffer_radius_km: 5.0,
      baseline_frp: 12.5,
    };

    expect(facility.id).toBe('fac-101');
    expect(facility.name).toBe('Refinery Alpha');
    expect(facility.type).toBe('Petrochemical');
    expect(facility.latitude).toBe(29.7604);
    expect(facility.longitude).toBe(-95.3698);
    expect(facility.buffer_radius_km).toBe(5.0);
    expect(facility.baseline_frp).toBe(12.5);
  });

  it('should instantiate valid Hotspot object with all required properties', () => {
    const hotspot: Hotspot = {
      id: 'hot-501',
      latitude: 34.0522,
      longitude: -118.2437,
      frp: 45.2,
      temperature_k: 310.5,
      modified_z_score: 4.1,
      persistence_index: 0.8,
      classification: 'High Confidence Fire',
    };

    expect(hotspot.id).toBe('hot-501');
    expect(hotspot.latitude).toBe(34.0522);
    expect(hotspot.longitude).toBe(-118.2437);
    expect(hotspot.frp).toBe(45.2);
    expect(hotspot.temperature_k).toBe(310.5);
    expect(hotspot.modified_z_score).toBe(4.1);
    expect(hotspot.persistence_index).toBe(0.8);
    expect(hotspot.classification).toBe('High Confidence Fire');
  });

  it('should verify parameter types and numeric boundaries', () => {
    const validHotspot: Hotspot = {
      id: 'hot-min',
      latitude: -90,
      longitude: -180,
      frp: 0,
      temperature_k: 0,
      modified_z_score: -10.5,
      persistence_index: 0,
      classification: 'Nominal',
    };

    expect(typeof validHotspot.id).toBe('string');
    expect(typeof validHotspot.latitude).toBe('number');
    expect(typeof validHotspot.longitude).toBe('number');
    expect(typeof validHotspot.frp).toBe('number');
    expect(typeof validHotspot.temperature_k).toBe('number');
    expect(typeof validHotspot.modified_z_score).toBe('number');
    expect(typeof validHotspot.persistence_index).toBe('number');
    expect(typeof validHotspot.classification).toBe('string');
  });
});
