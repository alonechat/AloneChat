"""
Chat service for AloneChat server.

Pure chat session and private messaging logic without transport concerns.
Multi-thread safe with optimized session management using fine-grained locking.
"""

import logging
import queue
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from AloneChat.config import config
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


@dataclass
class DBWriteTask:
    msg_id: str
    sender: str
    recipient: str
    content: str
    delivered: bool


class AsyncDBWriter:
    """Asynchronous database writer with batching support.
    
    Reduces database write latency by offloading to background thread.
    """
    
    def __init__(self, batch_size: int = 50, flush_interval: float = 1.0):
        self._queue: queue.Queue[Optional[DBWriteTask]] = queue.Queue(maxsize=10000)
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._running = False
        self._writer_thread: Optional[threading.Thread] = None
        self._db = get_database()
        self._stats = {
            'total_writes': 0,
            'total_batches': 0,
            'queue_size': 0,
        }
        self._stats_lock = threading.Lock()
    
    def start(self) -> None:
        if self._running:
            return
        
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._write_loop,
            daemon=True,
            name="async_db_writer"
        )
        self._writer_thread.start()
        logger.info("AsyncDBWriter started: batch_size=%d, flush_interval=%.1fs",
                   self._batch_size, self._flush_interval)
    
    def stop(self) -> None:
        if not self._running:
            return
        
        self._running = False
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)
        
        logger.info("AsyncDBWriter stopped. Stats: %s", self._stats)
    
    def _write_loop(self) -> None:
        batch: List[DBWriteTask] = []
        last_flush = time.time()
        
        while self._running:
            try:
                timeout = max(0.01, self._flush_interval - (time.time() - last_flush))
                task = self._queue.get(timeout=timeout)
                
                if task is None:
                    break
                
                batch.append(task)
                
                if len(batch) >= self._batch_size:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()
                    
            except queue.Empty:
                if batch and (time.time() - last_flush) >= self._flush_interval:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()
            except Exception as e:
                logger.error("AsyncDBWriter error: %s", e)
        
        if batch:
            self._flush_batch(batch)
    
    def _flush_batch(self, batch: List[DBWriteTask]) -> None:
        if not batch:
            return
        
        try:
            for task in batch:
                self._db.save_private_message(
                    task.msg_id, task.sender, task.recipient,
                    task.content, task.delivered
                )
            
            with self._stats_lock:
                self._stats['total_writes'] += len(batch)
                self._stats['total_batches'] += 1
                self._stats['queue_size'] = self._queue.qsize()
                
        except Exception as e:
            logger.error("Failed to flush batch: %s", e)
    
    def submit(self, msg_id: str, sender: str, recipient: str, content: str, delivered: bool) -> bool:
        task = DBWriteTask(
            msg_id=msg_id, sender=sender, recipient=recipient,
            content=content, delivered=delivered
        )
        try:
            self._queue.put_nowait(task)
            return True
        except queue.Full:
            logger.warning("AsyncDBWriter queue full, dropping message")
            return False
    
    def get_queue_size(self) -> int:
        return self._queue.qsize()
    
    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            return dict(self._stats)


class SessionLockManager:
    """Fine-grained lock manager for chat sessions.
    
    Uses striped locking to reduce contention while keeping lock count manageable.
    """
    
    def __init__(self, stripes: int = 64):
        self._stripes = stripes
        self._locks: List[threading.RLock] = [threading.RLock() for _ in range(stripes)]
    
    def get_lock(self, session_id: str) -> threading.RLock:
        idx = hash(session_id) % self._stripes
        return self._locks[idx]
    
    def get_lock_for_user(self, user_id: str) -> threading.RLock:
        idx = hash(user_id) % self._stripes
        return self._locks[idx]


