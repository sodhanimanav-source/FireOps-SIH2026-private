import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { X, Zap, Wind, ShieldAlert } from "lucide-react";
import { useIncidentCard, useTelemetry } from "@/api/client";
import { CLASS_COLORS, PRIORITY_COLORS } from "@/lib/theme";
import { useAppStore } from "@/store/useAppStore";

export default function TelemetryDrawer() {
  const open = useAppStore((s) => s.drawerOpen);
  const selected = useAppStore((s) => s.selectedCluster);
  const close = useAppStore((s) => s.closeDrawer);
  const enqueueHitl = useAppStore((s) => s.enqueueHitl);

  const clusterId = selected?.properties.cluster_id ?? null;
  const { data: telemetry, isFetching: telLoading } = useTelemetry(clusterId);
  const { data: card } = useIncidentCard(clusterId);

  
  const probs = useMemo(() => {
    if (!telemetry) return [];
    return Object.entries(telemetry.probabilities)
      .map(([k, v]) => ({ class: k, p: v }))
      .sort((a, b) => b.p - a.p);
  }, [telemetry]);

  if (!open || !selected) return null;
  const p = selected.properties;
  const cColor = CLASS_COLORS[p.predicted_class];

  return (
    <div className="glass absolute bottom-60 right-4 top-20 z-30 flex w-96 flex-col overflow-hidden shadow-2xl transition-transform duration-300">
      {}
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900/90 p-3">
        <div>
          <div className="hud-label mb-1">Target Acquired</div>
          <div className="font-mono text-sm font-bold text-slate-100">{p.cluster_id}</div>
        </div>
        <button onClick={close} className="text-slate-400 transition hover:text-slate-100">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {}
        <section>
          <div className="mb-2 flex items-center gap-2">
            <Zap className="h-4 w-4" style={{ color: cColor }} />
            <span className="font-mono text-xs font-bold uppercase" style={{ color: cColor }}>
              {p.predicted_class}
            </span>
          </div>
          <div className="space-y-1">
            {probs.map((prob) => (
              <div key={prob.class} className="flex items-center gap-2 font-mono text-[10px]">
                <span className="w-32 truncate text-slate-400">{prob.class}</span>
                <div className="relative h-1.5 flex-1 rounded-full bg-slate-800">
                  <div className="absolute top-0 h-1.5 rounded-full"
                    style={{ width: (prob.p * 100) + "%", background: CLASS_COLORS[prob.class as keyof typeof CLASS_COLORS] }} />
                </div>
                <span className="w-8 text-right text-slate-300">{(prob.p * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </section>

        {}
        <section>
          <div className="hud-label mb-2">FRP Telemetry (48h)</div>
          <div className="h-32 rounded border border-slate-800 bg-slate-950 p-2">
            {telLoading ? (
              <div className="flex h-full items-center justify-center font-mono text-xs text-slate-500 animate-pulse">LINKING SATELLITE...</div>
            ) : telemetry?.series ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={telemetry.series}>
                  <defs>
                    <linearGradient id="frpGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={cColor} stopOpacity={0.4} />
                      <stop offset="95%" stopColor={cColor} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 9, fontFamily: "monospace" }} tickFormatter={(v) => v.slice(11, 16)} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 9, fontFamily: "monospace" }} width={25} />
                  <Tooltip
                    contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontFamily: "monospace", fontSize: 10 }}
                    labelFormatter={(v) => "T: " + v}
                  />
                  <ReferenceLine y={telemetry.band_upper} stroke="#ef4444" strokeDasharray="3 3" />
                  <Area type="monotone" dataKey="frp" stroke={cColor} strokeWidth={2} fill="url(#frpGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : null}
          </div>
        </section>

        {}
        {card && (
          <section className="rounded border border-hud-amber/30 bg-hud-amber/5 p-3">
            <div className="mb-2 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-hud-amber" />
              <span className="font-mono text-xs font-bold text-hud-amber">TACTICAL TRIAGE</span>
              <span className="ml-auto font-mono text-[10px] font-bold uppercase text-slate-100"
                style={{ color: PRIORITY_COLORS[card.asset_risk_level] }}>
                {card.asset_risk_level} RISK
              </span>
            </div>
            <p className="mb-3 font-mono text-[11px] text-slate-300">{card.recommended_action}</p>

            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <div className="hud-label">Wind Vector</div>
                <div className="flex items-center gap-1 font-mono text-xs text-slate-100">
                  <Wind className="h-3 w-3 text-hud-cyan" /> {card.wind.dir_deg}° at {card.wind.speed_ms}m/s
                </div>
              </div>
              <div>
                <div className="hud-label">Cryo Override</div>
                <div className={"font-mono text-xs " + (card.cryogenic_override ? "text-hud-red" : "text-hud-cyan")}>
                  {card.cryogenic_override ? "ENGAGED" : "STANDBY"}
                </div>
              </div>
            </div>

            <div className="hud-label mb-1">Response Units ETA</div>
            <ul className="space-y-1 font-mono text-[10px] text-slate-300">
              {card.fire_stations.map((s, i) => (
                <li key={i} className="flex justify-between border-b border-slate-800/50 pb-1">
                  <span className="truncate pr-2">{s.name}</span>
                  <span className="text-hud-amber">{s.eta_min}m</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {}
      <div className="border-t border-slate-800 bg-slate-900/90 p-3 flex gap-2">
        <button
          onClick={() => { enqueueHitl(selected); close(); }}
          className="flex-1 rounded border border-hud-red bg-hud-red/10 py-1.5 font-mono text-[11px] font-bold text-hud-red transition hover:bg-hud-red/20 hover:shadow-glow-red"
        >
          ESCALATE TO HITL
        </button>
      </div>
    </div>
  );
}