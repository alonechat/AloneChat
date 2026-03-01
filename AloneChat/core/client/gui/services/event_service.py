"""
Event service for SSE-based real-time messaging.

Uses Server-Sent Events (/events endpoint) for efficient real-time communication.
Provides automatic reconnection, heartbeat handling, and event parsing.
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Set

import aiohttp

logger = logging.getLogger(__name__)


class MessageType(IntEnum):
    """Message type enumeration matching server."""
    TEXT = 1
    JOIN = 2
    LEAVE = 3
    HELP = 4
    COMMAND = 5
    ENCRYPTED = 6
    HEARTBEAT = 7


@dataclass
class ChatMessage:
    """Represents a chat message from SSE stream."""
    sender: str
    content: str
    msg_type: MessageType = MessageType.TEXT
    target: Optional[str] = None
    timestamp: Optional[float] = None
    
    @classmethod
    def from_sse_data(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Create message from SSE event data."""
        return cls(
            sender=data.get("sender", ""),
            content=data.get("content", ""),
            msg_type=MessageType(data.get("type", 1)),
            target=data.get("target"),
            timestamp=data.get("timestamp")
        )
    
    def is_private(self) -> bool:
        """Check if this is a private message."""
        return self.target is not None
    
    def is_system(self) -> bool:
        """Check if this is a system message."""
        return self.msg_type in (MessageType.JOIN, MessageType.LEAVE, 
                                  MessageType.HELP, MessageType.COMMAND)


@dataclass
class EventServiceConfig:
    """Configuration for event service."""
    base_url: str
    token: str
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 30.0
    heartbeat_timeout: float = 60.0
    buffer_size: int = 100
    skip_ssl_verify: bool = False


