import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Crosshair, Radio, ShieldAlert } from "lucide-react";
import { useHealth, useWindowHotspots } from "@/api/client";
import { useAppStore } from "@/store/useAppStore";
import { SEVERITY_THEMES } from "@/lib/severityTheme";
import TacticalMapModule from "@/components/Map/TacticalMapModule";
import TimeScrubber from "@/components/Controls/TimeScrubber";
import DecisionTreeSidebar from "@/components/Sidebar/DecisionTree";
import AnalyticsPanel from "@/components/Analytics/AnalyticsPanel";
import AlertFeed from "@/components/Alerts/AlertFeed";
import IncidentActionPanel from "@/components/Triage/IncidentActionPanel";
import { Login } from "@/pages/Login";
import { LogOut } from "lucide-react";

import KPIStrip from "@/components/Analytics/KPIStrip";
import RegionDrilldown from "@/components/Analytics/RegionDrilldown";


export default function App() {
  const { data: window } = useWindowHotspots(7);
  const { data: health } = useHealth();
  const setWindowData = useAppStore((s) => s.setWindowData);
  const severity = useAppStore((s) => s.globalSeverityLevel);
  const focusMode = useAppStore((s) => s.focusMode);
  const days = useAppStore((s) => s.days);
  const idx = useAppStore((s) => s.currentTimeScrubberIndex);
  const theme = SEVERITY_THEMES[severity];
  const isAuthenticated = useAppStore((s) => s.isAuthenticated);
  const logout = useAppStore((s) => s.logout);

    useEffect(() => {
    if (window) setWindowData(window.days, window.collection.features);
  }, [window, setWindowData]);

  if (!isAuthenticated) return <Login />;

  return (
    <motion.div
      className={`relative h-screen w-screen overflow-hidden font-mono text-slate-100 transition-colors duration-700 ${theme.root}`}
      data-severity={severity}
    >
      {}
      <motion.div
        key={severity}
        className="pointer-events-none absolute inset-0"
        initial={{ opacity: 0 }}
        animate={theme.pulse ? { opacity: [0.55, 1, 0.55] } : { opacity: 1 }}
        transition={theme.pulse ? { duration: 2.2, repeat: Infinity, ease: "easeInOut" } : { duration: 0.8 }}
        style={{ background: `radial-gradient(ellipse at 50% 120%, ${theme.ambient} 0%, transparent 60%), radial-gradient(ellipse at 50% -20%, ${theme.ambient} 0%, transparent 55%)` }}
      />

      <div className="relative z-10 grid h-full grid-cols-12 grid-rows-[56px_48px_minmax(0,1fr)_120px] gap-3 p-3">
        {}
        <header className={`col-span-12 flex items-center justify-between rounded-lg border px-4 ${theme.panel} ${theme.border} ${theme.glow}`}>
          <div className="flex items-center gap-3">
            <Crosshair className={`h-5 w-5 ${theme.accent}`} />
            <div>
              <div className="text-sm font-bold tracking-[0.25em]">FIREOPS COMMAND · v3.0</div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400">Mixed Analytical HUD · 7-day thermal window</div>
            </div>
          </div>
          <div className="flex items-center gap-6 text-[11px]">
            <div className="flex items-center gap-2">
              <Radio className={`h-4 w-4 ${health?.ingest_mode === "live" ? "animate-pulse text-cyan-400" : "text-amber-400"}`} />
              <span className="text-slate-400">INGEST</span>
              <span className="uppercase">{health?.ingest_mode ?? "…"}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-slate-400">T-WINDOW</span>
              <span>{days[idx] ?? "—"}</span>
            </div>
            <AnimatePresence>
              <motion.div
                key={severity}
                initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}
                className={`flex items-center gap-2 rounded border px-3 py-1 font-bold ${theme.border} ${theme.accent}`}
                style={{ boxShadow: `0 0 14px ${theme.accentHex}66` }}
              >
                <ShieldAlert className="h-4 w-4" /> DEFCON {severity}
              </motion.div>
            </AnimatePresence>
          </div>
        </header>
          <KPIStrip />

        {}
        <aside className="col-span-3 flex min-h-0 flex-col gap-3">
          <AnimatePresence mode="wait">
            {focusMode ? (
              <motion.div
                key="decision-tree"
                initial={{ opacity: 0, x: -20, height: 0 }}
                animate={{ opacity: 1, x: 0, height: "100%" }}
                exit={{ opacity: 0, scale: 0.95, height: 0 }}
                className="h-full w-full min-h-0 flex flex-col gap-3"
              >
                <div className="flex-[3] min-h-0"><DecisionTreeSidebar /></div>
                <div className="flex-[2] min-h-0"><RegionDrilldown onFocusRegion={(name, level, center) => useAppStore.getState().setFocusedRegion({ name, level, center })} /></div>
              </motion.div>
            ) : (
              <motion.div
                key="drilldown"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full w-full min-h-0"
              >
                <RegionDrilldown onFocusRegion={(name, level, center) => useAppStore.getState().setFocusedRegion({ name, level, center })} />
              </motion.div>
            )}
          </AnimatePresence>
        </aside>

        {}
        <main className="col-span-6 min-h-0">
          <TacticalMapModule />
        </main>

        {}
        <aside className="col-span-3 flex min-h-0 flex-col gap-3">
          <motion.div
            className="min-h-0"
            animate={{ flex: focusMode ? 1 : 3, opacity: focusMode ? 0.35 : 1 }}
            transition={{ duration: 0.5 }}
            style={{ display: "flex", flexDirection: "column" }}
          >
            <AlertFeed />
          </motion.div>
          <motion.div
            className="min-h-0"
            animate={{ flex: focusMode ? 4 : 2, scale: focusMode ? 1.0 : 0.98 }}
            transition={{ duration: 0.5 }}
            style={{ display: "flex", flexDirection: "column" }}
          >
            <IncidentActionPanel />
          </motion.div>
        </aside>

        {}
        <footer className="col-span-12 min-h-0">
          <TimeScrubber />
        </footer>
      </div>
    </motion.div>
  );
}
