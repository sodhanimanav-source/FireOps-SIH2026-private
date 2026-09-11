import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib
from datetime import datetime, timedelta

MODEL_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(MODEL_DIR, "..", "data", "segregated_historical_data.csv")
MODEL_PATH = os.path.join(MODEL_DIR, "forecaster_rf.pkl")

def train_forecaster():
    print("[AI PIPELINE] Training Forecasting Model...")
    
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] Data not found at {DATA_PATH}")
        return
        
    df = pd.read_csv(DATA_PATH)
    df['date'] = pd.to_datetime(df['date'])
    
    
    daily_counts = df.groupby('date').size().reset_index(name='count')
    daily_counts = daily_counts.sort_values('date')
    
    
    daily_counts['day_of_week'] = daily_counts['date'].dt.dayofweek
    daily_counts['day_of_month'] = daily_counts['date'].dt.day
    daily_counts['month'] = daily_counts['date'].dt.month
    
    
    daily_counts['lag_1'] = daily_counts['count'].shift(1)
    daily_counts['lag_3'] = daily_counts['count'].shift(3)
    daily_counts['lag_7'] = daily_counts['count'].shift(7)
    
    daily_counts.dropna(inplace=True)
    
    X = daily_counts[['day_of_week', 'day_of_month', 'month', 'lag_1', 'lag_3', 'lag_7']]
    y = daily_counts['count']
    
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    joblib.dump(model, MODEL_PATH)
    print(f"[AI PIPELINE] ✅ Forecasting model saved to {MODEL_PATH}")

def predict_future(days_ahead=5):
    if not os.path.exists(MODEL_PATH) or not os.path.exists(DATA_PATH):
        return []
        
    model = joblib.load(MODEL_PATH)
    df = pd.read_csv(DATA_PATH)
    df['date'] = pd.to_datetime(df['date'])
    
    daily_counts = df.groupby('date').size().reset_index(name='count').sort_values('date')
    last_date = daily_counts['date'].iloc[-1]
    
    history = daily_counts['count'].values.tolist()
    
    predictions = []
    
    for i in range(1, days_ahead + 1):
        target_date = last_date + timedelta(days=i)
        
        lag_1 = history[-1]
        lag_3 = history[-3] if len(history) >= 3 else history[-1]
        lag_7 = history[-7] if len(history) >= 7 else history[-1]
        
        X_pred = np.array([[target_date.dayofweek, target_date.day, target_date.month, lag_1, lag_3, lag_7]])
        pred_count = int(model.predict(X_pred)[0])
        
        predictions.append({
            "date": target_date.strftime("%Y-%m-%d"),
            "predicted_count": pred_count
        })
        
        history.append(pred_count)
        
    return predictions

if __name__ == "__main__":
    train_forecaster()
