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
    
    async def send_to_user(
        self,
        user_id: str,
        message: Message,
        skip_hooks: bool = False
    ) -> DeliveryResult:
        """
        Send a message to a specific user.
        
        Args:
            user_id: Target user ID
            message: Message to send
            skip_hooks: Whether to skip pre-send hooks
            
        Returns:
            DeliveryResult indicating status
        """
        # Apply pre-send hooks
        if not skip_hooks:
            for hook in self._pre_send_hooks:
                try:
                    modified = hook(message, user_id)
                    if modified is not None:
                        message = modified
                except Exception as e:
                    logger.exception("Error in pre-send hook: %s", e)
        
        # Try to send via WebSocket
        connection = self._registry.get_connection(user_id)
        if connection and connection.is_open():
            try:
                success = await connection.send(message.serialize())
                if success:
                    result = DeliveryResult(DeliveryStatus.DELIVERED, user_id)
                    self._invoke_post_hooks(message, user_id, result)
                    return result
                else:
                    result = DeliveryResult(
                        DeliveryStatus.FAILED,
                        user_id,
                        error="Send failed"
                    )
                    self._invoke_post_hooks(message, user_id, result)
                    return result
            except Exception as e:
                result = DeliveryResult(
                    DeliveryStatus.FAILED,
                    user_id,
                    error=str(e)
                )
                self._invoke_post_hooks(message, user_id, result)
                return result
        
        # User is offline, queue the message
        if user_id not in self._message_queues:
            self._message_queues[user_id] = asyncio.Queue(maxsize=self._queue_size)
        
        try:
            self._message_queues[user_id].put_nowait(message.serialize())
            result = DeliveryResult(DeliveryStatus.QUEUED, user_id)
            self._invoke_post_hooks(message, user_id, result)
            return result
        except asyncio.QueueFull:
            result = DeliveryResult(
                DeliveryStatus.FAILED,
                user_id,
                error="Message queue full"
            )
            self._invoke_post_hooks(message, user_id, result)
            return result
    
    async def broadcast(
        self,
        message: Message,
        exclude: Optional[List[str]] = None
    ) -> Dict[str, DeliveryResult]:
        """
        Broadcast a message to all connected users concurrently.

        Args:
            message: Message to broadcast
            exclude: List of user IDs to exclude

        Returns:
            Dictionary mapping user IDs to delivery results
        """
        exclude_set = set(exclude or [])
        results: Dict[str, DeliveryResult] = {}

        async def _send_safe(uid: str, msg: Message) -> tuple[str, DeliveryResult]:
            try:
                result = await self.send_to_user(uid, msg, skip_hooks=True)
                return uid, result
            except Exception as e:
                logger.exception("Error sending to %s: %s", uid, e)
                return uid, DeliveryResult(DeliveryStatus.FAILED, uid, error=str(e))

        send_tasks = []
        for user_id in self._registry.get_all_connections().keys():
            if user_id in exclude_set:
                continue
            send_tasks.append(_send_safe(user_id, message))

        for user_id in self._message_queues:
            if user_id not in exclude_set:
                send_tasks.append(_send_safe(user_id, message))

        if send_tasks:
            gathered_results = await asyncio.gather(*send_tasks, return_exceptions=True)
            for item in gathered_results:
                if isinstance(item, Exception):
                    logger.exception("Broadcast task failed: %s", item)
                elif isinstance(item, tuple):
                    uid, result = item
                    results[uid] = result

        for user_id, result in results.items():
            self._invoke_post_hooks(message, user_id, result)

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
