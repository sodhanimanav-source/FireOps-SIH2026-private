# FireOps Command Dashboard (SIH)

This project contains the **FireOps Command Dashboard**, consisting of a FastAPI Python backend and a React/Vite frontend. It uses a custom Transparent Intelligence Engine to classify thermal anomalies as either industrial flaring, accidents, or wildfires.

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
   *(If `requirements.txt` is missing, manually install: `pip install fastapi uvicorn pandas numpy requests scikit-learn`)*
6. Start the FastAPI server:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```
   The backend should now be running at `http://127.0.0.1:8000`. Leave this terminal open.

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
