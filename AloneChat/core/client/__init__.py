"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

import asyncio

import aiohttp
import curses
import getpass

import websockets
from websockets.exceptions import ConnectionClosed

from AloneChat.core.message.protocol import Message, MessageType
from .command import CommandSystem

__all__ = [
    'CommandSystem',
    'Client', 'StandardCommandlineClient', 'CursesClient'
]


class Client:
    """
    Base client class providing core websocket client functionality.
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
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
                # HTTP web runs on port+1
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
                # HTTP web runs on port+1
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


# type: ignore
class CursesClient(Client):
    """
    Curses-based chat client implementation with message history navigation.
    Provides enhanced terminal interface for chat interactions.
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        super().__init__(host, port)
        self.stdscr = None
        self.input_buffer = ""
        self.messages = []
        self.username = ""
        self.scroll_offset = 0  # For message history navigation
        self.auto_scroll = True  # Auto-scroll to new messages by default

    def init_curses(self, stdscr):
        """Initialize curses settings."""
        self.stdscr = stdscr
        curses.cbreak()
        curses.noecho()
        stdscr.keypad(True)
        stdscr.nodelay(True)
        self.update_display()

    def update_display(self):
        """Refresh the display with current messages and input buffer."""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        # Calculate available space for messages
        display_height = height - 1  # Last line for input

        # If auto-scroll is enabled, show the latest messages
        if self.auto_scroll:
            self.scroll_offset = max(0, len(self.messages) - display_height)

        # Determine which messages to display
        start_idx = max(0, self.scroll_offset)
        end_idx = min(len(self.messages), start_idx + display_height)

        # Display messages
        for i, idx in enumerate(range(start_idx, end_idx)):
            if i < display_height:  # Ensure we don't write beyond screen
                self.stdscr.addstr(i, 0, self.messages[idx][:width - 1])

        # Display input buffer with cursor
        input_line = f"> {self.input_buffer}"
        self.stdscr.addstr(height - 1, 0, input_line[:width - 1])

        # Position cursor at the end of input
        if len(input_line) < width:
            self.stdscr.move(height - 1, len(input_line))
        else:
            self.stdscr.move(height - 1, width - 1)

        self.stdscr.refresh()

    async def handle_input(self, websocket):
        """Handle user input from curses interface."""
        while True:
            try:
                key = self.stdscr.getch()

                if key == curses.KEY_ENTER or key in [10, 13]:  # Enter key
                    if self.input_buffer:
                        msg = CommandSystem.process(self.input_buffer, self.username)
                        await websocket.send(msg.serialize())
                        self.input_buffer = ""
                        self.auto_scroll = True  # Auto-scroll after sending

                elif key == curses.KEY_BACKSPACE or key == 8:  # Backspace key
                    # The backspace key in windows is "8"...
                    # Remove the last character from input buffer
                    self.input_buffer = self.input_buffer[:-1] \
                        if self.input_buffer != "" \
                        else self.input_buffer

                # Message history navigation
                elif key == curses.KEY_UP:
                    # Scroll up through history
                    if self.scroll_offset > 0:
                        self.scroll_offset -= 1
                        self.auto_scroll = False

                elif key == curses.KEY_DOWN:
                    # Scroll down through history
                    if self.scroll_offset < len(self.messages) - (self.stdscr.getmaxyx()[0] - 1):
                        self.scroll_offset += 1
                    else:
                        # Reached bottom - enable auto-scroll
                        self.auto_scroll = True

                elif key == curses.KEY_PPAGE:  # Page Up
                    self.scroll_offset = max(0, self.scroll_offset - (self.stdscr.getmaxyx()[0] - 1))
                    self.auto_scroll = False

                elif key == curses.KEY_NPAGE:  # Page Down
                    height = self.stdscr.getmaxyx()[0]
                    self.scroll_offset = min(
                        len(self.messages) - (height - 1),
                        self.scroll_offset + (height - 1)
                    )
                    # Check if we reached the bottom
                    if self.scroll_offset >= len(self.messages) - (height - 1):
                        self.auto_scroll = True

                elif key == curses.KEY_HOME:  # Home key
                    self.scroll_offset = 0
                    self.auto_scroll = False

                elif key == curses.KEY_END:  # End key
                    self.auto_scroll = True

                elif 0 < key < 256 and chr(key).isprintable():
                    self.input_buffer += chr(key)

                self.update_display()
                await asyncio.sleep(0.01)

            except ConnectionClosed:
                break

            except Exception as e:
                self.messages.append(f"Input error: {e}")
                self.update_display()

    async def handle_messages(self, websocket):
        """Handle incoming messages from server."""
        try:
            while True:
                try:
                    msg_data = await websocket.recv()
                    msg = Message.deserialize(msg_data)
                    self.messages.append(f"[{msg.sender}] {msg.content}")
                    self.update_display()
                except ConnectionClosed:
                    self.messages.append("! Server connection closed")
                    self.update_display()
                    break
        except Exception as e:
            self.messages.append(f"Receive error: {e}")
            self.update_display()

    async def async_run(self, stdscr):
        """Asynchronous main method for curses client."""
        self.init_curses(stdscr)

        token = None

        # Login or register before connecting
        while not token:
            self.stdscr.clear()
            self.stdscr.addstr(0, 0, "Please select an option:")
            self.stdscr.addstr(1, 0, "1. Login")
            self.stdscr.addstr(2, 0, "2. Register")
            self.stdscr.addstr(3, 0, "Please enter your choice (1/2): ")
            self.stdscr.refresh()

            choice = self._get_input(3, 19)

            if choice == "1":
                # noinspection PyUnresolvedReferences
                token = await self._login()
            elif choice == "2":
                success = await self._register()
                if success:
                    self.stdscr.addstr(5, 0, "Registration successful, please login")
                    self.stdscr.refresh()
                    await asyncio.sleep(2)
            else:
                self.stdscr.addstr(5, 0, "Invalid option, please choose again")
                self.stdscr.refresh()
                await asyncio.sleep(1)

        # Connect with token
        uri = f"ws://{self.host}:{self.port}?token={token}"

        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    # Send `join` message
                    join_msg = Message(MessageType.JOIN, self.username, "").serialize()
                    await websocket.send(join_msg)

                    # Start tasks
                    await asyncio.gather(
                        self.handle_messages(websocket),
                        self.handle_input(websocket)
                    )

            except ConnectionRefusedError:
                self.messages.append("Server not available, retrying in 3 seconds...")
                self.update_display()
                await asyncio.sleep(3)
            except Exception as error:
                self.messages.append(f"Fatal error: {str(error)}")
                self.update_display()
                await asyncio.sleep(5)
                break

    def _get_input(self, y, x):
        """Get user input at specified position without echoing characters."""
        input_str = ""
        self.stdscr.move(y, x)
        self.stdscr.refresh()

        while True:
            key = self.stdscr.getch()
            if key == curses.KEY_ENTER or key in [10, 13]:  # Enter key
                break
            elif key == curses.KEY_BACKSPACE or key == 8:  # Backspace key
                if input_str:
                    input_str = input_str[:-1]
                    self.stdscr.move(y, x + len(input_str))
                    self.stdscr.delch()
            elif 0 < key < 256 and chr(key).isprintable():
                input_str += chr(key)
                self.stdscr.addch(y, x + len(input_str) - 1, key)
            self.stdscr.refresh()
        return input_str

    def _get_password(self, y, x):
        """Get password input at specified position with masking."""
        password = ""
        self.stdscr.move(y, x)
        self.stdscr.refresh()

        while True:
            key = self.stdscr.getch()
            if key == curses.KEY_ENTER or key in [10, 13]:  # Enter key
                break
            elif key == curses.KEY_BACKSPACE or key == 8:  # Backspace key
                if password:
                    password = password[:-1]
                    self.stdscr.move(y, x + len(password))
                    self.stdscr.delch()
            elif 0 < key < 256 and chr(key).isprintable():
                password += chr(key)
                self.stdscr.addch(y, x + len(password) - 1, '*')
            self.stdscr.refresh()
        return password

    async def _login(self):
        """Handle user login and return JWT token."""

        self.stdscr.clear()
        self.stdscr.addstr(0, 0, "Username: ")
        self.stdscr.refresh()
        username = self._get_input(0, 9)

        self.stdscr.addstr(1, 0, "Password: ")
        self.stdscr.refresh()
        password = self._get_password(1, 9)

        try:
            async with aiohttp.ClientSession() as session:
                # HTTP web runs on port+1
                # noinspection HttpUrlsUsage
                async with session.post(f"http://{self.host}:{self.port + 1}/api/login", json={
                    "username": username,
                    "password": password
                }) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success"):
                            self.stdscr.addstr(3, 0, "Login successful")
                            self.stdscr.refresh()
                            await asyncio.sleep(1)
                            self.username = username
                            return data.get("token")
                        else:
                            self.stdscr.addstr(3, 0, f"Login failed: {data.get('message')}")
                            self.stdscr.refresh()
                            await asyncio.sleep(2)
                            return None
                    else:
                        self.stdscr.addstr(3, 0, f"Login request failed, status code: {response.status}")
                        self.stdscr.refresh()
                        await asyncio.sleep(2)
                        return None
        except Exception as e:
            self.stdscr.addstr(3, 0, f"Error during login: {str(e)}")
            self.stdscr.refresh()
            await asyncio.sleep(2)
            return None

    async def _register(self):
        """Handle user registration."""
        import aiohttp

        self.stdscr.clear()
        self.stdscr.addstr(0, 0, "Username: ")
        self.stdscr.refresh()
        username = self._get_input(0, 9)

        self.stdscr.addstr(1, 0, "Password: ")
        self.stdscr.refresh()
        password = self._get_password(1, 9)

        self.stdscr.addstr(2, 0, "Confirm password: ")
        self.stdscr.refresh()
        confirm_password = self._get_password(2, 19)

        if password != confirm_password:
            self.stdscr.addstr(4, 0, "Passwords do not match")
            self.stdscr.refresh()
            await asyncio.sleep(2)
            return False

        try:
            async with aiohttp.ClientSession() as session:
                # HTTP web runs on port+1
                # noinspection HttpUrlsUsage
                async with session.post(f"http://{self.host}:{self.port + 1}/api/register", json={
                    "username": username,
                    "password": password
                }) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success"):
                            self.stdscr.addstr(4, 0, "Registration successful")
                            self.stdscr.refresh()
                            await asyncio.sleep(1)
                            return True
                        else:
                            self.stdscr.addstr(4, 0, f"Registration failed: {data.get('message')}")
                            self.stdscr.refresh()
                            await asyncio.sleep(2)
                            return False
                    else:
                        self.stdscr.addstr(4, 0, f"Registration request failed, status code: {response.status}")
                        self.stdscr.refresh()
                        await asyncio.sleep(2)
                        return False
        except Exception as e:
            self.stdscr.addstr(4, 0, f"Error during registration: {str(e)}")
            self.stdscr.refresh()
            await asyncio.sleep(2)
            return False

    def run(self):
        try:
            """Start the curses-based client."""
            curses.wrapper(lambda stdscr: asyncio.run(self.async_run(stdscr)))
        except NameError:
            print(
                "Are you using AloneChat in Windows?"
                "You can install curses using `pip install windows-curses`."
                "Please check requirements.txt for more details."
                "Or you can add '--ui text' to client command."
            )
