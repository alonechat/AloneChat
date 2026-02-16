"""
Chat view with conversations, messages, and input.
Uses modular components for better maintainability.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, List, TYPE_CHECKING

from ..components import WinUI3ScrollableFrame, WinUI3MessageCard
from ..models.data import MessageItem, ReplyContext
from ..services.conversation_manager import ConversationManager
from .header import HeaderBar
from .sidebar import Sidebar
from .message_area import MessageArea
from .input_area import InputArea
from .status_bar import StatusBar

if TYPE_CHECKING:
    pass


class ChatView:
    """Main chat view with sidebar, message area, and status bar."""
    
    def __init__(
        self,
        root: tk.Tk,
        username: str,
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
        on_user_list: Optional[Callable[[], None]] = None,
        on_open_private: Optional[Callable[[str], None]] = None,
        on_friends_refresh: Optional[Callable[[], None]] = None,
        on_friend_request: Optional[Callable[[str], None]] = None,
        on_friend_accept: Optional[Callable[[str], None]] = None,
        on_friend_reject: Optional[Callable[[str], None]] = None
    ):
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

        self.on_open_private = on_open_private
        self.on_friends_refresh = on_friends_refresh
        self.on_friend_request = on_friend_request
        self.on_friend_accept = on_friend_accept
        self.on_friend_reject = on_friend_reject
        
        self.frame: Optional[ttk.Frame] = None
        self.main_pane: Optional[ttk.Frame] = None
        
        self._header: Optional[HeaderBar] = None
        self._sidebar: Optional[Sidebar] = None
        self._message_area: Optional[MessageArea] = None
        self._input_area: Optional[InputArea] = None
        self._status_bar: Optional[StatusBar] = None
    
    def show(self) -> None:
        """Display the chat view."""
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_columnconfigure(0, weight=1)
        
        self._build_header()
        self._build_main_pane()
        self._build_status_bar()
        self._bind_shortcuts()
    
    def hide(self) -> None:
        """Hide the chat view."""
        if self._header:
            self._header.destroy()
            self._header = None
        if self._sidebar:
            self._sidebar.destroy()
            self._sidebar = None
        if self._message_area:
            self._message_area.destroy()
            self._message_area = None
        if self._input_area:
            self._input_area.destroy()
            self._input_area = None
        if self._status_bar:
            self._status_bar.destroy()
            self._status_bar = None
        if self.main_pane:
            self.main_pane.destroy()
            self.main_pane = None
        self.frame = None
    
    def _build_header(self) -> None:
        """Build the header bar."""
        self._header = HeaderBar(
            self.root,
            username=self.username,
            on_logout=self.on_logout,
            on_export_logs=self.on_export_logs,
            on_refresh_users=self.on_refresh_users,
            on_set_status=self.on_set_status
        )
        header_frame = self._header.build()
        header_frame.grid(row=0, column=0, sticky="ew")
    
    def _build_main_pane(self) -> None:
        """Build the main content area."""
        self.main_pane = ttk.Frame(self.root)
        self.main_pane.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)
        self.main_pane.grid_rowconfigure(0, weight=1)
        self.main_pane.grid_columnconfigure(1, weight=1)
        
        self._build_sidebar()
        self._build_chat_area()
    
    def _build_sidebar(self) -> None:
        """Build the conversation sidebar."""
        self._sidebar = Sidebar(
            self.main_pane,
            conversation_manager=self.conv_manager,
            on_select_conversation=self.on_select_conversation,
            on_user_list=self.on_user_list,
            on_refresh_users=self.on_refresh_users,
            on_open_private=self.on_open_private,
            on_friends_refresh=self.on_friends_refresh,
            on_friend_request=self.on_friend_request,
            on_friend_accept=self.on_friend_accept,
            on_friend_reject=self.on_friend_reject,
        )
        self._sidebar.build().grid(row=0, column=0, sticky="ns")
    
    def _build_chat_area(self) -> None:
        """Build the chat message area."""
        right = ttk.Frame(self.main_pane)
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        
        self._message_area = MessageArea(
            right,
            conversation_manager=self.conv_manager,
            on_reply=self.on_reply
        )
        self._message_area.build().grid(row=0, column=0, sticky="nsew")
        
        self._input_area = InputArea(
            right,
            on_send=self.on_send,
            on_clear_reply=self.on_clear_reply
        )
        self._input_area.build().grid(row=1, column=0, sticky="ew", pady=(12, 0))
    
    def _build_status_bar(self) -> None:
        """Build the status bar at the bottom."""
        self._status_bar = StatusBar(self.root)
        self._status_bar.grid(row=2, column=0, sticky="ew")
    
    def _bind_shortcuts(self) -> None:
        """Bind keyboard shortcuts."""
        self.root.bind('<Control-l>', lambda e: self.on_logout())
    
    def refresh_conversation_list(self) -> None:
        """Refresh the conversation list display."""
        if self._sidebar:
            self._sidebar.refresh_conversation_list()
    
    def show_reply_banner(self, ctx: ReplyContext) -> None:
        """Show reply banner with context."""
        if self._input_area:
            self._input_area.show_reply_banner(ctx)
    
    def hide_reply_banner(self) -> None:
        """Hide the reply banner."""
        if self._input_area:
            self._input_area.hide_reply_banner()
    
    def clear_message_entry(self) -> None:
        """Clear the message entry field."""
        if self._input_area:
            self._input_area.clear_message_entry()
    
    def render_conversation(self) -> None:
        """Render the active conversation messages."""
        if self._message_area:
            self._message_area.render_conversation()
        if self._sidebar:
            self._sidebar.refresh_conversation_list()
    
    def add_message_card(self, item: MessageItem) -> WinUI3MessageCard:
        """Add a single message card to the view."""
        if self._message_area:
            return self._message_area.add_message_card(item)
        return None
    
    def scroll_to_bottom(self) -> None:
        """Scroll to bottom of messages."""
        if self._message_area:
            self._message_area.scroll_to_bottom()
    
    def scroll_to_card(self, card: WinUI3MessageCard) -> None:
        """Scroll to a specific message card."""
        if self._message_area:
            self._message_area.scroll_to_card(card)
    
    def get_message_cards(self) -> List[WinUI3MessageCard]:
        """Get all message cards in current view."""
        if self._message_area:
            return self._message_area.get_message_cards()
        return []
    
    def update_partner_status(
        self,
        partner_id: str,
        is_online: bool,
        status: str
    ) -> None:
        """Update partner status display."""
        if self._sidebar:
            self._sidebar.update_partner_status(partner_id, is_online, status)
    
    def set_connection_status(self, connected: bool, message: Optional[str] = None) -> None:
        """Set connection status in the status bar."""
        if self._status_bar:
            self._status_bar.set_connected(connected, message)
    
    def set_status_message(self, message: str, color: Optional[str] = None) -> None:
        """Set a custom status message in the status bar."""
        if self._status_bar:
            self._status_bar.set_status(message, color)



    def update_friends_data(self, friends=None, incoming=None, outgoing=None, users=None) -> None:
        """Update friends + users UI if available."""
        if not self._sidebar:
            return

        # Friends + requests
        if hasattr(self._sidebar, "set_friends_data"):
            try:
                self._sidebar.set_friends_data(friends=friends, incoming=incoming, outgoing=outgoing)
            except Exception:
                pass

        # All users list inside Friends tab
        if users is not None and hasattr(self._sidebar, "set_users_data"):
            try:
                self._sidebar.set_users_data(users=users)
            except Exception:
                pass

__all__ = ['ChatView']
