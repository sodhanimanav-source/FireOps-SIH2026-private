"""
Typed contracts exchanged between the six pipeline stages.

These dataclasses are the *only* coupling between stages. A stage imports
schemas from ``core`` and never from a sibling stage, which is what keeps the
dependency graph acyclic and lets any encoder be swapped or mocked.

Every schema is JSON-serialisable via ``to_dict()`` so that the FastAPI layer
and the SQLite intelligence store can persist stage output verbatim, without
the API layer needing to know how any model works.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class StageStatus(str, Enum):
    """Health of an individual encoder for one anomaly."""

    OK = "OK"                   # ran as designed
    FALLBACK = "FALLBACK"       # degraded analytic path was used
    SKIPPED = "SKIPPED"         # gated out on purpose (e.g. biomass short-circuit)
    FAILED = "FAILED"           # errored; downstream must treat it as missing


class ThermalClass(str, Enum):
    """Physics-level verdict produced by Stage 2."""

    BIOMASS = "BIOMASS"                 # T < gate: forest / agricultural burning
    INDUSTRIAL_CANDIDATE = "INDUSTRIAL_CANDIDATE"  # T >= gate: needs AI analysis
    INDETERMINATE = "INDETERMINATE"     # retrieval failed; no physical verdict


class SourceClass(str, Enum):
    """Final operational classification produced by Stage 6."""

    ROUTINE_FLARING = "ROUTINE_FLARING"
    FLARE_SPIKE = "FLARE_SPIKE"
    INDUSTRIAL_ACCIDENT = "INDUSTRIAL_ACCIDENT"
    COAL_MINE_FIRE = "COAL_MINE_FIRE"
    AGRICULTURAL_BURNING = "AGRICULTURAL_BURNING"
    WILDFIRE = "WILDFIRE"
    UNCLASSIFIED = "UNCLASSIFIED"


SEVERITY_BY_CLASS: Dict[str, str] = {
    SourceClass.INDUSTRIAL_ACCIDENT.value: "CRITICAL",
    SourceClass.WILDFIRE.value: "CRITICAL",
    SourceClass.FLARE_SPIKE.value: "HIGH",
    SourceClass.COAL_MINE_FIRE.value: "HIGH",
    SourceClass.AGRICULTURAL_BURNING.value: "MEDIUM",
    SourceClass.ROUTINE_FLARING.value: "LOW",
    SourceClass.UNCLASSIFIED.value: "LOW",
}

HUMAN_LABELS: Dict[str, str] = {
    SourceClass.ROUTINE_FLARING.value: "Routine Gas Flaring",
    SourceClass.FLARE_SPIKE.value: "Abnormal Flare Spike",
    SourceClass.INDUSTRIAL_ACCIDENT.value: "Industrial Accident / Refinery Fire",
    SourceClass.COAL_MINE_FIRE.value: "Coal Mine Fire",
    SourceClass.AGRICULTURAL_BURNING.value: "Agricultural Burning",
    SourceClass.WILDFIRE.value: "Wildfire",
    SourceClass.UNCLASSIFIED.value: "Unclassified Thermal Source",
}


def event_id_for(lat: float, lng: float) -> str:
    """
    Stable event identifier for a coordinate, quantised to ~1 km.

    Quantising matters: the same flare re-detected on the next orbit shifts by
    a few hundred metres, and an un-quantised id would create a brand new
    "event" on every pass. Exposed as a module function so the API layer can
    look up intelligence for a coordinate without constructing a Hotspot.
    """
    key = f"{round(lat, 2):.2f}:{round(lng, 2):.2f}"
    digest = hashlib.md5(key.encode()).hexdigest()[:10].upper()
    return f"EVT-{digest}"


def _clean(value: Any) -> Any:
    """Recursively make a value JSON-safe (NaN/Inf -> None, Enum -> value)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else round(value, 6)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass
class _Serialisable:
    def to_dict(self) -> Dict[str, Any]:
        return _clean(asdict(self))


