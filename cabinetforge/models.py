"""Data models used by CabinetForge."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock

from .cab_editor import CabEditor


@dataclass
class Workspace:
    """Per-user mutable workspace holding one editor instance and lock."""

    editor: CabEditor = field(default_factory=CabEditor)
    lock: RLock = field(default_factory=RLock)
    last_access: datetime = field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        """Refresh last-access timestamp for cleanup bookkeeping."""

        self.last_access = datetime.utcnow()
