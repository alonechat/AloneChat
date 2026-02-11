"""\
High-level API client for AloneChat application.
Provides a clean interface for interacting with the AloneChat API endpoints.
"""

import asyncio
import aiohttp
from typing import Optional, Dict, Any

from AloneChat.core.client.utils import DEFAULT_API_PORT
from AloneChat.core.message.protocol import Message, MessageType


class AloneChatAPIClient:
    """
    High-level API client for AloneChat application.
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
            
            # Default headers
            default_headers = {}
            if self.token:
                default_headers["Authorization"] = f"Bearer {self.token}"
            
            # Merge headers
            if headers:
                default_headers.update(headers)
            
            # Create a new session for each request
            async with aiohttp.ClientSession() as session:
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
        
        # Extract server address from base URL
        # Assuming API and WebSocket servers are on the same host
        # but WebSocket uses different port (typically base port - 1)
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
            
            # Default headers
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            
            # Create a new session for each request
            async with aiohttp.ClientSession() as session:
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


__all__ = ["AloneChatAPIClient"]
