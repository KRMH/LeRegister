"""Ports owned by the core. Adapters implement them."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """The only way core reads time."""

    def now(self) -> datetime:
        """Current timezone-aware instant."""
        ...
