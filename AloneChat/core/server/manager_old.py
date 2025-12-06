"""
Server session management module for AloneChat application.
Handles user sessions and their lifecycle management.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict

import websockets

from AloneChat.core.client.command import COMMANDS as COMMANDS
from ..message.protocol import Message, MessageType

from urllib.parse import parse_qs
import jwt
from AloneChat.config import config
# Note: avoid importing `update_user_online_status` at module import time
# to prevent circular imports with `AloneChat.web.routes`. Import it
# lazily inside methods where it's needed.


@dataclass
class UserSession:
    """
    Data class representing a user session.

    Attributes:
        user_id (str): Unique identifier for the user
        last_active (float): Timestamp of last user activity
    """
    user_id: str
    last_active: float

class SessionManager:
    """
    Manages user sessions and their states in the chat server.
    Handles session creation, removal, and activity monitoring.
    """
    def __init__(self):
        """Initialize an empty session manager."""
        self.sessions: Dict[str, UserSession] = {}

    def add_session(self, user_id: str):
        """
        Add a new user session.

        Args:
            user_id (str): Unique identifier for the user
        """
        self.sessions[user_id] = UserSession(
            user_id=user_id,
            last_active=time.time()
        )

    def remove_session(self, user_id: str):
        """
        Remove a user session.

        Args:
            user_id (str): Unique identifier for the user to remove
        """
        self.sessions.pop(user_id, None)

    def check_inactive(self, timeout: int = 300):
        """
        Check for inactive sessions based on a timeout period.

        Args:
            timeout (int): Timeout period in seconds (default: 300)

        Returns:
            list: List of inactive user IDs
        """
        current = time.time()
        inactive = [
            uid for uid, session in self.sessions.items()
            if current - session.last_active > timeout
        ]
        for uid in inactive:
            self.remove_session(uid)
        return inactive
    

class WebSocketManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(WebSocketManager, cls).__new__(cls)
        return cls._instance

    @staticmethod
    def get_instance():
        if WebSocketManager._instance is None:
            return WebSocketManager()
        return WebSocketManager._instance
    
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        if not hasattr(self, 'clients'):
            self.clients = set()
        if not hasattr(self, 'sessions'):
            self.sessions = {}
        # Ensure initialization port is unique
        print(f"WebSocketManager initialized with port: {self.port}")

    async def handler(self, websocket):
        # Verify JWT token during connection
        try:
            JWT_SECRET = config.JWT_SECRET
            JWT_ALGORITHM = config.JWT_ALGORITHM

            print("Start authentication process...")
            # Try get token from URL query parameters
            request_path = websocket.request.path
            print(f"Request path: {request_path}")
            query_params = {}
            if '?' in request_path:
                path_part, query_part = request_path.split('?', 1)
                query_params = parse_qs(query_part)
                print(f"Query options: {query_params}")
            token = query_params.get('token', [None])[0]
            print(f"Token get from url: {token}")

            # If there's no param token, try get it from Cookie header
            if not token:
                cookie_header = websocket.request.headers.get('Cookie', '')
                print(f"Cookie header: {cookie_header}")
                for cookie in cookie_header.split(';'):
                    if 'authToken=' in cookie:
                        token = cookie.split('=')[1].strip()
                        print(f"Token get from Cookie: {token}")
                        break

                if not token:
                    error_msg = Message(MessageType.TEXT, "SERVER", 
                                        "No verify token provided, please login first")
                    await websocket.send(error_msg.serialize())
                    await websocket.close(code=1008, reason="Unauthorized: No token")
                    return

            # Verify token
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                username = payload.get('sub')
                if not username:
                    raise ValueError("There is no username in token")

                # Use the name in the token as the user identity
                if username in self.sessions:
                    error_msg = Message(MessageType.TEXT, "SERVER", 
                                        f"User '{username}' already logged in at another location.")
                    await websocket.send(error_msg.serialize())
                    await websocket.close(code=1008, reason="User already logged in")
                    return
                self.sessions[username] = websocket
                print(f"User {username} connected")

                # Update user online status (lazy import to avoid circular import)
                from AloneChat.web.routes import update_user_online_status
                update_user_online_status(username, True)

                # Send a join message to all clients
                join_msg = Message(MessageType.JOIN, username, "User joined the chat")
                await self.broadcast(join_msg)
            except jwt.ExpiredSignatureError:
                error_msg = Message(MessageType.TEXT, "SERVER", "The token has expired.")
                await websocket.send(error_msg.serialize())
                await websocket.close(code=1008, reason="Token expired")
                return
            except jwt.InvalidTokenError as e:
                error_msg = Message(MessageType.TEXT, "SERVER", f"Invalid token: {str(e)}")
                await websocket.send(error_msg.serialize())
                await websocket.close(code=1008, reason="Invalid token")
                return
        except Exception as e:
            error_msg = Message(MessageType.TEXT, "SERVER", f"Error during auth: {str(e)}")
            await websocket.send(error_msg.serialize())
            await websocket.close(code=1011, reason="Server error during auth")
            return

        self.clients.add(websocket)
        try:
            async for message in websocket:
                msg = Message.deserialize(message)
                # Ignore json message (user already joined)
                if msg.type == MessageType.JOIN:
                    continue
                elif msg.type == MessageType.HEARTBEAT:
                    # Process heartbeat message
                    if msg.sender in self.sessions:
                        # TODO: Update last active time if needed
                        pass
                await self.process_message(msg)
        except websockets.exceptions.ConnectionClosedError:
            # Process connection closed error
            pass
        finally:
            # Ensure client is removed on disconnect
            self.clients.discard(websocket)
            # Remove from sessions
            for username, ws in list(self.sessions.items()):
                if ws == websocket:
                    del self.sessions[username]
                    # Update user online status (lazy import)
                    from AloneChat.web.routes import update_user_online_status
                    update_user_online_status(username, False)
                    break

    async def process_message(self, msg):
        """
        Process incoming messages based on their type.
        """
        # Check if sender is logged in
        if msg.sender not in self.sessions:
            print(f"Warning: Get message from un-login user {msg.sender}, ignore it.")
            return

        if msg.type == MessageType.COMMAND:
            parts = msg.content.split(maxsplit=1)
            cmd = parts[0]
            if cmd in list(COMMANDS.keys()):
                command_msg = Message(MessageType.TEXT, "COMMAND", COMMANDS[cmd]["handler"]())
                await self.sessions[msg.sender].send(command_msg.serialize())
        elif msg.type == MessageType.HEARTBEAT:  # Process heartbeat message
            # Send PONG back
            pong_msg = Message(MessageType.HEARTBEAT, "SERVER", "pong")
            await self.sessions[msg.sender].send(pong_msg.serialize())
        else:
            await self.broadcast(msg)

    async def broadcast(self, msg):
        if self.clients:
            # Create a list to hold all send tasks
            tasks = []
            for client in self.clients:
                # Create a task for each send operation
                task = asyncio.create_task(self._safe_send(client, msg.serialize()))
                tasks.append(task)
            # Wait for all send operations to complete
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, client, message):
        """
        Safe send method to handle exceptions during sending messages.
        """
        # Update user online status function
        from AloneChat.web.routes import update_user_online_status
        try:
            await client.send(message)
        except Exception as e:
            # Record the error and remove the client, but do not raise further exceptions
            print(f"Send message failed: {e}")
            # Remove invalid client from active clients
            if client in self.clients:
                self.clients.discard(client)
            # Remove from sessions
            for username, ws in list(self.sessions.items()):
                if ws == client:
                    del self.sessions[username]
                    # Update user online status
                    update_user_online_status(username, False)
                    # Broadcast leave message
                    leave_msg = Message(MessageType.LEAVE, username, "User left the chat")
                    await self.broadcast(leave_msg)
                    break

    async def run(self):
        # noinspection PyTypeChecker
        # websocket higher versions require 'host' and 'port' parameters
        async with websockets.serve(
            self.handler,
            self.host, self.port
        ):
            print(f"Server running on ws://{self.host}:{self.port}")
            await asyncio.Future()
