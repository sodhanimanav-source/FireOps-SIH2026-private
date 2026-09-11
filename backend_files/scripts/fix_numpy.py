import os

file_path = r'D:\SIH Competition\my web\backend_files\models\classifier.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = 

new_logic = 

content = content.replace(old_logic, new_logic)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed numpy type serialization!")
