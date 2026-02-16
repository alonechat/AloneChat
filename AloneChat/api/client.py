"""
High-level API client for AloneChat application.

Provides a clean interface for interacting with the AloneChat API endpoints.
"""

import asyncio
import threading
from typing import Any, Dict, Optional

import aiohttp

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
    """High-level API client for AloneChat."""
    
    def __init__(self, host: str = "localhost", port: int = DEFAULT_API_PORT):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.token: Optional[str] = None
        self.username: Optional[str] = None
    
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
        resp = await self._request("/api/logout", "POST")
        if resp.get("success"):
            self.token = None
            self.username = None
        return resp
    
    async def get_default_server(self) -> Dict[str, Any]:
        return await self._request("/api/get_default_server")
    
    async def send_message(self, message: str, target: Optional[str] = None) -> Dict[str, Any]:
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
    
    async def get_server_stats(self) -> Dict[str, Any]:
        return await self._request("/api/stats")
    
    def is_authenticated(self) -> bool:
        return self.token is not None
    
    def get_ws_url(self, token: Optional[str] = None) -> str:
        use_token = token or self.token
        if not use_token:
            raise ValueError("No token available")
        return f"ws://{self.host}:{self.port}/ws?token={use_token}"


async def close_session() -> None:
    await _session_manager.close()


__all__ = ["AloneChatAPIClient", "close_session"]
