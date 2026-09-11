path = r"D:\SIH Competition\my web\Frontend\src\api\types.ts"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

target = "  scenario_id?: string;\n}"
replacement = "  scenario_id?: string;\n  reason?: string;\n}"

if target in content:
    content = content.replace(target, replacement)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Added reason?: string to types.ts!")
else:
    print("Target not found in types.ts")
