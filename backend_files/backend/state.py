import pandas as pd
from backend.features.admin import AdminIndex
import json
from datetime import datetime, timedelta, timezone

class GlobalState:
    def __init__(self):
        self.admin = AdminIndex()
        self._window_df = None
        self._days = []
        
    def _generate_window_df(self):
        from backend.main import _generate_hotspots_window
        data = _generate_hotspots_window(days=7)
        features = data["collection"]["features"]
        self._days = data["days"]
        
        rows = []
        for f in features:
            props = f["properties"]
            geom = f["geometry"]["coordinates"]
            props["longitude"] = geom[0]
            props["latitude"] = geom[1]
            rows.append(props)
            
        df = pd.DataFrame(rows)
        if not df.empty:
            df = self.admin.tag_frame(df)
        self._window_df = df
        
    def window_df(self, day_index: int = None) -> pd.DataFrame:
        if self._window_df is None:
            self._generate_window_df()
            
        df = self._window_df
        if day_index is not None:
            df = df[df["day_index"] == day_index]
        return df

    def window_days(self) -> list[str]:
        if not self._days:
            self._generate_window_df()
        return self._days
        
state = GlobalState()
