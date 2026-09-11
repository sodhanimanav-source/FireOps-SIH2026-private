import React, { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useFacilities, useHotspots } from '../../api/queries';
import { useAppStore } from '../../store/appStore';
import { facilitiesToGeoJSON, hotspotsToGeoJSON, filterHotspots } from '../../utils/geoUtils';


type MapLayerType = 'google-hybrid' | 'google-satellite' | 'google-roadmap' | 'google-terrain';

const MAP_TILE_SOURCES: Record<MapLayerType, { name: string; url: string; subtext: string }> = {
  'google-hybrid': {
    name: 'Google Hybrid',
    url: 'https:
    subtext: 'High-Res Satellite + Street Labels',
  },
  'google-satellite': {
    name: 'Google Satellite',
    url: 'https:
    subtext: 'Pure Earth Satellite View',
  },
  'google-roadmap': {
    name: 'Google Roadmap',
    url: 'https:
    subtext: 'Standard High-Contrast Streets',
  },
  'google-terrain': {
    name: 'Google Terrain',
    url: 'https:
    subtext: 'Topographical Elevation View',
  },
};

export const MapController: React.FC = () => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [activeMapType, setActiveMapType] = useState<MapLayerType>('google-hybrid');
  const [isLayerMenuOpen, setIsLayerMenuOpen] = useState(false);
  const [mapLoaded, setMapLoaded] = useState(false);

  const { data: facilities } = useFacilities();
  const { data: hotspots } = useHotspots();

  const {
    setSelectedFacility,
    setSelectedHotspot,
    anomalyFilters,
    viewMode,
  } = useAppStore();

  
  useEffect(() => {
    if (mapContainer.current && !mapRef.current) {
      mapRef.current = new maplibregl.Map({
        container: mapContainer.current,
        style: {
          version: 8,
          sources: {
            'google-hybrid': {
              type: 'raster',
              tiles: [MAP_TILE_SOURCES['google-hybrid'].url],
              tileSize: 256,
              attribution: '© Google Maps',
            },
            'google-satellite': {
              type: 'raster',
              tiles: [MAP_TILE_SOURCES['google-satellite'].url],
              tileSize: 256,
              attribution: '© Google Maps',
            },
            'google-roadmap': {
              type: 'raster',
              tiles: [MAP_TILE_SOURCES['google-roadmap'].url],
              tileSize: 256,
              attribution: '© Google Maps',
            },
            'google-terrain': {
              type: 'raster',
              tiles: [MAP_TILE_SOURCES['google-terrain'].url],
              tileSize: 256,
              attribution: '© Google Maps',
            },
          },
          layers: [
            {
              id: 'layer-google-hybrid',
              type: 'raster',
              source: 'google-hybrid',
              minzoom: 0,
              maxzoom: 21,
              layout: { visibility: 'visible' },
            },
            {
              id: 'layer-google-satellite',
              type: 'raster',
              source: 'google-satellite',
              minzoom: 0,
              maxzoom: 21,
              layout: { visibility: 'none' },
            },
            {
              id: 'layer-google-roadmap',
              type: 'raster',
              source: 'google-roadmap',
              minzoom: 0,
              maxzoom: 21,
              layout: { visibility: 'none' },
            },
            {
              id: 'layer-google-terrain',
              type: 'raster',
              source: 'google-terrain',
              minzoom: 0,
              maxzoom: 21,
              layout: { visibility: 'none' },
            },
          ],
        },
        center: [78.9629, 20.5937], 
        zoom: 4.5,
      });

      
      mapRef.current.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), 'bottom-right');
      mapRef.current.addControl(new maplibregl.FullscreenControl(), 'bottom-right');

      mapRef.current.on('load', () => {
        const map = mapRef.current;
        if (!map) return;

        
        map.addSource('facilities', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [],
          },
        });

        
        map.addLayer({
          id: 'facilities-buffer-layer',
          type: 'circle',
          source: 'facilities',
          paint: {
            'circle-radius': 18,
            'circle-color': '#06b6d4',
            'circle-opacity': 0.2,
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#22d3ee',
            'circle-stroke-opacity': 0.6,
          },
        });

        
        map.addLayer({
          id: 'facilities-layer',
          type: 'circle',
          source: 'facilities',
          paint: {
            'circle-radius': 7,
            'circle-color': '#0284c7',
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff',
          },
        });

        
        map.addSource('hotspots', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [],
          },
        });

        
        map.addLayer({
          id: 'hotspots-glow-layer',
          type: 'circle',
          source: 'hotspots',
          paint: {
            'circle-radius': 14,
            'circle-color': [
            'match',
            ['get', 'severity'],
            'CRITICAL', '#ef4444',
            'MEDIUM', '#f59e0b',
            '#eab308'
          ],
            'circle-opacity': 0.35,
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#f87171',
            'circle-stroke-opacity': 0.8,
          },
        });

        
        map.addLayer({
          id: 'hotspots-layer',
          type: 'circle',
          source: 'hotspots',
          paint: {
            'circle-radius': 6,
            'circle-color': [
            'match',
            ['get', 'severity'],
            'CRITICAL', '#dc2626',
            'MEDIUM', '#d97706',
            '#ca8a04'
          ],
            'circle-stroke-width': 2,
            'circle-stroke-color': '#fef08a', 
          },
        });

        
        map.on('click', 'facilities-layer', (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
          if (e.features && e.features.length > 0) {
            const feature = e.features[0];
            setSelectedFacility(feature.properties?.id ?? null);
          }
        });

        
        map.on('click', 'hotspots-layer', (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
          if (e.features && e.features.length > 0) {
            const feature = e.features[0];
            setSelectedHotspot(feature.properties?.id ?? null);
          }
        });

        
        const setPointer = () => { map.getCanvas().style.cursor = 'pointer'; };
        const resetPointer = () => { map.getCanvas().style.cursor = ''; };

        map.on('mouseenter', 'facilities-layer', setPointer);
        map.on('mouseleave', 'facilities-layer', resetPointer);
        map.on('mouseenter', 'hotspots-layer', setPointer);
        map.on('mouseleave', 'hotspots-layer', resetPointer);

        setMapLoaded(true);
      });
    }

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        setMapLoaded(false);
      }
    };
  }, [setSelectedFacility, setSelectedHotspot]);

  
  const handleMapTypeChange = (type: MapLayerType) => {
    setActiveMapType(type);
    setIsLayerMenuOpen(false);

    if (mapRef.current) {
      (Object.keys(MAP_TILE_SOURCES) as MapLayerType[]).forEach((layerKey) => {
        const layerId = `layer-${layerKey}`;
        if (mapRef.current?.getLayer(layerId)) {
          mapRef.current.setLayoutProperty(
            layerId,
            'visibility',
            layerKey === type ? 'visible' : 'none'
          );
        }
      });
    }
  };

  
  useEffect(() => {
    if (mapLoaded && mapRef.current && facilities) {
      setTimeout(() => {
        const source = mapRef.current?.getSource('facilities') as maplibregl.GeoJSONSource | undefined;
        if (source && typeof source.setData === 'function') {
          const displayFac = (viewMode === 'hotspots' || viewMode === 'anomalies') ? [] : facilities;
          source.setData(facilitiesToGeoJSON(displayFac));
        }
      }, 500); 
    }
  }, [facilities, mapLoaded, viewMode]);

  
  useEffect(() => {
    if (mapLoaded && mapRef.current && hotspots) {
      setTimeout(() => {
        const source = mapRef.current?.getSource('hotspots') as maplibregl.GeoJSONSource | undefined;
        if (source && typeof source.setData === 'function') {
          let filtered = hotspots;
          if (viewMode === 'facilities') {
            filtered = [];
          } else if (viewMode === 'anomalies') {
            filtered = filterHotspots(hotspots, true);
          } else {
            filtered = filterHotspots(hotspots, anomalyFilters);
          }
          source.setData(hotspotsToGeoJSON(filtered));
        }
      }, 500);
    }
  }, [hotspots, anomalyFilters, viewMode, mapLoaded]);

  return (
    <div className="relative w-full h-full">
      {}
      <section ref={mapContainer} data-testid="maplibre-container" className="w-full h-full" />

      {}
      <div className="absolute top-4 left-4 z-20">
        <div className="relative">
          <button
            type="button"
            onClick={() => setIsLayerMenuOpen(!isLayerMenuOpen)}
            className="px-3.5 py-2 rounded-xl bg-slate-900/90 hover:bg-slate-800/95 border border-cyan-500/30 text-slate-100 shadow-xl backdrop-blur-md font-mono text-xs font-bold flex items-center gap-2.5 transition-all cursor-pointer"
          >
            <span className="material-symbols-outlined text-base text-cyan-400">layers</span>
            <span>{MAP_TILE_SOURCES[activeMapType].name}</span>
            <span className="material-symbols-outlined text-sm text-slate-400">
              {isLayerMenuOpen ? 'expand_less' : 'expand_more'}
            </span>
          </button>

          {}
          {isLayerMenuOpen && (
            <div className="absolute top-12 left-0 w-60 p-2 rounded-xl bg-slate-900/95 border border-slate-700 shadow-2xl backdrop-blur-xl flex flex-col gap-1 z-30">
              <div className="px-2 py-1 text-[10px] font-mono uppercase tracking-widest text-cyan-400 font-bold">
                Google Imagery Mode
              </div>
              {(Object.keys(MAP_TILE_SOURCES) as MapLayerType[]).map((key) => {
                const item = MAP_TILE_SOURCES[key];
                const isSelected = activeMapType === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => handleMapTypeChange(key)}
                    className={`w-full text-left p-2 rounded-lg font-mono text-xs transition-all flex flex-col cursor-pointer ${
                      isSelected
                        ? 'bg-cyan-500/15 border border-cyan-400/40 text-cyan-300'
                        : 'hover:bg-slate-800 text-slate-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold">{item.name}</span>
                      {isSelected && <span className="material-symbols-outlined text-sm text-cyan-400">check</span>}
                    </div>
                    <span className="text-[10px] text-slate-400 mt-0.5">{item.subtext}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

