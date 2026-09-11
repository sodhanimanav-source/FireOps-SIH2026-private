import { useMemo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { PieChart as PieIcon } from "lucide-react";
import type { ThermalClass } from "@/api/types";
import { CLASS_COLORS, CLASS_LABELS } from "@/lib/theme";
import { SEVERITY_THEMES } from "@/lib/severityTheme";
import { useAppStore, visibleSlice } from "@/store/useAppStore";

export default function AnalyticsPanel() {
  const windowFeatures = useAppStore((s) => s.windowFeatures);
  const idx = useAppStore((s) => s.currentTimeScrubberIndex);
  const scrubMode = useAppStore((s) => s.scrubMode);
  const visible = useMemo(() => visibleSlice(windowFeatures, idx, scrubMode), [windowFeatures, idx, scrubMode]);
  const theme = SEVERITY_THEMES[useAppStore((s) => s.globalSeverityLevel)];

  const breakdown = useMemo(() => {
    const m = new Map<ThermalClass, number>();
    visible.forEach((f) => m.set(f.properties.predicted_class, (m.get(f.properties.predicted_class) ?? 0) + 1));
    return [...m.entries()].map(([k, v]) => ({ key: k, name: CLASS_LABELS[k], value: v }));
  }, [visible]);

  return (
    <section className={`flex h-full flex-col rounded-xl border ${theme.panel} ${theme.border}`}>
      <header className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
        <PieIcon className={`h-4 w-4 ${theme.accent}`} />
        <div className="text-[10px] uppercase tracking-[0.2em] text-slate-300">Classification Breakdown</div>
      </header>
      <div className="flex flex-1 items-center gap-3 p-3">
        <div className="h-full w-1/2">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={breakdown} dataKey="value" innerRadius="55%" outerRadius="85%" paddingAngle={3} stroke="none">
                {breakdown.map((d) => <Cell key={d.key} fill={CLASS_COLORS[d.key]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontFamily: "monospace", fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="flex-1 space-y-1 text-[11px]">
          {breakdown.map((d) => (
            <li key={d.key} className="flex justify-between">
              <span className="flex items-center gap-2 text-slate-300"><span className="h-2 w-2 rounded-full" style={{ background: CLASS_COLORS[d.key] }} />{d.name}</span>
              <span>{d.value}</span>
            </li>
          ))}
          {breakdown.length === 0 && <li className="text-slate-500">No objects in window</li>}
        </ul>
      </div>
    </section>
  );
}
