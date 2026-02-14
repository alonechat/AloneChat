"""
Session management module for the server.

Provides session tracking, activity monitoring, and cleanup functionality.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from AloneChat.core.server.interfaces import SessionStore

logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    """
    Represents a user session with metadata.
    
    Attributes:
        user_id: Unique identifier for the user
        last_active: Timestamp of last activity
        created_at: Session creation timestamp
        metadata: Additional session metadata
    """
    user_id: str
    last_active: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, any] = field(default_factory=dict)
    
    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_active = time.time()
    
    def is_expired(self, timeout_seconds: int) -> bool:
        """
        Check if session has expired.
        
        Args:
            timeout_seconds: Inactivity timeout in seconds
            
        Returns:
            True if session has expired
        """
        return time.time() - self.last_active > timeout_seconds
    
    @property
    def duration(self) -> float:
        """Get session duration in seconds."""
        return time.time() - self.created_at
    
    @property
    def idle_time(self) -> float:
        """Get idle time in seconds."""
        return time.time() - self.last_active


class InMemorySessionStore:
    """
    In-memory session store implementation.
    
    Thread-safe (for asyncio) session management with support for
    activity tracking and automatic cleanup.
    """
    
    def __init__(self, default_timeout: int = 300):
        """
        Initialize session store.
        
        Args:
            default_timeout: Default inactivity timeout in seconds
        """
        self._sessions: Dict[str, UserSession] = {}
        self._default_timeout = default_timeout
        self._user_connections: Dict[str, int] = defaultdict(int)
    
    def add(self, user_id: str, metadata: Optional[Dict] = None) -> UserSession:
        """
        Add a new session.
        
        Args:
            user_id: User identifier
            metadata: Optional session metadata
            
        Returns:
            Created UserSession
        """
        session = UserSession(
            user_id=user_id,
            metadata=metadata or {}
        )
        self._sessions[user_id] = session
        self._user_connections[user_id] += 1
        
        logger.debug("Added session for user %s (total connections: %d)", 
                    user_id, self._user_connections[user_id])
        return session
    
    def remove(self, user_id: str) -> bool:
        """
        Remove a session.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if session was removed, False if not found
        """
        if user_id in self._sessions:
            del self._sessions[user_id]
            self._user_connections[user_id] = max(0, self._user_connections[user_id] - 1)
            
            logger.debug("Removed session for user %s", user_id)
            return True
        return False
    
    def touch(self, user_id: str) -> bool:
        """
        Update last activity timestamp.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if session exists and was updated
        """
        session = self._sessions.get(user_id)
        if session:
            session.touch()
            return True
        return False
    
    def get(self, user_id: str) -> Optional[UserSession]:
        """
        Get session by user ID.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserSession or None
        """
        return self._sessions.get(user_id)
    
    def is_active(self, user_id: str) -> bool:
        """
        Check if user has an active session.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if user has an active session
        """
        return user_id in self._sessions
    
    def get_inactive(self, timeout: Optional[int] = None) -> list[str]:
        """
        Get list of inactive user IDs.
        
        Args:
            timeout: Inactivity timeout in seconds (uses default if not specified)
            
        Returns:
            List of inactive user IDs
        """
        timeout = timeout or self._default_timeout
        inactive = [
            user_id for user_id, session in self._sessions.items()
            if session.is_expired(timeout)
        ]
        return inactive
    
    def cleanup_inactive(self, timeout: Optional[int] = None) -> list[str]:
        """
        Remove all inactive sessions.
        
        Args:
            timeout: Inactivity timeout in seconds
            
        Returns:
            List of removed user IDs
        """
        inactive = self.get_inactive(timeout)
        for user_id in inactive:
            self.remove(user_id)
        
        if inactive:
            logger.info("Cleaned up %d inactive sessions", len(inactive))
        
        return inactive
    
    def get_all_sessions(self) -> Dict[str, UserSession]:
        """
        Get all active sessions.
        
        Returns:
            Dictionary mapping user IDs to sessions
        """
        return self._sessions.copy()
    
    def get_active_users(self) -> Set[str]:
        """
        Get set of active user IDs.
        
        Returns:
            Set of user IDs with active sessions
        """
        return set(self._sessions.keys())
    
    def get_connection_count(self, user_id: str) -> int:
        """
        Get number of connections for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of active connections
        """
        return self._user_connections.get(user_id, 0)
    
    def __len__(self) -> int:
        """Return number of active sessions."""
        return len(self._sessions)
    
    def __contains__(self, user_id: str) -> bool:
        """Check if user has an active session."""
        return user_id in self._sessions


class SessionManager:
    """
    High-level session manager that coordinates session operations.
    
    Provides a simplified interface for session management and
    handles session lifecycle events.
    """
    
    def __init__(
        self,
        session_store: Optional[SessionStore] = None,
        cleanup_interval: int = 60
    ):
        """
        Initialize session manager.
        
        Args:
            session_store: Session store implementation (defaults to InMemorySessionStore)
            cleanup_interval: Seconds between automatic cleanup runs
        """
        self._store = session_store or InMemorySessionStore()
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
    
    def create_session(self, user_id: str, metadata: Optional[Dict] = None) -> UserSession:
        """
        Create a new session for a user.
        
        Args:
            user_id: User identifier
            metadata: Optional session metadata
            
        Returns:
            Created UserSession
        """
        return self._store.add(user_id, metadata)
    
    def end_session(self, user_id: str) -> bool:
        """
        End a user's session.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if session was ended
        """
        return self._store.remove(user_id)
    
    def update_activity(self, user_id: str) -> bool:
        """
        Update user activity timestamp.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if session exists
        """
        return self._store.touch(user_id)
    
    def is_session_active(self, user_id: str) -> bool:
        """
        Check if user has an active session.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if session is active
        """
        return self._store.is_active(user_id)
    
    def check_and_cleanup(self, force: bool = False) -> list[str]:
        """
        Check if cleanup is needed and run it.
        
        Args:
            force: Force cleanup regardless of interval
            
        Returns:
            List of cleaned up user IDs
        """
        now = time.time()
        if force or (now - self._last_cleanup) >= self._cleanup_interval:
            self._last_cleanup = now
            return self._store.cleanup_inactive()
        return []
    
    @property
    def session_store(self) -> SessionStore:
        """Get the underlying session store."""
        return self._store
    
    @property
    def active_sessions(self) -> int:
        """Get count of active sessions."""
        return len(self._store)
