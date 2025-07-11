import asyncio
import websockets
import time
from core.network.protocol import Message, MessageType

async def send_message():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        msg = Message(
            type=MessageType.TEXT,
            sender="test_user",
            content="Hello world!",
            timestamp=time.time()
        )
        await websocket.send(msg.serialize())
        response = await websocket.recv()
        print(f"Received: {response}")

asyncio.get_event_loop().run_until_complete(send_message())