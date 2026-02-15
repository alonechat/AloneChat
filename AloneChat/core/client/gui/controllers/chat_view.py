"""
Chat view with conversations, messages, and input - sv_ttk styled.
Uses ttk.Combobox for conversation selection (TTK widget, not TK).
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, List

from ..components import WinUI3ScrollableFrame, WinUI3MessageCard
from ..models.data import MessageItem, ReplyContext
from ..services.conversation_manager import ConversationManager


class ChatView:
    """Main chat view with sidebar and message area - sv_ttk styled."""
    
    def __init__(self, root: tk.Tk, username: str,
                 conversation_manager: ConversationManager,
                 on_send: Callable[[str], None],
                 on_new_conversation: Callable[[], None],
                 on_open_contacts: Callable[[], None],
                 on_select_conversation: Callable[[str], None],
                 on_toggle_pin: Callable[[], None],
                 on_toggle_mute: Callable[[], None],
                 on_reply: Callable[[str, str, str], None],
                 on_clear_reply: Callable[[], None],
                 on_export_md: Callable[[], None],
                 on_export_json: Callable[[], None],
                 on_export_logs: Callable[[], None],
                 on_logout: Callable[[], None]):
        self.root = root
        self.username = username
        self.conv_manager = conversation_manager
        self.on_send = on_send
        self.on_new_conversation = on_new_conversation
        self.on_open_contacts = on_open_contacts
        self.on_select_conversation = on_select_conversation
        self.on_toggle_pin = on_toggle_pin
        self.on_toggle_mute = on_toggle_mute
        self.on_reply = on_reply
        self.on_clear_reply = on_clear_reply
        self.on_export_md = on_export_md
        self.on_export_json = on_export_json
        self.on_export_logs = on_export_logs
        self.on_logout = on_logout
        
        # UI Components
        self.frame: Optional[ttk.Frame] = None
        self.header: Optional[ttk.Frame] = None
        self.main_pane: Optional[ttk.Frame] = None
        self.messages_container: Optional[WinUI3ScrollableFrame] = None
        self.conv_combo: Optional[ttk.Combobox] = None
        self.pin_btn: Optional[ttk.Button] = None
        self.mute_btn: Optional[ttk.Button] = None
        self.msg_entry: Optional[ttk.Entry] = None
        self.reply_banner: Optional[ttk.Frame] = None
        self.reply_label: Optional[ttk.Label] = None
        self.contacts_btn: Optional[ttk.Button] = None
        
        # Message cards for current view
        self.message_cards: List[WinUI3MessageCard] = []
    
    def show(self):
        """Display the chat view with sv_ttk styling."""
        # Configure grid - row 0 for header (no expand), row 1 for content (expand)
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Header
        self._build_header()
        
        # Main pane (left: conversations, right: chat)
        self._build_main_pane()
        
        # Bind shortcuts
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
        
        # App title - let sv_ttk handle fonts
        title = ttk.Label(header_left, text="AloneChat")
        title.pack(side="left")
        
        # User label
        user_label = ttk.Label(header_left, text=f"  |  {self.username}")
        user_label.pack(side="left")
        
        # Action buttons
        btn_frame = ttk.Frame(self.header)
        btn_frame.pack(side="right")
        
        # Export is intentionally hidden in the "WeChat-like" flow.
        ttk.Button(btn_frame, text="Logout",
                  command=self.on_logout).pack(side="right", padx=4)
    
    def _build_main_pane(self):
        """Build the main content area."""
        self.main_pane = ttk.Frame(self.root)
        self.main_pane.grid(row=1, column=0, sticky="nsew", 
                      padx=16, pady=12)
        self.main_pane.grid_rowconfigure(0, weight=1)
        self.main_pane.grid_columnconfigure(1, weight=1)
        
        # Left sidebar: conversations
        self._build_sidebar(self.main_pane)
        
        # Right: chat area
        self._build_chat_area(self.main_pane)
    
    def _build_sidebar(self, parent: ttk.Frame):
        """Build the conversation sidebar with sv_ttk styling using Combobox."""
        sidebar = ttk.LabelFrame(parent, text="Conversations", padding=12)
        sidebar.grid(row=0, column=0, sticky="ns")
        
        # Actions
        self.contacts_btn = ttk.Button(sidebar, text="Contacts / Friend Requests",
                                       command=self.on_open_contacts)
        self.contacts_btn.pack(fill="x", pady=(0, 8))
        ttk.Button(sidebar, text="New Conversation",
                   command=self.on_new_conversation).pack(fill="x", pady=(0, 12))
        
        # Conversation selector using Combobox (TTK widget)
        ttk.Label(sidebar, text="Select conversation:").pack(anchor="w", pady=(0, 4))
        
        self.conv_combo = ttk.Combobox(sidebar, state="readonly", width=25)
        self.conv_combo.pack(fill="x", pady=(0, 12))
        
        # Bind selection event
        self.conv_combo.bind("<<ComboboxSelected>>", self._on_conv_select)

        # Pin / Mute controls (WeChat-like)
        ctrl = ttk.Frame(sidebar)
        ctrl.pack(fill="x", pady=(0, 10))
        self.pin_btn = ttk.Button(ctrl, text="Pin", command=self.on_toggle_pin)
        self.pin_btn.pack(side="left", fill="x", expand=True)
        self.mute_btn = ttk.Button(ctrl, text="Mute", command=self.on_toggle_mute)
        self.mute_btn.pack(side="left", fill="x", expand=True, padx=(8, 0))
        
        self.refresh_conversation_list()

    def set_contacts_badge(self, pending_incoming: int = 0) -> None:
        """Update contacts button badge (incoming friend requests)."""
        if not self.contacts_btn:
            return
        n = int(pending_incoming or 0)
        if n > 0:
            self.contacts_btn.config(text=f"Contacts / Friend Requests  ({n})")
        else:
            self.contacts_btn.config(text="Contacts / Friend Requests")
    
    def _build_chat_area(self, parent: ttk.Frame):
        """Build the chat message area."""
        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        
        # Messages area
        self.messages_container = WinUI3ScrollableFrame(right)
        self.messages_container.grid(row=0, column=0, sticky="nsew")
        
        # Input area
        self._build_input_area(right)
    
    def _build_input_area(self, parent: ttk.Frame):
        """Build the message input area."""
        input_frame = ttk.LabelFrame(parent, text="", padding=(16, 12))
        input_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        
        # Reply banner (hidden by default)
        self.reply_banner = ttk.Frame(input_frame)
        self.reply_label = ttk.Label(self.reply_banner, text="")
        self.reply_label.pack(side="left", fill="x", expand=True)
        
        close_btn = ttk.Label(self.reply_banner, text="✕", cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.on_clear_reply())
        self.reply_banner.pack_forget()
        
        # Message entry row
        entry_row = ttk.Frame(input_frame)
        entry_row.pack(fill="x", pady=(8, 0))
        
        # Message entry
        self.msg_entry = ttk.Entry(entry_row)
        self.msg_entry.pack(side="left", fill="x", expand=True)
        self.msg_entry.bind('<Return>', self._on_enter_pressed)
        
        # Send button
        ttk.Button(entry_row, text="Send",
                  command=self._on_send_clicked).pack(side="right", padx=(12, 0))
    
    def _bind_shortcuts(self):
        """Bind keyboard shortcuts."""
        self.root.bind('<Control-l>', lambda e: self.on_logout())
    
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
            self.refresh_pin_mute_buttons()
    
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
        
        # Get conversation labels
        labels = self.conv_manager.get_conversation_labels()
        
        # Update combobox values
        self.conv_combo['values'] = labels
        
        # Set current selection
        try:
            idx = self.conv_manager.conversation_ids.index(self.conv_manager.active_cid)
            self.conv_combo.current(idx)
        except (ValueError, tk.TclError):
            pass

        self.refresh_pin_mute_buttons()

    def refresh_pin_mute_buttons(self):
        """Refresh pin/mute button states based on active conversation."""
        if not self.pin_btn or not self.mute_btn:
            return
        cid = self.conv_manager.active_cid
        conv = self.conv_manager.get_conversation(cid)
        if cid == "global" or conv is None:
            self.pin_btn.config(state="disabled", text="Pin")
            self.mute_btn.config(state="disabled", text="Mute")
            return
        self.pin_btn.config(state="normal", text=("Unpin" if getattr(conv, "pinned", False) else "Pin"))
        self.mute_btn.config(state="normal", text=("Unmute" if getattr(conv, "muted", False) else "Mute"))
    
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
        
        # Clear existing messages
        if hasattr(self.messages_container, 'content') and self.messages_container.content:
            for w in list(self.messages_container.content.winfo_children()):
                w.destroy()
        self.message_cards = []
        
        # Get active conversation
        conv = self.conv_manager.get_active_conversation()
        if not conv:
            return
        
        # Render messages
        for item in conv.items:
            card = self._create_message_card(item)
            card.pack(fill="x", pady=4)
            self.message_cards.append(card)
        
        if hasattr(self.messages_container, 'scroll_to_bottom'):
            self.messages_container.scroll_to_bottom()
    
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
