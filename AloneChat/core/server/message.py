"""
Message service for AloneChat server.

Pure message routing and broadcasting logic without transport concerns.
Supports both WebSocket connections and SSE (Server-Sent Events) clients.
Multi-thread and multi-process parallelization ready.
"""

import asyncio
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from AloneChat.config import config
from AloneChat.core.message.protocol import Message, MessageType

logger = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    success: bool = False
    user_id: str = ""
    error: Optional[str] = None


class MessageQueue:
    """High-performance message queue with overflow protection."""
    
    def __init__(self, max_size: int = 500):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._max_size = max_size
        self._lock = threading.Lock()
    
    async def put(self, data: str) -> bool:
        try:
            self._queue.put_nowait(data)
            return True
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(data)
                return True
            except Exception:
                return False
        except Exception:
            return False
    
    def put_nowait(self, data: str) -> bool:
        try:
            self._queue.put_nowait(data)
            return True
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(data)
                return True
            except Exception:
                return False
    
    async def get(self, timeout: float = 30.0) -> Optional[str]:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
    
    def get_nowait(self) -> Optional[str]:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    def get_batch(self, max_count: int = 10) -> List[str]:
        messages = []
        for _ in range(max_count):
            try:
                msg = self._queue.get_nowait()
                messages.append(msg)
            except asyncio.QueueEmpty:
                break
        return messages
    
    def size(self) -> int:
        return self._queue.qsize()


class BroadcastExecutor:
    """Parallel broadcast executor with thread pool."""
    
    def __init__(self, max_workers: int = None):
        self._max_workers = max_workers or config.THREAD_WORKERS
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="broadcast_"
        )
        self._semaphore: Optional[asyncio.Semaphore] = None
    
    def _get_semaphore(self, max_concurrent: int) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(max_concurrent)
        return self._semaphore
    
    async def broadcast_parallel(
        self,
        targets: Set[str],
        send_func: Callable,
        serialized: str,
        max_concurrent: int = None
    ) -> Dict[str, DeliveryResult]:
        max_concurrent = max_concurrent or config.BROADCAST_CONCURRENCY
        semaphore = self._get_semaphore(max_concurrent)
        results: Dict[str, DeliveryResult] = {}
        
        async def _send(uid: str) -> Tuple[str, DeliveryResult]:
            async with semaphore:
                try:
                    await send_func(uid, serialized)
                    return uid, DeliveryResult(success=True, user_id=uid)
                except Exception as e:
                    return uid, DeliveryResult(success=False, user_id=uid, error=str(e))
        
        if targets:
            batch_results = await asyncio.gather(
                *[_send(uid) for uid in targets],
                return_exceptions=True
            )
            for item in batch_results:
                if isinstance(item, tuple):
                    uid, result = item
                    results[uid] = result
        
        return results
    
    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)


_broadcast_executor: Optional[BroadcastExecutor] = None


def get_broadcast_executor() -> BroadcastExecutor:
    global _broadcast_executor
    if _broadcast_executor is None:
        _broadcast_executor = BroadcastExecutor()
    return _broadcast_executor


