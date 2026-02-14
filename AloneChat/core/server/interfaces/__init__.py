"""
Abstract base classes and interfaces for the server module.

This module defines the contracts that all implementations must follow,
ensuring a clean separation of concerns and making the codebase more
maintainable and testable.

Enhanced with plugin integration hooks for pre- /post-processing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from AloneChat.core.message.protocol import MessageType


class HookPhase(Enum):
    """Phases where hooks can be executed."""
    PRE_CONNECT = auto()
    POST_CONNECT = auto()
    PRE_AUTHENTICATE = auto()
    POST_AUTHENTICATE = auto()
    PRE_MESSAGE = auto()
    POST_MESSAGE = auto()
    PRE_BROADCAST = auto()
    POST_BROADCAST = auto()
    PRE_DISCONNECT = auto()
    POST_DISCONNECT = auto()
    PRE_COMMAND = auto()
    POST_COMMAND = auto()


@dataclass
class HookContext:
    """Context passed to hook functions."""
    phase: HookPhase
    user_id: Optional[str] = None
    message: Optional[Any] = None
    connection: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        self.metadata[key] = value


HookFunction = Callable[[HookContext], Optional[HookContext]]


@dataclass
class AuthResult:
    """Result of an authentication attempt."""
    success: bool
    username: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class ProcessingResult:
    """Result of message processing."""
    success: bool
    content: str
    modified: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    message_type: Optional['MessageType'] = None
    response_target: Optional[str] = None


@runtime_checkable
class HookRegistry(Protocol):
    """Protocol for hook registration and execution."""
    
    @abstractmethod
    def register_hook(
        self,
        phase: HookPhase,
        hook: HookFunction,
        priority: int = 100
    ) -> None:
        """Register a hook for a specific phase."""
        ...
    
    @abstractmethod
    async def execute_hooks(self, phase: HookPhase, context: HookContext) -> HookContext:
        """Execute all hooks for a phase."""
        ...


@runtime_checkable
class Authenticator(Protocol):
    """Protocol for authentication handlers."""
    
    @abstractmethod
    async def authenticate(self, token: str) -> AuthResult:
        """
        Authenticate a user using the provided token.
        
        Args:
            token: Authentication token
            
        Returns:
            AuthResult containing authentication status and username
        """
        ...
    
    @abstractmethod
    def extract_token(self, transport_context: object) -> Optional[str]:
        """
        Extract authentication token from transport context.
        
        Args:
            transport_context: Transport-specific context object
            
        Returns:
            Extracted token or None if not found
        """
        ...


@runtime_checkable
class SessionStore(Protocol):
    """Protocol for session storage implementations."""
    
    @abstractmethod
    def add(self, user_id: str) -> None:
        """Add a new session."""
        ...
    
    @abstractmethod
    def remove(self, user_id: str) -> None:
        """Remove a session."""
        ...
    
    @abstractmethod
    def touch(self, user_id: str) -> None:
        """Update last activity timestamp."""
        ...
    
    @abstractmethod
    def is_active(self, user_id: str) -> bool:
        """Check if session is active."""
        ...
    
    @abstractmethod
    def get_inactive(self, timeout: int) -> list[str]:
        """Get list of inactive user IDs."""
        ...


@runtime_checkable
class TransportConnection(Protocol):
    """Protocol for transport layer connections."""
    
    @abstractmethod
    async def send(self, message: str) -> bool:
        """Send a message through the connection."""
        ...
    
    @abstractmethod
    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the connection."""
        ...
    
    @abstractmethod
    def is_open(self) -> bool:
        """Check if connection is open."""
        ...


