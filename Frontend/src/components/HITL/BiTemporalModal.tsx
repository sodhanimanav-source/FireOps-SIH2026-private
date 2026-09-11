import { useMemo, useState } from "react";
import maplibregl, { Map as MLMap } from "maplibre-gl";
import { CheckCircle2, ChevronRight, Maximize2, ShieldAlert } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { IMAGERY_ONLY_STYLE } from "@/lib/mapStyles";
import { CLASS_LABELS } from "@/lib/theme";

export default function BiTemporalModal() {
  const activeId = useAppStore((s) => s.hitlActiveId);
  const queue = useAppStore((s) => s.hitlQueue);
  const resolve = useAppStore((s) => s.resolveHitl);
  const close = useAppStore((s) => s.closeHitl);

  const activeNode = useMemo(() => queue.find((q) => q.properties.cluster_id === activeId), [queue, activeId]);
  const [synced, setSynced] = useState(true);

  if (!activeNode) return null;
  const p = activeNode.properties;
  const coords = (activeNode.geometry as any).coordinates as [number, number];

  
  const syncMaps = (map1: MLMap, map2: MLMap) => {
    const handleMove = () => {
      if (!synced) return;
      map2.jumpTo({ center: map1.getCenter(), zoom: map1.getZoom(), bearing: map1.getBearing(), pitch: map1.getPitch() });
    };
    map1.on("move", handleMove);
    return () => map1.off("move", handleMove);
  };

  const initMap = (el: HTMLDivElement | null, dateStr: string, isLeft: boolean) => {
    if (!el) return;
    const map = new maplibregl.Map({
      container: el, style: IMAGERY_ONLY_STYLE,
      center: coords, zoom: 16, attributionControl: false, interactive: isLeft || !synced,
    });
    
    map.on("load", () => {
      map.addSource("dot", { type: "geojson", data: activeNode as any });
      map.addLayer({ id: "dot", type: "circle", source: "dot",
        paint: { "circle-color": "#ef4444", "circle-radius": 8, "circle-stroke-width": 2, "circle-stroke-color": "#fff" } });
    });
    return map;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
      <div className="glass flex h-[85vh] w-[90vw] flex-col overflow-hidden border-hud-cyan/30 shadow-glow-cyan">
        
        {}
        <header className="flex items-center justify-between border-b border-slate-700/50 bg-slate-900 p-4">
          <div className="flex items-center gap-3">
            <ShieldAlert className="h-5 w-5 text-hud-red" />
            <div>
              <div className="font-mono text-sm font-bold text-slate-100">HITL REVIEW REQUIRED</div>
              <div className="hud-label">{p.cluster_id} · {CLASS_LABELS[p.predicted_class]}</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="font-mono text-xs text-slate-400">{queue.length} in queue</div>
            <button onClick={close} className="text-slate-400 hover:text-slate-100"><Maximize2 className="h-5 w-5" /></button>
          </div>
        </header>

        {}
        <div className="flex flex-1 overflow-hidden">
          {}
          <div className="flex flex-1 gap-2 bg-slate-950 p-2">
            <div className="relative flex-1 rounded border border-slate-800">
              <div className="absolute left-2 top-2 z-10 rounded bg-slate-900/80 px-2 py-1 font-mono text-[10px] text-slate-300">T-minus 7 days (Archive)</div>
              <div className="h-full w-full" ref={(el) => { if (el && !el.hasChildNodes()) initMap(el, "arch", true); }} />
            </div>
            <div className="relative flex-1 rounded border border-hud-red/30 shadow-glow-red">
              <div className="absolute left-2 top-2 z-10 rounded bg-hud-red/20 px-2 py-1 font-mono text-[10px] text-hud-red">T-zero (Live)</div>
              <div className="h-full w-full" ref={(el) => { if (el && !el.hasChildNodes()) initMap(el, "live", false); }} />
            </div>
          </div>

          {}
          <div className="w-80 border-l border-slate-700/50 bg-slate-900 p-4">
            <div className="hud-label mb-4">Anomaly Details</div>
            <div className="space-y-3 font-mono text-xs text-slate-300">
              <div className="flex justify-between border-b border-slate-800 pb-1">
                <span className="text-slate-500">M_score</span>
                <span className="font-bold text-hud-red">{p.m_score.toFixed(2)}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800 pb-1">
                <span className="text-slate-500">FRP Max</span>
                <span>{p.frp_max.toFixed(1)} MW</span>
              </div>
              <div className="flex justify-between border-b border-slate-800 pb-1">
                <span className="text-slate-500">VNF Temp</span>
                <span>{p.vnf_temp_k ? Math.round(p.vnf_temp_k) + " K" : "N/A"}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800 pb-1">
                <span className="text-slate-500">Priority</span>
                <span className={p.priority === "CRITICAL" ? "text-hud-red" : "text-hud-amber"}>{p.priority}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800 pb-1">
                <span className="text-slate-500">Methane Suspected</span>
                <span className={p.methane_venting_suspected ? "text-hud-amber font-bold" : "text-slate-300"}>
                  {p.methane_venting_suspected ? "YES" : "NO"}
                </span>
              </div>
            </div>

            <div className="mt-8 space-y-3">
              <button
                onClick={() => resolve(activeId!, "ESCALATE")}
                className="flex w-full items-center justify-center gap-2 rounded bg-hud-red py-2 font-mono text-sm font-bold text-slate-950 transition hover:bg-red-400"
              >
                <ShieldAlert className="h-4 w-4" /> CONFIRM & ESCALATE
              </button>
              <button
                onClick={() => resolve(activeId!, "DISMISS")}
                className="flex w-full items-center justify-center gap-2 rounded border border-slate-700 bg-slate-800 py-2 font-mono text-sm text-slate-300 transition hover:bg-slate-700 hover:text-slate-100"
              >
                <CheckCircle2 className="h-4 w-4" /> DISMISS AS FALSE POSITIVE
              </button>
            </div>
            
            {queue.length > 1 && (
              <div className="mt-4 text-center font-mono text-[10px] text-slate-500">
                Next up: {queue[1].properties.cluster_id.slice(0,8)}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}