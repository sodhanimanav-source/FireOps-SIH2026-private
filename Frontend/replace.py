import os

files_to_update = {
    r'src\vite-env.d.ts': [
        ('VITE_API_BASE?:', 'VITE_API_BASE_URL?:')
    ],
    r'src\api\client.ts': [
        ('import.meta.env.VITE_API_BASE', 'import.meta.env.VITE_API_BASE_URL')
    ],
    r'src\api\queries.ts': [
        (\"baseURL: 'http://localhost:8000/api'\", \"baseURL: \\/api\\")
    ],
    r'src\api\queries.test.tsx': [
        (\"'http://localhost:8000/api'\", \"\\/api\\")
    ],
    r'src\components\Analytics\AIModelStatus.tsx': [
        (\"'http://localhost:8000/api/ai-status'\", \"\\/api/ai-status\\")
    ],
    r'src\components\Analytics\ClassificationBreakdown.tsx': [
        (\"'http://localhost:8000/api/analytics'\", \"\\/api/analytics\\")
    ],
    r'src\components\Analytics\PredictiveInsights.tsx': [
        (\"'http://localhost:8000/api/predictions'\", \"\\/api/predictions\\")
    ],
    r'src\components\Analytics\RiskAssessment.tsx': [
        (\"'http://localhost:8000/api/predictions'\", \"\\/api/predictions\\")
    ]
}

for rel_path, replacements in files_to_update.items():
    filepath = os.path.join(r'd:\SIH Competition\my web\Frontend', rel_path)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        for old_text, new_text in replacements:
            content = content.replace(old_text, new_text)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Updated {filepath}')
    else:
        print(f'File not found: {filepath}')
