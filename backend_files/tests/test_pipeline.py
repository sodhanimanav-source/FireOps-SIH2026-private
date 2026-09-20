"""
Verification suite for the 6-stage pipeline.

The physics tests are the important ones. Stages 3-5 are encoders whose
trained weights do not ship, so they are tested for contract and graceful
degradation rather than for accuracy. Stage 2, by contrast, makes a
*falsifiable* claim — that it recovers the true sub-pixel temperature of a
fire from its pixel-integrated radiances — and that claim is checked against
synthetic pixels with known ground truth.

Run:  python -m pytest tests/test_pipeline.py -v
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from core.schemas import (
    GraphContext,
    Hotspot,
    InsatCube,
    PlanckSolution,
    SourceClass,
    StageStatus,
    TemporalContext,
    ThermalClass,
    VisionContext,
    event_id_for,
)
from ingestion.physics_filter import (
    apply_thermal_gate,
    calculate_subpixel_temperature,
    calculate_subpixel_temperature_batch,
    inverse_planck_temperature,
    planck_radiance,
    thermal_gate_multiplier,
)

MIR_UM = settings.physics.viirs_mir_um
TIR_UM = settings.physics.viirs_tir_um
GATE = settings.physics.industrial_temperature_gate_k


# ===========================================================================
# Helpers
# ===========================================================================
def synthesise_pixel(fire_temp_k, fraction, background_k=300.0):
    """
    Forward-model a satellite pixel containing a known sub-pixel fire.

    This is the inverse of what Stage 2 does, so feeding its output back in
    must recover the inputs. Ground truth is exact by construction.
    """
    mir_radiance = fraction * planck_radiance(MIR_UM, fire_temp_k) + (
        1 - fraction
    ) * planck_radiance(MIR_UM, background_k)
    tir_radiance = fraction * planck_radiance(TIR_UM, fire_temp_k) + (
        1 - fraction
    ) * planck_radiance(TIR_UM, background_k)
    return {
        "bright_mir_k": float(inverse_planck_temperature(mir_radiance, MIR_UM)),
        "bright_tir_k": float(inverse_planck_temperature(tir_radiance, TIR_UM)),
        "background_temp_k": background_k,
        "mir_wavelength_um": MIR_UM,
        "tir_wavelength_um": TIR_UM,
        "frp": 10.0,
        "pixel_area_m2": 140625.0,
    }


# ===========================================================================
# Stage 2 — Planck inversion
# ===========================================================================
class TestPlanckLaw:
    def test_planck_inverse_is_exact(self):
        """Inverting the Planck function must return the input temperature."""
        for temperature in [250.0, 300.0, 500.0, 900.0, 1500.0, 2200.0]:
            for wavelength in [MIR_UM, TIR_UM]:
                radiance = planck_radiance(wavelength, temperature)
                recovered = float(inverse_planck_temperature(radiance, wavelength))
                assert recovered == pytest.approx(temperature, rel=1e-9)

    def test_wien_displacement(self):
        """Peak emission must shift to shorter wavelengths as T rises."""
        wavelengths = np.linspace(1.0, 20.0, 2000)
        previous_peak = None
        for temperature in [400.0, 800.0, 1600.0, 2400.0]:
            peak = wavelengths[int(np.argmax(planck_radiance(wavelengths, temperature)))]
            if previous_peak is not None:
                assert peak < previous_peak
            previous_peak = peak

    def test_radiance_increases_with_temperature(self):
        temps = np.array([300.0, 600.0, 1200.0, 2400.0])
        radiances = planck_radiance(MIR_UM, temps)
        assert np.all(np.diff(radiances) > 0)


class TestSubPixelRetrieval:
    """The falsifiable claim: recover known ground truth from pixel radiances."""

    TRUTH = [
        (1900.0, 5.0e-5),   # gas flare, tiny and extremely hot
        (1800.0, 1.0e-4),
        (1650.0, 3.0e-4),   # steel furnace
        (1400.0, 5.0e-4),
        (1200.0, 1.0e-3),   # exactly on the gate
        (900.0, 3.0e-3),    # forest fire
        (750.0, 8.0e-3),    # crop residue
        (2200.0, 4.0e-5),   # refinery blaze
    ]

    def test_recovers_true_temperature(self):
        pixels = [synthesise_pixel(t, f) for t, f in self.TRUTH]
        solutions = calculate_subpixel_temperature_batch(pixels)

        for (true_temp, _), solution in zip(self.TRUTH, solutions):
            assert solution.converged, f"no retrieval at {true_temp} K"
            assert solution.subpixel_temp_k == pytest.approx(true_temp, rel=1e-4)

    def test_recovers_true_fractional_area(self):
        pixels = [synthesise_pixel(t, f) for t, f in self.TRUTH]
        solutions = calculate_subpixel_temperature_batch(pixels)

        for (_, true_fraction), solution in zip(self.TRUTH, solutions):
            assert solution.fractional_area == pytest.approx(true_fraction, rel=1e-3)

    def test_gate_separates_industrial_from_biomass(self):
        pixels = [synthesise_pixel(t, f) for t, f in self.TRUTH]
        solutions = calculate_subpixel_temperature_batch(pixels)

        for (true_temp, _), solution in zip(self.TRUTH, solutions):
            # A source sitting exactly on the threshold has no defined class:
            # the retrieval converges to within ~1e-9 K of 1200, so which side
            # it lands on is floating-point noise, not physics. Stage 6 handles
            # this band through the smooth gate multiplier instead, which is
            # precisely why that multiplier exists.
            if abs(true_temp - GATE) < 1.0:
                continue
            if true_temp > GATE:
                assert solution.thermal_class is ThermalClass.INDUSTRIAL_CANDIDATE
                assert solution.passed_gate
            else:
                assert solution.thermal_class is ThermalClass.BIOMASS
                assert not solution.passed_gate

    def test_boundary_case_is_resolved_smoothly_not_sharply(self):
        """
        An anomaly on the threshold must not produce a confident verdict in
        either direction. The logistic gate returns ~0.5 there, which keeps
        both evidence families in play and sends the anomaly to an operator.
        """
        solution = calculate_subpixel_temperature(synthesise_pixel(GATE, 1e-3))
        assert solution.subpixel_temp_k == pytest.approx(GATE, abs=0.01)
        assert thermal_gate_multiplier(solution.subpixel_temp_k) == pytest.approx(
            0.5, abs=0.01
        )

    def test_brightness_temperature_alone_would_fail(self):
        """
        The motivating result for this whole architecture.

        A hot, small industrial source and a cooler, larger biomass fire are
        constructed so the biomass fire has the *higher* pixel brightness.
        Any classifier keyed on brightness must get these backwards; the
        physics retrieval must get them right.
        """
        flare = synthesise_pixel(1900.0, 5.0e-5)
        crop = synthesise_pixel(750.0, 1.2e-2)

        assert crop["bright_mir_k"] > flare["bright_mir_k"], (
            "test setup invalid — the biomass pixel should look brighter"
        )

        flare_solution, crop_solution = calculate_subpixel_temperature_batch([flare, crop])
        assert flare_solution.thermal_class is ThermalClass.INDUSTRIAL_CANDIDATE
        assert crop_solution.thermal_class is ThermalClass.BIOMASS

    def test_indeterminate_is_not_treated_as_cold(self):
        """
        A retrieval failure must not be silently reported as a cold source.

        This is the pipeline's most dangerous failure mode: a missing thermal
        band on a refinery fire must yield "unknown", never "biomass".
        """
        solution = calculate_subpixel_temperature(
            {"bright_mir_k": None, "bright_tir_k": None, "frp": 0.0}
        )
        assert not solution.converged
        assert solution.thermal_class is ThermalClass.INDETERMINATE
        assert solution.thermal_class is not ThermalClass.BIOMASS

    def test_backwards_compatible_tuple_unpacking(self):
        """The earlier two-value call convention must keep working."""
        temperature, fraction = calculate_subpixel_temperature(
            synthesise_pixel(1800.0, 1e-4)
        )
        assert temperature == pytest.approx(1800.0, rel=1e-4)
        assert fraction == pytest.approx(1e-4, rel=1e-3)

    def test_vectorisation_matches_scalar(self):
        """Batch and single-item paths must agree exactly."""
        pixels = [synthesise_pixel(t, f) for t, f in self.TRUTH]
        batched = calculate_subpixel_temperature_batch(pixels)
        for pixel, batch_solution in zip(pixels, batched):
            single = calculate_subpixel_temperature(pixel)
            assert single.subpixel_temp_k == pytest.approx(
                batch_solution.subpixel_temp_k, rel=1e-6
            )

    def test_batch_is_fast(self):
        """The gate must be cheap enough to run on the full national feed."""
        import time

        pixels = [synthesise_pixel(1500.0, 2e-4) for _ in range(5000)]
        started = time.perf_counter()
        solutions = calculate_subpixel_temperature_batch(pixels)
        elapsed = time.perf_counter() - started

        assert len(solutions) == 5000
        assert elapsed < 5.0, f"5000 retrievals took {elapsed:.2f}s — not vectorised"


class TestThermalGate:
    def test_multiplier_is_monotone_and_centred(self):
        assert thermal_gate_multiplier(GATE) == pytest.approx(0.5, abs=0.01)
        assert thermal_gate_multiplier(GATE - 500) < 0.02
        assert thermal_gate_multiplier(GATE + 500) > 0.98

        temps = [400, 800, 1200, 1600, 2000, 2400]
        values = [thermal_gate_multiplier(t) for t in temps]
        assert all(b > a for a, b in zip(values, values[1:]))

    def test_gate_partitions_and_saves_compute(self):
        pixels = [synthesise_pixel(t, f) for t, f in TestSubPixelRetrieval.TRUTH]
        solutions = calculate_subpixel_temperature_batch(pixels)
        candidates, muted = apply_thermal_gate(pixels, solutions)

        assert len(candidates) + len(muted) == len(pixels)
        assert len(muted) >= 2  # at minimum the 900 K and 750 K cases
        for _, solution in muted:
            # `<=` because the exactly-on-threshold case may land on either
            # side within floating-point tolerance.
            assert solution.subpixel_temp_k <= GATE


# ===========================================================================
# Stage 1 — Ingestion contracts
# ===========================================================================
class TestIngestion:
    def test_event_id_is_stable_and_quantised(self):
        """Re-detections a few hundred metres apart must be one event."""
        base = event_id_for(22.3562, 69.8686)
        assert event_id_for(22.3567, 69.8689) == base   # ~60 m away
        assert event_id_for(22.5000, 69.8686) != base   # ~16 km away

    def test_hotspot_legacy_dict_access(self):
        hotspot = Hotspot(lat=22.0, lng=70.0, bright_mir_k=350.0, frp_mw=42.0)
        assert hotspot.get("latitude") == 22.0
        assert hotspot.get("bright_ti4") == 350.0
        assert hotspot["frp"] == 42.0

    def test_insat_cube_spatial_query(self):
        cube = InsatCube(
            frames=[
                {
                    "timestamp": "2026-09-20T10:00:00+00:00",
                    "satellite": "INSAT-3D",
                    "samples": [
                        {"lat": 22.0, "lng": 70.0, "frp_mw": 30.0},
                        {"lat": 28.0, "lng": 77.0, "frp_mw": 12.0},
                    ],
                }
            ]
        )
        assert len(cube.series_near(22.0, 70.0, 4.0)) == 1
        assert len(cube.series_near(10.0, 50.0, 4.0)) == 0


# ===========================================================================
# Stage 5 — Rhythm recovery
# ===========================================================================
class TestTemporalDynamics:
    def test_lomb_scargle_recovers_period_from_irregular_samples(self):
        """
        The core temporal claim: recover a known cycle from *unevenly* sampled
        observations, which is what satellite passes actually provide.
        """
        from models.contiformer_time import lomb_scargle

        rng = np.random.default_rng(42)
        times = np.sort(rng.uniform(0, 168, 120))   # 7 days, random sampling
        values = 40 + 15 * np.sin(2 * np.pi * times / 24.0) + rng.normal(0, 1.5, times.size)

        periods, power = lomb_scargle(times, values)
        assert periods.size > 0
        assert periods[int(np.argmax(power))] == pytest.approx(24.0, rel=0.05)

    def test_persistence_separates_flare_from_crop_fire(self):
        """
        Persistence must measure how long the *source* burns, not how densely
        the satellite sampled it. A 4-hour crop fire caught by seven
        consecutive frames must not outscore a week-long flare.
        """
        from datetime import datetime, timedelta, timezone

        from models.contiformer_time import run_contiformer

        origin = datetime(2026, 9, 13, tzinfo=timezone.utc)
        rng = np.random.default_rng(7)

        def series(hours, values):
            return [
                {
                    "timestamp": (origin + timedelta(hours=float(h))).isoformat(),
                    "frp_mw": float(v),
                    "bright_mir_k": 300.0 + float(v),
                }
                for h, v in zip(hours, values)
            ]

        flare_hours = np.sort(rng.uniform(0, 168, 90))
        flare = run_contiformer(
            22.0, 70.0, None,
            extra_series=series(flare_hours, 40 + rng.normal(0, 2, 90)),
        )

        crop_hours = np.sort(rng.uniform(60, 65, 7))
        crop = run_contiformer(
            22.0, 70.0, None,
            extra_series=series(crop_hours, np.abs(30 + rng.normal(0, 6, 7))),
        )

        assert flare.persistence_score > 0.7
        assert crop.persistence_score < 0.2
        assert flare.persistence_score > crop.persistence_score

    def test_no_spurious_period_from_noise(self):
        """Noise must not be reported as an operational rhythm."""
        from datetime import datetime, timedelta, timezone

        from models.contiformer_time import run_contiformer

        origin = datetime(2026, 9, 13, tzinfo=timezone.utc)
        rng = np.random.default_rng(11)
        hours = np.sort(rng.uniform(0, 168, 90))
        values = 40 + rng.normal(0, 1.5, 90)      # steady, no cycle

        result = run_contiformer(
            22.0, 70.0, None,
            extra_series=[
                {
                    "timestamp": (origin + timedelta(hours=float(h))).isoformat(),
                    "frp_mw": float(v),
                }
                for h, v in zip(hours, values)
            ],
        )
        assert result.dominant_period_h is None

    def test_insufficient_history_is_skipped_not_guessed(self):
        from models.contiformer_time import run_contiformer

        result = run_contiformer(22.0, 70.0, None, extra_series=[])
        assert result.status is StageStatus.SKIPPED
        assert result.periodicity_score == 0.0


# ===========================================================================
# Stage 4 — Vision
# ===========================================================================
class TestVision:
    @staticmethod
    def _scene(blue, green, red, nir, swir1, swir2, frames=3, jitter=0.0, seed=0):
        rng = np.random.default_rng(seed)
        array = np.zeros((frames, 6, 24, 24), dtype=np.float32)
        for t in range(frames):
            drift = 1.0 + jitter * t
            for index, value in enumerate([blue, green, red, nir, swir1, swir2]):
                array[t, index] = value * drift + rng.normal(0, 0.004, (24, 24))
        return array

    def test_concrete_outscores_burn_scar_on_permanence(self):
        """
        NDBI alone cannot separate char from concrete — both are non-vegetated
        and SWIR-bright. The NBR collapse must break the tie correctly.
        """
        from models.prithvi_vision import run_prithvi_eo

        concrete = run_prithvi_eo(self._scene(.15, .17, .19, .22, .28, .25, seed=1))
        burn = run_prithvi_eo(
            self._scene(.05, .06, .08, .12, .25, .30, jitter=-0.15, seed=2)
        )
        forest = run_prithvi_eo(self._scene(.03, .05, .04, .40, .15, .08, seed=3))

        assert concrete.permanent_structure_score > burn.permanent_structure_score
        assert burn.burn_scar_score > concrete.burn_scar_score
        assert forest.permanent_structure_score < 0.2

    def test_no_imagery_is_skipped_not_invented(self):
        from models.prithvi_vision import run_prithvi_eo

        result = run_prithvi_eo(None)
        assert result.status is StageStatus.SKIPPED
        assert result.permanent_structure_score == 0.0


# ===========================================================================
# Stage 3 — Topology
# ===========================================================================
class TestTopology:
    def test_industrial_site_outscores_open_land(self):
        from models.gnn_topology import extract_osm_graph

        refinery = extract_osm_graph(22.3562, 69.8686)   # Jamnagar
        farmland = extract_osm_graph(30.55, 75.60)       # Punjab cropland

        assert refinery.industrial_topology_score > farmland.industrial_topology_score
        assert len(refinery.embedding) == settings.graph.embedding_dim

    def test_never_raises_on_bad_input(self):
        from models.gnn_topology import extract_osm_graph

        for lat, lng in [(0.0, 0.0), (91.0, 200.0), (-90.0, -180.0)]:
            result = extract_osm_graph(lat, lng)
            assert isinstance(result, GraphContext)


# ===========================================================================
# Stage 6 — Fusion
# ===========================================================================
def _contexts(topology, permanent, scar, persistence, periodicity, regularity, burst,
              period=None, status=StageStatus.OK, mine=False):
    from core.schemas import GraphNode

    node = GraphNode(
        node_id="n1",
        kind="quarry" if mine else "flare",
        name="Test Facility",
        tags={"landuse": "quarry"} if mine else {},
    )
    graph = GraphContext(
        embedding=[0.1] * settings.graph.embedding_dim,
        node_count=12, edge_count=20, pipeline_edges=4,
        industrial_topology_score=topology, facility_name="Test Facility",
        linked_osm_node="flare:n1", nodes=[node], status=status,
    )
    vision = VisionContext(
        embedding=[0.1] * settings.vision.embedding_dim,
        permanent_structure_score=permanent, burn_scar_score=scar, status=status,
    )
    temporal = TemporalContext(
        embedding=[0.1] * settings.temporal.latent_dim,
        event_count=90, observation_span_h=168.0,
        persistence_score=persistence, periodicity_score=periodicity,
        rhythm_regularity=regularity, burst_score=burst,
        dominant_period_h=period, status=status,
    )
    return graph, vision, temporal


def _physics(temperature, converged=True):
    return PlanckSolution(
        subpixel_temp_k=temperature,
        fractional_area=1e-4,
        background_temp_k=300.0,
        thermal_class=(
            ThermalClass.INDUSTRIAL_CANDIDATE if temperature >= GATE
            else ThermalClass.BIOMASS
        ),
        passed_gate=temperature >= GATE,
        converged=converged,
        fire_area_m2=14.0,
    )


SCENARIOS = [
    ("routine flare", 1850, (0.92, 0.85, 0.05, 0.95, 1.00, 0.95, 0.05, 24.0), 30.0,
     SourceClass.ROUTINE_FLARING),
    ("flare spike", 1900, (0.92, 0.85, 0.05, 0.90, 0.90, 0.35, 0.90, 24.0), 95.0,
     SourceClass.FLARE_SPIKE),
    ("refinery accident", 2150, (0.90, 0.88, 0.10, 0.30, 0.15, 0.15, 1.00, None), 160.0,
     SourceClass.INDUSTRIAL_ACCIDENT),
    ("crop residue", 760, (0.03, 0.15, 0.82, 0.06, 0.05, 0.60, 0.10, None), 18.0,
     SourceClass.AGRICULTURAL_BURNING),
    ("wildfire", 950, (0.00, 0.10, 0.90, 0.18, 0.05, 0.30, 0.50, None), 140.0,
     SourceClass.WILDFIRE),
]


class TestFusion:
    @pytest.mark.parametrize("name,temperature,params,frp,expected", SCENARIOS)
    def test_classifies_known_scenarios(self, name, temperature, params, frp, expected):
        from models.cross_modal_fusion import cross_modal_attention

        graph, vision, temporal = _contexts(*params)
        decision = cross_modal_attention(
            temp=temperature, graph_data=graph, vision_data=vision,
            time_data=temporal, physics=_physics(temperature),
            lat=22.0, lng=70.0, frp_mw=frp,
        )
        assert decision.classification == expected.value, f"{name} misclassified"

    def test_coal_mine_beats_flaring_on_mining_topology(self):
        """Flaring needs hydrocarbon processing; a coal seam has nothing to flare."""
        from models.cross_modal_fusion import cross_modal_attention

        graph, vision, temporal = _contexts(
            0.70, 0.60, 0.30, 0.99, 0.20, 0.90, 0.05, mine=True
        )
        decision = cross_modal_attention(
            temp=1350, graph_data=graph, vision_data=vision, time_data=temporal,
            physics=_physics(1350), lat=23.7, lng=86.4, frp_mw=25.0,
        )
        assert decision.classification == SourceClass.COAL_MINE_FIRE.value

    def test_gate_directs_attention(self):
        """
        The architecture's central rule: above the combustion threshold the
        decision must lean on topology and rhythm; below it, on vision.
        """
        from models.cross_modal_fusion import cross_modal_attention

        graph, vision, temporal = _contexts(0.8, 0.7, 0.3, 0.8, 0.8, 0.8, 0.2)

        hot = cross_modal_attention(
            temp=2000, graph_data=graph, vision_data=vision, time_data=temporal,
            physics=_physics(2000), frp_mw=50.0,
        )
        cold = cross_modal_attention(
            temp=700, graph_data=graph, vision_data=vision, time_data=temporal,
            physics=_physics(700), frp_mw=50.0,
        )

        hot_structural = hot.attention_weights["graph"] + hot.attention_weights["time"]
        cold_structural = cold.attention_weights["graph"] + cold.attention_weights["time"]

        assert hot_structural > 0.8
        assert cold.attention_weights["vision"] > 0.6
        assert hot_structural > cold_structural

    def test_degradation_lowers_confidence_and_forces_review(self):
        """A degraded pipeline must never auto-approve."""
        from models.cross_modal_fusion import cross_modal_attention

        params = (0.92, 0.85, 0.05, 0.95, 1.00, 0.95, 0.05, 24.0)

        ok_graph, ok_vision, ok_time = _contexts(*params)
        healthy = cross_modal_attention(
            temp=1850, graph_data=ok_graph, vision_data=ok_vision, time_data=ok_time,
            physics=_physics(1850), frp_mw=30.0,
        )

        bad_graph, bad_vision, bad_time = _contexts(*params, status=StageStatus.FALLBACK)
        degraded = cross_modal_attention(
            temp=1850, graph_data=bad_graph, vision_data=bad_vision, time_data=bad_time,
            physics=_physics(1850), frp_mw=30.0,
        )

        # Same verdict, lower confidence — degradation changes certainty,
        # not the reading of the evidence.
        assert degraded.classification == healthy.classification

        assert degraded.confidence < healthy.confidence
        assert degraded.requires_hitl
        assert degraded.degraded_stages

    def test_total_modality_failure_falls_back(self):
        """All encoders down must still yield an answer, flagged for review."""
        from models.cross_modal_fusion import cross_modal_attention

        failed = StageStatus.FAILED
        decision = cross_modal_attention(
            temp=1800,
            graph_data=GraphContext(status=failed),
            vision_data=VisionContext(status=failed),
            time_data=TemporalContext(status=failed),
            physics=_physics(1800), lat=22.3562, lng=69.8686, frp_mw=45.0,
        )
        assert decision.encoder == "legacy_rule_based"
        assert decision.requires_hitl
        assert decision.confidence < settings.fusion.hitl_confidence_threshold

    def test_indeterminate_physics_holds_gate_neutral(self):
        """
        An unretrievable anomaly must not be forced into the biomass family
        by a temperature of zero.
        """
        from models.cross_modal_fusion import cross_modal_attention

        graph, vision, temporal = _contexts(0.9, 0.85, 0.05, 0.9, 0.9, 0.9, 0.1)
        decision = cross_modal_attention(
            temp=0.0, graph_data=graph, vision_data=vision, time_data=temporal,
            physics=_physics(0.0, converged=False), frp_mw=30.0,
        )
        assert decision.thermal_gate_multiplier == pytest.approx(0.5)
        assert decision.requires_hitl

    def test_evidence_chain_is_populated(self):
        from models.cross_modal_fusion import cross_modal_attention

        graph, vision, temporal = _contexts(0.9, 0.85, 0.05, 0.9, 0.9, 0.9, 0.1)
        decision = cross_modal_attention(
            temp=1850, graph_data=graph, vision_data=vision, time_data=temporal,
            physics=_physics(1850), frp_mw=30.0,
        )
        assert len(decision.evidence) >= 3
        assert any("1850" in e or "K" in e for e in decision.evidence)
        assert abs(sum(decision.attention_weights.values()) - 1.0) < 0.01


# ===========================================================================
# Architecture integrity
# ===========================================================================
class TestArchitecture:
    def test_no_circular_imports(self):
        """Every stage must import cleanly in isolation, in any order."""
        import importlib

        modules = [
            "core.config", "core.schemas", "core.logging_utils", "core.store",
            "ingestion.api_loader", "ingestion.physics_filter",
            "ingestion.firms_fetcher", "ingestion.fetch_osm_facilities",
            "models.gnn_topology", "models.prithvi_vision",
            "models.contiformer_time", "models.cross_modal_fusion",
            "agent_loop",
        ]
        for name in modules:
            importlib.import_module(name)

    def test_orchestrator_holds_no_model_logic(self):
        """
        agent_loop must remain a traffic controller. If model mathematics
        starts leaking into it, the modular separation is gone.
        """
        import inspect

        import agent_loop

        source = inspect.getsource(agent_loop)
        for forbidden in ["planck", "np.exp", "SAGEConv", "odeint", "softmax", "sigmoid"]:
            assert forbidden not in source, (
                f"'{forbidden}' found in agent_loop — model logic belongs in a stage module"
            )

    def test_every_stage_returns_its_contract_on_failure(self):
        """No stage may raise; each degrades into its own typed contract."""
        from models.contiformer_time import run_contiformer
        from models.cross_modal_fusion import cross_modal_attention
        from models.gnn_topology import extract_osm_graph
        from models.prithvi_vision import run_prithvi_eo

        assert isinstance(extract_osm_graph(999.0, 999.0), GraphContext)
        assert isinstance(run_prithvi_eo("not an image"), VisionContext)
        assert isinstance(run_contiformer(999.0, 999.0, None), TemporalContext)
        assert cross_modal_attention(temp=None) is not None

    def test_schemas_are_json_serialisable(self):
        import json

        from core.schemas import FusionDecision, PipelineResult

        result = PipelineResult(
            event_id="EVT-TEST", lat=22.0, lng=70.0,
            physics=_physics(1800.0).to_dict(),
            fusion=FusionDecision(classification="ROUTINE_FLARING", confidence=0.9).to_dict(),
        )
        encoded = json.dumps(result.to_dict())
        assert "EVT-TEST" in encoded
        assert "AI_Confidence" in json.dumps(result.intelligence_properties())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
