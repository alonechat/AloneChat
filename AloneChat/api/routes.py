import uvicorn

from .routes_api import *


def run(api_port=SERVER_PORT + 1):
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
