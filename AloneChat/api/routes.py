import uvicorn

from AloneChat.core.client.utils import DEFAULT_API_PORT
from .routes_api import *


def run(api_port=DEFAULT_API_PORT):
    """
    Run the FastAPI application with Uvicorn server.

    Args:
        api_port (int): Port for the api.
    """
    # noinspection PyShadowingNames
    try:
        uvicorn.run(app, port=api_port)
    except Exception as e:
        print(f"Error running api server: {e}")
