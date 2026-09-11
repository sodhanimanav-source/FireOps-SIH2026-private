import re

file_path = r'D:\SIH Competition\my web\Frontend\src\components\Map\TacticalMapModule.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_loop = 

new_loop = 



new_loop = new_loop.replace('f"{gridX},{gridY}"', 'gridX + "," + gridY')

if old_loop in content:
    content = content.replace(old_loop, new_loop)
else:
    print('Warning: old loop not found exactly')

old_radius = 'cluster.properties.m_score = Math.max(cluster.properties.m_score, 8);'
new_radius = 'cluster.properties.frp_mean = Math.max(cluster.properties.frp_mean, 100); cluster.properties.m_score = Math.max(cluster.properties.m_score, 8);'
content = content.replace(old_radius, new_radius)

old_zoom = 'map.flyTo({ center: focusedRegion.center, zoom: 11, speed: 1.2 });'
new_zoom = 'map.flyTo({ center: focusedRegion.center, zoom: focusedRegion.level === "state" ? 6 : focusedRegion.level === "district" ? 8 : 11, speed: 1.2 });'
content = content.replace(old_zoom, new_zoom)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Optimized loop inserted')
