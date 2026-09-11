import { create } from 'zustand';

interface AppState {
  selectedFacility: string | null;
  selectedHotspot: string | null;
  anomalyFilters: boolean;
  viewMode: 'overview' | 'facilities' | 'hotspots' | 'anomalies';
  setSelectedFacility: (id: string | null) => void;
  setSelectedHotspot: (id: string | null) => void;
  setAnomalyFilters: (active: boolean) => void;
  setViewMode: (mode: 'overview' | 'facilities' | 'hotspots' | 'anomalies') => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedFacility: null,
  selectedHotspot: null,
  anomalyFilters: false,
  viewMode: 'overview', 
  setSelectedFacility: (id) => set({ selectedFacility: id }),
  setSelectedHotspot: (id) => set({ selectedHotspot: id }),
  setAnomalyFilters: (active) => set({ anomalyFilters: active, viewMode: active ? 'anomalies' : 'overview' }),
  setViewMode: (mode) => set({ viewMode: mode, anomalyFilters: mode === 'anomalies' }),
}));
