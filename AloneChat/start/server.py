from AloneChat.core.network.websocket import WebSocketManager

def server(port): 
    server = WebSocketManager(port=port)
    try:
        server.start()
    except KeyboardInterrupt:
        print("Closed by user.")
    