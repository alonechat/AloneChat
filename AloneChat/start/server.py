import asyncio
from AloneChat.core.server.manager import WebSocketManager

def server(port): 
    _server = WebSocketManager(port=port)
    try:
        asyncio.run(_server.run())
    except KeyboardInterrupt:
        print("Closed by user.")
    