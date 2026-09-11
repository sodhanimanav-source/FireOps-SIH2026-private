import React, { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

interface VerificationModalProps {
  alert: any;
  onConfirm: () => void;
  onDismiss: () => void;
  onClose: () => void;
}

export const VerificationModal: React.FC<VerificationModalProps> = ({ alert, onConfirm, onDismiss, onClose }) => {
  const mapBeforeRef = useRef<HTMLDivElement>(null);
  const mapAfterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mapBeforeRef.current || !mapAfterRef.current || !alert) return;

    const lat = alert.hotspot.lat;
    const lng = alert.hotspot.lng;

    
    const mapBefore = new maplibregl.Map({
      container: mapBeforeRef.current,
      style: {
        version: 8,
        sources: {
          'esri-satellite': {
            type: 'raster',
            tiles: [
              'https:
            ],
            tileSize: 256,
            attribution: 'Esri, Maxar, Earthstar Geographics'
          }
        },
        layers: [
          {
            id: 'satellite-layer',
            type: 'raster',
            source: 'esri-satellite',
            minzoom: 0,
            maxzoom: 19
          }
        ]
      },
      center: [lng, lat],
      zoom: 18,
      interactive: false,
    });

    
    const mapAfter = new maplibregl.Map({
      container: mapAfterRef.current,
      style: {
        version: 8,
        sources: {
          'esri-satellite': {
            type: 'raster',
            tiles: [
              'https:
            ],
            tileSize: 256,
          },
          'fire-source': {
            type: 'geojson',
            data: {
              type: 'FeatureCollection',
              features: [
                {
                  type: 'Feature',
                  properties: { intensity: 1 },
                  geometry: {
                    type: 'Point',
                    coordinates: [lng, lat]
                  }
                }
              ]
            }
          }
        },
        layers: [
          {
            id: 'satellite-layer',
            type: 'raster',
            source: 'esri-satellite',
            minzoom: 0,
            maxzoom: 19
          },
          {
            id: 'fire-glow',
            type: 'heatmap',
            source: 'fire-source',
            maxzoom: 19,
            paint: {
              'heatmap-weight': 1,
              'heatmap-intensity': 2,
              'heatmap-color': [
                'interpolate',
                ['linear'],
                ['heatmap-density'],
                0, 'rgba(0,0,0,0)',
                0.2, 'rgba(255,255,0,0.5)',
                0.5, 'rgba(255,153,0,0.8)',
                1.0, 'rgba(255,0,0,1)'
              ],
              'heatmap-radius': 40,
              'heatmap-opacity': 0.9
            }
          }
        ]
      },
      center: [lng, lat],
      zoom: 18,
      interactive: false,
    });

    
    const el1 = document.createElement('div');
    el1.className = 'w-4 h-4 border-2 border-cyan-400 rounded-full flex items-center justify-center';
    el1.innerHTML = '<div class="w-1 h-1 bg-cyan-400 rounded-full animate-ping"></div>';
    new maplibregl.Marker(el1).setLngLat([lng, lat]).addTo(mapBefore);

    const el2 = document.createElement('div');
    el2.className = 'w-6 h-6 border-2 border-red-500 rounded-full flex items-center justify-center bg-red-500/20';
    el2.innerHTML = '<div class="w-2 h-2 bg-red-500 rounded-full animate-ping"></div>';
    new maplibregl.Marker(el2).setLngLat([lng, lat]).addTo(mapAfter);

    return () => {
      mapBefore.remove();
      mapAfter.remove();
    };
  }, [alert]);

  if (!alert) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
      <div className="w-[90vw] max-w-5xl bg-slate-900 border border-slate-700 shadow-2xl rounded-2xl overflow-hidden flex flex-col animate-fade-in">
        
        {}
        <div className="bg-slate-800 px-6 py-4 border-b border-slate-700 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-yellow-500">satellite_alt</span>
            <h2 className="text-lg font-bold text-slate-100 font-mono tracking-widest uppercase">Bi-Temporal Satellite Verification</h2>
            <span className="bg-yellow-500/20 text-yellow-400 border border-yellow-500/50 px-2 py-0.5 rounded text-xs font-bold font-mono">HITL REQUIRED</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {}
        <div className="p-6 flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-4">
            
            {}
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center px-1">
                <span className="text-sm font-bold text-slate-300 font-mono">T0 - Baseline Imagery</span>
                <span className="text-xs text-slate-500 font-mono">Source: Esri World Imagery</span>
              </div>
              <div ref={mapBeforeRef} className="w-full h-[40vh] rounded-xl border-2 border-slate-700 overflow-hidden relative">
                <div className="absolute top-2 left-2 z-10 bg-black/60 backdrop-blur px-2 py-1 rounded text-[10px] text-white font-mono border border-white/10">Pre-Anomaly</div>
              </div>
            </div>

            {}
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center px-1">
                <span className="text-sm font-bold text-red-400 font-mono animate-pulse">T1 - Current Telemetry</span>
                <span className="text-xs text-slate-500 font-mono">Source: NASA FIRMS + Esri</span>
              </div>
              <div ref={mapAfterRef} className="w-full h-[40vh] rounded-xl border-2 border-red-500/50 overflow-hidden relative shadow-[0_0_20px_rgba(239,68,68,0.2)]">
                <div className="absolute top-2 left-2 z-10 bg-red-900/80 backdrop-blur px-2 py-1 rounded text-[10px] text-white font-mono border border-red-500/50">Active Fire Layer</div>
              </div>
            </div>

          </div>

          {}
          <div className="grid grid-cols-4 gap-4 bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div>
              <div className="text-[10px] text-slate-500 font-mono uppercase">Event ID</div>
              <div className="text-sm font-mono text-cyan-400 font-bold">{alert.id}</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 font-mono uppercase">Coordinates</div>
              <div className="text-sm font-mono text-slate-300">{alert.hotspot.lat.toFixed(4)}, {alert.hotspot.lng.toFixed(4)}</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 font-mono uppercase">AI Confidence</div>
              <div className="text-sm font-mono text-yellow-400 font-bold">{(alert.ai_results.ai_confidence * 100).toFixed(1)}%</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 font-mono uppercase">Spectral dNBR</div>
              <div className="text-sm font-mono text-slate-300">{alert.satellite_data.spectral_deltas.dNBR.toFixed(3)}</div>
            </div>
          </div>
        </div>

        {}
        <div className="bg-slate-800 px-6 py-4 border-t border-slate-700 flex justify-end gap-3">
          <button onClick={onDismiss} className="px-6 py-2 rounded font-bold font-mono text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 transition-colors border border-slate-600">
            DISMISS AS FALSE ALARM
          </button>
          <button onClick={onConfirm} className="px-6 py-2 rounded font-bold font-mono text-white bg-red-600 hover:bg-red-500 transition-colors shadow-[0_0_15px_rgba(220,38,38,0.5)]">
            CONFIRM ANOMALY
          </button>
        </div>

      </div>
    </div>
  );
};




