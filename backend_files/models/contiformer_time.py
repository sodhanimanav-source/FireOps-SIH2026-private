"""
STAGE 5 — Time Rhythm Dynamics (ContiFormer + Neural ODE, MTPP)
================================================================

The signal
----------
Given everything else is ambiguous, *when* a source burns is the most
discriminating evidence available:

* A refinery flare is lit continuously for months and modulated by plant
  load — a rhythm.
* A steel furnace follows shift cycles — a rhythm.
* A crop fire burns for four hours on one afternoon and never returns — an
  isolated burst.

The obstacle
------------
Satellites do not sample on a grid. LEO passes come twice a day at drifting
local times; cloud cover deletes observations at random; INSAT contributes a
30-minute cadence only when the sky is clear. The observation series is
**irregular, gapped, and non-uniform**, which breaks every standard sequence
model: an RNN or a vanilla Transformer sees "step 1, step 2, step 3" and has
no notion that step 2 came 20 minutes later and step 3 came nine hours later.

The approach
------------
Three complementary tools, each chosen for irregular sampling:

**1. Lomb-Scargle periodogram** — the classical spectral estimator built
specifically for unevenly sampled time series (Lomb 1976, Scargle 1982). It
fits sinusoids by least squares at each trial frequency rather than assuming a
uniform grid, so it recovers a 24-hour operational cycle from scattered passes
where an FFT would return noise. This is the component that actually
establishes periodicity, and its false-alarm probability gives a calibrated
significance.

**2. Neural ODE latent flow** — the latent state evolves *continuously*
between observations:

    dz/dt = f_θ(z, t),      z(t_{i+1}) = z(t_i) + ∫ f_θ dt

so a nine-hour gap is integrated as a nine-hour gap. Implemented with
``torchdiffeq`` where available and with an explicit RK4 integrator otherwise.

**3. Continuous-time attention (ContiFormer)** — attention logits carry an
explicit temporal kernel ``exp(-|t_i - t_j| / τ)``, so relevance decays with
real elapsed time rather than with index distance.

**Marked Temporal Point Process framing** — the sequence is treated as events
on a continuous timeline with marks (FRP, brightness), and the fitted
intensity ``λ(t)`` separates a persistent process from a one-off arrival.

Honesty note
------------
As with Stage 3, the ODE and attention weights are **deterministically
initialised, not trained** — no labelled rhythm corpus ships here. They
provide a stable continuous-time representation for the fusion layer. The
quantities that actually drive the Stage 6 decision are the *analytic*
statistics computed below — persistence, Lomb-Scargle periodicity, regularity
and burstiness — all of which are interpretable and independently verifiable.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.config import settings
from core.logging_utils import get_logger, stage_span
from core.schemas import InsatCube, StageStatus, TemporalContext

log = get_logger("stage5.temporal")

_STAGE = 5
_CFG = settings.temporal

try:
    import torch
    import torch.nn as nn

    _TORCH = True
except Exception:  # pragma: no cover
    _TORCH = False

try:
    from torchdiffeq import odeint

    _TORCHDIFFEQ = True
except Exception:  # pragma: no cover
    _TORCHDIFFEQ = False


# ---------------------------------------------------------------------------
# Event extraction
# ---------------------------------------------------------------------------
def _parse_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def build_event_sequence(
    lat: float,
    lng: float,
    cube: Optional[InsatCube] = None,
    extra_series: Optional[Sequence[Dict[str, Any]]] = None,
    radius_km: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Assemble the marked point process for one location.

    Returns ``(times_hours, frp_marks, brightness_marks)`` with ``times_hours``
    measured from the first observation. Samples are merged from the INSAT cube
    and any additional series the caller already holds.
    """
    samples: List[Dict[str, Any]] = []

    if cube is not None and cube.frame_count:
        radius = radius_km if radius_km is not None else cube.spatial_resolution_km
        samples.extend(cube.series_near(lat, lng, radius))

    if extra_series:
        samples.extend(extra_series)

    parsed: List[Tuple[datetime, float, float]] = []
    for sample in samples:
        stamp = _parse_time(sample.get("timestamp") or sample.get("acq_datetime"))
        if stamp is None:
            continue
        try:
            frp = float(sample.get("frp_mw", sample.get("frp", 0.0)) or 0.0)
        except (TypeError, ValueError):
            frp = 0.0
        try:
            brightness = float(
                sample.get("bright_mir_k", sample.get("bright_ti4", 0.0)) or 0.0
            )
        except (TypeError, ValueError):
            brightness = 0.0
        parsed.append((stamp, frp, brightness))

    if not parsed:
        return np.array([]), np.array([]), np.array([])

    parsed.sort(key=lambda row: row[0])
    origin = parsed[0][0]
    times = np.array(
        [(row[0] - origin).total_seconds() / 3600.0 for row in parsed], dtype=np.float64
    )
    frp = np.array([row[1] for row in parsed], dtype=np.float64)
    brightness = np.array([row[2] for row in parsed], dtype=np.float64)

    # Collapse duplicate timestamps (two satellites seeing the same minute).
    unique_times, index = np.unique(np.round(times, 4), return_index=True)
    return unique_times, frp[index], brightness[index]


