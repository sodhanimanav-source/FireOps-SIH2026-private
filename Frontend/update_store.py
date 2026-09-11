import re
file_path = r'D:\SIH Competition\my web\Frontend\src\store\useAppStore.ts'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('focusedRegion: { name: string; level: string } | null;', 'focusedRegion: { name: string; level: string; center?: [number, number] } | null;')
content = content.replace('setFocusedRegion: (region: { name: string; level: string } | null) => void;', 'setFocusedRegion: (region: { name: string; level: string; center?: [number, number] } | null) => void;')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('useAppStore.ts updated')
