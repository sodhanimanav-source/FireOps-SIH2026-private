
import numpy as np
import pandas as pd

CELL_DEG = 0.009  

def to_cells(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "acq_date" in df.columns:
        df["acq_dt"] = pd.to_datetime(df.acq_date, errors="coerce")
    else:
        df["acq_dt"] = pd.to_datetime("today")
    df["cell_lat"] = (df.latitude // CELL_DEG) * CELL_DEG + CELL_DEG / 2
    df["cell_lon"] = (df.longitude // CELL_DEG) * CELL_DEG + CELL_DEG / 2
    df["cell_id"] = df.cell_lat.round(4).astype(str) + "_" + df.cell_lon.round(4).astype(str)
    return df

def cell_profile(g: pd.DataFrame, window_days: int) -> dict:
    if "frp" in g.columns:
        daily = g.groupby(g.acq_dt.dt.date).frp.sum().sort_index()
    else:
        daily = g.groupby(g.acq_dt.dt.date).size()
        
    days_active = len(daily)
    gaps = np.diff(pd.to_datetime(daily.index).values).astype("timedelta64[D]").astype(int) if days_active > 1 else np.array([])
    med = daily.median()
    
    night_ratio = 0.0
    if "daynight" in g.columns:
        night_ratio = float((g.daynight == "N").mean())
        
    return {
        "cell_id": g.cell_id.iloc[0], "lat": g.cell_lat.iloc[0], "lon": g.cell_lon.iloc[0],
        "n_detections": len(g),
        "days_active": days_active,
        "recurrence_rate": days_active / window_days if window_days > 0 else 1.0,
        "mean_gap_days": float(gaps.mean()) if len(gaps) else None,
        "regularity": float(1 / (1 + gaps.std())) if len(gaps) > 1 else None,
        "night_ratio": night_ratio,
        "frp_median": float(med),
        "frp_max": float(daily.max()) if not daily.empty else 0.0,
        "spike_ratio": float(daily.max() / med) if med > 0 else None,
        "frp_cv": float(daily.std() / daily.mean()) if daily.mean() > 0 else None,
        "trend": float(np.polyfit(range(days_active), daily.values, 1)[0]) if days_active > 2 else 0.0,
        "first_seen": str(daily.index[0]) if not daily.empty else "N/A", 
        "last_seen": str(daily.index[-1]) if not daily.empty else "N/A",
        "is_new": days_active <= 2 and (g.acq_dt.max() - g.acq_dt.min()).days <= 2,
    }

def build_profiles(df: pd.DataFrame) -> pd.DataFrame:
    df = to_cells(df)
    window = max((df.acq_dt.max() - df.acq_dt.min()).days + 1, 1) if not df.empty else 1
    if df.empty:
        return pd.DataFrame()
    return pd.DataFrame([cell_profile(g, window) for _, g in df.groupby("cell_id")])

def spread_score(profiles: pd.DataFrame, df: pd.DataFrame) -> pd.Series:
    if df.empty or profiles.empty:
        return pd.Series(0, index=profiles.index)
    if "cell_id" not in df.columns:
        df = to_cells(df)
    active = df.groupby("cell_id").acq_dt.agg(["min", "max"])
    cells = set(active.index)
    def neighbours(cid):
        try:
            lat, lon = map(float, cid.split("_"))
            return [f"{round(lat+i*CELL_DEG,4)}_{round(lon+j*CELL_DEG,4)}" for i in (-1,0,1) for j in (-1,0,1) if (i,j)!=(0,0)]
        except:
            return []
    return profiles.cell_id.map(lambda c: sum(n in cells for n in neighbours(c)))
