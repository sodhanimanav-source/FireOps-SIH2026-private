"""
Central configuration for the FireOps 6-stage pipeline.

Every tunable constant in the pipeline lives here so that the scientific
thresholds (especially the 1200 K industrial combustion gate) are declared
in exactly one place and can be audited by reviewers.

All values can be overridden with environment variables, which keeps the
deployment (Render / Docker / judge's laptop) configurable without code
edits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

try:  # python-dotenv is in requirements.txt but must never be a hard failure
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))


@dataclass(frozen=True)
class Paths:
    """Filesystem layout (absolute, so the loop can be started from anywhere)."""

    root: str = _ROOT
    data: str = os.path.join(_ROOT, "data")
    cache: str = os.path.join(_ROOT, "data", "cache")
    osm_graph_cache: str = os.path.join(_ROOT, "data", "cache", "osm_graph")
    insat_cache: str = os.path.join(_ROOT, "data", "cache", "insat")
    vision_cache: str = os.path.join(_ROOT, "data", "cache", "vision")
    intelligence_db: str = os.path.join(_ROOT, "data", "intelligence.sqlite3")
    facilities: str = os.path.join(_ROOT, "data", "facilities.json")
    hotspots_backup: str = os.path.join(_ROOT, "data", "hotspots_backup.csv")

    def ensure(self) -> None:
        for directory in (
            self.data,
            self.cache,
            self.osm_graph_cache,
            self.insat_cache,
            self.vision_cache,
        ):
            os.makedirs(directory, exist_ok=True)


@dataclass(frozen=True)
class PhysicsSettings:
    """Stage 2 — Sub-pixel thermodynamics (Planck inversion)."""

    # ---- Planck constants (λ in micrometres, L in W m-2 sr-1 um-1) ---------
    # c1 = 2hc^2, c2 = hc/k_B  (CODATA 2018)
    c1: float = 1.191042953e8
    c2: float = 1.4387768775e4

    # ---- Sensor band centres ---------------------------------------------
    # VIIRS I4 (3.74 um) / I5 (11.45 um); MODIS band 21 (3.96) / 31 (11.03).
    viirs_mir_um: float = 3.74
    viirs_tir_um: float = 11.45
    modis_mir_um: float = 3.96
    modis_tir_um: float = 11.03
    # INSAT-3D imager: MIR 3.9 um, TIR-1 10.8 um.
    insat_mir_um: float = 3.90
    insat_tir_um: float = 10.80

    # ---- THE GATE --------------------------------------------------------
    # Biomass combustion (forest / crop residue) flame temperatures sit in the
    # 600-1100 K band. Gas flares, steel furnaces and refinery stacks burn at
    # 1400-2200 K. 1200 K is the separating threshold for the whole system.
    industrial_temperature_gate_k: float = _env_float("FIREOPS_TEMP_GATE_K", 1200.0)

    # Smoothing width (K) used to turn the hard gate into a differentiable
    # attention multiplier in Stage 6. A hard step would make confidence
    # discontinuous at 1199.9 K vs 1200.1 K.
    gate_softness_k: float = _env_float("FIREOPS_GATE_SOFTNESS_K", 120.0)

    # ---- Dozier solver bounds --------------------------------------------
    solver_min_temp_k: float = 400.0
    solver_max_temp_k: float = 3000.0
    solver_iterations: int = _env_int("FIREOPS_SOLVER_ITERS", 60)
    default_background_temp_k: float = _env_float("FIREOPS_BG_TEMP_K", 295.0)

    # Minimum fractional area for a retrieval to be considered physical.
    min_fractional_area: float = 1e-7
    max_fractional_area: float = 0.5

    # Stefan-Boltzmann constant, for the FRP cross-check (W m-2 K-4).
    stefan_boltzmann: float = 5.670374419e-8
    # Wooster et al. (2003) empirical FRP radiative coefficient (W m-2 K-4).
    wooster_a: float = 3.0e-9


@dataclass(frozen=True)
class IngestionSettings:
    """Stage 1 — Hybrid LEO + GEO multi-sensor fusion."""

    firms_map_key: str = os.getenv("FIRMS_MAP_KEY", "").strip()
    firms_bbox: str = os.getenv("FIREOPS_BBOX", "68,6,97,37")  # India
    firms_day_range: int = _env_int("FIREOPS_FIRMS_DAYS", 2)
    http_timeout_s: float = _env_float("FIREOPS_HTTP_TIMEOUT", 15.0)

    # INSAT-3D / 3DR / 3DS — MOSDAC hyper-temporal GEO imager.
    insat_enabled: bool = _env_bool("FIREOPS_INSAT_ENABLED", True)
    insat_base_url: str = os.getenv(
        "FIREOPS_INSAT_URL", "https://mosdac.gov.in/apiservices"
    )
    insat_token: str = os.getenv("MOSDAC_TOKEN", "").strip()
    insat_satellites: tuple = ("INSAT-3D", "INSAT-3DR", "INSAT-3DS")
    insat_revisit_minutes: int = _env_int("FIREOPS_INSAT_REVISIT_MIN", 30)
    insat_lookback_hours: int = _env_int("FIREOPS_INSAT_LOOKBACK_H", 72)
    insat_spatial_res_km: float = 4.0  # MIR/TIR imager resolution at nadir

    # LEO<->GEO association radius. INSAT pixels are ~4 km, VIIRS ~375 m, so a
    # LEO detection is matched to the GEO cell that contains it.
    fusion_radius_km: float = _env_float("FIREOPS_FUSION_RADIUS_KM", 4.0)
    cache_ttl_s: int = _env_int("FIREOPS_INSAT_CACHE_TTL", 900)


@dataclass(frozen=True)
class GraphSettings:
    """Stage 3 — OSM topological structure (GraphSAGE)."""

    overpass_url: str = os.getenv(
        "FIREOPS_OVERPASS_URL", "https://overpass-api.de/api/interpreter"
    )
    query_radius_m: int = _env_int("FIREOPS_OSM_RADIUS_M", 2500)
    # Geolocation-error immunity: satellite geolocation error is up to ~1.5 km,
    # so the graph is built over a wider disc than the nominal anomaly point.
    geolocation_tolerance_m: int = _env_int("FIREOPS_GEO_TOLERANCE_M", 1500)
    max_nodes: int = _env_int("FIREOPS_OSM_MAX_NODES", 512)
    embedding_dim: int = _env_int("FIREOPS_GNN_DIM", 64)
    sage_layers: int = _env_int("FIREOPS_GNN_LAYERS", 2)
    cache_ttl_s: int = _env_int("FIREOPS_OSM_CACHE_TTL", 604800)  # 7 days
    # Overpass is a free, heavily shared public service and frequently
    # rate-limits or stalls. Fail fast: a slow graph is worth far less than a
    # fast pipeline, because the local facility database covers the fallback.
    http_timeout_s: float = _env_float("FIREOPS_OVERPASS_TIMEOUT", 8.0)
    # Circuit breaker — after this many consecutive failures, stop calling
    # Overpass entirely for `breaker_cooldown_s`. Without this, every anomaly
    # in every cycle pays the full timeout, which dominates the runtime.
    breaker_threshold: int = _env_int("FIREOPS_OSM_BREAKER_THRESHOLD", 3)
    breaker_cooldown_s: int = _env_int("FIREOPS_OSM_BREAKER_COOLDOWN", 600)
    # Remember empty/failed lookups too, so a barren location is not queried
    # again on the next pass.
    negative_cache_ttl_s: int = _env_int("FIREOPS_OSM_NEG_CACHE_TTL", 3600)
    offline_only: bool = _env_bool("FIREOPS_OSM_OFFLINE", False)


@dataclass(frozen=True)
class VisionSettings:
    """Stage 4 — Prithvi-EO-2.0 visual semantic memory."""

    model_id: str = os.getenv(
        "PRITHVI_MODEL_ID", "ibm-nasa-geospatial/Prithvi-EO-2.0-300M"
    )
    enabled: bool = _env_bool("FIREOPS_PRITHVI_ENABLED", True)
    device: str = os.getenv("FIREOPS_TORCH_DEVICE", "cpu")
    image_size: int = _env_int("FIREOPS_PRITHVI_IMG", 224)
    num_frames: int = _env_int("FIREOPS_PRITHVI_FRAMES", 3)  # spatiotemporal
    embedding_dim: int = _env_int("FIREOPS_VISION_DIM", 64)
    hf_token: Optional[str] = os.getenv("HF_TOKEN") or os.getenv(
        "HUGGINGFACE_HUB_TOKEN"
    )
    # Prithvi-EO-2.0 HLS band order: Blue, Green, Red, NIR-Narrow, SWIR-1, SWIR-2
    bands: tuple = ("B02", "B03", "B04", "B8A", "B11", "B12")
    load_timeout_s: float = _env_float("FIREOPS_PRITHVI_TIMEOUT", 120.0)


@dataclass(frozen=True)
class TemporalSettings:
    """Stage 5 — ContiFormer / Neural-ODE time rhythm dynamics."""

    enabled: bool = _env_bool("FIREOPS_CONTIFORMER_ENABLED", True)
    latent_dim: int = _env_int("FIREOPS_ODE_DIM", 32)
    attention_heads: int = _env_int("FIREOPS_CONTIFORMER_HEADS", 4)
    # Continuous-time attention decay constant (hours). Events further apart
    # than a few tau contribute little to each other's representation.
    attention_tau_h: float = _env_float("FIREOPS_ATTENTION_TAU_H", 12.0)
    ode_solver_steps: int = _env_int("FIREOPS_ODE_STEPS", 4)
    min_events_for_rhythm: int = _env_int("FIREOPS_MIN_EVENTS", 4)
    # Industrial flaring is diurnal/continuous; the periodogram searches for
    # rhythms between 1 hour and 7 days.
    min_period_h: float = 1.0
    max_period_h: float = 168.0
    periodogram_resolution: int = _env_int("FIREOPS_PERIODOGRAM_RES", 512)


@dataclass(frozen=True)
class FusionSettings:
    """Stage 6 — Cross-modal attention and decision."""

    embedding_dim: int = _env_int("FIREOPS_FUSION_DIM", 64)
    attention_heads: int = _env_int("FIREOPS_FUSION_HEADS", 4)
    # Operator review gate: anything below this confidence goes to a human.
    hitl_confidence_threshold: float = _env_float("FIREOPS_HITL_THRESHOLD", 0.85)
    # Each failed encoder costs this much confidence — a degraded pipeline must
    # never report the same certainty as a fully healthy one.
    degraded_stage_penalty: float = _env_float("FIREOPS_DEGRADED_PENALTY", 0.08)
    max_confidence_degraded: float = _env_float("FIREOPS_MAX_CONF_DEGRADED", 0.84)


@dataclass(frozen=True)
class AgentSettings:
    """Orchestrator behaviour."""

    poll_interval_s: int = _env_int("FIREOPS_POLL_INTERVAL", 60)
    error_backoff_s: int = _env_int("FIREOPS_ERROR_BACKOFF", 15)
    max_events_per_cycle: int = _env_int("FIREOPS_MAX_EVENTS", 25)
    stage_workers: int = _env_int("FIREOPS_STAGE_WORKERS", 3)
    # Hard wall-clock budget for each parallel encoder. A hung HTTP call in
    # Stage 3 must never stall the whole national monitoring loop.
    stage_timeout_s: float = _env_float("FIREOPS_STAGE_TIMEOUT", 45.0)
    reprocess_after_s: int = _env_int("FIREOPS_REPROCESS_AFTER", 21600)  # 6 h
    enabled: bool = _env_bool("FIREOPS_AGENT_ENABLED", True)


@dataclass(frozen=True)
class Settings:
    paths: Paths = field(default_factory=Paths)
    physics: PhysicsSettings = field(default_factory=PhysicsSettings)
    ingestion: IngestionSettings = field(default_factory=IngestionSettings)
    graph: GraphSettings = field(default_factory=GraphSettings)
    vision: VisionSettings = field(default_factory=VisionSettings)
    temporal: TemporalSettings = field(default_factory=TemporalSettings)
    fusion: FusionSettings = field(default_factory=FusionSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)

    log_level: str = os.getenv("FIREOPS_LOG_LEVEL", "INFO").upper()
    log_json: bool = _env_bool("FIREOPS_LOG_JSON", False)
    # Deterministic seed — the same anomaly must always produce the same
    # classification, which matters for a system that has to be auditable.
    random_seed: int = _env_int("FIREOPS_SEED", 20260101)


settings = Settings()
settings.paths.ensure()

__all__ = [
    "settings",
    "Settings",
    "Paths",
    "PhysicsSettings",
    "IngestionSettings",
    "GraphSettings",
    "VisionSettings",
    "TemporalSettings",
    "FusionSettings",
    "AgentSettings",
]
