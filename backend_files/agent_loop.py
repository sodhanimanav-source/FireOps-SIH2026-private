"""
THE ORCHESTRATOR — Autonomous 6-Stage Monitoring Loop
======================================================

This module is a **traffic controller and nothing else**. It contains no
thermodynamics, no graph construction, no model inference and no decision
rules. Every scientific judgement lives in the stage module that owns it:

    Stage 1  ingestion.api_loader        LEO + GEO multi-sensor fusion
    Stage 2  ingestion.physics_filter    Planck inversion + the 1200 K gate
    Stage 3  models.gnn_topology         OSM directed graph + GraphSAGE
    Stage 4  models.prithvi_vision       Prithvi-EO-2.0 embeddings
    Stage 5  models.contiformer_time     ContiFormer / Neural ODE rhythm
    Stage 6  models.cross_modal_fusion   Cross-modal attention + decision

What this file *is* responsible for:

**Sequencing.** Stage 1 -> Stage 2 -> gate -> {3, 4, 5} in parallel -> Stage 6.

**The gate as a compute saving.** Stage 2 runs vectorised across the entire
national feed in one pass, and anomalies below 1200 K are closed out before
any encoder is touched. In stubble-burning season that discards the large
majority of detections for the cost of a few array operations.

**Parallel fan-out.** Stages 3, 4 and 5 are mutually independent — a graph
query, an image embedding and a time-series fit share no state — so they run
concurrently per anomaly under a wall-clock budget. A hung Overpass request
cannot stall the national loop.

**Failure isolation.** Every encoder is wrapped so that its failure produces a
``FAILED`` context rather than an exception. Stage 6 then reweights around the
missing modality, and if all three are gone it falls back to the legacy
classifier. One broken model degrades one signal, never the pipeline.

**Persistence.** Finished intelligence is written to the shared store, which
the API layer reads.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core import store
from core.config import settings
from core.logging_utils import (
    bind_cycle_id,
    current_cycle_id,
    get_logger,
    new_cycle_id,
    stage_span,
)
from core.schemas import (
    GraphContext,
    Hotspot,
    InsatCube,
    PipelineResult,
    PlanckSolution,
    SourceClass,
    StageStatus,
    TemporalContext,
    ThermalClass,
    VisionContext,
)

# --- Stage entry points (the only model imports in this file) --------------
from ingestion.api_loader import (
    fetch_firms_data,
    fetch_insat_hypertemporal,
    fuse_leo_geo,
)
from ingestion.physics_filter import (
    apply_thermal_gate,
    calculate_subpixel_temperature_batch,
)
from models.contiformer_time import run_contiformer
from models.cross_modal_fusion import cross_modal_attention
from models.gnn_topology import extract_osm_graph
from models.prithvi_vision import run_prithvi_eo

log = get_logger("orchestrator")

_STAGE = 0

# --- Shared runtime state, read by the API layer ---------------------------
monitored_events: Dict[str, str] = {}
pending_hitl_alerts: List[Dict[str, Any]] = []
_STATE_LOCK = threading.Lock()

agent_status: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "last_cycle_at": None,
    "cycles_completed": 0,
    "last_error": None,
    "last_cycle_stats": {},
}

_STOP_EVENT = threading.Event()


# ---------------------------------------------------------------------------
# Parallel encoder fan-out (Stages 3, 4, 5)
# ---------------------------------------------------------------------------
def _run_encoders_parallel(
    hotspot: Hotspot,
    cube: Optional[InsatCube],
    cycle_id: Optional[str],
) -> Tuple[GraphContext, VisionContext, TemporalContext, Dict[str, float]]:
    """
    Execute the three independent encoders concurrently.

    Each task is individually guarded and individually timed out. A task that
    raises or overruns returns a ``FAILED`` context carrying the reason, which
    Stage 6 treats as a missing modality rather than as a fatal error.
    """
    event_id = hotspot.event_id
    timings: Dict[str, float] = {}

    def guarded(name: str, func, fallback_factory):
        def task():
            # Thread-locals do not inherit, so the correlation id is rebound
            # inside each worker or its logs would be orphaned.
            bind_cycle_id(cycle_id)
            started = time.perf_counter()
            try:
                result = func()
            except Exception as exc:
                timings[name] = (time.perf_counter() - started) * 1000.0
                log.warning(
                    "Stage encoder '%s' raised: %s",
                    name,
                    str(exc)[:160],
                    extra={"stage": _STAGE, "event_id": event_id},
                )
                return fallback_factory(f"{type(exc).__name__}: {str(exc)[:140]}")
            timings[name] = (time.perf_counter() - started) * 1000.0
            return result

        return task

    graph_task = guarded(
        "graph",
        lambda: extract_osm_graph(hotspot.lat, hotspot.lng, event_id=event_id),
        lambda reason: GraphContext(
            embedding=[0.0] * settings.graph.embedding_dim,
            encoder="none",
            status=StageStatus.FAILED,
            notes=reason,
        ),
    )
    vision_task = guarded(
        "vision",
        lambda: run_prithvi_eo(
            hotspot.imagery_data, lat=hotspot.lat, lng=hotspot.lng, event_id=event_id
        ),
        lambda reason: VisionContext(
            embedding=[0.0] * settings.vision.embedding_dim,
            encoder="none",
            status=StageStatus.FAILED,
            notes=reason,
        ),
    )
    temporal_task = guarded(
        "time",
        lambda: run_contiformer(
            hotspot.lat,
            hotspot.lng,
            cube=cube,
            extra_series=hotspot.geo_series or None,
            event_id=event_id,
        ),
        lambda reason: TemporalContext(
            embedding=[0.0] * settings.temporal.latent_dim,
            encoder="none",
            status=StageStatus.FAILED,
            notes=reason,
        ),
    )

    with ThreadPoolExecutor(
        max_workers=settings.agent.stage_workers, thread_name_prefix="fireops-stage"
    ) as pool:
        futures = {
            "graph": pool.submit(graph_task),
            "vision": pool.submit(vision_task),
            "time": pool.submit(temporal_task),
        }

        results: Dict[str, Any] = {}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=settings.agent.stage_timeout_s)
            except FutureTimeout:
                log.warning(
                    "Stage encoder '%s' exceeded its %.0fs budget",
                    name,
                    settings.agent.stage_timeout_s,
                    extra={"stage": _STAGE, "event_id": event_id},
                )
                results[name] = None
            except Exception as exc:
                log.warning(
                    "Stage encoder '%s' failed: %s",
                    name,
                    str(exc)[:160],
                    extra={"stage": _STAGE, "event_id": event_id},
                )
                results[name] = None

    graph = results.get("graph") or GraphContext(
        embedding=[0.0] * settings.graph.embedding_dim,
        encoder="none",
        status=StageStatus.FAILED,
        notes="encoder timed out",
    )
    vision = results.get("vision") or VisionContext(
        embedding=[0.0] * settings.vision.embedding_dim,
        encoder="none",
        status=StageStatus.FAILED,
        notes="encoder timed out",
    )
    temporal = results.get("time") or TemporalContext(
        embedding=[0.0] * settings.temporal.latent_dim,
        encoder="none",
        status=StageStatus.FAILED,
        notes="encoder timed out",
    )

    return graph, vision, temporal, timings


# ---------------------------------------------------------------------------
# Single-anomaly pipeline
# ---------------------------------------------------------------------------
def process_anomaly(
    hotspot: Hotspot,
    solution: PlanckSolution,
    cube: Optional[InsatCube] = None,
    cycle_id: Optional[str] = None,
) -> PipelineResult:
    """
    Run Stages 3-6 for one anomaly that has already cleared the thermal gate.

    Stage 2 has run before this point; its solution is passed in so the
    expensive vectorised retrieval is done once per batch, not once per event.
    """
    event_id = hotspot.event_id
    result = PipelineResult(
        event_id=event_id,
        lat=hotspot.lat,
        lng=hotspot.lng,
        hotspot=hotspot.to_dict(),
        physics=solution.to_dict(),
        cycle_id=cycle_id,
    )

    graph, vision, temporal, timings = _run_encoders_parallel(hotspot, cube, cycle_id)

    fusion = cross_modal_attention(
        temp=solution.subpixel_temp_k,
        graph_data=graph,
        vision_data=vision,
        time_data=temporal,
        physics=solution,
        lat=hotspot.lat,
        lng=hotspot.lng,
        frp_mw=hotspot.frp_mw,
        event_id=event_id,
    )

    result.graph = graph.to_dict()
    result.vision = vision.to_dict()
    result.temporal = temporal.to_dict()
    result.fusion = fusion.to_dict()
    result.stage_timings_ms = {k: round(v, 1) for k, v in timings.items()}
    result.stage_status = {
        "physics": solution.status.value,
        "graph": graph.status.value,
        "vision": vision.status.value,
        "temporal": temporal.status.value,
        "fusion": fusion.status.value,
    }
    return result


def _muted_result(
    hotspot: Hotspot, solution: PlanckSolution, cycle_id: Optional[str]
) -> PipelineResult:
    """
    Close out an anomaly that the Stage 2 gate identified as biomass.

    The record is still written — muting is a classification, not a deletion,
    and an operator must be able to see and challenge it.
    """
    from core.schemas import HUMAN_LABELS, SEVERITY_BY_CLASS

    predicted = SourceClass.AGRICULTURAL_BURNING.value
    if hotspot.frp_mw > 60.0:
        predicted = SourceClass.WILDFIRE.value

    return PipelineResult(
        event_id=hotspot.event_id,
        lat=hotspot.lat,
        lng=hotspot.lng,
        hotspot=hotspot.to_dict(),
        physics=solution.to_dict(),
        gated_at_stage=2,
        cycle_id=cycle_id,
        fusion={
            "classification": predicted,
            "label": HUMAN_LABELS.get(predicted, predicted),
            "severity": SEVERITY_BY_CLASS.get(predicted, "MEDIUM"),
            "confidence": round(
                min(0.97, 0.80 + 0.17 * (1.0 - solution.subpixel_temp_k / max(1.0, solution.gate_threshold_k))),
                4,
            ),
            "thermal_gate_multiplier": 0.0,
            "attention_weights": {},
            "class_probabilities": {predicted: 1.0},
            "osm_linked_node": "None",
            "requires_hitl": False,
            "evidence": [
                f"Sub-pixel retrieval gives {solution.subpixel_temp_k:.0f} K, below the "
                f"{solution.gate_threshold_k:.0f} K industrial combustion threshold.",
                "Consistent with vegetation fuel; muted at Stage 2 without invoking "
                "the AI encoders.",
            ],
            "degraded_stages": [],
            "encoder": "thermal_gate",
            "status": StageStatus.OK.value,
            "notes": "muted by the Stage 2 physics gate",
        },
        stage_status={
            "physics": solution.status.value,
            "graph": StageStatus.SKIPPED.value,
            "vision": StageStatus.SKIPPED.value,
            "temporal": StageStatus.SKIPPED.value,
            "fusion": StageStatus.SKIPPED.value,
        },
    )


# ---------------------------------------------------------------------------
# One full monitoring cycle
# ---------------------------------------------------------------------------
def run_cycle(
    days: Optional[int] = None,
    sensor: str = "ALL",
    max_events: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute one complete pass of the six-stage pipeline.

    Returns a statistics dictionary. Safe to call directly — the HTTP layer
    uses it to trigger an on-demand analysis run.
    """
    cycle_id = new_cycle_id()
    store.start_cycle(cycle_id)
    started = time.perf_counter()
    limit = max_events if max_events is not None else settings.agent.max_events_per_cycle

    stats: Dict[str, Any] = {
        "cycle_id": cycle_id,
        "leo_detections": 0,
        "geo_frames": 0,
        "geo_source": "none",
        "gated_biomass": 0,
        "processed": 0,
        "errors": 0,
    }

    with stage_span(log, _STAGE, "monitoring_cycle") as span:
        # --- STAGE 1: hybrid ingestion --------------------------------------
        hotspots = fetch_firms_data(days=days, sensor=sensor)
        cube = fetch_insat_hypertemporal(anchors=hotspots)
        hotspots = fuse_leo_geo(hotspots, cube)

        stats["leo_detections"] = len(hotspots)
        stats["geo_frames"] = cube.frame_count
        stats["geo_source"] = cube.source

        if not hotspots:
            log.info("No detections in this cycle", extra={"stage": _STAGE})
            span["outcome"] = "empty"
            stats["duration_ms"] = (time.perf_counter() - started) * 1000.0
            store.finish_cycle(
                cycle_id, **{k: v for k, v in stats.items() if k != "cycle_id"}
            )
            return stats

        # --- STAGE 2: vectorised physics over the whole batch ---------------
        # One array pass for the entire national feed, before any per-event
        # work is considered.
        solutions = calculate_subpixel_temperature_batch(hotspots)
        candidates, muted = apply_thermal_gate(hotspots, solutions)
        stats["gated_biomass"] = len(muted)

        # Muted anomalies are recorded and closed out here — this is where the
        # architecture's compute saving is realised.
        for hotspot, solution in muted:
            result = _muted_result(hotspot, solution, cycle_id)
            store.save_result(result)
            with _STATE_LOCK:
                monitored_events[hotspot.event_id] = "MUTED_BIOMASS"

        # --- Triage: only the strongest candidates get the AI treatment -----
        already_seen = store.recently_processed_ids(settings.agent.reprocess_after_s)
        fresh: List[Tuple[Hotspot, PlanckSolution]] = []
        # Event ids are quantised to ~1 km, so several raw detections can map
        # to a single event. Collapse them here rather than running the full
        # encoder stack repeatedly on the same physical site.
        seen_this_cycle: set = set()
        for hotspot, solution in candidates:
            event_id = hotspot.event_id
            if event_id in already_seen or event_id in seen_this_cycle:
                continue
            seen_this_cycle.add(event_id)
            fresh.append((hotspot, solution))

        # Triage order matters as much as the gate itself. Ranking by
        # risk_score alone is ranking by FRP and brightness — precisely the
        # reasoning this architecture exists to replace. In practice that
        # buries the anomalies that actually cleared the 1200 K gate beneath a
        # crowd of unretrievable ones, so a capped cycle spends its entire
        # budget on anomalies whose physics is unknown and never reaches the
        # confirmed industrial candidates.
        #
        # Order instead by what Stage 2 established:
        #   1. anomalies that cleared the gate  (confirmed industrial heat)
        #   2. among those, the hottest first   (most energetic combustion)
        #   3. then the rest by triage score    (indeterminate, still worth a look)
        fresh.sort(
            key=lambda pair: (
                1 if pair[1].passed_gate else 0,
                pair[1].subpixel_temp_k,
                pair[0].risk_score,
            ),
            reverse=True,
        )
        selected = fresh[:limit]

        gate_passers = sum(1 for _, solution in selected if solution.passed_gate)
        span["selected_gate_passers"] = gate_passers

        span["leo"] = len(hotspots)
        span["muted"] = len(muted)
        span["candidates"] = len(candidates)
        span["selected"] = len(selected)

        log.info(
            "Gate passed %d of %d detections; processing %d (%d already analysed recently)",
            len(candidates),
            len(hotspots),
            len(selected),
            len(candidates) - len(fresh),
            extra={"stage": _STAGE},
        )

        # --- STAGES 3-6 per anomaly ----------------------------------------
        for hotspot, solution in selected:
            try:
                result = process_anomaly(hotspot, solution, cube, cycle_id)
                store.save_result(result)
                _update_runtime_state(result)
                stats["processed"] += 1
            except Exception as exc:
                stats["errors"] += 1
                log.exception(
                    "Anomaly %s failed: %s",
                    hotspot.event_id,
                    str(exc)[:160],
                    extra={"stage": _STAGE, "event_id": hotspot.event_id},
                )

        stats["duration_ms"] = (time.perf_counter() - started) * 1000.0
        store.finish_cycle(cycle_id, **{k: v for k, v in stats.items() if k != "cycle_id"})

        span["processed"] = stats["processed"]
        span["errors"] = stats["errors"]
        return stats


