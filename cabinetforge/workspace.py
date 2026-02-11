"""Session-scoped workspace management for concurrent users."""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import RLock
from uuid import uuid4

from flask import session

from .models import Workspace


class WorkspaceManager:
    """Store and retrieve per-session editor workspaces."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._state: dict[str, Workspace] = {}
        self._lock = RLock()

    def current(self) -> Workspace:
        """Return workspace for current session, creating one if needed."""

        with self._lock:
            self._purge_expired()
            wsid = session.get("wsid")
            if not wsid:
                wsid = uuid4().hex
                session["wsid"] = wsid

            workspace = self._state.get(wsid)
            if workspace is None:
                workspace = Workspace()
                self._state[wsid] = workspace

            workspace.touch()
            return workspace

    def _purge_expired(self) -> None:
        cutoff = datetime.utcnow() - self._ttl
        stale = [wsid for wsid, ws in self._state.items() if ws.last_access < cutoff]
        for wsid in stale:
            self._state.pop(wsid, None)
