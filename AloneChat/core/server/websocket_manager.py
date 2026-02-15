"""
Unified WebSocket manager that composes all server components.

This is the main entry point that orchestrates authentication,
session management, message routing, and command processing.

Enhanced with plugin system integration for pre/post processing hooks.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    UnifiedWebSocketManager                      │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
    │  │ Auth        │  │ Session     │  │ Plugin Manager          │  │
    │  │ Middleware  │  │ Manager     │  │ (Pre/Post Hooks)        │  │
    │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
    │  │ Connection  │  │ Message     │  │ Command                 │  │
    │  │ Registry    │  │ Router      │  │ Processor               │  │
    │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
    └─────────────────────────────────────────────────────────────────┘

Hook Execution Order:
    1. PRE_CONNECT → PRE_AUTHENTICATE → POST_AUTHENTICATE → POST_CONNECT
    2. PRE_MESSAGE → PRE_COMMAND → [command processing] → POST_COMMAND → POST_MESSAGE
    3. PRE_BROADCAST → [broadcast] → POST_BROADCAST
    4. PRE_DISCONNECT → [cleanup] → POST_DISCONNECT
"""

import asyncio
import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, List, Optional, Set

import websockets
from websockets.asyncio.server import ServerConnection

from AloneChat.core.message.protocol import Message, MessageType
from AloneChat.core.server.auth import JWTAuthenticator, AuthenticationMiddleware
from AloneChat.core.server.commands import CommandProcessor, create_default_processor
from AloneChat.core.server.interfaces import (
    AuthResult,
    HookContext,
    HookPhase,
    PluginAwareComponent,
    ProcessingResult,
)
from AloneChat.core.server.routing import MessageRouter, BroadcastServiceImpl
from AloneChat.core.server.session import SessionManager
from AloneChat.core.server.social_store import SocialStore
from AloneChat.core.server import presence
from AloneChat.core.server.transport import (
    WebSocketConnection,
    TransportFactory
)
from AloneChat.plugins import PluginManager, create_plugin_manager

logger = logging.getLogger(__name__)

_DM_HEADER_RE = re.compile(r"^\[\[DM\s+to=(?P<to>[A-Za-z0-9_.-]+)\]\]\s*\n?", re.IGNORECASE)


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
        self._metadata: Dict[str, Any] = {}
    
    @property
    def metadata(self) -> Dict[str, Any]:
        """Get connection metadata."""
        return self._metadata
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata value."""
        self._metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value."""
        return self._metadata.get(key, default)
    
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


