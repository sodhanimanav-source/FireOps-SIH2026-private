import os, joblib, numpy as np, lightgbm as lgb
model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
os.makedirs(model_dir, exist_ok=True)
np.random.seed(42)
n_samples = 5000
X = np.zeros((n_samples, 6))
X[:, 0] = np.random.uniform(5, 500, n_samples)
X[:, 1] = np.random.uniform(290, 400, n_samples)
X[:, 2] = np.random.uniform(0, 50, n_samples)
X[:, 3] = np.random.randint(0, 24, n_samples)
X[:, 4] = np.random.randint(1, 30, n_samples)
X[:, 5] = np.random.randint(0, 6, n_samples)
y = []
for i in range(n_samples):
    if X[i, 2] <= 5.0:
        if X[i, 0] > 150: y.append("INDUSTRIAL_ACCIDENT")
        elif X[i, 0] > 80: y.append("FLARE_SPIKE")
        else: y.append("ROUTINE_FLARING")
    else:
        if X[i, 0] < 25: y.append("AGRICULTURAL_BURNING")
        else: y.append("WILDFIRE")
clf = lgb.LGBMClassifier(n_estimators=100, random_state=42)
clf.fit(X, y)
joblib.dump(clf, os.path.join(model_dir, "lgb_classifier.pkl"))
print("Saved lgb_classifier.pkl")
