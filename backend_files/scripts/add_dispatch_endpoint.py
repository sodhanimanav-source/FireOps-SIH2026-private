path = r"D:\SIH Competition\my web\backend_files\backend\main.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

target = 'def get_incident_card_v1(cluster_id: str, lat: float = None, lon: float = None):'
end_marker = '"cryogenic_override": True\n    }'

new_endpoint = 

if end_marker in content:
    idx = content.find(end_marker) + len(end_marker)
    content = content[:idx] + new_endpoint + content[idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Added /api/v1/dispatch/log to main.py!")
else:
    print("Could not find end_marker in main.py")
