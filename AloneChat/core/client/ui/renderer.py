"""
Curses UI renderer for terminal-based chat interface.
Handles all screen drawing and display operations.
"""

import curses
from typing import Optional, List, Tuple

from .message_buffer import MessageBuffer


class CursesRenderer:
    """
    Handles all curses rendering operations.
    Manages screen layout, colors, and display updates.
    """

    def __init__(self, stdscr):
        """
        Initialize renderer with curses window.

        Args:
            stdscr: Main curses window object
        """
        self._stdscr = stdscr
        self._height: int = 0
        self._width: int = 0
        self._init_curses()

    def _init_curses(self) -> None:
        """Initialize curses settings and configuration."""
        curses.cbreak()
        curses.noecho()
        self._stdscr.keypad(True)
        self._stdscr.nodelay(True)

        # Initialize colors if supported
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            self._init_color_pairs()

        self._update_dimensions()

    def _init_color_pairs(self) -> None:
        """Initialize color pairs for different message types."""
        # Color pair definitions
        curses.init_pair(1, curses.COLOR_GREEN, -1)   # System messages
        curses.init_pair(2, curses.COLOR_RED, -1)     # Error messages
        curses.init_pair(3, curses.COLOR_CYAN, -1)    # User messages
        curses.init_pair(4, curses.COLOR_YELLOW, -1)  # Highlights

    def _update_dimensions(self) -> None:
        """Update stored screen dimensions."""
        self._height, self._width = self._stdscr.getmaxyx()

    @property
    def height(self) -> int:
        """Get screen height."""
        self._update_dimensions()
        return self._height

    @property
    def width(self) -> int:
        """Get screen width."""
        self._update_dimensions()
        return self._width

    @property
    def display_height(self) -> int:
        """Get height available for message display (excluding input line)."""
        return self.height - 1

    def clear(self) -> None:
        """Clear the screen."""
        self._stdscr.clear()

    def refresh(self) -> None:
        """Refresh the screen."""
        self._stdscr.refresh()

    def draw_message_area(self, messages: List[str]) -> None:
        """
        Draw the message display area.

        Args:
            messages: List of message strings to display
        """
        display_height = self.display_height

        for i, message in enumerate(messages):
            if i >= display_height:
                break

            # Truncate message if too long
            display_msg = message[:self._width - 1]

            # Apply color based on message type
            color_pair = self._get_message_color(message)

            try:
                if color_pair:
                    self._stdscr.addstr(i, 0, display_msg, curses.color_pair(color_pair))
                else:
                    self._stdscr.addstr(i, 0, display_msg)
            except curses.error:
                # Ignore errors for edge cases
                pass

    def _get_message_color(self, message: str) -> Optional[int]:
        """
        Determine color pair for a message.

        Args:
            message: Message string

        Returns:
            Color pair number or None for default
        """
        if message.startswith("[System]"):
            return 1
        elif message.startswith("[! Error]"):
            return 2
        elif message.startswith("["):
            return 3
        return None

    def draw_input_line(self, input_buffer: str, prompt: str = "> ") -> None:
        """
        Draw the input line at the bottom of the screen.

        Args:
            input_buffer: Current input text
            prompt: Input prompt string
        """
        input_line = f"{prompt}{input_buffer}"
        display_input = input_line[:self._width - 1]

        try:
            self._stdscr.addstr(self._height - 1, 0, display_input)

            # Position cursor at end of input
            cursor_pos = min(len(input_line), self._width - 1)
            self._stdscr.move(self._height - 1, cursor_pos)
        except curses.error:
            pass

    def draw_prompt(self, lines: List[str]) -> None:
        """
        Draw a prompt screen (for login/register menus).

        Args:
            lines: List of lines to display
        """
        self.clear()

        for i, line in enumerate(lines):
            if i >= self._height - 1:
                break
            try:
                self._stdscr.addstr(i, 0, line[:self._width - 1])
            except curses.error:
                pass

        self.refresh()

    def draw_input_field(self, y: int, x: int, label: str, value: str = "", mask: bool = False) -> None:
        """
        Draw an input field with optional masking.

        Args:
            y: Row position
            x: Column position for label
            label: Field label
            value: Current value
            mask: Whether to mask the value (for passwords)
        """
        display_value = "*" * len(value) if mask else value
        line = f"{label}{display_value}"

        try:
            self._stdscr.addstr(y, 0, line[:self._width - 1])
            self._stdscr.move(y, x + len(display_value))
        except curses.error:
            pass

    def update_display(self, message_buffer: MessageBuffer, input_buffer: str) -> None:
        """
        Update the entire display.

        Args:
            message_buffer: Buffer containing messages to display
            input_buffer: Current input text
        """
        self.clear()

        # Get visible messages
        messages = message_buffer.get_visible_messages(self.display_height)

        # Draw message area
        self.draw_message_area(messages)

        # Draw input line
        self.draw_input_line(input_buffer)

        self.refresh()

    def get_input_at_position(self, y: int, x: int, initial: str = "", mask: bool = False) -> str:
        """
        Get user input at a specific position with echoing.

        Args:
            y: Row position
            x: Column position
            initial: Initial input value
            mask: Whether to mask input (for passwords)

        Returns:
            Entered string
        """
        input_str = initial
        self._stdscr.nodelay(False)  # Blocking input for this operation

        try:
            while True:
                # Redraw current state
                display_value = "*" * len(input_str) if mask else input_str
                try:
                    self._stdscr.move(y, x)
                    self._stdscr.clrtoeol()
                    self._stdscr.addstr(y, x, display_value)
                    self._stdscr.move(y, x + len(display_value))
                    self.refresh()
                except curses.error:
                    pass

                key = self._stdscr.getch()

                if key in [curses.KEY_ENTER, 10, 13]:  # Enter
                    break
                elif key in [curses.KEY_BACKSPACE, 8, 127]:  # Backspace
                    if input_str:
                        input_str = input_str[:-1]
                elif 0 < key < 256 and chr(key).isprintable():
                    input_str += chr(key)

        finally:
            self._stdscr.nodelay(True)  # Restore non-blocking mode

        return input_str

    def show_error(self, message: str, duration: float = 2.0) -> None:
        """
        Show a temporary error message.

        Args:
            message: Error message to display
            duration: Duration to show message in seconds
        """
        try:
            self._stdscr.addstr(self._height // 2, 0, f"Error: {message}",
                               curses.color_pair(2) if curses.has_colors() else 0)
            self.refresh()
            import time
            time.sleep(duration)
        except curses.error:
            pass

    def show_success(self, message: str, duration: float = 1.0) -> None:
        """
        Show a temporary success message.

        Args:
            message: Success message to display
            duration: Duration to show message in seconds
        """
        try:
            self._stdscr.addstr(self._height // 2, 0, message,
                               curses.color_pair(1) if curses.has_colors() else 0)
            self.refresh()
            import time
            time.sleep(duration)
        except curses.error:
            pass
