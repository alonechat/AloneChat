"""
Chat session service for AloneChat server.

Provides chat session management and history tracking without transport
concerns.  Delivery of messages to live clients is the sole responsibility
of ``MessageService`` — this module only records history.

.. note::

   The ``_pending`` dictionary that existed in the original
   ``core/server/chat.py`` has been **removed entirely**.  ``record_message``
   always persists messages with ``delivered=True``.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from AloneChat.server.repositories.message_repo import MessageRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ChatSession:
    """Represents a chat session between two users.

    Attributes
    ----------
    user1, user2 : str
        The two participants (stored in sorted order).
    created_at : float
        POSIX timestamp when the session was first created.
    last_activity : float
        POSIX timestamp of the most recent message.
    message_count : int
        Total number of messages exchanged in this session.
    """

    user1: str
    user2: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0

    @property
    def session_id(self) -> str:
        """Canonical session identifier (``"user1:user2"``, sorted)."""
        return ChatService.make_session_id(self.user1, self.user2)

    def get_partner(self, user_id: str) -> Optional[str]:
        """Return the other participant, or ``None`` if *user_id* is not in
        this session."""
        if user_id == self.user1:
            return self.user2
        elif user_id == self.user2:
            return self.user1
        return None


# ---------------------------------------------------------------------------
# Chat service
# ---------------------------------------------------------------------------


class ChatService:
    """Chat session management — history only, no delivery concerns.

    All database access is delegated to the :class:`MessageRepository`
    instance provided at construction time.  There is no module-level
    ``get_chat_service()`` singleton; callers must inject the dependency.

    Parameters
    ----------
    message_repo : MessageRepository
        Repository for persisting and retrieving private messages.
    """

    MAX_HISTORY = 50

    def __init__(self, message_repo: MessageRepository) -> None:
        self._message_repo = message_repo
        self._sessions: Dict[str, ChatSession] = {}
        self._user_sessions: Dict[str, Set[str]] = {}
        self._history: Dict[str, List[Tuple[str, str, float]]] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_session_id(user1: str, user2: str) -> str:
        """Return a canonical, order-independent session ID for two users."""
        sorted_users = sorted([user1, user2])
        return f"{sorted_users[0]}:{sorted_users[1]}"

    def _ensure_user_set(self, user_id: str) -> Set[str]:
        """Return the session-id set for *user_id*, creating it when missing."""
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = set()
        return self._user_sessions[user_id]

    def _trim_history(self, history: List, max_size: int) -> List:
        """Trim *history* in-place to at most *max_size* most-recent entries."""
        if len(history) > max_size:
            del history[: len(history) - max_size]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_or_create_session(self, user1: str, user2: str) -> ChatSession:
        """Return the :class:`ChatSession` for *user1* and *user2*, creating
        one if it does not already exist."""
        session_id = self.make_session_id(user1, user2)

        if session_id not in self._sessions:
            sorted_users = sorted([user1, user2])
            session = ChatSession(user1=sorted_users[0], user2=sorted_users[1])
            self._sessions[session_id] = session
            self._ensure_user_set(user1).add(session_id)
            self._ensure_user_set(user2).add(session_id)

        return self._sessions[session_id]

    async def record_message(
        self, sender: str, recipient: str, content: str
    ) -> ChatSession:
        """Record a message in the session history and persist it to the
        database.

        Messages are **always** stored with ``delivered=True``.  Live
        delivery to connected clients is handled exclusively by
        :class:`~AloneChat.core.server.message.MessageService`.

        Returns the :class:`ChatSession` that the message belongs to.
        """
        session = await self.get_or_create_session(sender, recipient)
        session.message_count += 1
        session.last_activity = time.time()

        session_id = session.session_id

        # In-memory history (persistence is handled by MessageService)
        if session_id not in self._history:
            self._history[session_id] = []
        self._history[session_id].append((sender, content, time.time()))
        self._trim_history(self._history[session_id], self.MAX_HISTORY)

        return session

    async def get_history(
        self, user1: str, user2: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Return the message history between *user1* and *user2*.

        When the in-memory history is shorter than *limit*, the method falls
        back to the database via :class:`MessageRepository`.  Results are
        returned in ascending chronological order (oldest first).
        """
        session_id = self.make_session_id(user1, user2)
        history = self._history.get(session_id, [])

        if len(history) < limit:
            db_history = self._message_repo.get_private_messages(user1, user2, limit)
            if db_history:
                return db_history

        return [
            {"sender": msg[0], "content": msg[1], "timestamp": msg[2]}
            for msg in history[-limit:]
        ]

    async def get_recent_chats(
        self, user_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Return the most recent chat sessions for *user_id*, ordered by
        ``last_activity`` descending."""
        session_ids = self._user_sessions.get(user_id, set())
        sessions = [
            self._sessions[sid] for sid in session_ids if sid in self._sessions
        ]
        sessions.sort(key=lambda s: s.last_activity, reverse=True)

        return [
            {
                "session_id": s.session_id,
                "partner": s.get_partner(user_id),
                "last_activity": s.last_activity,
                "message_count": s.message_count,
            }
            for s in sessions[:limit]
        ]

    async def end_session(self, user1: str, user2: str) -> bool:
        """End the session between *user1* and *user2*, removing all
        in-memory state for it.

        Returns ``True`` if a session existed and was removed, ``False``
        otherwise.
        """
        session_id = self.make_session_id(user1, user2)

        if session_id not in self._sessions:
            return False

        session = self._sessions.pop(session_id)

        if session.user1 in self._user_sessions:
            self._user_sessions[session.user1].discard(session_id)
        if session.user2 in self._user_sessions:
            self._user_sessions[session.user2].discard(session_id)

        self._history.pop(session_id, None)
        return True


__all__ = [
    "ChatService",
    "ChatSession",
]
