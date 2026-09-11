import { useShallow } from "zustand/react/shallow";
import { useMemo } from "react";
import { create } from "zustand";
import type { Priority, WindowFeature } from "@/api/types";
import { PRIORITY_RANK } from "@/lib/severityTheme";

export type ScrubMode = "day" | "cumulative";

interface AppState {
  
  days: string[];
  windowFeatures: WindowFeature[];
  currentTimeScrubberIndex: number;   
  scrubMode: ScrubMode;
  isPlaying: boolean;

  
  globalSeverityLevel: Priority;
  selectedAnomaly: WindowFeature | null;
  acknowledgedIds: Set<string>;
  focusMode: boolean;                 
  focusedRegion: { name: string; level: string; center?: [number, number] } | null;

  
  isAuthenticated: boolean;
  login: () => void;
  logout: () => void;

  
  setWindowData: (days: string[], features: WindowFeature[]) => void;
  setScrubberIndex: (i: number) => void;
  stepScrubber: () => void;
  setPlaying: (p: boolean) => void;
  setScrubMode: (m: ScrubMode) => void;
  selectAnomaly: (f: WindowFeature | null) => void;
  setFocusedRegion: (region: { name: string; level: string; center?: [number, number] } | null) => void;
  acknowledge: (clusterId: string) => void;
  recomputeSeverity: () => void;
}


function maxPriority(features: WindowFeature[]): Priority {
  return features.reduce<Priority>(
    (acc, f) => (PRIORITY_RANK[f.properties.priority] > PRIORITY_RANK[acc] ? f.properties.priority : acc),
    "LOW",
  );
}

export function visibleSlice(features: WindowFeature[], idx: number, mode: ScrubMode): WindowFeature[] {
  return features.filter((f) => (mode === "day" ? f.properties.day_index === idx : f.properties.day_index <= idx));
}

export const useAppStore = create<AppState>((set, get) => ({
  isAuthenticated: true,
  login: () => set({ isAuthenticated: true }),
  logout: () => set({ isAuthenticated: false }),

  days: [],
  windowFeatures: [],
  currentTimeScrubberIndex: 6,
  scrubMode: "cumulative",
  isPlaying: false,
  globalSeverityLevel: "LOW",
  selectedAnomaly: null,
  acknowledgedIds: new Set(),
  focusMode: false,
  focusedRegion: null,

  setWindowData: (days, features) => {
    set({ days, windowFeatures: features, currentTimeScrubberIndex: Math.max(days.length - 1, 0) });
    get().recomputeSeverity();
  },
  setScrubberIndex: (i) => {
    const max = Math.max(get().days.length - 1, 0);
    set({ currentTimeScrubberIndex: Math.min(Math.max(i, 0), max) });
    get().recomputeSeverity();
  },
  stepScrubber: () => {
    const { currentTimeScrubberIndex, days } = get();
    get().setScrubberIndex((currentTimeScrubberIndex + 1) % Math.max(days.length, 1));
  },
  setPlaying: (p) => set({ isPlaying: p }),
  setScrubMode: (m) => { set({ scrubMode: m }); get().recomputeSeverity(); },

  selectAnomaly: (f) => set({ selectedAnomaly: f, focusMode: f?.properties.priority === "CRITICAL" }),
    setFocusedRegion: (region) => set({ focusedRegion: region }),
  acknowledge: (id) => {
    const next = new Set(get().acknowledgedIds); next.add(id);
    set({ acknowledgedIds: next });
    get().recomputeSeverity();
  },

  recomputeSeverity: () => {
    const { windowFeatures, currentTimeScrubberIndex, scrubMode, acknowledgedIds } = get();
    const active = visibleSlice(windowFeatures, currentTimeScrubberIndex, scrubMode)
      .filter((f) => !acknowledgedIds.has(f.properties.cluster_id));
    set({ globalSeverityLevel: maxPriority(active) });
  },
}));





import { useDeferredValue } from "react";
export const useVisibleFeatures = () => {
  const [features, rawIdx, mode] = useAppStore(useShallow((s) => [s.windowFeatures, s.currentTimeScrubberIndex, s.scrubMode]));
  const idx = useDeferredValue(rawIdx);
  return useMemo(() => visibleSlice(features, idx, mode), [features, idx, mode]);
};
