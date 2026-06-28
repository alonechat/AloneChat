"""
User data-access repository for AloneChat.

Pure ClickHouse SQL queries — no business logic.  Every method that takes
user-supplied values uses parameterised queries (``%(name)s`` style).

When ClickHouse is unavailable the repository falls back to an in-memory
store so that the application remains functional for development and testing.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from AloneChat.server.repositories.base import BaseRepository, UserData

logger = logging.getLogger(__name__)

# Module-level in-memory store used as a fallback when ClickHouse is
# unavailable.  Keys are user_id strings, values are UserData instances.
_memory_store: Dict[str, UserData] = {}


class UserRepository(BaseRepository):
    """Data access for the ``users`` table (ReplacingMergeTree).

    Receives a ClickHouse client via the constructor and delegates
    connection management to :class:`BaseRepository`.

    When the database backend is unavailable every method transparently
    falls back to an in-memory :class:`dict` so that the service layer
    never receives a hard error for routine user lookups.
    """

    # ------------------------------------------------------------------
    # Internal: lazy-connect helper
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> bool:
        """Trigger lazy ClickHouse connection on first use.

        Returns True if ClickHouse is now available, False if in-memory
        fallback is active.
        """
        # _get_client() attempts to connect if not already connected.
        # After this call, is_enabled reflects the real state.
        return self._get_client() is not None

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_user(
        self,
        user_id: str,
        password_hash: str,
        display_name: str = "",
    ) -> bool:
        """Insert a new user row.  Returns True on success."""
        if self._ensure_connected():
            query = """
                INSERT INTO users (user_id, password_hash, display_name)
                VALUES (%(user_id)s, %(password_hash)s, %(display_name)s)
            """
            params = {
                "user_id": user_id,
                "password_hash": password_hash,
                "display_name": display_name,
            }
            try:
                self._safe_execute(query, params)
                logger.info("User created (CH): %s", user_id)
                return True
            except Exception:
                logger.exception("Failed to create user (CH): %s", user_id)

        # In-memory fallback.
        if user_id in _memory_store:
            return False
        _memory_store[user_id] = UserData(
            user_id=user_id,
            password_hash=password_hash,
            display_name=display_name,
            status="offline",
            is_online=False,
            created_at=datetime.now(timezone.utc),
        )
        logger.info("User created (memory): %s", user_id)
        return True

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_user(self, user_id: str) -> Optional[UserData]:
        """Retrieve a single user by id.  Returns None when not found."""
        if self._ensure_connected():
            query = """
                SELECT
                    user_id,
                    password_hash,
                    display_name,
                    status,
                    is_online,
                    last_seen,
                    created_at
                FROM users FINAL
                WHERE user_id = %(user_id)s
                LIMIT 1
            """
            params = {"user_id": user_id}
            try:
                rows = self._safe_execute(query, params)
                if rows:
                    row = rows[0]
                    return UserData(
                        user_id=row[0],
                        password_hash=row[1],
                        display_name=row[2] or "",
                        status=row[3] or "offline",
                        is_online=bool(row[4]),
                        last_seen=row[5],
                        created_at=row[6],
                    )
            except Exception:
                logger.exception("Failed to get user (CH): %s", user_id)

        return _memory_store.get(user_id)

    def user_exists(self, user_id: str) -> bool:
        """Check whether a user row exists."""
        if self._ensure_connected():
            query = """
                SELECT count() AS cnt
                FROM users FINAL
                WHERE user_id = %(user_id)s
            """
            params = {"user_id": user_id}
            try:
                rows = self._safe_execute(query, params)
                if rows and rows[0][0] > 0:
                    return True
            except Exception:
                logger.exception("Failed to check user existence (CH): %s", user_id)

        return user_id in _memory_store

    def get_all_users(self) -> List[UserData]:
        """Return every user in the table."""
        if self._ensure_connected():
            query = """
                SELECT
                    user_id,
                    password_hash,
                    display_name,
                    status,
                    is_online,
                    last_seen,
                    created_at
                FROM users FINAL
            """
            try:
                rows = self._safe_execute(query)
                if rows:
                    return [
                        UserData(
                            user_id=row[0],
                            password_hash=row[1],
                            display_name=row[2] or "",
                            status=row[3] or "offline",
                            is_online=bool(row[4]),
                            last_seen=row[5],
                            created_at=row[6],
                        )
                        for row in rows
                    ]
            except Exception:
                logger.exception("Failed to get all users (CH)")

        return list(_memory_store.values())

    def get_online_users(self) -> List[UserData]:
        """Return users whose ``is_online`` flag is set."""
        if self._ensure_connected():
            query = """
                SELECT
                    user_id,
                    password_hash,
                    display_name,
                    status,
                    is_online,
                    last_seen,
                    created_at
                FROM users FINAL
                WHERE is_online = 1
            """
            try:
                rows = self._safe_execute(query)
                if rows:
                    return [
                        UserData(
                            user_id=row[0],
                            password_hash=row[1],
                            display_name=row[2] or "",
                            status=row[3] or "offline",
                            is_online=bool(row[4]),
                            last_seen=row[5],
                            created_at=row[6],
                        )
                        for row in rows
                    ]
            except Exception:
                logger.exception("Failed to get online users (CH)")

        return [u for u in _memory_store.values() if u.is_online]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_status(
        self, user_id: str, status: str, is_online: bool
    ) -> bool:
        """Set status and online flag for a single user.  Returns True on success.

        Uses INSERT…SELECT to create a new row version (ReplacingMergeTree
        deduplicates by ``user_id``, keeping the row with the highest
        ``updated_at``).
        """
        if self._ensure_connected():
            query = """
                INSERT INTO users (user_id, password_hash, display_name, status, is_online, last_seen, updated_at)
                SELECT
                    user_id,
                    argMax(password_hash, updated_at),
                    argMax(display_name, updated_at),
                    %(status)s,
                    %(is_online)s,
                    %(now)s,
                    %(now)s
                FROM users
                WHERE user_id = %(user_id)s
                GROUP BY user_id
            """
            params = {
                "user_id": user_id,
                "status": status,
                "is_online": 1 if is_online else 0,
                "now": datetime.now(timezone.utc),
            }
            try:
                self._safe_execute(query, params)
            except Exception:
                logger.exception("Failed to update status (CH): %s", user_id)

        if user_id in _memory_store:
            _memory_store[user_id].status = status
            _memory_store[user_id].is_online = is_online
            _memory_store[user_id].last_seen = datetime.now(timezone.utc)
            return True
        return False

    def batch_update_status(
        self, updates: List[Dict[str, Any]]
    ) -> int:
        """Apply multiple status updates.  Returns count of successful updates."""
        if not updates:
            return 0
        count = 0
        for upd in updates:
            if self.update_status(
                user_id=upd["user_id"],
                status=upd["status"],
                is_online=upd["is_online"],
            ):
                count += 1
        return count

    def set_all_offline(self) -> int:
        """Mark every user as offline.  Returns count of users that were online."""
        online_count = 0

        if self._ensure_connected():
            try:
                rows = self._safe_execute(
                    "SELECT count() FROM users FINAL WHERE is_online = 1"
                )
                online_count = rows[0][0] if rows else 0
            except Exception:
                pass

            try:
                self._safe_execute("""
                    INSERT INTO users (user_id, password_hash, display_name, status, is_online, last_seen, updated_at)
                    SELECT
                        user_id,
                        argMax(password_hash, updated_at),
                        argMax(display_name, updated_at),
                        'offline',
                        0,
                        now(),
                        now()
                    FROM users
                    WHERE is_online = 1
                    GROUP BY user_id
                """)
                logger.info("Set all users offline (was %s online)", online_count)
            except Exception:
                logger.exception("Failed to set all users offline (CH)")

        for u in _memory_store.values():
            if u.is_online:
                online_count += 1
                u.is_online = False
                u.status = "offline"
                u.last_seen = datetime.now(timezone.utc)

        return online_count
