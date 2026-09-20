# FireOps — 6-Stage Multi-Modal Industrial Fire Classification

## The problem this architecture exists to solve

India's thermal anomaly feed is dominated by two populations that look almost
identical from orbit:

- **Biomass burning** — crop residue, forest and grass fires. Transient,
  seasonal, enormous in number.
- **Industrial thermal sources** — gas flares, blast furnaces, refinery
  stacks, coal seam fires. Persistent, mapped, and the ones that matter for
  emergency response.

A generic NASA FIRMS alert parser cannot separate them, because the quantity
it keys on — pixel brightness temperature — is genuinely ambiguous.

### The motivating measurement

A satellite never measures the temperature of a fire. It measures the radiance
of an entire pixel — 375 m × 375 m for VIIRS — inside which the flame may
occupy a millionth of the area. Brightness temperature is therefore an
**area-weighted average**, which produces this:

| Source | True temperature | Pixel fraction | Observed 3.74 µm brightness |
|---|---|---|---|
| Gas flare | 1900 K | 0.00005 | **348 K** |
| Crop residue fire | 750 K | 0.012 | **383 K** |

The crop fire looks *hotter*. Any classifier keyed on brightness gets this
backwards, and no amount of machine learning on top of brightness fixes it,
because the information was destroyed at the sensor.

This is verified as an executable test:
`tests/test_pipeline.py::test_brightness_temperature_alone_would_fail`.

---

## The pipeline

```
   NASA FIRMS (LEO)              INSAT-3D/3DR/3DS (GEO)
   375 m · 2-4 passes/day        4 km · 1 frame / 30 min
            │                             │
            └──────────┬──────────────────┘
                       ▼
        STAGE 1   Hybrid Multi-Sensor Fusion
                  ingestion/api_loader.py
                       │
                       ▼
        STAGE 2   Sub-Pixel Thermodynamics
                  ingestion/physics_filter.py
                  Planck inversion → T_subpixel
                       │
              ┌────────┴────────┐
        T < 1200 K          T ≥ 1200 K
              │                 │
        ┌─────▼─────┐           ▼
        │  BIOMASS  │   ┌───────────────┬───────────────┐
        │   MUTED   │   ▼               ▼               ▼
        │ (~71-78%  │ STAGE 3        STAGE 4        STAGE 5
        │  of feed) │ Topology       Vision         Time
        └───────────┘ GraphSAGE      Prithvi-EO     ContiFormer
                      over OSM       2.0            + Neural ODE
                        └───────────────┼───────────────┘
                                        ▼
                             STAGE 6  Cross-Modal Attention
                                      models/cross_modal_fusion.py
                                        │
                              ┌─────────┴─────────┐
                        confidence ≥ 0.85    confidence < 0.85
                              ▼                   ▼
                        auto-approved       operator review
```

---

## Stage 1 — Hybrid Multi-Sensor Fusion

`ingestion/api_loader.py`

No single constellation can both see small and look often. LEO gives
resolution; GEO gives cadence. A flare and a crop fire are indistinguishable
in one snapshot — what separates them is *rhythm*, and rhythm needs the
30-minute INSAT revisit.

Each LEO detection is matched to the GEO cell containing it and carries away
its time series, which is the raw material for Stage 5.

**Degradation:** live MOSDAC → on-disk cache → a reconstructed cube. A
reconstructed cube is stamped `source="synthetic"`, `status=FALLBACK`, and
that flag propagates to Stage 6, which caps the confidence it will report.
The system never presents reconstruction as observation.

## Stage 2 — Sub-Pixel Thermodynamics

`ingestion/physics_filter.py`

For a pixel containing a source at `T_f` filling fraction `p` over background
`T_b`:

```
L_obs(λ) = p · B(λ, T_f) + (1 - p) · B(λ, T_b)        (1)
B(λ, T)  = c₁ / ( λ⁵ · (exp(c₂ / λT) - 1) )           (2)   Planck
```

Two unknowns, so two bands. Using MIR (3.74 µm, acutely sensitive to hot
sub-pixel sources) and TIR (11.45 µm, dominated by background) and
rearranging (1) gives a single scalar equation in `T_f` — the classical
bi-spectral retrieval of **Dozier (1981)**.

