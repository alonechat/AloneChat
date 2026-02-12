"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

from .client_base import Client
from .curses_client import CursesClient
from .gui_client import SimpleGUIClient

# Import submodules for easy access
from . import ui
from . import input
from . import auth
from . import utils
from . import cli

__all__ = [
    'Client',
    'CursesClient',
    'SimpleGUIClient',
    'CursesCLIClient',
    'ui',
    'input',
    'auth',
    'utils',
    'cli',
]
