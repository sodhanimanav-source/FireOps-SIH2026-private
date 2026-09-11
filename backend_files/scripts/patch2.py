path = r"D:\SIH Competition\my web\backend_files\models\classifier.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_snippet = 

new_snippet = 

if old_snippet.strip() in content:
    content = content.replace(old_snippet.strip(), new_snippet.strip())
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Cleaned up reason formatting in classifier.py!")
else:
    print("Snippet not found directly, let's check.")