That residual is **strictly monotonic**, because the MIR Planck function grows
exponentially with temperature while the TIR one grows quasi-linearly. So
bisection is unconditionally convergent, which is what makes the whole
retrieval safely **vectorisable**: every anomaly in the country is solved in a
fixed number of array passes with no Python loop. 5000 retrievals run in well
under a second.

**Accuracy:** recovers known ground truth to `rel=1e-4` in temperature and
`rel=1e-3` in fractional area across 1200–2200 K.

### The gate

Biomass combustion runs 600–1100 K; industrial combustion runs 1400–2200 K.
The separation is a property of fuel and oxidiser, not of the satellite, so
**1200 K** splits the populations on physics alone.

Below the gate, anomalies are muted immediately and never touch a neural
network. On the national feed this discards ~71–78% of detections for the cost
of a few array operations — the pipeline's main compute saving.

### Two things this stage is careful about

**A failed retrieval is not a cold source.** If the thermal excess is absent,
the result is `INDETERMINATE`, and Stage 6 holds the gate *neutral* at 0.5
rather than letting a temperature of zero force the anomaly into the biomass
family. Silently muting an unretrievable refinery fire would be the most
dangerous failure this system could have.

**The single-band fallback is honest about ambiguity.** When no thermal band
is available, FRP supplies the second constraint — but that residual is *not*
monotonic. Above ~1000 K the 3.74 µm band approaches the Rayleigh-Jeans limit
where `B ∝ T` while emitted power grows as `T⁴`, so the equation admits **zero
or two** roots. The solver scans for every sign change; if two roots straddle
the gate it **refuses to decide** rather than picking one, and the anomaly goes
to an operator.

## Stage 3 — Topological Structure Mapping

`models/gnn_topology.py`

Proximity ("is there a factory within 3 km?") fails in exactly the cases that
matter: VIIRS geolocation error reaches ~1.5 km, so a flare inside a refinery
can be reported outside its fence; and the field next door is also within 3 km.

A refinery is not a point, it is a **connected system**. This stage parses OSM
into a directed graph — nodes are tanks, flare stacks, chimneys, process works
and wells; edges are pipelines and process-flow relations following material
direction — and encodes it with **GraphSAGE**:

```
h_v^(l+1) = σ( W_self · h_v^(l) + W_neigh · mean_{u ∈ N(v)} h_u^(l) )
```

Because every node aggregates from its neighbours, a detection landing on a
tank and one landing on the adjacent pipeline junction converge to similar
embeddings after two hops. That is the geolocation-error immunity.

**Degradation:** Overpass → disk cache → the curated `data/facilities.json`.
torch_geometric `SAGEConv` when available, an identical-mathematics NumPy mean
aggregator otherwise.

## Stage 4 — Visual Semantic Memory

`models/prithvi_vision.py`

OSM can be years out of date. The discriminator that does not go stale is
**permanence**: concrete and steel look the same next month; a burn scar
regrows.

Uses NASA/IBM **Prithvi-EO-2.0**, a temporal ViT masked auto-encoder trained
on the global HLS archive over the six bands that separate built-up surfaces
from vegetation and burn scars. Being self-supervised, it characterises "what
kind of place is this" with no manual labelling.

**Degradation:** explicit NDVI / NBR / NDBI analysis over the same bands.

One subtlety handled here: **NDBI alone cannot separate char from concrete** —
both are non-vegetated and SWIR-bright, so a naive built-up index scores a
fresh burn scar as industrial. The discriminator is the *magnitude* of the NBR
collapse (char drives NBR below −0.3; concrete sits near −0.05), so burn
evidence is computed first and permanence is explicitly suppressed by it.

## Stage 5 — Time Rhythm Dynamics

`models/contiformer_time.py`

Satellites do not sample on a grid — passes drift, clouds delete observations.
This breaks standard sequence models, which see "step 1, step 2, step 3" with
no notion that one gap was 20 minutes and the next was nine hours.

Three tools chosen for irregular sampling:

1. **Lomb-Scargle periodogram** — the classical spectral estimator for
   unevenly sampled series. Fits sinusoids by least squares at each trial
   frequency rather than assuming a uniform grid. Recovers a 24.0 h flaring
   cycle to **24.01 h** and an 8 h shift cycle to **8.14 h** from randomly
   sampled observations.
