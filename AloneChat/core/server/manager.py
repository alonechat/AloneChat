"""
Refactored server session and WebSocket manager for AloneChat.

This file is a cleaned-up, better-typed and better-logged refactor
of the original `manager.py`. It preserves the original behavior
but separates concerns and adds safer send/broadcast logic.

Warning: DO NOT EXPOSE THIS SERVER TO THE PUBLIC INTERNET
THIS IS JUST A MIDIAN SERVER FOR LOCAL NETWORK USAGE ONLY
"""

from __future__ import annotations

import asyncio
import time
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Set

import websockets
# Import for type checkers only (pylance/static analyzers).
# `websockets.server` exposes `WebSocketServerProtocol` in recent versions.
from websockets.server import WebSocketServerProtocol  # type: ignore

from AloneChat.core.server.command import COMMANDS, CommandSystem
from ..message.protocol import Message, MessageType
from urllib.parse import parse_qs
import jwt
from AloneChat.config import config
# Avoid importing `update_user_online_status` at module import time to prevent
# circular imports with `AloneChat.api.routes`. We'll import it lazily where needed.

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


@dataclass
class UserSession:
    user_id: str
    last_active: float = 0.0


class SessionManager:
    """Maintain user sessions and last activity times."""

    def __init__(self) -> None:
        self.sessions: Dict[str, UserSession] = {}

    def add(self, user_id: str) -> None:
        self.sessions[user_id] = UserSession(user_id=user_id, last_active=time.time())
        logger.debug("Added session for %s", user_id)

    def remove(self, user_id: str) -> None:
        if user_id in self.sessions:
            del self.sessions[user_id]
            logger.debug("Removed session for %s", user_id)

    def touch(self, user_id: str) -> None:
        if user_id in self.sessions:
            self.sessions[user_id].last_active = time.time()

    def inactive(self, timeout: int = 300) -> list[str]:
        now = time.time()
        inactive_users = [uid for uid, s in self.sessions.items() if now - s.last_active > timeout]
        for uid in inactive_users:
            self.remove(uid)
        return inactive_users


