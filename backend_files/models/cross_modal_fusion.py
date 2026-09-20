"""
STAGE 6 — Cross-Modal Attention and Decision
=============================================

The four preceding stages each answer a different question about an anomaly:

    Stage 2  physics    how hot is the actual combustion?
    Stage 3  topology   is it wired into an industrial process system?
    Stage 4  vision     is the ground permanent infrastructure or a burn scar?
    Stage 5  time       does it follow an operational rhythm?

Fusing them by averaging would be wrong, because the modalities are not
equally trustworthy in every situation — and which one to trust is itself
decided by the physics.

The gating principle
--------------------
Sub-pixel temperature is the one measurement that is model-free: it comes from
inverting Planck's law on calibrated radiances, not from a learned prior. So
it is used as the **attention gate**.

    g = σ( (T_subpixel - 1200 K) / 120 K )

* ``g → 1`` (combustion above the industrial threshold): attention is forced
  onto the **topological graph and the temporal rhythm**. Those are the
  modalities that distinguish a routine flare from an accident, and they are
  only meaningful once the physics has already established that this is
  industrial combustion.
* ``g → 0`` (below the threshold): attention shifts to **vision**, which is
  what separates a crop fire from a forest fire, and the graph and rhythm
  evidence is suppressed — a hot-looking pixel next to a refinery is not a
  refinery fire if it is only burning at 800 K.

This is the concrete meaning of "the temperature acts as a high-attention
gating multiplier": it does not merely add a feature, it re-weights which
evidence the decision is allowed to rest on.

Confidence discipline
---------------------
Confidence is derived from the *margin* between the leading class and its
runner-up, then explicitly penalised for every encoder that fell back or
failed. A pipeline running on reconstructed temporal data and a facilities-file
graph cannot report the same certainty as one running on live INSAT frames and
a full OSM extract, and is capped below the human-review threshold so that a
degraded verdict always reaches an operator.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.config import settings
from core.logging_utils import get_logger, stage_span
from core.schemas import (
    HUMAN_LABELS,
    SEVERITY_BY_CLASS,
    FusionDecision,
    GraphContext,
    PlanckSolution,
    SourceClass,
    StageStatus,
    TemporalContext,
    ThermalClass,
    VisionContext,
)

log = get_logger("stage6.fusion")

_STAGE = 6
_CFG = settings.fusion

_MODALITIES = ("graph", "vision", "time")


# ---------------------------------------------------------------------------
# Attention
# ---------------------------------------------------------------------------
def _gate_multiplier(temperature_k: float) -> float:
    """Smooth industrial-combustion gate, shared with Stage 2."""
    from ingestion.physics_filter import thermal_gate_multiplier

    return thermal_gate_multiplier(temperature_k)


def _modality_availability(
    graph: Optional[GraphContext],
    vision: Optional[VisionContext],
    temporal: Optional[TemporalContext],
) -> Dict[str, float]:
    """
    How much each modality is worth right now, in [0, 1].

    A failed encoder contributes nothing; a fallback encoder contributes at
    reduced weight rather than being discarded, because a degraded signal is
    still better than no signal.
    """
    weights = {"graph": 0.0, "vision": 0.0, "time": 0.0}
    for name, context in (("graph", graph), ("vision", vision), ("time", temporal)):
        if context is None:
            continue
        status = getattr(context, "status", StageStatus.FAILED)
        if status is StageStatus.OK:
            weights[name] = 1.0
        elif status is StageStatus.FALLBACK:
            weights[name] = 0.6
        elif status is StageStatus.SKIPPED:
            weights[name] = 0.15
        else:  # FAILED
            weights[name] = 0.0
    return weights


def cross_modal_attention_weights(
    gate: float,
    availability: Dict[str, float],
    graph: Optional[GraphContext],
    vision: Optional[VisionContext],
    temporal: Optional[TemporalContext],
) -> Dict[str, float]:
    """
    Compute the attention distribution over the three AI modalities.

    The query is built from the thermal state; the keys are the modality
    embeddings. On top of the usual scaled dot-product term, an explicit gate
    bias implements the architecture's central rule: above the combustion
    threshold, look at structure and rhythm; below it, look at the ground.
    """
    dimension = _CFG.embedding_dim

    def key_of(context: Any) -> np.ndarray:
        embedding = np.asarray(getattr(context, "embedding", []) or [], dtype=np.float64)
        if embedding.size == 0:
            return np.zeros(dimension)
        if embedding.size < dimension:
            embedding = np.pad(embedding, (0, dimension - embedding.size))
        return embedding[:dimension]

    keys = {
        "graph": key_of(graph),
        "vision": key_of(vision),
        "time": key_of(temporal),
    }

    # Thermal query: a deterministic projection of the gate state into the
    # shared embedding space, so the dot-product term is stable across runs.
    rng = np.random.default_rng(settings.random_seed + 6)
    query_basis = rng.normal(0.0, 1.0 / math.sqrt(dimension), size=(2, dimension))
    query = gate * query_basis[0] + (1.0 - gate) * query_basis[1]

    # Gate bias — the architectural rule, stated numerically.
    #   above the gate: graph and time dominate
    #   below the gate: vision dominates
    bias = {
        "graph": 2.2 * gate - 0.8 * (1.0 - gate),
        "time": 2.2 * gate - 0.8 * (1.0 - gate),
        "vision": 1.8 * (1.0 - gate) + 0.3 * gate,
    }

    logits: Dict[str, float] = {}
    for name in _MODALITIES:
        if availability[name] <= 0.0:
            logits[name] = -1e9  # masked out entirely
            continue
        dot = float(query @ keys[name]) / math.sqrt(dimension)
        logits[name] = dot + bias[name] + math.log(max(availability[name], 1e-6))

    maximum = max(logits.values())
    if maximum <= -1e8:  # every modality unavailable
        return {name: 0.0 for name in _MODALITIES}

    exponentials = {n: math.exp(min(60.0, logits[n] - maximum)) for n in _MODALITIES}
    total = sum(exponentials.values())
    if total <= 0.0:
        return {name: 0.0 for name in _MODALITIES}
    return {n: round(exponentials[n] / total, 4) for n in _MODALITIES}


# ---------------------------------------------------------------------------
# Per-modality evidence
# ---------------------------------------------------------------------------
def _graph_evidence(graph: Optional[GraphContext]) -> Dict[str, float]:
    if graph is None:
        return {"industrial": 0.0, "biomass": 0.0, "mine": 0.0}
    topology = float(graph.industrial_topology_score)
    mine = 0.0
    for node in (graph.nodes or [])[:10]:
        tags = " ".join(str(v).lower() for v in (node.tags or {}).values())
        if "quarry" in tags or "mine" in tags or "coal" in tags:
            mine = max(mine, 0.8)
    return {
        "industrial": topology,
        # Absence of industrial structure is weak evidence for biomass; open
        # land simply has nothing mapped on it.
        "biomass": float(np.clip(1.0 - topology * 1.6, 0.0, 1.0)) * 0.7,
        "mine": mine,
    }


def _vision_evidence(vision: Optional[VisionContext]) -> Dict[str, float]:
    if vision is None:
        return {"industrial": 0.0, "biomass": 0.0}
    return {
        "industrial": float(vision.permanent_structure_score),
        "biomass": float(vision.burn_scar_score),
    }


def _time_evidence(temporal: Optional[TemporalContext]) -> Dict[str, float]:
    if temporal is None:
        return {
            "industrial": 0.0,
            "biomass": 0.0,
            "routine": 0.0,
            "anomalous": 0.0,
            "persistence": 0.0,
            "periodicity": 0.0,
        }

    persistence = float(temporal.persistence_score)
    periodicity = float(temporal.periodicity_score)
    regularity = float(temporal.rhythm_regularity)
    burst = float(temporal.burst_score)

    # Industrial evidence: the source keeps burning, and/or it follows a cycle.
    industrial = float(np.clip(0.60 * persistence + 0.40 * periodicity, 0.0, 1.0))
    # Biomass evidence: short-lived and without any established rhythm.
    biomass = float(np.clip((1.0 - persistence) * (1.0 - periodicity), 0.0, 1.0))
    # Routine vs anomalous *within* an industrial site.
    routine = float(np.clip(0.5 * regularity + 0.5 * (1.0 - burst), 0.0, 1.0))
    anomalous = float(np.clip(burst * 0.7 + (1.0 - regularity) * 0.3, 0.0, 1.0))

    return {
        "industrial": industrial,
        "biomass": biomass,
        "routine": routine,
        "anomalous": anomalous,
        # Exposed raw so the class scorer can reason about whether an
        # established operating rhythm existed before the current excursion.
        "persistence": persistence,
        "periodicity": periodicity,
    }


# ---------------------------------------------------------------------------
# Class scoring
# ---------------------------------------------------------------------------
def _score_classes(
    gate: float,
    temperature_k: float,
    attention: Dict[str, float],
    graph_ev: Dict[str, float],
    vision_ev: Dict[str, float],
    time_ev: Dict[str, float],
    frp_mw: float,
) -> Dict[str, float]:
    """
    Attention-weighted score for every operational class.

    Each class is scored from the evidence that actually distinguishes it,
    with the modality weights supplied by the cross-modal attention.
    """
    w_graph = attention.get("graph", 0.0)
    w_vision = attention.get("vision", 0.0)
    w_time = attention.get("time", 0.0)

    # Aggregate industrial / biomass context under attention.
    industrial_context = (
        w_graph * graph_ev["industrial"]
        + w_vision * vision_ev["industrial"]
        + w_time * time_ev["industrial"]
    )
    biomass_context = (
        w_graph * graph_ev["biomass"]
        + w_vision * vision_ev["biomass"]
        + w_time * time_ev["biomass"]
    )

    routine = time_ev.get("routine", 0.0)
    anomalous = time_ev.get("anomalous", 0.0)
    mine = graph_ev.get("mine", 0.0)

    # Was this site operating on an established schedule *before* the current
    # excursion? This is what separates a flare spike from an accident: a
    # spike is a known process deviating from its own baseline, an accident is
    # combustion where no routine operation existed.
    established_rhythm = float(
        np.clip(0.6 * time_ev.get("periodicity", 0.0) + 0.4 * time_ev.get("persistence", 0.0), 0.0, 1.0)
    )

    # Temperature bands. Flares and furnaces run 1400-2200 K; a runaway
    # hydrocarbon fire in a process unit is hotter and much less regular.
    very_hot = float(np.clip((temperature_k - 1600.0) / 400.0, 0.0, 1.0))
    moderate = float(np.clip((temperature_k - 700.0) / 400.0, 0.0, 1.0))

    # Flaring requires hydrocarbon processing infrastructure. Where the
    # topology says mine or quarry, the flaring classes are suppressed —
    # a coal seam has nothing to flare.
    not_mine_flare = 1.0 - 0.70 * mine
    not_mine_spike = 1.0 - 0.50 * mine

    scores: Dict[str, float] = {}

    # --- Industrial family (gated on the physics) --------------------------
    scores[SourceClass.ROUTINE_FLARING.value] = (
        gate * industrial_context * (0.60 * routine + 0.40 * (1.0 - anomalous)) * not_mine_flare
    )
    # A spike is an excursion *on top of* an established rhythm.
    scores[SourceClass.FLARE_SPIKE.value] = (
        gate
        * industrial_context
        * (0.45 * anomalous + 0.40 * established_rhythm + 0.15 * very_hot)
        * not_mine_spike
    )
    # An accident is anomalous combustion *without* an established rhythm,
    # typically hotter and more powerful than routine operation.
    scores[SourceClass.INDUSTRIAL_ACCIDENT.value] = gate * industrial_context * (
        0.40 * anomalous
        + 0.35 * very_hot
        + 0.25 * (1.0 - established_rhythm) * float(np.clip(frp_mw / 120.0, 0.0, 1.0))
    )
    # Coal seam fires: hot and effectively permanent, but with no operational
    # rhythm, sitting on mining rather than processing infrastructure.
    scores[SourceClass.COAL_MINE_FIRE.value] = (
        gate
        * mine
        * (
            0.45 * time_ev["industrial"]
            + 0.30 * (1.0 - anomalous)
            + 0.25 * time_ev.get("persistence", 0.0)
        )
    )

    # --- Biomass family (active below the gate) ----------------------------
    below = 1.0 - gate
    scores[SourceClass.AGRICULTURAL_BURNING.value] = below * biomass_context * (
        0.65 + 0.35 * (1.0 - float(np.clip(frp_mw / 60.0, 0.0, 1.0)))
    )
    scores[SourceClass.WILDFIRE.value] = below * biomass_context * (
        0.35 + 0.65 * float(np.clip(frp_mw / 60.0, 0.0, 1.0))
    ) * (0.5 + 0.5 * moderate)

    # --- Residual ----------------------------------------------------------
    # Whatever evidence none of the above explains lands here, which is what
    # routes genuinely ambiguous anomalies to a human instead of forcing a
    # confident but unsupported label.
    explained = max(scores.values()) if scores else 0.0
    scores[SourceClass.UNCLASSIFIED.value] = float(np.clip(0.35 - explained, 0.02, 1.0))

    return scores


def _normalise(scores: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, v) for v in scores.values())
    if total <= 0.0:
        return {k: round(1.0 / len(scores), 4) for k in scores}
    return {k: round(max(0.0, v) / total, 4) for k, v in scores.items()}


# ---------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------
def _build_evidence(
    temperature_k: float,
    gate: float,
    physics: Optional[PlanckSolution],
    graph: Optional[GraphContext],
    vision: Optional[VisionContext],
    temporal: Optional[TemporalContext],
    attention: Dict[str, float],
) -> List[str]:
    """Human-readable justification, shown to the operator beside the verdict."""
    evidence: List[str] = []

    if physics is not None and physics.converged:
        evidence.append(
            f"Planck inversion ({physics.method}) retrieved a sub-pixel source at "
            f"{temperature_k:.0f} K filling {physics.fractional_area:.2e} of the pixel "
            f"({physics.fire_area_m2:.0f} m² of fire)."
        )
        if physics.frp_agreement is not None and physics.frp_agreement > 0.5:
            evidence.append(
                f"Retrieved FRP agrees with the reported value to "
                f"{physics.frp_agreement * 100:.0f}%, so the retrieval is self-consistent."
            )
        if temperature_k >= physics.gate_threshold_k:
            evidence.append(
                f"{temperature_k:.0f} K exceeds the {physics.gate_threshold_k:.0f} K "
                "industrial combustion threshold — too hot for biomass fuel."
            )
        else:
            evidence.append(
                f"{temperature_k:.0f} K is below the {physics.gate_threshold_k:.0f} K "
                "threshold, consistent with vegetation combustion."
            )
    else:
        evidence.append(
            "No physical two-band retrieval was possible (the sensor reported no "
            "usable thermal excess), so the industrial gate is held neutral and "
            "classification rests on the AI modalities alone — this anomaly is "
            "explicitly not treated as cold."
        )

    if graph is not None and graph.node_count:
        evidence.append(
            f"Topology: {graph.node_count} mapped objects "
            f"({graph.tank_count} tanks, {graph.flare_count} flares, "
            f"{graph.chimney_count} chimneys) connected by {graph.edge_count} directed "
            f"edges including {graph.pipeline_edges} pipelines — "
            f"industrial structure score {graph.industrial_topology_score:.2f}."
        )
        if graph.facility_name:
            evidence.append(f"Nearest identified facility: {graph.facility_name}.")

    if vision is not None and vision.encoder != "none":
        evidence.append(
            f"Vision ({vision.encoder}): permanent-structure {vision.permanent_structure_score:.2f}, "
            f"burn-scar {vision.burn_scar_score:.2f}."
        )

    if temporal is not None and temporal.event_count:
        detail = (
            f"Rhythm: {temporal.event_count} observations over "
            f"{temporal.observation_span_h:.0f} h, persistence "
            f"{temporal.persistence_score:.2f}"
        )
        if temporal.dominant_period_h:
            detail += (
                f", repeating every {temporal.dominant_period_h:.1f} h "
                f"(confidence {temporal.periodicity_score:.2f})"
            )
        else:
            detail += ", no statistically significant cycle"
        if temporal.status is not StageStatus.OK and temporal.notes:
            # The operator must see when a rhythm was reconstructed rather
            # than observed, or a synthetic period reads as a real finding.
            detail += f" [{temporal.notes}]"
        evidence.append(detail + ".")

    dominant = max(attention, key=attention.get) if attention else None
    if dominant and attention.get(dominant, 0.0) > 0.0:
        evidence.append(
            f"Thermal gate multiplier {gate:.2f} directed attention mainly to the "
            f"{dominant} modality ("
            + ", ".join(f"{k} {v:.2f}" for k, v in attention.items())
            + ")."
        )

    return evidence


# ---------------------------------------------------------------------------
# Legacy fallback
# ---------------------------------------------------------------------------
def _legacy_fallback(
    lat: Optional[float],
    lng: Optional[float],
    frp_mw: float,
    temperature_k: float,
) -> FusionDecision:
    """
    Simple proximity + intensity classifier, used when every AI modality is
    unavailable. Mirrors the repository's original rule-based logic so the
    system still answers rather than returning nothing.
    """
    near: Dict[str, Any] = {}
    try:
        if lat is not None and lng is not None:
            from models.intelligence.proximity import what_is_nearby

            near = what_is_nearby(lat, lng, radius_m=3500) or {}
    except Exception:
        near = {}

    facility = None
    if near.get("assets"):
        facility = near["assets"][0].get("name")

    if near.get("has_industry"):
        if near.get("has_mine"):
            predicted = SourceClass.COAL_MINE_FIRE.value
        elif near.get("has_refinery_or_oilgas") and frp_mw < 25.0:
            predicted = SourceClass.ROUTINE_FLARING.value
        elif near.get("has_refinery_or_oilgas"):
            predicted = SourceClass.FLARE_SPIKE.value
        else:
            predicted = SourceClass.INDUSTRIAL_ACCIDENT.value
    elif frp_mw > 60.0:
        predicted = SourceClass.WILDFIRE.value
    else:
        predicted = SourceClass.AGRICULTURAL_BURNING.value

    return FusionDecision(
        classification=predicted,
        label=HUMAN_LABELS.get(predicted, predicted),
        severity=SEVERITY_BY_CLASS.get(predicted, "MEDIUM"),
        # Deliberately below the HITL threshold: a proximity heuristic must
        # never auto-approve anything.
        confidence=0.45,
        thermal_gate_multiplier=_gate_multiplier(temperature_k),
        attention_weights={},
        class_probabilities={predicted: 0.45},
        osm_linked_node=facility or "None",
        requires_hitl=True,
        evidence=[
            "All AI modalities were unavailable; fell back to the legacy "
            "proximity and intensity classifier.",
            f"Nearest industrial asset: {facility or 'none within 3.5 km'}.",
        ],
        degraded_stages=["graph", "vision", "time"],
        encoder="legacy_rule_based",
        status=StageStatus.FALLBACK,
        notes="degraded mode — operator review required",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def cross_modal_attention(
    temp: Any = None,
    graph_data: Optional[GraphContext] = None,
    vision_data: Optional[VisionContext] = None,
    time_data: Optional[TemporalContext] = None,
    physics: Optional[PlanckSolution] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    frp_mw: float = 0.0,
    event_id: Optional[str] = None,
) -> FusionDecision:
    """
    Stage 6 entry point: fuse all modalities into an operational verdict.

    ``temp`` accepts either a temperature in Kelvin or a
    :class:`PlanckSolution`, so both the current and the earlier call
    convention work.
    """
    with stage_span(log, _STAGE, "cross_modal_fusion", event_id=event_id) as span:
        try:
            # --- Resolve the thermal input ----------------------------------
            if isinstance(temp, PlanckSolution):
                physics = physics or temp
                temperature_k = float(temp.subpixel_temp_k)
            elif temp is None:
                temperature_k = float(physics.subpixel_temp_k) if physics else 0.0
            else:
                temperature_k = float(temp)

            # A failed retrieval must not masquerade as a cold source. With
            # temperature 0 the logistic gate returns ~0, which would silently
            # force every unretrievable anomaly into the biomass family and
            # auto-mute it — the most dangerous possible failure mode for this
            # system, since a missing thermal band would hide a refinery fire.
            # An indeterminate physics result therefore yields a *neutral*
            # gate: neither family is favoured, both sets of evidence stay in
            # play, and the reduced evidence quality pushes the verdict to a
            # human.
            physics_indeterminate = (
                temperature_k <= 0.0 or (physics is not None and not physics.converged)
            )
            if physics_indeterminate:
                gate = 0.5
            else:
                gate = _gate_multiplier(temperature_k)

            span["temp_k"] = round(temperature_k, 1)
            span["gate"] = gate
            if physics_indeterminate:
                span["physics"] = "indeterminate"

            availability = _modality_availability(graph_data, vision_data, time_data)
            span["available"] = sum(1 for v in availability.values() if v > 0.0)

            # --- Total modality failure -------------------------------------
            if all(value <= 0.0 for value in availability.values()):
                span["outcome"] = "legacy_fallback"
                log.warning(
                    "All AI modalities unavailable — using legacy classifier",
                    extra={"stage": _STAGE, "event_id": event_id},
                )
                return _legacy_fallback(lat, lng, frp_mw, temperature_k)

            # --- Attention ---------------------------------------------------
            attention = cross_modal_attention_weights(
                gate, availability, graph_data, vision_data, time_data
            )

            graph_ev = _graph_evidence(graph_data)
            vision_ev = _vision_evidence(vision_data)
            time_ev = _time_evidence(time_data)

            raw_scores = _score_classes(
                gate, temperature_k, attention, graph_ev, vision_ev, time_ev, frp_mw
            )
            probabilities = _normalise(raw_scores)

            ranked = sorted(probabilities.items(), key=lambda kv: kv[1], reverse=True)
            classification, top_probability = ranked[0]
            runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

            # --- Confidence --------------------------------------------------
            # Confidence is built in two tiers, because the two decisions are
            # not equally important and not equally hard.
            #
            # The primary claim is the *family*: industrial combustion versus
            # biomass. That is the question the whole architecture exists to
            # answer, and it is what an operator acts on.
            #
            # The secondary claim is the specific class within that family.
            # Routine flaring and a flare spike are the same physical process
            # at different intensities, so they legitimately share probability
            # mass. Scoring confidence purely on the margin between them would
            # report a textbook-clear refinery flare as a coin toss, which is
            # both wrong and operationally useless.
            industrial_classes = {
                SourceClass.ROUTINE_FLARING.value,
                SourceClass.FLARE_SPIKE.value,
                SourceClass.INDUSTRIAL_ACCIDENT.value,
                SourceClass.COAL_MINE_FIRE.value,
            }
            biomass_classes = {
                SourceClass.AGRICULTURAL_BURNING.value,
                SourceClass.WILDFIRE.value,
            }

            if classification in industrial_classes:
                family = industrial_classes
            elif classification in biomass_classes:
                family = biomass_classes
            else:
                family = {classification}

            family_probability = sum(probabilities.get(c, 0.0) for c in family)
            within_family = (
                top_probability / family_probability if family_probability > 1e-9 else 0.0
            )

            # Evidence quality: a failed physics retrieval or a temperature
            # sitting right on the 1200 K threshold means the family decision
            # itself rests on weaker ground.
            gate_certainty = abs(gate - 0.5) * 2.0
            physics_quality = 1.0 if (physics is None or physics.converged) else 0.3
            evidence_quality = 0.5 * gate_certainty + 0.5 * physics_quality

            confidence = float(
                np.clip(
                    0.55 * family_probability
                    + 0.30 * within_family
                    + 0.15 * evidence_quality,
                    0.0,
                    1.0,
                )
            )

            # An unclassified verdict is an admission of ignorance and must
            # never carry a high score, whatever the arithmetic says.
            if classification == SourceClass.UNCLASSIFIED.value:
                confidence = min(confidence, 0.35)

            span["family_prob"] = round(family_probability, 4)
            span["within_family"] = round(within_family, 4)

            degraded = [
                name
                for name, context in (
                    ("graph", graph_data),
                    ("vision", vision_data),
                    ("time", time_data),
                )
                if context is not None
                and getattr(context, "status", StageStatus.FAILED) is not StageStatus.OK
            ]
            confidence -= _CFG.degraded_stage_penalty * len(degraded)
            confidence = float(np.clip(confidence, 0.0, 1.0))

            # A degraded pipeline is never allowed to auto-approve.
            if degraded:
                confidence = min(confidence, _CFG.max_confidence_degraded)

            requires_hitl = confidence < _CFG.hitl_confidence_threshold

            severity = SEVERITY_BY_CLASS.get(classification, "MEDIUM")
            label = HUMAN_LABELS.get(classification, classification)
            if graph_data is not None and graph_data.facility_name and gate > 0.5:
                label = f"{label} @ {graph_data.facility_name}"

            linked_node = "None"
            if graph_data is not None and graph_data.linked_osm_node:
                linked_node = graph_data.linked_osm_node

            contributions = {
                "graph": round(attention.get("graph", 0.0) * graph_ev["industrial"], 4),
                "vision": round(attention.get("vision", 0.0) * vision_ev["industrial"], 4),
                "time": round(attention.get("time", 0.0) * time_ev["industrial"], 4),
                "thermal_gate": round(gate, 4),
            }

            span["class"] = classification
            span["confidence"] = round(confidence, 4)
            span["degraded"] = degraded or None

            return FusionDecision(
                classification=classification,
                label=label,
                severity=severity,
                confidence=round(confidence, 4),
                thermal_gate_multiplier=gate,
                attention_weights=attention,
                modality_contributions=contributions,
                class_probabilities=probabilities,
                osm_linked_node=linked_node,
                requires_hitl=requires_hitl,
                evidence=_build_evidence(
                    temperature_k, gate, physics, graph_data, vision_data, time_data, attention
                ),
                degraded_stages=degraded,
                encoder="cross_modal_attention",
                status=StageStatus.FALLBACK if degraded else StageStatus.OK,
                notes=(
                    "confidence capped — one or more encoders degraded"
                    if degraded
                    else ""
                ),
            )

        except Exception as exc:
            span["outcome"] = "error"
            span["error"] = str(exc)[:200]
            log.exception("Stage 6 failed", extra={"stage": _STAGE, "event_id": event_id})
            return FusionDecision(
                classification=SourceClass.UNCLASSIFIED.value,
                label=HUMAN_LABELS[SourceClass.UNCLASSIFIED.value],
                severity="LOW",
                confidence=0.0,
                requires_hitl=True,
                evidence=[f"Fusion error: {str(exc)[:160]}"],
                status=StageStatus.FAILED,
                notes="fusion failed; anomaly routed to operator review",
            )


__all__ = ["cross_modal_attention", "cross_modal_attention_weights"]
