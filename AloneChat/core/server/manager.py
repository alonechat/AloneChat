"""
Server session management module for AloneChat application.
Handles user sessions and their lifecycle management.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict
from typing import Set

import websockets

from ..message.protocol import Message, MessageType


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
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.sessions = {}

    async def handler(self, websocket):
        self.clients.add(websocket)
        try:
            async for message in websocket:
                msg = Message.deserialize(message)
                if msg.type == MessageType.JOIN:
                    self.sessions[msg.sender] = websocket
                await self.process_message(msg)
        finally:
            self.clients.discard(websocket)
            for user, ws in list(self.sessions.items()):
                if ws == websocket:
                    del self.sessions[user]

    async def process_message(self, msg):
        if msg.type == MessageType.KICK and msg.sender == "admin":
            if target_ws := self.sessions.get(msg.target):
                await target_ws.close()
        elif msg.type == MessageType.HELP:
            help_msg = Message(MessageType.TEXT, "SERVER", "Commands: /help, /join, /kick")
            await self.sessions[msg.sender].send(help_msg.serialize())
        else:
            await self.broadcast(msg)

    async def broadcast(self, msg):
        if self.clients:
            tasks = [asyncio.create_task(client.send(msg.serialize())) for client in self.clients]
            await asyncio.gather(*tasks)

    async def run(self):
        # noinspection PyTypeChecker
        async with websockets.serve(self.handler, self.host, self.port):
            print(f"Server running on ws://{self.host}:{self.port}")
            await asyncio.Future()
