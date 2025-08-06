"""
Message protocol module for AloneChat application.
Defines message types and message structure used in client-server communication.
"""

import json
from dataclasses import dataclass
from enum import Enum


class MessageType(Enum):
    """
    Enumeration of supported message types in the chat system.
    """
    TEXT = 1  # Regular text message
    JOIN = 2  # User join notification
    LEAVE = 3  # User leave notification
    HELP = 4  # Help command message
    COMMAND = 5  # System command message
    ENCRYPTED = 6  # Encrypted message type
    HEARTBEAT = 7  # Heartbeat message

@dataclass
class Message:
    """
    Message class representing chat messages with type, sender, content and optional target.

    Attributes:
        type (MessageType): Type of the message
        sender (str): Username of message sender
        content (str): Message content
        target (str, optional): Target user for specific message types
    """
    type: MessageType
    sender: str
    content: str
    target: str = None
    command: str = None

    def serialize(self) -> str:
        """
        Serialize a message object to JSON string.

        Returns:
            str: JSON representation of the message
        """
        return json.dumps({
            "type": self.type.value,
            "sender": self.sender,
            "content": self.content,
            "target": self.target,
            "command": self.command
        })

    @classmethod
    def deserialize(cls, data: str) -> 'Message':
        """
        Create a Message object from JSON string.

        Args:
            data (str): JSON string to deserialize

        Returns:
            Message: Deserialized message object
        """
        obj = json.loads(data)
        return cls(
            type=MessageType(obj["type"]),
            sender=obj["sender"],
            content=obj["content"],
            target=obj.get("target"),
            command=obj.get("command")
        )