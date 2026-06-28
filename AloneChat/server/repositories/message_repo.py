"""
Message repository for AloneChat server.

Provides data-access methods for private messages stored in ClickHouse.
Receives a ClickHouse client connection via __init__ and uses exclusively
parameterized SQL queries.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from AloneChat.server.database import get_client

logger = logging.getLogger(__name__)


class MessageRepository:
    """Data-access layer for private messages in ClickHouse.

    Parameters
    ----------
    client : optional
        A ClickHouse driver ``Client`` instance.  When omitted (or ``None``)
        the repository lazily fetches one from the module-level ``get_client``.
    db : optional
        A ``Database`` handle from the DI container.  Accepted for
        compatibility with the container's injection pattern.
    """

    def __init__(self, client: Optional[Any] = None, db: Optional[Any] = None):
        # Accept either a raw ClickHouse client or a Database handle.
        if client is not None:
            self._client = client
        elif db is not None:
            self._client = getattr(db, "_client", None)
        else:
            self._client = None
        self._enabled = self._client is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return a working ClickHouse client, reconnecting on failure."""
        if self._client is None:
            self._client = get_client()
            self._enabled = self._client is not None
        return self._client

    def _safe_execute(self, query: str, params: Optional[Dict[str, Any]] = None):
        """Execute a parameterized query with automatic reconnection on error.

        Raises
        ------
        Exception
            If the database is unavailable even after a reconnect attempt.
        """
        client = self._get_client()
        if client is None:
            raise Exception("Database not available")

        try:
            if params is not None:
                return client.execute(query, params)
            return client.execute(query)
        except Exception:
            logger.warning(
                "Query failed, attempting reconnect. Query: %.120s", query
            )
            self._client = None
            client = self._get_client()
            if client is None:
                raise Exception("Database reconnection failed")
            if params is not None:
                return client.execute(query, params)
            return client.execute(query)

    @property
    def is_enabled(self) -> bool:
        """``True`` when the repository has a working database connection."""
        return self._enabled

    def _ensure_connected(self) -> bool:
        """Trigger lazy ClickHouse connection on first use."""
        return self._get_client() is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_private_message(
        self,
        msg_id: str,
        sender: str,
        recipient: str,
        content: str,
        delivered: bool = False,
    ) -> bool:
        """Persist a private message to ClickHouse.

        Returns ``True`` on success, ``False`` when the database is disabled
        or an unexpected error occurs.
        """
        if not self._ensure_connected():
            return False

        try:
            self._safe_execute(
                "INSERT INTO private_messages "
                "(id, sender, recipient, content, timestamp, delivered) "
                "VALUES",
                [
                    {
                        "id": msg_id,
                        "sender": sender,
                        "recipient": recipient,
                        "content": content,
                        "timestamp": datetime.now(),
                        "delivered": 1 if delivered else 0,
                    }
                ],
            )
            return True
        except Exception:
            logger.exception(
                "save_private_message failed: msg_id=%s sender=%s recipient=%s",
                msg_id,
                sender,
                recipient,
            )
            return False

    def save_broadcast_messages(
        self,
        sender: str,
        recipients: list[str],
        content: str,
    ) -> bool:
        """Persist one broadcast message to many recipients in a single INSERT.

        Returns True on success.
        """
        if not recipients or not self._ensure_connected():
            return False

        import uuid as _uuid
        now = datetime.now()
        rows = [
            {
                "id": str(_uuid.uuid4()),
                "sender": sender,
                "recipient": uid,
                "content": content,
                "timestamp": now,
                "delivered": 0,
            }
            for uid in recipients
        ]

        try:
            self._safe_execute(
                "INSERT INTO private_messages "
                "(id, sender, recipient, content, timestamp, delivered) VALUES",
                rows,
            )
            return True
        except Exception:
            logger.exception("save_broadcast_messages failed: %d recipients", len(recipients))
            return False

    def get_undelivered_messages(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve undelivered messages for *user_id* (offline recovery).

        Returns list of dicts with sender/content/timestamp keys.
        """
        if not self._ensure_connected():
            return []

        try:
            rows = self._safe_execute(
                "SELECT sender, content, timestamp "
                "FROM private_messages "
                "WHERE recipient = %(uid)s AND delivered = 0 "
                "ORDER BY timestamp ASC "
                "LIMIT 200",
                {"uid": user_id},
            )
            return [
                {"sender": r[0], "content": r[1], "timestamp": r[2]}
                for r in rows
            ]
        except Exception:
            logger.exception("get_undelivered_messages failed for %s", user_id)
            return []

    def mark_delivered(self, user_id: str) -> None:
        """Mark all undelivered messages for *user_id* as delivered."""
        if not self._ensure_connected():
            return

        try:
            self._safe_execute(
                "ALTER TABLE private_messages "
                "UPDATE delivered = 1 "
                "WHERE recipient = %(uid)s AND delivered = 0",
                {"uid": user_id},
            )
        except Exception:
            # ALTER TABLE UPDATE on MergeTree is lightweight; if it fails
            # messages will be re-delivered on next connect (idempotent).
            logger.warning("mark_delivered failed for %s", user_id)

    def get_private_messages(
        self,
        user1: str,
        user2: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve the most recent private messages between two users.

        The result is returned in ascending chronological order (oldest
        first).  Each element is a dict with keys ``sender``, ``content``,
        and ``timestamp``.

        Returns an empty list when the database is disabled or an error
        occurs.
        """
        if not self._ensure_connected():
            return []

        try:
            result = self._safe_execute(
                "SELECT sender, content, timestamp "
                "FROM private_messages "
                "WHERE (sender = %(u1)s AND recipient = %(u2)s) "
                "   OR (sender = %(u2)s AND recipient = %(u1)s) "
                "ORDER BY timestamp DESC "
                "LIMIT %(limit)s",
                {"u1": user1, "u2": user2, "limit": limit},
            )
            return [
                {"sender": row[0], "content": row[1], "timestamp": row[2]}
                for row in reversed(result)
            ]
        except Exception:
            logger.exception(
                "get_private_messages failed: user1=%s user2=%s limit=%s",
                user1,
                user2,
                limit,
            )
            return []
