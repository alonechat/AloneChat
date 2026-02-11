"""
Curses-based command-line client for AloneChat.
Provides a command-line interface using curses for display.
"""

import curses
import asyncio
from typing import Optional

from .client_base import Client
from .cli import CLISelector, CursesBackend
from .utils import DEFAULT_HOST, DEFAULT_API_PORT

__all__ = ['CursesCLIClient']


class CursesCLIClient(Client):
    """
    Curses-based command-line client.
    Provides a CLI interface with curses display backend.
    """
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_API_PORT,
        ui_type: str = "tui"
    ):
        """
        Initialize the curses CLI client.

        Args:
            host: Server hostname
            port: Server port
            ui_type: UI type preference
        """
        super().__init__(host, port)
        self.ui_type = ui_type
        self.selector: Optional[CLISelector] = None
        self.backend: Optional[CursesBackend] = None
        
    def _init_components(self, stdscr) -> None:
        """Initialize client components with curses window."""
        # Create curses backend
        self.backend = CursesBackend(stdscr)
        
        # Create selector with backend
        self.selector = CLISelector(
            ui_backend=self.backend,
            host=self.host,
            port=self.port,
            ui_type=self.ui_type
        )
        
        # Register connect handler to actually connect
        self.selector.executor.parser.register_handler(
            self.selector.executor.parser.COMMAND_ALIASES.get('connect'),
            self._handle_connect
        )
    
    def _handle_connect(self, cmd) -> str:
        """Handle connect command - launch the appropriate UI."""
        if self.selector.executor.ui_type == "tui":
            return "Launching TUI mode... (not implemented in CLI mode)"
        elif self.selector.executor.ui_type == "gui":
            return "Launching GUI mode... (not implemented in CLI mode)"
        else:
            return f"Connecting to {self.selector.executor.host}:{self.selector.executor.port}..."
    
    def _curses_main(self, stdscr) -> None:
        """Main curses function."""
        self._init_components(stdscr)
        self.selector.run()
    
    def run(self) -> None:
        """Run the curses CLI client."""
        try:
            curses.wrapper(self._curses_main)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"Error: {e}")


class AsyncCursesCLIClient(CursesCLIClient):
    """
    Async version of curses CLI client with chat capabilities.
    Extends the CLI with actual chat functionality.
    """
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_API_PORT,
        ui_type: str = "tui"
    ):
        """Initialize async curses CLI client."""
        super().__init__(host, port, ui_type)
        self.chat_client = None
        self.running = False
        
    def _init_components(self, stdscr) -> None:
        """Initialize components with chat support."""
        super()._init_components(stdscr)
        
        # Override connect handler to start chat
        from AloneChat.api.client import AloneChatAPIClient
        self.api_client = AloneChatAPIClient(self.host, self.port)
        
        # Register chat-specific handlers
        self.selector.executor.parser.register_handler(
            self.selector.executor.parser.COMMAND_ALIASES.get('send'),
            self._handle_send
        )
        self.selector.executor.parser.register_handler(
            self.selector.executor.parser.COMMAND_ALIASES.get('join'),
            self._handle_join
        )
        self.selector.executor.parser.register_handler(
            self.selector.executor.parser.COMMAND_ALIASES.get('leave'),
            self._handle_leave
        )
    
    def _handle_send(self, cmd) -> str:
        """Handle send command."""
        message = cmd.kwargs.get('message', '')
        if message:
            # In actual implementation, this would send via API
            return f"[You] {message}"
        return "Error: No message to send"
    
    def _handle_join(self, cmd) -> str:
        """Handle join command."""
        channel = cmd.kwargs.get('channel', '')
        if channel:
            return f"Joined channel: {channel}"
        return "Error: No channel specified"
    
    def _handle_leave(self, cmd) -> str:
        """Handle leave command."""
        return "Left current channel"
    
    async def _message_receiver(self) -> None:
        """Background task to receive messages."""
        while self.running:
            try:
                # In actual implementation, this would receive from API
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
    
    async def async_run(self, stdscr) -> None:
        """Async main entry point."""
        self._init_components(stdscr)
        self.running = True
        
        # Show welcome
        self.selector.show_welcome()
        
        # Run message receiver in background
        receiver_task = asyncio.create_task(self._message_receiver())
        
        try:
            # Run CLI loop
            while self.running and self.selector.running:
                try:
                    input_line = self.selector.ui_backend.get_input("> ")
                    self.selector.process_command(input_line)
                except KeyboardInterrupt:
                    self.selector.ui_backend.display_output("\nUse 'exit' or 'quit' to exit.")
                except EOFError:
                    break
        finally:
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass
    
    def run(self) -> None:
        """Run the async curses CLI client."""
        try:
            curses.wrapper(lambda stdscr: asyncio.run(self.async_run(stdscr)))
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"Error: {e}")
