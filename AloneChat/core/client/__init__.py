"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

from . import auth
from . import cli
from . import input
# Import submodules for easy access
from . import ui
from . import utils
from .client_base import Client
from .curses_client import CursesClient
from .gui_client import SimpleGUIClient
from .qt_client import QtClient
from .runner import run_client

__all__ = [
    'Client',
    'CursesClient',
    'SimpleGUIClient',
    'QtClient',
    'run_client',
    'ui',
    'input',
    'auth',
    'utils',
    'cli',
]
