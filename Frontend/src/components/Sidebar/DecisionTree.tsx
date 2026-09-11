import { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BrainCircuit, Check, X as XIcon, ArrowDown } from "lucide-react";
import { useTelemetry } from "@/api/client";
import type { ShapItem, ThermalClass, WindowClusterProperties } from "@/api/types";
import { CLASS_COLORS, CLASS_LABELS } from "@/lib/theme";
import { SEVERITY_THEMES } from "@/lib/severityTheme";
import { useAppStore } from "@/store/useAppStore";

type Op = ">" | ">=" | "<" | "<=";
interface RuleNode { feature: keyof WindowClusterProperties | "dist_refinery_m" | "dist_mine_m" | "inside_industrial" | "lc_natural"; label: string; op: Op; threshold: number; unit?: string; }


const RULE_PATHS: Record<ThermalClass, RuleNode[]> = {
  FLARE_SPIKE: [
    { feature: "m_score", label: "Modified Z-score Mᵢ", op: ">", threshold: 3.5 },
    { feature: "dist_refinery_m", label: "Distance to refinery", op: "<", threshold: 2000, unit: "m" },
    { feature: "night_frac", label: "Night fraction", op: ">", threshold: 0.4 },
    { feature: "p_idx", label: "Persistence P_idx", op: ">=", threshold: 0.5 },
  ],
  ROUTINE_FLARING: [
    { feature: "p_idx", label: "Persistence P_idx", op: ">=", threshold: 0.5 },
    { feature: "night_frac", label: "Night fraction", op: ">", threshold: 0.4 },
    { feature: "dist_refinery_m", label: "Distance to refinery", op: "<", threshold: 2000, unit: "m" },
    { feature: "m_score", label: "Modified Z-score Mᵢ", op: "<=", threshold: 3.5 },
  ],
  INDUSTRIAL_ACCIDENT: [
    { feature: "inside_industrial", label: "Inside industrial land-use", op: ">=", threshold: 1 },
    { feature: "p_idx", label: "Historical persistence", op: "<", threshold: 0.15 },
    { feature: "m_score", label: "Sudden FRP surge Mᵢ", op: ">", threshold: 3.5 },
  ],
  COAL_MINE_FIRE: [
    { feature: "dist_mine_m", label: "Distance to mine/quarry", op: "<", threshold: 1000, unit: "m" },
    { feature: "p_idx", label: "Moderate persistence", op: ">=", threshold: 0.2 },
    { feature: "vnf_temp_k", label: "Smoldering temperature", op: "<=", threshold: 750, unit: "K" },
  ],
  WILDFIRE_AGRI: [
    { feature: "lc_natural", label: "Non-industrial land cover", op: ">", threshold: 0.6 },
    { feature: "drift_velocity_mpd", label: "Centroid drift", op: ">", threshold: 200, unit: "m/day" },
    { feature: "p_idx", label: "Low persistence", op: "<", threshold: 0.3 },
  ],
  UNLABELED: [],
};

const cmp = (v: number, op: Op, t: number) => (op === ">" ? v > t : op === ">=" ? v >= t : op === "<" ? v < t : v <= t);

