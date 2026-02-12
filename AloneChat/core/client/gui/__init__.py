"""
Modular GUI client for AloneChat with sv_ttk (Sun Valley) Windows 11 theme.

This package provides a clean, modular architecture for the GUI client:
- models: Data models and themes
- components: Reusable UI components using sv_ttk
- services: Business logic services
- controllers: View controllers
- client: Main GUI client class

Features:
- sv_ttk Sun Valley theme (Windows 11 style)
- Standard ttk widgets with modern styling
- Clean separation of concerns
"""

from .client import GUIClient
from .models import Theme, WinUI3Styles, ModernStyles, MessageItem, Conversation, ReplyContext
from .components import (
    BoundedFrame,
    ScrollableFrame, 
    WinUI3ScrollableFrame,
    ModernButton,
    WinUI3Button,
    ModernEntry,
    WinUI3Entry,
    MessageCard,
    WinUI3MessageCard,
)

__all__ = [
    'GUIClient',
    'Theme',
    'WinUI3Styles',
    'ModernStyles',
    'MessageItem',
    'Conversation',
    'ReplyContext',
    'BoundedFrame',
    'ScrollableFrame',
    'WinUI3ScrollableFrame',
    'ModernButton',
    'WinUI3Button',
    'ModernEntry',
    'WinUI3Entry',
    'MessageCard',
    'WinUI3MessageCard',
]
