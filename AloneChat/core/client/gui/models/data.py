"""
Data models for GUI client.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class MessageItem:
    """Represents a message in a conversation."""
    sender: str
    content: str
    timestamp: str
    ts: str
    is_self: bool = False
    is_system: bool = False
    status: Optional[str] = None
    
    @classmethod
    def create(cls, sender: str, content: str, is_self: bool = False, 
               is_system: bool = False, status: Optional[str] = None) -> 'MessageItem':
        """Factory method to create a message with current timestamp."""
        now = datetime.now()
        return cls(
            sender=sender,
            content=content,
            timestamp=now.strftime("%H:%M"),
            ts=now.strftime("%Y-%m-%d %H:%M:%S"),
            is_self=is_self,
            is_system=is_system,
            status=status
        )


@dataclass
class Conversation:
    """Represents a conversation/channel."""
    cid: str
    name: str
    items: List[MessageItem] = field(default_factory=list)
    unread: int = 0
    
    def add_message(self, item: MessageItem) -> None:
        """Add a message to this conversation."""
        self.items.append(item)
    
    def mark_read(self) -> None:
        """Mark all messages as read."""
        self.unread = 0
    
    def increment_unread(self) -> None:
        """Increment unread count."""
        self.unread += 1


@dataclass
class ReplyContext:
    """Context for reply/quote functionality."""
    sender: str
    content: str
    timestamp: str
    
    def get_snippet(self, max_length: int = 80) -> str:
        """Get a snippet of the content for display."""
        snippet = self.content.replace("\n", " ")
        if len(snippet) > max_length:
            snippet = snippet[:max_length] + "…"
        return snippet
