import AloneChat.api as _api
import AloneChat.config as config

# noinspection PyPep8Naming
def api(port=config.config.DEFAULT_API_PORT):
    """
    Start the static server for AloneChat.

    Args:
        port (int): Port number for the static server (default: 8766).
    """
    _api.run(api_port=port)
