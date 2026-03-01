"""
High-level API client for AloneChat application.

Provides a clean interface for interacting with the AloneChat API endpoints.
Core messaging (send/receive) uses WebSocket for high performance.
Other operations (auth, status, history) use HTTP.
"""

import asyncio
import json
import logging
import threading
from typing import Any, Callable, Dict, Optional

import aiohttp
import websockets

from AloneChat.core.message import Message, MessageType

logger = logging.getLogger(__name__)

DEFAULT_API_PORT = 8766


class SessionManager:
    """Singleton manager for aiohttp.ClientSession."""
    
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


_session_manager = SessionManager()


class AloneChatAPIClient:
    """High-level API client for AloneChat.
    
    Core messaging uses WebSocket for high performance.
    Other operations (auth, status, history) use HTTP.
    """
    
    def __init__(self, host: str = "localhost", port: int = DEFAULT_API_PORT):
        self.host = host
        self.port = port
        self.base_url = f"https://{host}:{port}" if port == 443 else f"http://{host}:{port}"
        self.ws_url = f"wss://{host}:{port}/ws" if port == 443 else f"ws://{host}:{port}/ws"
        self.token: Optional[str] = None
        self.username: Optional[str] = None
        
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_lock = asyncio.Lock()
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._receive_task: Optional[asyncio.Task] = None
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._running = False
    
    async def connect_ws(self) -> bool:
        """Connect to WebSocket server for messaging."""
        if not self.token:
            return False
        
        async with self._ws_lock:
            if self._ws is not None:
                try:
                    if not self._ws.state.name in ('CLOSING', 'CLOSED'):
                        return True
                except Exception:
                    pass
            
            try:
                headers = {"Authorization": f"Bearer {self.token}"}
                # We set proxy to None to avoid potential issues with proxy settings
                # Hope it works in most cases with stream grabbers...
                self._ws = await websockets.connect(self.ws_url, additional_headers=headers, proxy=None)
                self._running = True
                self._receive_task = asyncio.create_task(self._receive_loop())
                logger.debug("WebSocket connected: %s", self.username)
                return True
            except Exception as e:
                logger.warning("WebSocket connection failed: %s", e)
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
        """Background task to receive messages from WebSocket."""
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
    
    def on_message(self, msg_type: MessageType, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self._message_handlers[msg_type] = handler
    
    async def receive_message_ws(self, timeout: float = 30.0) -> Optional[Message]:
        """Receive a message from the WebSocket queue."""
        try:
            return await asyncio.wait_for(self._message_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
    
    async def send_message_ws(self, content: str, target: Optional[str] = None) -> bool:
        """Send a message through WebSocket.
        
        This is the high-performance messaging method.
        """
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
            msg = Message(MessageType.TEXT, self.username or "", content, target=target)
            await self._ws.send(msg.serialize())
            return True
        except Exception as e:
            logger.warning("WebSocket send failed: %s", e)
            return False
    
    @property
    def is_ws_connected(self) -> bool:
        """Check if WebSocket is connected."""
        if self._ws is None:
            return False
        try:
            return self._ws.state.name not in ('CLOSING', 'CLOSED')
        except Exception:
            return False
    
    async def _request(
        self, 
        endpoint: str, 
        method: str = "GET", 
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        try:
            url = f"{self.base_url}{endpoint}"
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            
            session = await _session_manager.get_session()
            async with session.request(method, url, json=data, headers=headers) as resp:
                try:
                    return await resp.json()
                except Exception:
                    return {"success": False, "message": f"HTTP {resp.status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def register(self, username: str, password: str) -> Dict[str, Any]:
        return await self._request("/api/register", "POST", {"username": username, "password": password})
    
    async def login(self, username: str, password: str) -> Dict[str, Any]:
        resp = await self._request("/api/login", "POST", {"username": username, "password": password})
        if resp.get("success") and resp.get("token"):
            self.token = resp["token"]
            self.username = username
        return resp
    
    async def logout(self) -> Dict[str, Any]:
        await self.disconnect_ws()
        resp = await self._request("/api/logout", "POST")
        if resp.get("success"):
            self.token = None
            self.username = None
        return resp
    
    async def get_default_server(self) -> Dict[str, Any]:
        return await self._request("/api/get_default_server")
    
    async def send_message(self, message: str, target: Optional[str] = None) -> Dict[str, Any]:
        """Send a message, preferring WebSocket for high performance.
        
        Falls back to HTTP if WebSocket is not available.
        """
        if self.is_ws_connected or await self.connect_ws():
            success = await self.send_message_ws(message, target)
            if success:
                return {"success": True}
        
        return await self._request("/send", "POST", {
            "sender": self.username, "message": message, "target": target
        })
    
    async def receive_message(self) -> Dict[str, Any]:
        return await self._request("/recv")
    
    async def receive_messages_batch(self, max_messages: int = 10, timeout: float = 5.0) -> Dict[str, Any]:
        return await self._request(f"/recv/batch?max_messages={max_messages}&timeout={timeout}")
    
    async def set_user_status(self, status: str) -> Dict[str, Any]:
        return await self._request("/api/user/status", "POST", {"status": status})
    
    async def get_user_status(self, user_id: str) -> Dict[str, Any]:
        return await self._request(f"/api/user/status/{user_id}")
    
    async def get_online_users(self) -> Dict[str, Any]:
        return await self._request("/api/users/online")
    
    async def get_all_users(self) -> Dict[str, Any]:
        return await self._request("/api/users/all")
    
    async def send_private_message(self, recipient: str, content: str) -> Dict[str, Any]:
        return await self._request("/api/chat/private", "POST", {"recipient": recipient, "content": content})
    
    async def get_chat_history(self, other_user: str, limit: int = 50) -> Dict[str, Any]:
        return await self._request(f"/api/chat/history/{other_user}?limit={limit}")
    
    async def get_recent_chats(self, limit: int = 10) -> Dict[str, Any]:
        return await self._request(f"/api/chat/recent?limit={limit}")
    
    async def get_pending_messages(self) -> Dict[str, Any]:
        return await self._request("/api/chat/pending")
    
    async def clear_pending_messages(self) -> Dict[str, Any]:
        return await self._request("/api/chat/pending/clear", "POST")
    
    async def get_friends(self) -> Dict[str, Any]:
        return await self._request("/api/friends")
    
    async def send_friend_request(self, to_user: str, message: str = "") -> Dict[str, Any]:
        return await self._request("/api/friends/request", "POST", {"to_user": to_user, "message": message})
    
    async def accept_friend_request(self, request_id: str) -> Dict[str, Any]:
        return await self._request("/api/friends/accept", "POST", {"request_id": request_id})
    
    async def reject_friend_request(self, request_id: str) -> Dict[str, Any]:
        return await self._request("/api/friends/reject", "POST", {"request_id": request_id})
    
    async def remove_friend(self, friend_id: str) -> Dict[str, Any]:
        return await self._request("/api/friends/remove", "POST", {"request_id": friend_id})
    
    async def set_friend_remark(self, friend_id: str, remark: str) -> Dict[str, Any]:
        return await self._request("/api/friends/remark", "POST", {"friend_id": friend_id, "remark": remark})
    
    async def get_pending_friend_requests(self) -> Dict[str, Any]:
        return await self._request("/api/friends/requests/pending")
    
    async def get_sent_friend_requests(self) -> Dict[str, Any]:
        return await self._request("/api/friends/requests/sent")
    
    async def search_users(self, query: str, limit: int = 20) -> Dict[str, Any]:
        return await self._request(f"/api/friends/search?query={query}&limit={limit}")
    
    async def check_friendship(self, user_id: str) -> Dict[str, Any]:
        return await self._request(f"/api/friends/check/{user_id}")
    
    async def get_server_stats(self) -> Dict[str, Any]:
        return await self._request("/api/stats")
    
    def is_authenticated(self) -> bool:
        return self.token is not None
    
    def get_ws_url(self) -> str:
        return self.ws_url


async def close_session() -> None:
    await _session_manager.close()


__all__ = ["AloneChatAPIClient", "close_session"]
