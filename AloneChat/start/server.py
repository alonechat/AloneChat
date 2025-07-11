from AloneChat.core.network.websocket import WebSocketManager

def server(port): 
    server = WebSocketManager(port=port)
    server.start()