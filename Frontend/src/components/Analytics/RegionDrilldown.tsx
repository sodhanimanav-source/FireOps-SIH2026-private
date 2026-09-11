import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ChevronRight, MapPinned } from "lucide-react";
import { api } from "@/api/client";
import { useAppStore } from "@/store/useAppStore";
import { SEVERITY_THEMES } from "@/lib/severityTheme";

type Level = "state" | "district" | "subdistrict";
interface Row { name: string; objects: number; anomalies: number; frp_total: number; max_m: number; critical: number; classes: Record<string, number>; center_lat?: number; center_lon?: number; }
const NEXT: Record<Level, Level | null> = { state: "district", district: "subdistrict", subdistrict: null };

export default function RegionDrilldown({ onFocusRegion }: { onFocusRegion?: (name: string, level: Level, center?: [number, number]) => void }) {
  const [path, setPath] = useState<{ level: Level; parent: string | null }[]>([{ level: "state", parent: null }]);
  const cur = path[path.length - 1];
  const idx = useAppStore((s) => s.currentTimeScrubberIndex);
  const mode = useAppStore((s) => s.scrubMode);
  const theme = SEVERITY_THEMES[useAppStore((s) => s.globalSeverityLevel)];

  const { data } = useQuery({
    queryKey: ["regions", cur.level, cur.parent, mode === "day" ? idx : `cum-${idx}`],
    queryFn: async () => (await api.get<{ rows: Row[] }>("/api/v1/regions/summary", { params: { level: cur.level, parent: cur.parent, day_index: idx, cumulative: mode === "cumulative" } })).data.rows,
    staleTime: 60_000,
  });
  const max = Math.max(1, ...(data ?? []).map((r) => r.objects));

  return (
    <section className={`flex h-full flex-col rounded-xl border ${theme.panel} ${theme.border}`}>
      <header className="flex items-center gap-1 border-b border-white/10 px-3 py-2 text-[10px] uppercase tracking-widest">
        <MapPinned className={`mr-1 h-4 w-4 ${theme.accent}`} />
        <button onClick={() => setPath([{ level: "state", parent: null }])} className="hover:text-cyan-300">India</button>
        {path.slice(1).map((p, i) => (
          <span key={i} className="flex items-center gap-1">
            <ChevronRight className="h-3 w-3 text-slate-500" />
            <button onClick={() => setPath(path.slice(0, i + 2))} className="hover:text-cyan-300">{p.parent}</button>
          </span>
        ))}
      </header>
      <div className="flex-1 overflow-y-auto p-2">
        <table className="w-full text-[11px]">
          <thead className="text-slate-500"><tr><th className="text-left font-normal pb-2">{cur.level}</th><th className="text-right font-normal pb-2">Obj</th><th className="text-right font-normal pb-2">⚠</th><th className="text-right font-normal pb-2">MW</th></tr></thead>
          <tbody>
            {data?.map((r, i) => (
              <motion.tr key={r.name} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}
                onClick={() => { onFocusRegion?.(r.name, cur.level, (r.center_lon && r.center_lat) ? [r.center_lon, r.center_lat] : undefined); const n = NEXT[cur.level]; if (n) setPath([...path, { level: n, parent: r.name }]); }}
                className="cursor-pointer border-t border-white/5 hover:bg-white/5">
                <td className="relative py-1.5 pr-2">
                  <div className="absolute inset-y-1 left-0 rounded bg-cyan-400/10" style={{ width: `${(r.objects / max) * 100}%` }} />
                  <span className="relative ml-1">{r.name}</span>
                  {r.critical > 0 && <span className="relative ml-2 rounded bg-red-500/30 px-1 text-[9px] text-red-300">CRIT {r.critical}</span>}
                </td>
                <td className="text-right tabular-nums">{r.objects}</td>
                <td className={`text-right tabular-nums ${r.anomalies ? "text-amber-400" : "text-slate-500"}`}>{r.anomalies}</td>
                <td className="text-right tabular-nums text-slate-400">{r.frp_total.toFixed(0)}</td>
              </motion.tr>
            ))}
            {!data?.length && (
                <tr><td colSpan={4} className="text-center text-slate-500 pt-4 text-xs">No active hotspots</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
