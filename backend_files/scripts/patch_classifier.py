path = r'D:\SIH Competition\my web\backend_files\models\classifier.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = 'if global_clf is not None and idx in pred_map:'
idx_find = content.find(target)
print('Found target at:', idx_find)

old_block = "

new_block = "

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully updated classifier.py!")
else:
    print("Error: old_block not found!")
