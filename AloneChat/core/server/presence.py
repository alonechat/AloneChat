"""Presence tracking for AloneChat.

Tracks online status per-user across multiple devices (connections) using heartbeat.
This module is intentionally simple and uses in-memory state.

Design:
- A user can have up to MAX_CONNECTIONS connections.
- Each connection has a conn_id, device_id and last_heartbeat timestamp.
- A user is considered online if they have at least 1 active connection.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


MAX_CONNECTIONS = 3
HEARTBEAT_TIMEOUT_SECONDS = 30.0


@dataclass
class PresenceConn:
    conn_id: str
    device_id: str
    created_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_heartbeat = time.time()

    def is_stale(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return (now - self.last_heartbeat) > HEARTBEAT_TIMEOUT_SECONDS


# user -> conn_id -> PresenceConn
_presence: Dict[str, Dict[str, PresenceConn]] = {}


def new_ids(device_id: Optional[str] = None) -> Tuple[str, str]:
    """Generate (conn_id, device_id)."""
    return uuid.uuid4().hex, (device_id or uuid.uuid4().hex)


def register(user: str, conn_id: str, device_id: str) -> Optional[str]:
    """Register a connection. Returns conn_id to evict (if any)."""
    conns = _presence.setdefault(user, {})
    conns[conn_id] = PresenceConn(conn_id=conn_id, device_id=device_id)
    # Enforce max connections by evicting the stalest/oldest
    if len(conns) > MAX_CONNECTIONS:
        # choose oldest by last_heartbeat then created_at
        items = list(conns.values())
        items.sort(key=lambda c: (c.last_heartbeat, c.created_at))
        evict = items[0].conn_id
        if evict != conn_id:
            conns.pop(evict, None)
            return evict
    return None


def unregister(user: str, conn_id: str) -> None:
    conns = _presence.get(user)
    if not conns:
        return
    conns.pop(conn_id, None)
    if not conns:
        _presence.pop(user, None)


def touch(user: str, conn_id: str) -> None:
    conns = _presence.get(user)
    if not conns:
        return
    c = conns.get(conn_id)
    if c:
        c.touch()


def is_online(user: str) -> bool:
    conns = _presence.get(user)
    return bool(conns)


def online_users() -> List[str]:
    return sorted(_presence.keys())


def snapshot() -> Dict[str, Dict[str, bool]]:
    """Return {username: {device_id: online}}."""
    out: Dict[str, Dict[str, bool]] = {}
    for u, conns in _presence.items():
        out[u] = {c.device_id: True for c in conns.values()}
    return out


def prune_stale(now: Optional[float] = None) -> List[Tuple[str, str]]:
    """Remove stale connections. Returns list of (user, conn_id) removed."""
    now = time.time() if now is None else now
    removed: List[Tuple[str, str]] = []
    for user in list(_presence.keys()):
        conns = _presence.get(user, {})
        for conn_id, c in list(conns.items()):
            if c.is_stale(now):
                conns.pop(conn_id, None)
                removed.append((user, conn_id))
        if not conns:
            _presence.pop(user, None)
    return removed