def _update_runtime_state(result: PipelineResult) -> None:
    """Mirror the decision into the in-memory state the API serves."""
    fusion = result.fusion or {}
    requires_hitl = bool(fusion.get("requires_hitl", True))

    with _STATE_LOCK:
        if requires_hitl:
            monitored_events[result.event_id] = "UNDER_REVIEW"
            if not any(a.get("id") == result.event_id for a in pending_hitl_alerts):
                pending_hitl_alerts.append(
                    {
                        "id": result.event_id,
                        "hotspot": result.hotspot,
                        "sub_pixel_temp": result.sub_pixel_temp,
                        "ai_results": fusion,
                        "intelligence": result.intelligence_properties(),
                        "status": "UNDER_REVIEW",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
        else:
            monitored_events[result.event_id] = f"AUTO_{fusion.get('severity', 'LOW')}"

    log.info(
        "%s -> %s (conf %.2f, %.0f K, %s)",
        result.event_id,
        result.classification,
        result.ai_confidence,
        result.sub_pixel_temp or 0.0,
        "OPERATOR REVIEW" if requires_hitl else "auto-approved",
        extra={"stage": _STAGE, "event_id": result.event_id},
    )


# ---------------------------------------------------------------------------
# Autonomous loop
# ---------------------------------------------------------------------------
def autonomous_loop() -> None:
    """Poll continuously until :func:`stop_agent` is called."""
    agent_status["running"] = True
    agent_status["started_at"] = datetime.now(timezone.utc).isoformat()

    log.info(
        "Multi-modal geospatial monitoring loop started (interval %ss)",
        settings.agent.poll_interval_s,
        extra={"stage": _STAGE},
    )

    while not _STOP_EVENT.is_set():
        try:
            stats = run_cycle()
            agent_status["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
            agent_status["cycles_completed"] += 1
            agent_status["last_cycle_stats"] = stats
            agent_status["last_error"] = None
            _STOP_EVENT.wait(settings.agent.poll_interval_s)
        except Exception as exc:
            agent_status["last_error"] = str(exc)[:300]
            log.exception("Cycle failed; backing off", extra={"stage": _STAGE})
            _STOP_EVENT.wait(settings.agent.error_backoff_s)

    agent_status["running"] = False
    log.info("Monitoring loop stopped", extra={"stage": _STAGE})


def start_agent() -> Optional[threading.Thread]:
    """Start the loop on a daemon thread. Returns the thread, or None if disabled."""
    if not settings.agent.enabled:
        log.info("Agent disabled by configuration", extra={"stage": _STAGE})
        return None
    if agent_status["running"]:
        log.info("Agent already running", extra={"stage": _STAGE})
        return None

    _STOP_EVENT.clear()
    thread = threading.Thread(target=autonomous_loop, daemon=True, name="fireops-agent")
    thread.start()
    return thread


def stop_agent() -> None:
    """Signal the loop to finish its current cycle and exit."""
    _STOP_EVENT.set()


def get_agent_status() -> Dict[str, Any]:
    with _STATE_LOCK:
        pending = len(pending_hitl_alerts)
        tracked = len(monitored_events)
    return {
        **agent_status,
        "pending_hitl": pending,
        "tracked_events": tracked,
        "poll_interval_s": settings.agent.poll_interval_s,
        "gate_threshold_k": settings.physics.industrial_temperature_gate_k,
    }


if __name__ == "__main__":  # pragma: no cover
    # Run a single cycle for manual inspection.
    import json

    print(json.dumps(run_cycle(), indent=2, default=str))
