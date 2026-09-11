import re
file_path = r'D:\SIH Competition\my web\Frontend\src\components\Analytics\RegionDrilldown.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()


old_row = 'interface Row { name: string; objects: number; anomalies: number; frp_total: number; max_m: number; critical: number; classes: Record<string, number>; }'
new_row = 'interface Row { name: string; objects: number; anomalies: number; frp_total: number; max_m: number; critical: number; classes: Record<string, number>; center_lat?: number; center_lon?: number; }'
content = content.replace(old_row, new_row)


old_focus = 'onFocusRegion?.(r.name, cur.level);'
new_focus = 'onFocusRegion?.(r.name, cur.level, (r.center_lon && r.center_lat) ? [r.center_lon, r.center_lat] : undefined);'
content = content.replace(old_focus, new_focus)


old_prop = 'onFocusRegion?: (name: string, level: Level) => void'
new_prop = 'onFocusRegion?: (name: string, level: Level, center?: [number, number]) => void'
content = content.replace(old_prop, new_prop)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('RegionDrilldown.tsx updated')
