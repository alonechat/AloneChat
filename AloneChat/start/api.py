import AloneChat.api as _api


# noinspection PyPep8Naming
def api(port=8766):
    """
    Start the static server for AloneChat.

    Args:
        port (int): Port number for the static server (default: 8766).
    """
    _api.run(api_port=port)
