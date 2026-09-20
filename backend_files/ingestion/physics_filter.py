"""
STAGE 2 — Sub-Pixel Thermodynamics (Planck Inversion)
======================================================

The problem
-----------
A satellite does not measure the temperature of a fire. It measures the
radiance of a whole pixel — 375 m x 375 m for VIIRS, 4 km for INSAT — inside
which the actual flame may occupy a millionth of the area. The reported
"brightness temperature" is therefore an area-weighted average, and a 1900 K
gas flare covering 30 m^2 and a 900 K crop fire covering 4000 m^2 can produce
*exactly the same* pixel brightness. Classifying on brightness alone is
physically incapable of separating them.

The solution
------------
Invert Planck's radiation law to recover the two quantities that actually
matter — the true source temperature ``T_subpixel`` and the fraction of the
pixel it fills ``p``.

For a pixel containing a hot source at ``T_f`` filling fraction ``p`` over a
background at ``T_b``, the observed spectral radiance in band lambda is:

    L_obs(λ) = p · B(λ, T_f) + (1 - p) · B(λ, T_b)                       (1)

with Planck's law

    B(λ, T) = c1 / ( λ^5 · ( exp(c2 / (λ·T)) - 1 ) )                     (2)

Two unknowns (``T_f``, ``p``), so two bands are needed. Using a mid-wave
infrared band (≈3.74 µm, exquisitely sensitive to hot sub-pixel sources) and a
thermal band (≈11 µm, dominated by the background) gives the classical
bi-spectral retrieval of Dozier (1981). Rearranging (1) for the MIR band:

    p = ( L_mir - B(λ_mir, T_b) ) / ( B(λ_mir, T_f) - B(λ_mir, T_b) )    (3)

Substituting (3) into (1) for the TIR band leaves a single scalar equation in
``T_f``:

    g(T_f) = p(T_f)·( B(λ_tir,T_f) - B(λ_tir,T_b) ) - ( L_tir - B(λ_tir,T_b) )

``g`` is strictly monotonically decreasing on ``(T_b, ∞)``: the MIR Planck
function grows exponentially with temperature while the TIR one grows only
quasi-linearly, so ``p(T_f)`` collapses far faster than ``B(λ_tir,T_f)`` rises.
A single root therefore exists and bisection is unconditionally convergent —
which is what makes the whole retrieval safely **vectorisable**: every
anomaly in the country is solved with the same fixed number of array
operations, with no per-pixel Python loop and no iteration-count divergence.

The gate
--------
Biomass combustion — forest litter, crop residue, grass — burns at roughly
600-1100 K. Industrial combustion — gas flares, blast furnaces, refinery
stacks — runs at 1400-2200 K. The separation is a property of the fuel and the
oxidiser, not of the observing satellite, so a threshold at **1200 K** splits
the two populations on physics alone.

Anything below the gate is muted immediately and never reaches the AI stages.
That is not only a classification decision, it is the pipeline's main compute
saving: during the North Indian stubble-burning season the LEO feed is >90%
biomass, and those anomalies are discarded for the cost of a few array
operations instead of three neural network invocations each.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from core.config import settings
from core.logging_utils import get_logger, stage_span
from core.schemas import Hotspot, PlanckSolution, StageStatus, ThermalClass

log = get_logger("stage2.physics")

_STAGE = 2
_PHYS = settings.physics

# Radiation constants, λ in µm and L in W·m^-2·sr^-1·µm^-1.
C1 = _PHYS.c1          # 2hc^2
C2 = _PHYS.c2          # hc / k_B
SIGMA = _PHYS.stefan_boltzmann

# Temperatures below this are non-physical for a combustion source and would
# risk overflow in the exponential.
_MIN_PHYSICAL_T = 50.0


# ---------------------------------------------------------------------------
# Planck's law and its analytic inverse (fully vectorised)
# ---------------------------------------------------------------------------
def planck_radiance(wavelength_um: Any, temperature_k: Any) -> np.ndarray:
    """
    Spectral radiance B(λ, T) in W·m^-2·sr^-1·µm^-1.

    Accepts scalars or arrays of any broadcastable shape.
    """
    lam = np.asarray(wavelength_um, dtype=np.float64)
    temp = np.clip(np.asarray(temperature_k, dtype=np.float64), _MIN_PHYSICAL_T, None)

    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        exponent = C2 / (lam * temp)
        # expm1 is exact for small arguments, where exp(x)-1 loses precision.
        denominator = np.expm1(exponent)
        radiance = C1 / (np.power(lam, 5.0) * denominator)

    return np.nan_to_num(radiance, nan=0.0, posinf=0.0, neginf=0.0)


def inverse_planck_temperature(radiance: Any, wavelength_um: Any) -> np.ndarray:
    """
    Brightness temperature from spectral radiance — the analytic inverse of (2).

        T = c2 / ( λ · ln( 1 + c1 / (λ^5 · L) ) )
    """
    lam = np.asarray(wavelength_um, dtype=np.float64)
    rad = np.asarray(radiance, dtype=np.float64)

    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        ratio = C1 / (np.power(lam, 5.0) * np.where(rad > 0.0, rad, np.nan))
        temperature = C2 / (lam * np.log1p(ratio))

    return np.nan_to_num(temperature, nan=0.0, posinf=0.0, neginf=0.0)


# ---------------------------------------------------------------------------
# Vectorised bisection
# ---------------------------------------------------------------------------
def _bisect(
    residual_fn,
    low: np.ndarray,
    high: np.ndarray,
    iterations: int,
) -> np.ndarray:
    """
    Vectorised bisection for a strictly decreasing residual function.

    Every element performs the identical fixed number of iterations, so the
    whole national batch is solved in ``iterations`` array passes with no
    data-dependent branching. ``iterations=60`` narrows a 2600 K bracket to
    below 1e-15 K, far past float64 resolution.
    """
    lo = np.array(low, dtype=np.float64, copy=True)
    hi = np.array(high, dtype=np.float64, copy=True)

    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        # Decreasing function: positive residual means the root lies above mid.
        above = residual_fn(mid) > 0.0
        lo = np.where(above, mid, lo)
        hi = np.where(above, hi, mid)

    return 0.5 * (lo + hi)


def _bisect_bracket(
    residual_fn,
    low: np.ndarray,
    high: np.ndarray,
    iterations: int,
) -> np.ndarray:
    """
    Bisection inside a bracket already known to contain a sign change.

    Unlike :func:`_bisect` this makes no assumption about whether the function
    increases or decreases, so it can refine a root of a non-monotonic
    residual. Used by the FRP-constrained retrieval.
    """
    lo = np.array(low, dtype=np.float64, copy=True)
    hi = np.array(high, dtype=np.float64, copy=True)
    f_lo = residual_fn(lo)

    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        f_mid = residual_fn(mid)
        same_side = (f_mid * f_lo) > 0.0
        lo = np.where(same_side, mid, lo)
        f_lo = np.where(same_side, f_mid, f_lo)
        hi = np.where(same_side, hi, mid)

    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Retrieval 1 — Dozier bi-spectral (MIR + TIR)
# ---------------------------------------------------------------------------
def solve_dozier(
    mir_radiance: np.ndarray,
    tir_radiance: np.ndarray,
    background_k: np.ndarray,
    mir_um: np.ndarray,
    tir_um: np.ndarray,
    iterations: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Bi-spectral sub-pixel retrieval.

    Returns ``(temperature_k, fractional_area, residual, valid)`` as arrays.
    ``valid`` marks the elements where the observation carries a genuine
    thermal excess in both bands, which is the precondition for (3) to have a
    physical solution.
    """
    iters = iterations if iterations is not None else _PHYS.solver_iterations

    mir_rad = np.asarray(mir_radiance, dtype=np.float64)
    tir_rad = np.asarray(tir_radiance, dtype=np.float64)
    t_bg = np.asarray(background_k, dtype=np.float64)

    b_mir_bg = planck_radiance(mir_um, t_bg)
    b_tir_bg = planck_radiance(tir_um, t_bg)

    # Thermal excess over the background in each band.
    delta_mir = mir_rad - b_mir_bg
    delta_tir = tir_rad - b_tir_bg

    # A physical retrieval needs a positive excess in both bands.
    valid = (delta_mir > 0.0) & (delta_tir > 0.0) & np.isfinite(delta_mir) & np.isfinite(delta_tir)

    # Guard the residual against division by zero on invalid elements; their
    # results are discarded by the caller via `valid`.
    safe_delta_mir = np.where(valid, delta_mir, 1.0)
    safe_delta_tir = np.where(valid, delta_tir, 1.0)

    def residual(temp: np.ndarray) -> np.ndarray:
        b_mir_fire = planck_radiance(mir_um, temp)
        b_tir_fire = planck_radiance(tir_um, temp)

        mir_contrast = b_mir_fire - b_mir_bg
        # Below the background the retrieval is meaningless; force the residual
        # positive there so bisection walks upward out of the region.
        mir_contrast = np.where(mir_contrast > 1e-12, mir_contrast, 1e-12)

        frac = safe_delta_mir / mir_contrast
        return frac * (b_tir_fire - b_tir_bg) - safe_delta_tir

    lower = np.maximum(t_bg + 1.0, _PHYS.solver_min_temp_k)
    upper = np.full_like(lower, _PHYS.solver_max_temp_k)

    temperature = _bisect(residual, lower, upper, iters)

    # Recover the fractional area at the converged temperature.
    b_mir_fire = planck_radiance(mir_um, temperature)
    mir_contrast = np.where(
        (b_mir_fire - b_mir_bg) > 1e-12, b_mir_fire - b_mir_bg, np.nan
    )
    fractional_area = np.nan_to_num(delta_mir / mir_contrast, nan=0.0)

    final_residual = np.abs(residual(temperature)) / np.maximum(np.abs(safe_delta_tir), 1e-12)

    # Reject retrievals that ran into the solver bounds or gave a non-physical
    # filling fraction.
    valid &= fractional_area > _PHYS.min_fractional_area
    valid &= fractional_area <= _PHYS.max_fractional_area
    valid &= temperature < (_PHYS.solver_max_temp_k - 1.0)
    valid &= temperature > (_PHYS.solver_min_temp_k + 1.0)

    return temperature, fractional_area, final_residual, valid


