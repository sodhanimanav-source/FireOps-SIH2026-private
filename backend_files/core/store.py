"""
Durable intelligence store.

The orchestrator writes finished :class:`PipelineResult` records here; the
FastAPI layer reads them. Keeping the store in ``core`` is what lets both
sides share it without ``agent_loop`` and ``backend.main`` importing each
other — the dependency runs one way, into ``core``.

SQLite is deliberate: the deployment target is a single monitoring node, the
write volume is a few hundred rows per polling cycle, and an operator needs to
be able to open the file and inspect an incident without any server running.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config import settings
from core.logging_utils import get_logger
from core.schemas import PipelineResult

log = get_logger("core.store")

_LOCK = threading.Lock()
_CONNECTION: Optional[sqlite3.Connection] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS intelligence (
    event_id        TEXT PRIMARY KEY,
    lat             REAL NOT NULL,
    lng             REAL NOT NULL,
    detected_at     TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    classification  TEXT,
    severity        TEXT,
    ai_confidence   REAL,
    sub_pixel_temp  REAL,
    linked_osm_node TEXT,
    requires_hitl   INTEGER DEFAULT 1,
    review_status   TEXT DEFAULT 'PENDING',
    gated_at_stage  INTEGER,
    cycle_id        TEXT,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intel_updated ON intelligence(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_intel_review  ON intelligence(review_status);
CREATE INDEX IF NOT EXISTS idx_intel_class   ON intelligence(classification);

CREATE TABLE IF NOT EXISTS cycles (
    cycle_id        TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    leo_detections  INTEGER DEFAULT 0,
    geo_frames      INTEGER DEFAULT 0,
    geo_source      TEXT,
    gated_biomass   INTEGER DEFAULT 0,
    processed       INTEGER DEFAULT 0,
    errors          INTEGER DEFAULT 0,
    duration_ms     REAL
);
"""


def _connect() -> sqlite3.Connection:
    global _CONNECTION
    if _CONNECTION is not None:
        return _CONNECTION
    with _LOCK:
        if _CONNECTION is not None:
            return _CONNECTION
        os.makedirs(os.path.dirname(settings.paths.intelligence_db), exist_ok=True)
        connection = sqlite3.connect(
            settings.paths.intelligence_db, check_same_thread=False
        )
        connection.row_factory = sqlite3.Row
        # WAL lets the API read while the agent loop writes.
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        connection.executescript(_SCHEMA)
        connection.commit()
        _CONNECTION = connection
        return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def save_result(result: PipelineResult) -> None:
    """Insert or update the intelligence record for one anomaly."""
    try:
        connection = _connect()
        fusion = result.fusion or {}
        payload = json.dumps(result.to_dict(), default=str)

        with _LOCK:
            connection.execute(
                """
                INSERT INTO intelligence (
                    event_id, lat, lng, detected_at, updated_at, classification,
                    severity, ai_confidence, sub_pixel_temp, linked_osm_node,
                    requires_hitl, review_status, gated_at_stage, cycle_id, payload
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(event_id) DO UPDATE SET
                    updated_at      = excluded.updated_at,
                    classification  = excluded.classification,
                    severity        = excluded.severity,
                    ai_confidence   = excluded.ai_confidence,
                    sub_pixel_temp  = excluded.sub_pixel_temp,
                    linked_osm_node = excluded.linked_osm_node,
                    requires_hitl   = excluded.requires_hitl,
                    gated_at_stage  = excluded.gated_at_stage,
                    cycle_id        = excluded.cycle_id,
                    payload         = excluded.payload,
                    -- An operator's decision is never overwritten by a later
                    -- automated pass; only untouched records revert to PENDING.
                    review_status   = CASE
                        WHEN intelligence.review_status IN ('CONFIRMED','DISMISSED')
                        THEN intelligence.review_status
                        ELSE excluded.review_status
                    END
                """,
                (
                    result.event_id,
                    result.lat,
                    result.lng,
                    result.detected_at,
                    _now(),
                    result.classification,
                    fusion.get("severity", "LOW"),
                    result.ai_confidence,
                    result.sub_pixel_temp,
                    result.linked_osm_node,
                    1 if fusion.get("requires_hitl", True) else 0,
                    "PENDING" if fusion.get("requires_hitl", True) else "AUTO_APPROVED",
                    result.gated_at_stage,
                    result.cycle_id,
                    payload,
                ),
            )
            connection.commit()
    except Exception as exc:
        log.warning("Failed to persist %s: %s", result.event_id, str(exc)[:160])


def save_results(results: List[PipelineResult]) -> int:
    saved = 0
    for result in results:
        save_result(result)
        saved += 1
    return saved


