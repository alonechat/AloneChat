"""
Unified WebSocket manager that composes all server components.

This is the main entry point that orchestrates authentication,
session management, message routing, and command processing.
"""

import asyncio
import logging
from typing import Optional, Callable, Any
from contextlib import asynccontextmanager

import websockets
from websockets.server import WebSocketServerProtocol

from AloneChat.core.server.interfaces import AuthResult
from AloneChat.core.server.auth import JWTAuthenticator, AuthenticationMiddleware, DefaultTokenExtractor
from AloneChat.core.server.session import SessionManager, InMemorySessionStore
from AloneChat.core.server.transport import (
    WebSocketConnection,
    WebSocketConnectionRegistry,
    ConnectionHealthMonitor,
    TransportFactory
)
from AloneChat.core.server.routing import MessageRouter, BroadcastServiceImpl
from AloneChat.core.server.commands import CommandProcessor, create_default_processor
from AloneChat.core.message.protocol import Message, MessageType

logger = logging.getLogger(__name__)


class ConnectionContext:
    """
    Context for a single WebSocket connection.
    
    Holds all relevant information about an active connection
    and provides helper methods for interaction.
    """
    
    def __init__(
        self,
        user_id: str,
        connection: WebSocketConnection,
        manager: 'UnifiedWebSocketManager'
    ):
        """
        Initialize connection context.
        
        Args:
            user_id: Authenticated user ID
            connection: WebSocket connection wrapper
            manager: Parent WebSocket manager
        """
        self.user_id = user_id
        self.connection = connection
        self._manager = manager
    
    async def send(self, message: Message) -> bool:
        """Send a message to this connection."""
        return await self.connection.send(message.serialize())
    
    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close this connection."""
        await self.connection.close(code, reason)
    
    async def send_system_message(self, content: str) -> bool:
        """Send a system message to this user."""
        msg = Message(MessageType.TEXT, "SERVER", content)
        return await self.send(msg)
    
    @property
    def is_active(self) -> bool:
        """Check if connection is still active."""
        return self.connection.is_open()


class UnifiedWebSocketManager:
    """
    Unified WebSocket manager that composes all server components.
    
    This class provides a clean, modular interface for managing
    WebSocket connections, authentication, sessions, and messaging.
    
    Architecture:
        - Authentication: JWT-based with pluggable extractors
        - Sessions: In-memory with automatic cleanup
        - Transport: WebSocket with connection registry
        - Routing: Message router with delivery tracking
        - Commands: Modular command processor with plugin support
    
    Example:
        manager = UnifiedWebSocketManager()
        await manager.start("localhost", 8765)
    """
    
    def __init__(
        self,
        authenticator: Optional[JWTAuthenticator] = None,
        session_manager: Optional[SessionManager] = None,
        command_processor: Optional[CommandProcessor] = None,
        on_user_connect: Optional[Callable[[str], None]] = None,
        on_user_disconnect: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the WebSocket manager.
        
        Args:
            authenticator: JWT authenticator (creates default if None)
            session_manager: Session manager (creates default if None)
            command_processor: Command processor (creates default if None)
            on_user_connect: Callback when user connects (user_id)
            on_user_disconnect: Callback when user disconnects (user_id)
        """
        # Components
        self._authenticator = authenticator or JWTAuthenticator()
        self._auth_middleware = AuthenticationMiddleware(self._authenticator)
        self._session_manager = session_manager or SessionManager()
        
        # Transport layer
        self._connection_registry = TransportFactory.create_registry()
        
        # Routing
        self._message_router = MessageRouter(self._connection_registry)
        self._broadcast_service = BroadcastServiceImpl(self._message_router)
        
        # Commands
        self._command_processor = command_processor or create_default_processor()
        
        # Health monitoring
        self._health_monitor = TransportFactory.create_health_monitor(
            self._connection_registry,
            on_disconnect=self._handle_disconnect
        )
        
        # Callbacks
        self._on_user_connect = on_user_connect
        self._on_user_disconnect = on_user_disconnect
        
        # State
        self._host: Optional[str] = None
        self._port: Optional[int] = None
        self._server = None
        self._running = False
        
        logger.info("UnifiedWebSocketManager initialized")
    
    @asynccontextmanager
    async def run(self, host: str = "localhost", port: int = 8765):
        """
        Run the WebSocket server as an async context manager.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            
        Yields:
            The manager instance
            
        Example:
            async with manager.run("localhost", 8765):
                await asyncio.Future()  # Run forever
        """
        await self.start(host, port)
        try:
            yield self
        finally:
            await self.stop()
    
    async def start(self, host: str = "localhost", port: int = 8765) -> None:
        """
        Start the WebSocket server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
        """
        self._host = host
        self._port = port
        self._running = True
        
        # Start health monitor
        await self._health_monitor.start()
        
        # Start server
        self._server = await websockets.serve(
            self._handle_connection,
            host,
            port
        )
        
        logger.info("WebSocket server started on ws://%s:%s", host, port)
    
    async def stop(self) -> None:
        """Stop the WebSocket server."""
        self._running = False
        
        # Stop health monitor
        await self._health_monitor.stop()
        
        # Close all connections
        for user_id, conn in list(self._connection_registry.get_all_connections().items()):
            try:
                await conn.close(1001, "Server shutting down")
            except Exception as e:
                logger.debug("Error closing connection for %s: %s", user_id, e)
        
        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        logger.info("WebSocket server stopped")
    
    async def _handle_connection(self, websocket: WebSocketServerProtocol) -> None:
        """
        Handle a new WebSocket connection.
        
        Args:
            websocket: WebSocket protocol instance
        """
        connection_wrapper = None
        username = None
        
        try:
            # Authenticate
            auth_result = await self._auth_middleware.authenticate_connection(websocket)
            
            if not auth_result.success:
                await self._send_auth_error(websocket, auth_result)
                return
            
            username = auth_result.username
            
            # Check for duplicate connections
            if self._connection_registry.is_connected(username):
                await self._send_duplicate_error(websocket, username)
                return
            
            # Create connection wrapper
            connection_wrapper = WebSocketConnection(websocket, username)
            
            # Create session
            self._session_manager.create_session(username)
            
            # Register connection
            self._connection_registry.register(username, connection_wrapper)
            
            # Create context
            context = ConnectionContext(username, connection_wrapper, self)
            
            # Notify
            if self._on_user_connect:
                try:
                    self._on_user_connect(username)
                except Exception as e:
                    logger.exception("Error in user connect callback: %s", e)
            
            # Send join message
            await self._broadcast_service.notify_user_joined(username, exclude=[username])
            
            logger.info("User %s connected", username)
            
            # Handle messages
            await self._message_loop(context, websocket)
            
        except websockets.exceptions.ConnectionClosed:
            logger.debug("Connection closed for %s", username or "unknown")
        except Exception as e:
            logger.exception("Error handling connection: %s", e)
        finally:
            # Cleanup
            if username:
                await self._cleanup_connection(username)
    
    async def _message_loop(
        self,
        context: ConnectionContext,
        websocket: WebSocketServerProtocol
    ) -> None:
        """
        Main message processing loop for a connection.
        
        Args:
            context: Connection context
            websocket: WebSocket protocol
        """
        async for raw_message in websocket:
            try:
                # Deserialize message
                message = Message.deserialize(raw_message)
                
                # Skip JOIN messages (already handled during connection)
                if message.type == MessageType.JOIN:
                    continue
                
                # Handle heartbeat
                if message.type == MessageType.HEARTBEAT:
                    await self._handle_heartbeat(context, message)
                    continue
                
                # Update activity
                self._session_manager.update_activity(context.user_id)
                
                # Process message
                await self._process_message(context, message)
                
            except Exception as e:
                logger.exception("Error processing message: %s", e)
    
    async def _handle_heartbeat(self, context: ConnectionContext, message: Message) -> None:
        """Handle heartbeat message."""
        self._session_manager.update_activity(context.user_id)
        await self._broadcast_service.send_pong(context.user_id)
    
    async def _process_message(self, context: ConnectionContext, message: Message) -> None:
        """
        Process a chat message.
        
        Args:
            context: Connection context
            message: Received message
        """
        # Process commands
        response = self._command_processor.process(
            content=message.content,
            sender=context.user_id,
            target=message.target,
            original_message=message
        )
        
        if response:
            # Send response to sender
            await context.send(response)
            
            # If it's not a command response (e.g., just text transformation),
            # also broadcast the message
            if response.type == MessageType.TEXT and response.sender == context.user_id:
                await self._broadcast_service.broadcast_text(
                    response.content,
                    sender=context.user_id
                )
    
    async def _cleanup_connection(self, username: str) -> None:
        """
        Clean up after a connection closes.
        
        Args:
            username: User ID
        """
        # Unregister connection
        self._connection_registry.unregister(username)
        
        # End session
        self._session_manager.end_session(username)
        
        # Clear message queue
        self._message_router.remove_user_queue(username)
        
        # Notify
        if self._on_user_disconnect:
            try:
                self._on_user_disconnect(username)
            except Exception as e:
                logger.exception("Error in user disconnect callback: %s", e)
        
        # Broadcast leave message
        await self._broadcast_service.notify_user_left(username)
        
        logger.info("User %s disconnected", username)
    
    def _handle_disconnect(self, user_id: str) -> None:
        """Handle disconnect detected by health monitor."""
        # This is called synchronously, so we just trigger cleanup
        asyncio.create_task(self._cleanup_connection(user_id))
    
    async def _send_auth_error(self, websocket: WebSocketServerProtocol, result: AuthResult) -> None:
        """Send authentication error and close connection."""
        error_msg = Message(
            MessageType.TEXT,
            "SERVER",
            result.error_message or "Authentication failed"
        )
        try:
            await websocket.send(error_msg.serialize())
            await websocket.close(code=1008, reason=result.error_code or "Unauthorized")
        except Exception:
            pass
    
    async def _send_duplicate_error(self, websocket: WebSocketServerProtocol, username: str) -> None:
        """Send duplicate connection error."""
        error_msg = Message(
            MessageType.TEXT,
            "SERVER",
            f"User '{username}' already logged in at another location."
        )
        try:
            await websocket.send(error_msg.serialize())
            await websocket.close(code=1008, reason="Already logged in")
        except Exception:
            pass
    
    # Public API for external use
    
    async def broadcast(self, message: Message, exclude: Optional[list] = None) -> None:
        """
        Broadcast a message to all users.
        
        Args:
            message: Message to broadcast
            exclude: List of usernames to exclude
        """
        await self._message_router.broadcast(message, exclude)
    
    async def send_to_user(self, username: str, message: Message) -> bool:
        """
        Send a message to a specific user.
        
        Args:
            username: Target username
            message: Message to send
            
        Returns:
            True if message was sent
        """
        result = await self._message_router.send_to_user(username, message)
        return result.status.name == "DELIVERED"
    
    def get_active_users(self) -> list[str]:
        """Get list of active users."""
        return list(self._connection_registry.get_all_connections().keys())
    
    def is_user_online(self, username: str) -> bool:
        """Check if a user is online."""
        return self._connection_registry.is_connected(username)
    
    @property
    def broadcast_service(self) -> BroadcastServiceImpl:
        """Get broadcast service."""
        return self._broadcast_service
    
    @property
    def command_processor(self) -> CommandProcessor:
        """Get command processor."""
        return self._command_processor
    
    @property
    def session_manager(self) -> SessionManager:
        """Get session manager."""
        return self._session_manager
