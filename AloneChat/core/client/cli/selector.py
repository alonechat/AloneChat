"""
CLI Selector for AloneChat client.
Provides a command-line interface that works with any UI backend.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable

from .parser import Command, CommandType, CommandExecutor
from ..utils import DEFAULT_HOST, DEFAULT_API_PORT


class UIBackend(ABC):
    """Abstract base class for UI backends."""

    @abstractmethod
    def display_output(self, message: str) -> None:
        """Display output to the user."""
        pass

    @abstractmethod
    def get_input(self, prompt: str = ">> ") -> str:
        """Get input from the user."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear the display."""
        pass

    @abstractmethod
    def run(self) -> None:
        """Run the UI main loop."""
        pass


class CLISelector:
    """
    Command-line selector that works with any UI backend.
    Provides the command-line interface logic independent of the display method.
    """

    def __init__(
        self,
        ui_backend: Optional[UIBackend] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_API_PORT,
        ui_type: str = "tui"
    ):
        """
        Initialize the CLI selector.
        
        Args:
            ui_backend: UI backend to use for I/O (None for default console)
            host: Default server host
            port: Default server port
            ui_type: Default UI type
        """
        self.executor = CommandExecutor()
        self.executor.host = host
        self.executor.port = port
        self.executor.ui_type = ui_type
        
        self.ui_backend = ui_backend or ConsoleBackend()
        self.running = False
        
        # Register additional handlers
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register command handlers."""
        self.executor.parser.register_handler(CommandType.EXIT, self._handle_exit)
        self.executor.parser.register_handler(CommandType.QUIT, self._handle_exit)
        self.executor.parser.register_handler(CommandType.CONNECT, self._handle_connect)
    
    def _handle_exit(self, cmd: Command) -> str:
        """Handle exit/quit command."""
        self.running = False
        return "Goodbye!"
    
    def _handle_connect(self, cmd: Command) -> str:
        """Handle connect command."""
        return f"Connecting to {self.executor.host}:{self.executor.port}..."
    
    def show_welcome(self) -> None:
        """Display welcome message."""
        welcome = f"""
╔══════════════════════════════════════╗
║     Welcome to AloneChat Client      ║
╚══════════════════════════════════════╝

Current settings:
  Server: {self.executor.host}:{self.executor.port}
  UI Type: {self.executor.ui_type}

Type 'help' for available commands or 'connect' to start.
"""
        self.ui_backend.display_output(welcome)
    
    def process_command(self, input_line: str) -> None:
        """
        Process a single command.
        
        Args:
            input_line: Raw input from user
        """
        command, result = self.executor.process(input_line)
        
        if result:
            self.ui_backend.display_output(str(result))
        elif command.type == CommandType.EMPTY:
            pass  # Ignore empty input
        elif command.type == CommandType.UNKNOWN:
            self.ui_backend.display_output(f"Unknown command: {command.raw}")
    
    def run(self) -> None:
        """Run the CLI selector main loop."""
        self.running = True
        self.show_welcome()
        
        while self.running:
            try:
                input_line = self.ui_backend.get_input("> ")
                self.process_command(input_line)
            except KeyboardInterrupt:
                self.ui_backend.display_output("\nUse 'exit' or 'quit' to exit.")
            except EOFError:
                break


class ConsoleBackend(UIBackend):
    """Default console-based UI backend."""
    
    def display_output(self, message: str) -> None:
        """Display output to console."""
        print(message)
    
    def get_input(self, prompt: str = ">> ") -> str:
        """Get input from console."""
        return input(prompt)
    
    def clear(self) -> None:
        """Clear console (the best effort)."""
        print("\033[2J\033[H", end="")
    
    def run(self) -> None:
        """Console backend doesn't need a run loop."""
        pass