class EventService:
    """
    SSE-based event service for real-time messaging.
    
    Features:
        - Server-Sent Events streaming via /events endpoint
        - Automatic reconnection with exponential backoff
        - Heartbeat detection and handling
        - Message buffering for offline resilience
        - Event callbacks for different message types
    """
    
    def __init__(self, config: EventServiceConfig):
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._connected = False
        self._reconnect_count = 0
        self._message_buffer: List[ChatMessage] = []
        self._buffer_lock = asyncio.Lock()
        
        self._on_message: Optional[Callable[[ChatMessage], None]] = None
        self._on_connected: Optional[Callable[[], None]] = None
        self._on_disconnected: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[Exception], None]] = None
        
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    def set_callbacks(
        self,
        on_message: Optional[Callable[[ChatMessage], None]] = None,
        on_connected: Optional[Callable[[], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> None:
        """Set event callbacks."""
        self._on_message = on_message
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
    
    async def start(self) -> None:
        """Start the SSE connection."""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=120, connect=10)
            connector = aiohttp.TCPConnector(ssl=False) if self._config.skip_ssl_verify else None
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        
        self._task = asyncio.create_task(self._run_loop())
    
    async def stop(self) -> None:
        """Stop the SSE connection."""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def _run_loop(self) -> None:
        """Main connection loop with reconnection logic."""
        while self._running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("SSE connection error: %s", e)
                if self._on_error:
                    self._on_error(e)
            
            if self._running:
                self._connected = False
                if self._on_disconnected:
                    self._on_disconnected()
                
                delay = min(
                    self._config.reconnect_delay * (2 ** self._reconnect_count),
                    self._config.max_reconnect_delay
                )
                self._reconnect_count += 1
                
                logger.info("Reconnecting in %.1f seconds...", delay)
                await asyncio.sleep(delay)
    
    async def _connect(self) -> None:
        """Establish SSE connection and process events."""
        url = f"{self._config.base_url}/events"
        headers = {
            "Authorization": f"Bearer {self._config.token}",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
        
        logger.info("Connecting to SSE: %s", url)
        
        async with self._session.get(url, headers=headers) as response:
            if response.status != 200:
                raise ConnectionError(f"SSE connection failed: HTTP {response.status}")
            
            self._connected = True
            self._reconnect_count = 0
            
            if self._on_connected:
                self._on_connected()
            
            logger.info("SSE connected successfully")
            
            buffer = ""
            async for line in response.content:
                if self._stop_event.is_set():
                    break
                
                line = line.decode('utf-8', errors='replace')
                buffer += line
                
                if buffer.endswith('\n\n'):
                    await self._process_event(buffer.strip())
                    buffer = ""
    
    async def _process_event(self, event_text: str) -> None:
        """Process a single SSE event."""
        if not event_text:
            return
        
        if event_text.startswith(':'):
            comment = event_text[1:].strip()
            if comment == "connected":
                logger.debug("SSE connected event received")
            elif comment == "heartbeat":
                logger.debug("SSE heartbeat received")
            return
        
        if event_text.startswith('data:'):
            try:
                data_str = event_text[5:].strip()
                data = json.loads(data_str)
                message = ChatMessage.from_sse_data(data)
                
                async with self._buffer_lock:
                    if len(self._message_buffer) >= self._config.buffer_size:
                        self._message_buffer.pop(0)
                    self._message_buffer.append(message)
                
                if self._on_message:
                    self._on_message(message)
                    
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse SSE data: %s", e)
            except Exception as e:
                logger.error("Error processing SSE event: %s", e)
    
    def get_buffered_messages(self) -> List[ChatMessage]:
        """Get all buffered messages."""
        return self._message_buffer.copy()
    
    def clear_buffer(self) -> None:
        """Clear message buffer."""
        self._message_buffer.clear()
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to SSE stream."""
        return self._connected
    
    @property
    def is_running(self) -> bool:
        """Check if service is running."""
        return self._running


class APIClient:
    """
    HTTP API client for AloneChat.
    
    Provides methods for authentication, messaging, and user management.
    Uses aiohttp for async HTTP requests.
    """
    
    def __init__(self, base_url: str, skip_ssl_verify: bool = None):
        self._base_url = base_url.rstrip('/')
        self._session: Optional[aiohttp.ClientSession] = None
        self._token: Optional[str] = None
        self._username: Optional[str] = None
        if skip_ssl_verify is None:
            self._skip_ssl_verify = base_url.startswith("https://")
        else:
            self._skip_ssl_verify = skip_ssl_verify
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60, connect=10)
            connector = aiohttp.TCPConnector(ssl=False) if self._skip_ssl_verify else None
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth token."""
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to API endpoint."""
        session = await self._get_session()
        url = f"{self._base_url}{endpoint}"
        
        logger.debug(f"API Request: {method} {url}")
        
        try:
            async with session.request(
                method, 
                url, 
                json=data, 
                params=params,
                headers=self._get_headers()
            ) as response:
                logger.debug(f"API Response: {response.status} {url}")
                try:
                    result = await response.json()
                    logger.debug(f"API Response Body: {result}")
                    return result
                except Exception:
                    return {"success": False, "message": f"HTTP {response.status}"}
        except aiohttp.ClientError as e:
            logger.error(f"API Client Error: {type(e).__name__}: {e}")
            return {"success": False, "message": str(e)}
        except Exception as e:
            logger.error(f"API Exception: {type(e).__name__}: {e}")
            return {"success": False, "message": str(e)}
    
    async def register(self, username: str, password: str) -> Dict[str, Any]:
        """Register a new user."""
        return await self._request("POST", "/api/register", {
            "username": username,
            "password": password
        })
    
    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login and get auth token."""
        result = await self._request("POST", "/api/login", {
            "username": username,
            "password": password
        })
        
        if result.get("success") and result.get("token"):
            self._token = result["token"]
            self._username = username
        
        return result
    
    async def logout(self) -> Dict[str, Any]:
        """Logout and invalidate token."""
        result = await self._request("POST", "/api/logout")
        self._token = None
        self._username = None
        return result
    
    async def send_message(
        self, 
        message: str, 
        target: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a message (broadcast or private)."""
        return await self._request("POST", "/send", {
            "sender": self._username,
            "message": message,
            "target": target
        })
    
    async def send_private_message(
        self, 
        recipient: str, 
        content: str
    ) -> Dict[str, Any]:
        """Send a private message via chat API."""
        return await self._request("POST", "/api/chat/private", {
            "recipient": recipient,
            "content": content
        })
    
    async def get_chat_history(
        self, 
        other_user: str, 
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get chat history with another user."""
        return await self._request(
            "GET", 
            f"/api/chat/history/{other_user}",
            params={"limit": limit}
        )
    
    async def get_recent_chats(self, limit: int = 10) -> Dict[str, Any]:
        """Get recent chat sessions."""
        return await self._request(
            "GET",
            "/api/chat/recent",
            params={"limit": limit}
        )
    
    async def get_pending_messages(self) -> Dict[str, Any]:
        """Get pending offline messages."""
        return await self._request("GET", "/api/chat/pending")
    
    async def clear_pending_messages(self) -> Dict[str, Any]:
        """Clear pending offline messages."""
        return await self._request("POST", "/api/chat/pending/clear")
    
    async def set_status(self, status: str) -> Dict[str, Any]:
        """Set user status (online, away, busy, offline)."""
        return await self._request("POST", "/api/user/status", {"status": status})
    
    async def get_user_status(self, user_id: str) -> Dict[str, Any]:
        """Get status of a specific user."""
        return await self._request("GET", f"/api/user/status/{user_id}")
    
    async def get_online_users(self) -> Dict[str, Any]:
        """Get list of online users."""
        return await self._request("GET", "/api/users/online")
    
    async def get_all_users(self) -> Dict[str, Any]:
        """Get list of all registered users."""
        return await self._request("GET", "/api/users/all")
    
    async def get_server_stats(self) -> Dict[str, Any]:
        """Get server statistics."""
        return await self._request("GET", "/api/stats")
    
    async def submit_feedback(self, content: str) -> Dict[str, Any]:
        """Submit user feedback."""
        return await self._request("POST", "/api/feedback/submit", {"content": content})
    
    async def get_my_feedback(self) -> Dict[str, Any]:
        """Get user's submitted feedback."""
        return await self._request("GET", "/api/feedback/my-feedback")
    
    async def get_friends(self) -> Dict[str, Any]:
        """Get user's friend list."""
        return await self._request("GET", "/api/friends")
    
    async def send_friend_request(self, to_user: str, message: str = "") -> Dict[str, Any]:
        """Send a friend request."""
        return await self._request("POST", "/api/friends/request", {
            "to_user": to_user,
            "message": message
        })
    
    async def accept_friend_request(self, request_id: str) -> Dict[str, Any]:
        """Accept a friend request."""
        return await self._request("POST", "/api/friends/accept", {
            "request_id": request_id
        })
    
    async def reject_friend_request(self, request_id: str) -> Dict[str, Any]:
        """Reject a friend request."""
        return await self._request("POST", "/api/friends/reject", {
            "request_id": request_id
        })
    
    async def remove_friend(self, friend_id: str) -> Dict[str, Any]:
        """Remove a friend."""
        return await self._request("POST", "/api/friends/remove", {
            "request_id": friend_id
        })
    
    async def set_friend_remark(self, friend_id: str, remark: str) -> Dict[str, Any]:
        """Set remark for a friend."""
        return await self._request("POST", "/api/friends/remark", {
            "friend_id": friend_id,
            "remark": remark
        })
    
    async def get_pending_friend_requests(self) -> Dict[str, Any]:
        """Get pending friend requests received."""
        return await self._request("GET", "/api/friends/requests/pending")
    
    async def get_sent_friend_requests(self) -> Dict[str, Any]:
        """Get sent friend requests pending."""
        return await self._request("GET", "/api/friends/requests/sent")
    
    async def search_users(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Search for users."""
        return await self._request("GET", "/api/friends/search", params={"query": query, "limit": limit})
    
    async def check_friendship(self, user_id: str) -> Dict[str, Any]:
        """Check if friends with a user."""
        return await self._request("GET", f"/api/friends/check/{user_id}")
    
    @property
    def token(self) -> Optional[str]:
        """Get current auth token."""
        return self._token
    
    @token.setter
    def token(self, value: str) -> None:
        """Set auth token."""
        self._token = value
    
    @property
    def username(self) -> Optional[str]:
        """Get current username."""
        return self._username
    
    @username.setter
    def username(self, value: str) -> None:
        """Set username."""
        self._username = value
    
    @property
    def base_url(self) -> str:
        """Get base URL."""
        return self._base_url
    
    def is_authenticated(self) -> bool:
        """Check if client has valid auth token."""
        return self._token is not None


__all__ = [
    'MessageType',
    'ChatMessage',
    'EventServiceConfig',
    'EventService',
    'APIClient',
]
