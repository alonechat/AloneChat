"""
Conversation management service.
Handles conversations, DMs, and message routing.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from ..models.data import Conversation, MessageItem


@dataclass
class PrivateChatInfo:
    """Information about a private chat."""
    partner_id: str
    partner_name: str
    is_online: bool = False
    status: str = "offline"
    last_activity: Optional[float] = None
    unread: int = 0


class ConversationManager:
    """Manages conversations and direct messages."""
    
    _DM_HEADER_RE = re.compile(r"^\[\[DM\s+to=(?P<to>[A-Za-z0-9_.-]+)\]\]\s*\n?", re.IGNORECASE)
    
    def __init__(self):
        self._conversations: Dict[str, Conversation] = {}
        self._conv_ids: List[str] = []
        self._active_cid: str = "global"
        self._private_chat_info: Dict[str, PrivateChatInfo] = {}
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
    
    def create_private_conversation(self, partner_id: str, partner_name: Optional[str] = None,
                                    is_online: bool = False, status: str = "offline") -> Conversation:
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
        conv = self._ensure_conversation(partner_id, name=partner_name or partner_id)
        
        self._private_chat_info[partner_id] = PrivateChatInfo(
            partner_id=partner_id,
            partner_name=partner_name or partner_id,
            is_online=is_online,
            status=status,
            last_activity=datetime.now().timestamp()
        )
        
        return conv
    
    def update_partner_status(self, partner_id: str, is_online: bool, status: str = "online") -> None:
        """
        Update partner online status.
        
        Args:
            partner_id: Partner user ID
            is_online: Whether partner is online
            status: Status string
        """
        if partner_id in self._private_chat_info:
            info = self._private_chat_info[partner_id]
            info.is_online = is_online
            info.status = status
    
    def get_private_chat_info(self, partner_id: str) -> Optional[PrivateChatInfo]:
        """Get private chat info for a partner."""
        return self._private_chat_info.get(partner_id)
    
    def is_private_conversation(self, cid: str) -> bool:
        """Check if a conversation is a private chat."""
        return cid != "global" and cid in self._private_chat_info
    
    def get_private_conversations(self) -> List[Tuple[str, PrivateChatInfo]]:
        """Get all private conversations with their info."""
        return [
            (cid, self._private_chat_info[cid])
            for cid in self._conv_ids
            if cid in self._private_chat_info
        ]
    
    def add_message(self, cid: str, item: MessageItem, is_active: bool = False) -> None:
        """Add a message to a conversation."""
        conv = self._ensure_conversation(cid)
        conv.add_message(item)
        if not is_active and not item.is_self:
            conv.increment_unread()
            if cid in self._private_chat_info:
                self._private_chat_info[cid].unread += 1
    
    def get_conversation_labels(self) -> List[str]:
        """Get display labels for all conversations."""
        labels = []
        for cid in self._conv_ids:
            conv = self._conversations.get(cid)
            if conv:
                label = conv.name
                
                if cid in self._private_chat_info:
                    info = self._private_chat_info[cid]
                    status_icon = self._get_status_icon(info.status, info.is_online)
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
            if (to_user or "").lower() != (current_user or "").lower():
                return None, sender, body
            self._ensure_conversation(sender, name=sender)
            if sender not in self._private_chat_info:
                self._private_chat_info[sender] = PrivateChatInfo(
                    partner_id=sender,
                    partner_name=sender
                )
            return sender, sender, body
        else:
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
            "private_chat_info": {
                pid: {
                    "partner_id": info.partner_id,
                    "partner_name": info.partner_name,
                    "is_online": info.is_online,
                    "status": info.status,
                    "last_activity": info.last_activity,
                    "unread": info.unread,
                }
                for pid, info in self._private_chat_info.items()
            }
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
        
        for pid, info_data in data.get("private_chat_info", {}).items():
            manager._private_chat_info[pid] = PrivateChatInfo(
                partner_id=info_data.get("partner_id", pid),
                partner_name=info_data.get("partner_name", pid),
                is_online=info_data.get("is_online", False),
                status=info_data.get("status", "offline"),
                last_activity=info_data.get("last_activity"),
                unread=info_data.get("unread", 0),
            )
        
        return manager
