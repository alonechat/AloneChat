"""
Message buffer management for curses client.
Handles message storage, scrolling, and navigation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class ScrollDirection(Enum):
    """Direction for scrolling operations."""
    UP = "up"
    DOWN = "down"
    HOME = "home"
    END = "end"
    PAGE_UP = "page_up"
    PAGE_DOWN = "page_down"


@dataclass
class Message:
    """Represents a chat message."""
    sender: str
    content: str
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.timestamp is None:
            import time
            self.timestamp = time.time()

    def format(self) -> str:
        """Format message for display."""
        return f"[{self.sender}] {self.content}"


class MessageBuffer:
    """
    Manages message history and scroll state.
    Provides methods for adding messages and navigating through history.
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize message buffer.

        Args:
            max_history: Maximum number of messages to keep in history
        """
        self._messages: List[Message] = []
        self._scroll_offset: int = 0
        self._auto_scroll: bool = True
        self._max_history: int = max_history

    @property
    def messages(self) -> List[Message]:
        """Get all messages."""
        return self._messages.copy()

    @property
    def scroll_offset(self) -> int:
        """Get current scroll offset."""
        return self._scroll_offset

    @property
    def auto_scroll(self) -> bool:
        """Get auto-scroll state."""
        return self._auto_scroll

    @auto_scroll.setter
    def auto_scroll(self, value: bool) -> None:
        """Set auto-scroll state."""
        self._auto_scroll = value

    def add_message(self, sender: str, content: str) -> None:
        """
        Add a new message to the buffer.

        Args:
            sender: Message sender
            content: Message content
        """
        message = Message(sender=sender, content=content)
        self._messages.append(message)

        # Trim history if exceeds max
        if len(self._messages) > self._max_history:
            self._messages = self._messages[-self._max_history:]
            # Adjust scroll offset if needed
            if self._scroll_offset > 0:
                self._scroll_offset = max(0, self._scroll_offset - 1)

    def add_system_message(self, content: str) -> None:
        """
        Add a system message.

        Args:
            content: Message content
        """
        self.add_message("System", content)

    def add_error_message(self, content: str) -> None:
        """
        Add an error message.

        Args:
            content: Error message content
        """
        self.add_message("! Error", content)

    def get_visible_messages(self, display_height: int) -> List[str]:
        """
        Get messages visible in the current view.

        Args:
            display_height: Height of the display area

        Returns:
            List of formatted message strings
        """
        if self._auto_scroll:
            self._scroll_offset = max(0, len(self._messages) - display_height)

        start_idx = max(0, self._scroll_offset)
        end_idx = min(len(self._messages), start_idx + display_height)

        return [msg.format() for msg in self._messages[start_idx:end_idx]]

    def scroll(self, direction: ScrollDirection, display_height: int) -> None:
        """
        Scroll the message view.

        Args:
            direction: Direction to scroll
            display_height: Height of the display area
        """
        max_offset = max(0, len(self._messages) - display_height)

        match direction:
            case ScrollDirection.UP:
                if self._scroll_offset > 0:
                    self._scroll_offset -= 1
                self._auto_scroll = False

            case ScrollDirection.DOWN:
                if self._scroll_offset < max_offset:
                    self._scroll_offset += 1
                if self._scroll_offset >= max_offset:
                    self._auto_scroll = True

            case ScrollDirection.PAGE_UP:
                self._scroll_offset = max(0, self._scroll_offset - display_height)
                self._auto_scroll = False

            case ScrollDirection.PAGE_DOWN:
                self._scroll_offset = min(max_offset, self._scroll_offset + display_height)
                if self._scroll_offset >= max_offset:
                    self._auto_scroll = True

            case ScrollDirection.HOME:
                self._scroll_offset = 0
                self._auto_scroll = False

            case ScrollDirection.END:
                self._auto_scroll = True

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()
        self._scroll_offset = 0
        self._auto_scroll = True

    def __len__(self) -> int:
        """Return number of messages."""
        return len(self._messages)
