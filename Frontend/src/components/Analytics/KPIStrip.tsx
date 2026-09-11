import { useMemo } from "react";
import { motion } from "framer-motion";
import { useVisibleFeatures } from "@/store/useAppStore";
import { SEVERITY_THEMES } from "@/lib/severityTheme";
import { useAppStore } from "@/store/useAppStore";
import { Flame, ShieldAlert, Target, AlertTriangle, Factory, Map } from "lucide-react";

function CounterBox({ label, value, icon: Icon, theme }: { label: string, value: number, icon: any, theme: any }) {
  return (
    <div className={`flex flex-col justify-center px-4 py-1 border-r border-white/5 last:border-0`}>
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-slate-400">
        <Icon className={`h-3 w-3 ${theme.accent}`} /> {label}
      </div>
      <motion.div 
        key={value}
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-lg font-light tabular-nums leading-none mt-1"
      >
        {value.toLocaleString()}
      </motion.div>
    </div>
  );
}

export default function KPIStrip() {
  const visible = useVisibleFeatures();
  const severity = useAppStore((s) => s.globalSeverityLevel);
  const theme = SEVERITY_THEMES[severity];

  const stats = useMemo(() => {
    let anomalies = 0;
    let critical = 0;
    let frp = 0;
    let persistent = 0;
    const districts = new Set<string>();

    for (const f of visible) {
      const p = f.properties;
      if (p.is_anomaly) anomalies++;
      if (p.priority === "CRITICAL") critical++;
      if (p.frp_mean) frp += p.frp_mean;
      if (p.predicted_class === "INDUSTRIAL_ACCIDENT" || p.predicted_class === "FLARE_SPIKE") persistent++;
      if (p.district) districts.add(p.district);
    }

    return {
      objects: visible.length,
      anomalies,
      critical,
      frp: Math.round(frp),
      persistent,
      districts: districts.size
    };
  }, [visible]);

  return (
    <div className={`col-span-12 h-12 flex rounded-xl border ${theme.panel} ${theme.border} overflow-hidden bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent`}>
      <div className="grid grid-cols-6 w-full divide-x divide-white/5">
        <CounterBox label="Objects in Window" value={stats.objects} icon={Target} theme={theme} />
        <CounterBox label="Active Anomalies" value={stats.anomalies} icon={AlertTriangle} theme={theme} />
        <CounterBox label="Critical Alerts" value={stats.critical} icon={ShieldAlert} theme={theme} />
        <CounterBox label="Districts Affected" value={stats.districts} icon={Map} theme={theme} />
        <CounterBox label="Total FRP (MW)" value={stats.frp} icon={Flame} theme={theme} />
        <CounterBox label="Persistent Sources" value={stats.persistent} icon={Factory} theme={theme} />
      </div>
    </div>
  );
}
