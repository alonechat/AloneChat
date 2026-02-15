"""
Message routing and broadcasting services.

Handles message delivery to clients and provides broadcasting capabilities.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Callable

from AloneChat.core.message.protocol import Message, MessageType
from AloneChat.core.server.transport import WebSocketConnectionRegistry

logger = logging.getLogger(__name__)


class DeliveryStatus(Enum):
    """Status of message delivery."""
    DELIVERED = auto()
    FAILED = auto()
    USER_OFFLINE = auto()
    QUEUED = auto()


@dataclass
class DeliveryResult:
    """Result of message delivery attempt."""
    status: DeliveryStatus
    user_id: str
    error: Optional[str] = None


class MessageRouter:
    """
    Routes messages to appropriate destinations.
    
    Handles message delivery to specific users, broadcasts,
    and manages message queues for offline users.
    """
    
    def __init__(
        self,
        connection_registry: WebSocketConnectionRegistry,
        message_queue_size: int = 100
    ):
        """
        Initialize message router.
        
        Args:
            connection_registry: Registry of active connections
            message_queue_size: Maximum size of per-user message queues
        """
        self._registry = connection_registry
        self._message_queues: Dict[str, asyncio.Queue] = {}
        self._queue_size = message_queue_size
        self._pre_send_hooks: List[Callable[[Message, str], Optional[Message]]] = []
        self._post_send_hooks: List[Callable[[Message, str, DeliveryResult], None]] = []
        # Optional queue manager (older canary variants referenced this).
        # We keep it as None unless explicitly injected.
        self._queue_manager = None
    
    def register_pre_send_hook(
        self,
        hook: Callable[[Message, str], Optional[Message]]
    ) -> None:
        """
        Register a hook to process messages before sending.
        
        Args:
            hook: Function that takes (message, user_id) and returns modified message or None
        """
        self._pre_send_hooks.append(hook)
    
    def register_post_send_hook(
        self,
        hook: Callable[[Message, str, DeliveryResult], None]
    ) -> None:
        """
        Register a hook to handle delivery results.
        
        Args:
            hook: Function that takes (message, user_id, result)
        """
        self._post_send_hooks.append(hook)
    
    async def send_to_user(self, message: Message, user_id: str) -> DeliveryResult:
        """Send message to a specific user (all active connections)."""
        message = self._invoke_pre_hooks(message, user_id)
        if message is None:
            # Pre-hook can drop the message
            result = DeliveryResult(DeliveryStatus.FAILED, user_id, error="Message dropped by pre-hook")
            # message is None here; skip post hooks
            return result

        connections = []
        if hasattr(self._registry, "get_connections"):
            try:
                connections = self._registry.get_connections(user_id)  # type: ignore[attr-defined]
            except Exception:
                connections = []
        if not connections:
            c = self._registry.get_connection(user_id)
            if c:
                connections = [c]

        any_success = False
        last_error: str | None = None

        for connection in connections:
            if not connection or not connection.is_open():
                continue
            try:
                success = await connection.send(message)
                if success:
                    any_success = True
                else:
                    last_error = "Send failed"
            except Exception as e:
                logger.exception("Error sending message to %s: %s", user_id, e)
                last_error = str(e)

        if any_success:
            result = DeliveryResult(DeliveryStatus.DELIVERED, user_id)
            self._invoke_post_hooks(message, user_id, result)
            return result

        # If no websocket delivery, optionally try queue manager if provided.
        if self._queue_manager is not None:
            try:
                if getattr(self._queue_manager, "has_queue", None) and self._queue_manager.has_queue(user_id):
                    await self._queue_manager.queue_message(user_id, message)
                    result = DeliveryResult(DeliveryStatus.QUEUED, user_id)
                    self._invoke_post_hooks(message, user_id, result)
                    return result
            except Exception as e:
                last_error = str(e)

        result = DeliveryResult(DeliveryStatus.FAILED, user_id, error=last_error or "No connection")
        self._invoke_post_hooks(message, user_id, result)
        return result

    async def broadcast(
        self,
        message: Message,
        exclude: Optional[List[str]] = None
    ) -> Dict[str, DeliveryResult]:
        """Broadcast a message to all currently connected users."""
        exclude_set = set(exclude or [])
        results: Dict[str, DeliveryResult] = {}

        # Prefer registry bulk API if available
        all_conns = {}
        try:
            all_conns = self._registry.get_all_connections()  # type: ignore[attr-defined]
        except Exception:
            all_conns = {}

        for user_id in list(all_conns.keys()):
            if user_id in exclude_set:
                continue
            results[user_id] = await self.send_to_user(message, user_id)

        return results
        
    def get_pending_messages(self, user_id: str) -> List[str]:
        """
        Get pending messages for a user (non-blocking).
        
        Args:
            user_id: User identifier
            
        Returns:
            List of serialized messages
        """
        queue = self._message_queues.get(user_id)
        if not queue:
            return []
        
        messages = []
        while not queue.empty():
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        
        return messages
    
    def clear_user_queue(self, user_id: str) -> int:
        """
        Clear message queue for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of messages cleared
        """
        if user_id in self._message_queues:
            count = self._message_queues[user_id].qsize()
            self._message_queues[user_id] = asyncio.Queue(maxsize=self._queue_size)
            return count
        return 0
    
    def remove_user_queue(self, user_id: str) -> None:
        """Remove message queue for a user."""
        self._message_queues.pop(user_id, None)
    
    def _invoke_post_hooks(
        self,
        message: Message,
        user_id: str,
        result: DeliveryResult
    ) -> None:
        """Invoke post-send hooks."""
        for hook in self._post_send_hooks:
            try:
                hook(message, user_id, result)
            except Exception as e:
                logger.exception("Error in post-send hook: %s", e)

    def _invoke_pre_hooks(self, message: Message, user_id: str) -> Optional[Message]:
        """Invoke pre-send hooks; hooks may modify or drop the message."""
        current = message
        for hook in self._pre_send_hooks:
            try:
                nxt = hook(current, user_id)
                if nxt is None:
                    return None
                current = nxt
            except Exception as e:
                logger.exception("Error in pre-send hook: %s", e)
        return current


class BroadcastServiceImpl:
    """
    Implementation of broadcast service.
    
    Provides high-level broadcasting capabilities with
    support for different message types.
    """
    
    def __init__(self, message_router: MessageRouter):
        """
        Initialize broadcast service.
        
        Args:
            message_router: Message router instance
        """
        self._router = message_router
    
    async def broadcast_text(
        self,
        content: str,
        sender: str = "SERVER",
        exclude: Optional[List[str]] = None
    ) -> Dict[str, DeliveryResult]:
        """
        Broadcast a text message.
        
        Args:
            content: Message content
            sender: Sender name
            exclude: Users to exclude
            
        Returns:
            Delivery results
        """
        message = Message(MessageType.TEXT, sender, content)
        return await self._router.broadcast(message, exclude)
    
    async def broadcast_system_message(
        self,
        content: str,
        exclude: Optional[List[str]] = None
    ) -> Dict[str, DeliveryResult]:
        """
        Broadcast a system message.
        
        Args:
            content: Message content
            exclude: Users to exclude
            
        Returns:
            Delivery results
        """
        message = Message(MessageType.TEXT, "SERVER", content)
        return await self._router.broadcast(message, exclude)
    
    async def notify_user_joined(
        self,
        username: str,
        exclude: Optional[List[str]] = None
    ) -> Dict[str, DeliveryResult]:
        """
        Broadcast user joined notification.
        
        Args:
            username: Joined username
            exclude: Users to exclude
            
        Returns:
            Delivery results
        """
        message = Message(MessageType.JOIN, username, f"{username} joined the chat")
        return await self._router.broadcast(message, exclude)
    
    async def notify_user_left(
        self,
        username: str,
        exclude: Optional[List[str]] = None
    ) -> Dict[str, DeliveryResult]:
        """
        Broadcast user left notification.
        
        Args:
            username: Left username
            exclude: Users to exclude
            
        Returns:
            Delivery results
        """
        message = Message(MessageType.LEAVE, username, f"{username} left the chat")
        return await self._router.broadcast(message, exclude)
    
    async def send_to_user(
        self,
        user_id: str,
        message: Message
    ) -> DeliveryResult:
        """
        Send a message to a specific user.
        
        Args:
            user_id: Target user
            message: Message to send
            
        Returns:
            Delivery result
        """
        return await self._router.send_to_user(user_id, message)
    
    async def send_pong(self, user_id: str) -> DeliveryResult:
        """
        Send heartbeat pong to a user.
        
        Args:
            user_id: Target user
            
        Returns:
            Delivery result
        """
        message = Message(MessageType.HEARTBEAT, "SERVER", "pong")
        return await self._router.send_to_user(user_id, message)


__all__ = [
    'MessageRouter',
    'BroadcastServiceImpl',
    'DeliveryResult',
    'DeliveryStatus',
]
