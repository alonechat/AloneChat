"""
Client startup module for AloneChat application.
Provides the entry point for starting the chat client.
"""

import asyncio

from AloneChat.core.client import StandardCommandlineClient

__all__ = ['client']

def client(host="localhost", port=8765):
    """
    Start the chat client with specified connection parameters.

    Args:
        host (str): Server hostname to connect to (default: localhost)
        port (int): Server port number (default: 8765)
    """
    _client = StandardCommandlineClient(host, port)
    try:
        asyncio.run(_client.run())
    except KeyboardInterrupt:
        print("Now quit. Bye!")