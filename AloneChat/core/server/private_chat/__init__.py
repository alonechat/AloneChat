"""
Private chat management module for the server.

Provides private messaging, chat sessions, and conversation management.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from AloneChat.core.message.protocol import Message, MessageType

logger = logging.getLogger(__name__)


@dataclass
class PrivateChatSession:
    """
    Represents a private chat session between two users.
    
    Attributes:
        user1: First user ID (alphabetically sorted)
        user2: Second user ID (alphabetically sorted)
        created_at: Session creation timestamp
        last_activity: Last message timestamp
        message_count: Number of messages exchanged
        metadata: Additional session metadata
    """
    user1: str
    user2: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def participants(self) -> Tuple[str, str]:
        """Get tuple of participants."""
        return (self.user1, self.user2)
    
    def involves(self, user_id: str) -> bool:
        """Check if user is a participant."""
        return user_id in (self.user1, self.user2)
    
    def get_partner(self, user_id: str) -> Optional[str]:
        """Get the other participant."""
        if user_id == self.user1:
            return self.user2
        elif user_id == self.user2:
            return self.user1
        return None
    
    def record_message(self) -> None:
        """Record a message in this session."""
        self.message_count += 1
        self.last_activity = time.time()
    
    @property
    def session_id(self) -> str:
        """Generate unique session ID."""
        return f"{self.user1}:{self.user2}"


@dataclass
class PendingMessage:
    """
    A message waiting to be delivered to an offline user.
    
    Attributes:
        message: The message content
        sender: Sender user ID
        recipient: Recipient user ID
        timestamp: When the message was sent
        delivered: Whether the message has been delivered
    """
    message: str
    sender: str
    recipient: str
    timestamp: float = field(default_factory=time.time)
    delivered: bool = False


class PrivateChatManager:
    """
    Manages private chat sessions and messages between users.
    
    Features:
        - Private chat session tracking
        - Message delivery to online/offline users
        - Pending message queue for offline users
        - Chat history tracking
        - Event callbacks for chat events
    """
    
    MAX_PENDING_MESSAGES = 100
    MAX_HISTORY_PER_CHAT = 50
    
    def __init__(
        self,
        on_private_message: Optional[Callable[[str, str, str], None]] = None,
        on_session_created: Optional[Callable[[str, str], None]] = None,
        max_pending: int = MAX_PENDING_MESSAGES,
        max_history: int = MAX_HISTORY_PER_CHAT
    ):
        """
        Initialize private chat manager.
        
        Args:
            on_private_message: Callback for private messages (sender, recipient, content)
            on_session_created: Callback when session is created (user1, user2)
            max_pending: Maximum pending messages per user
            max_history: Maximum history messages per chat
        """
        self._sessions: Dict[str, PrivateChatSession] = {}
        self._user_sessions: Dict[str, Set[str]] = defaultdict(set)
        self._pending_messages: Dict[str, List[PendingMessage]] = defaultdict(list)
        self._chat_history: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        
        self._on_private_message = on_private_message
        self._on_session_created = on_session_created
        
        self._max_pending = max_pending
        self._max_history = max_history
    
    @staticmethod
    def generate_session_id(user1: str, user2: str) -> str:
        """
        Generate a unique session ID for two users.
        
        Args:
            user1: First user ID
            user2: Second user ID
            
        Returns:
            Unique session ID (users sorted alphabetically)
        """
        sorted_users = sorted([user1, user2])
        return f"{sorted_users[0]}:{sorted_users[1]}"
    
    def get_or_create_session(self, user1: str, user2: str) -> PrivateChatSession:
        """
        Get existing session or create a new one.
        
        Args:
            user1: First user ID
            user2: Second user ID
            
        Returns:
            PrivateChatSession
        """
        session_id = self.generate_session_id(user1, user2)
        
        if session_id not in self._sessions:
            sorted_users = sorted([user1, user2])
            session = PrivateChatSession(
                user1=sorted_users[0],
                user2=sorted_users[1]
            )
            self._sessions[session_id] = session
            self._user_sessions[user1].add(session_id)
            self._user_sessions[user2].add(session_id)
            
            logger.debug("Created private chat session: %s", session_id)
            
            if self._on_session_created:
                try:
                    self._on_session_created(user1, user2)
                except Exception as e:
                    logger.warning("Error in session created callback: %s", e, exc_info=True)
        
        return self._sessions[session_id]
    
    def get_session(self, user1: str, user2: str) -> Optional[PrivateChatSession]:
        """
        Get session between two users.
        
        Args:
            user1: First user ID
            user2: Second user ID
            
        Returns:
            PrivateChatSession or None
        """
        session_id = self.generate_session_id(user1, user2)
        return self._sessions.get(session_id)
    
    def get_user_sessions(self, user_id: str) -> List[PrivateChatSession]:
        """
        Get all sessions for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of sessions involving the user
        """
        session_ids = self._user_sessions.get(user_id, set())
        return [
            self._sessions[sid] for sid in session_ids
            if sid in self._sessions
        ]
    
    def record_message(
        self,
        sender: str,
        recipient: str,
        content: str,
        is_delivered: bool = True
    ) -> PrivateChatSession:
        """
        Record a private message.
        
        Args:
            sender: Sender user ID
            recipient: Recipient user ID
            content: Message content
            is_delivered: Whether message was delivered
            
        Returns:
            The chat session
        """
        session = self.get_or_create_session(sender, recipient)
        session.record_message()
        
        self._chat_history[session.session_id].append(
            (sender, content, time.time())
        )
        
        if len(self._chat_history[session.session_id]) > self._max_history:
            self._chat_history[session.session_id] = \
                self._chat_history[session.session_id][-self._max_history:]
        
        if not is_delivered:
            pending = PendingMessage(
                message=content,
                sender=sender,
                recipient=recipient
            )
            self._pending_messages[recipient].append(pending)
            
            if len(self._pending_messages[recipient]) > self._max_pending:
                self._pending_messages[recipient] = \
                    self._pending_messages[recipient][-self._max_pending:]
        
        if self._on_private_message:
            try:
                self._on_private_message(sender, recipient, content)
            except Exception as e:
                logger.warning("Error in private message callback: %s", e, exc_info=True)
        
        return session
    
    def get_pending_messages(self, user_id: str) -> List[PendingMessage]:
        """
        Get pending messages for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of pending messages
        """
        return self._pending_messages.get(user_id, []).copy()
    
    def clear_pending_messages(self, user_id: str) -> int:
        """
        Clear pending messages for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of messages cleared
        """
        count = len(self._pending_messages.get(user_id, []))
        self._pending_messages[user_id] = []
        return count
    
    def mark_pending_delivered(self, user_id: str) -> int:
        """
        Mark all pending messages as delivered.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of messages marked
        """
        count = 0
        for msg in self._pending_messages.get(user_id, []):
            if not msg.delivered:
                msg.delivered = True
                count += 1
        return count
    
    def get_chat_history(
        self,
        user1: str,
        user2: str,
        limit: Optional[int] = None
    ) -> List[Tuple[str, str, float]]:
        """
        Get chat history between two users.
        
        Args:
            user1: First user ID
            user2: Second user ID
            limit: Maximum number of messages to return
            
        Returns:
            List of (sender, content, timestamp) tuples
        """
        session_id = self.generate_session_id(user1, user2)
        history = self._chat_history.get(session_id, [])
        
        if limit:
            return history[-limit:]
        return history.copy()
    
    def get_recent_chats(self, user_id: str, limit: int = 10) -> List[PrivateChatSession]:
        """
        Get recent chat sessions for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of sessions to return
            
        Returns:
            List of sessions sorted by last activity
        """
        sessions = self.get_user_sessions(user_id)
        sessions.sort(key=lambda s: s.last_activity, reverse=True)
        return sessions[:limit]
    
    def end_session(self, user1: str, user2: str) -> bool:
        """
        End a chat session.
        
        Args:
            user1: First user ID
            user2: Second user ID
            
        Returns:
            True if session was ended
        """
        session_id = self.generate_session_id(user1, user2)
        
        if session_id in self._sessions:
            session = self._sessions.pop(session_id)
            self._user_sessions[session.user1].discard(session_id)
            self._user_sessions[session.user2].discard(session_id)
            logger.debug("Ended private chat session: %s", session_id)
            return True
        
        return False
    
    def clear_user_sessions(self, user_id: str) -> int:
        """
        Clear all sessions for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of sessions cleared
        """
        session_ids = self._user_sessions.get(user_id, set()).copy()
        count = 0
        
        for session_id in session_ids:
            if session_id in self._sessions:
                session = self._sessions.pop(session_id)
                self._user_sessions[session.user1].discard(session_id)
                self._user_sessions[session.user2].discard(session_id)
                count += 1
        
        return count
    
    def get_session_count(self) -> int:
        """Get total number of active sessions."""
        return len(self._sessions)
    
    def get_total_message_count(self) -> int:
        """Get total number of messages across all sessions."""
        return sum(s.message_count for s in self._sessions.values())


__all__ = [
    'PrivateChatSession',
    'PendingMessage',
    'PrivateChatManager',
]
