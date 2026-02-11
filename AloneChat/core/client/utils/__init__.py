"""
Utility functions and shared components for the curses client.
"""

from .exceptions import ClientError, AuthenticationError, ConnectionError
from .constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_API_PORT,
    MAX_RECONNECT_ATTEMPTS,
    REFRESH_RATE_HZ,
)

__all__ = [
    'ClientError',
    'AuthenticationError',
    'ConnectionError',
    'DEFAULT_HOST',
    'DEFAULT_PORT',
    'DEFAULT_API_PORT',
    'MAX_RECONNECT_ATTEMPTS',
    'REFRESH_RATE_HZ',
]
