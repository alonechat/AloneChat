"""
Message service for AloneChat server.

SINGLE delivery path. Handles ALL delivery: live send via WebSocket
callback (set_send_callback), or queue for SSE/polling (/recv).
ChatService._pending dict is REMOVED — this is the only queuing layer.

All database access goes through the MessageRepository passed in __init__.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from AloneChat.message.protocol import Message, MessageType
from AloneChat.server.repositories.message_repo import MessageRepository

logger = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    """Result of a message delivery attempt."""

    success: bool = False
    user_id: str = ""
    error: Optional[str] = None


class MessageQueue:
    """High-performance per-user message queue with overflow protection.

    Used as the fallback delivery path for SSE clients and for polling
    via ``/recv`` when no live WebSocket callback is registered.
    """

    def __init__(self, max_size: int = 500):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._max_size = max_size

    async def put(self, data: str) -> bool:
        """Enqueue a serialized message, dropping the oldest if full.

        Returns ``True`` on success, ``False`` if the queue is in an
        unrecoverable state.
        """
        try:
            self._queue.put_nowait(data)
            return True
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()  # drop oldest
                self._queue.put_nowait(data)
                logger.warning(
                    "MessageQueue full (%d items), oldest message dropped",
                    self._max_size,
                )
                return True
            except Exception:
                return False
        except Exception:
            return False

    def put_nowait(self, data: str) -> bool:
        """Synchronous enqueue with the same overflow behaviour as ``put``."""
        try:
            self._queue.put_nowait(data)
            return True
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(data)
                logger.warning(
                    "MessageQueue full (%d items), oldest message dropped",
                    self._max_size,
                )
                return True
            except Exception:
                return False
        except Exception:
            return False

    async def get(self, timeout: float = 30.0) -> Optional[str]:
        """Block until a message is available or *timeout* expires.

        Returns ``None`` on timeout.
        """
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def get_nowait(self) -> Optional[str]:
        """Return the next message without blocking, or ``None`` if empty."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def get_batch(self, max_count: int = 10) -> List[str]:
        """Drain up to *max_count* messages from the queue atomically."""
        messages: List[str] = []
        for _ in range(max_count):
            try:
                msg = self._queue.get_nowait()
                messages.append(msg)
            except asyncio.QueueEmpty:
                break
        return messages

    def size(self) -> int:
        """Return the current number of queued messages."""
        return self._queue.qsize()


class MessageService:
    """SINGLE delivery path for all private messages.

    Replaces the dual queuing previously split across ``ChatService._pending``
    and the old ``MessageService``.  Every message flows through one of two
    routes:

    * **Live** — delivered immediately via a registered WebSocket callback
      (see :meth:`set_send_callback`).
    * **Queued** — stored in a per-user :class:`MessageQueue` for SSE
      streaming or polling via ``/recv`` (see :meth:`get_pending`,
      :meth:`clear_pending`).

    Database persistence is delegated to the :class:`MessageRepository`
    received at construction time.

    Parameters
    ----------
    message_repo : MessageRepository
        Repository for persisting private messages to ClickHouse.
    """

    def __init__(self, message_repo: MessageRepository):
        self._message_repo = message_repo
        # Per-user pending queues for SSE / polling fallback.
        self._queues: Dict[str, MessageQueue] = {}
        # Per-user WebSocket send callback (one per user).
        self._send_callbacks: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def set_send_callback(
        self, user_id: str, callback: Optional[Callable]
    ) -> None:
        """Register or unregister a WebSocket send callback for *user_id*.

        When *callback* is a callable, every subsequent call to
        :meth:`send_message` targeting this user attempts live delivery
        through it before falling back to the queue.

        Pass ``None`` to unregister.

        The callback signature should be ``callback(serialized_message: str)``
        and may be either a synchronous or an async function.
        """
        if callback is None:
            self._send_callbacks.pop(user_id, None)
        else:
            self._send_callbacks[user_id] = callback

    # ------------------------------------------------------------------
    # Message delivery
    # ------------------------------------------------------------------

    async def send_message(
        self,
        sender: str,
        recipient: str,
        content: str,
        msg_type: MessageType = MessageType.TEXT,
    ) -> DeliveryResult:
        """Send a message from *sender* to *recipient*.

        Delivery strategy:

        1. Attempt **live** delivery through the WebSocket callback.
        2. Always queue for SSE / polling.
        3. Persist to the database.

        Returns a :class:`DeliveryResult` describing the outcome.
        """
        serialized = Message(
            type=msg_type, sender=sender, content=content, target=recipient,
        ).serialize()

        # 1. Try live WebSocket delivery.
        error = None
        callback = self._send_callbacks.get(recipient)
        if callback is not None:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(serialized)
                else:
                    callback(serialized)
            except Exception as exc:
                error = str(exc)
                logger.debug("Live delivery failed for %s: %s", recipient, exc)

        # 2. Always queue for SSE / polling.
        queue = self._get_queue(recipient)
        await queue.put(serialized)

        # 3. Persist.
        self._message_repo.save_private_message(
            msg_id=str(uuid.uuid4()),
            sender=sender,
            recipient=recipient,
            content=content,
            delivered=(error is None),
        )

        return DeliveryResult(success=True, user_id=recipient, error=error)

    async def broadcast_message(
        self,
        sender: str,
        content: str,
        recipients: list[str],
        msg_type: MessageType = MessageType.TEXT,
    ) -> int:
        """Broadcast a message to many recipients efficiently.

        Queues all recipients in parallel and persists with a single
        batch INSERT.  Returns the number of recipients delivered to.
        """
        if not recipients:
            return 0

        serialized = Message(
            type=msg_type, sender=sender, content=content,
        ).serialize()

        # 1. Queue all recipients in parallel (no DB per recipient).
        tasks = []
        for uid in recipients:
            cb = self._send_callbacks.get(uid)
            if cb is not None:
                tasks.append(self._try_live_send(cb, uid, serialized))
            self._get_queue(uid).put_nowait(serialized)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # 2. Single batch INSERT for all recipients.
        self._message_repo.save_broadcast_messages(
            sender=sender,
            recipients=recipients,
            content=content,
        )

        return len(recipients)

    async def _try_live_send(self, callback, user_id: str, data: str) -> None:
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as exc:
            logger.debug("Live delivery failed for %s: %s", user_id, exc)

    # ------------------------------------------------------------------
    # Pending message retrieval (SSE / polling)
    # ------------------------------------------------------------------

    def get_pending(self, user_id: str) -> List[str]:
        """Return all serialized messages queued for *user_id*.

        The messages are drained from the queue — each call consumes them.
        Returns an empty list when no messages are pending.
        """
        queue = self._queues.get(user_id)
        if queue is None:
            return []
        return queue.get_batch(max_count=100)

    def clear_pending(self, user_id: str) -> int:
        """Discard all pending messages for *user_id* and return the count.

        This completely removes the user's queue.  Returns 0 if no queue
        existed.
        """
        queue = self._queues.pop(user_id, None)
        if queue is None:
            return 0
        count = queue.size()
        # Drain remaining items so the asyncio.Queue can be garbage-collected.
        queue.get_batch(max_count=10000)
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_queue(self, user_id: str) -> MessageQueue:
        """Return the queue for *user_id*, creating one if necessary."""
        if user_id not in self._queues:
            self._queues[user_id] = MessageQueue()
        return self._queues[user_id]

    def get_queue(self, user_id: str) -> MessageQueue:
        """Public accessor for the per-user message queue.

        Used by SSE endpoints and polling handlers that need direct
        access to the asyncio queue for streaming / batching.
        """
        return self._get_queue(user_id)
