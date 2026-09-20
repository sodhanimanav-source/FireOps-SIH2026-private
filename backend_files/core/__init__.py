"""
FireOps Core
============

Shared infrastructure for the 6-stage Multi-Modal Industrial Fire
Classification pipeline.

This package deliberately contains **no model logic and no I/O**. It only
holds configuration, structured logging and the dataclass contracts that
the pipeline stages exchange.

Dependency rule (enforced by tests/test_pipeline.py):

    core  <-  ingestion  <-  models  <-  agent_loop  <-  backend

`core` imports nothing from the project, so no stage can ever create a
circular import by depending on the shared contracts.
"""

from core.config import settings
from core.logging_utils import get_logger, stage_span

__all__ = ["settings", "get_logger", "stage_span"]
