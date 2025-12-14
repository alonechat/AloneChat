"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

import asyncio

import aiohttp
import curses

import websockets
from websockets.exceptions import ConnectionClosed

from AloneChat.core.message.protocol import Message, MessageType

from .command import CommandSystem
from .client_base import Client

__all__ = [
    'CommandSystem',
    'Client', 'CursesClient'
]


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

                elif key == curses.KEY_BACKSPACE or key == curses.KEY_DC or key in [8, 127]:  # Backspace key
                    # The backspace key in windows is "8"...
                    # And the curses.KEY_BACKSPACE is "263"...
                    # This inconsistency...
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

            choice = self._get_input(3, 32)

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
        username = self._get_input(0, 10)

        self.stdscr.addstr(1, 0, "Password: ")
        self.stdscr.refresh()
        password = self._get_password(1, 10)

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
        username = self._get_input(0, 10)

        self.stdscr.addstr(1, 0, "Password: ")
        self.stdscr.refresh()
        password = self._get_password(1, 10)

        self.stdscr.addstr(2, 0, "Confirm password: ")
        self.stdscr.refresh()
        confirm_password = self._get_password(2, 18)

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
