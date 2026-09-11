import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from './appStore';

describe('useAppStore - Zustand Global State', () => {
  beforeEach(() => {
    
    useAppStore.setState({
      selectedFacility: null,
      selectedHotspot: null,
      anomalyFilters: true,
    });
  });

  it('should initialize with expected default values', () => {
    const state = useAppStore.getState();
    expect(state.selectedFacility).toBeNull();
    expect(state.selectedHotspot).toBeNull();
    expect(state.anomalyFilters).toBe(true);
  });

  it('should update selectedFacility when setSelectedFacility is called', () => {
    const { setSelectedFacility } = useAppStore.getState();
    setSelectedFacility('facility-123');
    expect(useAppStore.getState().selectedFacility).toBe('facility-123');

    
    setSelectedFacility(null);
    expect(useAppStore.getState().selectedFacility).toBeNull();
  });

  it('should update selectedHotspot when setSelectedHotspot is called', () => {
    const { setSelectedHotspot } = useAppStore.getState();
    setSelectedHotspot('hotspot-999');
    expect(useAppStore.getState().selectedHotspot).toBe('hotspot-999');

    
    setSelectedHotspot(null);
    expect(useAppStore.getState().selectedHotspot).toBeNull();
  });

  it('should toggle anomalyFilters correctly', () => {
    const { setAnomalyFilters } = useAppStore.getState();
    setAnomalyFilters(false);
    expect(useAppStore.getState().anomalyFilters).toBe(false);

    setAnomalyFilters(true);
    expect(useAppStore.getState().anomalyFilters).toBe(true);
  });

  it('should handle rapid successive state changes without race conditions', () => {
    const { setSelectedFacility, setSelectedHotspot, setAnomalyFilters } = useAppStore.getState();
    setSelectedFacility('fac-1');
    setSelectedHotspot('hot-1');
    setAnomalyFilters(false);
    setSelectedFacility('fac-2');
    setSelectedHotspot(null);

    const finalState = useAppStore.getState();
    expect(finalState.selectedFacility).toBe('fac-2');
    expect(finalState.selectedHotspot).toBeNull();
    expect(finalState.anomalyFilters).toBe(false);
  });
});
