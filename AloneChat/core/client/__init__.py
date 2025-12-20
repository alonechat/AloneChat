"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

from .client_base import Client
from .command import CommandSystem
from .command_line_client import StandardCommandlineClient
from .curses_client import CursesClient
# from .neo_curses_client import CursesClient

__all__ = [
    'CommandSystem',
    'Client', 'StandardCommandlineClient', 'CursesClient'
]
