"""
Client startup module for AloneChat application.
Provides the entry point for starting the chat client.
"""

import asyncio

from AloneChat.core.client import CursesClient
from AloneChat.core.client import StandardCommandlineClient

__all__ = ['client']


def client(host="localhost", port=8765, ui="tui"):
    """
    Start the chat client with specified connection parameters.

    Args:
        host (str): Server hostname to connect to (default: localhost)
        port (int): Server port number (default: 8765)
        ui   (str): User interface type ("text" for command-line, "tui" for Textual UI)
    """
    try:
        if ui == "text":
            _client = StandardCommandlineClient(host, port)
            asyncio.run(_client.run())
        elif ui == "tui":
            _client = CursesClient(host, port)
            _client.run()
        else:
            print(
                "Sorry. But we don't have such a beautiful UI yet."
                "We apologize, but we just have a text-based (ugly) UI and a curses-based TUI."
                "No need? You are a geek! Why not join us in developing a new UI?"
                "GitHub: https://github.com/alonechat/AloneChat , welcome you!"
            )

    except KeyboardInterrupt:
        print("Now quit. Bye!")