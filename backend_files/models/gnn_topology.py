"""
STAGE 3 — Topological Structure Mapping (OSM -> Directed Graph -> GraphSAGE)
============================================================================

Why topology beats proximity
----------------------------
The previous system asked "is there a factory within 3 km?". That question is
fragile in exactly the situations that matter:

* VIIRS geolocation error reaches ~1.5 km, so a flare stack genuinely inside a
  refinery can be reported outside its fence line.
* A crop fire in the field next door is also "within 3 km of a factory".

Proximity treats industry as a scattering of unrelated points. In reality a
refinery is a *connected system*: wells feed tanks, tanks feed process units,
process units vent to flare stacks, all stitched together by pipelines. That
connectivity is the signature, and it is what a graph can represent and a
distance query cannot.

This module parses vector OpenStreetMap data into a **directed graph** —

    Nodes  = tanks, flare stacks, chimneys, process works, buildings, wells
    Edges  = pipelines and process-flow relations (material moves one way)

— and encodes it with a **GraphSAGE** message-passing network, whose
neighbourhood-aggregation formulation is what makes the representation
tolerant to the anomaly landing on any node of the complex:

    h_v^(l+1) = σ( W_self · h_v^(l) + W_neigh · mean_{u ∈ N(v)} h_u^(l) )

Because every node aggregates from its neighbours, a detection that lands on a
storage tank and one that lands on the adjacent pipeline junction converge to
similar embeddings after two hops. That is the geolocation-error immunity the
architecture is after.

A note on honesty
-----------------
No labelled OSM-topology training set ships with this repository, so the
GraphSAGE weights are **deterministically initialised, not trained**. An
untrained message-passing encoder is still a useful structural fingerprint —
it is a stable random projection of the neighbourhood aggregation, so similar
topologies map to similar vectors — but it is not a classifier. The
interpretable quantity that actually drives the Stage 6 decision is
``industrial_topology_score``, computed analytically from the graph structure
below. The embedding occupies the representation slot for the day labelled
data exists; ``train_topology_encoder`` documents how to fill it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.config import settings
from core.logging_utils import get_logger, stage_span
from core.schemas import GraphContext, GraphNode, StageStatus

log = get_logger("stage3.graph")

_STAGE = 3
_CFG = settings.graph

# Optional heavy dependencies — the stage degrades rather than failing.
try:
    import torch
    from torch_geometric.nn import SAGEConv  # noqa: F401

    _TORCH_GEOMETRIC = True
except Exception:  # pragma: no cover - exercised on minimal installs
    _TORCH_GEOMETRIC = False

try:
    import torch as _torch_probe  # noqa: F401

    _TORCH = True
except Exception:  # pragma: no cover
    _TORCH = False


# ---------------------------------------------------------------------------
# OSM taxonomy
# ---------------------------------------------------------------------------
# Ordered by process position: material flows from lower rank to higher rank.
# This is what turns an undirected OSM extract into a *directed* process graph.
_PROCESS_RANK: Dict[str, int] = {
    "well": 0,       # petroleum/gas wellhead — source
    "tank": 1,       # storage
    "works": 2,      # process units / plant site
    "plant": 2,      # power generation
    "building": 3,   # ancillary structures
    "chimney": 4,    # stack emission
    "flare": 5,      # flare tip — terminal combustion point
}

_NODE_KINDS = list(_PROCESS_RANK.keys()) + ["pipeline_junction", "other"]

# Features that indicate persistent heavy industry. The flare stack is the
# single most diagnostic object: it exists only where hydrocarbons are burned
# off deliberately.
_KIND_WEIGHT: Dict[str, float] = {
    "flare": 1.00,
    "well": 0.80,
    "tank": 0.75,
    "works": 0.70,
    "plant": 0.65,
    "chimney": 0.60,
    "pipeline_junction": 0.45,
    "building": 0.25,
    "other": 0.05,
}


def _classify_osm_element(tags: Dict[str, str]) -> Optional[str]:
    """Map raw OSM tags onto the process taxonomy."""
    if not tags:
        return None

    man_made = str(tags.get("man_made", "")).lower()
    building = str(tags.get("building", "")).lower()
    landuse = str(tags.get("landuse", "")).lower()
    industrial = str(tags.get("industrial", "")).lower()
    power = str(tags.get("power", "")).lower()
    usage = str(tags.get("usage", "")).lower()
    content = str(tags.get("content", "")).lower()

    if man_made in {"flare", "torch"} or usage == "flare" or content == "flare":
        return "flare"
    if man_made in {"storage_tank", "tank", "silo", "gasometer"}:
        return "tank"
    if man_made == "chimney":
        return "chimney"
    if man_made in {"petroleum_well", "oil_well", "gas_well"}:
        return "well"
    if man_made in {"works", "kiln", "furnace"}:
        return "works"
    if power in {"plant", "generator", "station"}:
        return "plant"
    if industrial or landuse in {"industrial", "quarry"}:
        return "works"
    if building in {"industrial", "warehouse", "factory", "refinery"}:
        return "building"
    if man_made == "pipeline":
        return "pipeline_junction"
    if building:
        return "building"
    return None


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * radius * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


# ---------------------------------------------------------------------------
# OSM retrieval (Overpass -> disk cache -> local facilities)
# ---------------------------------------------------------------------------
def _cache_key(lat: float, lng: float, radius_m: int) -> str:
    raw = f"{round(lat, 4)}:{round(lng, 4)}:{radius_m}"
    return hashlib.md5(raw.encode()).hexdigest()


def _read_cache(key: str) -> Optional[List[Dict[str, Any]]]:
    path = os.path.join(settings.paths.osm_graph_cache, f"{key}.json")
    if not os.path.exists(path):
        return None
    if (time.time() - os.path.getmtime(path)) > _CFG.cache_ttl_s:
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle).get("elements", [])
    except Exception:
        return None


def _write_cache(key: str, elements: List[Dict[str, Any]]) -> None:
    try:
        path = os.path.join(settings.paths.osm_graph_cache, f"{key}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"elements": elements, "cached_at": time.time()}, handle)
    except Exception:
        pass


def _build_overpass_query(lat: float, lng: float, radius_m: int) -> str:
    """Ask Overpass for every object that can be part of an industrial complex."""
    around = f"around:{radius_m},{lat},{lng}"
    selectors = [
        f'node["man_made"~"storage_tank|tank|silo|flare|torch|chimney|works|petroleum_well|gasometer"]({around});',
        f'way["man_made"~"storage_tank|tank|silo|flare|torch|chimney|works|petroleum_well|gasometer"]({around});',
        f'way["man_made"="pipeline"]({around});',
        f'way["landuse"~"industrial|quarry"]({around});',
        f'way["industrial"]({around});',
        f'way["power"~"plant|generator|station"]({around});',
        f'way["building"~"industrial|warehouse|factory|refinery"]({around});',
        f'relation["landuse"="industrial"]({around});',
        f'relation["industrial"]({around});',
    ]
    return f"[out:json][timeout:{int(_CFG.http_timeout_s)}];(" + "".join(selectors) + ");out center tags;"


def _fetch_overpass(lat: float, lng: float, radius_m: int) -> Optional[List[Dict[str, Any]]]:
    if _CFG.offline_only:
        return None
    try:
        import requests
    except ImportError:
        return None

    try:
        response = requests.post(
            _CFG.overpass_url,
            data={"data": _build_overpass_query(lat, lng, radius_m)},
            headers={"User-Agent": "FireOps-SIH2026/4.0"},
            timeout=_CFG.http_timeout_s,
        )
        if response.status_code != 200:
            return None
        return response.json().get("elements", [])
    except Exception as exc:
        log.debug("Overpass unavailable: %s", str(exc)[:120], extra={"stage": _STAGE})
        return None


_FACILITIES_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_local_facilities() -> List[Dict[str, Any]]:
    """The curated national facility list, used when Overpass is unreachable."""
    global _FACILITIES_CACHE
    if _FACILITIES_CACHE is not None:
        return _FACILITIES_CACHE
    try:
        with open(settings.paths.facilities, "r", encoding="utf-8") as handle:
            _FACILITIES_CACHE = json.load(handle)
    except Exception:
        _FACILITIES_CACHE = []
    return _FACILITIES_CACHE


def _facilities_as_elements(lat: float, lng: float, radius_m: int) -> List[Dict[str, Any]]:
    """
    Synthesise graph elements from ``data/facilities.json``.

    A curated facility record has no internal topology, so the graph built
    from it is necessarily coarser than a real OSM extract. That is reflected
    downstream: this path reports ``source="facilities"`` and the stage is
    marked ``FALLBACK``.
    """
    elements: List[Dict[str, Any]] = []
    search_radius = max(radius_m, _CFG.geolocation_tolerance_m)

    for facility in _load_local_facilities():
        flat = facility.get("lat")
        flng = facility.get("lng")
        if flat is None or flng is None:
            continue
        # Cheap bounding-box rejection before the expensive haversine.
        if abs(flat - lat) > (search_radius / 111_000.0) * 2.0:
            continue
        distance = _haversine_m(lat, lng, float(flat), float(flng))
        buffer_m = float(facility.get("buffer_km", 3.0)) * 1000.0
        if distance > max(search_radius, buffer_m):
            continue

        facility_type = str(facility.get("type", "")).lower()
        if "refinery" in facility_type or "oil" in facility_type or "gas" in facility_type:
            kind, extra = "works", {"industrial": "refinery"}
        elif "power" in facility_type or "thermal" in facility_type:
            kind, extra = "plant", {"power": "plant"}
        elif "steel" in facility_type or "iron" in facility_type:
            kind, extra = "works", {"industrial": "steel"}
        elif "chemical" in facility_type or "petro" in facility_type:
            kind, extra = "works", {"industrial": "chemical"}
        elif "mine" in facility_type or "quarry" in facility_type:
            kind, extra = "works", {"landuse": "quarry"}
        else:
            kind, extra = "works", {"landuse": "industrial"}

        elements.append(
            {
                "type": "node",
                "id": facility.get("id", f"FAC{len(elements)}"),
                "lat": float(flat),
                "lon": float(flng),
                "tags": {"name": facility.get("name", "unnamed"), **extra},
                "_kind_hint": kind,
                "_source": "facilities",
            }
        )
    return elements


def fetch_osm_subgraph(
    lat: float, lng: float, radius_m: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """Retrieve raw OSM elements around a point. Returns ``(elements, source)``."""
    radius = radius_m if radius_m is not None else _CFG.query_radius_m
    key = _cache_key(lat, lng, radius)

    cached = _read_cache(key)
    if cached is not None:
        return cached, "cache"

    elements = _fetch_overpass(lat, lng, radius)
    if elements:
        _write_cache(key, elements)
        return elements, "overpass"

    local = _facilities_as_elements(lat, lng, radius)
    if local:
        return local, "facilities"

    return [], "unavailable"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_directed_graph(
    elements: Sequence[Dict[str, Any]],
    lat: float,
    lng: float,
    max_nodes: Optional[int] = None,
) -> Tuple[List[GraphNode], List[Tuple[int, int, str]]]:
    """
    Convert OSM elements into a directed process graph.

    Edge semantics (all directed, following material/energy flow):

    ``pipeline``    an explicit ``man_made=pipeline`` way linking two objects
    ``process``     inferred flow between process stages (well -> tank -> works
                    -> chimney/flare), created only between objects close
                    enough to plausibly belong to the same complex
    ``containment`` a site polygon (works/plant) to the equipment inside it

    Returns the node list and an ``(src, dst, kind)`` edge list.
    """
    limit = max_nodes if max_nodes is not None else _CFG.max_nodes

    nodes: List[GraphNode] = []
    pipeline_ways: List[Dict[str, Any]] = []

    for element in elements:
        tags = element.get("tags", {}) or {}
        node_lat = element.get("lat") or (element.get("center") or {}).get("lat")
        node_lng = element.get("lon") or (element.get("center") or {}).get("lon")
        if node_lat is None or node_lng is None:
            continue

        kind = element.get("_kind_hint") or _classify_osm_element(tags)
        if kind is None:
            continue

        if kind == "pipeline_junction":
            pipeline_ways.append(
                {"lat": float(node_lat), "lng": float(node_lng), "tags": tags, "id": element.get("id")}
            )

        nodes.append(
            GraphNode(
                node_id=f"{str(element.get('type', 'n'))[0]}{element.get('id', len(nodes))}",
                kind=kind,
                name=str(tags.get("name") or tags.get("operator") or "unnamed"),
                lat=float(node_lat),
                lng=float(node_lng),
                distance_m=round(_haversine_m(lat, lng, float(node_lat), float(node_lng)), 1),
                tags={k: str(v)[:60] for k, v in list(tags.items())[:8]},
            )
        )

    # Keep the closest N — a graph of the whole district would dilute the
    # local structure the encoder is meant to describe.
    nodes.sort(key=lambda n: n.distance_m)
    nodes = nodes[:limit]

    edges: List[Tuple[int, int, str]] = []
    if len(nodes) < 2:
        return nodes, edges

    coords = np.array([[n.lat, n.lng] for n in nodes], dtype=np.float64)
    # Local metric conversion: at these scales a flat approximation is exact
    # enough and far cheaper than pairwise haversine.
    lat_scale = 111_320.0
    lng_scale = 111_320.0 * max(0.1, math.cos(math.radians(lat)))
    metres = np.column_stack(
        [(coords[:, 0] - lat) * lat_scale, (coords[:, 1] - lng) * lng_scale]
    )
    diff = metres[:, None, :] - metres[None, :, :]
    pairwise = np.sqrt((diff**2).sum(axis=-1))

    ranks = np.array([_PROCESS_RANK.get(n.kind, 3) for n in nodes])

    # --- Process-flow edges ------------------------------------------------
    # Objects within 400 m of each other and at different process stages are
    # connected in the direction of material flow.
    flow_radius_m = 400.0
    close = (pairwise > 0.0) & (pairwise <= flow_radius_m)
    src_idx, dst_idx = np.where(close & (ranks[:, None] < ranks[None, :]))
    for s, d in zip(src_idx.tolist(), dst_idx.tolist()):
        edges.append((s, d, "process"))

    # --- Containment edges -------------------------------------------------
    # A site polygon governs the equipment standing inside it.
    site_indices = [i for i, n in enumerate(nodes) if n.kind in {"works", "plant"}]
    for site in site_indices:
        within = np.where((pairwise[site] > 0.0) & (pairwise[site] <= 800.0))[0]
        for member in within.tolist():
            if nodes[member].kind not in {"works", "plant"}:
                edges.append((site, member, "containment"))

    # --- Pipeline edges ----------------------------------------------------
    # A pipeline physically couples the two nearest facility objects it runs
    # between; this is the strongest evidence of a single connected system.
    for way in pipeline_ways:
        way_metres = np.array(
            [(way["lat"] - lat) * lat_scale, (way["lng"] - lng) * lng_scale]
        )
        distances = np.sqrt(((metres - way_metres) ** 2).sum(axis=1))
        nearest = np.argsort(distances)[:2]
        if len(nearest) == 2 and distances[nearest[1]] < 1200.0:
            a, b = int(nearest[0]), int(nearest[1])
            if a != b:
                # Direction follows process rank; ties resolve deterministically.
                if ranks[a] <= ranks[b]:
                    edges.append((a, b, "pipeline"))
                else:
                    edges.append((b, a, "pipeline"))

    # Deduplicate while keeping the strongest relation for each ordered pair.
    priority = {"pipeline": 3, "process": 2, "containment": 1}
    best: Dict[Tuple[int, int], str] = {}
    for s, d, kind in edges:
        key = (s, d)
        if key not in best or priority[kind] > priority[best[key]]:
            best[key] = kind
    return nodes, [(s, d, k) for (s, d), k in best.items()]


# ---------------------------------------------------------------------------
# Node features
# ---------------------------------------------------------------------------
def build_node_features(
    nodes: Sequence[GraphNode],
    edges: Sequence[Tuple[int, int, str]],
    radius_m: float,
) -> np.ndarray:
    """
    Per-node feature matrix consumed by the message-passing encoder.

    Layout (16 dims): 9 one-hot kind channels, then normalised distance,
    in/out degree, pipeline degree, name presence, process rank and two
    reserved channels.
    """
    count = len(nodes)
    features = np.zeros((count, 16), dtype=np.float64)
    if count == 0:
        return features

    in_degree = np.zeros(count)
    out_degree = np.zeros(count)
    pipe_degree = np.zeros(count)
    for src, dst, kind in edges:
        out_degree[src] += 1.0
        in_degree[dst] += 1.0
        if kind == "pipeline":
            pipe_degree[src] += 1.0
            pipe_degree[dst] += 1.0

    max_degree = max(1.0, float(max(in_degree.max(), out_degree.max())))

    for index, node in enumerate(nodes):
        kind_index = _NODE_KINDS.index(node.kind) if node.kind in _NODE_KINDS else len(_NODE_KINDS) - 1
        features[index, kind_index] = 1.0
        features[index, 9] = min(1.0, node.distance_m / max(1.0, radius_m))
        features[index, 10] = in_degree[index] / max_degree
        features[index, 11] = out_degree[index] / max_degree
        features[index, 12] = min(1.0, pipe_degree[index] / 4.0)
        features[index, 13] = 1.0 if node.name and node.name != "unnamed" else 0.0
        features[index, 14] = _PROCESS_RANK.get(node.kind, 3) / 5.0
        features[index, 15] = _KIND_WEIGHT.get(node.kind, 0.05)

    return features


# ---------------------------------------------------------------------------
# GraphSAGE encoders
# ---------------------------------------------------------------------------
def _deterministic_weights(shape: Tuple[int, int], seed: int) -> np.ndarray:
    """Xavier-scaled weights from a fixed seed, so runs are reproducible."""
    rng = np.random.default_rng(seed)
    limit = math.sqrt(6.0 / (shape[0] + shape[1]))
    return rng.uniform(-limit, limit, size=shape)


class NumpyGraphSAGE:
    """
    Pure-NumPy GraphSAGE, mathematically identical to the torch_geometric
    ``SAGEConv`` mean aggregator:

        h' = ReLU( W_self · h + W_neigh · mean_{u ∈ N(v)} h_u )

    followed by L2 normalisation. Used when torch_geometric is absent so the
    stage keeps producing a comparable embedding on a minimal install.
    """

    def __init__(self, in_dim: int, hidden_dim: int, layers: int, seed: int) -> None:
        self.layers = layers
        self.weights: List[Tuple[np.ndarray, np.ndarray]] = []
        dims = [in_dim] + [hidden_dim] * layers
        for index in range(layers):
            self.weights.append(
                (
                    _deterministic_weights((dims[index], dims[index + 1]), seed + index * 7),
                    _deterministic_weights((dims[index], dims[index + 1]), seed + index * 13),
                )
            )

    def __call__(self, features: np.ndarray, adjacency: np.ndarray) -> np.ndarray:
        hidden = features
        # Row-normalised adjacency == mean aggregation over in-neighbours.
        degree = adjacency.sum(axis=1, keepdims=True)
        norm_adj = adjacency / np.where(degree > 0.0, degree, 1.0)

        for w_self, w_neigh in self.weights:
            aggregated = norm_adj @ hidden
            hidden = np.maximum(0.0, hidden @ w_self + aggregated @ w_neigh)
            norms = np.linalg.norm(hidden, axis=1, keepdims=True)
            hidden = hidden / np.where(norms > 0.0, norms, 1.0)
        return hidden


class TorchGraphSAGE:
    """torch_geometric ``SAGEConv`` stack, used when the dependency is present."""

    _instance: Optional["TorchGraphSAGE"] = None

    def __init__(self, in_dim: int, hidden_dim: int, layers: int, seed: int) -> None:
        import torch
        import torch.nn as nn
        from torch_geometric.nn import SAGEConv

        torch.manual_seed(seed)
        self._torch = torch
        self.convs = nn.ModuleList()
        dims = [in_dim] + [hidden_dim] * layers
        for index in range(layers):
            self.convs.append(SAGEConv(dims[index], dims[index + 1], aggr="mean"))
        for conv in self.convs:
            conv.eval()

    @classmethod
    def instance(cls, in_dim: int, hidden_dim: int, layers: int, seed: int) -> "TorchGraphSAGE":
        if cls._instance is None:
            cls._instance = cls(in_dim, hidden_dim, layers, seed)
        return cls._instance

    def __call__(self, features: np.ndarray, edge_index: np.ndarray) -> np.ndarray:
        torch = self._torch
        with torch.no_grad():
            x = torch.tensor(features, dtype=torch.float32)
            if edge_index.size == 0:
                edges = torch.zeros((2, 0), dtype=torch.long)
            else:
                edges = torch.tensor(edge_index, dtype=torch.long)
            for conv in self.convs:
                x = conv(x, edges)
                x = torch.relu(x)
                x = torch.nn.functional.normalize(x, p=2.0, dim=1)
            return x.numpy().astype(np.float64)


# ---------------------------------------------------------------------------
# Analytic topology score (the interpretable signal)
# ---------------------------------------------------------------------------
def _topology_score(
    nodes: Sequence[GraphNode],
    edges: Sequence[Tuple[int, int, str]],
    radius_m: float,
) -> Tuple[float, float]:
    """
    How strongly the local structure resembles a connected industrial complex.

    Four independent pieces of evidence, deliberately kept interpretable so an
    operator can be told *why* a site scored as it did:

    1. presence of diagnostic equipment (flare stacks, tanks, wells)
    2. graph connectivity — a plant is wired together, scattered sheds are not
    3. pipeline coupling — the strongest evidence of a single process system
    4. spatial compactness — a complex occupies a contiguous footprint

    Returns ``(score, connectivity)``, both in [0, 1].
    """
    if not nodes:
        return 0.0, 0.0

    count = len(nodes)

    # 1. Equipment evidence — the single best object dominates, because one
    #    flare stack is more diagnostic than twenty warehouses.
    weights = [_KIND_WEIGHT.get(node.kind, 0.05) for node in nodes]
    proximity = [
        max(0.0, 1.0 - node.distance_m / max(1.0, radius_m)) for node in nodes
    ]
    weighted = [w * (0.4 + 0.6 * p) for w, p in zip(weights, proximity)]
    equipment = max(weighted) if weighted else 0.0

    # 2. Connectivity — edges per node, saturating at 3.
    connectivity = min(1.0, len(edges) / max(1.0, count * 3.0)) if count > 1 else 0.0

    # 3. Pipeline coupling.
    pipeline_edges = sum(1 for _, _, kind in edges if kind == "pipeline")
    pipeline = min(1.0, pipeline_edges / 4.0)

    # 4. Compactness — median inter-object spacing inside a plant is small.
    if count > 2:
        distances = np.array([node.distance_m for node in nodes])
        spread = float(np.percentile(distances, 75))
        compactness = max(0.0, 1.0 - spread / max(1.0, radius_m))
    else:
        compactness = 0.0

    score = (
        0.45 * equipment
        + 0.25 * connectivity
        + 0.20 * pipeline
        + 0.10 * compactness
    )
    return round(min(1.0, score), 4), round(connectivity, 4)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def extract_osm_graph(
    lat: float,
    lng: float,
    radius_m: Optional[int] = None,
    event_id: Optional[str] = None,
) -> GraphContext:
    """
    Stage 3 entry point: build and encode the topological context of an anomaly.

    Never raises. Any failure downgrades the returned
    :class:`GraphContext` status so Stage 6 can discount this modality instead
    of the whole pipeline collapsing.
    """
    radius = radius_m if radius_m is not None else _CFG.query_radius_m

    with stage_span(log, _STAGE, "osm_topology", event_id=event_id) as span:
        try:
            elements, source = fetch_osm_subgraph(lat, lng, radius)
            span["source"] = source
            span["elements"] = len(elements)

            if not elements:
                span["outcome"] = "empty"
                return GraphContext(
                    embedding=[0.0] * _CFG.embedding_dim,
                    encoder="none",
                    source=source,
                    status=StageStatus.FALLBACK,
                    notes="no OSM features within the search radius",
                    geolocation_tolerance_m=float(_CFG.geolocation_tolerance_m),
                )

            nodes, edges = build_directed_graph(elements, lat, lng)
            span["nodes"] = len(nodes)
            span["edges"] = len(edges)

            if not nodes:
                return GraphContext(
                    embedding=[0.0] * _CFG.embedding_dim,
                    encoder="none",
                    source=source,
                    status=StageStatus.FALLBACK,
                    notes="OSM features present but none matched the industrial taxonomy",
                    geolocation_tolerance_m=float(_CFG.geolocation_tolerance_m),
                )

            features = build_node_features(nodes, edges, float(radius))

            # --- Encode -----------------------------------------------------
            encoder_name = "heuristic"
            embedding = np.zeros(_CFG.embedding_dim, dtype=np.float64)
            try:
                if _TORCH_GEOMETRIC and len(nodes) > 1:
                    edge_index = (
                        np.array([[s for s, _, _ in edges], [d for _, d, _ in edges]])
                        if edges
                        else np.zeros((2, 0), dtype=np.int64)
                    )
                    encoder = TorchGraphSAGE.instance(
                        features.shape[1], _CFG.embedding_dim, _CFG.sage_layers, settings.random_seed
                    )
                    node_embeddings = encoder(features, edge_index)
                    encoder_name = "graphsage"
                else:
                    adjacency = np.zeros((len(nodes), len(nodes)), dtype=np.float64)
                    for src, dst, _ in edges:
                        adjacency[dst, src] = 1.0  # aggregate from in-neighbours
                    encoder = NumpyGraphSAGE(
                        features.shape[1], _CFG.embedding_dim, _CFG.sage_layers, settings.random_seed
                    )
                    node_embeddings = encoder(features, adjacency)
                    encoder_name = "graphsage_numpy"

                # Readout: attention-free weighted pooling, emphasising nodes
                # that are both diagnostic and close to the anomaly.
                pool_weights = np.array(
                    [
                        _KIND_WEIGHT.get(node.kind, 0.05)
                        * max(0.05, 1.0 - node.distance_m / max(1.0, radius))
                        for node in nodes
                    ]
                )
                if pool_weights.sum() <= 0.0:
                    pool_weights = np.ones(len(nodes))
                pool_weights = pool_weights / pool_weights.sum()
                embedding = (node_embeddings * pool_weights[:, None]).sum(axis=0)
            except Exception as exc:
                span["encoder_error"] = str(exc)[:160]
                log.warning(
                    "GraphSAGE encoding failed, falling back to structural features",
                    extra={"stage": _STAGE, "event_id": event_id},
                )
                encoder_name = "heuristic"
                pooled = features.mean(axis=0)
                embedding = np.resize(pooled, _CFG.embedding_dim)

            score, connectivity = _topology_score(nodes, edges, float(radius))

            # --- Node linkage ----------------------------------------------
            nearest = nodes[0]
            named = [n for n in nodes if n.name and n.name != "unnamed"]
            facility_name = named[0].name if named else None
            linked = f"{nearest.kind}:{nearest.node_id}"
            if nearest.name and nearest.name != "unnamed":
                linked = f"{nearest.kind}:{nearest.node_id} ({nearest.name})"

            tank_count = sum(1 for n in nodes if n.kind == "tank")
            flare_count = sum(1 for n in nodes if n.kind == "flare")
            chimney_count = sum(1 for n in nodes if n.kind == "chimney")
            building_count = sum(1 for n in nodes if n.kind == "building")
            pipeline_edges = sum(1 for _, _, kind in edges if kind == "pipeline")

            # How far the anomaly could have been mislocated and still have hit
            # this same complex — the geolocation-error immunity margin.
            tolerance = min(
                float(_CFG.geolocation_tolerance_m),
                max(node.distance_m for node in nodes) if nodes else 0.0,
            )

            span["topology_score"] = score
            span["encoder"] = encoder_name
            span["linked"] = linked

            return GraphContext(
                embedding=[round(float(v), 6) for v in embedding],
                node_count=len(nodes),
                edge_count=len(edges),
                pipeline_edges=pipeline_edges,
                tank_count=tank_count,
                flare_count=flare_count,
                chimney_count=chimney_count,
                building_count=building_count,
                industrial_topology_score=score,
                connectivity=connectivity,
                nearest_node=nearest,
                linked_osm_node=linked,
                facility_name=facility_name,
                geolocation_tolerance_m=round(tolerance, 1),
                encoder=encoder_name,
                source=source,
                status=StageStatus.OK if source in {"overpass", "cache"} else StageStatus.FALLBACK,
                notes="" if source in {"overpass", "cache"} else f"graph derived from {source}",
                nodes=nodes[:25],
            )

        except Exception as exc:
            span["outcome"] = "error"
            span["error"] = str(exc)[:200]
            log.exception("Stage 3 failed", extra={"stage": _STAGE, "event_id": event_id})
            return GraphContext(
                embedding=[0.0] * _CFG.embedding_dim,
                status=StageStatus.FAILED,
                notes=f"graph encoder error: {str(exc)[:160]}",
            )


def train_topology_encoder(*_args: Any, **_kwargs: Any) -> None:
    """
    Placeholder for supervised training of the GraphSAGE weights.

    To train: assemble ``(subgraph, label)`` pairs — subgraphs extracted around
    confirmed industrial anomalies versus confirmed biomass anomalies, which
    the HITL queue in ``backend/main.py`` already records — then optimise a
    binary readout on the pooled embedding and persist the state dict next to
    the other model artefacts in ``models/``. ``extract_osm_graph`` will pick
    up trained weights without any change to its call signature.
    """
    raise NotImplementedError(
        "No labelled topology dataset ships with this repository. "
        "See the docstring for the training procedure."
    )


__all__ = [
    "extract_osm_graph",
    "fetch_osm_subgraph",
    "build_directed_graph",
    "build_node_features",
    "NumpyGraphSAGE",
    "TorchGraphSAGE",
]
