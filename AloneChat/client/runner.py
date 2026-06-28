"""
Client runner module for AloneChat.
Provides simplified entry point for starting chat clients.

MIGRATED from core/client/runner.py.
"""

from AloneChat.client.gui_client import SimpleGUIClient

DEFAULT_HOST = "localhost"
DEFAULT_API_PORT = 8766

__all__ = ["run_client", "DEFAULT_HOST", "DEFAULT_API_PORT"]


def run_client(api_host=DEFAULT_HOST, api_port=DEFAULT_API_PORT, ui="gui"):
    """Start the AloneChat client.

    Args:
        api_host: API server hostname (default: localhost).
        api_port: API server port (default: 8766).
        ui: UI type — currently only "gui" is supported.
    """
    print("Welcome to AloneChat Client!")
    print(f"Connecting to API at {api_host}:{api_port} using {ui} interface...")

    try:
        if ui == "gui":
            client = SimpleGUIClient(api_host, api_port)
            client.run()
        else:
            print(f"Unknown UI type: {ui}. Available options: gui")
    except KeyboardInterrupt:
        print("\nConnection closed by user.")
    except Exception as e:
        print(f"Failed to connect: {e}")
