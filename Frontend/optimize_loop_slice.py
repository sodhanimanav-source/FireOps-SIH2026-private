import re

file_path = r'D:\SIH Competition\my web\Frontend\src\components\Map\TacticalMapModule.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()


start_marker = "const clusters: any[] = [];"
end_marker = "// Assign AI-like labels based on classification"

if start_marker in content and end_marker in content:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    old_block = content[start_idx:end_idx]
    
    new_block = 
    
    content = content[:start_idx] + new_block + content[end_idx:]
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replaced loop successfully via index slice.')
else:
    print('Markers not found.')
