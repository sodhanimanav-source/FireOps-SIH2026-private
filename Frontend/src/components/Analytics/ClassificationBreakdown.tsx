import React, { useEffect, useState } from 'react';

interface AnalyticsData {
  classification_breakdown: Record<string, number>;
  severity_distribution: Record<string, number>;
  avg_frp_by_class: Record<string, number>;
  total_hotspots: number;
}

const SOURCE_COLORS: Record<string, string> = {
  INDUSTRIAL_FIRE: '#ef4444',
  GAS_FLARE: '#f97316',
  AGRICULTURAL_BURNING: '#84cc16',
  MINING_ACTIVITY: '#a16207',
  WILDFIRE: '#dc2626',
  PERSISTENT_THERMAL: '#3b82f6',
};

const SOURCE_LABELS: Record<string, string> = {
  INDUSTRIAL_FIRE: 'Industrial Fire',
  GAS_FLARE: 'Gas Flare',
  AGRICULTURAL_BURNING: 'Agri Burning',
  MINING_ACTIVITY: 'Mining Activity',
  WILDFIRE: 'Wildfire',
  PERSISTENT_THERMAL: 'Persistent Thermal',
};

export const ClassificationBreakdown: React.FC = () => {
  const [data, setData] = useState<AnalyticsData | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_BASE_URL ?? 'http:
      .then(r => r.json())
      .then(d => { if (d.status === 'success') setData(d); })
      .catch(() => {});
  }, []);

  if (!data || data.total_hotspots === 0) {
    return (
      <div className="flex-1 min-w-[280px] p-4 rounded-xl bg-gradient-to-br from-slate-800/40 to-slate-900/40 border border-slate-700/50 shadow-inner flex flex-col justify-between">
        <div className="text-xs font-mono uppercase tracking-widest text-cyan-400 font-bold mb-2 flex items-center gap-3 hover:bg-slate-800/60 p-2 rounded-lg transition-colors cursor-pointer">
          <span className="material-symbols-outlined text-sm">donut_small</span>
          AI Classification
        </div>
        <div className="text-xs text-slate-500 font-mono">Loading...</div>
      </div>
    );
  }

  const entries = Object.entries(data.classification_breakdown);
  const total = entries.reduce((s, [, v]) => s + v, 0);

  
  let cumulativePercent = 0;
  const segments = entries.map(([key, count]) => {
    const pct = (count / total) * 100;
    const startAngle = (cumulativePercent / 100) * 360;
    const endAngle = ((cumulativePercent + pct) / 100) * 360;
    cumulativePercent += pct;
    
    const startRad = ((startAngle - 90) * Math.PI) / 180;
    const endRad = ((endAngle - 90) * Math.PI) / 180;
    const largeArc = pct > 50 ? 1 : 0;
    
    const r = 36;
    const cx = 50, cy = 50;
    const x1 = cx + r * Math.cos(startRad);
    const y1 = cy + r * Math.sin(startRad);
    const x2 = cx + r * Math.cos(endRad);
    const y2 = cy + r * Math.sin(endRad);
    
    return (
      <path
        key={key}
        d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`}
        fill={SOURCE_COLORS[key] || '#6b7280'}
        stroke="#0f172a"
        strokeWidth="1"
        opacity="0.85"
      />
    );
  });

  return (
    <div className="flex-1 min-w-[280px] p-4 rounded-xl bg-gradient-to-br from-slate-800/40 to-slate-900/40 border border-slate-700/50 shadow-inner flex flex-col justify-between">
      <div className="text-xs font-mono uppercase tracking-widest text-cyan-400 font-bold mb-3 flex items-center gap-3 hover:bg-slate-800/60 p-2 rounded-lg transition-colors cursor-pointer">
        <span className="material-symbols-outlined text-sm">donut_small</span>
        AI Classification Breakdown
      </div>
      
      <div className="flex items-center gap-8 justify-between h-full px-2">
        {}
        <svg viewBox="0 0 100 100" className="w-36 h-36 lg:w-44 lg:h-44 shrink-0 drop-shadow-[0_0_12px_rgba(0,0,0,0.5)]">
          {segments}
          <circle cx="50" cy="50" r="20" fill="transparent" />
          <text x="50" y="47" textAnchor="middle" className="fill-slate-100 text-[18px] font-bold" style={{fontFamily: 'monospace'}}>{total}</text>
          <text x="50" y="60" textAnchor="middle" className="fill-slate-400 text-[12px]" style={{fontFamily: 'monospace'}}>total</text>
        </svg>
        
        {}
        <div className="flex flex-col gap-2 flex-1">
          {entries.map(([key, count]) => (
            <div key={key} className="flex items-center gap-3 hover:bg-slate-800/60 p-2 rounded-lg transition-colors cursor-pointer">
              <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: SOURCE_COLORS[key] || '#6b7280' }} />
              <span className="text-sm font-mono font-bold text-slate-200 truncate">{SOURCE_LABELS[key] || key}</span>
              <span className="text-sm font-mono font-bold text-slate-400 ml-auto">{count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
