"""
High-level API client for AloneChat application.
Provides a clean interface for interacting with the AloneChat API endpoints.
Uses singleton pattern for aiohttp.ClientSession to enable connection pooling.
"""

import asyncio
import weakref
from typing import Optional, Dict, Any

import aiohttp

from AloneChat.core.client.utils import DEFAULT_API_PORT


class SessionManager:
    """
    Singleton manager for aiohttp.ClientSession.
    
    Provides a shared session across all API client instances,
    enabling connection pooling and reducing overhead.
    """
    
    _instance: Optional['SessionManager'] = None
    _session: Optional[aiohttp.ClientSession] = None
    _lock = asyncio.Lock()
    
    def __new__(cls) -> 'SessionManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create the shared aiohttp session."""
        if self._session is None or self._session.closed:
            async with self._lock:
                if self._session is None or self._session.closed:
                    connector = aiohttp.TCPConnector(
                        limit=0,
                        limit_per_host=0,
                        ttl_dns_cache=300,
                        enable_cleanup_closed=True
                    )
                    timeout = aiohttp.ClientTimeout(total=60, connect=10)
                    self._session = aiohttp.ClientSession(
                        connector=connector,
                        timeout=timeout,
                        trust_env=False
                    )
        return self._session
    
    async def close(self) -> None:
        """Close the shared session."""
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
    
    @property
    def is_closed(self) -> bool:
        """Check if the session is closed."""
        return self._session is None or self._session.closed


_session_manager = SessionManager()


class AloneChatAPIClient:
    """
    High-level API client for AloneChat application.
    
    Uses a shared aiohttp.ClientSession for all requests,
    enabling connection pooling and reducing TCP handshake overhead.
    """

    def __init__(self, host: str = "localhost", port: int = DEFAULT_API_PORT):
        """
        Initialize the API client.

        Args:
            host (str): API server hostname
            port (int): API server port
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.token: Optional[str] = None
        self.username: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get the shared aiohttp session."""
        return await _session_manager.get_session()

    async def _make_request(
        self, 
        endpoint: str, 
        method: str = "GET", 
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            endpoint (str): API endpoint to call
            method (str): HTTP method to use
            data (dict): Data to send in the request
            headers (dict): Additional headers to send

        Returns:
            dict: Response from the API
        """
        try:
            url = f"{self.base_url}{endpoint}"
            
            default_headers = {}
            if self.token:
                default_headers["Authorization"] = f"Bearer {self.token}"
            
            if headers:
                default_headers.update(headers)
            
            session = await self._get_session()
            async with session.request(
                method=method, 
                url=url, 
                json=data, 
                headers=default_headers
            ) as response:
                try:
                    return await response.json()
                except Exception:
                    return {"success": False, "message": f"Request failed with status {response.status}"}
        except Exception as e:
            return {"success": False, "message": f"Request failed: {str(e)}"}

    async def register(self, username: str, password: str) -> Dict[str, Any]:
        """
        Register a new user.

        Args:
            username (str): Username for the new account
            password (str): Password for the new account

        Returns:
            dict: Registration response
        """
        response = await self._make_request(
            "/api/register",
            method="POST",
            data={"username": username, "password": password}
        )
        return response

    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Login a user.

        Args:
            username (str): Username
            password (str): Password

        Returns:
            dict: Login response with token if successful
        """
        response = await self._make_request(
            "/api/login",
            method="POST",
            data={"username": username, "password": password}
        )
        
        if response.get("success") and response.get("token"):
            self.token = response["token"]
            self.username = username
        
        return response

    async def logout(self) -> Dict[str, Any]:
        """
        Logout the current user.

        Returns:
            dict: Logout response
        """
        response = await self._make_request(
            "/api/logout",
            method="POST"
        )
        
        if response.get("success"):
            self.token = None
            self.username = None
        
        return response

    async def get_default_server(self) -> Dict[str, Any]:
        """
        Get the default server address.

        Returns:
            dict: Default server address response
        """
        return await self._make_request("/api/get_default_server")

    def get_ws_url(self, token: Optional[str] = None) -> str:
        """
        Get the WebSocket URL with token.

        Args:
            token (str): Authentication token

        Returns:
            str: WebSocket URL with token parameter
        """
        use_token = token or self.token
        if not use_token:
            raise ValueError("No authentication token available")
        
        ws_port = self.port - 1
        return f"ws://{self.host}:{ws_port}?token={use_token}"

    async def send_message(self, message: str, target: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a message via the API.

        Args:
            message (str): Message content
            target (str): Optional target recipient

        Returns:
            dict: Response from the API
        """
        response = await self._make_request(
            "/send",
            method="POST",
            data={
                "sender": self.username,
                "message": message,
                "target": target
            }
        )
        return response

    async def receive_message(self) -> dict:
        """
        Receive a message via the API.

        Returns:
            dict: Message from the API
        """
        try:
            url = f"{self.base_url}/recv"
            
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            
            session = await self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"success": False, "error": f"Error: {response.status}"}
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}

    def is_authenticated(self) -> bool:
        """
        Check if the client is authenticated.

        Returns:
            bool: True if authenticated, False otherwise
        """
        return self.token is not None


async def close_session() -> None:
    """
    Close the shared aiohttp session.
    
    Should be called when the application shuts down
    to properly release resources.
    """
    await _session_manager.close()


__all__ = ["AloneChatAPIClient", "close_session"]
