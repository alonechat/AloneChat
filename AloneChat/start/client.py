"""
Client startup module for AloneChat application.
Provides the entry point for starting the chat client with multiple UI options.
"""

from AloneChat.core.client import CursesClient, SimpleGUIClient
from AloneChat.core.client.cli import CLISelector, ConsoleBackend
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT

__all__ = ['client', 'cli_client']


def client(host=DEFAULT_HOST, port=DEFAULT_API_PORT, ui="tui", auto_connect=False):
    """
    Start the chat client with specified connection parameters.

    Args:
        host (str): Server hostname to connect to (default: localhost)
        port (int): Server API port number (default: 8766)
        ui (str): User interface type ("text" for command-line, "tui" for Textual UI, "gui" for GUI)
        auto_connect (bool): Whether to automatically connect to the server (default: False)
    """
    print("Welcome AloneChat Client!")
    print(f"Current setting: server={host}:{port}, UI={ui}")
    
    if auto_connect:
        _connect_to_server(host, port, ui)
    else:
        # Use the new CLI selector for command-line interface
        _run_cli_selector(host, port, ui)


def _run_cli_selector(host, port, ui):
    """Run the CLI selector for interactive command-line interface."""
    # Create selector with console backend
    selector = CLISelector(
        ui_backend=ConsoleBackend(),
        host=host,
        port=port,
        ui_type=ui
    )
    
    # Register connect handler to launch appropriate UI
    from AloneChat.core.client.cli import CommandType
    
    def handle_connect(cmd):
        """Handle connect command by launching the selected UI."""
        ui_type = selector.executor.ui_type
        _connect_to_server(selector.executor.host, selector.executor.port, ui_type)
        return f"Launched {ui_type} UI"
    
    selector.executor.parser.register_handler(CommandType.CONNECT, handle_connect)
    
    # Run the selector
    selector.run()


def cli_client(host=DEFAULT_HOST, port=DEFAULT_API_PORT):
    """
    Start the console-based CLI client.

    Args:
        host (str): Server hostname
        port (int): Server API port
    """
    selector = CLISelector(
        ui_backend=ConsoleBackend(),
        host=host,
        port=port,
        ui_type="text"
    )
    selector.run()


def _connect_to_server(host, port, ui):
    """Helper function to connect to the server with the specified UI."""
    try:
        if ui == "tui":
            _client = CursesClient(host, port)
            _client.run()
        elif ui == "gui":
            _client = SimpleGUIClient(host, port)
            _client.run()
        elif ui == "text":
            # Use the new CLI selector for text mode
            selector = CLISelector(
                ui_backend=ConsoleBackend(),
                host=host,
                port=port,
                ui_type="text"
            )
            selector.run()
        else:
            print(
                f"Sorry. But we don't have a {ui} UI yet.\n"
                "We apologize, but we have the following options:\n"
                "  - tui: Curses-based TUI (full chat interface)\n"
                "  - gui: Modern GUI (full chat interface)\n"
                "\n"
                "No need? You are a geek! Why not join us in developing a new UI?\n"
                "GitHub: https://github.com/alonechat/AloneChat , welcome you!"
            )
    except KeyboardInterrupt:
        print("\nConnection reset.")
    except Exception as e:
        print(f"Failed to connect: {e}")


# Backward compatibility - keep the old function signature
def old_client(host="localhost", port=8765, ui="tui", auto_connect=False):
    """
    Original client function for backward compatibility.
    Uses the old command parsing logic.
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
                    print(f"Server address set to: {host}")

                case ["set", "port", port_str] if port_str.isdigit():
                    port = int(port_str)
                    print(f"Port set to: {port}")

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
                    print("Use case: set host <hostname> or set port <port)")

                case _:
                    print(
                        f"Unknown command: {command}, try type command 'help' "
                        "to check commands")


if __name__ == "__main__":
    # Default entry point
    import sys
    
    # Parse command line arguments
    args = sys.argv[1:]
    host = "localhost"
    port = 8765
    ui = "tui"
    
    i = 0
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == "--ui" and i + 1 < len(args):
            ui = args[i + 1]
            i += 2
        elif args[i] in ["--cli", "--text"]:
            ui = "text"
            i += 1
        elif args[i] == "--curses-cli":
            ui = "curses-cli"
            i += 1
        elif args[i] == "--gui-cli":
            ui = "gui-cli"
            i += 1
        else:
            i += 1
    
    client(host=host, port=port, ui=ui)
