import React, { useEffect, useState } from 'react';

interface AIStatus {
  model_type: string;
  classes: string[];
  features: string[];
  training_samples: number;
  validation_accuracy: number;
  feature_importances: Record<string, number>;
  ensemble_components: string[];
}

export const AIModelStatus: React.FC = () => {
  const [status, setStatus] = useState<AIStatus | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'}/api/ai-status`)
      .then(r => r.json())
      .then(d => { if (d.status === 'success') setStatus(d); })
      .catch(() => {});
  }, []);

  if (!status) {
    return (
      <div className="flex-1 min-w-[280px] p-4 rounded-xl bg-gradient-to-br from-slate-800/40 to-slate-900/40 border border-slate-700/50 shadow-inner flex flex-col justify-between">
        <div className="text-xs font-mono uppercase tracking-widest text-cyan-400 font-bold mb-2 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-sm">smart_toy</span>
          AI Engine Status
        </div>
        <div className="text-xs text-slate-500 font-mono">Loading...</div>
      </div>
    );
  }

  
  const topFeatures = Object.entries(status.feature_importances)
    .sort(([,a], [,b]) => b - a)
    .slice(0, 4);
  const maxImp = Math.max(...topFeatures.map(([,v]) => v), 0.01);

  return (
    <div className="flex-1 min-w-[280px] p-4 rounded-xl bg-gradient-to-br from-slate-800/40 to-slate-900/40 border border-slate-700/50 shadow-inner flex flex-col justify-between">
      <div className="text-xs font-mono uppercase tracking-widest text-cyan-400 font-bold mb-3 flex items-center gap-1.5">
        <span className="material-symbols-outlined text-sm">smart_toy</span>
        AI Engine Status
      </div>
      
      {}
      <div className="flex items-center gap-2 hover:bg-slate-800/50 p-1 rounded cursor-crosshair mb-3">
        <div className="px-2 py-1 rounded-lg bg-emerald-500/15 border border-emerald-500/30">
          <span className="text-xs font-mono font-black text-emerald-400">{status.validation_accuracy}%</span>
        </div>
        <span className="text-[9px] font-mono text-slate-400">Validation Accuracy</span>
      </div>
      
      {}
      <div className="space-y-1.5 mb-3">
        <div className="text-[9px] font-mono text-slate-400">
          <span className="text-slate-500">Classes:</span> <span className="text-purple-400">{status.classes.length}</span>
          <span className="text-slate-600 mx-1">|</span>
          <span className="text-slate-500">Samples:</span> <span className="text-cyan-400">{status.training_samples.toLocaleString()}</span>
        </div>
        <div className="text-[9px] font-mono text-slate-500">
          Ensemble: {status.ensemble_components.length} models
        </div>
      </div>
      
      {}
      <div className="text-[8px] font-mono uppercase tracking-widest text-slate-500 mb-1.5">Feature Importance</div>
      <div className="space-y-1">
        {topFeatures.map(([name, imp]) => (
          <div key={name} className="flex items-center gap-1.5">
            <span className="text-[8px] font-mono text-slate-400 w-14 truncate">{name.replace('_', ' ')}</span>
            <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div 
                className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-purple-500 transition-all"
                style={{ width: `${(imp / maxImp) * 100}%` }}
              />
            </div>
            <span className="text-[7px] font-mono text-slate-500 w-6 text-right">{(imp * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
};
