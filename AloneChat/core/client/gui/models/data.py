"""
Data models for GUI client.

Re-exports from conversation_manager for backward compatibility.
"""

from ..services.conversation_manager import (
    ConversationType,
    MessageItem,
    Conversation,
    ReplyContext,
)

__all__ = [
    'ConversationType',
    'MessageItem',
    'Conversation',
    'ReplyContext',
]
