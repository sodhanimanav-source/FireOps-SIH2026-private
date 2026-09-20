/**
 * Classification palette and labels.
 *
 * Colours are kept deliberately in sync with the backend's `color_map` in
 * `backend_files/backend/main.py`, so a cluster rendered on the map matches
 * the colour the API assigns it. If you change one, change the other.
 */

import type { Priority, ThermalClass } from "@/api/types";

/** Marker / text colour for each thermal classification. */
export const CLASS_COLORS: Record<ThermalClass, string> = {
  // Industrial family — ambers through reds, escalating with severity.
  ROUTINE_FLARING: "#FFB300",      // routine, expected operation
  FLARE_SPIKE: "#FF8F00",          // excursion above the site's own baseline
  INDUSTRIAL_ACCIDENT: "#F44336",  // unplanned combustion — highest priority
  COAL_MINE_FIRE: "#D32F2F",       // persistent subsurface seam fire

  // Biomass family — warmer yellows, visually distinct from industry.
  AGRICULTURAL_BURNING: "#FFC107",
  WILDFIRE_AGRI: "#FF7043",
  WILDFIRE: "#FF5722",

  // No verdict yet.
  UNLABELED: "#9E9E9E",
};

/** Human-readable label shown in panels and incident cards. */
export const CLASS_LABELS: Record<ThermalClass, string> = {
  ROUTINE_FLARING: "Routine Gas Flaring",
  FLARE_SPIKE: "Abnormal Flare Spike",
  INDUSTRIAL_ACCIDENT: "Industrial Accident / Refinery Fire",
  COAL_MINE_FIRE: "Coal Mine Fire",
  AGRICULTURAL_BURNING: "Agricultural Burning",
  WILDFIRE_AGRI: "Agricultural Wildfire",
  WILDFIRE: "Wildfire",
  UNLABELED: "Unclassified Thermal Source",
};

/**
 * Priority colours.
 *
 * Indexed with `Priority`, but the triage card can also report transient
 * states such as "EVALUATING" while the pipeline is still working, so the
 * record is widened and every lookup falls back to slate.
 */
export const PRIORITY_COLORS: Record<Priority | string, string> = {
  LOW: "#22d3ee",       // hud-cyan
  MEDIUM: "#f59e0b",    // hud-amber
  HIGH: "#fb923c",
  CRITICAL: "#ef4444",  // hud-red
  EVALUATING: "#94a3b8",
  UNKNOWN: "#94a3b8",
};

/**
 * MapLibre data-driven expression colouring each hotspot by its class.
 *
 * Used for both the halo and core circle layers in the tactical map, so the
 * two always agree. The trailing value is the fallback for any class the
 * frontend does not know about yet — which matters, because the backend can
 * add classifications before the UI is updated.
 */
export const CLASS_MATCH_EXPR: (string | string[])[] = [
  "match",
  ["get", "predicted_class"],
  "ROUTINE_FLARING", CLASS_COLORS.ROUTINE_FLARING,
  "FLARE_SPIKE", CLASS_COLORS.FLARE_SPIKE,
  "INDUSTRIAL_ACCIDENT", CLASS_COLORS.INDUSTRIAL_ACCIDENT,
  "COAL_MINE_FIRE", CLASS_COLORS.COAL_MINE_FIRE,
  "AGRICULTURAL_BURNING", CLASS_COLORS.AGRICULTURAL_BURNING,
  "WILDFIRE_AGRI", CLASS_COLORS.WILDFIRE_AGRI,
  "WILDFIRE", CLASS_COLORS.WILDFIRE,
  CLASS_COLORS.UNLABELED,
];
