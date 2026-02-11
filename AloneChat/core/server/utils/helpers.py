"""
Utility functions and helpers for the server module.
"""

import logging
from typing import Optional

from AloneChat.core.message.protocol import Message, MessageType

logger = logging.getLogger(__name__)


class MessageBuilder:
    """
    Builder pattern for creating messages.
    
    Provides a fluent interface for constructing messages
    with various properties.
    """
    
    def __init__(self):
        """Initialize message builder."""
        self._type = MessageType.TEXT
        self._sender = "SERVER"
        self._content = ""
        self._target = None
        self._command = None
    
    def text(self, content: str) -> 'MessageBuilder':
        """Set message as text type."""
        self._type = MessageType.TEXT
        self._content = content
        return self
    
    def system(self, content: str) -> 'MessageBuilder':
        """Set message as system message."""
        self._type = MessageType.TEXT
        self._sender = "SERVER"
        self._content = content
        return self
    
    def join(self, username: str) -> 'MessageBuilder':
        """Set message as join notification."""
        self._type = MessageType.JOIN
        self._sender = username
        self._content = f"{username} joined the chat"
        return self
    
    def leave(self, username: str) -> 'MessageBuilder':
        """Set message as leave notification."""
        self._type = MessageType.LEAVE
        self._sender = username
        self._content = f"{username} left the chat"
        return self
    
    def heartbeat(self, content: str = "pong") -> 'MessageBuilder':
        """Set message as heartbeat."""
        self._type = MessageType.HEARTBEAT
        self._sender = "SERVER"
        self._content = content
        return self
    
    def error(self, content: str) -> 'MessageBuilder':
        """Set message as error."""
        self._type = MessageType.TEXT
        self._sender = "SERVER"
        self._content = f"Error: {content}"
        return self
    
    def from_user(self, username: str) -> 'MessageBuilder':
        """Set sender username."""
        self._sender = username
        return self
    
    def to_user(self, username: str) -> 'MessageBuilder':
        """Set target user."""
        self._target = username
        return self
    
    def with_command(self, command: str) -> 'MessageBuilder':
        """Set command field."""
        self._command = command
        return self
    
    def build(self) -> Message:
        """Build and return the message."""
        return Message(
            type=self._type,
            sender=self._sender,
            content=self._content,
            target=self._target,
            command=self._command
        )


def create_server_message(content: str) -> Message:
    """
    Create a server message.
    
    Args:
        content: Message content
        
    Returns:
        Message instance
    """
    return Message(MessageType.TEXT, "SERVER", content)


def create_error_message(content: str) -> Message:
    """
    Create an error message.
    
    Args:
        content: Error content
        
    Returns:
        Message instance
    """
    return Message(MessageType.TEXT, "SERVER", f"Error: {content}")


def create_join_message(username: str) -> Message:
    """
    Create a user join message.
    
    Args:
        username: Joining username
        
    Returns:
        Message instance
    """
    return Message(MessageType.JOIN, username, f"{username} joined the chat")


def create_leave_message(username: str) -> Message:
    """
    Create a user leave message.
    
    Args:
        username: Leaving username
        
    Returns:
        Message instance
    """
    return Message(MessageType.LEAVE, username, f"{username} left the chat")


class SafeSender:
    """
    Utility for safely sending messages with automatic error handling.
    """
    
    @staticmethod
    async def send(connection, message: Message) -> bool:
        """
        Safely send a message.
        
        Args:
            connection: Connection object with send method
            message: Message to send
            
        Returns:
            True if successful
        """
        try:
            await connection.send(message.serialize())
            return True
        except Exception as e:
            logger.warning("Failed to send message: %s", e)
            return False
    
    @staticmethod
    async def send_to_many(connections, message: Message) -> dict:
        """
        Send a message to multiple connections.
        
        Args:
            connections: Iterable of connection objects
            message: Message to send
            
        Returns:
            Dict mapping connection to success status
        """
        results = {}
        for conn in connections:
            try:
                await conn.send(message.serialize())
                results[conn] = True
            except Exception as e:
                logger.warning("Failed to send to connection: %s", e)
                results[conn] = False
        return results