class WebSocketManager:
    """
    Singleton manager handling WebSocket connections and message routing.
    """

    _instance: Optional[WebSocketManager] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get_instance() -> WebSocketManager:
        if WebSocketManager._instance is None:
            return WebSocketManager()
        return WebSocketManager._instance

    def __init__(self, host: str = "localhost", port: int = 8765) -> None:
        if hasattr(self, "initialized") and self.initialized:
            return
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        # Map username -> websocket
        self.sessions_ws: Dict[str, WebSocketServerProtocol] = {}
        # Track last activity per user
        self.session_mgr = SessionManager()
        # Message queues for each user (for HTTP /recv endpoint)
        self.message_queues: Dict[str, asyncio.Queue] = {}
        self.initialized = True
        logger.info("WebSocketManager initialized on %s:%s", host, port)

    # --- Helper methods ---
    @staticmethod
    def _extract_token(websocket: WebSocketServerProtocol) -> Optional[str]:
        # Try to obtain the request path
        token = None
        request_path = getattr(websocket, "request", None)
        path = None
        if request_path is not None:
            # older/newer websockets expose request with path
            path = getattr(websocket.request, "path", None)
        if not path:
            path = getattr(websocket, "path", None)

        if path and "?" in path:
            try:
                _, query = path.split("?", 1)
                params = parse_qs(query)
                token = params.get("token", [None])[0]
            except Exception:
                token = None

        if not token:
            cookie_header = ""
            try:
                cookie_header = websocket.request.headers.get("Cookie", "")
            except Exception:
                # fallback: some versions expose headers directly on websocket
                cookie_header = getattr(websocket, "request", {}).get("headers", {}) if websocket else ""
            if cookie_header:
                for cookie in cookie_header.split(";"):
                    if "authToken=" in cookie:
                        token = cookie.split("=", 1)[1].strip()
                        break

        return token

    def _verify_jwt(self, token: str) -> Optional[str]:
        try:
            payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            raise
        except Exception:
            raise

    # --- WebSocket handler ---
    async def handler(self, websocket: WebSocketServerProtocol) -> None:
        # Authenticate connection
        try:
            logger.debug("Starting auth for incoming websocket")
            token = self._extract_token(websocket)
            if not token:
                msg = Message(MessageType.TEXT, "SERVER", "No verify token provided, please login first")
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="Unauthorized: No token")
                return

            try:
                username = self._verify_jwt(token)
            except jwt.ExpiredSignatureError:
                msg = Message(MessageType.TEXT, "SERVER", "The token has expired.")
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="Token expired")
                return
            except Exception as e:
                msg = Message(MessageType.TEXT, "SERVER", f"Invalid token: {e}")
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="Invalid token")
                return

            if not username:
                msg = Message(MessageType.TEXT, "SERVER", "There is no username in token")
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="Invalid token payload")
                return

            if username in self.sessions_ws:
                msg = Message(MessageType.TEXT, "SERVER", f"User '{username}' already logged in at another location.")
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="User already logged in")
                return

            self.sessions_ws[username] = websocket
            self.session_mgr.add(username)
            # Lazy import to avoid circular import
            from AloneChat.api.routes import update_user_online_status
            update_user_online_status(username, True)
            logger.info("User %s connected", username)

            join_msg = Message(MessageType.JOIN, username, "User joined the chat")
            await self.broadcast(join_msg)

        except Exception as e:
            logger.exception("Unexpected error during websocket auth: %s", e)
            try:
                err = Message(MessageType.TEXT, "SERVER", f"Error during auth: {e}")
                await websocket.send(err.serialize())
                await websocket.close(code=1011, reason="Server error during auth")
            except Exception:
                pass
            return

        # Add to client set and listen
        self.clients.add(websocket)
        # Create message queue for this user if it doesn't exist
        if username not in self.message_queues:
            self.message_queues[username] = asyncio.Queue()
        
        try:
            async for raw in websocket:
                try:
                    msg = Message.deserialize(raw)
                except Exception:
                    logger.debug("Received non-Message payload; ignoring")
                    continue

                if msg.type == MessageType.JOIN:
                    continue
                if msg.type == MessageType.HEARTBEAT:
                    # update last active
                    self.session_mgr.touch(msg.sender)
                    # reply pong
                    pong = Message(MessageType.HEARTBEAT, "SERVER", "pong")
                    ws = self.sessions_ws.get(msg.sender)
                    if ws:
                        await self._safe_send(ws, pong.serialize())
                    continue

                await self.process_message(msg)

        except websockets.exceptions.ConnectionClosedError:
            logger.debug("ConnectionClosedError for a client")
        except Exception:
            logger.exception("Unexpected error in websocket receive loop")
        finally:
            # Cleanup any sessions that referenced this websocket
            self.clients.discard(websocket)
            for username, ws in list(self.sessions_ws.items()):
                if ws == websocket:
                    del self.sessions_ws[username]
                    self.session_mgr.remove(username)
                    # Remove message queue for this user
                    if username in self.message_queues:
                        del self.message_queues[username]
                    from AloneChat.api.routes import update_user_online_status
                    update_user_online_status(username, False)
                    leave_msg = Message(MessageType.LEAVE, username, "User left the chat")
                    await self.broadcast(leave_msg)
                    logger.info("User %s disconnected and cleaned up", username)
                    break

    async def process_message(self, msg: Message) -> None:
        # Verify sender session
        if msg.sender not in self.sessions_ws:
            logger.warning("Message from unlogged user %s, ignoring", msg.sender)
            return

        if msg.type == MessageType.HEARTBEAT:
            # handled earlier; keep here as fallback
            ws = self.sessions_ws.get(msg.sender)
            if ws:
                await self._safe_send(ws, Message(MessageType.HEARTBEAT, "SERVER", "pong").serialize())
            return
        else:
            # Preprocessing, just use process for commands
            response = CommandSystem.process(msg.content, msg.sender, msg.target)
            ws = self.sessions_ws.get(msg.sender)
            if ws:
                await self._safe_send(ws, response.serialize())
                return

        # Broadcast other messages
        await self.broadcast(msg)

    async def broadcast(self, msg: Message) -> None:
        data = msg.serialize()
        
        # Send to connected WebSocket clients
        if self.clients:
            tasks = [asyncio.create_task(self._safe_send(client, data)) for client in list(self.clients)]
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Add message to all users' message queues
        for username in self.message_queues:
            try:
                await self.message_queues[username].put(data)
            except Exception:
                # Ignore errors when adding to queue
                pass

    async def _safe_send(self, client: WebSocketServerProtocol, message: str) -> None:
        try:
            await client.send(message)
        except Exception as e:
            logger.warning("Failed to send to client: %s", e)
            # best-effort cleanup
            if client in self.clients:
                self.clients.discard(client)
            for username, ws in list(self.sessions_ws.items()):
                if ws == client:
                    del self.sessions_ws[username]
                    self.session_mgr.remove(username)
                    from AloneChat.api.routes import update_user_online_status
                    update_user_online_status(username, False)
                    leave_msg = Message(MessageType.LEAVE, username, "User left the chat")
                    # schedule a broadcast but don't await here to avoid recursion issues
                    asyncio.create_task(self.broadcast(leave_msg))
                    break

    async def run(self) -> None:
        async with websockets.serve(self.handler, self.host, self.port):
            logger.info("Server running on ws://%s:%s", self.host, self.port)
            await asyncio.Future()
