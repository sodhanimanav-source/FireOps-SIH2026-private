path = r"D:\SIH Competition\my web\backend_files\models\classifier.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    'reason = f"AI Reasoning: RandomForest Ensemble (confidence {conf_pct}%) detected {predicted_class} signature co-located with {fac_name}."',
    'reason = f"RandomForest Ensemble (confidence {conf_pct}%) detected {predicted_class} signature co-located with {fac_name}."'
)
content = content.replace(
    'reason = f"AI Reasoning: RandomForest Ensemble (confidence {conf_pct}%) detected {predicted_class} signature."',
    'reason = f"RandomForest Ensemble (confidence {conf_pct}%) detected {predicted_class} signature."'
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Removed duplicate AI Reasoning prefix from classifier.py!")
