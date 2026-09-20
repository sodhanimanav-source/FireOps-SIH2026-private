"""
Structured, stage-aware logging for the FireOps pipeline.

Every pipeline stage emits records tagged with the stage number, the event id
and the wall-clock duration, so a failure in a national-scale monitoring loop
can be traced to an exact anomaly and an exact encoder.

Usage
-----
    log = get_logger("stage2.physics")

    with stage_span(log, stage=2, name="planck_inversion", event_id=evt) as span:
        span["subpixel_temp_k"] = 1843.2
        ...

The span context manager records duration, success/failure and any fields the
stage attaches, then emits a single structured line. Exceptions are logged
with a traceback and re-raised — the orchestrator decides on the fallback,
not the logger.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from core.config import settings

_CONFIGURED = False
_CONFIG_LOCK = threading.Lock()

# Correlation id for the current processing cycle, so interleaved logs from the
# parallel Stage 3/4/5 workers can be grouped back together.
_CONTEXT = threading.local()


class _JsonFormatter(logging.Formatter):
    """One JSON object per line — ready for Loki / CloudWatch ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("stage", "event_id", "duration_ms", "outcome", "cycle_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        extra = getattr(record, "fields", None)
        if extra:
            payload["fields"] = extra
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _HumanFormatter(logging.Formatter):
    """Readable console output for local development and demo runs."""

    _STAGE_TAGS = {
        0: "ORCHESTRATOR",
        1: "S1-INGEST  ",
        2: "S2-PHYSICS ",
        3: "S3-GRAPH   ",
        4: "S4-VISION  ",
        5: "S5-TIME    ",
        6: "S6-FUSION  ",
    }

    def format(self, record: logging.LogRecord) -> str:
        stage = getattr(record, "stage", None)
        tag = self._STAGE_TAGS.get(stage, "SYSTEM     ") if stage is not None else "SYSTEM     "
        stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        parts = [f"{stamp} [{tag}] {record.levelname:<7} {record.getMessage()}"]

        event_id = getattr(record, "event_id", None)
        if event_id:
            parts.append(f"evt={event_id}")
        duration = getattr(record, "duration_ms", None)
        if duration is not None:
            parts.append(f"{duration:.0f}ms")
        fields = getattr(record, "fields", None)
        if fields:
            rendered = " ".join(
                f"{k}={_render(v)}" for k, v in fields.items() if v is not None
            )
            if rendered:
                parts.append(rendered)
        line = " | ".join(parts)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def _render(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)[:160]
    return str(value)


def _configure() -> None:
    global _CONFIGURED
    with _CONFIG_LOCK:
        if _CONFIGURED:
            return
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter() if settings.log_json else _HumanFormatter())

        root = logging.getLogger("fireops")
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(getattr(logging, settings.log_level, logging.INFO))
        root.propagate = False

        # Third-party libraries are noisy at INFO; keep the operator console clean.
        for noisy in ("urllib3", "httpx", "transformers", "huggingface_hub", "filelock"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
        _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the shared ``fireops`` root."""
    _configure()
    return logging.getLogger(f"fireops.{name}")


def new_cycle_id() -> str:
    """Start a new correlation scope for one polling cycle."""
    cycle_id = uuid.uuid4().hex[:8]
    _CONTEXT.cycle_id = cycle_id
    return cycle_id


def current_cycle_id() -> Optional[str]:
    return getattr(_CONTEXT, "cycle_id", None)


def bind_cycle_id(cycle_id: Optional[str]) -> None:
    """Propagate the cycle id into a worker thread (thread-locals don't inherit)."""
    _CONTEXT.cycle_id = cycle_id


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    stage: Optional[int] = None,
    event_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    outcome: Optional[str] = None,
    exc_info: Any = None,
    **fields: Any,
) -> None:
    """Emit a structured record without needing a span."""
    logger.log(
        level,
        message,
        exc_info=exc_info,
        extra={
            "stage": stage,
            "event_id": event_id,
            "duration_ms": duration_ms,
            "outcome": outcome,
            "cycle_id": current_cycle_id(),
            "fields": fields or None,
        },
    )


@contextmanager
def stage_span(
    logger: logging.Logger,
    stage: int,
    name: str,
    event_id: Optional[str] = None,
    level: int = logging.INFO,
) -> Iterator[Dict[str, Any]]:
    """
    Time a pipeline stage and emit exactly one structured record for it.

    Fields written into the yielded dict are included in the final record, so
    a stage reports its scientific outputs (temperature, node count, period)
    in the same line as its timing.
    """
    started = time.perf_counter()
    fields: Dict[str, Any] = {}
    try:
        yield fields
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000.0
        log_event(
            logger,
            logging.ERROR,
            f"{name} failed",
            stage=stage,
            event_id=event_id,
            duration_ms=duration_ms,
            outcome="error",
            exc_info=True,
            **fields,
        )
        raise
    else:
        duration_ms = (time.perf_counter() - started) * 1000.0
        log_event(
            logger,
            level,
            name,
            stage=stage,
            event_id=event_id,
            duration_ms=duration_ms,
            outcome=fields.pop("outcome", "ok"),
            **fields,
        )


__all__ = [
    "get_logger",
    "stage_span",
    "log_event",
    "new_cycle_id",
    "current_cycle_id",
    "bind_cycle_id",
]