2. **Neural ODE latent flow** — `dz/dt = f_θ(z,t)` integrated over true
   elapsed time, so a nine-hour gap is integrated as a nine-hour gap
   (`torchdiffeq`, or explicit RK4 in NumPy).
3. **Continuous-time attention (ContiFormer)** — attention logits carry an
   `exp(-|tᵢ-tⱼ|/τ)` kernel, so relevance decays with real time rather than
   index distance.

**Persistence measures the source, not the sampling.** Sampling density alone
would score a 4-hour crop fire caught by seven consecutive GEO frames *above*
a refinery flare burning for a week. Persistence is therefore absolute
activity duration (saturating at 48 h — biomass exhausts its fuel, industrial
combustion is refuelled) times continuity across dark gaps.

**A peak must clear two independent tests** — false-alarm probability *and*
peak-to-median prominence — before a cycle is reported. FAP alone is
optimistic on long series, where noise reliably produces one tall spike.

## Stage 6 — Cross-Modal Attention and Decision

`models/cross_modal_fusion.py`

Averaging the modalities would be wrong, because which one to trust is itself
decided by the physics. Sub-pixel temperature is the one model-free
measurement, so it is the **attention gate**:

```
g = σ( (T_subpixel − 1200 K) / 120 K )
```

- `g → 1`: attention is forced onto **topology and rhythm** — the modalities
  that separate routine flaring from an accident.
- `g → 0`: attention shifts to **vision** — which separates crop fire from
  wildfire — and structural evidence is suppressed.

Measured behaviour: at 2000 K the graph and time modalities take 0.93 of the
attention mass; at 700 K vision takes 0.86.

### Confidence discipline

Confidence is built in two tiers. The **family** decision (industrial vs
biomass) is the primary claim and what an operator acts on. The specific class
within a family is secondary — routine flaring and a flare spike are the same
physical process at different intensities and legitimately share probability
mass, so scoring on their margin alone would report a textbook-clear refinery
flare as a coin toss.

Every degraded encoder then costs confidence, and a degraded pipeline is
**capped below the review threshold** — it can never auto-approve:

| Scenario | Verdict | Confidence | Outcome |
|---|---|---|---|
| Routine flare, all encoders healthy | `ROUTINE_FLARING` | 0.86 | auto-approved |
| Same anomaly, all three encoders degraded | `ROUTINE_FLARING` | 0.62 | **operator review** |
| Anomaly at 1210 K, ambiguous evidence | `UNCLASSIFIED` | 0.35 | **operator review** |

---

## What is trained and what is not

This matters for reading the code honestly.

**Stage 2 is not a model.** It is the inversion of a physical law, its output
is verifiable against ground truth, and it is what actually drives the
industrial/biomass split.

**Stages 3 and 5 ship with deterministically initialised, untrained weights.**
No labelled OSM-topology or rhythm corpus ships with this repository. An
untrained message-passing encoder is still a useful structural fingerprint — a
stable projection of neighbourhood aggregation, so similar topologies map to
similar vectors — but it is **not a classifier**. The quantities that drive the
Stage 6 decision are the *analytic* statistics: `industrial_topology_score`,
`persistence_score`, Lomb-Scargle `periodicity_score`, `rhythm_regularity`,
`burst_score`. All are interpretable and independently checkable.
`train_topology_encoder()` documents the procedure for training the weights
once labelled data exists — the HITL queue is already recording it.

**Stage 4 uses genuinely pretrained weights** (Prithvi-EO-2.0) when the
Hugging Face Hub is reachable, and real spectral physics otherwise.

---

## Failure isolation

Every stage returns its typed contract rather than raising. Encoders run
concurrently under a wall-clock budget, so a hung Overpass request cannot
stall the national loop.

| Failure | Consequence |
|---|---|
| No FIRMS key | Cached detections served |
| MOSDAC unreachable | Reconstructed GEO cube, flagged, confidence capped |
| Overpass unreachable | Graph from `facilities.json`, marked `FALLBACK` |
| Hugging Face unreachable | NDVI/NBR/NDBI analysis, marked `FALLBACK` |
| torch / torch_geometric absent | NumPy GraphSAGE and RK4 paths |
| An encoder times out | `FAILED` context; Stage 6 reweights around it |
| **All three encoders down** | Legacy proximity classifier, confidence 0.45, forced review |

