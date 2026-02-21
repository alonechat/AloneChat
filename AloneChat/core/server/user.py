"""
User service for AloneChat server.

Pure user management logic without any transport concerns.
Multi-thread safe with optimized status buffering.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set

from AloneChat.config import config
from .database import get_database, UserData

logger = logging.getLogger(__name__)


class Status(Enum):
    ONLINE = auto()
    AWAY = auto()
    BUSY = auto()
    OFFLINE = auto()


@dataclass
class UserInfo:
    user_id: str
    status: Status = Status.ONLINE
    display_name: str = ""
    last_seen: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'status': self.status.name.lower(),
            'display_name': self.display_name,
            'last_seen': self.last_seen,
            'is_online': self.status != Status.OFFLINE
        }


class StatusBuffer:
    """Buffer for batching status updates to reduce database writes.
    
    Features:
    - Batches multiple status updates before writing to database
    - Auto-flushes every flush_interval seconds
    - Auto-flushes when buffer reaches max_size
    - Thread-safe for concurrent access
    - Supports parallel processing with configurable workers
    """
    
    def __init__(self, flush_interval: float = None, max_size: int = None):
        self._buffer: Dict[str, Dict[str, Any]] = {}
        self._flush_interval = flush_interval or 5.0
        self._max_size = max_size or 50
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None
        self._stats = {
            'total_updates': 0,
            'total_flushes': 0,
            'last_flush_count': 0,
        }
    
    def start(self) -> None:
        if self._running:
            return
        
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True, name="status_buffer")
        self._flush_thread.start()
        logger.info("StatusBuffer started with flush_interval=%.1fs, max_size=%d", 
                   self._flush_interval, self._max_size)
    
    def stop(self) -> None:
        self._running = False
        self.force_flush()
        logger.info("StatusBuffer stopped. Stats: %s", self._stats)
    
    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self._flush_interval)
            if self._running and self._buffer:
                self.flush()
    
    def add(self, user_id: str, status: str, is_online: bool) -> bool:
        should_flush = False
        
        with self._lock:
            self._buffer[user_id] = {
                'user_id': user_id,
                'status': status,
                'is_online': is_online
            }
            self._stats['total_updates'] += 1
            
            if len(self._buffer) >= self._max_size:
                should_flush = True
        
        if should_flush:
            return self.flush()
        return False
    
    def get_pending_count(self) -> int:
        with self._lock:
            return len(self._buffer)
    
    def flush(self) -> bool:
        if not self._buffer:
            return False
        
        with self._lock:
            if not self._buffer:
                return False
            
            updates = list(self._buffer.values())
            self._buffer.clear()
            self._last_flush = time.time()
        
        if updates:
            db = get_database()
            count = db.batch_update_status(updates)
            if count > 0:
                self._stats['total_flushes'] += 1
                self._stats['last_flush_count'] = count
                logger.debug("Flushed %d status updates to database", count)
                return True
        return False
    
    def force_flush(self) -> int:
        with self._lock:
            updates = list(self._buffer.values())
            self._buffer.clear()
            self._last_flush = time.time()
        
        if updates:
            db = get_database()
            return db.batch_update_status(updates)
        return 0
    
    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                'pending_count': len(self._buffer),
                'buffer_size': self._max_size,
                'flush_interval': self._flush_interval,
            }


class UserService:
    """Pure user management - no transport concerns.
    
    Thread-safe with optimized status buffering for parallel processing.
    """
    
    def __init__(self, flush_interval: float = None, max_buffer_size: int = None):
        self._db = get_database()
        self._online_users: Dict[str, UserInfo] = {}
        self._user_connections: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._status_buffer = StatusBuffer(
            flush_interval=flush_interval or 5.0,
            max_size=max_buffer_size or 50
        )
        self._status_buffer.start()
        self._stats = {
            'total_online': 0,
            'total_offline': 0,
            'current_online': 0,
        }
    
    def register(self, username: str, password: str):
        from .auth import get_auth_service
        return get_auth_service().register(username, password)
    
    def authenticate(self, username: str, password: str):
        from .auth import get_auth_service
        return get_auth_service().authenticate(username, password)
    
    def set_online(self, user_id: str) -> None:
        with self._lock:
            if user_id not in self._online_users:
                user_data = self._db.get_user(user_id)
                display_name = user_data.display_name if user_data else user_id
                self._online_users[user_id] = UserInfo(
                    user_id=user_id,
                    status=Status.ONLINE,
                    display_name=display_name
                )
                self._stats['total_online'] += 1
            else:
                self._online_users[user_id].status = Status.ONLINE
                self._online_users[user_id].last_seen = time.time()
            
            self._user_connections[user_id] = self._user_connections.get(user_id, 0) + 1
            self._stats['current_online'] = len([u for u in self._online_users.values() if u.status != Status.OFFLINE])
        
        self._status_buffer.add(user_id, "online", True)
    
    def set_offline(self, user_id: str) -> None:
        with self._lock:
            if user_id in self._user_connections:
                self._user_connections[user_id] -= 1
                if self._user_connections[user_id] <= 0:
                    del self._user_connections[user_id]
                    if user_id in self._online_users:
                        self._online_users[user_id].status = Status.OFFLINE
                        self._online_users[user_id].last_seen = time.time()
                    self._stats['total_offline'] += 1
                    self._stats['current_online'] = len([u for u in self._online_users.values() if u.status != Status.OFFLINE])
                    self._status_buffer.add(user_id, "offline", False)
    
    def set_status(self, user_id: str, status: Status) -> bool:
        with self._lock:
            if user_id not in self._online_users:
                return False
            
            self._online_users[user_id].status = status
            self._online_users[user_id].last_seen = time.time()
        
        status_str = status.name.lower()
        is_online = status != Status.OFFLINE
        self._status_buffer.add(user_id, status_str, is_online)
        return True
    
    def is_online(self, user_id: str) -> bool:
        with self._lock:
            info = self._online_users.get(user_id)
            return info is not None and info.status != Status.OFFLINE
    
    def get_online_users(self) -> List[str]:
        with self._lock:
            return [uid for uid, info in self._online_users.items() if info.status != Status.OFFLINE]
    
    def get_user_info(self, user_id: str) -> Optional[UserInfo]:
        with self._lock:
            if user_id in self._online_users:
                return self._online_users[user_id]
        
        user_data = self._db.get_user(user_id)
        if user_data:
            return UserInfo(
                user_id=user_data.user_id,
                status=Status.OFFLINE,
                display_name=user_data.display_name,
                last_seen=user_data.last_seen.timestamp() if user_data.last_seen else 0
            )
        return None
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        users = self._db.get_all_users()
        result = []
        for u in users:
            with self._lock:
                info = self._online_users.get(u.user_id)
            if info:
                result.append(info.to_dict())
            else:
                result.append({
                    'user_id': u.user_id,
                    'status': u.status,
                    'display_name': u.display_name,
                    'last_seen': u.last_seen.timestamp() if u.last_seen else 0,
                    'is_online': u.is_online
                })
        return result
    
    def user_exists(self, user_id: str) -> bool:
        return self._db.user_exists(user_id)
    
    def flush_status_buffer(self) -> int:
        return self._status_buffer.force_flush()
    
    def get_pending_status_count(self) -> int:
        return self._status_buffer.get_pending_count()
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                'buffer_stats': self._status_buffer.get_stats(),
            }
    
    def shutdown(self) -> None:
        self._status_buffer.stop()


_user_service: Optional[UserService] = None


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service


def shutdown_user_service() -> None:
    global _user_service
    if _user_service is not None:
        _user_service.shutdown()
        _user_service = None
