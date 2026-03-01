"""
AloneChat API module.

This module provides the HTTP/WebSocket interaction layer.
All business logic is delegated to the server layer.
"""

from AloneChat.api.app import app
from AloneChat.api import models
from AloneChat.api import middleware
from AloneChat.api import routes


__all__ = ['app', 'models', 'middleware', 'routes']
