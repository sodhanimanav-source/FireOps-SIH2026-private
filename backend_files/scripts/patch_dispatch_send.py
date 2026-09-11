path = r"D:\SIH Competition\my web\backend_files\backend\main.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

target = '@app.post("/api/v1/dispatch/log")'
replacement = '@app.post("/api/v1/dispatch/log")\n@app.post("/api/v1/dispatch/send")'

if target in content and '@app.post("/api/v1/dispatch/send")' not in content:
    content = content.replace(target, replacement)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Added /api/v1/dispatch/send alias to main.py!")
else:
    print("Already exists or target not found.")
