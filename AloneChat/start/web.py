from AloneChat.web import server


def web(ws_host=None, ws_port=None, port=None):
    """Laundh web server."""
    server(ws_host=ws_host, ws_port=ws_port, port=port)
