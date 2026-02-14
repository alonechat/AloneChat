"""
Command-line interface module for AloneChat client.
Provides independent command parsing and selector logic.
"""

from .parser import CommandParser, Command, CommandType
from .selector import CLISelector, ConsoleBackend, CursesBackend, GUIBackend, UIBackend

__all__ = [
    'CommandParser', 'Command', 'CommandType', 'CLISelector',
    'ConsoleBackend', 'CursesBackend', 'GUIBackend', 'UIBackend'
]
