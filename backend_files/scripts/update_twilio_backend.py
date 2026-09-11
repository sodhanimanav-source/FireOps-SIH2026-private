path = r"D:\SIH Competition\my web\backend_files\backend\main.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_dispatch = 

new_dispatch = 

if old_dispatch in content:
    content = content.replace(old_dispatch, new_dispatch)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully updated log_dispatch with Twilio in main.py!")
else:
    print("old_dispatch not found, checking exact text.")