# ---------------------------------------------------------------------------
# Retrieval 2 — FRP-constrained (MIR + FRP, used when TIR is missing)
# ---------------------------------------------------------------------------
def solve_frp_constrained(
    mir_radiance: np.ndarray,
    frp_watts: np.ndarray,
    pixel_area_m2: np.ndarray,
    background_k: np.ndarray,
    mir_um: np.ndarray,
    iterations: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Second closure equation when no thermal band is reported.

    MODIS and some VIIRS products deliver a fire radiative power but no usable
    11 µm brightness. FRP supplies the missing constraint through the
    Stefan-Boltzmann relation over the fire's own area:

        FRP = A_pixel · p · σ · (T_f^4 - T_b^4)

    Combined with (3) this gives a single scalar equation in ``T_f``.

    **This residual is not monotonic**, and that matters. As temperature
    rises, the 3.74 µm Planck function eventually leaves the Wien regime and
    approaches the Rayleigh-Jeans limit where ``B ∝ T``, while the emitted
    power keeps growing as ``T⁴``. The ratio ``(T⁴-T_b⁴)/(B_mir(T)-B_mir(T_b))``
    therefore *falls* to a minimum near 1000 K and *rises* again above it, so
    the equation admits **zero or two** solutions rather than one.

    The consequence is physical, not numerical: a single MIR band plus an FRP
    value genuinely cannot always distinguish a large cool fire from a small
    hot one. Rather than let a bisection silently return whichever bound it
    drifted into, this routine scans for every sign change and then:

    * no root        -> no retrieval (the reported FRP is inconsistent with
                        the observed MIR excess)
    * one root       -> accept it
    * two roots that fall on the same side of the industrial gate -> accept
                        the hotter one; the gate decision is identical either
                        way, so only the reported temperature is affected
    * two roots that straddle the gate -> **refuse to decide**. The evidence
                        is genuinely ambiguous, and Stage 6 will hold the
                        anomaly for an operator instead of guessing.
    """
    iters = iterations if iterations is not None else _PHYS.solver_iterations

    mir_rad = np.asarray(mir_radiance, dtype=np.float64)
    frp_w = np.asarray(frp_watts, dtype=np.float64)
    area = np.asarray(pixel_area_m2, dtype=np.float64)
    t_bg = np.asarray(background_k, dtype=np.float64)
    lam = np.asarray(mir_um, dtype=np.float64)

    b_mir_bg = planck_radiance(lam, t_bg)
    delta_mir = mir_rad - b_mir_bg

    valid = (delta_mir > 0.0) & (frp_w > 0.0) & (area > 0.0) & np.isfinite(delta_mir)
    safe_delta_mir = np.where(valid, delta_mir, 1.0)
    safe_frp = np.where(valid, frp_w, 1.0)
    safe_area = np.where(valid, area, 1.0)

    def residual_at(temp: np.ndarray, axis: bool = False) -> np.ndarray:
        """Residual, broadcasting against either (n,) or (n, G) temperatures."""
        if axis:
            bg = t_bg[:, None]
            b_bg = b_mir_bg[:, None]
            d_mir = safe_delta_mir[:, None]
            a_px = safe_area[:, None]
            frp = safe_frp[:, None]
            wl = lam[:, None]
        else:
            bg, b_bg, d_mir, a_px, frp, wl = (
                t_bg, b_mir_bg, safe_delta_mir, safe_area, safe_frp, lam
            )
        b_fire = planck_radiance(wl, temp)
        contrast = np.where((b_fire - b_bg) > 1e-12, b_fire - b_bg, 1e-12)
        frac = d_mir / contrast
        emitted = a_px * frac * SIGMA * (np.power(temp, 4.0) - np.power(bg, 4.0))
        return emitted - frp

    lower = np.maximum(t_bg + 1.0, _PHYS.solver_min_temp_k)
    upper = np.full_like(lower, _PHYS.solver_max_temp_k)

    # --- Scan for sign changes across the full physical range --------------
    grid_size = 256
    fractions = np.linspace(0.0, 1.0, grid_size)
    grid = lower[:, None] + (upper - lower)[:, None] * fractions[None, :]
    values = residual_at(grid, axis=True)

    crossings = (values[:, :-1] * values[:, 1:]) < 0.0
    root_count = crossings.sum(axis=1)

    n = delta_mir.shape[0]
    rows = np.arange(n)

    # First bracket.
    first_idx = np.argmax(crossings, axis=1)
    has_first = root_count >= 1
    lo1 = np.where(has_first, grid[rows, first_idx], lower)
    hi1 = np.where(has_first, grid[rows, np.minimum(first_idx + 1, grid_size - 1)], upper)
    root1 = _bisect_bracket(lambda t: residual_at(t), lo1, hi1, iters)

    # Second bracket, if any.
    masked = crossings.copy()
    masked[rows, first_idx] = False
    second_idx = np.argmax(masked, axis=1)
    has_second = root_count >= 2
    lo2 = np.where(has_second, grid[rows, second_idx], lower)
    hi2 = np.where(has_second, grid[rows, np.minimum(second_idx + 1, grid_size - 1)], upper)
    root2 = _bisect_bracket(lambda t: residual_at(t), lo2, hi2, iters)

    gate = _PHYS.industrial_temperature_gate_k
    hotter = np.maximum(root1, root2)
    cooler = np.minimum(root1, root2)

    # Two roots straddling the gate: the retrieval cannot adjudicate.
    straddles = has_second & ((cooler < gate) & (hotter >= gate))

    temperature = np.where(has_second, hotter, root1)
    valid &= has_first
    valid &= ~straddles

    b_mir_fire = planck_radiance(lam, temperature)
    mir_contrast = np.where(
        (b_mir_fire - b_mir_bg) > 1e-12, b_mir_fire - b_mir_bg, np.nan
    )
    fractional_area = np.nan_to_num(delta_mir / mir_contrast, nan=0.0)
    final_residual = np.abs(residual_at(temperature)) / np.maximum(np.abs(safe_frp), 1e-12)

    valid &= fractional_area > _PHYS.min_fractional_area
    valid &= fractional_area <= _PHYS.max_fractional_area
    valid &= temperature < (_PHYS.solver_max_temp_k - 1.0)
    valid &= temperature > (_PHYS.solver_min_temp_k + 1.0)

    return temperature, fractional_area, final_residual, valid


# ---------------------------------------------------------------------------
# Batch driver
# ---------------------------------------------------------------------------
def _as_hotspot_fields(item: Any) -> Dict[str, Optional[float]]:
    """Read the physics inputs from a Hotspot, a dict, or a DataFrame row."""
    def pick(*keys: str) -> Optional[float]:
        for key in keys:
            if isinstance(item, Hotspot):
                value = item.get(key, None)
            elif isinstance(item, dict):
                value = item.get(key)
            else:
                value = getattr(item, key, None)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isnan(number) or math.isinf(number):
                continue
            return number
        return None

    return {
        "mir_k": pick("bright_mir_k", "bright_ti4", "brightness", "bright_t21"),
        "tir_k": pick("bright_tir_k", "bright_ti5", "bright_t31"),
        "frp_mw": pick("frp_mw", "frp") or 0.0,
        "pixel_area_m2": pick("pixel_area_m2") or 140_625.0,  # 375 m VIIRS pixel
        "background_k": pick("background_temp_k"),
        "mir_um": pick("mir_wavelength_um") or _PHYS.viirs_mir_um,
        "tir_um": pick("tir_wavelength_um") or _PHYS.viirs_tir_um,
    }


def calculate_subpixel_temperature_batch(
    items: Sequence[Any],
    gate_k: Optional[float] = None,
) -> List[PlanckSolution]:
    """
    Vectorised Stage 2 over an entire batch of anomalies.

    This is the function the orchestrator should call: all anomalies in a
    polling cycle are solved in a handful of array operations, which is what
    keeps the gate cheap enough to run on the full national feed.
    """
    threshold = gate_k if gate_k is not None else _PHYS.industrial_temperature_gate_k

    if not items:
        return []

    with stage_span(log, _STAGE, "planck_inversion_batch") as span:
        span["count"] = len(items)
        span["gate_k"] = threshold

        fields = [_as_hotspot_fields(item) for item in items]

        mir_k = np.array([f["mir_k"] if f["mir_k"] else np.nan for f in fields], dtype=np.float64)
        tir_k = np.array([f["tir_k"] if f["tir_k"] else np.nan for f in fields], dtype=np.float64)
        frp_mw = np.array([f["frp_mw"] for f in fields], dtype=np.float64)
        pixel_area = np.array([f["pixel_area_m2"] for f in fields], dtype=np.float64)
        mir_um = np.array([f["mir_um"] for f in fields], dtype=np.float64)
        tir_um = np.array([f["tir_um"] for f in fields], dtype=np.float64)

        # Background temperature: prefer a measured GEO-derived value, then the
        # scene's own cool percentile, then the configured default.
        supplied_bg = np.array(
            [f["background_k"] if f["background_k"] else np.nan for f in fields],
            dtype=np.float64,
        )
        scene_bg = _estimate_scene_background(tir_k)
        background_k = np.where(np.isfinite(supplied_bg), supplied_bg, scene_bg)

        # Convert observed brightness temperatures to spectral radiances.
        mir_radiance = np.where(
            np.isfinite(mir_k), planck_radiance(mir_um, np.nan_to_num(mir_k, nan=1.0)), np.nan
        )
        tir_radiance = np.where(
            np.isfinite(tir_k), planck_radiance(tir_um, np.nan_to_num(tir_k, nan=1.0)), np.nan
        )

        has_both = np.isfinite(mir_radiance) & np.isfinite(tir_radiance)
        has_mir_frp = np.isfinite(mir_radiance) & (frp_mw > 0.0)

        n = len(items)
        temperature = np.zeros(n, dtype=np.float64)
        fractional = np.zeros(n, dtype=np.float64)
        residual = np.zeros(n, dtype=np.float64)
        converged = np.zeros(n, dtype=bool)
        method = np.array(["insufficient_bands"] * n, dtype=object)

        # --- Primary: Dozier bi-spectral -----------------------------------
        if has_both.any():
            t_d, p_d, r_d, ok_d = solve_dozier(
                np.nan_to_num(mir_radiance, nan=0.0),
                np.nan_to_num(tir_radiance, nan=0.0),
                background_k,
                mir_um,
                tir_um,
            )
            use = has_both & ok_d
            temperature = np.where(use, t_d, temperature)
            fractional = np.where(use, p_d, fractional)
            residual = np.where(use, r_d, residual)
            converged |= use
            method = np.where(use, "dozier_bispectral", method)

        # --- Secondary: FRP-constrained ------------------------------------
        needs_fallback = (~converged) & has_mir_frp
        if needs_fallback.any():
            t_f, p_f, r_f, ok_f = solve_frp_constrained(
                np.nan_to_num(mir_radiance, nan=0.0),
                frp_mw * 1.0e6,  # MW -> W
                pixel_area,
                background_k,
                mir_um,
            )
            use = needs_fallback & ok_f
            temperature = np.where(use, t_f, temperature)
            fractional = np.where(use, p_f, fractional)
            residual = np.where(use, r_f, residual)
            converged |= use
            method = np.where(use, "frp_constrained", method)

        # --- Derived quantities --------------------------------------------
        fire_area = fractional * pixel_area
        frp_retrieved_w = (
            fire_area * SIGMA * (np.power(temperature, 4.0) - np.power(background_k, 4.0))
        )
        frp_retrieved_mw = np.where(converged, frp_retrieved_w / 1.0e6, np.nan)

        # Agreement between the retrieved and the reported FRP — an independent
        # check that the inversion is self-consistent.
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = np.where(
                (frp_mw > 0.0) & np.isfinite(frp_retrieved_mw),
                np.minimum(frp_retrieved_mw, frp_mw) / np.maximum(frp_retrieved_mw, frp_mw),
                np.nan,
            )
        agreement = np.clip(np.nan_to_num(ratio, nan=-1.0), -1.0, 1.0)

        passed = converged & (temperature >= threshold)

        # Retrievals above the physical ceiling for combustion in air are kept
        # — the anomaly is unquestionably industrial-hot and the gate decision
        # is unaffected — but flagged, because the *number* is not credible and
        # Stage 6 should not rest confidence on it.
        implausible = converged & (temperature > _PHYS.max_plausible_combustion_k)

        solutions: List[PlanckSolution] = []
        for index in range(n):
            if converged[index]:
                thermal_class = (
                    ThermalClass.INDUSTRIAL_CANDIDATE
                    if passed[index]
                    else ThermalClass.BIOMASS
                )
                if implausible[index]:
                    status = StageStatus.FALLBACK
                    note = (
                        f"retrieved {temperature[index]:.0f} K exceeds the "
                        f"{_PHYS.max_plausible_combustion_k:.0f} K ceiling for "
                        "combustion in air — the bi-spectral solution is "
                        "noise-dominated (near-zero TIR excess). Treated as "
                        "confirmed industrial heat, but the temperature value "
                        "itself is not relied upon."
                    )
                else:
                    status = StageStatus.OK
                    note = ""
            else:
                thermal_class = ThermalClass.INDETERMINATE
                status = StageStatus.FALLBACK
                note = (
                    "no usable retrieval: the thermal excess was absent in one "
                    "or both bands, the filling fraction fell outside physical "
                    "bounds, or the single-band solution was ambiguous across "
                    "the industrial gate. Treated as unknown, not as cold."
                )

            solutions.append(
                PlanckSolution(
                    subpixel_temp_k=round(float(temperature[index]), 2) if converged[index] else 0.0,
                    fractional_area=float(fractional[index]) if converged[index] else 0.0,
                    background_temp_k=round(float(background_k[index]), 2),
                    thermal_class=thermal_class,
                    gate_threshold_k=threshold,
                    passed_gate=bool(passed[index]),
                    method=str(method[index]),
                    residual=float(residual[index]),
                    converged=bool(converged[index]),
                    retrieval_plausible=not bool(implausible[index]),
                    fire_area_m2=round(float(fire_area[index]), 4) if converged[index] else 0.0,
                    frp_retrieved_mw=(
                        round(float(frp_retrieved_mw[index]), 3)
                        if converged[index] and np.isfinite(frp_retrieved_mw[index])
                        else None
                    ),
                    frp_observed_mw=round(float(frp_mw[index]), 3),
                    frp_agreement=(
                        round(float(agreement[index]), 4) if agreement[index] >= 0.0 else None
                    ),
                    mir_radiance=(
                        round(float(mir_radiance[index]), 6)
                        if np.isfinite(mir_radiance[index])
                        else None
                    ),
                    tir_radiance=(
                        round(float(tir_radiance[index]), 6)
                        if np.isfinite(tir_radiance[index])
                        else None
                    ),
                    status=status,
                    notes=note,
                )
            )

        span["converged"] = int(converged.sum())
        span["passed_gate"] = int(passed.sum())
        if implausible.any():
            span["implausible"] = int(implausible.sum())
        span["muted_biomass"] = int((converged & ~passed).sum())
        span["mean_temp_k"] = float(temperature[converged].mean()) if converged.any() else 0.0
        return solutions


def _estimate_scene_background(tir_k: np.ndarray) -> np.ndarray:
    """
    Background temperature for each pixel.

    With enough thermal readings in the batch the 20th percentile of the scene
    is a good ambient estimate (fires are a small minority of any scene). With
    too few, the configured climatological default is used.
    """
    finite = tir_k[np.isfinite(tir_k)]
    if finite.size >= 8:
        estimate = float(np.percentile(finite, 20.0))
        estimate = min(max(estimate, 270.0), 330.0)
    else:
        estimate = _PHYS.default_background_temp_k
    return np.full(tir_k.shape, estimate, dtype=np.float64)


# ---------------------------------------------------------------------------
# Single-anomaly convenience wrapper
# ---------------------------------------------------------------------------
def calculate_subpixel_temperature(hotspot: Any, gate_k: Optional[float] = None) -> PlanckSolution:
    """
    Solve one anomaly.

    Returns a :class:`PlanckSolution`, which also unpacks as a 2-tuple::

        subpixel_temp, fractional_area = calculate_subpixel_temperature(hs)

    For more than a handful of anomalies call
    :func:`calculate_subpixel_temperature_batch` instead — it is the vectorised
    path and avoids the per-call array setup.
    """
    results = calculate_subpixel_temperature_batch([hotspot], gate_k=gate_k)
    if results:
        return results[0]
    return PlanckSolution(
        subpixel_temp_k=0.0,
        fractional_area=0.0,
        background_temp_k=_PHYS.default_background_temp_k,
        thermal_class=ThermalClass.INDETERMINATE,
        status=StageStatus.FAILED,
        notes="no input",
    )


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
def apply_thermal_gate(
    items: Sequence[Any],
    solutions: Sequence[PlanckSolution],
) -> Tuple[List[Tuple[Any, PlanckSolution]], List[Tuple[Any, PlanckSolution]]]:
    """
    Split anomalies on the 1200 K industrial combustion threshold.

    Returns ``(industrial_candidates, muted_biomass)``. Only the first list is
    allowed to continue to Stages 3-6; the second is closed out here, which is
    where the pipeline's compute saving comes from.

    Anomalies with no physical solution are routed to the candidate list rather
    than being silently discarded — an un-retrievable anomaly is an unknown,
    not a confirmed biomass fire, and Stage 6 will hold it for operator review.
    """
    candidates: List[Tuple[Any, PlanckSolution]] = []
    muted: List[Tuple[Any, PlanckSolution]] = []

    for item, solution in zip(items, solutions):
        if solution.thermal_class is ThermalClass.BIOMASS:
            muted.append((item, solution))
        else:
            candidates.append((item, solution))

    log.info(
        "Thermal gate: %d industrial candidates, %d biomass anomalies muted",
        len(candidates),
        len(muted),
        extra={
            "stage": _STAGE,
            "fields": {
                "gate_k": _PHYS.industrial_temperature_gate_k,
                "compute_saved_pct": round(
                    100.0 * len(muted) / max(1, len(muted) + len(candidates)), 1
                ),
            },
        },
    )
    return candidates, muted


def thermal_gate_multiplier(temperature_k: float, gate_k: Optional[float] = None) -> float:
    """
    Smooth version of the gate, used by Stage 6 as an attention multiplier.

    A hard step would make a 1199 K and a 1201 K retrieval produce wildly
    different confidences despite being within the retrieval's own uncertainty.
    A logistic centred on the gate keeps the decision continuous while still
    collapsing to ~0 well below it and ~1 well above.
    """
    threshold = gate_k if gate_k is not None else _PHYS.industrial_temperature_gate_k
    softness = max(1e-6, _PHYS.gate_softness_k)
    exponent = -(float(temperature_k) - threshold) / softness
    exponent = max(-60.0, min(60.0, exponent))
    return round(1.0 / (1.0 + math.exp(exponent)), 6)


__all__ = [
    "planck_radiance",
    "inverse_planck_temperature",
    "solve_dozier",
    "solve_frp_constrained",
    "calculate_subpixel_temperature",
    "calculate_subpixel_temperature_batch",
    "apply_thermal_gate",
    "thermal_gate_multiplier",
]
