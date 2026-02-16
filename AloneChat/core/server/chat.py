"""
Chat service for AloneChat server.

Pure chat session and private messaging logic without transport concerns.
"""

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .database import get_database

logger = logging.getLogger(__name__)


@dataclass
class ChatSession:
    user1: str
    user2: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    
    @property
    def session_id(self) -> str:
        return f"{self.user1}:{self.user2}"
    
    def get_partner(self, user_id: str) -> Optional[str]:
        if user_id == self.user1:
            return self.user2
        elif user_id == self.user2:
            return self.user1
        return None


@dataclass
class PendingMessage:
    message: str
    sender: str
    recipient: str
    timestamp: float = field(default_factory=time.time)
    delivered: bool = False


class ChatService:
    """Pure chat management - no transport concerns."""
    
    MAX_PENDING = 100
    MAX_HISTORY = 50
    
    def __init__(self):
        self._sessions: Dict[str, ChatSession] = {}
        self._user_sessions: Dict[str, Set[str]] = defaultdict(set)
        self._pending: Dict[str, List[PendingMessage]] = defaultdict(list)
        self._history: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        self._db = get_database()
    
    @staticmethod
    def make_session_id(user1: str, user2: str) -> str:
        sorted_users = sorted([user1, user2])
        return f"{sorted_users[0]}:{sorted_users[1]}"
    
    def get_or_create_session(self, user1: str, user2: str) -> ChatSession:
        session_id = self.make_session_id(user1, user2)
        
        if session_id not in self._sessions:
            sorted_users = sorted([user1, user2])
            session = ChatSession(user1=sorted_users[0], user2=sorted_users[1])
            self._sessions[session_id] = session
            self._user_sessions[user1].add(session_id)
            self._user_sessions[user2].add(session_id)
        
        return self._sessions[session_id]
    
    def record_message(self, sender: str, recipient: str, content: str, delivered: bool = True) -> ChatSession:
        session = self.get_or_create_session(sender, recipient)
        session.message_count += 1
        session.last_activity = time.time()
        
        self._history[session.session_id].append((sender, content, time.time()))
        
        if len(self._history[session.session_id]) > self.MAX_HISTORY:
            self._history[session.session_id] = self._history[session.session_id][-self.MAX_HISTORY:]
        
        msg_id = str(uuid.uuid4())
        self._db.save_private_message(msg_id, sender, recipient, content, delivered)
        
        if not delivered:
            pending = PendingMessage(message=content, sender=sender, recipient=recipient)
            self._pending[recipient].append(pending)
            
            if len(self._pending[recipient]) > self.MAX_PENDING:
                self._pending[recipient] = self._pending[recipient][-self.MAX_PENDING:]
        
        return session
    
    def get_history(self, user1: str, user2: str, limit: int = 50) -> List[Dict[str, Any]]:
        session_id = self.make_session_id(user1, user2)
        history = self._history.get(session_id, [])
        
        if len(history) < limit:
            db_history = self._db.get_private_messages(user1, user2, limit)
            if db_history:
                return db_history
        
        return [
            {'sender': msg[0], 'content': msg[1], 'timestamp': msg[2]}
            for msg in history[-limit:]
        ]
    
    def get_pending(self, user_id: str) -> List[PendingMessage]:
        return self._pending.get(user_id, []).copy()
    
    def clear_pending(self, user_id: str) -> int:
        count = len(self._pending.get(user_id, []))
        self._pending[user_id] = []
        return count
    
    def get_user_sessions(self, user_id: str) -> List[ChatSession]:
        session_ids = self._user_sessions.get(user_id, set())
        sessions = [self._sessions[sid] for sid in session_ids if sid in self._sessions]
        sessions.sort(key=lambda s: s.last_activity, reverse=True)
        return sessions
    
    def get_recent_chats(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        sessions = self.get_user_sessions(user_id)[:limit]
        return [
            {
                'session_id': s.session_id,
                'partner': s.get_partner(user_id),
                'last_activity': s.last_activity,
                'message_count': s.message_count
            }
            for s in sessions
        ]
    
    def end_session(self, user1: str, user2: str) -> bool:
        session_id = self.make_session_id(user1, user2)
        
        if session_id in self._sessions:
            session = self._sessions.pop(session_id)
            self._user_sessions[session.user1].discard(session_id)
            self._user_sessions[session.user2].discard(session_id)
            return True
        return False
    
    def get_session_count(self) -> int:
        return len(self._sessions)
    
    def get_total_message_count(self) -> int:
        return sum(s.message_count for s in self._sessions.values())


_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
