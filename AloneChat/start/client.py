"""
Client startup module for AloneChat.
Simple wrapper interface for starting the chat client.
"""

from AloneChat.core.client import run_client
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT

__all__ = ['client']


def client(api_host=DEFAULT_HOST, api_port=DEFAULT_API_PORT, ui="gui"):
    """
    Start the chat client with specified API connection parameters.
    The client will connect to the API first to fetch server configuration.

    Args:
        api_host (str): API server hostname to connect to (default: localhost)
        api_port (int): API server port number (default: 8766)
        ui (str): User interface type ("gui" for GUI, "tui" for curses TUI)
    """
    run_client(api_host=api_host, api_port=api_port, ui=ui)
