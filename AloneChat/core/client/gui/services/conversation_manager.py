"""
Conversation management service.

Handles conversations, private chats, and message routing.
Optimized for performance with efficient data structures.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class ConversationType(Enum):
    """Type of conversation."""
    GLOBAL = "global"
    PRIVATE = "private"


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
    msg_id: Optional[str] = None
    
    @classmethod
    def create(
        cls,
        sender: str,
        content: str,
        is_self: bool = False,
        is_system: bool = False,
        status: Optional[str] = None,
        msg_id: Optional[str] = None
    ) -> 'MessageItem':
        """Factory method to create a message with current timestamp."""
        now = datetime.now()
        return cls(
            sender=sender,
            content=content,
            timestamp=now.strftime("%H:%M"),
            ts=now.strftime("%Y-%m-%d %H:%M:%S"),
            is_self=is_self,
            is_system=is_system,
            status=status,
            msg_id=msg_id
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sender": self.sender,
            "content": self.content,
            "timestamp": self.timestamp,
            "ts": self.ts,
            "is_self": self.is_self,
            "is_system": self.is_system,
            "status": self.status,
            "msg_id": self.msg_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageItem':
        """Create from dictionary."""
        return cls(
            sender=data.get("sender", ""),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", ""),
            ts=data.get("ts", ""),
            is_self=data.get("is_self", False),
            is_system=data.get("is_system", False),
            status=data.get("status"),
            msg_id=data.get("msg_id"),
        )


@dataclass
class Conversation:
    """Represents a conversation/channel."""
    cid: str
    name: str
    conv_type: ConversationType = ConversationType.GLOBAL
    items: List[MessageItem] = field(default_factory=list)
    unread: int = 0
    partner_online: bool = False
    partner_status: str = "offline"
    last_activity: Optional[float] = None
    max_items: int = 1000
    
    def add_message(self, item: MessageItem) -> None:
        """Add a message to this conversation."""
        self.items.append(item)
        self.last_activity = datetime.now().timestamp()
        
        while len(self.items) > self.max_items:
            self.items.pop(0)
    
    def mark_read(self) -> None:
        """Mark all messages as read."""
        self.unread = 0
    
    def increment_unread(self) -> None:
        """Increment unread count."""
        self.unread += 1
    
    def update_partner_status(self, is_online: bool, status: str) -> None:
        """Update partner status for private conversations."""
        self.partner_online = is_online
        self.partner_status = status
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cid": self.cid,
            "name": self.name,
            "conv_type": self.conv_type.value,
            "items": [item.to_dict() for item in self.items],
            "unread": self.unread,
            "partner_online": self.partner_online,
            "partner_status": self.partner_status,
            "last_activity": self.last_activity,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        """Create from dictionary."""
        return cls(
            cid=data.get("cid", ""),
            name=data.get("name", ""),
            conv_type=ConversationType(data.get("conv_type", "global")),
            items=[MessageItem.from_dict(item) for item in data.get("items", [])],
            unread=data.get("unread", 0),
            partner_online=data.get("partner_online", False),
            partner_status=data.get("partner_status", "offline"),
            last_activity=data.get("last_activity"),
        )


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


class ConversationManager:
    """
    Manages conversations and direct messages.
    
    Features:
        - Global and private conversations
        - Message routing and DM handling
        - Unread tracking
        - Partner status management
        - Serialization support
    """
    
    _DM_HEADER_RE = re.compile(
        r"^\[\[DM\s+to=(?P<to>[A-Za-z0-9_.-]+)\]\]\s*\n?",
        re.IGNORECASE
    )
    
    def __init__(self, max_items_per_conv: int = 1000):
        self._conversations: Dict[str, Conversation] = {}
        self._conv_ids: List[str] = []
        self._active_cid: str = "global"
        self._max_items = max_items_per_conv
        self._on_conversation_update: Optional[Callable[[str], None]] = None
        
        self._ensure_conversation("global", name="# Global", 
                                   conv_type=ConversationType.GLOBAL)
    
    def set_update_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Set callback for conversation updates."""
        self._on_conversation_update = callback
    
    @property
    def active_cid(self) -> str:
        """Get currently active conversation ID."""
        return self._active_cid
    
    @active_cid.setter
    def active_cid(self, cid: str) -> None:
        """Set active conversation ID."""
        if cid in self._conversations:
            self._active_cid = cid
            self._conversations[cid].mark_read()
    
    @property
    def conversation_ids(self) -> List[str]:
        """Get list of conversation IDs."""
        return self._conv_ids.copy()
    
    def get_conversation(self, cid: str) -> Optional[Conversation]:
        """Get conversation by ID."""
        return self._conversations.get(cid)
    
    def get_active_conversation(self) -> Optional[Conversation]:
        """Get currently active conversation."""
        return self._conversations.get(self._active_cid)
    
    def _ensure_conversation(
        self,
        cid: str,
        name: Optional[str] = None,
        conv_type: ConversationType = ConversationType.PRIVATE
    ) -> Conversation:
        """Ensure a conversation exists, creating it if necessary."""
        if cid not in self._conversations:
            conv = Conversation(
                cid=cid,
                name=name or cid,
                conv_type=conv_type,
                max_items=self._max_items
            )
            self._conversations[cid] = conv
        
        if cid not in self._conv_ids:
            self._conv_ids.append(cid)
        
        return self._conversations[cid]
    
    def switch_conversation(self, cid: str) -> bool:
        """Switch to a different conversation."""
        if cid not in self._conversations:
            return False
        
        self._active_cid = cid
        self._conversations[cid].mark_read()
        
        if self._on_conversation_update:
            self._on_conversation_update(cid)
        
        return True
    
    def create_conversation(
        self,
        cid: str,
        name: Optional[str] = None,
        conv_type: ConversationType = ConversationType.PRIVATE
    ) -> Conversation:
        """Create a new conversation."""
        return self._ensure_conversation(cid, name, conv_type)
    
    def create_private_conversation(
        self,
        partner_id: str,
        partner_name: Optional[str] = None,
        is_online: bool = False,
        status: str = "offline"
    ) -> Conversation:
        """
        Create a private conversation with a user.
        
        Args:
            partner_id: Partner user ID
            partner_name: Partner display name
            is_online: Whether partner is online
            status: Partner status
            
        Returns:
            Conversation
        """
        conv = self._ensure_conversation(
            partner_id,
            name=partner_name or partner_id,
            conv_type=ConversationType.PRIVATE
        )
        
        conv.update_partner_status(is_online, status)
        
        return conv
    
    def update_partner_status(
        self,
        partner_id: str,
        is_online: bool,
        status: str = "online"
    ) -> None:
        """Update partner online status."""
        if partner_id in self._conversations:
            conv = self._conversations[partner_id]
            conv.update_partner_status(is_online, status)
    
    def is_private_conversation(self, cid: str) -> bool:
        """Check if a conversation is a private chat."""
        conv = self._conversations.get(cid)
        return conv is not None and conv.conv_type == ConversationType.PRIVATE
    
    def get_private_conversations(self) -> List[Tuple[str, Conversation]]:
        """Get all private conversations."""
        return [
            (cid, conv)
            for cid in self._conv_ids
            if cid in self._conversations
            and self._conversations[cid].conv_type == ConversationType.PRIVATE
        ]
    
    def add_message(
        self,
        cid: str,
        item: MessageItem,
        is_active: bool = False
    ) -> None:
        """Add a message to a conversation."""
        conv = self._ensure_conversation(cid)
        conv.add_message(item)
        
        if not is_active and not item.is_self:
            conv.increment_unread()
        
        if self._on_conversation_update:
            self._on_conversation_update(cid)
    
    def get_conversation_labels(self) -> List[str]:
        """Get display labels for all conversations."""
        labels = []
        for cid in self._conv_ids:
            conv = self._conversations.get(cid)
            if not conv:
                continue
            
            label = conv.name
            
            if conv.conv_type == ConversationType.PRIVATE:
                status_icon = self._get_status_icon(conv.partner_status, conv.partner_online)
                label = f"{status_icon} {label}"
            
            if conv.unread > 0:
                label = f"{label} ({conv.unread})"
            
            labels.append(label)
        
        return labels
    
    @staticmethod
    def _get_status_icon(status: str, is_online: bool) -> str:
        """Get status icon for display."""
        if not is_online or status == "offline":
            return "○"
        elif status == "away":
            return "◐"
        elif status == "busy":
            return "◑"
        else:
            return "●"
    
    @staticmethod
    def pack_dm(to_user: str, body: str) -> str:
        """Pack a DM message with header."""
        return f"[[DM to={to_user}]]\n{body}"
    
    def unpack_dm(self, content: str) -> Tuple[bool, Optional[str], str]:
        """Unpack a DM message, returning (is_dm, to_user, body)."""
        m = self._DM_HEADER_RE.match(content or "")
        if not m:
            return False, None, content
        
        to_user = m.group("to")
        body = content[m.end():] if content else ""
        return True, to_user, body
    
    def prepare_send_payload(self, content: str, target_cid: str) -> Tuple[str, str]:
        """Prepare payload for sending, handling DM wrapping if needed."""
        if target_cid != "global":
            return self.pack_dm(target_cid, content), target_cid
        return content, "global"
    
    def process_received_message(
        self,
        sender: str,
        content: str,
        current_user: str
    ) -> Tuple[Optional[str], str, str]:
        """
        Process received message.
        
        Returns:
            Tuple of (conversation_id, sender, body)
        """
        is_dm, to_user, body = self.unpack_dm(content)
        
        if is_dm:
            if (to_user or "").lower() != (current_user or "").lower():
                return None, sender, body
            
            self._ensure_conversation(sender, name=sender, 
                                       conv_type=ConversationType.PRIVATE)
            return sender, sender, body
        else:
            return "global", sender, content
    
    def delete_conversation(self, cid: str) -> bool:
        """Delete a conversation."""
        if cid == "global":
            return False
        
        if cid in self._conversations:
            del self._conversations[cid]
            self._conv_ids.remove(cid)
            
            if self._active_cid == cid:
                self._active_cid = "global"
            
            return True
        
        return False
    
    def clear_conversation(self, cid: str) -> bool:
        """Clear all messages from a conversation."""
        if cid in self._conversations:
            self._conversations[cid].items.clear()
            self._conversations[cid].unread = 0
            return True
        return False
    
    def get_total_unread(self) -> int:
        """Get total unread count across all conversations."""
        return sum(conv.unread for conv in self._conversations.values())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "conversations": {
                cid: conv.to_dict()
                for cid, conv in self._conversations.items()
            },
            "conv_ids": self._conv_ids,
            "active_cid": self._active_cid,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationManager':
        """Create from dictionary."""
        manager = cls()
        manager._conversations = {}
        manager._conv_ids = data.get("conv_ids", ["global"])
        manager._active_cid = data.get("active_cid", "global")
        
        for cid, conv_data in data.get("conversations", {}).items():
            manager._conversations[cid] = Conversation.from_dict(conv_data)
        
        return manager


__all__ = [
    'ConversationType',
    'MessageItem',
    'Conversation',
    'ReplyContext',
    'ConversationManager',
]
