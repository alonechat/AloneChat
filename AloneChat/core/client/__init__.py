"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

from .client_base import Client
from .curses_client import CursesClient

# Import submodules for easy access
from . import ui
from . import input
from . import auth
from . import utils

__all__ = [
    'Client',
    'CursesClient',
    'ui',
    'input',
    'auth',
    'utils',
]
