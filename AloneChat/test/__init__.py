"""
Test module for AloneChat client functionality.
Provides a simple test case for WebSocket message exchange.
"""

import asyncio

import websockets

from ..core.message.protocol import Message, MessageType


async def send_message(context, host="localhost", port=8765):
    """
    Test websocket connection and message sending functionality.
    Connects to local test server and sends a test message.
    """
    uri = f"ws://{host}:{port}"
    async with websockets.connect(uri) as websocket:
        # Create and send a test message
        msg = Message(
            type=MessageType.TEXT,
            sender="test_user",
            content=context,
        )
        await websocket.send(msg.serialize())

        # Wait for and print server response
        response = await websocket.recv()
        print(f"Received: {response}")


def main(context, host="localhost", port=8765):
    # Run the test using asyncio event loop
    asyncio.get_event_loop().run_until_complete(
        send_message(context, host, port)
    )