---

## Modular separation

```
core  ←  ingestion  ←  models  ←  agent_loop  ←  backend
```

`core` imports nothing from the project, so no stage can create a cycle by
depending on shared contracts. Stages communicate *only* through the
dataclasses in `core/schemas.py` — no stage imports a sibling stage.

`agent_loop.py` is a traffic controller and contains no model mathematics.
This is enforced by a test
(`TestArchitecture::test_orchestrator_holds_no_model_logic`) that greps its
source for `planck`, `SAGEConv`, `odeint`, `softmax` and friends.

---

## Running it

```bash
pip install -r requirements.txt                      # core — fully functional
pip install -r requirements.txt -r requirements-v2.txt   # + trained-model paths

uvicorn backend.main:app --reload                    # API + autonomous agent
python agent_loop.py                                 # one cycle, printed
python -m pytest tests/test_pipeline.py -v           # 40 verification tests
```

### Configuration

Every threshold is environment-overridable; see `core/config.py`.

| Variable | Default | Meaning |
|---|---|---|
| `FIREOPS_TEMP_GATE_K` | `1200` | Industrial combustion threshold |
| `FIREOPS_GATE_SOFTNESS_K` | `120` | Logistic width of the attention gate |
| `FIREOPS_HITL_THRESHOLD` | `0.85` | Below this, an operator reviews |
| `FIREOPS_POLL_INTERVAL` | `60` | Seconds between cycles |
| `FIREOPS_MAX_EVENTS` | `25` | Anomalies fully analysed per cycle |
| `FIREOPS_STAGE_TIMEOUT` | `45` | Per-encoder wall-clock budget |
| `FIREOPS_AGENT_ENABLED` | `1` | Set `0` to serve the API without the agent |
| `FIRMS_MAP_KEY` | — | NASA FIRMS key |
| `MOSDAC_TOKEN` | — | ISRO MOSDAC token (enables live INSAT) |
| `HF_TOKEN` | — | Hugging Face token (enables Prithvi-EO-2.0) |

### API

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/hotspots/live` | Live GeoJSON, enriched with `AI_Confidence`, `Sub_Pixel_Temp`, `Linked_OSM_Node` |
| `GET /api/v1/intelligence` | Full pipeline records, filterable by class and confidence |
| `GET /api/v1/intelligence/geojson` | Intelligence as GeoJSON |
| `GET /api/v1/intelligence/{event_id}` | Complete six-stage trace + evidence chain |
| `GET /api/v1/pipeline/status` | Agent health and last-cycle statistics |
| `POST /api/v1/pipeline/run?max_events=N` | Run one cycle synchronously |
| `GET /api/v1/alerts/pending` | Review queue, lowest confidence first |
| `POST /api/v1/alerts/resolve/{event_id}` | Record an operator decision |
| `GET /api/ai-status` | Which encoder each stage is actually running |

Operator decisions are never overwritten by later automated passes.

### Every verdict is explainable

```json
{
  "summary": {
    "AI_Confidence": 0.86,
    "Sub_Pixel_Temp": 1847.3,
    "Linked_OSM_Node": "flare:w402118 (Jamnagar Refinery Complex)",
    "classification": "ROUTINE_FLARING"
  },
  "evidence": [
    "Planck inversion (dozier_bispectral) retrieved a sub-pixel source at 1847 K filling 9.40e-05 of the pixel (13 m² of fire).",
    "Retrieved FRP agrees with the reported value to 91%, so the retrieval is self-consistent.",
    "1847 K exceeds the 1200 K industrial combustion threshold — too hot for biomass fuel.",
    "Topology: 34 mapped objects (12 tanks, 3 flares, 5 chimneys) connected by 61 directed edges including 8 pipelines — industrial structure score 0.92.",
    "Rhythm: 142 observations over 168 h, persistence 0.95, repeating every 24.1 h (confidence 1.00).",
    "Thermal gate multiplier 1.00 directed attention mainly to the time modality (graph 0.46, vision 0.07, time 0.47)."
  ]
}
```