class ChatService:
    """Pure chat management - no transport concerns.
    
    Thread-safe with fine-grained locking for high concurrency.
    Uses async database writer to reduce latency.
    """
    
    MAX_PENDING = 100
    MAX_HISTORY = 50
    
    def __init__(self):
        self._sessions: Dict[str, ChatSession] = {}
        self._user_sessions: Dict[str, Set[str]] = defaultdict(set)
        self._pending: Dict[str, List[PendingMessage]] = defaultdict(list)
        self._history: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        self._db = get_database()
        
        self._lock_manager = SessionLockManager(stripes=64)
        self._sessions_lock = threading.RLock()
        self._pending_lock = threading.RLock()
        self._history_lock = threading.RLock()
        
        self._async_writer = AsyncDBWriter(
            batch_size=getattr(config, 'DB_WRITE_BATCH_SIZE', 50),
            flush_interval=getattr(config, 'DB_WRITE_INTERVAL', 1.0)
        )
        self._async_writer.start()
        
        self._stats = {
            'total_sessions': 0,
            'total_messages': 0,
            'active_sessions': 0,
        }
        self._stats_lock = threading.Lock()
    
    @staticmethod
    def make_session_id(user1: str, user2: str) -> str:
        sorted_users = sorted([user1, user2])
        return f"{sorted_users[0]}:{sorted_users[1]}"
    
    def get_or_create_session(self, user1: str, user2: str) -> ChatSession:
        session_id = self.make_session_id(user1, user2)
        session_lock = self._lock_manager.get_lock(session_id)
        
        with session_lock:
            with self._sessions_lock:
                if session_id not in self._sessions:
                    sorted_users = sorted([user1, user2])
                    session = ChatSession(user1=sorted_users[0], user2=sorted_users[1])
                    self._sessions[session_id] = session
                    self._user_sessions[user1].add(session_id)
                    self._user_sessions[user2].add(session_id)
                    self._stats['total_sessions'] += 1
                    self._stats['active_sessions'] = len(self._sessions)
                
                return self._sessions[session_id]
    
    def record_message(self, sender: str, recipient: str, content: str, delivered: bool = True) -> ChatSession:
        session = self.get_or_create_session(sender, recipient)
        session_id = session.session_id
        session_lock = self._lock_manager.get_lock(session_id)
        
        with session_lock:
            session.message_count += 1
            session.last_activity = time.time()
        
        with self._history_lock:
            self._history[session_id].append((sender, content, time.time()))
            if len(self._history[session_id]) > self.MAX_HISTORY:
                self._history[session_id] = self._history[session_id][-self.MAX_HISTORY:]
        
        with self._stats_lock:
            self._stats['total_messages'] += 1
        
        msg_id = str(uuid.uuid4())
        self._async_writer.submit(msg_id, sender, recipient, content, delivered)
        
        if not delivered:
            with self._pending_lock:
                pending = PendingMessage(message=content, sender=sender, recipient=recipient)
                self._pending[recipient].append(pending)
                if len(self._pending[recipient]) > self.MAX_PENDING:
                    self._pending[recipient] = self._pending[recipient][-self.MAX_PENDING:]
        
        return session
    
    def get_history(self, user1: str, user2: str, limit: int = 50) -> List[Dict[str, Any]]:
        session_id = self.make_session_id(user1, user2)
        
        with self._history_lock:
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
        with self._pending_lock:
            return self._pending.get(user_id, []).copy()
    
    def clear_pending(self, user_id: str) -> int:
        with self._pending_lock:
            count = len(self._pending.get(user_id, []))
            self._pending[user_id] = []
            return count
    
    def get_user_sessions(self, user_id: str) -> List[ChatSession]:
        with self._sessions_lock:
            session_ids = self._user_sessions.get(user_id, set()).copy()
        
        sessions = []
        for sid in session_ids:
            session_lock = self._lock_manager.get_lock(sid)
            with session_lock:
                with self._sessions_lock:
                    if sid in self._sessions:
                        sessions.append(self._sessions[sid])
        
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
        session_lock = self._lock_manager.get_lock(session_id)
        
        with session_lock:
            with self._sessions_lock:
                if session_id in self._sessions:
                    session = self._sessions.pop(session_id)
                    self._user_sessions[session.user1].discard(session_id)
                    self._user_sessions[session.user2].discard(session_id)
                    self._stats['active_sessions'] = len(self._sessions)
                    return True
                return False
    
    def get_session_count(self) -> int:
        with self._sessions_lock:
            return len(self._sessions)
    
    def get_total_message_count(self) -> int:
        with self._stats_lock:
            return self._stats['total_messages']
    
    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            stats = dict(self._stats)
        
        with self._pending_lock:
            stats['pending_messages'] = sum(len(p) for p in self._pending.values())
        
        with self._history_lock:
            stats['history_entries'] = sum(len(h) for h in self._history.values())
        
        stats['db_writer'] = self._async_writer.get_stats()
        return stats
    
    def shutdown(self) -> None:
        self._async_writer.stop()


_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


def shutdown_chat_service() -> None:
    global _chat_service
    if _chat_service is not None:
        _chat_service.shutdown()
        _chat_service = None
