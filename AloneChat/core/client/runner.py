"""Client runner module for AloneChat.

This file keeps imports lazy so server startup does not require GUI libraries.
"""

from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT

__all__ = ['run_client']


def run_client(api_host=DEFAULT_HOST, api_port=DEFAULT_API_PORT, ui="gui"):
    """Start the chat client with specified API connection parameters.

    Args:
        api_host: API server hostname (default: localhost)
        api_port: API server port (default: 8766)
        ui: UI type: 'gui' (Qt GUI), 'qt' (Qt GUI), 'tk' (legacy Tk GUI), 'tui' (terminal UI)
    """
    ui = (ui or "gui").lower()
    if ui == "tui":
        # Keep compatibility: tui = terminal UI (curses). If curses is unavailable,
        # users should choose 'qt' or install windows-curses.
        pass

    print("Welcome to AloneChat Client!")
    print(f"Connecting to API at {api_host}:{api_port} using {ui} interface...")

    try:
        if ui in ("gui","qt"):
            from AloneChat.core.client.qt_gui_client import QtGUIClient
            client = QtGUIClient(api_host, api_port)
            client.run()
        elif ui in ("tk",):
            from AloneChat.core.client.gui_client import SimpleGUIClient
            client = SimpleGUIClient(api_host, api_port)
            client.run()
        elif ui in ("tui",):
            from AloneChat.core.client.curses_client import CursesClient
            client = CursesClient(api_host, api_port)
            client.run()
        else:
            print(f"Unknown UI type: {ui}. Available options: gui, qt, tui")
    except KeyboardInterrupt:
        print("\nClient stopped by user.")
