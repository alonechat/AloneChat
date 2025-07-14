"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

import asyncio

import websockets
from websockets.exceptions import ConnectionClosed

from AloneChat.core.client.command import CommandSystem
from AloneChat.core.message.protocol import Message, MessageType
from .command import CommandSystem

__all__ = [
    'CommandSystem', 
    'Client', 'StandardCommandlineClient'
]


class Client:
    """
    Base client class providing core websocket client functionality.
    """
    def __init__(self, host:str="localhost", port:int=8765):
        """
        Initialize client with connection parameters.

        Args:
            host (str): Server hostname to connect to
            port (int): Server port number
        """
        self.host = host
        self.port = port

    def run(self):
        """
        Abstract method to start the client.
        Must be implemented by subclasses.
        """
        return NotImplementedError
    
class StandardCommandlineClient(Client):
    """
    Standard command-line-based chat client implementation.
    Provides "text-based" interface for chat interactions.
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        super().__init__(host, port)

    @staticmethod
    def while_try_connection_closed(function, **params):
        """
        Utility method to repeatedly try a function until connection is closed.

        Args:
            function: Function to execute
            **params: Parameters to pass to the function
        """
        while True:
            try:
                function(**params)
            except ConnectionClosed:
                pass

    @staticmethod
    async def send(name, websocket):
        """
        Asynchronously send messages to the websocket server.

        Args:
            name (str): Username of the client
            websocket: Websocket connection object
        """
        try:
            while True:
                # Use asyncio to get input asynchronously
                # This allows the program to handle other events while waiting for input
                # Note: input() is blocking, but we run it in an executor to avoid blocking the event loop
                try:
                    text = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
                    msg = CommandSystem.process(text, name)
                    await websocket.send(msg.serialize())
                except ConnectionClosed:
                    break
        except Exception as e:
            print(f"\nSend error: {e}")

    @staticmethod
    async def receive(websocket):
        """
        Asynchronously receive messages from the websocket server.

        Args:
            websocket: Websocket connection object
        """
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

    async def run(self):
        """
        Start the standard command-line client.
        Establishes connection to the server and handles sending/receiving messages.
        """
        host = self.host
        port = self.port

        # TODO: Change to t-string in Python 3.14 to keep safe
        uri = f"ws://{host}:{port}"

        name = input("Enter username: ")
        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    print("Connected to server!")
                    await websocket.send(Message(MessageType.JOIN, name, "").serialize())
                    await asyncio.gather(self.receive(websocket), self.send(name, websocket))

            except ConnectionRefusedError:
                print("Server not available, retrying in 3 seconds...")
                await asyncio.sleep(3)
            except Exception as error:
                print(f"Fatal error: {str(error)}")
                break
