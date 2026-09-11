import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../store/appStore';
import { useFacilities, useHotspots, usePendingAlerts, resolveAlert } from '../api/queries';
import { MapController } from '../components/Map/MapController';
import { ClassificationBreakdown } from '../components/Analytics/ClassificationBreakdown';
import { RiskAssessment } from '../components/Analytics/RiskAssessment';
import { PredictiveInsights } from '../components/Analytics/PredictiveInsights';
import { AIModelStatus } from '../components/Analytics/AIModelStatus';
import { VerificationModal } from '../components/Map/VerificationModal';

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();

  
  const [reviewingAlert, setReviewingAlert] = React.useState<any>(null);
  const [toastMessage, setToastMessage] = React.useState<string | null>(null);
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const { 
    selectedFacility, 
    selectedHotspot, 
    anomalyFilters, 
    setSelectedFacility,
    setSelectedHotspot,
      setAnomalyFilters,
      viewMode,
      setViewMode
    } = useAppStore();

  const { data: facilities } = useFacilities();
  const { data: hotspots, refetch: refetchHotspots } = useHotspots();
  const { data: pendingAlerts, refetch: refetchAlerts } = usePendingAlerts();

  const activeHotspotData = hotspots?.find((h) => h.id === selectedHotspot);
  const activeFacilityData = facilities?.find((f) => f.id === selectedFacility);

  const handleClosePanel = () => {
    setSelectedHotspot(null);
    setSelectedFacility(null);
  };

  const highAnomalyCount = hotspots?.filter((h) => h.modified_z_score > 3.5).length ?? 0;
  const totalHotspots = hotspots?.length ?? 0;
  const totalFacilities = facilities?.length ?? 0;

  return (
    <div className="h-screen w-screen bg-[#070d1e] text-slate-100 relative overflow-hidden font-sans select-none">
      
      {}
      <div className="absolute inset-0 z-0 pl-64 pt-16" data-testid="map-wrapper">
        <MapController />
      </div>

      {}
      <header className="fixed top-0 left-0 right-0 h-16 bg-slate-900/95 backdrop-blur-md border-b border-slate-800 z-40 px-6 flex items-center justify-between">
        
        {}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 p-0.5 shadow-md shadow-cyan-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <span className="material-symbols-outlined text-xl text-cyan-400" style={{ fontVariationSettings: "'FILL' 1" }}>
                local_fire_department
              </span>
            </div>
          </div>
          <div>
            <span className="font-mono font-extrabold text-lg tracking-wider text-slate-100">
              FIREOPS<span className="text-cyan-400">.COMMAND</span>
            </span>
            <span className="hidden sm:inline-block ml-2 px-2 py-0.5 text-sm font-mono font-bold uppercase tracking-widest bg-cyan-950 text-cyan-400 border border-cyan-800 rounded">
              v2.4 Pro
            </span>
          </div>
        </div>

        {}
        <div className="hidden lg:flex items-center gap-6 px-4 py-1.5 rounded-full bg-slate-950/80 border border-slate-800 text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 pulse-green"></span>
            <span className="text-emerald-400 font-bold uppercase tracking-wider">Live Telemetry</span>
          </div>
          <span className="text-slate-600">|</span>
          <div className="text-slate-300">
            Monitored Facilities: <span className="text-cyan-400 font-bold">{totalFacilities}</span>
          </div>
          <span className="text-slate-600">|</span>
          <div className="text-slate-300">
            Active Hotspots: <span className="text-amber-400 font-bold">{totalHotspots}</span>
          </div>
        </div>

                {}
        { false && (
          <div className="absolute top-24 left-4 z-20 w-80 max-h-[60vh] overflow-y-auto bg-slate-900/95 border-2 border-yellow-500/50 rounded-xl shadow-2xl backdrop-blur-md flex flex-col">
            <div className="bg-yellow-500/20 px-4 py-2 border-b border-yellow-500/30 flex justify-between items-center">
              <span className="font-bold text-yellow-400 font-mono text-sm tracking-wide flex items-center gap-2">
                <span className="material-symbols-outlined text-lg animate-pulse">warning</span>
                HITL REVIEW ({pendingAlerts.length})
              </span>
            </div>
            <div className="p-3 flex flex-col gap-3">
              {pendingAlerts.map((alert: any) => (
                <div key={alert.id} className="bg-slate-800/80 rounded-lg p-3 border border-slate-700 hover:border-yellow-500/50 transition-colors">
                  <div className="text-xs font-mono text-slate-400 mb-1">{alert.id}</div>
                  <div className="flex justify-between items-end mb-3">
                    <div>
                      <div className="text-sm font-bold text-slate-200">AI Confidence: {(alert.ai_results.ai_confidence * 100).toFixed(1)}%</div>
                      <div className="text-[10px] text-yellow-300">Spread: {alert.ai_results.spatial_spread_m}m | ΔNBR: {alert.satellite_data.spectral_deltas.dNBR.toFixed(2)}</div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => setReviewingAlert(alert)} className="w-full bg-cyan-500/20 hover:bg-cyan-500/40 text-cyan-400 border border-cyan-500/50 rounded py-1.5 text-xs font-bold transition-all flex items-center justify-center gap-2">
                      <span className="material-symbols-outlined text-[14px]">satellite_alt</span>
                      REVIEW SATELLITE DATA
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {}
        <div className="flex items-center gap-4">
          
          {}
          <label 
            htmlFor="anomaly-filter-switch"
            className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-slate-700 cursor-pointer transition-all"
          >
            <div className="relative inline-flex items-center">
              <input 
                id="anomaly-filter-switch"
                type="checkbox" 
                role="switch"
                aria-label="Filter High Anomalies"
                checked={anomalyFilters} 
                onChange={(e) => setAnomalyFilters(e.target.checked)}
                className="sr-only peer" 
              />
              <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-red-500"></div>
            </div>
            <span className={`text-sm font-mono font-bold tracking-wider uppercase ${anomalyFilters ? 'text-red-400' : 'text-slate-400'}`}>
              High Anomalies (Z &gt; 3.5)
            </span>
          </label>

          {}
          <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
            <div className="w-8 h-8 rounded-full bg-cyan-950 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-mono text-xs font-bold">
              OP
            </div>
          </div>
        </div>
      </header>

      {}
      <aside 
        aria-label="Main Sidebar"
        className="fixed top-16 left-0 bottom-0 w-64 bg-slate-900/90 backdrop-blur-md border-r border-slate-800 z-30 flex flex-col justify-between p-4"
      >
        
        {}
        <div className="space-y-6">
          
          {}
          <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800/80">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">Command Node</span>
              <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">ONLINE</span>
            </div>
            <p className="text-sm font-mono font-bold text-slate-200">Vigilance Alpha-9</p>
          </div>

          {}
          <nav className="space-y-1">
            <a href="#" onClick={(e) => { e.preventDefault(); setViewMode("overview"); }} className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg font-mono text-sm font-bold uppercase tracking-wider transition-all cursor-pointer ${viewMode === "overview" ? "bg-cyan-500/10 border-l-2 border-cyan-400 text-cyan-300" : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-2 border-transparent"}`}>
<span className="material-symbols-outlined text-lg">dashboard</span>
<div className="flex-1">OVERVIEW</div>
</a>
            
            <a href="#" onClick={(e) => { e.preventDefault(); setViewMode("facilities"); }} className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg font-mono text-sm font-bold uppercase tracking-wider transition-all cursor-pointer ${viewMode === "facilities" ? "bg-cyan-500/10 border-l-2 border-cyan-400 text-cyan-300" : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-2 border-transparent"}`}>
<span className="material-symbols-outlined text-lg">factory</span>
<div className="flex-1">FACILITIES</div>
<div className="px-2 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300">196</div>
</a>

            <a href="#" onClick={(e) => { e.preventDefault(); setViewMode("hotspots"); }} className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg font-mono text-sm font-bold uppercase tracking-wider transition-all cursor-pointer ${viewMode === "hotspots" ? "bg-amber-500/10 border-l-2 border-amber-400 text-amber-300" : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-2 border-transparent"}`}>
<span className="material-symbols-outlined text-lg">local_fire_department</span>
<div className="flex-1">HOTSPOTS</div>
<div className="px-2 py-0.5 rounded bg-amber-500/20 text-[10px] text-amber-400">1431</div>
</a>

            <a 
              href="#alerts" 
              className="flex items-center justify-between px-3.5 py-2.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 font-mono text-xs font-semibold uppercase tracking-wider transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-lg text-red-400">warning</span>
                Anomalies
              </div>
              <span className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 font-mono">{highAnomalyCount}</span>
            </a>
          </nav>
        </div>

        {}
        <div className="space-y-2 pt-4 border-t border-slate-800">
          <button 
            type="button"
            className="w-full py-2.5 px-3 rounded-lg bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 font-mono text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <span className="material-symbols-outlined text-base">campaign</span>
            Emergency Broadcast
          </button>

          <button 
            type="button"
            onClick={() => navigate('/')} 
            className="w-full py-2 px-3 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 font-mono text-xs font-semibold uppercase tracking-wider flex items-center gap-2 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-base">logout</span>
            Log Out
          </button>
        </div>
      </aside>


      {}
      {}
      <div className="fixed bottom-6 left-72 right-6 z-20 pointer-events-auto flex flex-col gap-2">
        <div className="text-xs font-mono text-cyan-500 uppercase tracking-widest ml-1 font-bold flex items-center gap-2">
           <span className="material-symbols-outlined text-xs">memory</span>
           Live AI Telemetry & Predictions
        </div>
        <div className="p-2 rounded-2xl bg-slate-900/90 border border-slate-700/60 shadow-2xl backdrop-blur-xl flex gap-4 overflow-hidden p-3">
          <ClassificationBreakdown />
          <RiskAssessment />
          <PredictiveInsights />
          <AIModelStatus />
        </div>
      </div>
      {}

      <div className="fixed top-28 right-6 z-20 pointer-events-none flex flex-col items-end gap-3">
        <div className="pointer-events-auto px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl backdrop-blur-md flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <span className="material-symbols-outlined text-xl">satellite_alt</span>
          </div>
          <div>
            <div className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">Satellite Feed</div>
            <div className="text-sm font-mono font-bold text-slate-200">Google Hybrid & NASA FIRMS NRT</div>
          </div>
        </div>

        <div 
          className="pointer-events-auto px-4 py-3 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-slate-800 hover:border-red-500/50 shadow-xl backdrop-blur-md flex items-center gap-4 cursor-pointer transition-all"
          onClick={() => setAnomalyFilters(!anomalyFilters)}
        >
          <div className="w-10 h-10 rounded-lg bg-red-500/10 border border-red-500/30 flex items-center justify-center text-red-400">
            <span className="material-symbols-outlined text-xl">crisis_alert</span>
          </div>
          <div>
            <div className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">Anomaly Filter Status</div>
            <div className="text-sm font-mono font-bold text-red-400">
              {anomalyFilters ? `Active: ${highAnomalyCount} Alerts Isolated` : 'All Thermal Signatures Shown'}
            </div>
          </div>
        </div>
      </div>

      {}
      <aside 
        aria-label="Telemetry Panel"
        className={`fixed top-20 right-6 w-[390px] z-30 transition-all duration-300 ${selectedHotspot || selectedFacility ? 'opacity-100 translate-x-0 pointer-events-auto' : 'opacity-0 translate-x-8 pointer-events-none'}`}
      >
        
        {}
        {selectedHotspot && (
          <div 
            className="w-full p-6 rounded-2xl bg-slate-900/95 border border-red-500/40 shadow-2xl shadow-red-950/40 backdrop-blur-xl flex flex-col gap-4"
            data-testid="hotspot-panel"
          >
            {}
            <div className="h-1 bg-gradient-to-r from-red-500 to-amber-500 rounded-full w-full"></div>

            {}
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-red-500/20 border border-red-500/50 flex items-center justify-center text-red-400 pulse-red">
                  <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                    local_fire_department
                  </span>
                </div>
                <div>
                  <h3 className="font-mono font-bold text-base text-red-400 leading-tight">Thermal Hotspot</h3>
                  <p className="font-mono text-xs text-slate-400 mt-0.5" data-testid="hotspot-id">ID: {selectedHotspot}</p>
                </div>
              </div>

              <button 
                onClick={handleClosePanel}
                aria-label="Close telemetry panel"
                className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-100 flex items-center justify-center transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-lg">close</span>
              </button>
            </div>

            {}
            <div className="flex items-center gap-2">
              <div className="px-3 py-1.5 rounded-lg bg-red-500/15 border border-red-500/30 text-red-300 font-mono text-xs font-bold uppercase tracking-wider flex items-center gap-1.5 w-max">
                <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>verified</span>
                {activeHotspotData?.classification || 'High Confidence Fire'}
              </div>
              {activeHotspotData?.severity && (
                <div className={`px-2.5 py-1.5 rounded-lg font-mono text-xs font-extrabold uppercase border ${
                  activeHotspotData.severity === 'CRITICAL'
                    ? 'bg-red-500/20 text-red-400 border-red-500/40 animate-pulse'
                    : 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                }`}>
                  {activeHotspotData.severity}
                </div>
              )}
            </div>

            {}
            {activeHotspotData?.facility_name && (
              <div className="p-2.5 rounded-xl bg-cyan-950/40 border border-cyan-500/30 text-xs font-mono flex items-center justify-between text-cyan-300">
                <span className="flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm text-cyan-400">factory</span>
                  {activeHotspotData.facility_name}
                </span>
                {activeHotspotData.distance_km !== null && activeHotspotData.distance_km !== undefined && (
                  <span className="text-xs text-slate-400 font-bold">{activeHotspotData.distance_km} km away</span>
                )}
              </div>
            )}

            {}
            <div className="grid grid-cols-2 gap-2.5">
              
              <div className="col-span-2 p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Coordinates</span>
                <span className="font-mono text-sm text-slate-100 font-bold" data-testid="hotspot-coords">
                  {activeHotspotData ? `${activeHotspotData.latitude.toFixed(4)}° N, ${activeHotspotData.longitude.toFixed(4)}° E` : 'N/A'}
                </span>
              </div>

              <div className="col-span-2 p-3 rounded-xl bg-slate-950/80 border border-red-500/30">
                <span className="block text-xs font-mono uppercase tracking-widest text-red-400 font-bold mb-1">Fire Radiative Power (FRP)</span>
                <span className="font-mono text-2xl font-black text-red-400" data-testid="hotspot-frp">
                  {activeHotspotData ? `${activeHotspotData.frp} MW` : 'N/A'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Brightness Temp</span>
                <span className="font-mono text-base font-bold text-amber-300" data-testid="hotspot-temp">
                  {activeHotspotData ? `${activeHotspotData.temperature_k} K` : 'N/A'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Z-Score</span>
                <span className="font-mono text-base font-bold text-red-400" data-testid="hotspot-zscore">
                  {activeHotspotData ? activeHotspotData.modified_z_score : 'N/A'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Acquisition Date</span>
                <span className="font-mono text-xs font-bold text-slate-200">
                  {activeHotspotData?.date || 'Live NRT'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Persistence</span>
                <span className="font-mono text-base font-bold text-slate-200" data-testid="hotspot-persistence">
                  {activeHotspotData ? activeHotspotData.persistence_index : 'N/A'}
                </span>
              
              </div>

              {}
              <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-700/60 shadow-inner relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1 h-full bg-cyan-500"></div>
                <span className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-cyan-400 font-bold mb-2">
                  <span className="material-symbols-outlined text-sm">history</span>
                  Historical Context AI
                </span>
                
                <p className="font-mono text-[11px] text-slate-300 leading-relaxed text-justify">
                  {activeHotspotData?.classification === 'INDUSTRIAL_FIRE' ? (
                    'Critical deviation from baseline. No significant thermal activity in this 5km radius over the past 11 months. Sudden high-FRP onset suggests an industrial accident or blast.'
                  ) : activeHotspotData?.classification === 'GAS_FLARE' ? (
                    'Routine industrial operation. Telemetry indicates 342 continuous burning days in the last 12 months within a 2km radius.'
                  ) : activeHotspotData?.classification === 'AGRICULTURAL_BURNING' ? (
                    'Strong seasonal pattern matched. Similar widespread thermal signatures detected here during Oct-Nov in the past 3 years.'
                  ) : activeHotspotData?.classification === 'WILDFIRE' ? (
                    'Rapid spread vector detected. Area has no history of industrial or agricultural burns. Onset began roughly 3 days ago.'
                  ) : (
                    'Analyzing localized historical telemetry data (5km radius) to determine long-term thermal persistence patterns...'
                  )}
                </p>
                
                <div className="mt-2.5 flex items-center gap-4 border-t border-slate-800 pt-2.5">
                  <div className="flex flex-col">
                    <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">Radius Check</span>
                    <span className="text-[10px] font-mono font-bold text-slate-300">5.0 km</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">Timeline</span>
                    <span className="text-[10px] font-mono font-bold text-slate-300">36 Months</span>
                  </div>
                  <div className="flex flex-col ml-auto">
                    <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest text-right">Confidence</span>
                    <span className="text-[10px] font-mono font-bold text-cyan-400 text-right">94.2%</span>
                  </div>
                </div>
              </div>

              </div>
              {}

            <div className="grid grid-cols-2 gap-2 mt-1">
              <button 
                type="button"
                className="py-2.5 px-3 rounded-xl bg-gradient-to-r from-red-500 to-amber-600 hover:from-red-400 hover:to-amber-500 text-slate-950 font-mono font-bold text-xs uppercase tracking-wider shadow-lg shadow-red-500/20 active:scale-95 transition-all cursor-pointer"
               onClick={() => showToast("🚨 COMMAND SENT: Emergency response unit dispatched to the hotspot location. ETA 12 minutes.")}>
                Dispatch Unit
              </button>
              <button 
                type="button"
                className="py-2.5 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-mono font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer"
               onClick={() => showToast("🔒 GRID ISOLATED: The facility has been isolated from the main power grid to prevent cascading failure.")}>
                Isolate Grid
              </button>
            </div>
          </div>
        )}

        {}
        {selectedFacility && !selectedHotspot && (
          <div 
            className="w-full p-6 rounded-2xl bg-slate-900/95 border border-cyan-500/40 shadow-2xl shadow-cyan-950/40 backdrop-blur-xl flex flex-col gap-4"
            data-testid="facility-panel"
          >
            {}
            <div className="h-1 bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full w-full"></div>

            {}
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-cyan-500/20 border border-cyan-500/50 flex items-center justify-center text-cyan-400">
                  <span className="material-symbols-outlined text-2xl">
                    factory
                  </span>
                </div>
                <div>
                  <h3 className="font-mono font-bold text-base text-cyan-400 leading-tight">Facility Telemetry</h3>
                  <p className="font-mono text-xs text-slate-400 mt-0.5" data-testid="facility-id">ID: {selectedFacility}</p>
                </div>
              </div>

              <button 
                onClick={handleClosePanel}
                aria-label="Close facility panel"
                className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-100 flex items-center justify-center transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-lg">close</span>
              </button>
            </div>

            {}
            <div 
              className="px-3 py-1.5 rounded-lg bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 font-mono text-xs font-bold uppercase tracking-wider flex items-center gap-2 w-max"
              data-testid="facility-type"
            >
              <span className="material-symbols-outlined text-sm">apartment</span>
              {activeFacilityData?.type || 'Industrial Complex'}
            </div>

            {}
            <div className="grid grid-cols-2 gap-2.5">
              <div className="col-span-2 p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Facility Name</span>
                <span className="font-mono text-sm text-slate-100 font-bold" data-testid="facility-name">
                  {activeFacilityData?.name || 'Unknown Facility'}
                </span>
              </div>

              <div className="col-span-2 p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Coordinates</span>
                <span className="font-mono text-sm text-slate-100 font-bold" data-testid="facility-coords">
                  {activeFacilityData ? `${activeFacilityData.latitude.toFixed(4)}° N, ${activeFacilityData.longitude.toFixed(4)}° E` : 'N/A'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Buffer Radius</span>
                <span className="font-mono text-base font-bold text-cyan-400" data-testid="facility-buffer">
                  {activeFacilityData ? `${activeFacilityData.buffer_radius_km} km` : 'N/A'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                <span className="block text-xs font-mono uppercase tracking-widest text-slate-400 font-bold mb-1">Baseline FRP</span>
                <span className="font-mono text-base font-bold text-amber-300" data-testid="facility-baseline-frp">
                  {activeFacilityData ? `${activeFacilityData.baseline_frp} MW` : 'N/A'}
                </span>
              </div>
            </div>

            {}
            <div className="mt-1">
              <button 
                type="button"
                className="w-full py-2.5 px-4 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-400 font-mono font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer"
               onClick={() => showToast("📊 LOGS: Opening historical telemetry logs for this facility...")}>
                View Historical Log
              </button>
            </div>
          </div>
        )}
      </aside>

      {}
      {toastMessage && (
        <div className="fixed top-24 left-1/2 -translate-x-1/2 z-50 animate-in fade-in slide-in-from-top-4 duration-300">
          <div className="px-6 py-4 rounded-xl bg-slate-900 border-2 border-cyan-500/50 shadow-[0_0_30px_rgba(6,182,212,0.3)] backdrop-blur-md flex items-center gap-4">
            <div className="w-8 h-8 rounded-full bg-cyan-500/20 flex items-center justify-center text-cyan-400">
              <span className="material-symbols-outlined text-lg">info</span>
            </div>
            <span className="font-mono text-sm font-bold text-slate-100 tracking-wide">{toastMessage}</span>
            <button onClick={() => setToastMessage(null)} className="ml-4 text-slate-400 hover:text-white transition-colors cursor-pointer">
              <span className="material-symbols-outlined text-lg">close</span>
            </button>
          </div>
        </div>
      )}

      {reviewingAlert && (
        <VerificationModal 
          alert={reviewingAlert} 
          onClose={() => setReviewingAlert(null)}
          onConfirm={async () => {
            await resolveAlert(reviewingAlert.id, 'CONFIRM_ANOMALY');
            setReviewingAlert(null);
            refetchAlerts();
            refetchHotspots();
            showToast('Anomaly CONFIRMED. Escalating to response teams.');
          }}
          onDismiss={async () => {
            await resolveAlert(reviewingAlert.id, 'DISMISS');
            setReviewingAlert(null);
            refetchAlerts();
            refetchHotspots();
            showToast('Alert DISMISSED as false alarm.');
          }}
        />
      )}
    </div>
  );
};


