"""
Client module for AloneChat application.
Provides base client functionality and standard command-line client implementation.
"""

import asyncio
import curses
from typing import Optional

from AloneChat.api.client import AloneChatAPIClient
from .auth import AuthFlow
from .client_base import Client
from .input import InputHandler, InputResult
from .ui import CursesRenderer, MessageBuffer
from .utils import DEFAULT_HOST, DEFAULT_API_PORT, REFRESH_RATE_HZ

__all__ = ['Client', 'CursesClient']


class CursesClient(Client):
    """
    Curses-based chat client implementation with message history navigation.
    Provides enhanced terminal interface for chat interactions.

    Architecture:
        - UI Layer: CursesRenderer handles all display operations
        - Input Layer: InputHandler processes keyboard input
        - Auth Layer: AuthFlow manages login/registration
        - Data Layer: MessageBuffer stores and manages messages
        - API Layer: AloneChatAPIClient communicates with server
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_API_PORT,
        max_history: int = 1000
    ):
        """
        Initialize the curses client.

        Args:
            host: Server hostname to connect to
            port: Server port number
            max_history: Maximum number of messages to keep in history
        """
        super().__init__(host, port)

        # Core components (initialized in async_run)
        self._renderer: Optional[CursesRenderer] = None
        self._message_buffer: Optional[MessageBuffer] = None
        self._input_handler: Optional[InputHandler] = None
        self._auth_flow: Optional[AuthFlow] = None

        # API client
        self._api_client = AloneChatAPIClient(host, port)

        # State
        self._username: str = ""
        self._token: Optional[str] = None
        self._running: bool = False

    @property
    def username(self) -> str:
        """Get the current username."""
        return self._username

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self._token is not None

    async def _send_message(self, content: str) -> None:
        """
        Send a message to the server.

        Args:
            content: Message content to send
        """
        if not self.is_authenticated:
            self._message_buffer.add_error_message("Not authenticated")
            return

        try:
            response = await self._api_client.send_message(content)

            if not response.get("success"):
                error_msg = response.get("message", "Unknown error")
                self._message_buffer.add_error_message(f"Failed to send: {error_msg}")

        except Exception as e:
            self._message_buffer.add_error_message(f"Send error: {e}")

    def _init_components(self, stdscr) -> None:
        """
        Initialize all client components.

        Args:
            stdscr: Curses window object
        """
        # Initialize UI components
        self._renderer = CursesRenderer(stdscr)
        self._message_buffer = MessageBuffer(max_history=1000)

        # Initialize input handler with submit callback
        self._input_handler = InputHandler(
            stdscr=stdscr,
            message_buffer=self._message_buffer,
            on_submit=self._send_message
        )

        # Initialize auth flow
        self._auth_flow = AuthFlow(self._renderer, self._api_client)

        self._running = True

    async def _authenticate(self) -> bool:
        """
        Run the authentication flow.

        Returns:
            True if authentication successful, False otherwise
        """
        session = await self._auth_flow.show_auth_menu()

        if session is None:
            return False

        # Update client state with session
        self._username = session.username
        self._token = session.token
        self._api_client.token = self._token
        self._api_client.username = self._username

        return True

    async def _handle_messages(self) -> None:
        """
        Background task to receive messages from the server.
        Runs continuously until client stops.
        """
        while self._running:
            try:
                msg_data = await self._api_client.receive_message()

                if not isinstance(msg_data, dict):
                    await asyncio.sleep(0.1)
                    continue

                if not msg_data.get("success"):
                    error = msg_data.get("error")
                    if error and error != "Timeout waiting for message":
                        self._message_buffer.add_error_message(f"Receive error: {error}")
                    await asyncio.sleep(0.1)
                    continue

                sender = msg_data.get("sender")
                content = msg_data.get("content")

                if sender and content:
                    self._message_buffer.add_message(sender, content)

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    async def _handle_input(self) -> None:
        """
        Main input handling loop.
        Processes keyboard input until client stops.
        """
        while self._running and self._input_handler.is_running:
            try:
                result, _ = await self._input_handler.read_input()

                if result == InputResult.SUBMIT:
                    # Clear input buffer after successful submit
                    self._input_handler.clear_buffer()
                    # Enable auto-scroll on new message
                    self._message_buffer.auto_scroll = True

                elif result == InputResult.QUIT:
                    self._running = False
                    break

                # Small delay to prevent CPU spinning
                await asyncio.sleep(1.0 / REFRESH_RATE_HZ)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._message_buffer.add_error_message(f"Input error: {e}")

    async def _render_loop(self) -> None:
        """
        Render loop that continuously updates the display.
        Runs at a fixed rate to ensure smooth UI updates.
        """
        while self._running:
            try:
                if self._input_handler:
                    self._renderer.update_display(
                        self._message_buffer,
                        self._input_handler.input_buffer
                    )
                await asyncio.sleep(1.0 / REFRESH_RATE_HZ)

            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _run_chat_session(self) -> None:
        """
        Run the main chat session after authentication.
        Manages message receiving, input handling, and rendering.
        """
        self._message_buffer.add_system_message("Connected to server using API")

        try:
            # Run all tasks concurrently
            await asyncio.gather(
                self._handle_messages(),
                self._handle_input(),
                self._render_loop()
            )

        except ConnectionRefusedError:
            self._message_buffer.add_error_message(
                "Server not available, retrying..."
            )
            await asyncio.sleep(3)

        except Exception as e:
            self._message_buffer.add_error_message(f"Fatal error: {e}")
            await asyncio.sleep(5)

    async def async_run(self, stdscr) -> None:
        """
        Asynchronous main entry point for the curses client.

        Args:
            stdscr: Curses window object passed by curses.wrapper
        """
        # Initialize all components
        self._init_components(stdscr)

        # Authenticate user
        if not await self._authenticate():
            return

        # Main connection loop with reconnection support
        while self._running:
            try:
                await self._run_chat_session()

            except Exception as e:
                self._message_buffer.add_error_message(f"Connection error: {e}")
                await asyncio.sleep(3)

    async def _logout(self) -> None:
        """Perform graceful logout."""
        if self._auth_flow and self._auth_flow.is_authenticated:
            try:
                await self._auth_flow.logout()
                self._message_buffer.add_system_message("Logged out successfully")
            except Exception:
                pass

    def run(self) -> None:
        """
        Start the curses-based client.
        This is the main entry point that wraps the async execution.
        """
        try:
            curses.wrapper(lambda stdscr: asyncio.run(self.async_run(stdscr)))
        except NameError:
            print(
                "Are you using AloneChat on Windows?\n"
                "You can install curses using `pip install windows-curses`.\n"
                "Please check requirements.txt for more details.\n"
                "Or you can add '--ui text' to the client command."
            )
        except KeyboardInterrupt:
            pass
        finally:
            # Ensure cleanup
            if self._running:
                self._running = False
