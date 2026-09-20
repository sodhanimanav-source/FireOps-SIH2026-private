"""
STAGE 4 — Visual Semantic Memory (NASA/IBM Prithvi-EO-2.0)
===========================================================

What this stage answers
-----------------------
Thermodynamics (Stage 2) says *how hot*. Topology (Stage 3) says *what is
mapped nearby*. Neither says what the ground actually **looks like right now**,
and that matters for the two hardest cases:

* An OSM map can be years out of date. A new plant may be unmapped; a mapped
  one may be demolished.
* A burn scar and a concrete apron are both dark, both non-vegetated, and both
  sit next to industry.

The discriminator is *permanence*. Industrial infrastructure is concrete and
steel that looked the same last month and will look the same next month. A
burn scar is a sudden collapse in vegetation indices that regrows over weeks.
Separating the two needs a model with spatiotemporal memory.

Prithvi-EO-2.0
--------------
A geospatial foundation model trained by NASA and IBM on a global HLS
(Harmonised Landsat-Sentinel) archive. It is a temporal ViT masked
auto-encoder over six bands — Blue, Green, Red, NIR-narrow, SWIR-1, SWIR-2 —
which is precisely the band set that separates built-up surfaces from
vegetation and burn scars. Being self-supervised, it yields useful embeddings
of "what kind of place is this" **without any manual labelling**, which is the
property this pipeline needs.

Degradation
-----------
The model weights are ~1.2 GB and are fetched from the Hugging Face Hub on
first use. Where the hub is unreachable — an air-gapped deployment, a demo
laptop, a locked-down judging environment — the stage falls back to explicit
spectral index analysis (NDVI / NBR / NDBI) over the same bands. That fallback
computes real physical quantities from real pixels; it is weaker than the
foundation model but it is not a stub, and it flags itself as ``FALLBACK`` so
Stage 6 discounts it.
"""

from __future__ import annotations

import math
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.config import settings
from core.logging_utils import get_logger, stage_span
from core.schemas import StageStatus, VisionContext

log = get_logger("stage4.vision")

_STAGE = 4
_CFG = settings.vision

# Band indices inside the Prithvi HLS band order.
_BLUE, _GREEN, _RED, _NIR, _SWIR1, _SWIR2 = range(6)

_MODEL_LOCK = threading.Lock()
_MODEL_STATE: Dict[str, Any] = {"model": None, "loaded": False, "error": None}


# ---------------------------------------------------------------------------
# Model loading (lazy, cached, thread-safe)
# ---------------------------------------------------------------------------
def _load_prithvi() -> Tuple[Any, Optional[str]]:
    """
    Load Prithvi-EO-2.0 once per process.

    Returns ``(model, error)``. A failure is cached too — a locked-down
    environment must not re-attempt a 1.2 GB download for every anomaly in
    every polling cycle.
    """
    if _MODEL_STATE["loaded"]:
        return _MODEL_STATE["model"], _MODEL_STATE["error"]

    with _MODEL_LOCK:
        if _MODEL_STATE["loaded"]:
            return _MODEL_STATE["model"], _MODEL_STATE["error"]

        if not _CFG.enabled:
            _MODEL_STATE.update(loaded=True, model=None, error="disabled by configuration")
            return None, _MODEL_STATE["error"]

        try:
            import torch
            from transformers import AutoModel

            log.info(
                "Loading Prithvi-EO-2.0 foundation model (first call may download weights)",
                extra={"stage": _STAGE, "fields": {"model_id": _CFG.model_id}},
            )
            model = AutoModel.from_pretrained(
                _CFG.model_id,
                trust_remote_code=True,
                token=_CFG.hf_token,
            )
            model.eval()
            model.to(_CFG.device)

            _MODEL_STATE.update(loaded=True, model=model, error=None)
            log.info("Prithvi-EO-2.0 ready", extra={"stage": _STAGE})
            return model, None

        except Exception as exc:
            message = f"{type(exc).__name__}: {str(exc)[:200]}"
            _MODEL_STATE.update(loaded=True, model=None, error=message)
            log.warning(
                "Prithvi-EO-2.0 unavailable, using spectral-index fallback: %s",
                message,
                extra={"stage": _STAGE},
            )
            return None, message


