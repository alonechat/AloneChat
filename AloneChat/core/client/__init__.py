"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

from AloneChat.core.message.protocol import Message, MessageType
from .client import Client, CursesClient, StandardCommandlineClient
from .command import CommandSystem

__all__ = [
    "Client", "CursesClient", "StandardCommandlineClient",
    "CommandSystem", "Message", "MessageType",
]