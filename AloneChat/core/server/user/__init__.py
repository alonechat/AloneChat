"""
User management module for the server.

Provides user tracking, status management, and user-related operations.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class UserStatus(Enum):
    """User online status."""
    ONLINE = auto()
    AWAY = auto()
    BUSY = auto()
    OFFLINE = auto()


@dataclass
class UserInfo:
    """
    Information about a user.
    
    Attributes:
        user_id: Unique identifier for the user
        status: Current user status
        display_name: Optional display name
        last_seen: Timestamp of last activity
        metadata: Additional user metadata
    """
    user_id: str
    status: UserStatus = UserStatus.ONLINE
    display_name: Optional[str] = None
    last_seen: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_activity(self) -> None:
        """Update last seen timestamp."""
        self.last_seen = time.time()
    
    def set_status(self, status: UserStatus) -> None:
        """Update user status."""
        self.status = status
        if status != UserStatus.OFFLINE:
            self.last_seen = time.time()


class UserManager:
    """
    Manages user information and status tracking.
    
    Provides a centralized way to track users, their status,
    and handle user-related operations.
    
    Features:
        - User registration and tracking
        - Status management (online, away, busy, offline)
        - Activity tracking
        - User metadata storage
        - Event callbacks for user changes
    """
    
    def __init__(
        self,
        on_user_online: Optional[Callable[[str], None]] = None,
        on_user_offline: Optional[Callable[[str], None]] = None,
        on_status_change: Optional[Callable[[str, UserStatus, UserStatus], None]] = None
    ):
        """
        Initialize user manager.
        
        Args:
            on_user_online: Callback when user comes online
            on_user_offline: Callback when user goes offline
            on_status_change: Callback when user status changes (user_id, old_status, new_status)
        """
        self._users: Dict[str, UserInfo] = {}
        self._display_names: Dict[str, str] = {}
        self._on_user_online = on_user_online
        self._on_user_offline = on_user_offline
        self._on_status_change = on_status_change
        self._user_connections: Dict[str, int] = defaultdict(int)
    
    def register_user(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UserInfo:
        """
        Register a new user or update existing user.
        
        Args:
            user_id: Unique user identifier
            display_name: Optional display name
            metadata: Optional user metadata
            
        Returns:
            UserInfo for the user
        """
        is_new_user = user_id not in self._users
        
        if is_new_user:
            user_info = UserInfo(
                user_id=user_id,
                display_name=display_name or user_id,
                metadata=metadata or {},
                status=UserStatus.ONLINE
            )
            self._users[user_id] = user_info
            self._display_names[user_id] = user_info.display_name or user_id
            logger.debug("Registered new user: %s (online)", user_id)
        else:
            user_info = self._users[user_id]
            if display_name:
                user_info.display_name = display_name
                self._display_names[user_id] = display_name
            if metadata:
                user_info.metadata.update(metadata)
            user_info.update_activity()
            
            if user_info.status == UserStatus.OFFLINE:
                old_status = user_info.status
                user_info.set_status(UserStatus.ONLINE)
                if self._on_status_change and old_status != UserStatus.ONLINE:
                    try:
                        self._on_status_change(user_id, old_status, UserStatus.ONLINE)
                    except Exception as e:
                        logger.warning("Error in status change callback: %s", e, exc_info=True)
        
        self._user_connections[user_id] += 1
        
        if is_new_user and self._on_user_online:
            try:
                self._on_user_online(user_id)
            except Exception as e:
                logger.warning("Error in user online callback: %s", e, exc_info=True)
        
        return user_info
    
    def unregister_user(self, user_id: str) -> bool:
        """
        Unregister a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if user was unregistered
        """
        if user_id not in self._users:
            return False
        
        self._user_connections[user_id] = max(0, self._user_connections[user_id] - 1)
        
        if self._user_connections[user_id] <= 0:
            old_status = self._users[user_id].status
            self._users[user_id].set_status(UserStatus.OFFLINE)
            
            if self._on_status_change and old_status != UserStatus.OFFLINE:
                try:
                    self._on_status_change(user_id, old_status, UserStatus.OFFLINE)
                except Exception as e:
                    logger.warning("Error in status change callback: %s", e, exc_info=True)
            
            if self._on_user_offline:
                try:
                    self._on_user_offline(user_id)
                except Exception as e:
                    logger.warning("Error in user offline callback: %s", e, exc_info=True)
            
            logger.debug("User went offline: %s", user_id)
        
        return True
    
    def get_user(self, user_id: str) -> Optional[UserInfo]:
        """
        Get user information.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserInfo or None if not found
        """
        return self._users.get(user_id)
    
    def get_display_name(self, user_id: str) -> str:
        """
        Get display name for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Display name or user_id if not found
        """
        return self._display_names.get(user_id, user_id)
    
    def set_display_name(self, user_id: str, display_name: str) -> bool:
        """
        Set display name for a user.
        
        Args:
            user_id: User identifier
            display_name: New display name
            
        Returns:
            True if user exists and name was set
        """
        if user_id not in self._users:
            return False
        
        self._users[user_id].display_name = display_name
        self._display_names[user_id] = display_name
        return True
    
    def set_status(self, user_id: str, status: UserStatus) -> bool:
        """
        Set user status.
        
        Args:
            user_id: User identifier
            status: New status
            
        Returns:
            True if status was changed
        """
        user_info = self._users.get(user_id)
        if not user_info:
            return False
        
        old_status = user_info.status
        if old_status == status:
            return False
        
        user_info.set_status(status)
        
        if self._on_status_change:
            try:
                self._on_status_change(user_id, old_status, status)
            except Exception as e:
                logger.warning("Error in status change callback: %s", e, exc_info=True)
        
        logger.debug("User %s status changed: %s -> %s", user_id, old_status.name, status.name)
        return True
    
    def update_activity(self, user_id: str) -> bool:
        """
        Update user activity timestamp.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if user exists
        """
        user_info = self._users.get(user_id)
        if user_info:
            user_info.update_activity()
            return True
        return False
    
    def is_online(self, user_id: str) -> bool:
        """
        Check if user is online.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if user is online
        """
        user_info = self._users.get(user_id)
        return user_info is not None and user_info.status != UserStatus.OFFLINE
    
    def get_online_users(self) -> Set[str]:
        """
        Get set of online user IDs.
        
        Returns:
            Set of user IDs with online status
        """
        return {
            user_id for user_id, info in self._users.items()
            if info.status != UserStatus.OFFLINE
        }
    
    def get_users_by_status(self, status: UserStatus) -> List[str]:
        """
        Get users with a specific status.
        
        Args:
            status: Status to filter by
            
        Returns:
            List of user IDs with the specified status
        """
        return [
            user_id for user_id, info in self._users.items()
            if info.status == status
        ]
    
    def get_all_users(self) -> Dict[str, UserInfo]:
        """
        Get all registered users.
        
        Returns:
            Dictionary mapping user IDs to UserInfo
        """
        return self._users.copy()
    
    def get_user_count(self) -> int:
        """
        Get total number of registered users.
        
        Returns:
            Number of users
        """
        return len(self._users)
    
    def get_online_count(self) -> int:
        """
        Get number of online users.
        
        Returns:
            Number of online users
        """
        return len(self.get_online_users())
    
    def set_user_metadata(self, user_id: str, key: str, value: Any) -> bool:
        """
        Set metadata for a user.
        
        Args:
            user_id: User identifier
            key: Metadata key
            value: Metadata value
            
        Returns:
            True if user exists
        """
        user_info = self._users.get(user_id)
        if user_info:
            user_info.metadata[key] = value
            return True
        return False
    
    def get_user_metadata(self, user_id: str, key: str, default: Any = None) -> Any:
        """
        Get metadata for a user.
        
        Args:
            user_id: User identifier
            key: Metadata key
            default: Default value if not found
            
        Returns:
            Metadata value or default
        """
        user_info = self._users.get(user_id)
        if user_info:
            return user_info.metadata.get(key, default)
        return default
    
    def __contains__(self, user_id: str) -> bool:
        """Check if user is registered."""
        return user_id in self._users
    
    def __len__(self) -> int:
        """Return number of registered users."""
        return len(self._users)


__all__ = [
    'UserStatus',
    'UserInfo',
    'UserManager',
]
