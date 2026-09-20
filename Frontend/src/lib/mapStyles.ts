/**
 * MapLibre basemap styles.
 *
 * Every source here is keyless, so the dashboard runs on a judge's laptop or
 * an air-gapped demo machine without anyone provisioning a Mapbox token.
 * Attribution strings are kept intact because these tile services require
 * them; do not strip them.
 *
 * Three styles, for three jobs:
 *   HYBRID_STYLE        satellite imagery + place labels — the default
 *                       tactical view, where an operator needs to see the
 *                       actual plant under the anomaly.
 *   DARK_STYLE          muted vector-style basemap for when the thermal
 *                       overlay matters more than the ground.
 *   IMAGERY_ONLY_STYLE  bare imagery with no labels, used by the bi-temporal
 *                       comparison modal so that nothing obscures the
 *                       before/after difference.
 */

import type { StyleSpecification } from "maplibre-gl";

const ESRI_IMAGERY =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

const ESRI_ATTRIBUTION =
  "Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community";

const CARTO_DARK = [
  "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
  "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
  "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
];

const CARTO_LABELS = [
  "https://a.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png",
  "https://b.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png",
  "https://c.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png",
];

const CARTO_ATTRIBUTION =
  "&copy; OpenStreetMap contributors &copy; CARTO";

/** Satellite imagery with dark place labels layered on top. */
export const HYBRID_STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
  sources: {
    "esri-imagery": {
      type: "raster",
      tiles: [ESRI_IMAGERY],
      tileSize: 256,
      maxzoom: 19,
      attribution: ESRI_ATTRIBUTION,
    },
    "carto-labels": {
      type: "raster",
      tiles: CARTO_LABELS,
      tileSize: 256,
      maxzoom: 19,
      attribution: CARTO_ATTRIBUTION,
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#04070f" } },
    { id: "imagery", type: "raster", source: "esri-imagery", paint: { "raster-opacity": 1 } },
    {
      id: "labels",
      type: "raster",
      source: "carto-labels",
      // Labels are dimmed so the thermal overlay stays the brightest thing
      // on screen — the map is context, not the subject.
      paint: { "raster-opacity": 0.75 },
    },
  ],
};

/** Muted dark basemap — maximum contrast for the hotspot overlay. */
export const DARK_STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
  sources: {
    "carto-dark": {
      type: "raster",
      tiles: CARTO_DARK,
      tileSize: 256,
      maxzoom: 19,
      attribution: CARTO_ATTRIBUTION,
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#04070f" } },
    { id: "basemap", type: "raster", source: "carto-dark", paint: { "raster-opacity": 0.9 } },
  ],
};

/** Imagery with no labels — for before/after change comparison. */
export const IMAGERY_ONLY_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    "esri-imagery": {
      type: "raster",
      tiles: [ESRI_IMAGERY],
      tileSize: 256,
      maxzoom: 19,
      attribution: ESRI_ATTRIBUTION,
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#04070f" } },
    { id: "imagery", type: "raster", source: "esri-imagery" },
  ],
};
