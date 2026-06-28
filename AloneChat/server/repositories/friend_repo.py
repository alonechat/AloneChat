"""
Friend repository for AloneChat server.

Provides data-access methods for friend relationships and friend requests
stored in ClickHouse.  Receives a ClickHouse client connection via __init__
and uses exclusively parameterized SQL queries.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from AloneChat.server.database import get_client

logger = logging.getLogger(__name__)


class FriendRepository:
    """Data-access layer for friendships and friend requests in ClickHouse.

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

    def _ensure_connected(self) -> bool:
        """Trigger lazy ClickHouse connection on first use."""
        return self._get_client() is not None

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

    # ------------------------------------------------------------------
    # Friendship CRUD
    # ------------------------------------------------------------------

    def add_friend(
        self,
        user_id: str,
        friend_id: str,
        remark: str = "",
    ) -> bool:
        """Create a bidirectional friendship between two users.

        Both directions are inserted in a single batch so that each user sees
        the other in their friend list.  Returns ``True`` on success, ``False``
        when the database is disabled or an error occurs.
        """
        if not self._ensure_connected():
            return False

        try:
            now = datetime.now()
            self._safe_execute(
                "INSERT INTO friendships "
                "(user_id, friend_id, remark, created_at, updated_at) "
                "VALUES",
                [
                    {
                        "user_id": user_id,
                        "friend_id": friend_id,
                        "remark": remark,
                        "created_at": now,
                        "updated_at": now,
                    },
                    {
                        "user_id": friend_id,
                        "friend_id": user_id,
                        "remark": "",
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )
            return True
        except Exception:
            logger.exception(
                "add_friend failed: user_id=%s friend_id=%s", user_id, friend_id
            )
            return False

    def remove_friend(self, user_id: str, friend_id: str) -> bool:
        """Soft-delete a friendship by marking both directions as deleted.

        Uses a special ``'__deleted__'`` remark value that is filtered out in
        ``get_friends`` and ``is_friend`` queries.  Returns ``True`` on
        success, ``False`` when the database is disabled or an error occurs.
        """
        if not self._ensure_connected():
            return False

        try:
            now = datetime.now()
            self._safe_execute(
                "INSERT INTO friendships "
                "(user_id, friend_id, remark, created_at, updated_at) "
                "VALUES",
                [
                    {
                        "user_id": user_id,
                        "friend_id": friend_id,
                        "remark": "__deleted__",
                        "created_at": now,
                        "updated_at": now,
                    },
                    {
                        "user_id": friend_id,
                        "friend_id": user_id,
                        "remark": "__deleted__",
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )
            return True
        except Exception:
            logger.exception(
                "remove_friend failed: user_id=%s friend_id=%s",
                user_id,
                friend_id,
            )
            return False

    def get_friends(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all active (non-deleted) friends of a user.

        Each element is a dict with keys ``friend_id``, ``remark``, and
        ``created_at``.  Results are ordered by most recent first.

        Returns an empty list when the database is disabled or an error occurs.
        """
        if not self._ensure_connected():
            return []

        try:
            result = self._safe_execute(
                "SELECT friend_id, remark, created_at "
                "FROM friendships FINAL "
                "WHERE user_id = %(uid)s AND remark != '__deleted__' "
                "ORDER BY created_at DESC",
                {"uid": user_id},
            )
            return [
                {"friend_id": row[0], "remark": row[1], "created_at": row[2]}
                for row in result
            ]
        except Exception:
            logger.exception("get_friends failed: user_id=%s", user_id)
            return []

    def is_friend(self, user_id: str, friend_id: str) -> bool:
        """Check whether ``user_id`` and ``friend_id`` are currently friends.

        Uses ``FRIENDSHIPS FINAL`` so the ReplacingMergeTree deduplication
        is applied and soft-deleted rows are excluded.

        Returns ``False`` when the database is disabled or an error occurs.
        """
        if not self._ensure_connected():
            return False

        try:
            result = self._safe_execute(
                "SELECT remark FROM friendships FINAL "
                "WHERE user_id = %(uid)s AND friend_id = %(fid)s "
                "LIMIT 1",
                {"uid": user_id, "fid": friend_id},
            )
            if result and result[0][0] != "__deleted__":
                return True
            return False
        except Exception:
            logger.exception(
                "is_friend failed: user_id=%s friend_id=%s",
                user_id,
                friend_id,
            )
            return False

    def set_friend_remark(
        self,
        user_id: str,
        friend_id: str,
        remark: str,
    ) -> bool:
        """Set a display remark for an existing friendship.

        Uses the ReplacingMergeTree insert pattern: a new row is inserted and
        ``FINAL`` queries later resolve the most recent remark.

        Returns ``True`` on success, ``False`` when the database is disabled
        or an error occurs.
        """
        if not self._ensure_connected():
            return False

        try:
            now = datetime.now()
            self._safe_execute(
                "INSERT INTO friendships "
                "(user_id, friend_id, remark, created_at, updated_at) "
                "VALUES",
                [
                    {
                        "user_id": user_id,
                        "friend_id": friend_id,
                        "remark": remark,
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )
            return True
        except Exception:
            logger.exception(
                "set_friend_remark failed: user_id=%s friend_id=%s",
                user_id,
                friend_id,
            )
            return False

    # ------------------------------------------------------------------
    # Friend requests
    # ------------------------------------------------------------------

    def create_friend_request(
        self,
        request_id: str,
        from_user: str,
        to_user: str,
        message: str = "",
    ) -> bool:
        """Create a new friend request with status ``'pending'``.

        Returns ``True`` on success, ``False`` when the database is disabled
        or an error occurs.
        """
        if not self._ensure_connected():
            return False

        try:
            now = datetime.now()
            self._safe_execute(
                "INSERT INTO friend_requests "
                "(id, from_user, to_user, message, status, created_at, updated_at) "
                "VALUES",
                [
                    {
                        "id": request_id,
                        "from_user": from_user,
                        "to_user": to_user,
                        "message": message,
                        "status": "pending",
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )
            return True
        except Exception:
            logger.exception(
                "create_friend_request failed: request_id=%s from=%s to=%s",
                request_id,
                from_user,
                to_user,
            )
            return False

    def get_friend_request(
        self,
        request_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a single friend request by its ID.

        Uses ``FRIEND_REQUESTS FINAL`` so that the ReplacingMergeTree
        deduplication is applied.  Returns a dict with keys ``id``,
        ``from_user``, ``to_user``, ``message``, ``status``, and
        ``created_at``, or ``None`` when not found, the database is disabled,
        or an error occurs.
        """
        if not self._ensure_connected():
            return None

        try:
            result = self._safe_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE id = %(rid)s "
                "LIMIT 1",
                {"rid": request_id},
            )
            if result:
                row = result[0]
                return {
                    "id": row[0],
                    "from_user": row[1],
                    "to_user": row[2],
                    "message": row[3],
                    "status": row[4],
                    "created_at": row[5],
                }
            return None
        except Exception:
            logger.exception(
                "get_friend_request failed: request_id=%s", request_id
            )
            return None

    def get_pending_friend_requests(
        self,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Return all pending friend requests received by ``user_id``.

        Each element is a dict with keys ``id``, ``from_user``, ``to_user``,
        ``message``, ``status``, and ``created_at``.  Results are ordered by
        most recent first.

        Returns an empty list when the database is disabled or an error occurs.
        """
        if not self._ensure_connected():
            return []

        try:
            result = self._safe_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE to_user = %(uid)s AND status = 'pending' "
                "ORDER BY created_at DESC",
                {"uid": user_id},
            )
            return [
                {
                    "id": row[0],
                    "from_user": row[1],
                    "to_user": row[2],
                    "message": row[3],
                    "status": row[4],
                    "created_at": row[5],
                }
                for row in result
            ]
        except Exception:
            logger.exception(
                "get_pending_friend_requests failed: user_id=%s", user_id
            )
            return []

    def get_sent_friend_requests(
        self,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Return all pending friend requests sent by ``user_id``.

        Each element is a dict with keys ``id``, ``from_user``, ``to_user``,
        ``message``, ``status``, and ``created_at``.  Results are ordered by
        most recent first.

        Returns an empty list when the database is disabled or an error occurs.
        """
        if not self._ensure_connected():
            return []

        try:
            result = self._safe_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE from_user = %(uid)s AND status = 'pending' "
                "ORDER BY created_at DESC",
                {"uid": user_id},
            )
            return [
                {
                    "id": row[0],
                    "from_user": row[1],
                    "to_user": row[2],
                    "message": row[3],
                    "status": row[4],
                    "created_at": row[5],
                }
                for row in result
            ]
        except Exception:
            logger.exception(
                "get_sent_friend_requests failed: user_id=%s", user_id
            )
            return []

    def update_friend_request_status(
        self,
        request_id: str,
        status: str,
    ) -> bool:
        """Update the status of an existing friend request.

        Reads the current row (via ``FINAL``), then re-inserts with the new
        status, preserving all other fields.  Uses the ReplacingMergeTree
        pattern: the new row supersedes the old one based on ``updated_at``.

        Returns ``True`` on success, ``False`` when the request does not
        exist, the database is disabled, or an error occurs.
        """
        if not self._ensure_connected():
            return False

        try:
            existing = self.get_friend_request(request_id)
            if not existing:
                return False

            now = datetime.now()
            self._safe_execute(
                "INSERT INTO friend_requests "
                "(id, from_user, to_user, message, status, created_at, updated_at) "
                "VALUES",
                [
                    {
                        "id": request_id,
                        "from_user": existing["from_user"],
                        "to_user": existing["to_user"],
                        "message": existing["message"],
                        "status": status,
                        "created_at": existing["created_at"],
                        "updated_at": now,
                    },
                ],
            )
            return True
        except Exception:
            logger.exception(
                "update_friend_request_status failed: request_id=%s status=%s",
                request_id,
                status,
            )
            return False

    def has_pending_request(self, from_user: str, to_user: str) -> bool:
        """Check whether a pending friend request already exists.

        Returns ``False`` when the database is disabled or an error occurs.
        """
        if not self._ensure_connected():
            return False

        try:
            result = self._safe_execute(
                "SELECT 1 FROM friend_requests FINAL "
                "WHERE from_user = %(f)s AND to_user = %(t)s "
                "  AND status = 'pending' "
                "LIMIT 1",
                {"f": from_user, "t": to_user},
            )
            return len(result) > 0
        except Exception:
            logger.exception(
                "has_pending_request failed: from=%s to=%s",
                from_user,
                to_user,
            )
            return False
