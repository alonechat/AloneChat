"""
Sidebar component for chat view.
Contains conversation selector and user list button.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..services.conversation_manager import ConversationManager


class Sidebar:
    """Sidebar with conversation selector and user list."""
    
    def __init__(self, parent: ttk.Frame, 
                 conversation_manager: 'ConversationManager',
                 on_select_conversation: Callable[[str], None],
                 on_user_list: Optional[Callable[[], None]] = None):
        self.parent = parent
        self.conv_manager = conversation_manager
        self.on_select_conversation = on_select_conversation
        self.on_user_list = on_user_list
        
        self.frame: Optional[ttk.LabelFrame] = None
        self.conv_combo: Optional[ttk.Combobox] = None
        self.partner_status_label: Optional[ttk.Label] = None
    
    def build(self) -> ttk.LabelFrame:
        """Build and return the sidebar frame."""
        self.frame = ttk.LabelFrame(self.parent, text="Conversations", padding=12)
        
        if self.on_user_list:
            ttk.Button(self.frame, text="User List",
                      command=self._on_user_list).pack(fill="x", pady=(0, 12))
        
        ttk.Label(self.frame, text="Select conversation:").pack(anchor="w", pady=(0, 4))
        
        self.conv_combo = ttk.Combobox(self.frame, state="readonly", width=25)
        self.conv_combo.pack(fill="x", pady=(0, 12))
        self.conv_combo.bind("<<ComboboxSelected>>", self._on_conv_select)
        
        self.partner_status_label = ttk.Label(self.frame, text="", foreground="gray")
        self.partner_status_label.pack(anchor="w", pady=(0, 8))
        
        self.refresh_conversation_list()
        
        return self.frame
    
    def _on_user_list(self):
        """Handle user list button click."""
        if self.on_user_list:
            self.on_user_list()
    
    def _on_conv_select(self, event):
        """Handle conversation selection from Combobox."""
        if not self.conv_combo:
            return
        
        selection = self.conv_combo.current()
        if selection < 0:
            return
        
        conv_ids = self.conv_manager.conversation_ids
        if 0 <= selection < len(conv_ids):
            self.on_select_conversation(conv_ids[selection])
            self._update_partner_status_label(conv_ids[selection])
    
    def _update_partner_status_label(self, cid: str):
        """Update partner status label for private chats."""
        if not self.partner_status_label:
            return
        
        if self.conv_manager.is_private_conversation(cid):
            info = self.conv_manager.get_private_chat_info(cid)
            if info:
                status_text = f"Status: {info.status}"
                if info.is_online:
                    status_text += " (online)"
                self.partner_status_label.config(text=status_text)
            else:
                self.partner_status_label.config(text="Status: unknown")
        else:
            self.partner_status_label.config(text="")
    
    def refresh_conversation_list(self):
        """Refresh the conversation list display."""
        if not self.conv_combo:
            return
        
        labels = self.conv_manager.get_conversation_labels()
        self.conv_combo['values'] = labels
        
        try:
            idx = self.conv_manager.conversation_ids.index(self.conv_manager.active_cid)
            self.conv_combo.current(idx)
            self._update_partner_status_label(self.conv_manager.active_cid)
        except (ValueError, tk.TclError):
            pass
    
    def update_partner_status(self, partner_id: str, is_online: bool, status: str):
        """Update partner status display."""
        self.conv_manager.update_partner_status(partner_id, is_online, status)
        if self.conv_manager.active_cid == partner_id:
            self._update_partner_status_label(partner_id)
        self.refresh_conversation_list()
    
    def destroy(self):
        """Destroy the sidebar frame."""
        if self.frame:
            self.frame.destroy()
            self.frame = None
