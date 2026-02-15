"""
Transport layer abstraction for WebSocket connections.

Provides clean interfaces for connection management and
handles transport-specific details.
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Optional, Set, Callable

from websockets.asyncio.server import ServerConnection

from AloneChat.core.server.interfaces import ConnectionRegistry

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """
    Wrapper around ServerConnection that implements TransportConnection.

    Provides a clean interface for sending messages and managing
    connection state.
    """

    def __init__(self, websocket: ServerConnection, user_id: str, device_id: str | None = None):
        """
        Initialize WebSocket connection wrapper.

        Args:
            websocket: Underlying WebSocket protocol
            user_id: Associated user ID
        """
        self._websocket = websocket
        self._user_id = user_id
        self._closed = False
        self.conn_id: str = uuid.uuid4().hex
        self.device_id: str = device_id or uuid.uuid4().hex
        self.last_heartbeat: float = time.time()

    @property
    def user_id(self) -> str:
        """Get associated user ID."""
        return self._user_id

    @property
    def raw_websocket(self) -> ServerConnection:
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
    
    def touch(self) -> None:
        """Update last heartbeat time."""
        self.last_heartbeat = time.time()

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
        # user -> conn_id -> connection
        self._connections: Dict[str, Dict[str, WebSocketConnection]] = {}
        self._lock = asyncio.Lock()
    
    def register(self, user_id: str, connection: WebSocketConnection) -> None:
        """
        Register a new connection (multi-device).
        Keeps up to 3 connections per user; evicts the stalest if needed.
        """
        conns = self._connections.setdefault(user_id, {})
        conns[connection.conn_id] = connection
        # enforce max 3
        if len(conns) > 3:
            items = list(conns.values())
            items.sort(key=lambda c: (c.last_heartbeat, c.conn_id))
            evict = items[0]
            if evict.conn_id != connection.conn_id:
                conns.pop(evict.conn_id, None)
                try:
                    # best-effort close
                    asyncio.create_task(evict.close())
                except Exception:
                    pass
        logger.debug("Registered connection for user %s (%s)", user_id, connection.conn_id)
    
    def unregister_connection(self, user_id: str, conn_id: str) -> Optional[WebSocketConnection]:
        """Unregister a specific connection."""
        conns = self._connections.get(user_id)
        if not conns:
            return None
        c = conns.pop(conn_id, None)
        if not conns:
            self._connections.pop(user_id, None)
        return c

    def unregister(self, user_id: str) -> Optional[WebSocketConnection]:
        """Unregister ALL connections for a user.

        Returns the most-recent connection (if any) for compatibility.
        """
        conns = self._connections.pop(user_id, None)
        if not conns:
            return None
        # best-effort close all
        for c in list(conns.values()):
            try:
                asyncio.create_task(c.close())
            except Exception:
                pass
        # return one connection object for backward compatibility
        return next(iter(conns.values()), None)

    def get_connections(self, user_id: str) -> list[WebSocketConnection]:
        conns = self._connections.get(user_id) or {}
        return list(conns.values())

    def get_connection(self, user_id: str) -> Optional[WebSocketConnection]:
        """
        Get connection for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            WebSocketConnection or None
        """
        conns = self._connections.get(user_id) or {}
        return next(iter(conns.values()), None)
    
    def get_all_connections(self) -> Dict[str, WebSocketConnection]:
        """
        Get all active connections.
        
        Returns:
            Dictionary mapping user IDs to connections
        """
        out: Dict[str, WebSocketConnection] = {}
        for user, conns in self._connections.items():
            for cid, c in conns.items():
                out[f"{user}#{cid}"] = c
        return out
    
    def is_connected(self, user_id: str) -> bool:
        """True if user has at least one open connection."""
        conns = self._connections.get(user_id) or {}
        return any(c.is_open() for c in conns.values())

    def get_all_clients(self) -> Set[ServerConnection]:
        """Get all raw WebSocket clients across all connections."""
        out: Set[ServerConnection] = set()
        for conns in self._connections.values():
            for c in conns.values():
                out.add(c.raw_websocket)
        return out


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
        websocket: ServerConnection,
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
