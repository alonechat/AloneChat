import asyncio
import getpass

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

from AloneChat.core.message.protocol import Message, MessageType
from .client_base import Client
from .command import CommandSystem


class StandardCommandlineClient(Client):
    """
    Standard command-line-based chat client implementation.
    Provides "text-based" interface for chat interactions.
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        super().__init__(host, port)

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

                    # Handle different types of messages
                    if msg.type == MessageType.JOIN:
                        print(f"\n[System message] {msg.sender} joined the chat room")
                    elif msg.type == MessageType.LEAVE:
                        print(f"\n[System message] {msg.sender} left the chat room")
                    else:
                        # Regular message
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
        Includes login and registration functionality.
        """
        host = self.host
        port = self.port
        token = None

        # Login or register before connecting
        while not token:
            print("\nPlease select options:")
            print("1. Login")
            print("2. Register")
            choice = input("Please enter your choice (1/2): ").strip()

            if choice == "1":
                # noinspection PyUnresolvedReferences
                token = await self._login(host, port)
            elif choice == "2":
                success = await self._register(host, port)
                if success:
                    print("Registration successful, please login")
            else:
                print("Invalid option, please choose again")

        # Connect with token
        uri = f"ws://{host}:{port}?token={token}"

        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    print("Connected to server!")
                    await asyncio.gather(self.receive(websocket), self.send("", websocket))

            except ConnectionRefusedError:
                print("Server not available, retrying in 3 seconds...")
                await asyncio.sleep(3)
            except Exception as error:
                print(f"Fatal error: {str(error)}")
                break

    @staticmethod
    async def _login(host, port):
        """
        Handle user login and return JWT token.
        """

        username = input("Username: ").strip()
        password = getpass.getpass("Password: ").strip()

        try:
            async with aiohttp.ClientSession() as session:
                # HTTP api runs on port+1
                # noinspection HttpUrlsUsage
                async with session.post(f"http://{host}:{port + 1}/api/login", json={
                    "username": username,
                    "password": password
                }) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success"):
                            print("Login successfully!")
                            return data.get("token")
                        else:
                            print(f"Login failed: {data.get('message')}")
                            return None
                    else:
                        print(f"Request failed, status code: {response.status}")
                        return None
        except Exception as e:
            print(f"Failed during login stage: {str(e)}")
            return None

    @staticmethod
    async def _register(host, port):
        """
        Handle user registration.
        """

        username = input("Username: ").strip()
        password = getpass.getpass("Password: ").strip()
        confirm_password = getpass.getpass("Confirm password: ").strip()

        if password != confirm_password:
            print("Incorrect confirm password.")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                # HTTP api runs on port+1
                # noinspection HttpUrlsUsage
                async with session.post(f"http://{host}:{port + 1}/api/register", json={
                    "username": username,
                    "password": password
                }) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success"):
                            print("Register successfully!")
                            return True
                        else:
                            print(f"Register failed: {data.get('message')}")
                            return False
                    else:
                        print(f"Request failed, status code: {response.status}")
                        return False
        except Exception as e:
            print(f"Failed during register stage: {str(e)}")
            return False