"""
MIGRATED from core/client/client_base.py.

Abstract base client class for AloneChat clients.
Provides the foundation for GUI, CLI, and API clients.

MessageType is imported from AloneChat.message.protocol (migrated from
the former AloneChat.core.message.protocol).
"""

from abc import ABC, abstractmethod
from typing import Optional

from AloneChat.message.protocol import MessageType


class Client(ABC):
    """
    Abstract base client class.

    Provides core client functionality and interface for subclasses.
    Subclasses must implement :meth:`run`.
    """

    def __init__(self, host: str = "localhost", port: int = 8766):
        """
        Initialize client with connection parameters.

        Args:
            host: Server hostname
            port: Server port number
        """
        self.host = host
        self.port = port
        self._running = False

    @abstractmethod
    def run(self) -> None:
        """
        Start the client.

        Must be implemented by subclasses.
        """
        pass

    def is_running(self) -> bool:
        """Check if client is running."""
        return self._running

    def stop(self) -> None:
        """Stop the client."""
        self._running = False

    @property
    def server_url(self) -> str:
        """Get the server URL."""
        return f"http://{self.host}:{self.port}"


__all__ = ["Client"]
