"""
Client startup module for AloneChat application.
Provides the entry point for starting the chat client.
"""

import asyncio

from AloneChat.core.client import CursesClient
from AloneChat.core.client import StandardCommandlineClient

__all__ = ['client']


def client(host="localhost", port=8765, ui="tui", auto_connect=False):
    """
    Start the chat client with specified connection parameters.
    Args:
        host (str): Server hostname to connect to (default: localhost)
        port (int): Server port number (default: 8765)
        ui (str): User interface type ("text" for command-line, "tui" for Textual UI)
        auto_connect (bool): Whether to automatically connect to the server (default: False)
    """
    print("Welcome AloneChat Client!")
    print(f"Current setting: server={host}:{port}, UI={ui}")
    if auto_connect:
        _connect_to_server(host, port, ui)
    else:
        print(
            "Type 'connect' to connect to the server, "
            "'set host <hostname>' to set the server address, \n"
            "'set port <port>' to set the server port, "
            "and 'exit' to exit."
        )
        while True:
            command = input(">> ").strip().lower()
            command_parts = command.split()

            match command_parts:
                case ["exit"]:
                    print("Bye!")
                    break

                case ["connect"]:
                    _connect_to_server(host, port, ui)

                case ["set", "host", hostname]:
                    host = hostname
                    print(f"Server address setted to: {host}")

                case ["set", "port", port_str] if port_str.isdigit():
                    port = int(port_str)
                    print(f"Port setted to: {port}")

                case ["set", "host"]:
                    print("Usage: set host <hostname>")

                case ["set", "port"]:
                    print("Usage: set port <port>")

                case ["set", "port", _]:
                    print("Port must be a number")

                case ["help"]:
                    print("Commands:")
                    print("  connect - Connect to server")
                    print("  set host <hostname> - Set server address")
                    print("  set port <port> - Set server port")
                    print("  exit - Exit the client")

                case ["set", _]:
                    print("Use case: set host <hostname> or set port <port>")

                case _:
                    print(
                        f"Unknown command: {command}, try type command 'help' "
                        "to check commands")


def _connect_to_server(host, port, ui):
    """Helper function to connect to the server"""
    try:
        if ui == "text":
            _client = StandardCommandlineClient(host, port)
            asyncio.run(_client.run())
        elif ui == "tui":
            _client = CursesClient(host, port)
            _client.run()
        else:
            print(
                f"Sorry. But we don't have a {ui} UI yet."
                "We apologize, but we just have a text-based (ugly) UI and a curses-based TUI."
                "No need? You are a geek! Why not join us in developing a new UI?"
                "GitHub: https://github.com/alonechat/AloneChat , welcome you!"
            )
    except KeyboardInterrupt:
        print("Connect reseted.")
    except Exception as e:
        print(f"Failed to connect: {e}")
