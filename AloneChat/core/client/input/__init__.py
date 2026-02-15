"""
Input handling module for curses client.
Provides keyboard input processing and command handling.
"""

from .handler import InputHandler, InputResult
from .key_mappings import KeyCode, get_action_for_key, InputAction

__all__ = ['InputHandler', 'InputResult', 'KeyCode', 'get_action_for_key', 'InputAction']
