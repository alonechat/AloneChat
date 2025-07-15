"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

import asyncio
import curses

import websockets
from websockets.exceptions import ConnectionClosed

from AloneChat.core.client.command import CommandSystem
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

        # Position cursor at end of input
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
                        if self.input_buffer != [] \
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

        # Get username
        self.stdscr.addstr(0, 0, "Enter username: ")
        self.stdscr.refresh()
        curses.echo()
        self.username = self.stdscr.getstr().decode('utf-8')
        curses.noecho()

        uri = f"ws://{self.host}:{self.port}"

        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    # Send join message
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

    def run(self):
        """Start the curses-based client."""
        curses.wrapper(lambda stdscr: asyncio.run(self.async_run(stdscr)))
