import AloneChat.web as _web


# noinspection PyPep8Naming
def web(port=8767):
    """
    Start the static server for AloneChat.

    Args:
        port (int): Port number for the static server (default: 8766).
    """
    _web.run(api_port=port)
