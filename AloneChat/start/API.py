import AloneChat.API as _API


# noinspection PyPep8Naming
def API(port=8766):
    """
    Start the API server for AloneChat.

    Args:
        port (int): Port number for the API server (default: 8766).
    """
    _API.run(api_port=port)
