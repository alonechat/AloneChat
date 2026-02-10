"""
Abstract base classes and interfaces for the server module.

This module defines the contracts that all implementations must follow,
ensuring a clean separation of concerns and making the codebase more
maintainable and testable.
"""

from abc import ABC, abstractmethod
from typing import Optional, Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass
class AuthResult:
    """Result of an authentication attempt."""
    success: bool
    username: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None


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
    async def send(self, message: str) -> None:
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
class MessageHandler(Protocol):
    """Protocol for message handlers."""
    
    @abstractmethod
    async def handle(self, message: object, sender: str, transport: TransportConnection) -> None:
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
    async def broadcast(self, message: str, exclude: Optional[list[str]] = None) -> None:
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
