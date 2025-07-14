"""
Server startup module for AloneChat application.
Provides the entry point for starting the chat server.
"""

import asyncio

from AloneChat.core.server import WebSocketManager


def server(port):
    """
    Start the chat server on the specified port.

    Args:
        port (int): Port number to listen on
    """
    _server = WebSocketManager(port=port)
    try:
        asyncio.run(_server.run())
    except KeyboardInterrupt:
        print("Closed by user.")
