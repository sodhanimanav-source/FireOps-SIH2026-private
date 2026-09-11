import os

file_path = r'D:\SIH Competition\my web\backend_files\models\intelligence\proximity.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_loop = 

new_loop = 

content = content.replace(old_loop, new_loop)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Optimized proximity.py with bounding box filter!")
