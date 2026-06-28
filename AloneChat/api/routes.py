"""
Run the AloneChat API server.
"""

import uvicorn

from AloneChat.api.app import app
from AloneChat.config import Config


def run(api_port: int = Config.DEFAULT_API_PORT):
    """Run the FastAPI application with Uvicorn."""
    try:
        uvicorn.run(app, port=api_port)
    except Exception as e:
        print(f"Error running API server: {e}")
