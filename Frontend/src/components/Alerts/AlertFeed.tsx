import { useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, BellOff } from "lucide-react";
import { CLASS_COLORS, PRIORITY_COLORS } from "@/lib/theme";
import { PRIORITY_RANK, SEVERITY_THEMES } from "@/lib/severityTheme";
import { useAppStore, visibleSlice } from "@/store/useAppStore";

export default function AlertFeed() {
  const windowFeatures = useAppStore((s) => s.windowFeatures);
  const idx = useAppStore((s) => s.currentTimeScrubberIndex);
  const scrubMode = useAppStore((s) => s.scrubMode);
  const visible = useMemo(() => visibleSlice(windowFeatures, idx, scrubMode), [windowFeatures, idx, scrubMode]);
  const acked = useAppStore((s) => s.acknowledgedIds);
  const acknowledge = useAppStore((s) => s.acknowledge);
  const select = useAppStore((s) => s.selectAnomaly);
  const selected = useAppStore((s) => s.selectedAnomaly);
  const theme = SEVERITY_THEMES[useAppStore((s) => s.globalSeverityLevel)];

  const alerts = useMemo(() =>
    visible.filter((f) => f.properties.m_score > 3.5 || PRIORITY_RANK[f.properties.priority] >= 2)
      .sort((a, b) => PRIORITY_RANK[b.properties.priority] - PRIORITY_RANK[a.properties.priority] || b.properties.m_score - a.properties.m_score),
    [visible]);

  return (
    <section className={`flex h-full min-h-0 flex-col rounded-xl border ${theme.panel} ${theme.border} ${theme.glow}`}>
      <header className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
        <Bell className={`h-4 w-4 ${theme.accent} ${theme.pulse ? "animate-bounce" : ""}`} />
        <div className="text-[10px] uppercase tracking-[0.2em] text-slate-300">Context-Aware Alert Feed</div>
        <span className="ml-auto rounded bg-white/10 px-1.5 text-[10px]">{alerts.filter((a) => !acked.has(a.properties.cluster_id)).length}</span>
      </header>
      <ul className="flex-1 space-y-1.5 overflow-y-auto p-2">
        <AnimatePresence initial={false}>
          {alerts.map((f) => {
            const p = f.properties; const isAck = acked.has(p.cluster_id); const isSel = selected?.properties.cluster_id === p.cluster_id;
            return (
              <motion.li key={p.cluster_id} layout initial={{ opacity: 0, x: 24 }} animate={{ opacity: isAck ? 0.4 : 1, x: 0 }} exit={{ opacity: 0, x: 24 }}
                onClick={() => select(f)}
                className={`cursor-pointer rounded-lg border p-2 text-[11px] transition ${isSel ? "border-white/60 bg-white/10" : "border-white/10 hover:bg-white/5"}`}
                style={{ borderLeft: `3px solid ${PRIORITY_COLORS[p.priority]}` }}>
                <div className="flex items-center justify-between">
                  <span className="font-bold" style={{ color: CLASS_COLORS[p.predicted_class] }}>{p.predicted_class}</span>
                  <span style={{ color: PRIORITY_COLORS[p.priority] }}>{p.priority}</span>
                </div>
                <div className="flex items-center justify-between text-slate-400">
                  <span>{p.cluster_id.slice(0, 8)} · {p.acq_date}</span>
                  <span>Mᵢ <b className="text-red-400">{p.m_score.toFixed(1)}</b> · {p.frp_max.toFixed(0)} MW</span>
                </div>
                {p.methane_venting_suspected && <div className="mt-1 text-[10px] text-amber-400">⚠ methane venting suspected</div>}
                {!isAck && (
                  <button onClick={(e) => { e.stopPropagation(); acknowledge(p.cluster_id); }}
                    className="mt-1 flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-200"><BellOff className="h-3 w-3" /> acknowledge</button>
                )}
              </motion.li>
            );
          })}
        </AnimatePresence>
        {alerts.length === 0 && <li className="p-4 text-center text-[11px] text-slate-500">All quiet in this window.</li>}
      </ul>
    </section>
  );
}
