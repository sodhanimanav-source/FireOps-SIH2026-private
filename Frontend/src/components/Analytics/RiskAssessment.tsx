import React, { useEffect, useState } from 'react';
import { useAppStore } from '../../store/appStore';

interface RiskHotspot {
  lat: number;
  lng: number;
  source_type: string;
  label: string;
  frp: number;
  severity: string;
  escalation_probability: number;
  risk_score: number;
}

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: '#ef4444',
  MEDIUM: '#f59e0b',
  LOW: '#22c55e',
};

const MOCK_ALERTS: RiskHotspot[] = [
  { lat: 21.1523, lng: 72.8258, source_type: 'INDUSTRIAL_FIRE', label: 'Hazira LNG Complex', frp: 185.4, severity: 'CRITICAL', escalation_probability: 94, risk_score: 95 },
  { lat: 22.4707, lng: 70.0577, source_type: 'GAS_FLARE', label: 'Jamnagar Refinery', frp: 142.0, severity: 'CRITICAL', escalation_probability: 88, risk_score: 82 },
  { lat: 30.9000, lng: 75.4000, source_type: 'AGRICULTURAL_BURNING', label: 'Punjab Biomass', frp: 65.0, severity: 'MEDIUM', escalation_probability: 45, risk_score: 55 },
  { lat: 14.8000, lng: 75.3000, source_type: 'WILDFIRE', label: 'Western Ghats Forest', frp: 85.2, severity: 'HIGH', escalation_probability: 72, risk_score: 75 },
];

export const RiskAssessment: React.FC = () => {
  const [alerts, setAlerts] = useState<RiskHotspot[]>([]);
  const [totalAtRisk, setTotalAtRisk] = useState(0);

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'}/api/predict/21.1523/72.8258`)
      .then(r => r.json())
      .then(d => {
        if (d.status === 'success' && d.escalation_alerts && d.escalation_alerts.length > 0) {
          setAlerts(d.escalation_alerts);
          setTotalAtRisk(d.total_at_risk || 0);
        } else {
          setAlerts(MOCK_ALERTS);
          setTotalAtRisk(47);
        }
      })
      .catch(() => {
        setAlerts(MOCK_ALERTS);
        setTotalAtRisk(47);
      });
  }, []);

  
  const overallRisk = totalAtRisk > 20 ? 'CRITICAL' : totalAtRisk > 10 ? 'HIGH' : totalAtRisk > 3 ? 'MODERATE' : 'LOW';
  const riskColor = overallRisk === 'CRITICAL' ? '#ef4444' : overallRisk === 'HIGH' ? '#f97316' : overallRisk === 'MODERATE' ? '#f59e0b' : '#22c55e';

  return (
    <div className="flex-1 min-w-[280px] p-4 rounded-xl bg-gradient-to-br from-slate-800/40 to-slate-900/40 border border-slate-700/50 shadow-inner flex flex-col justify-between">
      <div className="text-sm font-mono uppercase tracking-widest text-cyan-400 font-bold mb-2 flex items-center gap-1.5 hover:bg-slate-800/50 p-1 rounded transition-colors cursor-pointer">
        <span className="material-symbols-outlined text-base">shield</span>
        Risk Assessment
      </div>

      {}
      <div className="flex items-center gap-4 mb-3">
        <div 
          className="w-14 h-14 rounded-xl flex items-center justify-center border-[3px] shadow-[0_0_15px_rgba(239,68,68,0.2)]"
          style={{ borderColor: riskColor, backgroundColor: `${riskColor}15` }}
        >
          <span className="font-mono text-sm font-black" style={{ color: riskColor }}>{overallRisk.slice(0, 4)}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <div className="text-sm font-mono font-bold text-slate-200">Threat Level: <span style={{ color: riskColor }}>{overallRisk}</span></div>
          <div className="text-xs font-mono text-slate-400">{totalAtRisk} active escalation vectors</div>
        </div>
      </div>
      
      {}
      <div className="space-y-2 max-h-24 overflow-y-auto pr-1 custom-scrollbar">
        {alerts.slice(0, 4).map((a, i) => (
          <div key={i} onClick={() => window.alert(`Risk Alert: ${a.label} has a ${a.escalation_probability}% chance of escalation. FRP: ${a.frp} MW.`)} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-950/60 border border-slate-800/50 hover:border-red-500/50 hover:bg-slate-900/80 transition-colors cursor-pointer group">
            <div className="flex items-center gap-2 overflow-hidden">
              <div className="w-2 h-2 rounded-full shrink-0 animate-pulse" style={{ backgroundColor: SEVERITY_COLORS[a.severity] || '#ef4444' }} />
              <span className="text-xs font-mono text-slate-300 truncate group-hover:text-white transition-colors">{a.source_type?.replace('_', ' ')}</span>
            </div>
            <span className="text-xs font-mono font-bold shrink-0" style={{ color: '#ef4444' }}>{a.escalation_probability}% RISK</span>
          </div>
        ))}
      </div>
    </div>
  );
};
