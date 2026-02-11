"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

from .client_base import Client
from .curses_client import CursesClient
from .gui_client import SimpleGUIClient

# CLI clients
from .curses_cli_client import CursesCLIClient
from .gui_cli_client import GUICLIClient

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
    'GUICLIClient',
    'ui',
    'input',
    'auth',
    'utils',
    'cli',
]
