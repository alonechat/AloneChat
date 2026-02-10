"""
Input handler for processing keyboard input in the curses client.
Manages input buffer state and processes key presses.
"""

import curses
from typing import Optional, Callable, Awaitable
from enum import Enum, auto

from .key_mappings import InputAction, get_action_for_key, get_char
from ..ui.message_buffer import MessageBuffer, ScrollDirection


class InputResult(Enum):
    """Result of processing an input action."""
    HANDLED = auto()
    SUBMIT = auto()
    QUIT = auto()
    ERROR = auto()


class InputHandler:
    """
    Handles keyboard input processing for the chat client.
    Manages input buffer and dispatches actions.
    """

    def __init__(
        self,
        stdscr,
        message_buffer: MessageBuffer,
        on_submit: Optional[Callable[[str], Awaitable[None]]] = None
    ):
        """
        Initialize input handler.

        Args:
            stdscr: Curses window object
            message_buffer: Message buffer for scroll operations
            on_submit: Callback for when input is submitted
        """
        self._stdscr = stdscr
        self._message_buffer = message_buffer
        self._on_submit = on_submit
        self._input_buffer: str = ""
        self._running: bool = True

    @property
    def input_buffer(self) -> str:
        """Get current input buffer content."""
        return self._input_buffer

    @property
    def is_running(self) -> bool:
        """Check if handler is running."""
        return self._running

    def clear_buffer(self) -> None:
        """Clear the input buffer."""
        self._input_buffer = ""

    def set_buffer(self, text: str) -> None:
        """
        Set the input buffer content.

        Args:
            text: Text to set
        """
        self._input_buffer = text

    async def process_key(self, key: int) -> InputResult:
        """
        Process a single key press.

        Args:
            key: Curses key code

        Returns:
            InputResult indicating the outcome
        """
        action = get_action_for_key(key)

        match action:
            case InputAction.TYPE_CHAR:
                char = get_char(key)
                if char:
                    self._input_buffer += char
                return InputResult.HANDLED

            case InputAction.BACKSPACE:
                if self._input_buffer:
                    self._input_buffer = self._input_buffer[:-1]
                return InputResult.HANDLED

            case InputAction.SUBMIT:
                if self._input_buffer.strip():
                    if self._on_submit:
                        await self._on_submit(self._input_buffer)
                    return InputResult.SUBMIT
                return InputResult.HANDLED

            case InputAction.SCROLL_UP:
                self._message_buffer.scroll(ScrollDirection.UP, self._get_display_height())
                return InputResult.HANDLED

            case InputAction.SCROLL_DOWN:
                self._message_buffer.scroll(ScrollDirection.DOWN, self._get_display_height())
                return InputResult.HANDLED

            case InputAction.SCROLL_PAGE_UP:
                self._message_buffer.scroll(ScrollDirection.PAGE_UP, self._get_display_height())
                return InputResult.HANDLED

            case InputAction.SCROLL_PAGE_DOWN:
                self._message_buffer.scroll(ScrollDirection.PAGE_DOWN, self._get_display_height())
                return InputResult.HANDLED

            case InputAction.SCROLL_HOME:
                self._message_buffer.scroll(ScrollDirection.HOME, self._get_display_height())
                return InputResult.HANDLED

            case InputAction.SCROLL_END:
                self._message_buffer.scroll(ScrollDirection.END, self._get_display_height())
                return InputResult.HANDLED

            case InputAction.QUIT:
                self._running = False
                return InputResult.QUIT

            case InputAction.HELP:
                # Could show help message
                return InputResult.HANDLED

            case _:
                return InputResult.HANDLED

    def _get_display_height(self) -> int:
        """Get the display height from screen dimensions."""
        height, _ = self._stdscr.getmaxyx()
        return height - 1  # Reserve one line for input

    async def read_input(self) -> tuple[InputResult, int]:
        """
        Read and process a single key press.

        Returns:
            Tuple of (InputResult, raw_key_code)
        """
        try:
            key = self._stdscr.getch()
            if key == -1:  # No input available
                return InputResult.HANDLED, key

            result = await self.process_key(key)
            return result, key

        except Exception as e:
            # Log error but don't crash
            return InputResult.ERROR, -1

    def stop(self) -> None:
        """Stop the input handler."""
        self._running = False
