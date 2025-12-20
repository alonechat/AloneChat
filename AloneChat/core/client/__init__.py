"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

from .client_base import Client
from .curses_client import CursesClient

__all__ = [
    'Client', 'CursesClient'
]
