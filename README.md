# FireOps Command Dashboard (SIH)

This project contains the **FireOps Command Dashboard**, consisting of a FastAPI Python backend and a React/Vite frontend. It classifies thermal anomalies as industrial flaring, industrial accidents, coal-seam fires, agricultural burning or wildfires.

## The 6-Stage Multi-Modal Architecture

The backend runs a deterministic six-stage pipeline that separates industrial
thermal sources from biomass burning using **thermodynamics rather than pixel
brightness**.

| Stage | Domain | Module |
|---|---|---|
| 1 | Hybrid LEO + GEO ingestion (FIRMS + INSAT-3D/3DR/3DS) | `ingestion/api_loader.py` |
| 2 | Sub-pixel thermodynamics — Planck inversion + 1200 K gate | `ingestion/physics_filter.py` |
| 3 | Topological structure — OSM directed graph + GraphSAGE | `models/gnn_topology.py` |
| 4 | Visual semantic memory — NASA/IBM Prithvi-EO-2.0 | `models/prithvi_vision.py` |
| 5 | Time rhythm dynamics — ContiFormer + Neural ODE | `models/contiformer_time.py` |
| 6 | Cross-modal attention and decision | `models/cross_modal_fusion.py` |

**Why this is necessary.** A satellite measures the radiance of a whole
375 m pixel, not the temperature of the fire inside it. A 1900 K gas flare
filling 0.005% of a pixel reads as **348 K**; a 750 K crop fire filling 1.2%
reads as **383 K**. The crop fire looks hotter, so any classifier keyed on
brightness gets it backwards. Stage 2 inverts Planck's radiation law to
recover the true sub-pixel temperature, and gates on 1200 K — the boundary
between biomass and industrial combustion chemistry. That single step mutes
roughly three quarters of the national feed before any neural network runs.

**→ Full technical documentation: [`backend_files/ARCHITECTURE.md`](backend_files/ARCHITECTURE.md)**

Verify the physics for yourself:

```bash
cd backend_files
python -m pytest tests/test_pipeline.py -v      # 40 tests, incl. ground-truth retrieval
```

## Prerequisites

Before running the project on a new PC, ensure you have the following installed:

1. **Node.js** (v18 or higher recommended) - [Download Here](https://nodejs.org/)
2. **Python** (v3.10 or higher recommended) - [Download Here](https://www.python.org/downloads/)
3. **Git** (optional, for version control)

---

## 🛠️ Step 1: Running the Backend

The backend is built with Python and FastAPI. It processes NASA FIRMS thermal data and runs the intelligence engine.

1. Open a new terminal (Command Prompt or PowerShell).
2. Navigate to the backend directory:
   ```bash
   cd "backend_files"
   ```
3. Create a virtual environment (highly recommended):
   ```bash
   python -m venv venv
   ```
4. Activate the virtual environment:
   - On Windows: `venv\Scripts\activate`
   - On Mac/Linux: `source venv/bin/activate`
5. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   This is enough to run all six stages. The deep-learning stack is optional:
   ```bash
   pip install -r requirements-v2.txt    # torch, torch_geometric, torchdiffeq, transformers
   ```
   Without it, Stages 3–5 use their NumPy and analytic implementations and the
   system stays fully functional — it simply reports itself as degraded and
   routes more anomalies to operator review.
6. Start the FastAPI server:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```
   The backend should now be running at `http://127.0.0.1:8000`, with the
   autonomous monitoring loop running alongside it. Leave this terminal open.

   Useful endpoints:
   - `POST /api/v1/pipeline/run?max_events=5` — run one full cycle and watch it
   - `GET  /api/v1/intelligence/{event_id}` — the complete six-stage trace and evidence chain for one anomaly
   - `GET  /api/ai-status` — which encoder each stage is actually running right now

   Set `FIREOPS_AGENT_ENABLED=0` to serve the API without the background agent.

---

## 💻 Step 2: Running the Frontend

The frontend is a beautifully designed React application bundled with Vite.

1. Open a **second** terminal window.
2. Navigate to the frontend directory:
   ```bash
   cd "Frontend"
   ```
3. Install the Node.js dependencies:
   ```bash
   npm install
   ```
   *(Note: This might take a few minutes if running for the first time)*
4. Start the development server:
   ```bash
   npm run dev
   ```
5. The terminal will display a local URL (usually `http://localhost:5173`). 
6. Open that URL in your web browser to view the FireOps Command Dashboard!

---

## Troubleshooting

- **Port in Use Error (`[Errno 10048]`):** If the backend fails to start saying the port is in use, another instance of Python is running. Open Task Manager and end any rogue `python.exe` processes, then try again.
- **Frontend API Errors:** Ensure the backend is actively running on port 8000 before opening the frontend. If the frontend says "No data", hard-refresh the page (Ctrl + F5).
- **Missing Module Errors:** Make sure you activated your virtual environment before running the `uvicorn` command.
