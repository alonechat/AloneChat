"""
Run the AloneChat API server.
"""

import uvicorn

DEFAULT_API_PORT = 8766
from .app import app


def run(api_port: int = DEFAULT_API_PORT):
    """Run the FastAPI application with Uvicorn."""
    try:
        uvicorn.run(app, port=api_port)
    except Exception as e:
        print(f"Error running API server: {e}")
