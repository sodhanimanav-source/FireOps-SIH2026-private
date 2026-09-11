import os
import subprocess
import sys

def run_command(command, cwd=None):
    print(f"Running: {command} in {cwd or os.getcwd()}")
    process = subprocess.Popen(command, shell=True, cwd=cwd)
    process.wait()
    if process.returncode != 0:
        print(f"Command failed with exit code {process.returncode}")
    else:
        print("Success!\n")

def main():
    print("==============================================")
    print("   FireOps Setup - Dependencies Installer     ")
    print("==============================================\n")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(base_dir, "backend_files")
    frontend_dir = os.path.join(base_dir, "Frontend")
    
    print("Step 1/2: Installing Backend Dependencies...")
    req_file = os.path.join(backend_dir, "requirements.txt")
    if os.path.exists(req_file):
        run_command(f"{sys.executable} -m pip install -r requirements.txt", cwd=backend_dir)
        
        run_command(f"{sys.executable} -m pip install pandas geopandas scikit-learn rasterio joblib shapely", cwd=backend_dir)
    else:
        print(f"Warning: {req_file} not found.\n")

    print("Step 2/2: Installing Frontend Dependencies...")
    if os.path.exists(os.path.join(frontend_dir, "package.json")):
        run_command("npm install", cwd=frontend_dir)
    else:
        print(f"Warning: package.json not found in {frontend_dir}.\n")
        
    print("==============================================")
    print("                 SETUP COMPLETE               ")
    print("==============================================\n")
    print("To run the project on your GPU laptop:")
    print("1. Open a terminal, go to the 'backend_files' folder and run:")
    print("   uvicorn backend.main:app --host 127.0.0.1 --port 8000")
    print("\n2. Open a SECOND terminal, go to the 'Frontend' folder and run:")
    print("   npm run dev")
    print("\n3. Open your browser and go to http://localhost:5173")
    print("\nNote: Make sure Python (with pip) and Node.js (with npm) are installed on the new laptop!")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
