"""
AloneChat message package.

Provides the core message protocol types, migrated from AloneChat.core.message.
"""

from .protocol import Message, MessageType, ProtocolError

__all__ = ["Message", "MessageType", "ProtocolError"]
