path = r"D:\SIH Competition\my web\Frontend\src\components\Triage\IncidentActionPanel.tsx"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("(CLASS_LABELS[p?.predicted_class as any]", "((CLASS_LABELS as any)[p?.predicted_class || '']")
content = content.replace("CLASS_LABELS[p.predicted_class as any]", "(CLASS_LABELS as any)[p.predicted_class || '']")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated casts in IncidentActionPanel.tsx!")
