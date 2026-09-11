import re
file_path = r'D:\SIH Competition\my web\Frontend\src\components\Map\TacticalMapModule.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()





content = content.replace(
    'const selected = useAppStore((s) => s.selectedAnomaly);',
    'const selected = useAppStore((s) => s.selectedAnomaly);\n  const focusedRegion = useAppStore((s) => s.focusedRegion);'
)



use_effect = 
content = content.replace('  return (\n', use_effect)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('TacticalMapModule.tsx updated')
