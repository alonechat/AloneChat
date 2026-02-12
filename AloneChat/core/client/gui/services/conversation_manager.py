"""
Conversation management service.
Handles conversations, DMs, and message routing.
"""
import re
from typing import Dict, List, Optional, Any, Tuple
from ..models.data import Conversation, MessageItem


class ConversationManager:
    """Manages conversations and direct messages."""
    
    _DM_HEADER_RE = re.compile(r"^\[\[DM\s+to=(?P<to>[A-Za-z0-9_.-]+)\]\]\s*\n?", re.IGNORECASE)
    
    def __init__(self):
        self._conversations: Dict[str, Conversation] = {}
        self._conv_ids: List[str] = []
        self._active_cid: str = "global"
        self._ensure_conversation("global", name="# Global")
    
    @property
    def active_cid(self) -> str:
        """Get currently active conversation ID."""
        return self._active_cid
    
    @active_cid.setter
    def active_cid(self, cid: str) -> None:
        """Set active conversation ID."""
        self._active_cid = cid
        if cid in self._conversations:
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
    
    def _ensure_conversation(self, cid: str, name: Optional[str] = None) -> Conversation:
        """Ensure a conversation exists, creating it if necessary."""
        if cid not in self._conversations:
            self._conversations[cid] = Conversation(cid=cid, name=name or cid)
        if cid not in self._conv_ids:
            self._conv_ids.append(cid)
        return self._conversations[cid]
    
    def switch_conversation(self, cid: str) -> bool:
        """Switch to a different conversation."""
        if cid not in self._conversations:
            return False
        self._active_cid = cid
        self._conversations[cid].mark_read()
        return True
    
    def create_conversation(self, cid: str, name: Optional[str] = None) -> Conversation:
        """Create a new conversation."""
        return self._ensure_conversation(cid, name)
    
    def add_message(self, cid: str, item: MessageItem, is_active: bool = False) -> None:
        """Add a message to a conversation."""
        conv = self._ensure_conversation(cid)
        conv.add_message(item)
        if not is_active and not item.is_self:
            conv.increment_unread()
    
    def get_conversation_labels(self) -> List[str]:
        """Get display labels for all conversations."""
        labels = []
        for cid in self._conv_ids:
            conv = self._conversations.get(cid)
            if conv:
                label = conv.name
                if conv.unread > 0:
                    label = f"{label} ({conv.unread})"
                labels.append(label)
        return labels
    
    def pack_dm(self, to_user: str, body: str) -> str:
        """Pack a DM message with header."""
        return f"[[DM to={to_user}]]\n{body}"
    
    def unpack_dm(self, content: str) -> Tuple[bool, Optional[str], str]:
        """Unpack a DM message, returning (is_dm, to_user, body)."""
        m = self._DM_HEADER_RE.match(content or "")
        if not m:
            return False, None, content
        to_user = m.group("to")
        body = (content[m.end():] if content else "")
        return True, to_user, body
    
    def prepare_send_payload(self, content: str, target_cid: str) -> Tuple[str, str]:
        """Prepare payload for sending, handling DM wrapping if needed."""
        if target_cid != "global":
            return self.pack_dm(target_cid, content), target_cid
        return content, "global"
    
    def process_received_message(self, sender: str, content: str, 
                                 current_user: str) -> Tuple[Optional[str], str, str]:
        """Process received message, returning (cid, sender, body)."""
        is_dm, to_user, body = self.unpack_dm(content)
        
        if is_dm:
            # Only accept DMs addressed to me
            if (to_user or "").lower() != (current_user or "").lower():
                return None, sender, body
            # DM from sender
            self._ensure_conversation(sender, name=sender)
            return sender, sender, body
        else:
            # Global message
            return "global", sender, content
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "conversations": {
                cid: {
                    "cid": conv.cid,
                    "name": conv.name,
                    "items": [
                        {
                            "sender": item.sender,
                            "content": item.content,
                            "timestamp": item.timestamp,
                            "ts": item.ts,
                            "is_self": item.is_self,
                            "is_system": item.is_system,
                            "status": item.status,
                        }
                        for item in conv.items
                    ],
                    "unread": conv.unread,
                }
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
            conv = Conversation(
                cid=conv_data["cid"],
                name=conv_data["name"],
                items=[
                    MessageItem(
                        sender=item["sender"],
                        content=item["content"],
                        timestamp=item["timestamp"],
                        ts=item["ts"],
                        is_self=item["is_self"],
                        is_system=item["is_system"],
                        status=item.get("status"),
                    )
                    for item in conv_data.get("items", [])
                ],
                unread=conv_data.get("unread", 0),
            )
            manager._conversations[cid] = conv
        
        return manager
