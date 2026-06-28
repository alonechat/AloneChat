"""
Single unified API client for AloneChat.

Merges the standalone api/client.py (AloneChatAPIClient + SessionManager) with
gui/services/event_service.py (APIClient).  Uses aiohttp for HTTP requests and
websockets for real-time messaging.

Provides:
    - Authentication methods (register, login, logout)
    - Message send / receive (WebSocket primary, HTTP fallback)
    - Friend operations (request, accept, reject, remove, remark, search)
    - User queries (status, online users, all users)
    - Chat history and server stats

The canonical MessageType is imported from AloneChat.core.message.protocol.
"""

import asyncio
import logging
import threading
from typing import Any, Callable, Dict, Optional

import aiohttp
import websockets

from AloneChat.message.protocol import Message, MessageType

logger = logging.getLogger(__name__)

DEFAULT_API_PORT = 8766


# ---------------------------------------------------------------------------
# SessionManager – thread-safe singleton for shared aiohttp.ClientSession
# ---------------------------------------------------------------------------

class SessionManager:
    """Singleton manager for aiohttp.ClientSession.

    Shares a single session across all client instances so that connection
    pools are reused and resources are not leaked.
    """

    _instance: Optional['SessionManager'] = None
    _lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls) -> 'SessionManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        with SessionManager._lock:
            if self._initialized:
                return
            self._initialized = True
            self._session: Optional[aiohttp.ClientSession] = None
            self._async_lock = asyncio.Lock()

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            async with self._async_lock:
                if self._session is None or self._session.closed:
                    connector = aiohttp.TCPConnector(
                        limit=0, limit_per_host=0, ttl_dns_cache=300
                    )
                    timeout = aiohttp.ClientTimeout(total=60, connect=10)
                    self._session = aiohttp.ClientSession(
                        connector=connector, timeout=timeout
                    )
        return self._session

    async def close(self) -> None:
        async with self._async_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None


# Module-level singleton – one session pool for the whole process.
_session_manager = SessionManager()


# ---------------------------------------------------------------------------
# AloneChatAPIClient – merged HTTP + WebSocket client
# ---------------------------------------------------------------------------