# ---------------------------------------------------------------------------
# Lomb-Scargle periodogram for unevenly sampled data
# ---------------------------------------------------------------------------
def lomb_scargle(
    times: np.ndarray,
    values: np.ndarray,
    min_period_h: Optional[float] = None,
    max_period_h: Optional[float] = None,
    resolution: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Normalised Lomb-Scargle power spectrum.

    For each trial angular frequency ω, a time offset τ is chosen so the
    sine and cosine bases are orthogonal on the *actual* sample times:

        tan(2ωτ) = Σ sin(2ω t_i) / Σ cos(2ω t_i)

    and the power is the least-squares fit quality of a sinusoid at that
    frequency:

        P(ω) = 1/(2σ²) · [ (Σ y cos ω(t-τ))² / Σ cos²ω(t-τ)
                         + (Σ y sin ω(t-τ))² / Σ sin²ω(t-τ) ]

    Returns ``(periods_hours, power)``, power normalised by the data variance.
    """
    low = min_period_h if min_period_h is not None else _CFG.min_period_h
    high = max_period_h if max_period_h is not None else _CFG.max_period_h
    steps = resolution if resolution is not None else _CFG.periodogram_resolution

    if times.size < 4:
        return np.array([]), np.array([])

    span = float(times.max() - times.min())
    if span <= 0.0:
        return np.array([]), np.array([])

    # Never search for periods longer than the observation window — a "cycle"
    # that has not completed once is not evidence of a cycle.
    high = min(high, span)
    if high <= low:
        return np.array([]), np.array([])

    centred = values - values.mean()
    variance = float(centred.var(ddof=1)) if centred.size > 1 else 0.0
    if variance <= 1e-12:
        # A perfectly constant series has no spectral peak — and that itself
        # is meaningful: it is maximal persistence, handled by the caller.
        return np.array([]), np.array([])

    periods = np.linspace(low, high, steps)
    omegas = 2.0 * np.pi / periods

    # Vectorised over (frequency, sample).
    wt = omegas[:, None] * times[None, :]

    sin_2wt = np.sin(2.0 * wt).sum(axis=1)
    cos_2wt = np.cos(2.0 * wt).sum(axis=1)
    tau = np.arctan2(sin_2wt, cos_2wt) / (2.0 * omegas)

    shifted = omegas[:, None] * (times[None, :] - tau[:, None])
    cos_s = np.cos(shifted)
    sin_s = np.sin(shifted)

    cc = (cos_s**2).sum(axis=1)
    ss = (sin_s**2).sum(axis=1)
    yc = (centred[None, :] * cos_s).sum(axis=1)
    ys = (centred[None, :] * sin_s).sum(axis=1)

    with np.errstate(divide="ignore", invalid="ignore"):
        power = 0.5 * (
            np.where(cc > 1e-12, yc**2 / cc, 0.0) + np.where(ss > 1e-12, ys**2 / ss, 0.0)
        ) / variance

    return periods, np.nan_to_num(power, nan=0.0, posinf=0.0)


def _false_alarm_probability(peak_power: float, n_samples: int) -> float:
    """
    Probability that a peak this strong arises from pure noise.

    Uses the standard independent-frequencies approximation
    ``FAP = 1 - (1 - e^{-P})^M`` with ``M ≈ n_samples`` trial frequencies.
    """
    if n_samples < 2 or peak_power <= 0.0:
        return 1.0
    exponent = max(-700.0, -float(peak_power))
    single = 1.0 - math.exp(exponent)
    return float(np.clip(1.0 - single ** max(1, n_samples), 0.0, 1.0))


# ---------------------------------------------------------------------------
# Analytic rhythm statistics (the interpretable signal)
# ---------------------------------------------------------------------------
# A source still burning after this many hours is being refuelled, which
# biomass in a single field cannot do. Two days is comfortably beyond the
# lifetime of a crop-residue or surface forest fire while being short enough
# that a genuine flare reaches full credit within one observation window.
PERSISTENCE_SATURATION_H = 48.0

# A dark interval longer than this counts as the source having gone out
# rather than merely having been unobserved. Set above the ~6-hour worst case
# between usable LEO passes so ordinary sampling gaps are not penalised.
DARK_GAP_H = 8.0

# Peak-to-median power ratio a Lomb-Scargle peak must clear before it is
# reported as a real cycle. The false-alarm probability alone is optimistic
# on long, densely sampled series, where noise reliably produces one tall
# spike somewhere in the search band.
MIN_PEAK_PROMINENCE = 6.0


def _rhythm_statistics(
    times: np.ndarray, frp: np.ndarray, cadence_h: float
) -> Dict[str, float]:
    """Persistence, regularity, burstiness and trend of the marked process."""
    stats: Dict[str, float] = {
        "persistence": 0.0,
        "regularity": 0.0,
        "burst": 0.0,
        "mean_intensity": 0.0,
        "trend": 0.0,
        "mtpp_intensity": 0.0,
        "span_h": 0.0,
    }
    if times.size == 0:
        return stats

    span = float(times.max() - times.min())
    stats["span_h"] = round(span, 3)
    active = frp > 0.5  # MW — below this a GEO pixel carries no usable signal
    stats["mean_intensity"] = round(float(frp[active].mean()) if active.any() else 0.0, 4)

    # --- Persistence -------------------------------------------------------
    # Persistence must measure how long the *source* stays alight, not how
    # densely the satellite happened to sample it. Sampling density alone
    # scores a 4-hour crop fire caught by seven consecutive GEO frames higher
    # than a refinery flare burning for a week, which is exactly backwards.
    #
    # Two independent factors:
    #   duration   — absolute length of thermal activity, saturating at
    #                PERSISTENCE_SATURATION_H. Biomass exhausts its fuel in
    #                hours; industrial combustion is refuelled indefinitely.
    #   continuity — the share of that window not lost to long dark gaps,
    #                which separates a genuinely continuous source from one
    #                that flared once, went out, and flared again days later.
    if active.sum() >= 1:
        active_times = times[active]
        active_span = float(active_times.max() - active_times.min())
        duration = float(np.clip(active_span / PERSISTENCE_SATURATION_H, 0.0, 1.0))

        continuity = 1.0
        if active_times.size >= 2 and active_span > 0.0:
            gaps = np.diff(active_times)
            dark = float(gaps[gaps > DARK_GAP_H].sum())
            continuity = float(np.clip(1.0 - dark / active_span, 0.0, 1.0))

        stats["persistence"] = round(float(np.clip(duration * continuity, 0.0, 1.0)), 4)

    if span > 0.0:
        stats["mtpp_intensity"] = round(float(active.sum() / max(span, 1e-6)), 4)

    # --- Regularity --------------------------------------------------------
    # Steadiness of the emission itself. Note this deliberately uses the FRP
    # values, not the inter-sample gaps: the gaps describe the satellite's
    # schedule, not the source's behaviour.
    if active.sum() >= 3:
        values = frp[active]
        mean = float(values.mean())
        if mean > 1e-6:
            cv = float(values.std(ddof=1) / mean)
            stats["regularity"] = round(float(np.clip(1.0 - cv, 0.0, 1.0)), 4)

        # --- Burstiness ----------------------------------------------------
        # A sharp excursion above the source's own baseline — the signature of
        # a flare spike or an accident rather than routine operation.
        median = float(np.median(values))
        if median > 1e-6:
            ratio = float(values.max() / median)
            stats["burst"] = round(float(np.clip((ratio - 1.0) / 4.0, 0.0, 1.0)), 4)

        # --- Trend ---------------------------------------------------------
        active_times = times[active]
        if active_times.size >= 3 and float(active_times.std()) > 1e-6:
            slope = float(np.polyfit(active_times, values, 1)[0])
            stats["trend"] = round(float(np.clip(slope / max(mean, 1e-6), -1.0, 1.0)), 4)

    return stats


# ---------------------------------------------------------------------------
# Neural ODE + continuous-time attention
# ---------------------------------------------------------------------------
def _deterministic_matrix(shape: Tuple[int, int], seed: int, scale: float = 0.5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    limit = scale * math.sqrt(6.0 / (shape[0] + shape[1]))
    return rng.uniform(-limit, limit, size=shape)


class NumpyContiFormer:
    """
    Explicit-RK4 continuous-time encoder, used when torch is unavailable.

    Latent dynamics between observations:

        dz/dt = tanh(W_dyn · z) · decay

    integrated with classical fourth-order Runge-Kutta over the true elapsed
    time, then a gated update at each observation. Finally a single pass of
    continuous-time attention pools the states with an ``exp(-Δt/τ)`` kernel.
    """

    def __init__(self, input_dim: int, latent_dim: int, seed: int) -> None:
        self.latent_dim = latent_dim
        self.w_dyn = _deterministic_matrix((latent_dim, latent_dim), seed, scale=0.3)
        self.w_in = _deterministic_matrix((input_dim, latent_dim), seed + 11)
        self.w_gate = _deterministic_matrix((latent_dim, latent_dim), seed + 23)
        self.w_query = _deterministic_matrix((latent_dim, latent_dim), seed + 31)
        self.w_key = _deterministic_matrix((latent_dim, latent_dim), seed + 43)

    def _drift(self, z: np.ndarray) -> np.ndarray:
        # Contractive drift keeps the flow stable over long gaps.
        return np.tanh(z @ self.w_dyn) - 0.1 * z

    def _integrate(self, z: np.ndarray, dt: float, steps: int) -> np.ndarray:
        if dt <= 0.0:
            return z
        h = dt / max(1, steps)
        for _ in range(max(1, steps)):
            k1 = self._drift(z)
            k2 = self._drift(z + 0.5 * h * k1)
            k3 = self._drift(z + 0.5 * h * k2)
            k4 = self._drift(z + h * k3)
            z = z + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
            # Bound the state so a long gap cannot blow it up.
            z = np.clip(z, -10.0, 10.0)
        return z

    def __call__(
        self, times: np.ndarray, marks: np.ndarray, tau_h: float, ode_steps: int
    ) -> np.ndarray:
        n = times.size
        z = np.zeros(self.latent_dim, dtype=np.float64)
        states = np.zeros((n, self.latent_dim), dtype=np.float64)

        for i in range(n):
            if i > 0:
                # Elapsed time is scaled so a multi-day gap stays numerically
                # sane while remaining monotone in real duration.
                dt = float(np.clip((times[i] - times[i - 1]) / max(tau_h, 1e-6), 0.0, 10.0))
                z = self._integrate(z, dt, ode_steps)
            update = np.tanh(marks[i] @ self.w_in)
            gate = 1.0 / (1.0 + np.exp(-(z @ self.w_gate)))
            z = gate * z + (1.0 - gate) * update
            states[i] = z

        # --- Continuous-time attention ------------------------------------
        queries = states @ self.w_query
        keys = states @ self.w_key
        logits = (queries @ keys.T) / math.sqrt(self.latent_dim)
        # Temporal kernel: relevance decays with real elapsed time.
        delta = np.abs(times[:, None] - times[None, :])
        logits = logits - delta / max(tau_h, 1e-6)
        logits = logits - logits.max(axis=1, keepdims=True)
        weights = np.exp(logits)
        weights = weights / np.maximum(weights.sum(axis=1, keepdims=True), 1e-12)
        attended = weights @ states

        pooled = attended.mean(axis=0)
        norm = np.linalg.norm(pooled)
        return pooled / norm if norm > 0.0 else pooled


class TorchContiFormer:
    """ContiFormer with a ``torchdiffeq`` Neural ODE flow."""

    _instance: Optional["TorchContiFormer"] = None

    def __init__(self, input_dim: int, latent_dim: int, seed: int) -> None:
        import torch
        import torch.nn as nn

        torch.manual_seed(seed)
        self._torch = torch
        self.latent_dim = latent_dim

        class ODEFunc(nn.Module):
            def __init__(self, dim: int) -> None:
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(dim, dim), nn.Tanh(), nn.Linear(dim, dim), nn.Tanh()
                )

            def forward(self, t, z):  # noqa: ANN001 - torchdiffeq signature
                return self.net(z) - 0.1 * z

        self.ode_func = ODEFunc(latent_dim).eval()
        self.encoder = nn.Linear(input_dim, latent_dim).eval()
        self.gate = nn.Linear(latent_dim, latent_dim).eval()
        self.attention = nn.MultiheadAttention(
            latent_dim, _CFG.attention_heads, batch_first=True
        ).eval()

    @classmethod
    def instance(cls, input_dim: int, latent_dim: int, seed: int) -> "TorchContiFormer":
        if cls._instance is None:
            cls._instance = cls(input_dim, latent_dim, seed)
        return cls._instance

    def __call__(
        self, times: np.ndarray, marks: np.ndarray, tau_h: float, ode_steps: int
    ) -> np.ndarray:
        torch = self._torch
        with torch.no_grad():
            mark_tensor = torch.tensor(marks, dtype=torch.float32)
            encoded = torch.tanh(self.encoder(mark_tensor))

            z = torch.zeros(self.latent_dim, dtype=torch.float32)
            states = []
            for i in range(times.size):
                if i > 0:
                    dt = float(np.clip((times[i] - times[i - 1]) / max(tau_h, 1e-6), 0.0, 10.0))
                    if dt > 1e-6:
                        grid = torch.linspace(0.0, dt, max(2, ode_steps))
                        z = odeint(self.ode_func, z, grid, method="rk4")[-1]
                        z = torch.clamp(z, -10.0, 10.0)
                gate = torch.sigmoid(self.gate(z))
                z = gate * z + (1.0 - gate) * encoded[i]
                states.append(z)

            sequence = torch.stack(states).unsqueeze(0)

            # Continuous-time bias: penalise attention across long real gaps.
            delta = np.abs(times[:, None] - times[None, :]) / max(tau_h, 1e-6)
            mask = torch.tensor(delta, dtype=torch.float32)
            attended, _ = self.attention(
                sequence, sequence, sequence, attn_mask=mask
            )

            pooled = attended.squeeze(0).mean(dim=0)
            pooled = torch.nn.functional.normalize(pooled, p=2.0, dim=0)
            return pooled.numpy().astype(np.float64)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_contiformer(
    lat: float,
    lng: float,
    cube: Optional[InsatCube] = None,
    extra_series: Optional[Sequence[Dict[str, Any]]] = None,
    event_id: Optional[str] = None,
) -> TemporalContext:
    """
    Stage 5 entry point: recover the operational rhythm of a thermal source.

    Never raises — a temporal failure degrades this modality only.
    """
    with stage_span(log, _STAGE, "contiformer_rhythm", event_id=event_id) as span:
        try:
            times, frp, brightness = build_event_sequence(
                lat, lng, cube=cube, extra_series=extra_series
            )
            span["events"] = int(times.size)

            if times.size < _CFG.min_events_for_rhythm:
                span["outcome"] = "insufficient_history"
                return TemporalContext(
                    embedding=[0.0] * _CFG.latent_dim,
                    event_count=int(times.size),
                    encoder="none",
                    status=StageStatus.SKIPPED,
                    notes=(
                        f"only {times.size} observations — at least "
                        f"{_CFG.min_events_for_rhythm} are needed to infer a rhythm"
                    ),
                )

            cadence_h = (
                (cube.revisit_minutes / 60.0)
                if cube is not None and cube.revisit_minutes
                else 0.5
            )
            stats = _rhythm_statistics(times, frp, cadence_h)

            # --- Periodicity via Lomb-Scargle -------------------------------
            periods, power = lomb_scargle(times, frp)
            dominant_period: Optional[float] = None
            periodicity = 0.0
            if periods.size and power.size:
                peak = int(np.argmax(power))
                peak_power = float(power[peak])
                fap = _false_alarm_probability(peak_power, int(times.size))

                # Two independent tests must agree before a cycle is claimed:
                # the peak must be statistically unlikely under noise (FAP),
                # and it must stand clearly above the rest of the spectrum
                # (prominence). Noise on a long series passes the first test
                # far too easily on its own.
                median_power = float(np.median(power))
                prominence = peak_power / max(median_power, 1e-9)
                significant = (fap < 0.01) and (prominence >= MIN_PEAK_PROMINENCE)

                periodicity = round(float(np.clip(1.0 - fap, 0.0, 1.0)), 4)
                if significant:
                    dominant_period = round(float(periods[peak]), 3)
                else:
                    # Statistically unconvincing: keep a token score so a weak
                    # hint is not reported as an established rhythm.
                    periodicity = round(min(periodicity, 0.35), 4)

                span["peak_power"] = round(peak_power, 4)
                span["prominence"] = round(prominence, 2)
                span["fap"] = round(fap, 6)

            # A perfectly steady source produces no spectral peak at all, but
            # continuous operation is itself strong industrial evidence. Credit
            # it through persistence + regularity instead of periodicity.
            if periods.size == 0 and stats["persistence"] > 0.8:
                periodicity = round(0.6 * stats["regularity"], 4)
                span["note"] = "constant emission — no spectral peak by construction"

            # --- Continuous-time encoding -----------------------------------
            marks = np.column_stack(
                [
                    np.log1p(np.maximum(frp, 0.0)),
                    np.clip((brightness - 280.0) / 120.0, -2.0, 4.0),
                    np.clip(np.gradient(frp) if frp.size > 1 else np.zeros_like(frp), -50.0, 50.0)
                    / 10.0,
                ]
            )

            encoder_name = "statistical"
            embedding = np.zeros(_CFG.latent_dim, dtype=np.float64)
            if _CFG.enabled:
                try:
                    if _TORCH and _TORCHDIFFEQ:
                        model = TorchContiFormer.instance(
                            marks.shape[1], _CFG.latent_dim, settings.random_seed
                        )
                        encoder_name = "contiformer_ode"
                    else:
                        model = NumpyContiFormer(
                            marks.shape[1], _CFG.latent_dim, settings.random_seed
                        )
                        encoder_name = "contiformer_numpy"
                    embedding = model(
                        times, marks, _CFG.attention_tau_h, _CFG.ode_solver_steps
                    )
                except Exception as exc:
                    span["encoder_error"] = str(exc)[:160]
                    log.warning(
                        "ContiFormer encoding failed, using statistical features: %s",
                        str(exc)[:160],
                        extra={"stage": _STAGE, "event_id": event_id},
                    )
                    encoder_name = "statistical"
                    base = np.array(
                        [
                            stats["persistence"],
                            periodicity,
                            stats["regularity"],
                            stats["burst"],
                            stats["trend"],
                        ]
                    )
                    embedding = np.resize(base, _CFG.latent_dim)

            # A cube reconstructed from LEO anchors cannot establish a genuine
            # rhythm, so the stage reports itself degraded and Stage 6 caps the
            # confidence it derives from this modality.
            degraded = cube is not None and cube.status is not StageStatus.OK
            status = StageStatus.FALLBACK if degraded else StageStatus.OK
            notes = ""
            if degraded:
                notes = (
                    f"temporal evidence derived from a {cube.source} GEO cube — "
                    "rhythm is indicative, not observed"
                )

            span["persistence"] = stats["persistence"]
            span["periodicity"] = periodicity
            span["period_h"] = dominant_period
            span["encoder"] = encoder_name

            return TemporalContext(
                embedding=[round(float(v), 6) for v in embedding],
                event_count=int(times.size),
                observation_span_h=stats["span_h"],
                persistence_score=stats["persistence"],
                periodicity_score=periodicity,
                dominant_period_h=dominant_period,
                rhythm_regularity=stats["regularity"],
                burst_score=stats["burst"],
                mean_intensity=stats["mean_intensity"],
                intensity_trend=stats["trend"],
                mtpp_intensity=stats["mtpp_intensity"],
                encoder=encoder_name,
                status=status,
                notes=notes,
            )

        except Exception as exc:
            span["outcome"] = "error"
            span["error"] = str(exc)[:200]
            log.exception("Stage 5 failed", extra={"stage": _STAGE, "event_id": event_id})
            return TemporalContext(
                embedding=[0.0] * _CFG.latent_dim,
                encoder="none",
                status=StageStatus.FAILED,
                notes=f"temporal encoder error: {str(exc)[:160]}",
            )


__all__ = [
    "run_contiformer",
    "build_event_sequence",
    "lomb_scargle",
    "NumpyContiFormer",
    "TorchContiFormer",
]
