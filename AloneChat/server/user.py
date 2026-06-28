"""
User management service for AloneChat.

Pure user management logic without transport concerns.
Receives UserRepository and AuthService via ``__init__`` — no global
``get_*()`` calls.  All database access goes through the repository.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

from AloneChat.server.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class Status(Enum):
    """User online-status enumeration."""

    ONLINE = auto()
    AWAY = auto()
    BUSY = auto()
    OFFLINE = auto()


@dataclass
class UserInfo:
    """Lightweight user-information transfer object."""

    user_id: str
    status: Status = Status.ONLINE
    display_name: str = ""
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "status": self.status.name.lower(),
            "display_name": self.display_name,
            "last_seen": self.last_seen,
            "is_online": self.status != Status.OFFLINE,
        }


# ---------------------------------------------------------------------------
# StatusBuffer — batching writes to reduce database load
# ---------------------------------------------------------------------------


class StatusBuffer:
    """Buffer for batching status updates to reduce database writes.

    Features:
    - Batches multiple status updates before writing to the repository
    - Auto-flushes every *flush_interval* seconds
    - Auto-flushes when buffer reaches *max_size*
    - Thread-safe for concurrent access
    """

    def __init__(
        self,
        user_repo: UserRepository,
        flush_interval: float = 5.0,
        max_size: int = 50,
    ) -> None:
        self._user_repo = user_repo
        self._buffer: Dict[str, Dict[str, Any]] = {}
        self._flush_interval = flush_interval
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._last_flush = time.time()
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Begin the periodic flush loop as a background asyncio task."""
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(
            "StatusBuffer started with flush_interval=%.1fs, max_size=%d",
            self._flush_interval,
            self._max_size,
        )

    async def stop(self) -> None:
        """Cancel the flush loop and flush any remaining updates."""
        self._running = False
        await self.force_flush()
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        logger.info("StatusBuffer stopped")

    async def _flush_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
            except asyncio.CancelledError:
                break
            if self._running and self._buffer:
                await self.flush()

    async def add(
        self, user_id: str, status: str, is_online: bool
    ) -> bool:
        """Queue a status update; flushes immediately if buffer is full."""
        should_flush = False

        async with self._lock:
            self._buffer[user_id] = {
                "user_id": user_id,
                "status": status,
                "is_online": is_online,
            }
            if len(self._buffer) >= self._max_size:
                should_flush = True

        if should_flush:
            return await self.flush()
        return False

    async def get_pending_count(self) -> int:
        """Return the number of buffered (unflushed) updates."""
        async with self._lock:
            return len(self._buffer)

    async def flush(self) -> bool:
        """Flush buffered updates to the database.

        Returns ``True`` when at least one update was successfully written.
        """
        async with self._lock:
            if not self._buffer:
                return False
            updates = list(self._buffer.values())
            self._buffer.clear()
            self._last_flush = time.time()

        if updates:
            count = self._user_repo.batch_update_status(updates)
            if count > 0:
                logger.debug("Flushed %d status updates to database", count)
                return True
        return False

    async def force_flush(self) -> int:
        """Flush everything immediately and return the count of updates."""
        async with self._lock:
            updates = list(self._buffer.values())
            self._buffer.clear()
            self._last_flush = time.time()

        if updates:
            return self._user_repo.batch_update_status(updates)
        return 0

    async def clear(self) -> None:
        """Discard all buffered updates without writing them."""
        async with self._lock:
            self._buffer.clear()


# ---------------------------------------------------------------------------
# UserService
# ---------------------------------------------------------------------------