def prithvi_is_available() -> bool:
    """Whether the foundation model is loaded and usable (for /api/ai-status)."""
    model, _ = _load_prithvi()
    return model is not None


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------
def _normalise_imagery(imagery: Any) -> Optional[np.ndarray]:
    """
    Coerce the many shapes imagery arrives in into ``(T, 6, H, W)`` float32.

    Accepted forms:
      * ``np.ndarray`` of shape (6,H,W) or (T,6,H,W)
      * ``{"frames": [...]}`` or ``{"bands": {...}}``
      * ``{"B02": array, "B03": array, ...}``
    """
    if imagery is None:
        return None

    if isinstance(imagery, np.ndarray):
        array = imagery.astype(np.float32)
        if array.ndim == 3:
            array = array[None, ...]
        return array if array.ndim == 4 and array.shape[1] >= 6 else None

    if isinstance(imagery, dict):
        if "frames" in imagery and isinstance(imagery["frames"], (list, tuple)):
            frames = [_normalise_imagery(f) for f in imagery["frames"]]
            frames = [f for f in frames if f is not None]
            if frames:
                return np.concatenate(frames, axis=0)
            return None

        band_source = imagery.get("bands", imagery)
        if isinstance(band_source, dict):
            stack: List[np.ndarray] = []
            for band_name in _CFG.bands:
                value = band_source.get(band_name)
                if value is None:
                    return None
                stack.append(np.asarray(value, dtype=np.float32))
            try:
                array = np.stack(stack, axis=0)
            except ValueError:
                return None
            if array.ndim == 3:
                array = array[None, ...]
            return array

    if isinstance(imagery, (list, tuple)):
        return _normalise_imagery(np.asarray(imagery, dtype=np.float32))

    return None


