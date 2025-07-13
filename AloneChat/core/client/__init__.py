import asyncio
import websockets
from websockets.exceptions import ConnectionClosed
from AloneChat.core.message.protocol import Message, MessageType
from AloneChat.core.client.command import CommandSystem

from .command import CommandSystem

__all__ = [
    'CommandSystem', 
    'Client', 'StandardCommandlineClient'
]


class Client:
    def __init__(self, host:str="localhost", port:int=8765):
        self.host = host
        self.port = port

    def run(self):
        return NotImplementedError
    
class StandardCommandlineClient(Client):
    def __init__(self, host = "localhost", port = 8765):
        super().__init__(host, port)

    async def run(self):
        host = self.host
        port = self.port

        uri = f"ws://{host}:{port}" # TODO: Change to t-string in Python 3.14

        name = input("Enter username: ")

        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    print("Connected to server!")
                    await websocket.send(Message(MessageType.JOIN, name, "").serialize())

                    async def receive():
                        try:
                            while True:
                                try:
                                    msg = Message.deserialize(await websocket.recv())
                                    print(f"\n[{msg.sender}] {msg.content}")
                                except ConnectionClosed:
                                    print("\n! Server connection closed")
                                    break
                        except Exception as e:
                            print(f"\nReceive error: {e}")

                    async def send():
                        try:
                            while True:
                                try:
                                    text = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
                                    msg = CommandSystem.process(text, name)
                                    await websocket.send(msg.serialize())
                                except ConnectionClosed:
                                    break
                        except Exception as e:
                            print(f"\nSend error: {e}")

                    await asyncio.gather(receive(), send())

            except ConnectionRefusedError:
                print("Server not available, retrying in 3 seconds...")
                await asyncio.sleep(3)
            except Exception as e:
                print(f"Fatal error: {str(e)}")
                break