class CursesBackend(UIBackend):
    """Curses-based UI backend for command-line interface."""
    
    def __init__(self, stdscr=None):
        """
        Initialize curses backend.
        
        Args:
            stdscr: Curses window object (set later if None)
        """
        self.stdscr = stdscr
        self.output_buffer: list[str] = []
        self.input_buffer = ""
        self.max_output_lines = 100
        
    def set_window(self, stdscr) -> None:
        """Set the curses window object."""
        self.stdscr = stdscr
        self._init_curses()
    
    def _init_curses(self) -> None:
        """Initialize curses settings."""
        import curses
        curses.cbreak()
        curses.noecho()
        self.stdscr.keypad(True)
        self.stdscr.nodelay(False)  # Blocking for CLI mode
    
    def display_output(self, message: str) -> None:
        """Display output in curses window."""
        lines = message.split('\n')
        self.output_buffer.extend(lines)
        
        # Trim buffer if too large
        if len(self.output_buffer) > self.max_output_lines:
            self.output_buffer = self.output_buffer[-self.max_output_lines:]
        
        self._refresh_display()
    
    def _refresh_display(self) -> None:
        """Refresh the curses display."""
        import curses
        
        if not self.stdscr:
            return
        
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        
        # Display output buffer
        display_lines = self.output_buffer[-(height-2):]  # Reserve 2 lines for input
        for i, line in enumerate(display_lines):
            if i < height - 2:
                try:
                    self.stdscr.addstr(i, 0, line[:width-1])
                except curses.error:
                    pass
        
        # Display input prompt
        try:
            self.stdscr.addstr(height-1, 0, "> " + self.input_buffer)
            self.stdscr.move(height-1, 2 + len(self.input_buffer))
        except curses.error:
            pass
        
        self.stdscr.refresh()
    
    def get_input(self, prompt: str = "> ") -> str:
        """Get input using curses."""
        import curses
        
        if not self.stdscr:
            raise RuntimeError("Curses window not initialized")
        
        self.input_buffer = ""
        self._refresh_display()
        
        while True:
            key = self.stdscr.getch()
            
            if key in [curses.KEY_ENTER, 10, 13]:
                result = self.input_buffer
                self.input_buffer = ""
                return result
            
            elif key in [curses.KEY_BACKSPACE, 8, 127]:
                if self.input_buffer:
                    self.input_buffer = self.input_buffer[:-1]
            
            elif 0 < key < 256 and chr(key).isprintable():
                self.input_buffer += chr(key)
            
            self._refresh_display()
    
    def clear(self) -> None:
        """Clear the display."""
        self.output_buffer.clear()
        if self.stdscr:
            self.stdscr.clear()
            self.stdscr.refresh()
    
    def run(self) -> None:
        """Run with curses wrapper."""
        import curses
        curses.wrapper(self._curses_main)
    
    def _curses_main(self, stdscr) -> None:
        """Main curses function."""
        self.set_window(stdscr)
        # The actual run loop is handled by CLISelector


class GUIBackend(UIBackend):
    """GUI-based UI backend for command-line interface."""
    
    def __init__(self):
        """Initialize GUI backend."""
        self.output_buffer: list[str] = []
        self.input_callback: Optional[Callable[[str], None]] = None
        self.output_callback: Optional[Callable[[str], None]] = None
        
    def set_callbacks(
        self,
        input_callback: Callable[[str], None],
        output_callback: Callable[[str], None]
    ) -> None:
        """
        Set callbacks for GUI integration.
        
        Args:
            input_callback: Called when user submits input
            output_callback: Called when output should be displayed
        """
        self.input_callback = input_callback
        self.output_callback = output_callback
    
    def display_output(self, message: str) -> None:
        """Display output via callback."""
        lines = message.split('\n')
        self.output_buffer.extend(lines)
        
        if self.output_callback:
            self.output_callback(message)
    
    def get_input(self, prompt: str = ">> ") -> str:
        """
        Get input from GUI.
        Note: This is non-blocking in GUI mode, returns empty string.
        Actual input comes through input_callback.
        """
        # In GUI mode, input is handled asynchronously
        return ""
    
    def submit_input(self, text: str) -> None:
        """Submit input from GUI."""
        if self.input_callback:
            self.input_callback(text)
    
    def clear(self) -> None:
        """Clear output buffer."""
        self.output_buffer.clear()
    
    def run(self) -> None:
        """GUI backend doesn't need a run loop."""
        pass