def _resize_nearest(array: np.ndarray, size: int) -> np.ndarray:
    """Nearest-neighbour resize to the model's expected input size."""
    _, _, height, width = array.shape
    if height == size and width == size:
        return array
    rows = np.clip((np.arange(size) * height // max(1, size)), 0, height - 1)
    cols = np.clip((np.arange(size) * width // max(1, size)), 0, width - 1)
    return array[:, :, rows][:, :, :, cols]


# ---------------------------------------------------------------------------
# Spectral indices — the interpretable signal and the fallback encoder
# ---------------------------------------------------------------------------
def compute_spectral_indices(array: np.ndarray) -> Dict[str, float]:
    """
    Physical indices over the anomaly footprint.

    NDVI  (NIR-Red)/(NIR+Red)      vegetation vigour
    NBR   (NIR-SWIR2)/(NIR+SWIR2)  burn severity — collapses over fresh scars
    NDBI  (SWIR1-NIR)/(SWIR1+NIR)  built-up surfaces — concrete, metal, asphalt
    """
    def safe_ratio(a: np.ndarray, b: np.ndarray) -> float:
        denominator = a + b
        valid = np.abs(denominator) > 1e-6
        if not valid.any():
            return 0.0
        return float(np.mean((a[valid] - b[valid]) / denominator[valid]))

    # Average over time for the scene-level indices.
    scene = array.mean(axis=0)
    nir, red = scene[_NIR], scene[_RED]
    swir1, swir2 = scene[_SWIR1], scene[_SWIR2]

    ndvi = safe_ratio(nir, red)
    nbr = safe_ratio(nir, swir2)
    ndbi = safe_ratio(swir1, nir)

    # Temporal stability: how little the scene changes across frames. A
    # permanent installation is static; a burn scar is a step change.
    if array.shape[0] > 1:
        per_frame = array.mean(axis=(2, 3))            # (T, C)
        variation = np.std(per_frame, axis=0)
        magnitude = np.abs(np.mean(per_frame, axis=0)) + 1e-6
        stability = float(np.clip(1.0 - np.mean(variation / magnitude), 0.0, 1.0))
    else:
        stability = 0.5  # unknown with a single frame

    return {"ndvi": ndvi, "nbr": nbr, "ndbi": ndbi, "stability": stability}


def _scores_from_indices(indices: Dict[str, float]) -> Tuple[float, float]:
    """
    Turn spectral indices into the two decision-relevant scores.

    The subtle part is that **NDBI alone cannot separate charred ground from
    concrete**. Both are non-vegetated and both are SWIR-bright relative to
    NIR, so a naive built-up index scores a fresh burn scar as industrial —
    exactly the error this stage exists to prevent.

    What separates them is the *magnitude* of the NBR collapse. Char is an
    extremely strong SWIR-2 absorber-turned-emitter and drives NBR sharply
    negative (< -0.3); concrete and steel sit only mildly negative (~ -0.05
    to -0.1). So burn evidence is computed first, and permanence is then
    explicitly suppressed by it.

    Permanence is also gated on the surface being non-vegetated: a static
    scene is only evidence of built infrastructure if there is something built
    there. A stable forest is stable, not permanent infrastructure.
    """
    ndvi = indices["ndvi"]
    nbr = indices["nbr"]
    ndbi = indices["ndbi"]
    stability = indices["stability"]

    # --- Burn evidence first ----------------------------------------------
    # Deep NBR collapse is the char signature; mild negatives are ordinary
    # dry or built surfaces and must not register.
    burn = float(np.clip((-nbr - 0.05) / 0.45, 0.0, 1.0))
    transient = 1.0 - stability
    scar = float(np.clip(0.65 * burn + 0.35 * transient, 0.0, 1.0))

    # --- Permanence, gated on being genuinely non-vegetated ---------------
    built = float(np.clip(ndbi / 0.25, 0.0, 1.0))
    bare = 1.0 - float(np.clip((ndvi + 0.1) / 0.6, 0.0, 1.0))
    surface = 0.55 * built + 0.45 * bare
    # A static scene reinforces permanence but cannot create it on its own.
    raw_permanent = surface * (0.5 + 0.5 * stability)
    # Suppress anything that carries a strong char signature.
    permanent = float(np.clip(raw_permanent * (1.0 - 0.85 * scar), 0.0, 1.0))

    return round(permanent, 4), round(scar, 4)


def _scores_from_legacy_deltas(deltas: Dict[str, Any]) -> Optional[Tuple[float, float, Dict[str, float]]]:
    """
    Accept the ``spectral_deltas`` dict the existing ``satellite_pipeline``
    produces (``dNBR``, ``dSWIR``, ``dNDVI``) so the new stage stays
    compatible with the repository's earlier change-detection output.
    """
    try:
        d_nbr = float(deltas.get("dNBR", 0.0))
        d_ndvi = float(deltas.get("dNDVI", 0.0))
        d_swir = float(deltas.get("dSWIR", 0.0))
    except (TypeError, ValueError):
        return None

    # A large positive dNBR with a large negative dNDVI is the classic
    # vegetation burn-scar signature.
    scar = float(np.clip(0.6 * np.clip(d_nbr / 0.6, 0.0, 1.0)
                         + 0.4 * np.clip(-d_ndvi / 0.5, 0.0, 1.0), 0.0, 1.0))
    # Persistent SWIR brightness with little vegetation change reads as built-up.
    permanent = float(np.clip(0.6 * np.clip(d_swir, 0.0, 1.0)
                              + 0.4 * (1.0 - scar), 0.0, 1.0))
    indices = {"ndvi": d_ndvi, "nbr": d_nbr, "ndbi": d_swir, "stability": 1.0 - scar}
    return round(permanent, 4), round(scar, 4), indices


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------
def _project(vector: np.ndarray, dim: int) -> List[float]:
    """
    Reduce a foundation-model embedding to the pipeline's fusion width with a
    fixed random projection (Johnson-Lindenstrauss), which preserves relative
    distances without needing a trained projection head.
    """
    vector = np.asarray(vector, dtype=np.float64).ravel()
    if vector.size == 0:
        return [0.0] * dim
    if vector.size == dim:
        reduced = vector
    else:
        rng = np.random.default_rng(settings.random_seed)
        projection = rng.normal(0.0, 1.0 / math.sqrt(dim), size=(vector.size, dim))
        reduced = vector @ projection
    norm = np.linalg.norm(reduced)
    if norm > 0.0:
        reduced = reduced / norm
    return [round(float(v), 6) for v in reduced]


def _embedding_from_indices(indices: Dict[str, float], dim: int) -> List[float]:
    """Deterministic embedding built from the physical indices."""
    base = np.array(
        [
            indices["ndvi"],
            indices["nbr"],
            indices["ndbi"],
            indices["stability"],
            indices["ndvi"] * indices["ndbi"],
            indices["nbr"] * indices["stability"],
        ],
        dtype=np.float64,
    )
    rng = np.random.default_rng(settings.random_seed + 4)
    projection = rng.normal(0.0, 1.0 / math.sqrt(dim), size=(base.size, dim))
    reduced = np.tanh(base @ projection)
    norm = np.linalg.norm(reduced)
    if norm > 0.0:
        reduced = reduced / norm
    return [round(float(v), 6) for v in reduced]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_prithvi_eo(
    imagery: Any = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    event_id: Optional[str] = None,
) -> VisionContext:
    """
    Stage 4 entry point: spatiotemporal semantics for the anomaly footprint.

    Never raises — a vision failure degrades this modality only.
    """
    with stage_span(log, _STAGE, "prithvi_embedding", event_id=event_id) as span:
        try:
            # --- Legacy spectral-delta input --------------------------------
            if isinstance(imagery, dict) and "spectral_deltas" in imagery:
                legacy = _scores_from_legacy_deltas(imagery["spectral_deltas"])
                if legacy is not None:
                    permanent, scar, indices = legacy
                    span["encoder"] = "spectral_deltas"
                    span["permanent"] = permanent
                    return VisionContext(
                        embedding=_embedding_from_indices(indices, _CFG.embedding_dim),
                        permanent_structure_score=permanent,
                        burn_scar_score=scar,
                        vegetation_index=round(indices["ndvi"], 4),
                        built_up_index=round(indices["ndbi"], 4),
                        burn_index=round(indices["nbr"], 4),
                        temporal_stability=round(indices["stability"], 4),
                        frames_used=1,
                        encoder="spectral_deltas",
                        status=StageStatus.FALLBACK,
                        notes="derived from bi-temporal change deltas, not from raw imagery",
                    )

            array = _normalise_imagery(imagery)

            # --- No imagery at all ------------------------------------------
            if array is None:
                span["outcome"] = "no_imagery"
                return VisionContext(
                    embedding=[0.0] * _CFG.embedding_dim,
                    encoder="none",
                    status=StageStatus.SKIPPED,
                    notes=(
                        "no imagery supplied — connect a Sentinel-2/HLS tile "
                        "source to enable Stage 4"
                    ),
                )

            array = _resize_nearest(array[:, :6], _CFG.image_size)
            indices = compute_spectral_indices(array)
            permanent, scar = _scores_from_indices(indices)
            span["frames"] = int(array.shape[0])

            # --- Foundation model path --------------------------------------
            model, load_error = _load_prithvi()
            if model is not None:
                try:
                    import torch

                    with torch.no_grad():
                        tensor = torch.tensor(array, dtype=torch.float32, device=_CFG.device)
                        # Prithvi expects (B, C, T, H, W).
                        tensor = tensor.permute(1, 0, 2, 3).unsqueeze(0)
                        output = model(tensor)

                    hidden = getattr(output, "last_hidden_state", output)
                    if isinstance(hidden, (tuple, list)):
                        hidden = hidden[0]
                    pooled = hidden.reshape(hidden.shape[0], -1, hidden.shape[-1]).mean(axis=1)
                    embedding = _project(pooled.cpu().numpy(), _CFG.embedding_dim)

                    span["encoder"] = "prithvi_eo_2"
                    span["permanent"] = permanent
                    return VisionContext(
                        embedding=embedding,
                        permanent_structure_score=permanent,
                        burn_scar_score=scar,
                        vegetation_index=round(indices["ndvi"], 4),
                        built_up_index=round(indices["ndbi"], 4),
                        burn_index=round(indices["nbr"], 4),
                        temporal_stability=round(indices["stability"], 4),
                        frames_used=int(array.shape[0]),
                        model_id=_CFG.model_id,
                        encoder="prithvi_eo_2",
                        status=StageStatus.OK,
                    )
                except Exception as exc:
                    span["inference_error"] = str(exc)[:160]
                    log.warning(
                        "Prithvi inference failed, using spectral indices: %s",
                        str(exc)[:160],
                        extra={"stage": _STAGE, "event_id": event_id},
                    )

            # --- Spectral-index fallback ------------------------------------
            span["encoder"] = "spectral_heuristic"
            span["permanent"] = permanent
            span["outcome"] = "fallback"
            return VisionContext(
                embedding=_embedding_from_indices(indices, _CFG.embedding_dim),
                permanent_structure_score=permanent,
                burn_scar_score=scar,
                vegetation_index=round(indices["ndvi"], 4),
                built_up_index=round(indices["ndbi"], 4),
                burn_index=round(indices["nbr"], 4),
                temporal_stability=round(indices["stability"], 4),
                frames_used=int(array.shape[0]),
                encoder="spectral_heuristic",
                status=StageStatus.FALLBACK,
                notes=load_error or "foundation model unavailable; NDVI/NBR/NDBI analysis used",
            )

        except Exception as exc:
            span["outcome"] = "error"
            span["error"] = str(exc)[:200]
            log.exception("Stage 4 failed", extra={"stage": _STAGE, "event_id": event_id})
            return VisionContext(
                embedding=[0.0] * _CFG.embedding_dim,
                encoder="none",
                status=StageStatus.FAILED,
                notes=f"vision encoder error: {str(exc)[:160]}",
            )


__all__ = [
    "run_prithvi_eo",
    "compute_spectral_indices",
    "prithvi_is_available",
]
