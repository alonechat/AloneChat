"""
Legacy WebSocket manager for backward compatibility.

This file is DEPRECATED. Use UnifiedWebSocketManager instead.

Migration Guide:
    # Old way (deprecated):
    from AloneChat.core.server import WebSocketManager
    manager = WebSocketManager()
    await manager.run()
    
    # New way (recommended):
    from AloneChat.core.server import UnifiedWebSocketManager
    manager = UnifiedWebSocketManager()
    async with manager.run("localhost", 8765):
        await asyncio.Future()

Warning: DO NOT EXPOSE THIS SERVER TO THE PUBLIC INTERNET
THIS IS JUST A MEDIUM SERVER FOR LOCAL NETWORK USAGE ONLY
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from dataclasses import dataclass
from typing import Dict, Optional, Set

from websockets.server import WebSocketServerProtocol

from AloneChat.core.message.protocol import Message, MessageType
from AloneChat.core.server.websocket_manager import UnifiedWebSocketManager

logger = logging.getLogger(__name__)


def _deprecated_warning(message: str) -> None:
    """Issue deprecation warning."""
    warnings.warn(
        message,
        DeprecationWarning,
        stacklevel=3
    )


@dataclass
class UserSession:
    """Legacy user session dataclass. Use session.UserSession instead."""
    user_id: str
    last_active: float = 0.0


class SessionManager:
    """
    Legacy session manager.
    
    Deprecated: Use session.SessionManager instead.
    """
    
    def __init__(self) -> None:
        self.sessions: Dict[str, UserSession] = {}
    
    def add(self, user_id: str) -> None:
        self.sessions[user_id] = UserSession(user_id=user_id)
        logger.debug("Added session for %s", user_id)
    
    def remove(self, user_id: str) -> None:
        if user_id in self.sessions:
            del self.sessions[user_id]
            logger.debug("Removed session for %s", user_id)
    
    def touch(self, user_id: str) -> None:
        import time
        if user_id in self.sessions:
            self.sessions[user_id].last_active = time.time()
    
    def inactive(self, timeout: int = 300) -> list[str]:
        import time
        now = time.time()
        inactive_users = [
            uid for uid, s in self.sessions.items()
            if now - s.last_active > timeout
        ]
        for uid in inactive_users:
            self.remove(uid)
        return inactive_users


class WebSocketManager:
    """
    Legacy WebSocket manager.
    
    DEPRECATED: Use UnifiedWebSocketManager instead.
    
    This class provides backward compatibility with the old API
    while delegating to the new UnifiedWebSocketManager internally.
    """
    
    _instance: Optional[WebSocketManager] = None
    
    def __new__(cls, *args, **kwargs):
        _deprecated_warning(
            "WebSocketManager is deprecated. Use UnifiedWebSocketManager instead."
        )
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @staticmethod
    def get_instance() -> WebSocketManager:
        """Get singleton instance."""
        _deprecated_warning(
            "WebSocketManager.get_instance() is deprecated. "
            "Create UnifiedWebSocketManager directly."
        )
        if WebSocketManager._instance is None:
            return WebSocketManager()
        return WebSocketManager._instance
    
    def __init__(self, host: str = "localhost", port: int = 8765) -> None:
        if hasattr(self, "initialized") and self.initialized:
            return
        
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.sessions_ws: Dict[str, WebSocketServerProtocol] = {}
        self.session_mgr = SessionManager()
        self.message_queues: Dict[str, asyncio.Queue] = {}
        self._queue_maxsize: int = 500
        
        self._unified_manager: Optional[UnifiedWebSocketManager] = None
        
        try:
            from AloneChat.api.routes_base import load_user_credentials
            for _u in load_user_credentials().keys():
                self._ensure_queue(_u)
        except Exception:
            pass
        
        self.initialized = True
        logger.info("WebSocketManager initialized on %s:%s (DEPRECATED)", host, port)
    
    def _ensure_queue(self, username: str) -> None:
        """Ensure a bounded asyncio.Queue exists for the given user."""
        if username not in self.message_queues:
            self.message_queues[username] = asyncio.Queue(maxsize=self._queue_maxsize)
    
    @staticmethod
    def _extract_token(websocket: WebSocketServerProtocol) -> Optional[str]:
        """Extract JWT token from WebSocket connection."""
        from urllib.parse import parse_qs
        
        token = None
        request_path = getattr(websocket, "request", None)
        path = None
        
        if request_path is not None:
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
                cookie_header = getattr(
                    websocket, "request", {}
                ).get("headers", {}) if websocket else ""
            
            if cookie_header:
                for cookie in cookie_header.split(";"):
                    if "authToken=" in cookie:
                        token = cookie.split("=", 1)[1].strip()
                        break
        
        return token
    
    @staticmethod
    def _verify_jwt(token: str) -> Optional[str]:
        """Verify JWT token and return username."""
        import jwt
        from AloneChat.config import config
        
        try:
            payload = jwt.decode(
                token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
            )
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            raise
        except Exception:
            raise
    
    async def handler(self, websocket: WebSocketServerProtocol) -> None:
        """
        Handle WebSocket connection.
        
        Deprecated: This method is kept for backward compatibility.
        """
        _deprecated_warning(
            "WebSocketManager.handler() is deprecated. "
            "Use UnifiedWebSocketManager directly."
        )
        
        try:
            token = self._extract_token(websocket)
            if not token:
                msg = Message(
                    MessageType.TEXT, "SERVER",
                    "No verify token provided, please login first"
                )
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="Unauthorized: No token")
                return
            
            try:
                username = self._verify_jwt(token)
            except Exception as e:
                msg = Message(MessageType.TEXT, "SERVER", f"Invalid token: {e}")
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="Invalid token")
                return
            
            if not username:
                msg = Message(
                    MessageType.TEXT, "SERVER",
                    "There is no username in token"
                )
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="Invalid token payload")
                return
            
            if username in self.sessions_ws:
                msg = Message(
                    MessageType.TEXT, "SERVER",
                    f"User '{username}' already logged in at another location."
                )
                await websocket.send(msg.serialize())
                await websocket.close(code=1008, reason="User already logged in")
                return
            
            self.sessions_ws[username] = websocket
            self.session_mgr.add(username)
            
            try:
                from AloneChat.api.routes import update_user_online_status
                update_user_online_status(username, True)
            except Exception:
                pass
            
            logger.info("User %s connected", username)
            
            join_msg = Message(MessageType.JOIN, username, "User joined the chat")
            await self.broadcast(join_msg)
            
        except Exception as e:
            logger.exception("Unexpected error during websocket auth: %s", e)
            return
        
        self.clients.add(websocket)
        self._ensure_queue(username)
        
        try:
            async for raw in websocket:
                try:
                    msg = Message.deserialize(raw)
                except Exception:
                    continue
                
                if msg.type == MessageType.JOIN:
                    continue
                if msg.type == MessageType.HEARTBEAT:
                    self.session_mgr.touch(msg.sender)
                    pong = Message(MessageType.HEARTBEAT, "SERVER", "pong")
                    ws = self.sessions_ws.get(msg.sender)
                    if ws:
                        await self._safe_send(ws, pong.serialize())
                    continue
                
                await self.process_message(msg)
        
        except Exception:
            logger.exception("Error in websocket receive loop")
        finally:
            self.clients.discard(websocket)
            for uname, ws in list(self.sessions_ws.items()):
                if ws == websocket:
                    del self.sessions_ws[uname]
                    self.session_mgr.remove(uname)
                    try:
                        from AloneChat.api.routes import update_user_online_status
                        update_user_online_status(uname, False)
                    except Exception:
                        pass
                    leave_msg = Message(MessageType.LEAVE, uname, "User left the chat")
                    await self.broadcast(leave_msg)
                    logger.info("User %s disconnected", uname)
                    break
    
    async def process_message(self, msg: Message) -> None:
        """Process incoming message."""
        from AloneChat.core.server.command import CommandSystem
        
        if msg.sender not in self.sessions_ws:
            logger.warning("Message from unlogged user %s", msg.sender)
            return
        
        if msg.type == MessageType.HEARTBEAT:
            ws = self.sessions_ws.get(msg.sender)
            if ws:
                await self._safe_send(
                    ws, Message(MessageType.HEARTBEAT, "SERVER", "pong").serialize()
                )
            return
        else:
            response = CommandSystem.process(msg.content, msg.sender, msg.target)
            ws = self.sessions_ws.get(msg.sender)
            if ws:
                await self._safe_send(ws, response.serialize())
                return
        
        if msg.target:
            await self._send_to_target(msg)
        else:
            await self.broadcast(msg)
    
    async def broadcast(self, msg: Message) -> None:
        """Broadcast message to all clients."""
        data = msg.serialize()
        
        if self.clients:
            tasks = [
                asyncio.create_task(self._safe_send(client, data))
                for client in list(self.clients)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
        
        try:
            from AloneChat.api.routes_base import load_user_credentials
            for _u in load_user_credentials().keys():
                self._ensure_queue(_u)
        except Exception:
            pass
        
        for username, q in list(self.message_queues.items()):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(data)
                except Exception:
                    pass
    
    async def _send_to_target(self, msg: Message) -> None:
        """Send message to target user."""
        if msg.target not in self.sessions_ws and msg.target not in self.message_queues:
            logger.warning("Target user %s does not exist", msg.target)
            return
        
        data = msg.serialize()
        
        sender_ws = self.sessions_ws.get(msg.sender)
        target_ws = self.sessions_ws.get(msg.target)
        
        if target_ws:
            await self._safe_send(target_ws, data)
        
        if sender_ws and sender_ws != target_ws:
            await self._safe_send(sender_ws, data)
        
        if msg.target:
            self._ensure_queue(msg.target)
            try:
                self.message_queues[msg.target].put_nowait(data)
            except asyncio.QueueFull:
                try:
                    _ = self.message_queues[msg.target].get_nowait()
                    self.message_queues[msg.target].put_nowait(data)
                except Exception:
                    pass
    
    async def _safe_send(self, client: WebSocketServerProtocol, message: str) -> None:
        """Safely send message to client."""
        try:
            await client.send(message)
        except Exception as e:
            logger.warning("Failed to send to client: %s", e)
            if client in self.clients:
                self.clients.discard(client)
            for username, ws in list(self.sessions_ws.items()):
                if ws == client:
                    del self.sessions_ws[username]
                    self.session_mgr.remove(username)
                    try:
                        from AloneChat.api.routes import update_user_online_status
                        update_user_online_status(username, False)
                    except Exception:
                        pass
                    leave_msg = Message(MessageType.LEAVE, username, "User left the chat")
                    asyncio.create_task(self.broadcast(leave_msg))
                    break
    
    async def run(self) -> None:
        """Run the WebSocket server."""
        import websockets
        
        _deprecated_warning(
            "WebSocketManager.run() is deprecated. "
            "Use UnifiedWebSocketManager with async context manager."
        )
        
        async with websockets.serve(self.handler, self.host, self.port):
            logger.info("Server running on ws://%s:%s (DEPRECATED)", self.host, self.port)
            await asyncio.Future()
