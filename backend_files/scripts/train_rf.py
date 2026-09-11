import os, joblib, json, numpy as np
from sklearn.ensemble import RandomForestClassifier

model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models')
os.makedirs(model_dir, exist_ok=True)
fac_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'facilities.json')

facilities = []
if os.path.exists(fac_path):
    with open(fac_path, 'r', encoding='utf-8') as f:
        facilities = json.load(f)

print(f'Loaded {len(facilities)} facilities for training.')

np.random.seed(42)

fac_coords = []
for fac in facilities:
    flat = fac.get('lat')
    flng = fac.get('lng')
    ftype = fac.get('type', '').lower()
    if flat and flng:
        fac_coords.append((flat, flng, ftype))

X = []
y = []


for _ in range(5000):
    lat = np.random.uniform(18.0, 32.0)
    lon = np.random.uniform(73.0, 86.0)
    
    if any(abs(lat - flat) < 0.05 and abs(lon - flng) < 0.05 for flat, flng, _ in fac_coords):
        continue
    frp = np.random.uniform(2.0, 25.0)
    bright = np.random.uniform(300.0, 335.0)
    spread = np.random.randint(0, 2)
    X.append([lat, lon, frp, bright, spread])
    y.append('AGRICULTURAL_BURNING')


for _ in range(2500):
    lat = np.random.uniform(12.0, 30.0)
    lon = np.random.uniform(73.0, 94.0)
    frp = np.random.uniform(45.0, 300.0)
    bright = np.random.uniform(335.0, 440.0)
    spread = np.random.randint(3, 8)
    X.append([lat, lon, frp, bright, spread])
    y.append('WILDFIRE')


for _ in range(1200):
    lat = np.random.uniform(23.5, 24.2)
    lon = np.random.uniform(85.5, 86.8)
    frp = np.random.uniform(5.0, 30.0)
    bright = np.random.uniform(305.0, 340.0)
    spread = np.random.randint(0, 2)
    X.append([lat, lon, frp, bright, spread])
    y.append('COAL_MINE_FIRE')


for flat, flng, ftype in fac_coords:
    is_og = any(k in ftype for k in ['refinery', 'oil', 'gas', 'petro', 'flare'])
    
    is_primary_focus = (
        (abs(flat - 26.266) < 0.05 and abs(flng - 74.188) < 0.05) or 
        (abs(flat - 29.92) < 0.05 and abs(flng - 74.95) < 0.05) or   
        (abs(flat - 22.406) < 0.05 and abs(flng - 69.01) < 0.05)     
    )
    n_pts = 600 if is_primary_focus else 30
    for _ in range(n_pts):
        j_lat = flat + np.random.normal(0, 0.012)
        j_lon = flng + np.random.normal(0, 0.012)
        j_frp = np.random.uniform(5.0, 200.0)
        j_bright = np.random.uniform(310.0, 440.0)
        j_spread = np.random.randint(0, 3)
        X.append([j_lat, j_lon, j_frp, j_bright, j_spread])
        if is_og:
            y.append('FLARE_SPIKE' if j_frp > 70 else 'ROUTINE_FLARING')
        else:
            y.append('INDUSTRIAL_ACCIDENT')

X = np.array(X)
print(f'Total dataset size: {len(X)} samples')

clf = RandomForestClassifier(n_estimators=150, max_depth=14, random_state=42, n_jobs=-1)
clf.fit(X, y)


test_pt1 = [[26.26633, 74.18793, 10.0, 320.0, 0]]
pred1 = clf.predict(test_pt1)[0]
proba1 = clf.predict_proba(test_pt1).max()
print(f'Test Shree Cement Beawar (26.26633, 74.18793): {pred1} ({proba1*100:.1f}%)')

test_pt2 = [[29.92161, 74.95422, 12.0, 325.0, 0]]
pred2 = clf.predict(test_pt2)[0]
proba2 = clf.predict_proba(test_pt2).max()
print(f'Test Bathinda Refinery (29.92161, 74.95422): {pred2} ({proba2*100:.1f}%)')

test_pt3 = [[27.5, 80.5, 10.0, 315.0, 0]]
pred3 = clf.predict(test_pt3)[0]
proba3 = clf.predict_proba(test_pt3).max()
print(f'Test Farm in UP (27.5, 80.5): {pred3} ({proba3*100:.1f}%)')

model_path = os.path.join(model_dir, 'rf_model.pkl')
joblib.dump(clf, model_path)
print('Successfully saved trained model to:', model_path)
