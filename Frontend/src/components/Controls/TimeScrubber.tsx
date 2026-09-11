import { useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { Pause, Play, SkipBack, Layers2, CalendarDays } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { SEVERITY_THEMES, PRIORITY_RANK } from "@/lib/severityTheme";
import { PRIORITY_COLORS } from "@/lib/theme";
import type { Priority } from "@/api/types";

const PLAY_INTERVAL_MS = 1100;

export default function TimeScrubber() {
  const days = useAppStore((s) => s.days);
  const features = useAppStore((s) => s.windowFeatures);
  const idx = useAppStore((s) => s.currentTimeScrubberIndex);
  const isPlaying = useAppStore((s) => s.isPlaying);
  const scrubMode = useAppStore((s) => s.scrubMode);
  const setIdx = useAppStore((s) => s.setScrubberIndex);
  const step = useAppStore((s) => s.stepScrubber);
  const setPlaying = useAppStore((s) => s.setPlaying);
  const setScrubMode = useAppStore((s) => s.setScrubMode);
  const theme = SEVERITY_THEMES[useAppStore((s) => s.globalSeverityLevel)];

  
  const perDay = useMemo(() => days.map((_, i) => {
    const fs = features.filter((f) => f.properties.day_index === i);
    const worst = fs.reduce<Priority>((a, f) => (PRIORITY_RANK[f.properties.priority] > PRIORITY_RANK[a] ? f.properties.priority : a), "LOW");
    return { count: fs.length, worst, anomalies: fs.filter((f) => f.properties.m_score > 3.5).length };
  }), [days, features]);
  const maxCount = Math.max(1, ...perDay.map((d) => d.count));

  useEffect(() => {
    if (!isPlaying) return;
    const t = setInterval(step, PLAY_INTERVAL_MS);
    return () => clearInterval(t);
  }, [isPlaying, step]);

  const n = Math.max(days.length, 1);
  const pct = (i: number) => (n === 1 ? 0 : (i / (n - 1)) * 100);

  return (
    <section className={`flex h-full items-center gap-5 rounded-xl border px-5 ${theme.panel} ${theme.border} ${theme.glow}`}>
      {}
      <div className="flex items-center gap-2">
        <button onClick={() => { setPlaying(false); setIdx(0); }} className="rounded border border-slate-700 p-2 text-slate-300 hover:bg-white/10"><SkipBack className="h-4 w-4" /></button>
        <button onClick={() => setPlaying(!isPlaying)}
          className={`flex items-center gap-2 rounded border px-3 py-2 text-xs font-bold ${theme.border} ${theme.accent}`}
          style={{ boxShadow: `0 0 12px ${theme.accentHex}66` }}>
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />} {isPlaying ? "PAUSE" : "PLAY 7D"}
        </button>
        <button onClick={() => setScrubMode(scrubMode === "day" ? "cumulative" : "day")}
          className="flex items-center gap-1 rounded border border-slate-700 px-2 py-2 text-[10px] uppercase text-slate-300 hover:bg-white/10" title="Toggle single-day / cumulative spread">
          {scrubMode === "day" ? <CalendarDays className="h-3 w-3" /> : <Layers2 className="h-3 w-3" />} {scrubMode}
        </button>
      </div>

      {}
      <div className="relative flex-1 select-none pt-6">
        {}
        <div className="absolute inset-x-0 top-0 flex h-6 items-end">
          {perDay.map((d, i) => (
            <div key={i} className="absolute flex w-10 -translate-x-1/2 flex-col items-center" style={{ left: `${pct(i)}%` }}>
              <motion.div className="w-2 rounded-t" animate={{ height: 4 + (d.count / maxCount) * 18 }}
                style={{ background: PRIORITY_COLORS[d.worst], boxShadow: `0 0 6px ${PRIORITY_COLORS[d.worst]}` }} />
            </div>
          ))}
        </div>

        {}
        <div className="relative h-1.5 rounded bg-slate-800">
          <motion.div className="absolute left-0 top-0 h-1.5 rounded" animate={{ width: `${pct(idx)}%` }}
            style={{ background: `linear-gradient(90deg, ${theme.accentHex}55, ${theme.accentHex})` }} transition={{ type: "spring", stiffness: 180, damping: 24 }} />
          {days.map((d, i) => (
            <button key={d} onClick={() => { setPlaying(false); setIdx(i); }}
              className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: `${pct(i)}%` }} aria-label={d}>
              <span className={`block h-3 w-3 rounded-full border-2 transition ${i <= idx ? "border-white bg-slate-900" : "border-slate-600 bg-slate-900"}`}
                style={i === idx ? { boxShadow: `0 0 10px ${theme.accentHex}`, borderColor: theme.accentHex } : undefined} />
            </button>
          ))}
          <input type="range" min={0} max={n - 1} step={1} value={idx}
            onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)); }}
            className="absolute inset-x-0 top-1/2 h-6 -translate-y-1/2 cursor-pointer opacity-0" />
        </div>

        {}
        <div className="relative mt-2 h-4">
          {days.map((d, i) => (
            <div key={d} className={`absolute -translate-x-1/2 text-[10px] ${i === idx ? theme.accent : "text-slate-500"}`} style={{ left: `${pct(i)}%` }}>
              {i === n - 1 ? "LIVE" : `T-${n - 1 - i}`} <span className="text-slate-600">{d.slice(5)}</span>
            </div>
          ))}
        </div>
      </div>

      {}
      <div className="w-40 text-right">
        <div className="text-[10px] uppercase tracking-widest text-slate-400">Window cursor</div>
        <div className={`text-sm font-bold ${theme.accent}`}>{days[idx] ?? "—"}</div>
        <div className="text-[10px] text-slate-400">
          {perDay[idx]?.count ?? 0} objects · <span className="text-red-400">{perDay[idx]?.anomalies ?? 0} anomalies</span>
        </div>
      </div>
    </section>
  );
}
