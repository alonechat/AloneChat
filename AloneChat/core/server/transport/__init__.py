"""
Transport layer abstraction for WebSocket connections.

Provides clean interfaces for connection management and
handles transport-specific details.
"""

import asyncio
import logging
from typing import Dict, Optional, Set, Any, Callable
from collections import defaultdict

import websockets
from websockets.server import WebSocketServerProtocol

from AloneChat.core.server.interfaces import TransportConnection, ConnectionRegistry

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """
    Wrapper around WebSocketServerProtocol that implements TransportConnection.
    
    Provides a clean interface for sending messages and managing
    connection state.
    """
    
    def __init__(self, websocket: WebSocketServerProtocol, user_id: str):
        """
        Initialize WebSocket connection wrapper.
        
        Args:
            websocket: Underlying WebSocket protocol
            user_id: Associated user ID
        """
        self._websocket = websocket
        self._user_id = user_id
        self._closed = False
    
    @property
    def user_id(self) -> str:
        """Get associated user ID."""
        return self._user_id
    
    @property
    def raw_websocket(self) -> WebSocketServerProtocol:
        """Get underlying WebSocket protocol."""
        return self._websocket
    
    async def send(self, message: str) -> bool:
        """
        Send a message through the connection.
        
        Args:
            message: Message to send
            
        Returns:
            True if message was sent successfully
        """
        if self._closed:
            return False
        
        try:
            await self._websocket.send(message)
            return True
        except Exception as e:
            logger.debug("Failed to send to %s: %s", self._user_id, e)
            return False
    
    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close the connection.
        
        Args:
            code: Close code
            reason: Close reason
        """
        if not self._closed:
            self._closed = True
            try:
                await self._websocket.close(code=code, reason=reason)
            except Exception as e:
                logger.debug("Error closing connection for %s: %s", self._user_id, e)
    
    def is_open(self) -> bool:
        """Check if connection is open."""
        if self._closed:
            return False
        
        # Check underlying WebSocket state
        try:
            return self._websocket.open
        except Exception:
            return False


class WebSocketConnectionRegistry(ConnectionRegistry):
    """
    Registry for managing WebSocket connections.
    
    Provides thread-safe (for asyncio) connection management
    with support for lookups by user ID.
    """
    
    def __init__(self):
        """Initialize connection registry."""
        self._connections: Dict[str, WebSocketConnection] = {}
        self._user_to_connection: Dict[str, WebSocketConnection] = {}
        self._lock = asyncio.Lock()
    
    def register(self, user_id: str, connection: WebSocketConnection) -> None:
        """
        Register a new connection.
        
        Args:
            user_id: User identifier
            connection: WebSocket connection wrapper
        """
        self._connections[user_id] = connection
        self._user_to_connection[user_id] = connection
        logger.debug("Registered connection for user %s", user_id)
    
    def unregister(self, user_id: str) -> Optional[WebSocketConnection]:
        """
        Unregister a connection.
        
        Args:
            user_id: User identifier
            
        Returns:
            The removed connection or None
        """
        connection = self._connections.pop(user_id, None)
        self._user_to_connection.pop(user_id, None)
        
        if connection:
            logger.debug("Unregistered connection for user %s", user_id)
        
        return connection
    
    def get_connection(self, user_id: str) -> Optional[WebSocketConnection]:
        """
        Get connection for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            WebSocketConnection or None
        """
        return self._connections.get(user_id)
    
    def get_all_connections(self) -> Dict[str, WebSocketConnection]:
        """
        Get all active connections.
        
        Returns:
            Dictionary mapping user IDs to connections
        """
        return self._connections.copy()
    
    def is_connected(self, user_id: str) -> bool:
        """
        Check if user is connected.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if user has an active connection
        """
        connection = self._connections.get(user_id)
        return connection is not None and connection.is_open()
    
    def get_all_clients(self) -> Set[WebSocketServerProtocol]:
        """
        Get all raw WebSocket clients.
        
        Returns:
            Set of WebSocketServerProtocol objects
        """
        return {
            conn.raw_websocket for conn in self._connections.values()
        }
    
    def __len__(self) -> int:
        """Return number of registered connections."""
        return len(self._connections)


class ConnectionHealthMonitor:
    """
    Monitors connection health and handles cleanup.
    
    Periodically checks connections and removes unhealthy ones.
    """
    
    def __init__(
        self,
        registry: ConnectionRegistry,
        check_interval: int = 30,
        on_disconnect: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize health monitor.
        
        Args:
            registry: Connection registry to monitor
            check_interval: Seconds between health checks
            on_disconnect: Callback for disconnect events
        """
        self._registry = registry
        self._check_interval = check_interval
        self._on_disconnect = on_disconnect
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the health monitor."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Connection health monitor started")
    
    async def stop(self) -> None:
        """Stop the health monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Connection health monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_connections()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in health monitor: %s", e)
                await asyncio.sleep(self._check_interval)
    
    async def _check_connections(self) -> None:
        """Check all connections and cleanup dead ones."""
        dead_connections = []
        
        for user_id, connection in self._registry.get_all_connections().items():
            if not connection.is_open():
                dead_connections.append(user_id)
        
        for user_id in dead_connections:
            self._registry.unregister(user_id)
            if self._on_disconnect:
                try:
                    self._on_disconnect(user_id)
                except Exception as e:
                    logger.exception("Error in disconnect callback: %s", e)
        
        if dead_connections:
            logger.info("Cleaned up %d dead connections", len(dead_connections))


class TransportFactory:
    """
    Factory for creating transport layer components.
    
    Provides a centralized way to create and configure
    transport components.
    """
    
    @staticmethod
    def create_connection(
        websocket: WebSocketServerProtocol,
        user_id: str
    ) -> WebSocketConnection:
        """
        Create a WebSocket connection wrapper.
        
        Args:
            websocket: WebSocket protocol
            user_id: User identifier
            
        Returns:
            WebSocketConnection wrapper
        """
        return WebSocketConnection(websocket, user_id)
    
    @staticmethod
    def create_registry() -> WebSocketConnectionRegistry:
        """Create a new connection registry."""
        return WebSocketConnectionRegistry()
    
    @staticmethod
    def create_health_monitor(
        registry: ConnectionRegistry,
        check_interval: int = 30,
        on_disconnect: Optional[Callable[[str], None]] = None
    ) -> ConnectionHealthMonitor:
        """
        Create a connection health monitor.
        
        Args:
            registry: Connection registry to monitor
            check_interval: Seconds between checks
            on_disconnect: Disconnect callback
            
        Returns:
            ConnectionHealthMonitor instance
        """
        return ConnectionHealthMonitor(registry, check_interval, on_disconnect)