class AloneChatAPIClient:
    """High-level API client for AloneChat.

    Core messaging uses WebSocket for high performance.
    Other operations (auth, friends, user queries, history) use HTTP.
    """

    def __init__(self, host: str = "localhost", port: int = DEFAULT_API_PORT):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{port}/ws"
        self.token: Optional[str] = None
        self.username: Optional[str] = None

        # -- WebSocket state --
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_lock = asyncio.Lock()
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._receive_task: Optional[asyncio.Task] = None
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._running = False

    # ------------------------------------------------------------------
    # WebSocket connection management
    # ------------------------------------------------------------------

    async def connect_ws(self) -> bool:
        """Connect to WebSocket server for real-time messaging."""
        if not self.token:
            return False

        async with self._ws_lock:
            if self._ws is not None:
                try:
                    if self._ws.state.name not in ('CLOSING', 'CLOSED'):
                        return True
                except Exception:
                    pass

            try:
                headers = {"Authorization": f"Bearer {self.token}"}
                self._ws = await websockets.connect(
                    self.ws_url, additional_headers=headers, proxy=None
                )
                self._running = True
                self._receive_task = asyncio.create_task(self._receive_loop())
                logger.debug("WebSocket connected: %s", self.username)
                return True
            except Exception as e:
                logger.debug("WebSocket connection failed: %s", e)
                return False

    async def disconnect_ws(self) -> None:
        """Disconnect WebSocket."""
        self._running = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        async with self._ws_lock:
            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass
            self._ws = None

    async def _receive_loop(self) -> None:
        """Background task that reads messages from the WebSocket."""
        while self._running:
            try:
                if self._ws is None:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    if self._ws.state.name in ('CLOSING', 'CLOSED'):
                        break
                except Exception:
                    break

                data = await self._ws.recv()
                try:
                    msg = Message.deserialize(data)

                    if msg.type == MessageType.HEARTBEAT:
                        continue

                    await self._message_queue.put(msg)

                    if msg.type in self._message_handlers:
                        handler = self._message_handlers[msg.type]
                        if asyncio.iscoroutinefunction(handler):
                            await handler(msg)
                        else:
                            handler(msg)
                except Exception:
                    await self._message_queue.put(data)

            except websockets.ConnectionClosed:
                logger.debug("WebSocket connection closed")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Receive error: %s", e)
                await asyncio.sleep(0.1)

    @property
    def is_ws_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        if self._ws is None:
            return False
        try:
            return self._ws.state.name not in ('CLOSING', 'CLOSED')
        except Exception:
            return False

    def on_message(self, msg_type: MessageType, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self._message_handlers[msg_type] = handler

    async def receive_message_ws(self, timeout: float = 30.0) -> Optional[Message]:
        """Receive a message from the WebSocket queue."""
        try:
            return await asyncio.wait_for(self._message_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def send_message_ws(
        self, content: str, target: Optional[str] = None
    ) -> bool:
        """Send a message through WebSocket (high-performance path)."""
        if self._ws is None:
            connected = await self.connect_ws()
            if not connected:
                return False

        try:
            if self._ws.state.name in ('CLOSING', 'CLOSED'):
                return False
        except Exception:
            return False

        try:
            msg = Message(
                MessageType.TEXT, self.username or "", content, target=target
            )
            await self._ws.send(msg.serialize())
            return True
        except Exception as e:
            logger.warning("WebSocket send failed: %s", e)
            return False

    def get_ws_url(self) -> str:
        return self.ws_url

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Issue an HTTP request to the API and return the JSON response."""
        try:
            url = f"{self.base_url}{endpoint}"
            headers: Dict[str, str] = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            session = await _session_manager.get_session()
            async with session.request(
                method, url, json=data, params=params, headers=headers
            ) as resp:
                try:
                    return await resp.json()
                except Exception:
                    return {"success": False, "message": f"HTTP {resp.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def register(self, username: str, password: str) -> Dict[str, Any]:
        """Register a new user."""
        return await self._request(
            "/api/auth/register", "POST",
            {"username": username, "password": password},
        )

    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login and store the auth token."""
        resp = await self._request(
            "/api/auth/login", "POST",
            {"username": username, "password": password},
        )
        if resp.get("success") and resp.get("token"):
            self.token = resp["token"]
            self.username = username
        return resp

    async def logout(self) -> Dict[str, Any]:
        """Logout: disconnect WS and invalidate the token."""
        await self.disconnect_ws()
        resp = await self._request("/api/auth/logout", "POST")
        if resp.get("success"):
            self.token = None
            self.username = None
        return resp

    def is_authenticated(self) -> bool:
        return self.token is not None

    # ------------------------------------------------------------------
    # Server info
    # ------------------------------------------------------------------

    async def get_default_server(self) -> Dict[str, Any]:
        return await self._request("/api/get_default_server")

    async def get_server_stats(self) -> Dict[str, Any]:
        return await self._request("/api/stats")

    # ------------------------------------------------------------------
    # Messaging  (WebSocket first, HTTP fallback)
    # ------------------------------------------------------------------

    async def send_message(
        self, message: str, target: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a message.  Prefers WebSocket; falls back to HTTP."""
        if self.is_ws_connected or await self.connect_ws():
            success = await self.send_message_ws(message, target)
            if success:
                return {"success": True}

        return await self._request(
            "/api/chat/send", "POST",
            {"recipient": target, "content": message},
        )

    async def receive_message(self) -> Dict[str, Any]:
        return await self._request("/api/chat/recv", "POST")

    async def receive_messages_batch(
        self, max_messages: int = 10, timeout: float = 5.0
    ) -> Dict[str, Any]:
        return await self._request(
            "/api/chat/recv", "POST",
        )

    async def send_private_message(
        self, recipient: str, content: str
    ) -> Dict[str, Any]:
        return await self._request(
            "/api/chat/send", "POST",
            {"recipient": recipient, "content": content},
        )

    # ------------------------------------------------------------------
    # Chat history & pending messages
    # ------------------------------------------------------------------

    async def get_chat_history(
        self, other_user: str, limit: int = 50
    ) -> Dict[str, Any]:
        return await self._request(
            "/api/chat/history",
            params={"other_user": other_user, "limit": limit},
        )

    async def get_recent_chats(self, limit: int = 10) -> Dict[str, Any]:
        return await self._request(
            "/api/chat/sessions", params={"limit": limit},
        )

    async def get_pending_messages(self) -> Dict[str, Any]:
        return await self._request("/api/chat/recv", "POST")

    async def clear_pending_messages(self) -> Dict[str, Any]:
        return await self._request("/api/chat/recv/clear", "POST")

    # ------------------------------------------------------------------
    # User status & queries
    # ------------------------------------------------------------------

    async def set_user_status(self, status: str) -> Dict[str, Any]:
        return await self._request(
            "/api/users/status", "POST", {"status": status},
        )

    async def set_status(self, status: str) -> Dict[str, Any]:
        """Alias for :meth:`set_user_status` (backward-compat)."""
        return await self.set_user_status(status)

    async def get_user_status(self, user_id: str) -> Dict[str, Any]:
        return await self._request(f"/api/users/status/{user_id}")

    async def get_online_users(self) -> Dict[str, Any]:
        return await self._request("/api/users/online")

    async def get_all_users(self) -> Dict[str, Any]:
        return await self._request("/api/users/all")

    async def search_users(
        self, query: str, limit: int = 20
    ) -> Dict[str, Any]:
        return await self._request(
            "/api/friends/search", params={"query": query, "limit": limit},
        )

    # ------------------------------------------------------------------
    # Friend operations
    # ------------------------------------------------------------------

    async def get_friends(self) -> Dict[str, Any]:
        return await self._request("/api/friends/list")

    async def send_friend_request(
        self, to_user: str, message: str = ""
    ) -> Dict[str, Any]:
        return await self._request(
            "/api/friends/request", "POST",
            {"to_user": to_user, "message": message},
        )

    async def accept_friend_request(self, request_id: str) -> Dict[str, Any]:
        return await self._request(
            f"/api/friends/requests/{request_id}/accept", "POST",
        )

    async def reject_friend_request(self, request_id: str) -> Dict[str, Any]:
        return await self._request(
            f"/api/friends/requests/{request_id}/reject", "POST",
        )

    async def remove_friend(self, friend_id: str) -> Dict[str, Any]:
        return await self._request(
            "/api/friends/remove", "POST",
            {"friend_id": friend_id},
        )

    async def set_friend_remark(
        self, friend_id: str, remark: str
    ) -> Dict[str, Any]:
        return await self._request(
            "/api/friends/remark", "POST",
            {"friend_id": friend_id, "remark": remark},
        )

    async def get_pending_friend_requests(self) -> Dict[str, Any]:
        return await self._request("/api/friends/requests/pending")

    async def get_sent_friend_requests(self) -> Dict[str, Any]:
        return await self._request("/api/friends/requests/sent")

    async def check_friendship(self, user_id: str) -> Dict[str, Any]:
        return await self._request(f"/api/friends/list")

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    async def submit_feedback(self, content: str) -> Dict[str, Any]:
        return await self._request(
            "/api/feedback/submit", "POST", {"content": content},
        )

    async def get_my_feedback(self) -> Dict[str, Any]:
        return await self._request("/api/feedback/my-feedback")

    async def close(self) -> None:
        """Disconnect WebSocket and clean up resources."""
        await self.disconnect_ws()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

async def close_session() -> None:
    """Close the shared aiohttp session (call on application shutdown)."""
    await _session_manager.close()


APIClient = AloneChatAPIClient  # backward-compatibility alias

__all__ = ["AloneChatAPIClient", "APIClient", "SessionManager", "close_session"]
