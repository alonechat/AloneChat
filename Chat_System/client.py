import asyncio
import websockets
from core.network.protocol import Message
from core.client.command import CommandSystem


async def chat_client():
    uri = "ws://localhost:8765"
    name = input("Enter username: ")

    async with websockets.connect(uri) as websocket:
        await websocket.send(Message(MessageType.JOIN, name, "").serialize())

        async def receive():
            while True:
                msg = Message.deserialize(await websocket.recv())
                print(f"\n[{msg.sender}] {msg.content}")

        async def send():
            while True:
                text = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
                msg = CommandSystem.process(text, name)
                await websocket.send(msg.serialize())

        await asyncio.gather(receive(), send())


asyncio.get_event_loop().run_until_complete(chat_client())