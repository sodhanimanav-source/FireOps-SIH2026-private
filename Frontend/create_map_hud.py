import os

base_dir = r'd:\SIH Competition\my web\Frontend'

files = {
    'src/components/Map/TacticalMap.tsx': ,
    'src/components/HUD/BottomHUD.tsx': 
}

for rel_path, content in files.items():
    full_path = os.path.join(base_dir, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

print('Map and HUD files generated successfully')
