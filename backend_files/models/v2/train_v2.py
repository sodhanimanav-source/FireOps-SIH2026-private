import os
import joblib
import json
import pandas as pd
from tqdm import tqdm
from math import floor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import classification_report
import lightgbm as lgb
from .features_v2 import ContextBuilder, FEATURES
from .labels_v2 import weak_label

def main():
    history_path = "data/firms_india_history.parquet"
    if not os.path.exists(history_path):
        print("No history data to train on.")
        return
        
    df = pd.read_parquet(history_path)
    builder = ContextBuilder(osm_path="data/osm_industry_india.parquet",
                             history_path="data/firms_india_history.parquet",
                             worldcover_path="data/worldcover_india.tif")
                             
    features_list = []
    labels = []
    groups = []
    
    print("Building features...")
    for idx, row in tqdm(df.iterrows(), total=len(df)):
        lat = row.get("latitude")
        lng = row.get("longitude")
        frp = row.get("frp", 5.0)
        bright = row.get("bright_ti4", row.get("brightness", 310.0))
        dn = row.get("daynight", "D")
        
        f = builder.build(lat, lng, frp, bright, dn)
        l = weak_label(f)
        if l is not None:
            features_list.append([f[k] for k in FEATURES])
            labels.append(l)
            groups.append(f"{floor(lat/0.5)}_{floor(lng/0.5)}")
            
    X = pd.DataFrame(features_list, columns=FEATURES)
    y = pd.Series(labels)
    groups = pd.Series(groups)
    
    print("Class counts:")
    print(y.value_counts())
    
    gkf = GroupKFold(n_splits=5)
    train_idx, test_idx = next(gkf.split(X, y, groups))
    
    model = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=31,
                               class_weight="balanced", min_child_samples=50, 
                               subsample=0.8, colsample_bytree=0.8)
    
    print("Training fold 0 for evaluation...")
    model.fit(X.iloc[train_idx], y.iloc[train_idx])
    preds = model.predict(X.iloc[test_idx])
    print(classification_report(y.iloc[test_idx], preds))
    
    print("Training final model on all data...")
    model.fit(X, y)
    
    os.makedirs("models", exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES, "classes": list(model.classes_)}, "models/lgb_v2.pkl")
    
    imp = dict(zip(FEATURES, model.feature_importances_.tolist()))
    with open("models/v2/feature_importance.json", "w") as f:
        json.dump(imp, f, indent=2)
    print("Saved models/lgb_v2.pkl")

if __name__ == "__main__":
    main()
