import re

file_path = r'D:\SIH Competition\my web\backend_files\backend\routers\regions.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

fallback_logic = 
content = re.sub(r'df\[level\] = df\[level\]\.fillna\("Unknown"\)', fallback_logic, content)

groupby_old = 'classes=("predicted_class", get_classes),'
groupby_new = 'classes=("predicted_class", get_classes),\n        center_lat=("latitude", "mean"),\n        center_lon=("longitude", "mean")'
content = content.replace(groupby_old, groupby_new)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('regions.py updated')
