"""
UI module for curses-based client.
Provides components for rendering and display management.
"""

from .renderer import CursesRenderer
from .message_buffer import MessageBuffer

__all__ = ['CursesRenderer', 'MessageBuffer']
