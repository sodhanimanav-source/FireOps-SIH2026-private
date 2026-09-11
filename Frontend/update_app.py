import re
file_path = r'D:\SIH Competition\my web\Frontend\src\App.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_focus = 'onFocusRegion={(name, level) => \nuseAppStore.getState().setFocusedRegion({ name, level })}'
new_focus = 'onFocusRegion={(name, level, center) => useAppStore.getState().setFocusedRegion({ name, level, center })}'

content = re.sub(r'onFocusRegion=\{\(name, level\) =>\s*useAppStore\.getState\(\)\.setFocusedRegion\(\{ name, level \}\)\}', new_focus, content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('App.tsx updated')
