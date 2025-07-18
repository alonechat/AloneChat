import sys
from typing import List

# import asyncio
import uvicorn
import websockets
from fastapi import FastAPI, HTTPException

from AloneChat import __version__ as __main_version__
from AloneChat.core.client.command import CommandSystem
from ..core.message.protocol import Message

SERVER_ADDR = "localhost"
SERVER_PORT = 8765

try:
    SERVER = f"ws://{SERVER_ADDR}:{SERVER_PORT}"
except Exception as e:
    print(f"Error connecting to server at {SERVER_ADDR}:{SERVER_PORT}: {e}")
    print("Ensure the server is running and accessible.")
    sys.exit(1)

app = FastAPI(
    title="AloneChat API",
    version=__main_version__,
    description="API for AloneChat, a simple chat application.",
    contact={
        "name": "AloneChat Team"
    }
)


@app.post("/send")
async def send_message(sender: str, message: str, target: str | None = None):
    """
    Send a message to the connected WebSocket.

    Args:
        sender : The sender of the message.
        message (str): The message to send.
        target (str, optional): Target user for the message, if needed
    """
    # noinspection PyShadowingNames
    try:
        msg = CommandSystem.process(message, sender, target)
        async with websockets.connect(SERVER) as websocket:
            await websocket.send(msg.serialize())
    except Exception as e:
        print(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/recv")
async def recv_messages():
    """
    List all messages in the chat.

    Args:

    Returns:
        List[Message]: List of all messages.
    """
    # noinspection PyShadowingNames
    try:
        async with websockets.connect(SERVER) as websocket:
            msg = await websocket.recv()
        return msg
    except Exception as e:
        print(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


def run(api_port=SERVER_PORT + 1):
    """
    Run the FastAPI application with Uvicorn server.

    Args:
        api_port (int): Port for the API.
    """
    # noinspection PyShadowingNames
    try:
        uvicorn.run(app, port=api_port)
    except Exception as e:
        print(f"Error running API server: {e}")
