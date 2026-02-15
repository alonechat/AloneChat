"""
Custom exceptions for the curses client.
"""


class ClientError(Exception):
    """Base exception for client errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class AuthenticationError(ClientError):
    """Exception raised for authentication-related errors."""
    pass


class WsConnectionError(ClientError):
    """Exception raised for connection-related errors."""
    pass


class MessageError(ClientError):
    """Exception raised for message-related errors."""
    pass


class RenderError(ClientError):
    """Exception raised for rendering-related errors."""
    pass
