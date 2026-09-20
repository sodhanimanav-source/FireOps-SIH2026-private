/**
 * Severity-reactive theming for the command dashboard.
 *
 * The whole console shifts colour with the worst active incident, so an
 * operator glancing at the screen from across a room can read the situation
 * before reading any text. `globalSeverityLevel` in the app store drives it;
 * every panel pulls its chrome from the matching entry here.
 *
 * Values are Tailwind utility class strings (composed into `className`), with
 * the exception of `accentHex` and `ambient`, which are raw CSS colours used
 * in inline styles and on the SVG connectors.
 */

import type { Priority } from "@/api/types";

export interface SeverityTheme {
  /** Root background wash for the whole application shell. */
  root: string;
  /** Panel surface — every card and sidebar uses this. */
  panel: string;
  /** Panel border colour. */
  border: string;
  /** Accent text colour for icons and headings. */
  accent: string;
  /** Same accent as a raw hex, for inline styles and SVG strokes. */
  accentHex: string;
  /** Outer glow on panels; intensifies with severity. */
  glow: string;
  /** Whether alert icons should animate. Only true when action is needed. */
  pulse: boolean;
  /** Radial ambient wash behind the map, as an rgba() string. */
  ambient: string;
}

/**
 * Ordering used to rank and sort incidents.
 *
 * AlertFeed treats `>= 2` as "worth surfacing", so HIGH and CRITICAL reach
 * the operator's queue while LOW and MEDIUM stay on the map only.
 */
export const PRIORITY_RANK: Record<Priority, number> = {
  LOW: 0,
  MEDIUM: 1,
  HIGH: 2,
  CRITICAL: 3,
};

export const SEVERITY_THEMES: Record<Priority, SeverityTheme> = {
  // Nominal — calm cyan, nothing demanding attention.
  LOW: {
    root: "bg-[#070d1e]",
    panel: "bg-slate-900/60 backdrop-blur-sm",
    border: "border-cyan-500/25",
    accent: "text-hud-cyan",
    accentHex: "#22d3ee",
    glow: "shadow-glow-cyan",
    pulse: false,
    ambient: "rgba(34,211,238,0.10)",
  },

  // Elevated — amber. Something is off but not yet urgent.
  MEDIUM: {
    root: "bg-[#0b0f1a]",
    panel: "bg-slate-900/65 backdrop-blur-sm",
    border: "border-amber-500/30",
    accent: "text-hud-amber",
    accentHex: "#f59e0b",
    glow: "shadow-glow-amber",
    pulse: false,
    ambient: "rgba(245,158,11,0.12)",
  },

  // Urgent — orange, and icons begin to move.
  HIGH: {
    root: "bg-[#120c0a]",
    panel: "bg-orange-950/40 backdrop-blur-sm",
    border: "border-orange-500/45",
    accent: "text-orange-400",
    accentHex: "#fb923c",
    glow: "shadow-glow-amber",
    pulse: true,
    ambient: "rgba(251,146,60,0.16)",
  },

  // Emergency — red everywhere, maximum glow.
  CRITICAL: {
    root: "bg-[#150708]",
    panel: "bg-red-950/40 backdrop-blur-sm",
    border: "border-red-500/60",
    accent: "text-hud-red",
    accentHex: "#ef4444",
    glow: "shadow-glow-red",
    pulse: true,
    ambient: "rgba(239,68,68,0.20)",
  },
};

/** The worst priority in a set — used to derive the global severity level. */
export function maxPriority(priorities: Priority[]): Priority {
  return priorities.reduce<Priority>(
    (worst, p) => (PRIORITY_RANK[p] > PRIORITY_RANK[worst] ? p : worst),
    "LOW",
  );
}
