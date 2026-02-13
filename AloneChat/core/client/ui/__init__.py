"""
UI module for curses-based client.
Provides components for rendering and display management.
"""

from .message_buffer import MessageBuffer
from .renderer import CursesRenderer

__all__ = ['CursesRenderer', 'MessageBuffer']