@runtime_checkable
class MessageProcessor(Protocol):
    """Protocol for message processing with plugin support."""
    
    @abstractmethod
    async def process(
        self,
        content: str,
        sender: str,
        target: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ProcessingResult:
        """
        Process a message through the processing pipeline.
        
        Args:
            content: Message content
            sender: Sender username
            target: Optional target user
            context: Additional context
            
        Returns:
            ProcessingResult with processed content
        """
        ...


@runtime_checkable
class MessageHandler(Protocol):
    """Protocol for message handlers."""
    
    @abstractmethod
    async def handle(
        self,
        message: object,
        sender: str,
        transport: TransportConnection
    ) -> None:
        """
        Handle an incoming message.
        
        Args:
            message: The message object
            sender: Username of the sender
            transport: Transport connection for responses
        """
        ...
    
    @abstractmethod
    def can_handle(self, message: object) -> bool:
        """Check if this handler can process the given message."""
        ...


@runtime_checkable
class BroadcastService(Protocol):
    """Protocol for message broadcasting services."""
    
    @abstractmethod
    async def broadcast(
        self,
        message: str,
        exclude: Optional[list[str]] = None
    ) -> None:
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Message to broadcast
            exclude: List of usernames to exclude from broadcast
        """
        ...
    
    @abstractmethod
    async def send_to_user(self, username: str, message: str) -> bool:
        """
        Send a message to a specific user.
        
        Args:
            username: Target username
            message: Message to send
            
        Returns:
            True if message was sent successfully
        """
        ...


class ConnectionRegistry(ABC):
    """Abstract base class for connection registries."""
    
    @abstractmethod
    def register(self, user_id: str, connection: TransportConnection) -> None:
        """Register a new connection."""
        pass
    
    @abstractmethod
    def unregister(self, user_id: str) -> None:
        """Unregister a connection."""
        pass
    
    @abstractmethod
    def get_connection(self, user_id: str) -> Optional[TransportConnection]:
        """Get connection for a user."""
        pass
    
    @abstractmethod
    def get_all_connections(self) -> dict[str, TransportConnection]:
        """Get all active connections."""
        pass
    
    @abstractmethod
    def is_connected(self, user_id: str) -> bool:
        """Check if user is connected."""
        pass


class ServerLifecycle(ABC):
    """Abstract base class for server lifecycle management."""
    
    @abstractmethod
    async def start(self, host: str, port: int) -> None:
        """Start the server."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the server."""
        pass
    
    @abstractmethod
    def is_running(self) -> bool:
        """Check if server is running."""
        pass


class PluginAwareComponent(ABC):
    """Base class for components that support plugin hooks."""
    
    def __init__(self):
        self._hooks: Dict[HookPhase, List[tuple[int, HookFunction]]] = {}
    
    def register_hook(
        self,
        phase: HookPhase,
        hook: HookFunction,
        priority: int = 100
    ) -> None:
        """
        Register a hook for a specific phase.
        
        Args:
            phase: Phase to hook into
            hook: Hook function
            priority: Lower numbers execute first
        """
        if phase not in self._hooks:
            self._hooks[phase] = []
        self._hooks[phase].append((priority, hook))
        self._hooks[phase].sort(key=lambda x: x[0])
    
    def unregister_hook(self, phase: HookPhase, hook: HookFunction) -> bool:
        """
        Unregister a hook.
        
        Args:
            phase: Phase the hook is registered for
            hook: Hook function to remove
            
        Returns:
            True if hook was found and removed
        """
        if phase in self._hooks:
            for i, (_, h) in enumerate(self._hooks[phase]):
                if h == hook:
                    self._hooks[phase].pop(i)
                    return True
        return False
    
    async def _execute_hooks(self, phase: HookPhase, context: HookContext) -> HookContext:
        """
        Execute all hooks for a phase.
        
        Args:
            phase: Phase to execute hooks for
            context: Hook context
            
        Returns:
            Modified context
        """
        if phase not in self._hooks:
            return context
        
        result_context = context
        for _, hook in self._hooks[phase]:
            try:
                modified = hook(result_context)
                if modified is not None:
                    result_context = modified
            except Exception:
                pass
        
        return result_context


__all__ = [
    'HookPhase',
    'HookContext',
    'HookFunction',
    'HookRegistry',
    'AuthResult',
    'ProcessingResult',
    'Authenticator',
    'SessionStore',
    'TransportConnection',
    'MessageProcessor',
    'MessageHandler',
    'BroadcastService',
    'ConnectionRegistry',
    'ServerLifecycle',
    'PluginAwareComponent',
]
