import { useMemo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Activity, AlertTriangle, Cpu } from "lucide-react";
import { useHealth, useLiveHotspots, useTelemetry } from "@/api/client";
import type { ThermalClass } from "@/api/types";
import { CLASS_COLORS, CLASS_LABELS } from "@/lib/theme";
import { useAppStore } from "@/store/useAppStore";

export default function BottomHUD() {
  const { data: hotspots, isFetching } = useLiveHotspots();
  const { data: health } = useHealth();
  const selected = useAppStore((s) => s.selectedCluster);
  const selectCluster = useAppStore((s) => s.selectCluster);
  const { data: telemetry } = useTelemetry(selected?.properties.cluster_id ?? null);

  const breakdown = useMemo(() => {
    const counts = new Map<ThermalClass, number>();
    hotspots?.features.forEach((f) => counts.set(f.properties.predicted_class, (counts.get(f.properties.predicted_class) ?? 0) + 1));
    return [...counts.entries()].map(([k, v]) => ({ name: CLASS_LABELS[k], key: k, value: v }));
  }, [hotspots]);

  const risks = useMemo(
    () => (hotspots?.features ?? []).filter((f) => f.properties.m_score > 3.5).sort((a, b) => b.properties.m_score - a.properties.m_score).slice(0, 8),
    [hotspots],
  );

  const shap = telemetry?.shap_waterfall.slice(0, 6) ?? [];
  const shapMax = Math.max(...shap.map((s) => Math.abs(s.shap_value)), 1e-6);
  const total = hotspots?.features.length ?? 0;

  return (
    <footer className="glass absolute bottom-4 left-4 right-4 z-20 grid h-52 grid-cols-3 gap-4 p-3">
      {}
      <section className="flex gap-3">
        <div className="h-full w-40">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={breakdown} dataKey="value" innerRadius={45} outerRadius={70} paddingAngle={3} stroke="none">
                {breakdown.map((d) => <Cell key={d.key} fill={CLASS_COLORS[d.key as ThermalClass]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontFamily: "monospace", fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1">
          <div className="hud-label mb-1">AI Classification</div>
          <div className="hud-value mb-2 neon-cyan">{total} objects</div>
          <ul className="space-y-1">
            {breakdown.map((d) => (
              <li key={d.key} className="flex items-center justify-between font-mono text-[11px]">
                <span className="flex items-center gap-2 text-slate-300">
                  <span className="h-2 w-2 rounded-full" style={{ background: CLASS_COLORS[d.key as ThermalClass], boxShadow: `0 0 6px ${CLASS_COLORS[d.key as ThermalClass]}` }} />
                  {d.name}
                </span>
                <span className="text-slate-100">{d.value}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {}
      <section className="flex flex-col">
        <div className="mb-1 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-hud-red" />
          <span className="hud-label">Anomaly Register · M<sub>i</sub> &gt; 3.5</span>
          <span className="ml-auto rounded bg-hud-red/20 px-1.5 font-mono text-[10px] text-hud-red">{risks.length}</span>
        </div>
        <div className="flex-1 overflow-y-auto pr-1">
          <table className="w-full font-mono text-[11px]">
            <thead className="sticky top-0 bg-slate-900/90 text-slate-500">
              <tr><th className="text-left">ID</th><th className="text-left">Class</th><th className="text-right">M<sub>i</sub></th><th className="text-right">FRP</th><th className="text-right">Pri</th></tr>
            </thead>
            <tbody>
              {risks.map((f) => (
                <tr key={f.properties.cluster_id} onClick={() => selectCluster(f)}
                  className="cursor-pointer border-t border-slate-800/60 text-slate-300 transition hover:bg-slate-800/70">
                  <td className="py-0.5 text-slate-400">{f.properties.cluster_id.slice(0, 8)}</td>
                  <td style={{ color: CLASS_COLORS[f.properties.predicted_class] }}>{f.properties.predicted_class}</td>
                  <td className="text-right text-hud-red">{f.properties.m_score.toFixed(2)}</td>
                  <td className="text-right">{f.properties.frp_mean.toFixed(0)}</td>
                  <td className={`text-right ${f.properties.priority === "CRITICAL" ? "neon-red" : "text-hud-amber"}`}>{f.properties.priority[0]}</td>
                </tr>
              ))}
              {risks.length === 0 && <tr><td colSpan={5} className="py-4 text-center text-slate-500">No active anomalies</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {}
      <section className="flex flex-col">
        <div className="mb-1 flex items-center gap-2">
          <Cpu className="h-4 w-4 text-hud-cyan" />
          <span className="hud-label">Engine Status</span>
          <Activity className={`ml-auto h-3 w-3 ${isFetching ? "animate-pulse text-hud-cyan" : "text-slate-600"}`} />
        </div>
        <div className="mb-2 grid grid-cols-3 gap-2 font-mono text-[11px]">
          <Stat label="Backend" value={health?.status === "ok" ? "ONLINE" : "OFFLINE"} tone={health?.status === "ok" ? "cyan" : "red"} />
          <Stat label="Ingest" value={(health?.ingest_mode ?? "—").toUpperCase()} tone={health?.ingest_mode === "live" ? "cyan" : "amber"} />
          <Stat label="Model" value="LGBM+SHAP" tone="cyan" />
        </div>
        <div className="hud-label mb-1">{selected ? `SHAP · ${selected.properties.cluster_id.slice(0, 8)}` : "SHAP · select a node"}</div>
        <div className="flex-1 space-y-1 overflow-hidden">
          {shap.map((s) => (
            <div key={s.feature} className="flex items-center gap-2 font-mono text-[10px]">
              <span className="w-28 truncate text-slate-400">{s.feature}</span>
              <div className="relative h-2 flex-1 rounded bg-slate-800">
                <div className="absolute top-0 h-2 rounded"
                  style={{ width: `${(Math.abs(s.shap_value) / shapMax) * 100}%`, background: s.shap_value >= 0 ? "#ef4444" : "#22d3ee", boxShadow: `0 0 6px ${s.shap_value >= 0 ? "#ef4444" : "#22d3ee"}` }} />
              </div>
              <span className={`w-12 text-right ${s.shap_value >= 0 ? "text-hud-red" : "text-hud-cyan"}`}>{s.shap_value.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </section>
    </footer>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: "cyan" | "amber" | "red" }) {
  const cls = tone === "cyan" ? "neon-cyan" : tone === "amber" ? "neon-amber" : "neon-red";
  return (
    <div className="rounded border border-slate-800 bg-slate-950/50 p-1.5">
      <div className="hud-label">{label}</div>
      <div className={`font-mono text-xs font-bold ${cls}`}>{value}</div>
    </div>
  );
}
