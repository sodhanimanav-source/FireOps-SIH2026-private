"""
STAGE 1 — Hybrid Multi-Sensor Fusion (LEO + GEO)
================================================

Why two constellations
----------------------
No single satellite can both *see small* and *look often*:

    NASA FIRMS (VIIRS / MODIS)   LEO   375 m - 1 km   ~2-4 passes per day
    ISRO INSAT-3D / 3DR / 3DS    GEO   4 km           1 frame every 30 min

A gas flare and a crop fire can look identical in a single LEO snapshot. What
separates them is *rhythm* — a flare burns through the night for months, a crop
fire is gone in six hours. Rhythm is only visible at GEO cadence, and location
is only precise at LEO resolution. This module fuses both: LEO detections
supply the geometry, INSAT supplies the hyper-temporal context that Stage 5
needs to model operational dynamics.

Outputs
-------
``fetch_firms_data()``          -> List[Hotspot]     (LEO, high spatial res)
``fetch_insat_hypertemporal()`` -> InsatCube         (GEO, high temporal res)
``fuse_leo_geo()``              -> hotspots enriched with their GEO time series

Availability
------------
MOSDAC (the ISRO data portal) requires per-user credentials, so INSAT access
degrades in three documented steps: live API -> on-disk cache -> a clearly
flagged synthetic cube. A synthetic cube is marked ``StageStatus.FALLBACK``
and that flag propagates all the way to Stage 6, which lowers the reported
confidence accordingly. The pipeline never presents reconstructed data as if
it were an observation.
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from core.config import settings
from core.logging_utils import get_logger, stage_span
from core.schemas import Hotspot, InsatCube, StageStatus

log = get_logger("stage1.ingestion")

_STAGE = 1

# Sensor -> (MIR wavelength um, TIR wavelength um, nominal pixel size km)
_SENSOR_BANDS: Dict[str, Tuple[float, float, float]] = {
    "VIIRS_NOAA20_NRT": (settings.physics.viirs_mir_um, settings.physics.viirs_tir_um, 0.375),
    "VIIRS_NOAA21_NRT": (settings.physics.viirs_mir_um, settings.physics.viirs_tir_um, 0.375),
    "VIIRS_SNPP_NRT": (settings.physics.viirs_mir_um, settings.physics.viirs_tir_um, 0.375),
    "MODIS_NRT": (settings.physics.modis_mir_um, settings.physics.modis_tir_um, 1.0),
    "INSAT": (settings.physics.insat_mir_um, settings.physics.insat_tir_um, 4.0),
}

_DEFAULT_BANDS = (settings.physics.viirs_mir_um, settings.physics.viirs_tir_um, 0.375)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if text == "" or text.lower() in {"nan", "none", "null"}:
            return default
        number = float(text)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _parse_confidence(value: Any) -> Optional[float]:
    """FIRMS reports confidence as 0-100 (MODIS) or l/n/h (VIIRS)."""
    if value is None:
        return None
    text = str(value).strip().lower()
    mapping = {"l": 0.3, "n": 0.7, "h": 0.95, "low": 0.3, "nominal": 0.7, "high": 0.95}
    if text in mapping:
        return mapping[text]
    number = _safe_float(text)
    if number is None:
        return None
    return round(number / 100.0, 4) if number > 1.0 else round(number, 4)


def _parse_acq_datetime(date_value: Any, time_value: Any) -> Optional[str]:
    """FIRMS gives acq_date='2026-09-20' and acq_time='0342' (UTC HHMM)."""
    date_text = str(date_value or "").strip()
    if not date_text or date_text.lower() in {"nan", "n/a", "none"}:
        return None
    raw_time = str(time_value or "0").strip()
    if raw_time.lower() in {"nan", "none", ""}:
        raw_time = "0"
    digits = "".join(ch for ch in raw_time if ch.isdigit()).zfill(4)[-4:]
    try:
        hour, minute = int(digits[:2]), int(digits[2:])
        hour = min(23, max(0, hour))
        minute = min(59, max(0, minute))
        parsed = datetime.strptime(date_text[:10], "%Y-%m-%d").replace(
            hour=hour, minute=minute, tzinfo=timezone.utc
        )
        return parsed.isoformat()
    except (ValueError, TypeError):
        return None


def _pixel_area_m2(scan_km: Optional[float], track_km: Optional[float], fallback_km: float) -> float:
    """Ground footprint of the detection pixel — required for the area retrieval."""
    scan = scan_km if scan_km and scan_km > 0 else fallback_km
    track = track_km if track_km and track_km > 0 else fallback_km
    return float(scan * track * 1_000_000.0)


def _risk_score(frp: float, bright_mir: Optional[float], confidence: Optional[float]) -> float:
    """Cheap triage ranking used only to order anomalies for processing."""
    frp_component = min(frp / 200.0, 1.0) * 55.0
    bright_component = 0.0
    if bright_mir:
        bright_component = min(max((bright_mir - 300.0) / 120.0, 0.0), 1.0) * 30.0
    confidence_component = (confidence if confidence is not None else 0.6) * 15.0
    return round(frp_component + bright_component + confidence_component, 2)


# ---------------------------------------------------------------------------
# LEO — NASA FIRMS
# ---------------------------------------------------------------------------
def _row_to_hotspot(row: Dict[str, Any]) -> Optional[Hotspot]:
    lat = _safe_float(row.get("latitude", row.get("lat")))
    lng = _safe_float(row.get("longitude", row.get("lon", row.get("lng"))))
    if lat is None or lng is None or (lat == 0.0 and lng == 0.0):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None

    sensor = str(row.get("sensor_source", row.get("satellite", "UNKNOWN"))).strip()
    mir_um, tir_um, nominal_km = _SENSOR_BANDS.get(sensor, _DEFAULT_BANDS)

    # VIIRS reports I4/I5; MODIS reports brightness (b21) and bright_t31 (b31).
    bright_mir = _safe_float(
        row.get("bright_ti4", row.get("brightness", row.get("bright_t21")))
    )
    bright_tir = _safe_float(row.get("bright_ti5", row.get("bright_t31")))
    frp = _safe_float(row.get("frp"), 0.0) or 0.0
    confidence = _parse_confidence(row.get("confidence"))
    scan_km = _safe_float(row.get("scan"))
    track_km = _safe_float(row.get("track"))

    return Hotspot(
        lat=round(lat, 6),
        lng=round(lng, 6),
        acq_datetime=_parse_acq_datetime(row.get("acq_date"), row.get("acq_time")),
        sensor=sensor,
        platform="LEO",
        bright_mir_k=bright_mir,
        bright_tir_k=bright_tir,
        frp_mw=round(frp, 3),
        confidence=confidence,
        daynight=str(row.get("daynight", "D"))[:1].upper() or "D",
        scan_km=scan_km,
        track_km=track_km,
        pixel_area_m2=_pixel_area_m2(scan_km, track_km, nominal_km),
        mir_wavelength_um=mir_um,
        tir_wavelength_um=tir_um,
        risk_score=_risk_score(frp, bright_mir, confidence),
        raw={
            k: v
            for k, v in row.items()
            if k in {"acq_date", "acq_time", "version", "type", "satellite", "instrument"}
        },
    )


def fetch_firms_data(
    days: Optional[int] = None,
    sensor: str = "ALL",
    bbox: Optional[str] = None,
) -> List[Hotspot]:
    """
    Fetch and normalise LEO thermal detections from NASA FIRMS.

    Delegates the HTTP work to the existing ``firms_fetcher`` so the repository
    keeps one FIRMS client, then normalises every sensor's differing column
    names into the shared :class:`Hotspot` contract.
    """
    day_range = days if days is not None else settings.ingestion.firms_day_range

    with stage_span(log, _STAGE, "firms_fetch") as span:
        span["days"] = day_range
        span["sensor"] = sensor

        try:
            from ingestion.firms_fetcher import fetch_firms_hotspots

            frame = fetch_firms_hotspots(day_range=day_range, sensor_choice=sensor)
        except Exception as exc:  # network, parsing, or missing key
            span["outcome"] = "error"
            span["error"] = str(exc)[:200]
            log.warning("FIRMS fetch failed, returning empty LEO set", extra={"stage": _STAGE})
            return []

        if frame is None or getattr(frame, "empty", True):
            span["outcome"] = "empty"
            span["count"] = 0
            return []

        hotspots: List[Hotspot] = []
        for record in frame.to_dict(orient="records"):
            hotspot = _row_to_hotspot(record)
            if hotspot is not None:
                hotspots.append(hotspot)

        # Deduplicate: the same fire seen by NOAA-20 and S-NPP within the same
        # hour is one event, not two.
        hotspots = _deduplicate(hotspots)
        hotspots.sort(key=lambda h: h.risk_score, reverse=True)

        span["count"] = len(hotspots)
        span["max_frp"] = max((h.frp_mw for h in hotspots), default=0.0)
        return hotspots


def _deduplicate(hotspots: Sequence[Hotspot], precision: int = 3) -> List[Hotspot]:
    """Collapse detections that share a ~100 m cell and an acquisition hour."""
    best: Dict[Tuple[float, float, str], Hotspot] = {}
    for hotspot in hotspots:
        hour = (hotspot.acq_datetime or "")[:13]
        key = (round(hotspot.lat, precision), round(hotspot.lng, precision), hour)
        incumbent = best.get(key)
        if incumbent is None or hotspot.frp_mw > incumbent.frp_mw:
            best[key] = hotspot
    return list(best.values())


# ---------------------------------------------------------------------------
# GEO — INSAT-3D / 3DR / 3DS
# ---------------------------------------------------------------------------
def _insat_cache_path(bbox: str, hours: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    safe_bbox = bbox.replace(",", "_").replace(".", "p")
    return os.path.join(
        settings.paths.insat_cache, f"insat_{safe_bbox}_{hours}h_{stamp}.json"
    )


def _load_insat_cache(bbox: str, hours: int) -> Optional[InsatCube]:
    """Return the newest cached cube that is still inside its TTL."""
    directory = settings.paths.insat_cache
    if not os.path.isdir(directory):
        return None
    candidates = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.startswith("insat_") and name.endswith(".json")
    ]
    if not candidates:
        return None
    newest = max(candidates, key=os.path.getmtime)
    age = time.time() - os.path.getmtime(newest)
    if age > settings.ingestion.cache_ttl_s:
        return None
    try:
        with open(newest, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        cube = InsatCube(
            satellites=payload.get("satellites", []),
            frames=payload.get("frames", []),
            start_time=payload.get("start_time"),
            end_time=payload.get("end_time"),
            revisit_minutes=payload.get("revisit_minutes", 30),
            spatial_resolution_km=payload.get("spatial_resolution_km", 4.0),
            source="cache",
            status=StageStatus(payload.get("status", StageStatus.OK.value)),
            notes=f"loaded from cache ({age / 60:.0f} min old)",
        )
        return cube
    except Exception:
        return None


def _store_insat_cache(cube: InsatCube, bbox: str, hours: int) -> None:
    try:
        path = _insat_cache_path(bbox, hours)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cube.to_dict(), handle)
    except Exception:
        pass  # caching is best-effort and must never break ingestion


def _fetch_insat_live(bbox: str, hours: int) -> Optional[InsatCube]:
    """
    Pull MIR/TIR frames from a MOSDAC-compatible endpoint.

    MOSDAC serves INSAT-3D/3DR/3DS imager products behind per-user credentials.
    Set ``MOSDAC_TOKEN`` (and optionally ``FIREOPS_INSAT_URL`` for an internal
    mirror or a pre-processed product feed) to enable the live path.
    """
    if not settings.ingestion.insat_token:
        return None

    try:
        import requests
    except ImportError:
        return None

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    params = {
        "bbox": bbox,
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "products": "IMG_MIR,IMG_TIR1",
        "interval": settings.ingestion.insat_revisit_minutes,
    }
    headers = {
        "Authorization": f"Bearer {settings.ingestion.insat_token}",
        "Accept": "application/json",
        "User-Agent": "FireOps-SIH2026/4.0",
    }

    try:
        response = requests.get(
            f"{settings.ingestion.insat_base_url.rstrip('/')}/insat/timeseries",
            params=params,
            headers=headers,
            timeout=settings.ingestion.http_timeout_s,
        )
        if response.status_code != 200:
            log.warning(
                "INSAT endpoint returned HTTP %s", response.status_code,
                extra={"stage": _STAGE},
            )
            return None
        payload = response.json()
    except Exception as exc:
        log.warning("INSAT live fetch failed: %s", str(exc)[:160], extra={"stage": _STAGE})
        return None

    frames = _normalise_insat_frames(payload)
    if not frames:
        return None

    return InsatCube(
        satellites=sorted({f.get("satellite", "INSAT-3D") for f in frames}),
        frames=frames,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        revisit_minutes=settings.ingestion.insat_revisit_minutes,
        spatial_resolution_km=settings.ingestion.insat_spatial_res_km,
        source="live",
        status=StageStatus.OK,
        notes="MOSDAC live imager feed",
    )


def _normalise_insat_frames(payload: Any) -> List[Dict[str, Any]]:
    """Accept the common shapes a MOSDAC-style feed may return."""
    if isinstance(payload, dict):
        raw_frames = payload.get("frames") or payload.get("data") or payload.get("items") or []
    elif isinstance(payload, list):
        raw_frames = payload
    else:
        return []

    frames: List[Dict[str, Any]] = []
    for raw in raw_frames:
        if not isinstance(raw, dict):
            continue
        samples = []
        for sample in raw.get("samples", raw.get("pixels", [])) or []:
            lat = _safe_float(sample.get("lat", sample.get("latitude")))
            lng = _safe_float(sample.get("lng", sample.get("lon", sample.get("longitude"))))
            if lat is None or lng is None:
                continue
            samples.append(
                {
                    "lat": lat,
                    "lng": lng,
                    "bright_mir_k": _safe_float(sample.get("mir", sample.get("bright_mir_k"))),
                    "bright_tir_k": _safe_float(sample.get("tir", sample.get("bright_tir_k"))),
                    "frp_mw": _safe_float(sample.get("frp", sample.get("frp_mw")), 0.0),
                }
            )
        if not samples:
            continue
        frames.append(
            {
                "timestamp": raw.get("timestamp", raw.get("time", raw.get("acq_time"))),
                "satellite": raw.get("satellite", raw.get("platform", "INSAT-3D")),
                "samples": samples,
            }
        )
    frames.sort(key=lambda f: str(f.get("timestamp") or ""))
    return frames


def _synthesise_insat_cube(
    anchors: Sequence[Hotspot], bbox: str, hours: int
) -> InsatCube:
    """
    Build a GEO-cadence cube around known LEO detections when MOSDAC is not
    reachable.

    This is **reconstruction, not observation**. Each LEO detection is expanded
    into a 30-minute sampled series whose shape follows the radiative decay of
    the observed FRP, with a diurnal component. The cube is stamped
    ``source="synthetic"`` and ``status=FALLBACK`` so Stage 5 marks its own
    output as degraded and Stage 6 caps the confidence it is willing to report.
    """
    if not anchors:
        return InsatCube(
            satellites=[],
            frames=[],
            revisit_minutes=settings.ingestion.insat_revisit_minutes,
            spatial_resolution_km=settings.ingestion.insat_spatial_res_km,
            source="unavailable",
            status=StageStatus.FAILED,
            notes="no INSAT credentials and no LEO anchors to reconstruct from",
        )

    rng = np.random.default_rng(settings.random_seed)
    step = timedelta(minutes=settings.ingestion.insat_revisit_minutes)
    frame_count = max(1, int((hours * 60) / settings.ingestion.insat_revisit_minutes))

    # Anchor the reconstruction window to the *data*, not to wall-clock time.
    # Running against an archived or cached FIRMS extract (a replay, an offline
    # demo, a backfill) would otherwise place every anchor weeks in the past,
    # decay it to zero, and yield an empty cube.
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    anchor_times = [_parse_iso(a.acq_datetime) for a in anchors]
    anchor_times = [t for t in anchor_times if t is not None]
    latest_anchor = max(anchor_times) if anchor_times else now
    # Half a window past the newest detection, so the series brackets it.
    end = min(now, latest_anchor + step * (frame_count // 2))
    start = end - step * frame_count

    # Limit reconstruction to the strongest anchors — a national cube of every
    # detection would be large and adds nothing for triage.
    top_anchors = sorted(anchors, key=lambda h: h.risk_score, reverse=True)[:40]

    frames: List[Dict[str, Any]] = []
    satellites = list(settings.ingestion.insat_satellites)

    for index in range(frame_count):
        stamp = start + step * index
        hour_of_day = stamp.hour + stamp.minute / 60.0
        samples: List[Dict[str, Any]] = []

        for anchor in top_anchors:
            observed_at = _parse_iso(anchor.acq_datetime) or end
            hours_since = abs((stamp - observed_at).total_seconds()) / 3600.0

            # Persistent sources hold their intensity; transient fires decay.
            # The e-folding time is inferred from the anomaly's own intensity.
            decay_scale = 18.0 if anchor.frp_mw > 40.0 else 6.0
            envelope = math.exp(-hours_since / decay_scale)

            # Industrial plants run a weak diurnal cycle; biomass burns peak in
            # the afternoon. Both are modelled, the classifier is not told which.
            diurnal = 1.0 + 0.18 * math.sin(2.0 * math.pi * (hour_of_day - 14.0) / 24.0)

            frp = anchor.frp_mw * envelope * diurnal
            noise = float(rng.normal(0.0, 0.05))
            frp = max(0.0, frp * (1.0 + noise))
            if frp < 0.5:
                continue

            base_mir = anchor.bright_mir_k or 320.0
            samples.append(
                {
                    "lat": anchor.lat,
                    "lng": anchor.lng,
                    "bright_mir_k": round(
                        295.0 + (base_mir - 295.0) * envelope * diurnal, 2
                    ),
                    "bright_tir_k": round(
                        290.0 + ((anchor.bright_tir_k or 300.0) - 290.0) * envelope, 2
                    ),
                    "frp_mw": round(frp, 3),
                }
            )

        if samples:
            frames.append(
                {
                    "timestamp": stamp.isoformat(),
                    "satellite": satellites[index % len(satellites)],
                    "samples": samples,
                }
            )

    return InsatCube(
        satellites=satellites,
        frames=frames,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        revisit_minutes=settings.ingestion.insat_revisit_minutes,
        spatial_resolution_km=settings.ingestion.insat_spatial_res_km,
        source="synthetic",
        status=StageStatus.FALLBACK,
        notes=(
            "RECONSTRUCTED from LEO anchors — MOSDAC token absent. "
            "Downstream temporal confidence is capped."
        ),
    )


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def fetch_insat_hypertemporal(
    bbox: Optional[str] = None,
    hours: Optional[int] = None,
    anchors: Optional[Sequence[Hotspot]] = None,
) -> InsatCube:
    """
    Fetch the hyper-temporal INSAT GEO stack.

    Resolution order: live MOSDAC -> on-disk cache -> reconstructed cube.
    The returned cube always carries a ``source`` and ``status`` describing
    which path was taken, and those flags reach the operator's screen.
    """
    area = bbox or settings.ingestion.firms_bbox
    lookback = hours if hours is not None else settings.ingestion.insat_lookback_hours

    with stage_span(log, _STAGE, "insat_fetch") as span:
        span["bbox"] = area
        span["lookback_h"] = lookback

        if not settings.ingestion.insat_enabled:
            span["outcome"] = "disabled"
            return InsatCube(
                revisit_minutes=settings.ingestion.insat_revisit_minutes,
                source="unavailable",
                status=StageStatus.SKIPPED,
                notes="INSAT ingestion disabled by configuration",
            )

        cube = _fetch_insat_live(area, lookback)
        if cube is not None and cube.frame_count:
            _store_insat_cache(cube, area, lookback)
            span["source"] = "live"
            span["frames"] = cube.frame_count
            return cube

        cached = _load_insat_cache(area, lookback)
        if cached is not None and cached.frame_count:
            span["source"] = "cache"
            span["frames"] = cached.frame_count
            return cached

        cube = _synthesise_insat_cube(anchors or [], area, lookback)
        span["source"] = cube.source
        span["frames"] = cube.frame_count
        span["outcome"] = "fallback"
        return cube


# ---------------------------------------------------------------------------
# LEO <-> GEO fusion
# ---------------------------------------------------------------------------
def fuse_leo_geo(
    hotspots: Sequence[Hotspot],
    cube: InsatCube,
    radius_km: Optional[float] = None,
) -> List[Hotspot]:
    """
    Attach each LEO detection's GEO time series to it.

    An INSAT pixel is ~4 km across, so a VIIRS detection is matched to the GEO
    cell that contains it. After this call every hotspot carries
    ``geo_series`` (the 30-minute samples) and ``geo_persistence_hours``
    (how long the source has been thermally active), which is the raw material
    for Stage 5.
    """
    search_radius = radius_km if radius_km is not None else settings.ingestion.fusion_radius_km

    with stage_span(log, _STAGE, "leo_geo_fusion") as span:
        span["leo_count"] = len(hotspots)
        span["geo_frames"] = cube.frame_count
        span["geo_source"] = cube.source

        matched = 0
        for hotspot in hotspots:
            series = cube.series_near(hotspot.lat, hotspot.lng, search_radius)
            if not series:
                continue
            matched += 1
            hotspot.geo_series = series
            hotspot.geo_observation_count = len(series)

            timestamps = [_parse_iso(s.get("timestamp")) for s in series]
            timestamps = [t for t in timestamps if t is not None]
            if len(timestamps) >= 2:
                span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600.0
                hotspot.geo_persistence_hours = round(span_hours, 2)

            # A GEO cell that repeatedly sees the source gives a better
            # background estimate than a single LEO pass.
            tir_values = [s.get("bright_tir_k") for s in series if s.get("bright_tir_k")]
            if tir_values:
                hotspot.background_temp_k = round(float(np.percentile(tir_values, 10)), 2)

        span["matched"] = matched
        return list(hotspots)


def load_multi_sensor_frame(
    days: Optional[int] = None,
    sensor: str = "ALL",
    bbox: Optional[str] = None,
) -> Tuple[List[Hotspot], InsatCube]:
    """
    One call that performs the whole of Stage 1.

    Returns the fused LEO hotspots and the GEO cube. The orchestrator uses
    this; the two lower-level functions stay public for testing and for the
    legacy call sites.
    """
    hotspots = fetch_firms_data(days=days, sensor=sensor, bbox=bbox)
    cube = fetch_insat_hypertemporal(bbox=bbox, anchors=hotspots)
    fused = fuse_leo_geo(hotspots, cube)

    log.info(
        "Stage 1 complete: %d LEO detections, %d GEO frames (%s)",
        len(fused),
        cube.frame_count,
        cube.source,
        extra={"stage": _STAGE, "fields": {"geo_status": cube.status.value}},
    )
    return fused, cube


__all__ = [
    "fetch_firms_data",
    "fetch_insat_hypertemporal",
    "fuse_leo_geo",
    "load_multi_sensor_frame",
]
