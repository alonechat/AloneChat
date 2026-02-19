"""
Message service for AloneChat server.

Pure message routing and broadcasting logic without transport concerns.
Supports both WebSocket connections and SSE (Server-Sent Events) clients.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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


class MessageService:
    """
    Pure message routing - no transport concerns.
    
    Supports two types of clients:
    - WebSocket clients: registered with a send callback
    - SSE clients: use message queues for polling
    """
    
    def __init__(self, max_concurrent: int = 1024):
        self._queues: Dict[str, MessageQueue] = {}
        self._connections: Dict[str, Callable] = {}
        self._sse_clients: Set[str] = set()
        self._max_concurrent = max_concurrent
        self._semaphore: Optional[asyncio.Semaphore] = None
    
    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore
    
    def register_connection(self, user_id: str, send_func: Callable) -> None:
        """Register a WebSocket connection for a user."""
        self._connections[user_id] = send_func
        if user_id not in self._queues:
            self._queues[user_id] = MessageQueue()
    
    def unregister_connection(self, user_id: str) -> None:
        """Unregister a WebSocket connection."""
        self._connections.pop(user_id, None)
    
    def register_sse_client(self, user_id: str) -> None:
        """Register an SSE client (uses queue-based messaging)."""
        self._sse_clients.add(user_id)
        if user_id not in self._queues:
            self._queues[user_id] = MessageQueue()
    
    def unregister_sse_client(self, user_id: str) -> None:
        """Unregister an SSE client."""
        self._sse_clients.discard(user_id)
    
    def get_queue(self, user_id: str) -> MessageQueue:
        if user_id not in self._queues:
            self._queues[user_id] = MessageQueue()
        return self._queues[user_id]
    
    def has_connection(self, user_id: str) -> bool:
        return user_id in self._connections
    
    def has_sse_client(self, user_id: str) -> bool:
        return user_id in self._sse_clients
    
    async def send_to_user(self, user_id: str, message: Message) -> DeliveryResult:
        serialized = message.serialize()
        
        if user_id in self._connections:
            try:
                send_func = self._connections[user_id]
                if asyncio.iscoroutinefunction(send_func):
                    await send_func(serialized)
                else:
                    send_func(serialized)
                return DeliveryResult(success=True, user_id=user_id)
            except Exception as e:
                logger.warning("send_to_user failed: %s -> %s", user_id, e)
                return DeliveryResult(success=False, user_id=user_id, error=str(e))
        
        queue = self.get_queue(user_id)
        await queue.put(serialized)
        return DeliveryResult(success=True, user_id=user_id)
    
    async def broadcast(self, message: Message, exclude: Optional[Set[str]] = None) -> Dict[str, DeliveryResult]:
        """
        Broadcast message to all connected users.
        
        Sends to:
        - WebSocket clients via their registered send callback
        - SSE clients via their message queue
        """
        exclude = exclude or set()
        results: Dict[str, DeliveryResult] = {}
        
        serialized = message.serialize()
        semaphore = self._get_semaphore()
        
        all_users = set(self._connections.keys()) | set(self._sse_clients)
        
        async def _send(uid: str) -> Tuple[str, DeliveryResult]:
            async with semaphore:
                if uid in self._connections:
                    try:
                        send_func = self._connections[uid]
                        import inspect

                        if inspect.iscoroutinefunction(send_func):
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
        
        return results
    
    def get_pending_messages(self, user_id: str) -> List[str]:
        queue = self._queues.get(user_id)
        if not queue:
            return []
        return queue.get_batch(max_count=100)
    
    def clear_queue(self, user_id: str) -> None:
        if user_id in self._queues:
            del self._queues[user_id]
    
    def get_all_connected_users(self) -> Set[str]:
        """Get all users with active connections (WebSocket or SSE)."""
        return set(self._connections.keys()) | self._sse_clients


_message_service: Optional[MessageService] = None


def get_message_service() -> MessageService:
    global _message_service
    if _message_service is None:
        _message_service = MessageService()
    return _message_service