class UserService:
    """Pure user management service — no transport concerns.

    Receives ``UserRepository`` and ``AuthService`` via ``__init__``.
    All database access is delegated to the repository.  Status updates
    are batched through an internal :class:`StatusBuffer` for efficiency.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        auth_service: Any,
        flush_interval: float = 5.0,
        max_buffer_size: int = 50,
    ) -> None:
        self._user_repo = user_repo
        self._auth_service = auth_service
        self._online_users: Dict[str, UserInfo] = {}
        self._user_connections: Dict[str, int] = {}
        self._status_buffer = StatusBuffer(
            user_repo=user_repo,
            flush_interval=flush_interval,
            max_size=max_buffer_size,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_buffer_started(self) -> None:
        """Schedule the background flush loop if not already running.

        Must be called from within a running event loop.
        """
        if not self._status_buffer._running:
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self._status_buffer.start())
            except RuntimeError:
                # No running event loop yet — buffer flushes will be explicit.
                pass

    async def shutdown(self) -> None:
        """Flush all pending status updates and stop the background loop."""
        await self._status_buffer.stop()

    # ------------------------------------------------------------------
    # Authentication (delegated)
    # ------------------------------------------------------------------

    def register(self, username: str, password: str):
        """Delegate user registration to :class:`AuthService`."""
        return self._auth_service.register(username, password)

    def authenticate(self, username: str, password: str):
        """Delegate authentication to :class:`AuthService`."""
        return self._auth_service.authenticate(username, password)

    # ------------------------------------------------------------------
    # Online / offline tracking
    # ------------------------------------------------------------------

    async def set_online(self, user_id: str) -> None:
        """Mark a user as online and track a connection reference."""
        self._ensure_buffer_started()

        if user_id not in self._online_users:
            user_data = self._user_repo.get_user(user_id)
            display_name = user_data.display_name if user_data else user_id
            self._online_users[user_id] = UserInfo(
                user_id=user_id,
                status=Status.ONLINE,
                display_name=display_name,
            )
        else:
            self._online_users[user_id].status = Status.ONLINE
            self._online_users[user_id].last_seen = time.time()

        self._user_connections[user_id] = (
            self._user_connections.get(user_id, 0) + 1
        )
        await self._status_buffer.add(user_id, "online", True)

    async def set_offline(self, user_id: str) -> None:
        """Decrement connection count; mark offline when it reaches zero."""
        if user_id not in self._user_connections:
            return

        self._user_connections[user_id] -= 1
        if self._user_connections[user_id] <= 0:
            del self._user_connections[user_id]
            if user_id in self._online_users:
                self._online_users[user_id].status = Status.OFFLINE
                self._online_users[user_id].last_seen = time.time()
            await self._status_buffer.add(user_id, "offline", False)

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    async def update_status(self, user_id: str, status: Status) -> bool:
        """Set a user's status (online/away/busy/offline).

        Returns ``False`` when the user is not currently tracked as online.
        """
        if user_id not in self._online_users:
            return False

        self._online_users[user_id].status = status
        self._online_users[user_id].last_seen = time.time()

        status_str = status.name.lower()
        is_online = status != Status.OFFLINE
        await self._status_buffer.add(user_id, status_str, is_online)
        return True

    # Legacy alias — matches the pre-migration API name
    async def set_status(self, user_id: str, status: Status) -> bool:
        """Alias for :meth:`update_status`."""
        return await self.update_status(user_id, status)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_online(self, user_id: str) -> bool:
        """Return ``True`` when *user_id* is tracked as online."""
        info = self._online_users.get(user_id)
        return info is not None and info.status != Status.OFFLINE

    def get_online_users(self) -> List[str]:
        """Return the user IDs of all currently online users."""
        return [
            uid
            for uid, info in self._online_users.items()
            if info.status != Status.OFFLINE
        ]

    def get_user_info(self, user_id: str) -> Optional[UserInfo]:
        """Retrieve a :class:`UserInfo` for *user_id*.

        Checks the in-memory online map first, falling back to the
        database for offline users.
        """
        if user_id in self._online_users:
            return self._online_users[user_id]

        user_data = self._user_repo.get_user(user_id)
        if user_data:
            return UserInfo(
                user_id=user_data.user_id,
                status=Status.OFFLINE,
                display_name=user_data.display_name,
                last_seen=(
                    user_data.last_seen.timestamp()
                    if user_data.last_seen
                    else 0
                ),
            )
        return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Return every known user, merging in-memory state with the DB."""
        users = self._user_repo.get_all_users()
        result: List[Dict[str, Any]] = []
        for u in users:
            info = self._online_users.get(u.user_id)
            if info:
                result.append(info.to_dict())
            else:
                result.append(
                    {
                        "user_id": u.user_id,
                        "status": u.status,
                        "display_name": u.display_name,
                        "last_seen": (
                            u.last_seen.timestamp()
                            if u.last_seen
                            else 0
                        ),
                        "is_online": u.is_online,
                    }
                )
        return result

    def user_exists(self, user_id: str) -> bool:
        """Check whether a user row exists in the database."""
        return self._user_repo.user_exists(user_id)

    # ------------------------------------------------------------------
    # Status buffer helpers
    # ------------------------------------------------------------------

    async def flush_status_buffer(self) -> int:
        """Force-flush the status-update buffer to the database."""
        return await self._status_buffer.force_flush()

    async def get_pending_status_count(self) -> int:
        """Return the number of buffered (unwritten) status updates."""
        return await self._status_buffer.get_pending_count()