class MessageService:
    """
    Pure message routing - no transport concerns.
    
    Supports two types of clients:
    - WebSocket clients: registered with a send callback
    - SSE clients: use message queues for polling
    
    Multi-thread and multi-process parallelization ready.
    """
    
    def __init__(self, max_concurrent: int = None):
        self._queues: Dict[str, MessageQueue] = {}
        self._connections: Dict[str, Callable] = {}
        self._sse_clients: Set[str] = set()
        self._max_concurrent = max_concurrent or config.BROADCAST_CONCURRENCY
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._lock = threading.Lock()
        self._stats = {
            'messages_sent': 0,
            'broadcasts': 0,
            'errors': 0,
        }
        self._stats_lock = threading.Lock()
    
    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore
    
    def _increment_stat(self, key: str, delta: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + delta
    
    def get_stats(self) -> Dict[str, int]:
        with self._stats_lock:
            return dict(self._stats)
    
    def register_connection(self, user_id: str, send_func: Callable) -> None:
        with self._lock:
            self._connections[user_id] = send_func
            if user_id not in self._queues:
                self._queues[user_id] = MessageQueue(max_size=config.MESSAGE_QUEUE_SIZE)
    
    def unregister_connection(self, user_id: str) -> None:
        with self._lock:
            self._connections.pop(user_id, None)
    
    def register_sse_client(self, user_id: str) -> None:
        with self._lock:
            self._sse_clients.add(user_id)
            if user_id not in self._queues:
                self._queues[user_id] = MessageQueue(max_size=config.MESSAGE_QUEUE_SIZE)
    
    def unregister_sse_client(self, user_id: str) -> None:
        with self._lock:
            self._sse_clients.discard(user_id)
    
    def get_queue(self, user_id: str) -> MessageQueue:
        with self._lock:
            if user_id not in self._queues:
                self._queues[user_id] = MessageQueue(max_size=config.MESSAGE_QUEUE_SIZE)
            return self._queues[user_id]
    
    def has_connection(self, user_id: str) -> bool:
        return user_id in self._connections
    
    def has_sse_client(self, user_id: str) -> bool:
        return user_id in self._sse_clients
    
    async def send_to_user(self, user_id: str, message: Message) -> DeliveryResult:
        serialized = message.serialize()
        
        with self._lock:
            send_func = self._connections.get(user_id)
        
        if send_func:
            try:
                if asyncio.iscoroutinefunction(send_func):
                    await send_func(serialized)
                else:
                    send_func(serialized)
                self._increment_stat('messages_sent')
                return DeliveryResult(success=True, user_id=user_id)
            except Exception as e:
                logger.warning("send_to_user failed: %s -> %s", user_id, e)
                self._increment_stat('errors')
                return DeliveryResult(success=False, user_id=user_id, error=str(e))
        
        queue = self.get_queue(user_id)
        await queue.put(serialized)
        self._increment_stat('messages_sent')
        return DeliveryResult(success=True, user_id=user_id)
    
    async def broadcast(self, message: Message, exclude: Optional[Set[str]] = None) -> Dict[str, DeliveryResult]:
        exclude = exclude or set()
        results: Dict[str, DeliveryResult] = {}
        
        serialized = message.serialize()
        semaphore = self._get_semaphore()
        
        with self._lock:
            all_users = set(self._connections.keys()) | set(self._sse_clients)
        
        async def _send(uid: str) -> Tuple[str, DeliveryResult]:
            async with semaphore:
                with self._lock:
                    send_func = self._connections.get(uid)
                
                if send_func:
                    try:
                        if asyncio.iscoroutinefunction(send_func):
                            await send_func(serialized)
                        else:
                            send_func(serialized)
                        return uid, DeliveryResult(success=True, user_id=uid)
                    except Exception as e:
                        return uid, DeliveryResult(success=False, user_id=uid, error=str(e))
                else:
                    queue = self.get_queue(uid)
                    await queue.put(serialized)
                    return uid, DeliveryResult(success=True, user_id=uid)
        
        targets = [uid for uid in all_users if uid not in exclude]
        
        if targets:
            batch_results = await asyncio.gather(
                *[_send(uid) for uid in targets],
                return_exceptions=True
            )
            for item in batch_results:
                if isinstance(item, tuple):
                    uid, result = item
                    results[uid] = result
        
        self._increment_stat('broadcasts')
        return results
    
    async def broadcast_parallel(
        self,
        message: Message,
        exclude: Optional[Set[str]] = None,
        batch_size: int = 100
    ) -> Dict[str, DeliveryResult]:
        """High-performance parallel broadcast with batching."""
        exclude = exclude or set()
        results: Dict[str, DeliveryResult] = {}
        
        serialized = message.serialize()
        
        with self._lock:
            all_users = set(self._connections.keys()) | set(self._sse_clients)
        
        targets = [uid for uid in all_users if uid not in exclude]
        
        async def _send_batch(batch: List[str]) -> List[Tuple[str, DeliveryResult]]:
            batch_results = []
            for uid in batch:
                with self._lock:
                    send_func = self._connections.get(uid)
                
                if send_func:
                    try:
                        if asyncio.iscoroutinefunction(send_func):
                            await send_func(serialized)
                        else:
                            send_func(serialized)
                        batch_results.append((uid, DeliveryResult(success=True, user_id=uid)))
                    except Exception as e:
                        batch_results.append((uid, DeliveryResult(success=False, user_id=uid, error=str(e))))
                else:
                    queue = self.get_queue(uid)
                    await queue.put(serialized)
                    batch_results.append((uid, DeliveryResult(success=True, user_id=uid)))
            return batch_results
        
        for i in range(0, len(targets), batch_size):
            batch = targets[i:i + batch_size]
            batch_results = await _send_batch(batch)
            for uid, result in batch_results:
                results[uid] = result
        
        self._increment_stat('broadcasts')
        return results
    
    def get_pending_messages(self, user_id: str) -> List[str]:
        queue = self._queues.get(user_id)
        if not queue:
            return []
        return queue.get_batch(max_count=100)
    
    def clear_queue(self, user_id: str) -> None:
        with self._lock:
            if user_id in self._queues:
                del self._queues[user_id]
    
    def get_all_connected_users(self) -> Set[str]:
        with self._lock:
            return set(self._connections.keys()) | self._sse_clients
    
    def get_connection_count(self) -> int:
        with self._lock:
            return len(self._connections)
    
    def get_sse_client_count(self) -> int:
        with self._lock:
            return len(self._sse_clients)


_message_service: Optional[MessageService] = None


def get_message_service() -> MessageService:
    global _message_service
    if _message_service is None:
        _message_service = MessageService()
    return _message_service


def shutdown_message_service() -> None:
    global _message_service, _broadcast_executor
    if _broadcast_executor:
        _broadcast_executor.shutdown()
        _broadcast_executor = None
    _message_service = None
    logger.info("Message service shutdown complete")
