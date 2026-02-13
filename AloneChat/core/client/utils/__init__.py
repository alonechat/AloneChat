"""
Utility functions and shared components for the curses client.
"""

from .constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_API_PORT,
    MAX_RECONNECT_ATTEMPTS,
    REFRESH_RATE_HZ,
)
from .exceptions import ClientError, AuthenticationError, WsConnectionError

__all__ = [
    'ClientError',
    'AuthenticationError',
    'WsConnectionError',
    'DEFAULT_HOST',
    'DEFAULT_PORT',
    'DEFAULT_API_PORT',
    'MAX_RECONNECT_ATTEMPTS',
    'REFRESH_RATE_HZ',
]