def start_cycle(cycle_id: str) -> None:
    try:
        connection = _connect()
        with _LOCK:
            connection.execute(
                "INSERT OR REPLACE INTO cycles (cycle_id, started_at) VALUES (?,?)",
                (cycle_id, _now()),
            )
            connection.commit()
    except Exception:
        pass


def finish_cycle(cycle_id: str, **stats: Any) -> None:
    try:
        connection = _connect()
        with _LOCK:
            connection.execute(
                """
                UPDATE cycles SET finished_at=?, leo_detections=?, geo_frames=?,
                    geo_source=?, gated_biomass=?, processed=?, errors=?, duration_ms=?
                WHERE cycle_id=?
                """,
                (
                    _now(),
                    int(stats.get("leo_detections", 0)),
                    int(stats.get("geo_frames", 0)),
                    str(stats.get("geo_source", "")),
                    int(stats.get("gated_biomass", 0)),
                    int(stats.get("processed", 0)),
                    int(stats.get("errors", 0)),
                    float(stats.get("duration_ms", 0.0)),
                    cycle_id,
                ),
            )
            connection.commit()
    except Exception:
        pass


def set_review_status(event_id: str, status: str) -> bool:
    """Record an operator's decision on an anomaly."""
    try:
        connection = _connect()
        with _LOCK:
            cursor = connection.execute(
                "UPDATE intelligence SET review_status=?, updated_at=? WHERE event_id=?",
                (status, _now(), event_id),
            )
            connection.commit()
            return cursor.rowcount > 0
    except Exception as exc:
        log.warning("Failed to update review status: %s", str(exc)[:160])
        return False


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def _row_to_payload(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        payload = json.loads(row["payload"])
    except Exception:
        payload = {}
    payload["review_status"] = row["review_status"]
    return payload


def recent_results(limit: int = 500, since_hours: Optional[float] = None) -> List[Dict[str, Any]]:
    try:
        connection = _connect()
        query = "SELECT * FROM intelligence"
        params: List[Any] = []
        if since_hours:
            query += " WHERE updated_at >= datetime('now', ?)"
            params.append(f"-{float(since_hours)} hours")
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(limit))
        with _LOCK:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_payload(row) for row in rows]
    except Exception as exc:
        log.warning("Read failed: %s", str(exc)[:160])
        return []


def pending_reviews(limit: int = 100) -> List[Dict[str, Any]]:
    try:
        connection = _connect()
        with _LOCK:
            rows = connection.execute(
                """
                SELECT * FROM intelligence
                WHERE review_status='PENDING' AND requires_hitl=1
                ORDER BY ai_confidence ASC, updated_at DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [_row_to_payload(row) for row in rows]
    except Exception:
        return []


def get_result(event_id: str) -> Optional[Dict[str, Any]]:
    try:
        connection = _connect()
        with _LOCK:
            row = connection.execute(
                "SELECT * FROM intelligence WHERE event_id=?", (event_id,)
            ).fetchone()
        return _row_to_payload(row) if row else None
    except Exception:
        return None


def statistics() -> Dict[str, Any]:
    """Aggregate counters for the dashboard's status panel."""
    try:
        connection = _connect()
        with _LOCK:
            total = connection.execute("SELECT COUNT(*) c FROM intelligence").fetchone()["c"]
            pending = connection.execute(
                "SELECT COUNT(*) c FROM intelligence WHERE review_status='PENDING'"
            ).fetchone()["c"]
            by_class = connection.execute(
                "SELECT classification, COUNT(*) c FROM intelligence GROUP BY classification"
            ).fetchall()
            last_cycle = connection.execute(
                "SELECT * FROM cycles ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return {
            "total_events": total,
            "pending_review": pending,
            "by_classification": {r["classification"] or "UNKNOWN": r["c"] for r in by_class},
            "last_cycle": dict(last_cycle) if last_cycle else None,
        }
    except Exception:
        return {"total_events": 0, "pending_review": 0, "by_classification": {}, "last_cycle": None}


def recently_processed_ids(within_seconds: int) -> Dict[str, str]:
    """Event ids already analysed recently, so a cycle can skip re-work."""
    try:
        connection = _connect()
        with _LOCK:
            rows = connection.execute(
                "SELECT event_id, updated_at FROM intelligence "
                "WHERE updated_at >= datetime('now', ?)",
                (f"-{int(within_seconds)} seconds",),
            ).fetchall()
        return {row["event_id"]: row["updated_at"] for row in rows}
    except Exception:
        return {}


__all__ = [
    "save_result",
    "save_results",
    "start_cycle",
    "finish_cycle",
    "set_review_status",
    "recent_results",
    "pending_reviews",
    "get_result",
    "statistics",
    "recently_processed_ids",
]
