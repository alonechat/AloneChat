"""
Private chat service for client-side private messaging.

Handles private chat sessions, user status tracking, and offline messages.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class PrivateChatSession:
    """Represents a private chat session with another user."""
    
    partner_id: str
    partner_name: str
    last_activity: float = field(default_factory=lambda: datetime.now().timestamp())
    unread_count: int = 0
    is_online: bool = False
    partner_status: str = "offline"
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now().timestamp()
    
    def increment_unread(self) -> None:
        """Increment unread message count."""
        self.unread_count += 1
    
    def clear_unread(self) -> None:
        """Clear unread message count."""
        self.unread_count = 0


@dataclass
class UserStatus:
    """User status information."""
    
    user_id: str
    display_name: str
    status: str = "offline"
    is_online: bool = False
    last_seen: Optional[float] = None


class PrivateChatService:
    """
    Client-side service for private chat functionality.
    
    Features:
        - Track private chat sessions
        - Manage user status
        - Handle offline messages
        - Sync with server API
    """
    
    def __init__(
        self,
        on_session_update: Optional[Callable[[str], None]] = None,
        on_user_status_update: Optional[Callable[[str, str], None]] = None
    ):
        """
        Initialize private chat service.
        
        Args:
            on_session_update: Callback when session is updated (partner_id)
            on_user_status_update: Callback when user status changes (user_id, status)
        """
        self._sessions: Dict[str, PrivateChatSession] = {}
        self._user_statuses: Dict[str, UserStatus] = {}
        self._online_users: Set[str] = set()
        
        self._on_session_update = on_session_update
        self._on_user_status_update = on_user_status_update
    
    def get_or_create_session(self, partner_id: str, partner_name: Optional[str] = None) -> PrivateChatSession:
        """
        Get existing session or create a new one.
        
        Args:
            partner_id: Partner user ID
            partner_name: Optional partner display name
            
        Returns:
            PrivateChatSession
        """
        if partner_id not in self._sessions:
            self._sessions[partner_id] = PrivateChatSession(
                partner_id=partner_id,
                partner_name=partner_name or partner_id
            )
            logger.debug("Created private chat session with %s", partner_id)
        
        return self._sessions[partner_id]
    
    def get_session(self, partner_id: str) -> Optional[PrivateChatSession]:
        """Get session by partner ID."""
        return self._sessions.get(partner_id)
    
    def get_all_sessions(self) -> List[PrivateChatSession]:
        """Get all private chat sessions sorted by last activity."""
        return sorted(
            self._sessions.values(),
            key=lambda s: s.last_activity,
            reverse=True
        )
    
    def update_session_activity(self, partner_id: str) -> None:
        """Update session activity timestamp."""
        session = self._sessions.get(partner_id)
        if session:
            session.update_activity()
    
    def mark_session_read(self, partner_id: str) -> None:
        """Mark session as read."""
        session = self._sessions.get(partner_id)
        if session:
            session.clear_unread()
            if self._on_session_update:
                self._on_session_update(partner_id)
    
    def increment_unread(self, partner_id: str) -> None:
        """Increment unread count for a session."""
        session = self.get_or_create_session(partner_id)
        session.increment_unread()
        if self._on_session_update:
            self._on_session_update(partner_id)
    
    def set_partner_online(self, partner_id: str, is_online: bool, status: str = "online") -> None:
        """
        Set partner online status.
        
        Args:
            partner_id: Partner user ID
            is_online: Whether partner is online
            status: Status string (online, away, busy, offline)
        """
        session = self.get_or_create_session(partner_id)
        old_status = session.partner_status
        session.is_online = is_online
        session.partner_status = status
        
        if is_online:
            self._online_users.add(partner_id)
        else:
            self._online_users.discard(partner_id)
        
        if old_status != status and self._on_user_status_update:
            self._on_user_status_update(partner_id, status)
    
    def update_user_status(self, user_id: str, display_name: Optional[str] = None,
                           status: str = "offline", is_online: bool = False,
                           last_seen: Optional[float] = None) -> None:
        """
        Update user status information.
        
        Args:
            user_id: User identifier
            display_name: Display name
            status: Status string
            is_online: Whether user is online
            last_seen: Last seen timestamp
        """
        if user_id in self._sessions:
            self.set_partner_online(user_id, is_online, status)
        
        self._user_statuses[user_id] = UserStatus(
            user_id=user_id,
            display_name=display_name or user_id,
            status=status,
            is_online=is_online,
            last_seen=last_seen
        )
    
    def get_user_status(self, user_id: str) -> Optional[UserStatus]:
        """Get user status information."""
        return self._user_statuses.get(user_id)
    
    def get_online_users(self) -> Set[str]:
        """Get set of online user IDs."""
        return self._online_users.copy()
    
    def is_user_online(self, user_id: str) -> bool:
        """Check if user is online."""
        return user_id in self._online_users
    
    def get_total_unread(self) -> int:
        """Get total unread count across all sessions."""
        return sum(s.unread_count for s in self._sessions.values())
    
    def remove_session(self, partner_id: str) -> bool:
        """Remove a session."""
        if partner_id in self._sessions:
            del self._sessions[partner_id]
            self._online_users.discard(partner_id)
            return True
        return False
    
    def clear_all_sessions(self) -> None:
        """Clear all sessions."""
        self._sessions.clear()
        self._online_users.clear()
    
    def sync_from_api(self, api_data: Dict[str, Any]) -> None:
        """
        Sync sessions from API response.
        
        Args:
            api_data: API response containing sessions and user data
        """
        sessions = api_data.get("sessions", [])
        for session_data in sessions:
            partner_id = session_data.get("partner")
            if partner_id:
                session = self.get_or_create_session(partner_id)
                session.last_activity = session_data.get("last_activity", session.last_activity)
                session.partner_name = session_data.get("partner", session.partner_name)
        
        users = api_data.get("users", [])
        for user_data in users:
            user_id = user_data.get("user_id")
            if user_id:
                self.update_user_status(
                    user_id=user_id,
                    display_name=user_data.get("display_name"),
                    status=user_data.get("status", "offline"),
                    is_online=user_data.get("is_online", False)
                )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "sessions": [
                {
                    "partner_id": s.partner_id,
                    "partner_name": s.partner_name,
                    "last_activity": s.last_activity,
                    "unread_count": s.unread_count,
                    "is_online": s.is_online,
                    "partner_status": s.partner_status
                }
                for s in self._sessions.values()
            ],
            "online_users": list(self._online_users)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PrivateChatService':
        """Create from dictionary."""
        service = cls()
        
        for session_data in data.get("sessions", []):
            partner_id = session_data.get("partner_id")
            if partner_id:
                session = PrivateChatSession(
                    partner_id=partner_id,
                    partner_name=session_data.get("partner_name", partner_id),
                    last_activity=session_data.get("last_activity", datetime.now().timestamp()),
                    unread_count=session_data.get("unread_count", 0),
                    is_online=session_data.get("is_online", False),
                    partner_status=session_data.get("partner_status", "offline")
                )
                service._sessions[partner_id] = session
                if session.is_online:
                    service._online_users.add(partner_id)
        
        return service


__all__ = [
    'PrivateChatSession',
    'UserStatus',
    'PrivateChatService',
]