class MessageProcessingPipeline:
    """
    Pipeline for processing messages through plugins and commands.
    
    Integrates the plugin system with command processing to provide
    a unified processing flow with pre- / post-hooks.
    """
    
    def __init__(
        self,
        command_processor: CommandProcessor,
        plugin_manager: Optional[PluginManager] = None
    ):
        """
        Initialize the processing pipeline.
        
        Args:
            command_processor: Command processor instance
            plugin_manager: Optional plugin manager for extended processing
        """
        self._command_processor = command_processor
        self._plugin_manager = plugin_manager
        self._pre_processors: List[Callable[[str, str, Optional[str]], str]] = []
        self._post_processors: List[Callable[[ProcessingResult], None]] = []
    
    def add_pre_processor(
        self,
        processor: Callable[[str, str, Optional[str]], str]
    ) -> None:
        """Add a pre-processor function."""
        self._pre_processors.append(processor)
    
    def add_post_processor(
        self,
        processor: Callable[[ProcessingResult], None]
    ) -> None:
        """Add a post-processor function."""
        self._post_processors.append(processor)
    
    async def process(
        self,
        content: str,
        sender: str,
        target: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ProcessingResult:
        """
        Process a message through the full pipeline.
        
        Args:
            content: Message content
            sender: Sender username
            target: Optional target user
            context: Additional context
            
        Returns:
            ProcessingResult with processed content
        """
        result_content = content
        modified = False
        result_message_type = None
        result_target = target
        
        for processor in self._pre_processors:
            try:
                processed = processor(result_content, sender, target)
                if processed != result_content:
                    result_content = processed
                    modified = True
            except Exception as e:
                logger.exception("Error in pre-processor: %s", e)
        
        if self._plugin_manager:
            try:
                plugin_result = self._plugin_manager.process_command(
                    result_content, sender, target
                )
                if plugin_result != result_content:
                    result_content = plugin_result
                    modified = True
            except Exception as e:
                logger.exception("Error in plugin processing: %s", e)
        
        try:
            message = self._command_processor.process(
                result_content, sender, target
            )
            if message.content != result_content:
                result_content = message.content
                modified = True
            if message.type != MessageType.TEXT:
                result_message_type = message.type
            if message.target and message.target != target:
                result_target = message.target
        except Exception as e:
            logger.exception("Error in command processing: %s", e)
        
        result = ProcessingResult(
            success=True,
            content=result_content,
            modified=modified,
            metadata=context or {},
            message_type=result_message_type,
            response_target=result_target
        )
        
        for processor in self._post_processors:
            try:
                processor(result)
            except Exception as e:
                logger.exception("Error in post-processor: %s", e)
        
        return result


class UnifiedWebSocketManager(PluginAwareComponent):
    """
    Unified WebSocket manager that composes all server components.
    
    This class provides a clean, modular interface for managing
    WebSocket connections, authentication, sessions, and messaging.
    
    Features:
        - Plugin-aware architecture with pre- / post-hooks
        - Modular component composition
        - Clean separation of concerns
        - Backward compatibility with legacy code
        - Comprehensive error handling
    
    Example:
        manager = UnifiedWebSocketManager()
        
        # Register hooks
        manager.register_hook(HookPhase.PRE_MESSAGE, my_pre_hook)
        manager.register_hook(HookPhase.POST_MESSAGE, my_post_hook)
        
        # Start server
        async with manager.run("localhost", 8765):
            await asyncio.Future()
    """
    
    def __init__(
        self,
        authenticator: Optional[JWTAuthenticator] = None,
        session_manager: Optional[SessionManager] = None,
        command_processor: Optional[CommandProcessor] = None,
        plugin_manager: Optional[PluginManager] = None,
        on_user_connect: Optional[Callable[[str], None]] = None,
        on_user_disconnect: Optional[Callable[[str], None]] = None,
        enable_plugins: bool = True
    ):
        """
        Initialize the WebSocket manager.
        
        Args:
            authenticator: JWT authenticator (creates default if None)
            session_manager: Session manager (creates default if None)
            command_processor: Command processor (creates default if None)
            plugin_manager: Plugin manager for extended processing
            on_user_connect: Callback when user connects (user_id)
            on_user_disconnect: Callback when user disconnects (user_id)
            enable_plugins: Whether to enable plugin system integration
        """
        super().__init__()
        
        self._authenticator = authenticator or JWTAuthenticator()
        self._auth_middleware = AuthenticationMiddleware(self._authenticator)
        self._session_manager = session_manager or SessionManager()
        
        self._connection_registry = TransportFactory.create_registry()
        
        self._message_router = MessageRouter(self._connection_registry)
        self._broadcast_service = BroadcastServiceImpl(self._message_router)

        self._social_store = SocialStore()
        
        self._command_processor = command_processor or create_default_processor()
        
        self._plugin_manager = plugin_manager
        self._enable_plugins = enable_plugins
        
        if enable_plugins and plugin_manager is None:
            try:
                self._plugin_manager = create_plugin_manager(
                    plugin_paths=["./AloneChat/plugins"],
                    auto_load=True,
                    auto_init=True
                )
            except Exception as e:
                logger.warning("Could not initialize plugin manager: %s", e)
                self._plugin_manager = None
        
        self._processing_pipeline = MessageProcessingPipeline(
            self._command_processor,
            self._plugin_manager
        )
        
        self._health_monitor = TransportFactory.create_health_monitor(
            self._connection_registry,
            on_disconnect=self._handle_disconnect
        )
        self._presence_task = None  # asyncio.Task
        
        self._on_user_connect = on_user_connect
        self._on_user_disconnect = on_user_disconnect
        
        self._host: Optional[str] = None
        self._port: Optional[int] = None
        self._server = None
        self._running = False
        
        self._connection_contexts: Dict[str, dict[str, ConnectionContext]] = {}  # user -> conn_id -> ctx
        
        logger.info("UnifiedWebSocketManager initialized")
    
    @property
    def plugin_manager(self) -> Optional[PluginManager]:
        """Get the plugin manager."""
        return self._plugin_manager
    
    @property
    def processing_pipeline(self) -> MessageProcessingPipeline:
        """Get the message processing pipeline."""
        return self._processing_pipeline
    
    @property
    def connection_contexts(self) -> Dict[str, ConnectionContext]:
        """Get all connection contexts."""
        return self._connection_contexts.copy()
    
    def get_connection_context(self, user_id: str) -> Optional[ConnectionContext]:
        """Get connection context for a user."""
        return self._connection_contexts.get(user_id)
    
    @asynccontextmanager
    async def run(self, host: str = "localhost", port: int = 8765):
        """
        Run the WebSocket server as an async context manager.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            
        Yields:
            The manager instance
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
        
        await self._health_monitor.start()
        # Presence monitor: prune stale heartbeats (multi-device)
        self._presence_task = asyncio.create_task(self._presence_monitor_loop())
        
        self._server = await websockets.serve(
            self._handle_connection,
            host,
            port
        )
        
        logger.info("WebSocket server started on ws://%s:%s", host, port)
    
    async def stop(self) -> None:
        """Stop the WebSocket server."""
        self._running = False
        
        await self._health_monitor.stop()
        if self._presence_task:
            self._presence_task.cancel()
            try:
                await self._presence_task
            except asyncio.CancelledError:
                pass
            self._presence_task = None

        
        for user_id, conn in list(self._connection_registry.get_all_connections().items()):
            try:
                await conn.close(1001, "Server shutting down")
            except Exception as e:
                logger.debug("Error closing connection for %s: %s", user_id, e)
        
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        if self._plugin_manager:
            self._plugin_manager.shutdown_all()
        
        logger.info("WebSocket server stopped")
    
    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """
        Handle a new WebSocket connection.
        
        Executes hooks at each phase of the connection lifecycle.
        """
        connection_wrapper = None
        username = None
        
        try:
            hook_ctx = HookContext(phase=HookPhase.PRE_CONNECT, connection=websocket)
            hook_ctx = await self._execute_hooks(HookPhase.PRE_CONNECT, hook_ctx)
            
            hook_ctx.phase = HookPhase.PRE_AUTHENTICATE
            hook_ctx = await self._execute_hooks(HookPhase.PRE_AUTHENTICATE, hook_ctx)
            
            auth_result = await self._auth_middleware.authenticate_connection(websocket)
            
            hook_ctx.phase = HookPhase.POST_AUTHENTICATE
            hook_ctx.metadata['auth_result'] = auth_result
            hook_ctx = await self._execute_hooks(HookPhase.POST_AUTHENTICATE, hook_ctx)
            
            if not auth_result.success:
                await self._send_auth_error(websocket, auth_result)
                return
            
            username = auth_result.username
            
            connection_wrapper = WebSocketConnection(websocket, username)
            # identifiers for multi-device online
            connection_wrapper.conn_id = uuid.uuid4().hex  # type: ignore[attr-defined]
            connection_wrapper.device_id = uuid.uuid4().hex  # type: ignore[attr-defined]
            if hasattr(connection_wrapper, 'touch'):
                connection_wrapper.touch()

            self._session_manager.create_session(username)
            
            self._connection_registry.register(username, connection_wrapper)
            # presence register
            evict_conn_id = presence.register(
                username,
                getattr(connection_wrapper, 'conn_id', uuid.uuid4().hex),
                getattr(connection_wrapper, 'device_id', uuid.uuid4().hex)
            )
            # If presence module evicted an old connection, close it (kick oldest)
            if evict_conn_id:
                old_ctx = self._connection_contexts.get(username, {}).pop(evict_conn_id, None)
                try:
                    self._connection_registry.unregister_connection(username, evict_conn_id)  # type: ignore[attr-defined]
                except Exception:
                    pass
                if old_ctx and hasattr(old_ctx.connection, 'close'):
                    try:
                        await old_ctx.connection.close(4000, 'Kicked: too many devices')
                    except Exception:
                        pass

            
            context = ConnectionContext(username, connection_wrapper, self)
            cid = getattr(connection_wrapper, 'conn_id', uuid.uuid4().hex)
            self._connection_contexts.setdefault(username, {})[cid] = context
            
            hook_ctx.phase = HookPhase.POST_CONNECT
            hook_ctx.user_id = username
            hook_ctx.connection = connection_wrapper
            hook_ctx = await self._execute_hooks(HookPhase.POST_CONNECT, hook_ctx)
            
            if self._on_user_connect:
                try:
                    self._on_user_connect(username)
                except Exception as e:
                    logger.exception("Error in user connect callback: %s", e)
            
            await self._broadcast_service.notify_user_joined(username, exclude=[username])
            
            logger.info("User %s connected", username)
            
            await self._message_loop(context, websocket)
            
        except websockets.exceptions.ConnectionClosed:
            logger.debug("Connection closed for %s", username or "unknown")
        except Exception as e:
            logger.exception("Error handling connection: %s", e)
        finally:
            if username and connection_wrapper:
                await self._cleanup_connection(username, getattr(connection_wrapper, 'conn_id', None))
    
    async def _message_loop(
        self,
        context: ConnectionContext,
        websocket: ServerConnection
    ) -> None:
        """
        Main message processing loop for a connection.
        """
        async for raw_message in websocket:
            try:
                message = Message.deserialize(raw_message)
                
                if message.type == MessageType.JOIN:
                    continue
                
                if message.type == MessageType.HEARTBEAT:
                    await self._handle_heartbeat(context, message)
                    continue
                
                self._session_manager.update_activity(context.user_id)
                
                await self._process_message(context, message)
                
            except Exception as e:
                logger.exception("Error processing message: %s", e)
    
    async def _handle_heartbeat(self, context: ConnectionContext, message: Message) -> None:
        """Handle heartbeat message."""
        self._session_manager.update_activity(context.user_id)
        try:
            cid = getattr(context.connection, 'conn_id', None)
            if cid:
                presence.touch(context.user_id, cid)
            if hasattr(context.connection, 'touch'):
                context.connection.touch()
        except Exception:
            pass
        await self._broadcast_service.send_pong(context.user_id)
    
    async def _process_message(self, context: ConnectionContext, message: Message) -> None:
        """
        Process a chat message through the full pipeline.
        """
        hook_ctx = HookContext(
            phase=HookPhase.PRE_MESSAGE,
            user_id=context.user_id,
            message=message,
            connection=context.connection
        )
        hook_ctx = await self._execute_hooks(HookPhase.PRE_MESSAGE, hook_ctx)
        
        if hook_ctx.message:
            message = hook_ctx.message

        # Detect DM header ([[DM to=USER]]) and set target
        m = _DM_HEADER_RE.match(message.content or "")
        if m:
            message.target = m.group('to')

        result = await self._processing_pipeline.process(
            content=message.content,
            sender=context.user_id,
            target=message.target,
            context={'original_message': message}
        )
        
        hook_ctx.phase = HookPhase.POST_MESSAGE
        hook_ctx.metadata['processing_result'] = result
        hook_ctx = await self._execute_hooks(HookPhase.POST_MESSAGE, hook_ctx)

        if result.modified or result.content != message.content:
            response_type = result.message_type or MessageType.TEXT
            response_target = result.response_target if result.response_target else message.target
        
            response = Message(
                response_type,
                context.user_id,
                result.content,
                target=response_target
            )
        
            # Always echo back to sender (keep existing UX)
            await context.send(response)
        
            # Route message to target or broadcast for TEXT messages
            if response_type == MessageType.TEXT:
                if message.target:
                    # Friend gate for DM
                    if not self._social_store.are_friends(context.user_id, message.target):
                        deny = Message(
                            MessageType.TEXT,
                            "SERVER",
                            f"Cannot DM {message.target}: not friends yet.",
                            target=context.user_id
                        )
                        await context.send(deny)
                        return
                    await self._send_to_target(response)
                else:
                    hook_ctx.phase = HookPhase.PRE_BROADCAST
                    hook_ctx = await self._execute_hooks(HookPhase.PRE_BROADCAST, hook_ctx)
        
                    await self._broadcast_service.broadcast_text(
                        result.content,
                        sender=context.user_id,
                        exclude=[context.user_id]
                    )
        
                    hook_ctx.phase = HookPhase.POST_BROADCAST
                    hook_ctx = await self._execute_hooks(HookPhase.POST_BROADCAST, hook_ctx)
        
            
    async def _cleanup_connection(self, username: str, conn_id: str | None = None) -> None:
        """
        Clean up after a connection closes.
        """
        hook_ctx = HookContext(
            phase=HookPhase.PRE_DISCONNECT,
            user_id=username
        )
        hook_ctx = await self._execute_hooks(HookPhase.PRE_DISCONNECT, hook_ctx)
        
        if conn_id and hasattr(self._connection_registry, 'unregister_connection'):
            self._connection_registry.unregister_connection(username, conn_id)  # type: ignore[attr-defined]
        else:
            self._connection_registry.unregister(username)
        if conn_id:
            presence.unregister(username, conn_id)
        
        if not self._connection_registry.is_connected(username):
            self._session_manager.end_session(username)
            self._message_router.remove_user_queue(username)
        # remove only this context
        if conn_id:
            self._connection_contexts.get(username, {}).pop(conn_id, None)
            if not self._connection_contexts.get(username):
                self._connection_contexts.pop(username, None)
        else:
            self._connection_contexts.pop(username, None)
        

        # Only treat as fully offline when no active presence remains
        is_fully_offline = (not presence.is_online(username)) and (not self._connection_registry.is_connected(username))

        if is_fully_offline:
            if self._on_user_disconnect:
                try:
                    self._on_user_disconnect(username)
                except Exception as e:
                    logger.exception("Error in user disconnect callback: %s", e)

            await self._broadcast_service.notify_user_left(username)
        
        hook_ctx.phase = HookPhase.POST_DISCONNECT
        hook_ctx = await self._execute_hooks(HookPhase.POST_DISCONNECT, hook_ctx)
        
        logger.info("User %s disconnected", username)
    
    def _handle_disconnect(self, user_id: str) -> None:
        """Handle disconnect detected by health monitor."""
        asyncio.create_task(self._cleanup_connection(user_id))

    async def _presence_monitor_loop(self) -> None:
        """Prune stale heartbeat connections and mark users offline."""
        while self._running:
            try:
                removed = presence.prune_stale()
                # Cleanup removed connections (best-effort)
                for username, conn_id in removed:
                    try:
                        await self._cleanup_connection(username, conn_id)
                    except Exception:
                        pass
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Presence monitor error: %s", e)
                await asyncio.sleep(5)

    # noinspection PyMethodMayBeStatic
    async def _send_auth_error(
        self,
        websocket: ServerConnection,
        result: AuthResult
    ) -> None:
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

    # noinspection PyMethodMayBeStatic
    async def _send_duplicate_error(
        self,
        websocket: ServerConnection,
        username: str
    ) -> None:
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
    
    async def broadcast(
        self,
        message: Message,
        exclude: Optional[list] = None
    ) -> None:
        """
        Broadcast a message to all users.
        """
        await self._message_router.broadcast(message, exclude)
    
    async def send_to_user(self, username: str, message: Message) -> bool:
        """
        Send a message to a specific user.
        """
        result = await self._message_router.send_to_user(username, message)
        
        # Also put message in legacy queue for HTTP polling clients
        if hasattr(self, '_legacy_message_queues'):
            queue = self._legacy_message_queues.get(username)
            if queue:
                try:
                    queue.put_nowait(message.serialize())
                except asyncio.QueueFull:
                    try:
                        _ = queue.get_nowait()
                        queue.put_nowait(message.serialize())
                    except Exception:
                        pass
        
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
    
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running

    # ==================== Legacy Compatibility Layer ====================
    
    @property
    def sessions(self) -> Dict[str, Any]:
        """
        Legacy compatibility: Get active sessions mapping username to connection.
        
        Returns:
            Dictionary mapping username to connection info
        """
        return {
            user_id: ctx.connection.raw_websocket
            for user_id, ctx in self._connection_contexts.items()
        }
    
    @property
    def clients(self) -> Set[ServerConnection]:
        """
        Legacy compatibility: Get set of all client connections.
        
        Returns:
            Set of raw WebSocket connections
        """
        return {
            ctx.connection.raw_websocket
            for ctx in self._connection_contexts.values()
        }
    
    def _ensure_queue(self, username: str) -> None:
        """
        Legacy compatibility: Ensure message queue exists for user.
        
        Args:
            username: Username to ensure queue for
        """
        # Access message_queues property to ensure proper initialization
        _ = self.message_queues[username]
    
    class _MessageQueuesDict(dict):
        """Custom dict that auto-creates queues on access."""
        
        def __init__(self, manager: 'UnifiedWebSocketManager'):
            super().__init__()
            self._manager = manager
        
        def __getitem__(self, key: str) -> asyncio.Queue:
            # Auto-create queue if it doesn't exist
            if not super().__contains__(key):
                super().__setitem__(key, asyncio.Queue(maxsize=500))
            return super().__getitem__(key)
        
        def __contains__(self, key: object) -> bool:
            # Check if key exists without creating it
            return super().__contains__(key)
    
    @property
    def message_queues(self) -> Dict[str, asyncio.Queue]:
        """
        Legacy compatibility: Get message queues for HTTP polling.
        
        Returns:
            Dictionary mapping username to message queue (auto-creates on access)
        """
        # Create queues on-demand for HTTP polling compatibility
        if not hasattr(self, '_legacy_message_queues'):
            self._legacy_message_queues = self._MessageQueuesDict(self)
        return self._legacy_message_queues
    
    async def broadcast(self, message: Message) -> None:
        """
        Legacy compatibility: Broadcast a message to all connected clients.
        Also processes commands and sends responses back to the sender.
        
        Args:
            message: Message to broadcast
        """
        # Process the message through the command pipeline
        result = self._command_processor.process(
            message.content,
            message.sender,
            message.target
        )
        
        # Check if this was a command that produced a response
        if result.content != message.content or result.type != MessageType.TEXT or result.target:
            # This was a command - send response back to sender only
            await self.send_to_user(message.sender, result)
            # Don't broadcast the original command message
            return
        
        # Not a command - broadcast the message normally
        await self._message_router.broadcast(message)
        
        # Also put message in legacy queues for HTTP polling
        if hasattr(self, '_legacy_message_queues'):
            for username, queue in list(self._legacy_message_queues.items()):
                try:
                    queue.put_nowait(message.serialize())
                except asyncio.QueueFull:
                    try:
                        _ = queue.get_nowait()
                        queue.put_nowait(message.serialize())
                    except Exception:
                        pass
    
    async def _send_to_target(self, message: Message) -> None:
        """
        Legacy compatibility: Send a message to a specific target user.
        
        Args:
            message: Message to send (target must be set)
        """
        if not message.target:
            return
        
        await self.send_to_user(message.target, message)
        
        # Also send to sender if different from target
        if message.sender != message.target:
            await self.send_to_user(message.sender, message)


def create_server(
    host: str = "localhost",
    port: int = 8765,
    enable_plugins: bool = True,
    **kwargs
) -> UnifiedWebSocketManager:
    """
    Factory function to create a configured WebSocket server.
    
    Args:
        host: Server host
        port: Server port
        enable_plugins: Whether to enable plugins
        **kwargs: Additional arguments passed to UnifiedWebSocketManager
        
    Returns:
        Configured UnifiedWebSocketManager instance
    """
    manager = UnifiedWebSocketManager(enable_plugins=enable_plugins, **kwargs)
    return manager
