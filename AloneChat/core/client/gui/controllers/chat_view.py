"""
Chat view with conversations, messages, and input - sv_ttk styled.
Uses ttk.Combobox for conversation selection (TTK widget, not TK).
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional, List

from ..components import WinUI3ScrollableFrame, WinUI3MessageCard
from ..models.data import MessageItem, ReplyContext
from ..services.conversation_manager import ConversationManager


class ChatView:
    """Main chat view with sidebar and message area - sv_ttk styled."""
    
    def __init__(self, root: tk.Tk, username: str,
                 conversation_manager: ConversationManager,
                 on_send: Callable[[str], None],
                 on_select_conversation: Callable[[str], None],
                 on_reply: Callable[[str, str, str], None],
                 on_clear_reply: Callable[[], None],
                 on_export_md: Callable[[], None],
                 on_export_json: Callable[[], None],
                 on_export_logs: Callable[[], None],
                 on_logout: Callable[[], None],
                 on_set_status: Optional[Callable[[str], None]] = None,
                 on_refresh_users: Optional[Callable[[], None]] = None,
                 on_user_list: Optional[Callable[[], None]] = None):
        self.root = root
        self.username = username
        self.conv_manager = conversation_manager
        self.on_send = on_send
        self.on_select_conversation = on_select_conversation
        self.on_reply = on_reply
        self.on_clear_reply = on_clear_reply
        self.on_export_md = on_export_md
        self.on_export_json = on_export_json
        self.on_export_logs = on_export_logs
        self.on_logout = on_logout
        self.on_set_status = on_set_status
        self.on_refresh_users = on_refresh_users
        self.on_user_list = on_user_list
        
        self.frame: Optional[ttk.Frame] = None
        self.header: Optional[ttk.Frame] = None
        self.main_pane: Optional[ttk.Frame] = None
        self.messages_container: Optional[WinUI3ScrollableFrame] = None
        self.conv_combo: Optional[ttk.Combobox] = None
        self.msg_entry: Optional[ttk.Entry] = None
        self.reply_banner: Optional[ttk.Frame] = None
        self.reply_label: Optional[ttk.Label] = None
        self.status_var: Optional[tk.StringVar] = None
        self.status_combo: Optional[ttk.Combobox] = None
        self.partner_status_label: Optional[ttk.Label] = None
        
        self.message_cards: List[WinUI3MessageCard] = []
    
    def show(self):
        """Display the chat view with sv_ttk styling."""
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        self._build_header()
        self._build_main_pane()
        self._bind_shortcuts()
    
    def hide(self):
        """Hide the chat view."""
        if self.header:
            self.header.destroy()
            self.header = None
        if self.main_pane:
            self.main_pane.destroy()
            self.main_pane = None
        self.frame = None
    
    def _build_header(self):
        """Build the header bar with sv_ttk styling."""
        self.header = ttk.Frame(self.root, padding=(16, 12))
        self.header.grid(row=0, column=0, sticky="ew")
        
        header_left = ttk.Frame(self.header)
        header_left.pack(side="left")
        
        title = ttk.Label(header_left, text="AloneChat")
        title.pack(side="left")
        
        user_label = ttk.Label(header_left, text=f"  |  {self.username}")
        user_label.pack(side="left")
        
        if self.on_set_status:
            self.status_var = tk.StringVar(value="online")
            self.status_combo = ttk.Combobox(
                header_left, 
                textvariable=self.status_var,
                values=["online", "away", "busy", "offline"],
                state="readonly",
                width=8
            )
            self.status_combo.pack(side="left", padx=(8, 0))
            self.status_combo.bind("<<ComboboxSelected>>", self._on_status_change)
        
        btn_frame = ttk.Frame(self.header)
        btn_frame.pack(side="right")
        
        if self.on_refresh_users:
            ttk.Button(btn_frame, text="Refresh", 
                      command=self.on_refresh_users).pack(side="right", padx=4)
        
        ttk.Button(btn_frame, text="Export", 
                  command=self.on_export_logs).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="Logout",
                  command=self.on_logout).pack(side="right", padx=4)
    
    def _build_main_pane(self):
        """Build the main content area."""
        self.main_pane = ttk.Frame(self.root)
        self.main_pane.grid(row=1, column=0, sticky="nsew", 
                      padx=16, pady=12)
        self.main_pane.grid_rowconfigure(0, weight=1)
        self.main_pane.grid_columnconfigure(1, weight=1)
        
        self._build_sidebar(self.main_pane)
        self._build_chat_area(self.main_pane)
    
    def _build_sidebar(self, parent: ttk.Frame):
        """Build the conversation sidebar with sv_ttk styling using Combobox."""
        sidebar = ttk.LabelFrame(parent, text="Conversations", padding=12)
        sidebar.grid(row=0, column=0, sticky="ns")
        
        ttk.Button(sidebar, text="User List", 
                  command=self._on_user_list).pack(fill="x", pady=(0, 12))
        
        ttk.Label(sidebar, text="Select conversation:").pack(anchor="w", pady=(0, 4))
        
        self.conv_combo = ttk.Combobox(sidebar, state="readonly", width=25)
        self.conv_combo.pack(fill="x", pady=(0, 12))
        
        self.conv_combo.bind("<<ComboboxSelected>>", self._on_conv_select)
        
        self.partner_status_label = ttk.Label(sidebar, text="", foreground="gray")
        self.partner_status_label.pack(anchor="w", pady=(0, 8))
        
        self.refresh_conversation_list()
    
    def _build_chat_area(self, parent: ttk.Frame):
        """Build the chat message area."""
        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        
        self.messages_container = WinUI3ScrollableFrame(right)
        self.messages_container.grid(row=0, column=0, sticky="nsew")
        
        self._build_input_area(right)
    
    def _build_input_area(self, parent: ttk.Frame):
        """Build the message input area."""
        input_frame = ttk.LabelFrame(parent, text="", padding=(16, 12))
        input_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        
        self.reply_banner = ttk.Frame(input_frame)
        self.reply_label = ttk.Label(self.reply_banner, text="")
        self.reply_label.pack(side="left", fill="x", expand=True)
        
        close_btn = ttk.Label(self.reply_banner, text="✕", cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.on_clear_reply())
        self.reply_banner.pack_forget()
        
        entry_row = ttk.Frame(input_frame)
        entry_row.pack(fill="x", pady=(8, 0))
        
        self.msg_entry = ttk.Entry(entry_row)
        self.msg_entry.pack(side="left", fill="x", expand=True)
        self.msg_entry.bind('<Return>', self._on_enter_pressed)
        
        ttk.Button(entry_row, text="Send",
                  command=self._on_send_clicked).pack(side="right", padx=(12, 0))
    
    def _bind_shortcuts(self):
        """Bind keyboard shortcuts."""
        self.root.bind('<Control-l>', lambda e: self.on_logout())
    
    def _on_status_change(self, event):
        """Handle status change."""
        if self.status_var and self.on_set_status:
            status = self.status_var.get()
            self.on_set_status(status)
    
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
    
    def _on_send_clicked(self):
        """Handle send button click."""
        content = self.msg_entry.get() if self.msg_entry else ""
        if content.strip():
            self.on_send(content)
    
    def _on_enter_pressed(self, event=None):
        """Handle Enter key in message entry."""
        self._on_send_clicked()
        return "break"
    
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
    
    def show_reply_banner(self, ctx: ReplyContext):
        """Show reply banner with context."""
        if self.reply_banner and self.reply_label:
            snippet = ctx.get_snippet(80)
            self.reply_label.config(
                text=f"Replying to {ctx.sender} ({ctx.timestamp}): {snippet}")
            self.reply_banner.pack(fill="x", pady=(0, 8))
    
    def hide_reply_banner(self):
        """Hide the reply banner."""
        if self.reply_banner:
            self.reply_banner.pack_forget()
    
    def clear_message_entry(self):
        """Clear the message entry field."""
        if self.msg_entry:
            self.msg_entry.delete(0, tk.END)
    
    def render_conversation(self):
        """Render the active conversation messages."""
        if not self.messages_container:
            return
        
        if hasattr(self.messages_container, 'content') and self.messages_container.content:
            for w in list(self.messages_container.content.winfo_children()):
                w.destroy()
        self.message_cards = []
        
        conv = self.conv_manager.get_active_conversation()
        if not conv:
            return
        
        for item in conv.items:
            card = self._create_message_card(item)
            card.pack(fill="x", pady=4)
            self.message_cards.append(card)
        
        if hasattr(self.messages_container, 'scroll_to_bottom'):
            self.messages_container.scroll_to_bottom()
        
        self._update_partner_status_label(self.conv_manager.active_cid)
    
    def _create_message_card(self, item: MessageItem) -> WinUI3MessageCard:
        """Create a message card from a message item."""
        on_reply = None if item.is_system else self.on_reply
        return WinUI3MessageCard(
            self.messages_container.content,
            sender=item.sender,
            content=item.content,
            is_self=item.is_self,
            is_system=item.is_system,
            timestamp=item.timestamp,
            status=item.status,
            on_reply=on_reply,
        )
    
    def add_message_card(self, item: MessageItem) -> WinUI3MessageCard:
        """Add a single message card to the view."""
        card = self._create_message_card(item)
        card.pack(fill="x", pady=4)
        self.message_cards.append(card)
        self.messages_container.scroll_to_bottom()
        return card
    
    def scroll_to_bottom(self):
        """Scroll to bottom of messages."""
        if self.messages_container:
            self.messages_container.scroll_to_bottom()
    
    def scroll_to_card(self, card: WinUI3MessageCard):
        """Scroll to a specific message card."""
        if self.messages_container:
            self.messages_container.scroll_to_widget(card)
    
    def get_message_cards(self) -> List[WinUI3MessageCard]:
        """Get all message cards in current view."""
        return self.message_cards
    
    def update_partner_status(self, partner_id: str, is_online: bool, status: str):
        """Update partner status display."""
        self.conv_manager.update_partner_status(partner_id, is_online, status)
        if self.conv_manager.active_cid == partner_id:
            self._update_partner_status_label(partner_id)
        self.refresh_conversation_list()
