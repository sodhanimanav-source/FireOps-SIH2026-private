path = r"D:\SIH Competition\my web\backend_files\backend\main.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

target = "class DispatchLogRequest(BaseModel):"
end_marker = '"carrier_status": "DISPATCHED",\n    }\n    _dispatch_logs.append(entry)\n    return {"status": "success", "dispatch_id": f"DISP-{len(_dispatch_logs):04d}", "entry": entry}'

new_code = 

idx_start = content.find(target)
idx_end = content.find(end_marker)

if idx_start != -1 and idx_end != -1:
    idx_end += len(end_marker)
    content = content[:idx_start] + new_code + content[idx_end:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully patched main.py with HttpSMS!")
else:
    print(f"Could not find markers: idx_start={idx_start}, idx_end={idx_end}")
