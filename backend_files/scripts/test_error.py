import sys
import os
sys.path.append(r'D:\SIH Competition\my web\backend_files')
import json
import traceback
from backend.main import get_classified_hotspots

try:
    data = get_classified_hotspots(days=7, sensor='VIIRS')
    print("Success")
except Exception as e:
    print("ERROR:")
    traceback.print_exc()