export default function DecisionTreeSidebar() {
  const selected = useAppStore((s) => s.selectedAnomaly);
  const theme = SEVERITY_THEMES[useAppStore((s) => s.globalSeverityLevel)];
  const { data: telemetry } = useTelemetry(selected?.properties.cluster_id ?? null);

  const nodes = useMemo(() => {
    if (!selected) return [];
    const p = selected.properties as any;
    const shapByFeature = new Map<string, ShapItem>((telemetry?.shap_waterfall ?? []).map((s) => [s.feature, s]));
    const shapMax = Math.max(1e-6, ...(telemetry?.shap_waterfall ?? []).map((s) => Math.abs(s.shap_value)));
    const rules = RULE_PATHS[selected.properties.predicted_class] || []; return rules.map((r) => {
      const shap = shapByFeature.get(r.feature);
      const raw = p[r.feature] ?? shap?.value;
      const value = typeof raw === "boolean" ? (raw ? 1 : 0) : Number(raw);
      return { ...r, value, shap, pass: Number.isFinite(value) ? cmp(value, r.op, r.threshold) : false, weight: shap ? Math.abs(shap.shap_value) / shapMax : 0 };
    });
  }, [selected, telemetry]);

  return (
    <section className={`flex h-full flex-col rounded-xl border ${theme.panel} ${theme.border} ${theme.glow}`}>
      <header className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
        <BrainCircuit className={`h-4 w-4 ${theme.accent}`} />
        <div className="text-[10px] uppercase tracking-[0.2em] text-slate-300">Explainable AI · Decision Path</div>
      </header>

      <div className="flex-1 overflow-y-auto p-4">
        <AnimatePresence mode="wait">
          {!selected ? (
            <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="flex h-full items-center justify-center text-center text-[11px] text-slate-500">
              Select a hotspot on the map to trace the LightGBM decision path.
            </motion.div>
          ) : (
            <motion.div key={selected.properties.cluster_id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="relative">
              {}
              <Node delay={0}>
                <div className="text-[10px] uppercase text-slate-400">Input object</div>
                <div className="text-xs font-bold">{selected.properties.cluster_id}</div>
                <div className="text-[10px] text-slate-400">{selected.properties.n_detections} detections · FRP {selected.properties.frp_mean.toFixed(1)} MW</div>
              </Node>

              {nodes.map((n, i) => (
                <div key={n.feature}>
                  <Connector delay={0.1 + i * 0.15} color={n.pass ? theme.accentHex : "#64748b"} />
                  <Node delay={0.15 + i * 0.15} tone={n.pass ? "pass" : "fail"}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-[10px] uppercase text-slate-400">{n.label}</div>
                        <div className="text-xs font-bold">
                          {n.feature === "inside_industrial" ? (n.value ? "TRUE" : "FALSE") : `${fmt(n.value)}${n.unit ? " " + n.unit : ""}`}
                          <span className="text-slate-500"> {n.op} {n.feature === "inside_industrial" ? "TRUE" : `${n.threshold}${n.unit ? " " + n.unit : ""}`}</span>
                        </div>
                      </div>
                      {n.pass ? <Check className="h-4 w-4 shrink-0 text-emerald-400" /> : <XIcon className="h-4 w-4 shrink-0 text-slate-500" />}
                    </div>
                    {n.shap && (
                      <div className="mt-1.5 flex items-center gap-2 text-[10px]">
                        <span className="text-slate-500">SHAP</span>
                        <div className="h-1 flex-1 rounded bg-slate-800">
                          <motion.div className="h-1 rounded" initial={{ width: 0 }} animate={{ width: `${n.weight * 100}%` }}
                            style={{ background: n.shap.shap_value >= 0 ? "#ef4444" : "#22d3ee" }} transition={{ delay: 0.3 + i * 0.15 }} />
                        </div>
                        <span className={n.shap.shap_value >= 0 ? "text-red-400" : "text-cyan-400"}>{n.shap.shap_value >= 0 ? "+" : ""}{n.shap.shap_value.toFixed(2)}</span>
                      </div>
                    )}
                  </Node>
                </div>
              ))}

              <Connector delay={0.2 + nodes.length * 0.15} color={CLASS_COLORS[selected.properties.predicted_class as ThermalClass] || "#94a3b8"} />
              <Node delay={0.25 + nodes.length * 0.15} tone="outcome" color={CLASS_COLORS[selected.properties.predicted_class as ThermalClass] || "#94a3b8"}>
                <div className="text-[10px] uppercase text-slate-300">Outcome</div>
                <div className="text-sm font-bold" style={{ color: CLASS_COLORS[selected.properties.predicted_class as ThermalClass] || "#94a3b8" }}>
                  {(CLASS_LABELS[selected.properties.predicted_class as ThermalClass] || selected.properties.predicted_class || "UNKNOWN").toUpperCase()}
                </div>
                <div className="text-[10px] text-slate-300">
                  confidence {((selected.properties.probabilities?.[selected.properties.predicted_class] ?? 0) * 100).toFixed(0)}% · priority {selected.properties.priority}
                </div>
              </Node>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}

function fmt(v: number) { return Number.isFinite(v) ? (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2)) : "n/a"; }

function Node({ children, delay, tone = "neutral", color }: { children: React.ReactNode; delay: number; tone?: "neutral" | "pass" | "fail" | "outcome"; color?: string }) {
  const cls = tone === "pass" ? "border-emerald-500/50 bg-emerald-500/5"
    : tone === "fail" ? "border-slate-700 bg-slate-900/40 opacity-70"
    : tone === "outcome" ? "border-2 bg-slate-950/70" : "border-slate-600 bg-slate-900/60";
  return (
    <motion.div initial={{ opacity: 0, y: -8, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ delay, duration: 0.3 }}
      className={`rounded-lg border p-3 ${cls}`} style={tone === "outcome" && color ? { borderColor: color, boxShadow: `0 0 18px ${color}66` } : undefined}>
      {children}
    </motion.div>
  );
}

function Connector({ delay, color }: { delay: number; color: string }) {
  return (
    <motion.svg width="100%" height="28" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay }} className="block">
      <motion.line x1="50%" y1="0" x2="50%" y2="20" stroke={color} strokeWidth="2" strokeDasharray="4 3"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay, duration: 0.3 }} />
      <ArrowDown x="calc(50% - 6px)" y="14" width="12" height="12" style={{ color }} />
    </motion.svg>
  );
}
