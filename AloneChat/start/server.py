"""
Server startup module for AloneChat application.
Provides the entry point for starting the chat server and web services.
"""

import asyncio
import uvicorn
import threading
from AloneChat.core.server import WebSocketManager
from AloneChat.web.routes import app


def server(port=8765, srv_only=False):
    """
    Start the chat server and web services on the specified port.

    Args:
        port (int): Port number to listen on (default: 8765)
        srv_only (bool): If True, serve only the web services only.
    """
    # Reset all online to offline
    from AloneChat.web.routes import load_user_credentials, save_user_credentials
    user_credentials = load_user_credentials()
    for username in user_credentials:
        user_credentials[username]['is_online'] = False
    save_user_credentials(user_credentials)
    print("All user credentials saved. All status reseted to 'leaved'.")

    # Create WebSocket manager
    ws_manager = WebSocketManager(port=port)

    # Start WebSocket server in a separate task
    async def start_websocket_server():
        await ws_manager.run()

    # Start HTTP server with uvicorn
    def start_http_server():
        uvicorn.run(app, host="0.0.0.0", port=port + 1)

    # Run both servers
    try:
        # Start HTTP server in a separate thread
        if not srv_only:
            http_thread = threading.Thread(target=start_http_server, daemon=True)
            http_thread.start()

        # Run WebSocket server in the main thread
        asyncio.run(start_websocket_server())
    except KeyboardInterrupt:
        print("Closed by user.")
