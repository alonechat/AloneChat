"""
AloneChat API module.

This module provides the HTTP/WebSocket interaction layer.
All business logic is delegated to the server layer.
"""

from .app import app

__all__ = ['app']
