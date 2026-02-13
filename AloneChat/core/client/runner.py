"""
Client runner module for AloneChat.
Provides simplified entry point for starting chat clients.
"""

from AloneChat.core.client import CursesClient, SimpleGUIClient
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT

__all__ = ['run_client']


def run_client(api_host=DEFAULT_HOST, api_port=DEFAULT_API_PORT, ui="gui"):
    """
    Start the chat client with specified API connection parameters.
    The client will connect to the API first to fetch server configuration.

    Args:
        api_host (str): API server hostname to connect to (default: localhost)
        api_port (int): API server port number (default: 8766)
        ui (str): User interface type ("gui" for GUI, "tui" for curses TUI)
    """
    print("Welcome to AloneChat Client!")
    print(f"Connecting to API at {api_host}:{api_port} using {ui} interface...")
    
    try:
        if ui == "gui":
            client = SimpleGUIClient(api_host, api_port)
            client.run()
        elif ui == "tui":
            client = CursesClient(api_host, api_port)
            client.run()
        else:
            print(f"Unknown UI type: {ui}. Available options: gui, tui")
    except KeyboardInterrupt:
        print("\nConnection closed by user.")
    except Exception as e:
        print(f"Failed to connect: {e}")