# ---------------------------------------------------------------------------
# Stage 1 — Ingestion
# ---------------------------------------------------------------------------
@dataclass
class Hotspot(_Serialisable):
    """
    A single thermal anomaly, normalised across VIIRS / MODIS / INSAT.

    Brightness temperatures are kept in Kelvin exactly as the sensor reports
    them; Stage 2 is the only component allowed to convert them to radiance.
    """

    lat: float
    lng: float
    acq_datetime: Optional[str] = None
    sensor: str = "UNKNOWN"
    platform: str = "LEO"                # LEO (FIRMS) | GEO (INSAT)
    # Mid-wave infrared brightness temperature (K) — VIIRS I4 / MODIS b21.
    bright_mir_k: Optional[float] = None
    # Thermal infrared brightness temperature (K) — VIIRS I5 / MODIS b31.
    bright_tir_k: Optional[float] = None
    frp_mw: float = 0.0
    confidence: Optional[float] = None
    daynight: str = "D"
    scan_km: Optional[float] = None
    track_km: Optional[float] = None
    pixel_area_m2: Optional[float] = None
    mir_wavelength_um: Optional[float] = None
    tir_wavelength_um: Optional[float] = None
    background_temp_k: Optional[float] = None
    risk_score: float = 0.0
    # GEO context attached by the fusion step in Stage 1.
    geo_observation_count: int = 0
    geo_persistence_hours: float = 0.0
    geo_series: List[Dict[str, Any]] = field(default_factory=list)
    imagery_data: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        """Stable identifier, quantised to ~1 km. See :func:`event_id_for`."""
        return event_id_for(self.lat, self.lng)

    # Convenience accessors used by legacy code paths -----------------------
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style access so legacy helpers keep working unchanged."""
        if hasattr(self, key):
            return getattr(self, key)
        aliases = {
            "latitude": self.lat,
            "longitude": self.lng,
            "lon": self.lng,
            "brightness": self.bright_mir_k,
            "bright_ti4": self.bright_mir_k,
            "bright_ti5": self.bright_tir_k,
            "frp": self.frp_mw,
        }
        if key in aliases:
            return aliases[key] if aliases[key] is not None else default
        return self.raw.get(key, default)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key, None)
        if value is None and not hasattr(self, key) and key not in self.raw:
            raise KeyError(key)
        return value


@dataclass
class InsatCube(_Serialisable):
    """
    Hyper-temporal GEO stack from INSAT-3D / 3DR / 3DS.

    A cube holds the last N hours of 30-minute MIR/TIR frames over the area of
    interest. Its value is temporal, not spatial: it is what makes Stage 5 able
    to recover an operational rhythm that LEO's 2-passes-per-day cannot.
    """

    satellites: List[str] = field(default_factory=list)
    frames: List[Dict[str, Any]] = field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    revisit_minutes: int = 30
    spatial_resolution_km: float = 4.0
    source: str = "unavailable"          # live | cache | synthetic | unavailable
    status: StageStatus = StageStatus.OK
    notes: str = ""

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def series_near(self, lat: float, lng: float, radius_km: float = 4.0) -> List[Dict[str, Any]]:
        """All GEO samples whose footprint contains the given point."""
        out: List[Dict[str, Any]] = []
        # 1 deg latitude ~ 111 km; longitude shrinks with cos(lat).
        dlat = radius_km / 111.0
        cos_lat = max(0.1, math.cos(math.radians(lat)))
        dlng = dlat / cos_lat
        for frame in self.frames:
            for sample in frame.get("samples", []):
                if (
                    abs(sample.get("lat", 999.0) - lat) <= dlat
                    and abs(sample.get("lng", 999.0) - lng) <= dlng
                ):
                    enriched = dict(sample)
                    enriched["timestamp"] = frame.get("timestamp")
                    enriched["satellite"] = frame.get("satellite")
                    out.append(enriched)
        out.sort(key=lambda s: str(s.get("timestamp") or ""))
        return out


# ---------------------------------------------------------------------------
# Stage 2 — Physics
# ---------------------------------------------------------------------------
@dataclass
class PlanckSolution(_Serialisable):
    """
    Result of inverting Planck's radiation law for one anomaly.

    Supports tuple unpacking — ``temp, frac = solution`` — so the earlier
    two-value call convention in ``agent_loop`` keeps working.
    """

    subpixel_temp_k: float
    fractional_area: float
    background_temp_k: float
    thermal_class: ThermalClass = ThermalClass.INDETERMINATE
    gate_threshold_k: float = 1200.0
    passed_gate: bool = False
    method: str = "dozier_bispectral"
    residual: float = 0.0
    converged: bool = False
    # False when the retrieved temperature exceeds what terrestrial combustion
    # in air can physically reach, which signals a noise-driven solution
    # rather than an extraordinarily hot fire.
    retrieval_plausible: bool = True
    fire_area_m2: float = 0.0
    frp_retrieved_mw: Optional[float] = None
    frp_observed_mw: Optional[float] = None
    frp_agreement: Optional[float] = None
    mir_radiance: Optional[float] = None
    tir_radiance: Optional[float] = None
    status: StageStatus = StageStatus.OK
    notes: str = ""

    def __iter__(self) -> Iterator[float]:
        yield self.subpixel_temp_k
        yield self.fractional_area

    @property
    def is_industrial_candidate(self) -> bool:
        return self.thermal_class is ThermalClass.INDUSTRIAL_CANDIDATE


# ---------------------------------------------------------------------------
# Stage 3 — Graph
# ---------------------------------------------------------------------------
@dataclass
class GraphNode(_Serialisable):
    node_id: str
    kind: str                            # tank | flare | chimney | building | works | ...
    name: str = "unnamed"
    lat: float = 0.0
    lng: float = 0.0
    distance_m: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class GraphContext(_Serialisable):
    """Topological description of the industrial ecosystem around an anomaly."""

    embedding: List[float] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    pipeline_edges: int = 0
    tank_count: int = 0
    flare_count: int = 0
    chimney_count: int = 0
    building_count: int = 0
    # 0..1 — how strongly the local topology resembles a connected industrial
    # plant rather than scattered unrelated features.
    industrial_topology_score: float = 0.0
    connectivity: float = 0.0
    nearest_node: Optional[GraphNode] = None
    linked_osm_node: str = "None"
    facility_name: Optional[str] = None
    # Distance at which the graph was still recognisably the same facility;
    # quantifies immunity to satellite geolocation error.
    geolocation_tolerance_m: float = 0.0
    encoder: str = "graphsage"           # graphsage | graphsage_numpy | heuristic
    source: str = "unavailable"          # overpass | cache | facilities | unavailable
    status: StageStatus = StageStatus.OK
    notes: str = ""
    nodes: List[GraphNode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 4 — Vision
# ---------------------------------------------------------------------------
@dataclass
class VisionContext(_Serialisable):
    """Prithvi-EO-2.0 spatiotemporal semantics for the anomaly footprint."""

    embedding: List[float] = field(default_factory=list)
    # 0..1 — permanent built infrastructure (concrete, metal, roads).
    permanent_structure_score: float = 0.0
    # 0..1 — transient vegetation burn scar.
    burn_scar_score: float = 0.0
    vegetation_index: Optional[float] = None
    built_up_index: Optional[float] = None
    burn_index: Optional[float] = None
    temporal_stability: float = 0.0      # how static the scene is across frames
    frames_used: int = 0
    model_id: str = ""
    encoder: str = "prithvi_eo_2"        # prithvi_eo_2 | spectral_heuristic
    status: StageStatus = StageStatus.OK
    notes: str = ""


# ---------------------------------------------------------------------------
# Stage 5 — Time
# ---------------------------------------------------------------------------
@dataclass
class TemporalContext(_Serialisable):
    """Continuous-time operational rhythm recovered from irregular passes."""

    embedding: List[float] = field(default_factory=list)
    event_count: int = 0
    observation_span_h: float = 0.0
    # 0..1 — how continuously present the thermal source is.
    persistence_score: float = 0.0
    # 0..1 — strength of a repeating operational cycle.
    periodicity_score: float = 0.0
    dominant_period_h: Optional[float] = None
    rhythm_regularity: float = 0.0
    burst_score: float = 0.0             # high = sudden departure from rhythm
    mean_intensity: float = 0.0
    intensity_trend: float = 0.0
    mtpp_intensity: float = 0.0          # fitted point-process intensity (events/h)
    encoder: str = "contiformer_ode"     # contiformer_ode | contiformer_numpy | statistical
    status: StageStatus = StageStatus.OK
    notes: str = ""


# ---------------------------------------------------------------------------
# Stage 6 — Fusion
# ---------------------------------------------------------------------------
@dataclass
class FusionDecision(_Serialisable):
    """Final multi-modal verdict with a full explainability trace."""

    classification: str = SourceClass.UNCLASSIFIED.value
    label: str = ""
    severity: str = "LOW"
    confidence: float = 0.0
    # Stage-2 temperature turned into an attention multiplier.
    thermal_gate_multiplier: float = 0.0
    attention_weights: Dict[str, float] = field(default_factory=dict)
    modality_contributions: Dict[str, float] = field(default_factory=dict)
    class_probabilities: Dict[str, float] = field(default_factory=dict)
    osm_linked_node: str = "None"
    requires_hitl: bool = True
    evidence: List[str] = field(default_factory=list)
    degraded_stages: List[str] = field(default_factory=list)
    encoder: str = "cross_modal_attention"
    status: StageStatus = StageStatus.OK
    notes: str = ""

    # Backwards-compatible dict access — the previous orchestrator did
    # ``fusion_results['confidence']`` and ``fusion_results.get('osm_linked_node')``.
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)


# ---------------------------------------------------------------------------
# Whole-pipeline record
# ---------------------------------------------------------------------------
@dataclass
class PipelineResult(_Serialisable):
    """Everything the six stages learned about one anomaly."""

    event_id: str
    lat: float
    lng: float
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    hotspot: Optional[Dict[str, Any]] = None
    physics: Optional[Dict[str, Any]] = None
    graph: Optional[Dict[str, Any]] = None
    vision: Optional[Dict[str, Any]] = None
    temporal: Optional[Dict[str, Any]] = None
    fusion: Optional[Dict[str, Any]] = None
    stage_status: Dict[str, str] = field(default_factory=dict)
    stage_timings_ms: Dict[str, float] = field(default_factory=dict)
    gated_at_stage: Optional[int] = None
    cycle_id: Optional[str] = None

    # --- Flattened intelligence fields consumed by the API/GeoJSON layer ---
    @property
    def ai_confidence(self) -> float:
        return float((self.fusion or {}).get("confidence", 0.0) or 0.0)

    @property
    def sub_pixel_temp(self) -> Optional[float]:
        """
        Retrieved source temperature, or None when no retrieval was possible.

        Reporting 0 K for a failed retrieval would be read as "ice cold" by
        anything consuming this field, so an unretrieved anomaly returns None.
        """
        physics = self.physics or {}
        if not physics.get("converged"):
            return None
        value = physics.get("subpixel_temp_k")
        return float(value) if value else None

    @property
    def linked_osm_node(self) -> str:
        return str((self.fusion or {}).get("osm_linked_node", "None") or "None")

    @property
    def classification(self) -> str:
        return str(
            (self.fusion or {}).get("classification", SourceClass.UNCLASSIFIED.value)
        )

    def intelligence_properties(self) -> Dict[str, Any]:
        """The exact property block served inside the API GeoJSON features."""
        physics = self.physics or {}
        graph = self.graph or {}
        vision = self.vision or {}
        temporal = self.temporal or {}
        fusion = self.fusion or {}
        return _clean(
            {
                "AI_Confidence": self.ai_confidence,
                "Sub_Pixel_Temp": self.sub_pixel_temp,
                "Linked_OSM_Node": self.linked_osm_node,
                "event_id": self.event_id,
                "predicted_class": self.classification,
                "label": fusion.get("label"),
                "priority": fusion.get("severity", "LOW"),
                "requires_hitl": fusion.get("requires_hitl", True),
                "thermal_class": physics.get("thermal_class"),
                "fractional_area": physics.get("fractional_area"),
                "fire_area_m2": physics.get("fire_area_m2"),
                "thermal_gate_multiplier": fusion.get("thermal_gate_multiplier"),
                "attention_weights": fusion.get("attention_weights", {}),
                "class_probabilities": fusion.get("class_probabilities", {}),
                "industrial_topology_score": graph.get("industrial_topology_score"),
                "linked_facility": graph.get("facility_name"),
                "permanent_structure_score": vision.get("permanent_structure_score"),
                "burn_scar_score": vision.get("burn_scar_score"),
                "persistence_score": temporal.get("persistence_score"),
                "periodicity_score": temporal.get("periodicity_score"),
                "dominant_period_h": temporal.get("dominant_period_h"),
                "evidence": fusion.get("evidence", []),
                "degraded_stages": fusion.get("degraded_stages", []),
                "stage_status": self.stage_status,
                "detected_at": self.detected_at,
            }
        )


__all__ = [
    "event_id_for",
    "StageStatus",
    "ThermalClass",
    "SourceClass",
    "SEVERITY_BY_CLASS",
    "HUMAN_LABELS",
    "Hotspot",
    "InsatCube",
    "PlanckSolution",
    "GraphNode",
    "GraphContext",
    "VisionContext",
    "TemporalContext",
    "FusionDecision",
    "PipelineResult",
]
