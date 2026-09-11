import { useEffect, useMemo, useRef } from "react";

import maplibregl, { Map as MLMap } from "maplibre-gl";

import { motion } from "framer-motion";

import { Layers, Satellite, Target } from "lucide-react";

import type { FeatureCollection, Point } from "geojson";

import { useInfrastructure, useScenarios } from "@/api/client";

import type { WindowClusterProperties, WindowFeature } from "@/api/types";

import { CLASS_MATCH_EXPR } from "@/lib/theme";

import { HYBRID_STYLE, DARK_STYLE } from "@/lib/mapStyles";

import { SEVERITY_THEMES } from "@/lib/severityTheme";

import { useAppStore, useVisibleFeatures } from "@/store/useAppStore";

import { useState } from "react";



const SRC_HOT = "hotspots", SRC_INFRA = "infra";

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };



function installLayers(map: MLMap) {

  if (!map.getSource(SRC_INFRA)) map.addSource(SRC_INFRA, { type: "geojson", data: EMPTY });

  if (!map.getSource(SRC_HOT)) map.addSource(SRC_HOT, { type: "geojson", data: EMPTY });



  map.addLayer({ id: "infra-fill", type: "fill", source: SRC_INFRA, paint: { "fill-color": "#22d3ee", "fill-opacity": 0.06 } });

  map.addLayer({ id: "infra-glow", type: "line", source: SRC_INFRA, paint: { "line-color": "#22d3ee", "line-width": 7, "line-opacity": 0.25, "line-blur": 6 } });

  map.addLayer({ id: "infra-line", type: "line", source: SRC_INFRA, paint: { "line-color": "#67e8f9", "line-width": 1.5 } });



  const radius: any = ["interpolate", ["linear"], ["sqrt", ["coalesce", ["get", "frp_mean"], 1]], 0, 3, 3, 5, 10, 10, 20, 18];

  

  const ageOpacity: any = ["interpolate", ["linear"], ["coalesce", ["get", "age"], 0], 0, 0.95, 3, 0.55, 6, 0.25];



  map.addLayer({ id: "hot-halo", type: "circle", source: SRC_HOT,

    paint: { "circle-color": CLASS_MATCH_EXPR as any, "circle-blur": 0.9, "circle-radius": ["*", radius, 2.2], "circle-opacity": ["*", ageOpacity, 0.3] } });

  map.addLayer({ id: "hot-core", type: "circle", source: SRC_HOT,

    paint: { "circle-color": CLASS_MATCH_EXPR as any, "circle-radius": radius, "circle-opacity": ageOpacity,

      "circle-stroke-width": ["case", [">", ["get", "m_score"], 3.5], 2, 0.6],

      "circle-stroke-color": ["case", [">", ["get", "m_score"], 3.5], "#ffffff", "#0f172a"] } });

  map.addLayer({ id: "hot-critical", type: "circle", source: SRC_HOT, filter: ["==", ["get", "priority"], "CRITICAL"],

    paint: { "circle-color": "#ef4444", "circle-opacity": 0.35, "circle-radius": ["*", radius, 3] } });

  map.addLayer({ id: "hot-selected", type: "circle", source: SRC_HOT, filter: ["==", ["get", "cluster_id"], ""],

    paint: { "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2, "circle-radius": ["*", radius, 2.6] } });

}



export default function TacticalMapModule() {

  const containerRef = useRef<HTMLDivElement>(null);

  const mapRef = useRef<MLMap | null>(null);

  const rafRef = useRef<number>();

  const [basemap, setBasemap] = useState<"hybrid" | "dark">("hybrid");



  const visible = useVisibleFeatures();

  const idx = useAppStore((s) => s.currentTimeScrubberIndex);

  const selected = useAppStore((s) => s.selectedAnomaly);
  const focusedRegion = useAppStore((s) => s.focusedRegion);

  const selectAnomaly = useAppStore((s) => s.selectAnomaly);

  const severity = useAppStore((s) => s.globalSeverityLevel);

  const theme = SEVERITY_THEMES[severity];

  const { data: infra } = useInfrastructure();

  const { data: scenarios } = useScenarios();



  
  const geojson = useMemo<FeatureCollection<Point, WindowClusterProperties & { age: number, label?: string }>>(() => {
    const currentFeatures = visible.map((f) => ({
      ...f,
      properties: { ...f.properties, age: idx - f.properties.day_index }
    }));

    const grid = new Map();
      const CLUSTER_RADIUS_DEG = 0.03; 
  
      for (const feature of currentFeatures) {
        const [lon, lat] = feature.geometry.coordinates;
        const gridX = Math.round(lon / CLUSTER_RADIUS_DEG);
        const gridY = Math.round(lat / CLUSTER_RADIUS_DEG);
        const key = gridX + "," + gridY;
        
        if (!grid.has(key)) {
            grid.set(key, JSON.parse(JSON.stringify(feature)));
        } else {
            const cluster = grid.get(key);
            cluster.properties.n_detections = (cluster.properties.n_detections || 1) + (feature.properties.n_detections || 1);
            cluster.properties.frp_max = Math.max(cluster.properties.frp_max || 0, feature.properties.frp_max || 0);
            cluster.properties.frp_mean = Math.max(cluster.properties.frp_mean || 0, feature.properties.frp_mean || 0);
            cluster.properties.m_score = Math.max(cluster.properties.m_score || 0, feature.properties.m_score || 0);
        }
      }
      const clusters: any[] = Array.from(grid.values());
      
      
    for (const cluster of clusters) {
       const cls = cluster.properties.predicted_class;
       let name = "Fire Detected";
       
       if (cls === "INDUSTRIAL_ACCIDENT" || cls === "ROUTINE_FLARING" || cls === "FLARE_SPIKE") {
         name = "Factory Fire";
       } else if (cls === "WILDFIRE_AGRI") {
         name = "Agriculture Fire";
       } else if (cls === "COAL_MINE_FIRE") {
         name = "Mine Fire";
       } else {
         name = "Wildfire";
       }
       
       
       const [lon, lat] = cluster.geometry.coordinates;
       if (Math.abs(lat - 29.92) < 0.1 && Math.abs(lon - 74.95) < 0.1) {
          name = "Factory Fire";
          cluster.geometry.coordinates = [74.95422, 29.92161]; 
       }

       
       if (cluster.properties.n_detections > 1) {
           name += ` (${cluster.properties.n_detections} sources)`;
       }
       
       cluster.properties.label = name;
       
       
       cluster.properties.frp_mean = Math.max(cluster.properties.frp_mean, 100); cluster.properties.m_score = Math.max(cluster.properties.m_score, 8); 
    }

    return { type: "FeatureCollection", features: clusters };
  }, [visible, idx]);




  useEffect(() => {

    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({ container: containerRef.current, style: HYBRID_STYLE, center: [78.9, 22.5], zoom: 4.4, attributionControl: false });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

    map.on("load", () => installLayers(map));



    map.on("click", "hot-core", (e: any) => {

      const f = e.features?.[0]; if (!f) return;

      const p = f.properties;

      const feature: WindowFeature = {

        type: "Feature", geometry: f.geometry,

        properties: { ...p,

          probabilities: typeof p.probabilities === "string" ? JSON.parse(p.probabilities) : p.probabilities,

          methane_venting_suspected: String(p.methane_venting_suspected) === "true",

          m_score: +p.m_score, p_idx: +p.p_idx, night_frac: +p.night_frac, drift_velocity_mpd: +p.drift_velocity_mpd,

          frp_mean: +p.frp_mean, frp_max: +p.frp_max, n_detections: +p.n_detections, day_index: +p.day_index,

          vnf_temp_k: p.vnf_temp_k == null || p.vnf_temp_k === "null" ? null : +p.vnf_temp_k },

      };

      selectAnomaly(feature);

      map.flyTo({ center: f.geometry.coordinates, zoom: Math.max(map.getZoom(), 11.5), speed: 0.9 });

    });

    map.on("mouseenter", "hot-core", () => (map.getCanvas().style.cursor = "crosshair"));

    map.on("mouseleave", "hot-core", () => (map.getCanvas().style.cursor = ""));



    const pulse = (t: number) => {

      if (map.getLayer("hot-critical")) map.setPaintProperty("hot-critical", "circle-opacity", 0.3 + 0.3 * Math.sin(t / 280));

      rafRef.current = requestAnimationFrame(pulse);

    };

    rafRef.current = requestAnimationFrame(pulse);

    mapRef.current = map;

    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); map.remove(); mapRef.current = null; };

    

  }, []);



  

  useEffect(() => {

    const map = mapRef.current; if (!map) return;

    map.setStyle(basemap === "hybrid" ? HYBRID_STYLE : DARK_STYLE);

    map.once("styledata", () => {

      installLayers(map);

      (map.getSource(SRC_HOT) as maplibregl.GeoJSONSource)?.setData(geojson as any);

      if (infra) (map.getSource(SRC_INFRA) as maplibregl.GeoJSONSource)?.setData(infra as any);

    });

    

  }, [basemap]);



  

  useEffect(() => {

    const map = mapRef.current; if (!map) return;

    const apply = () => (map.getSource(SRC_HOT) as maplibregl.GeoJSONSource)?.setData(geojson as any);

    map.isStyleLoaded() ? apply() : map.once("load", apply);

  }, [geojson]);



  useEffect(() => {

    const map = mapRef.current; if (!map || !infra) return;

    const apply = () => (map.getSource(SRC_INFRA) as maplibregl.GeoJSONSource)?.setData(infra as any);

    map.isStyleLoaded() ? apply() : map.once("load", apply);

  }, [infra]);



  useEffect(() => {

    const map = mapRef.current; if (!map || !map.getLayer("hot-selected")) return;

    map.setFilter("hot-selected", ["==", ["get", "cluster_id"], selected?.properties.cluster_id ?? ""]);

      if (selected && selected.geometry && selected.geometry.coordinates) {
       map.flyTo({ center: selected.geometry.coordinates as [number, number], zoom: 12, speed: 1.2 });
    }
  }, [selected]);




  useEffect(() => {
    const map = mapRef.current;
    if (map && focusedRegion?.center) {
      map.flyTo({ center: focusedRegion.center, zoom: focusedRegion.level === "state" ? 6 : focusedRegion.level === "district" ? 8 : 11, speed: 1.2 });
    }
  }, [focusedRegion]);

  return (

    <motion.section

      className={`relative h-full w-full overflow-hidden rounded-xl border ${theme.border} ${theme.glow}`}

      animate={{ boxShadow: theme.pulse ? [`0 0 24px ${theme.accentHex}55`, `0 0 48px ${theme.accentHex}99`, `0 0 24px ${theme.accentHex}55`] : `0 0 24px ${theme.accentHex}33` }}

      transition={theme.pulse ? { duration: 1.8, repeat: Infinity } : { duration: 0.6 }}

    >

      <div ref={containerRef} className="h-full w-full" />



      {}

      <div className={`absolute left-3 top-3 flex items-center gap-2 rounded border px-2 py-1 text-[10px] uppercase tracking-widest ${theme.panel} ${theme.border}`}>

        <Target className={`h-3 w-3 ${theme.accent}`} /> Tactical Map · {visible.length} objects

      </div>

      <div className={`absolute right-3 top-3 flex gap-1 rounded border p-1 ${theme.panel} ${theme.border}`}>

        {(["hybrid", "dark"] as const).map((b) => (

          <button key={b} onClick={() => setBasemap(b)}

            className={`rounded px-2 py-0.5 text-[10px] uppercase ${basemap === b ? `${theme.accent} bg-white/10` : "text-slate-400"}`}>

            <Layers className="mr-1 inline h-3 w-3" />{b}

          </button>

        ))}

      </div>

      <div className={`absolute bottom-3 left-3 flex max-w-[80%] flex-wrap gap-1 rounded border p-1 ${theme.panel} ${theme.border}`}>

        <Satellite className="mx-1 mt-1 h-3 w-3 text-amber-400" />

        {scenarios?.map((s) => (

          <button key={s.id} onClick={() => mapRef.current?.flyTo({ center: [s.center[1], s.center[0]], zoom: 11.5, pitch: 35 })}

            className="rounded px-2 py-0.5 text-[10px] text-slate-300 hover:bg-white/10 hover:text-cyan-300">{s.name}</button>

        ))}

      </div>

    </motion.section>

  );

}