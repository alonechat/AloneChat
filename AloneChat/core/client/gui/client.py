"""
Modern GUI client for AloneChat using SSE for real-time messaging.

Features:
- Server-Sent Events (SSE) for efficient real-time communication
- Clean, modern interface using ttk (themed tkinter widgets)
- Responsive layout that adapts to window size
- Modern card-based design with proper spacing
- Smooth scrolling and message history
- Keyboard shortcuts for power users
- High-DPI support for modern displays
"""

import gc
import logging
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional, List, Dict, Any

import darkdetect
import sv_ttk

from AloneChat.core.client.client_base import Client
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT
from .components import WinUI3MessageCard
from .controllers.auth_view import AuthView
from .controllers.chat_view import ChatView
from .controllers.search_dialog import SearchDialog
from .controllers.user_list_dialog import UserListDialog
from .controllers.friend_list_dialog import FriendListDialog
from .controllers.add_friend_dialog import AddFriendDialog
from .controllers.friend_request_dialog import FriendRequestDialog
from .services.async_service import AsyncService
from .services.conversation_manager import ConversationManager, MessageItem, ReplyContext
from .services.event_service import APIClient, EventService, EventServiceConfig, ChatMessage, MessageType
from .services.persistence_service import PersistenceService
from .services.search_service import SearchService

logger = logging.getLogger(__name__)


class GUIClient(Client):
    """
    Modern GUI client with SSE-based real-time messaging.
    
    Features:
    - SSE streaming via /events endpoint
    - Clean, modern interface
    - Responsive layout
    - Automatic reconnection
    """
    
    def __init__(self, api_host: str = DEFAULT_HOST, api_port: int = DEFAULT_API_PORT):
        super().__init__(api_host, api_port)
        
        self._api_host = api_host
        self._api_port = api_port
        
        self._api_client = APIClient(f"http://{api_host}:{api_port}")
        self._event_service: Optional[EventService] = None
        
        self._username = ""
        self._token: Optional[str] = None
        self._running = False
        self._closing = False
        
        self.root: Optional[tk.Tk] = None
        self._auth_view: Optional[AuthView] = None
        self._chat_view: Optional[ChatView] = None
        self._search_dialog: Optional[SearchDialog] = None
        self._user_list_dialog: Optional[UserListDialog] = None
        self._friend_list_dialog: Optional[FriendListDialog] = None
        self._add_friend_dialog: Optional[AddFriendDialog] = None
        self._friend_request_dialog: Optional[FriendRequestDialog] = None
        
        self._async_service = AsyncService()
        self._conv_manager = ConversationManager()
        self._search_service = SearchService()
        self._persistence = PersistenceService()
        
        self._reply_ctx: Optional[ReplyContext] = None
    
    def run(self) -> None:
        """Start the GUI client."""
        self.root = tk.Tk()
        self.root.title("AloneChat")
        self.root.geometry("1200x640")
        self.root.minsize(800, 500)
        
        try:
            self.root.iconphoto(False, tk.PhotoImage(file="../../../../assets/icon.jpg"))
        except Exception:
            pass
        
        sv_ttk.set_theme(darkdetect.theme())
        
        self._async_service.start()
        
        self._show_auth_view()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self.root.mainloop()
    
    def _ui_alive(self) -> bool:
        """Check if UI is still alive."""
        return bool(self.root) and bool(self.root.winfo_exists()) and not self._closing
    
    def _clear_view(self) -> None:
        """Clear current view."""
        if self._auth_view:
            self._auth_view.hide()
            self._auth_view = None
        if self._chat_view:
            self._chat_view.hide()
            self._chat_view = None
        if self._search_dialog:
            self._search_dialog.hide()
            self._search_dialog = None
        
        self._search_service.clear()
    
    def _show_auth_view(self) -> None:
        """Show authentication view."""
        self._clear_view()
        self._auth_view = AuthView(
            self.root,
            on_login=self._handle_login_request,
            on_register=self._handle_register_request,
            on_server_settings_changed=self._handle_server_settings_changed,
            default_api_host=self._api_host,
            default_api_port=self._api_port
        )
        self._auth_view.show()
    
    def _show_chat_view(self) -> None:
        """Show chat view."""
        self._clear_view()
        self._running = True
        
        self._chat_view = ChatView(
            self.root,
            username=self._username,
            conversation_manager=self._conv_manager,
            on_send=self._handle_send,
            on_select_conversation=self._handle_switch_conversation,
            on_reply=self._handle_begin_reply,
            on_clear_reply=self._handle_clear_reply,
            on_export_md=self._handle_export_md,
            on_export_json=self._handle_export_json,
            on_export_logs=self._handle_export_logs,
            on_logout=self._handle_logout,
            on_set_status=self._handle_set_status,
            on_refresh_users=self._handle_refresh_users,
            on_user_list=self._handle_user_list,
            on_friends=self._handle_friends,
            on_friend_requests=self._handle_friend_requests
        )
        self._chat_view.show()
        
        self.root.bind('<Control-f>', lambda e: self._open_search())
        
        self._chat_view._status_bar.set_connecting()
        
        self._start_event_service()
        
        self._start_status_refresh_timer()
        
        self._show_onboarding()
        
        self._chat_view.render_conversation()
    
    def _start_event_service(self) -> None:
        """Start the SSE event service."""
        if not self._token:
            return
        
        config = EventServiceConfig(
            base_url=f"http://{self._api_host}:{self._api_port}",
            token=self._token,
            reconnect_delay=1.0,
            max_reconnect_delay=30.0,
            heartbeat_timeout=60.0,
            buffer_size=100
        )
        
        self._event_service = EventService(config)
        self._event_service.set_callbacks(
            on_message=self._on_sse_message,
            on_connected=self._on_sse_connected,
            on_disconnected=self._on_sse_disconnected,
            on_error=self._on_sse_error
        )
        
        self._async_service.run_async(self._event_service.start())
    
    def _on_sse_message(self, message: ChatMessage) -> None:
        """Handle incoming SSE message."""
        if message.sender == self._username:
            return
        
        if message.is_system():
            self._handle_system_message(message)
            return
        
        cid, actual_sender, body = self._conv_manager.process_received_message(
            message.sender, message.content, self._username
        )
        
        if not cid:
            return
        
        item = MessageItem.create(actual_sender, body, is_self=False)
        is_active = (cid == self._conv_manager.active_cid)
        self._conv_manager.add_message(cid, item, is_active=is_active)
        
        if self._ui_alive():
            if is_active:
                self.root.after(0, lambda i=item: self._add_message_to_ui(i))
            else:
                self.root.after(0, self._chat_view.refresh_conversation_list)
    
    def _handle_system_message(self, message: ChatMessage) -> None:
        """Handle system messages (join/leave/etc)."""
        if message.msg_type == MessageType.JOIN:
            content = f"{message.sender} joined the chat"
        elif message.msg_type == MessageType.LEAVE:
            content = f"{message.sender} left the chat"
        else:
            content = message.content
        
        item = MessageItem.create("System", content, is_system=True)
        self._conv_manager.add_message("global", item, is_active=True)
        
        if self._ui_alive() and self._conv_manager.active_cid == "global":
            self.root.after(0, lambda i=item: self._add_message_to_ui(i))
    
    def _on_sse_connected(self) -> None:
        """Handle SSE connection established."""
        logger.info("SSE connected")
        if self._ui_alive():
            self.root.after(0, lambda: self._chat_view.set_connection_status(True))
    
    def _on_sse_disconnected(self) -> None:
        """Handle SSE connection lost."""
        logger.warning("SSE disconnected")
        if self._ui_alive():
            self.root.after(0, lambda: self._chat_view.set_connection_status(False, "Reconnecting..."))
    
    def _on_sse_error(self, error: Exception) -> None:
        """Handle SSE error."""
        logger.error("SSE error: %s", error)
    
    def _start_status_refresh_timer(self) -> None:
        """Start periodic user status refresh timer."""
        self._refresh_status()
    
    def _refresh_status(self) -> None:
        """Refresh user status periodically."""
        if not self._running or self._closing:
            return
        
        self._async_service.run_async(self._do_refresh_all_users())
        
        if self._ui_alive():
            self.root.after(15000, self._refresh_status)
    
    async def _do_refresh_all_users(self) -> None:
        """Refresh all users status from API."""
        try:
            result = await self._api_client.get_all_users()
            if result and self._ui_alive():
                users = result.get("users", [])
                
                for user_data in users:
                    if isinstance(user_data, dict):
                        user_id = user_data.get("user_id")
                        status = user_data.get("status", "offline")
                        is_online = user_data.get("is_online", False)
                        
                        if user_id and user_id != self._username:
                            self._conv_manager.update_partner_status(user_id, is_online, status)
                
                self.root.after(0, self._chat_view.refresh_conversation_list)
        except Exception as e:
            logger.debug("Failed to refresh user status: %s", e)
    
    def _show_onboarding(self) -> None:
        """Show one-time onboarding tips."""
        state = self._persistence.load_state_sync()
        if not state.get("onboarding_shown", False):
            self._add_system_message(
                "Tips:\n"
                "• Click Send to send messages\n"
                "• If a message fails, click the red status to retry\n"
                "• Use Export to open your local chat logs folder\n"
                "• Need help? Contact to us with tonytao2022 @outlook.com | zhang.chenyun @outlook.com"
            )
            state["onboarding_shown"] = True
            self._persistence.save_state_sync(state)
    
    def _handle_login_request(self, username: str, password: str) -> None:
        """Handle login request from auth view."""
        if not username or not password:
            messagebox.showwarning("Login", "Please enter username and password")
            return
        
        self._async_service.run_async(self._do_login(username, password))
    
    async def _do_login(self, username: str, password: str) -> None:
        """Perform login."""
        try:
            response = await self._api_client.login(username, password)
            
            if response.get("success"):
                self._username = username
                self._token = response.get("token")
                
                if self._ui_alive():
                    self.root.after(0, self._show_chat_view)
            else:
                error = response.get("message", "Login failed")
                if self._ui_alive():
                    self.root.after(0, lambda: messagebox.showerror("Login Failed", error))
        except Exception as e:
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    def _handle_register_request(self, username: str, password: str) -> None:
        """Handle register request from auth view."""
        if not username or not password:
            messagebox.showwarning("Register", "Please enter username and password")
            return
        
        self._async_service.run_async(self._do_register(username, password))
    
    async def _do_register(self, username: str, password: str) -> None:
        """Perform registration."""
        try:
            response = await self._api_client.register(username, password)
            
            if response.get("success"):
                if self._ui_alive():
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Success", "Account created! Please sign in."
                    ))
            else:
                error = response.get("message", "Registration failed")
                if self._ui_alive():
                    self.root.after(0, lambda: messagebox.showerror("Registration Failed", error))
        except Exception as e:
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    def _handle_server_settings_changed(self, api_host: str, api_port: int) -> None:
        """Handle server settings change from auth view."""
        self._api_host = api_host
        self._api_port = api_port
        self._api_client = APIClient(f"http://{api_host}:{api_port}")
        print(f"Server settings updated: API at {api_host}:{api_port}")
    
    def _handle_send(self, content: str) -> None:
        """Handle send message request."""
        if not content.strip():
            return
        
        if self._reply_ctx:
            quote = self._reply_ctx.get_snippet(120)
            content = f"> Reply to {self._reply_ctx.sender} ({self._reply_ctx.timestamp}): {quote}\n{content}"
        
        target_cid = self._conv_manager.active_cid
        payload, cid = self._conv_manager.prepare_send_payload(content, target_cid)
        
        item = MessageItem.create(self._username, content, is_self=True, status="Sending…")
        self._conv_manager.add_message(cid, item, is_active=(cid == target_cid))
        
        if cid == target_cid:
            card = self._chat_view.add_message_card(item)
            self._search_service.set_message_cards(self._chat_view.get_message_cards())
        else:
            card = None
            self._chat_view.refresh_conversation_list()
        
        self._chat_view.clear_message_entry()
        self._handle_clear_reply()
        
        target = cid if cid != "global" else None
        self._async_service.run_async(self._send_message(payload, item, card, target))
    
    async def _send_message(
        self,
        payload: str,
        item: MessageItem,
        card: Optional[WinUI3MessageCard],
        target: Optional[str] = None
    ) -> None:
        """Send message via API."""
        try:
            response = await self._api_client.send_message(payload, target)
            
            if response.get("success"):
                item.status = "✓"
                if card and self._ui_alive():
                    self.root.after(0, lambda: card.update_status("✓"))
            else:
                error = response.get("message", "Failed to send")
                item.status = f"Failed: {error}"
                if card and self._ui_alive():
                    self.root.after(0, lambda: card.update_status(
                        "Failed — click to retry",
                        is_error=True,
                        on_retry=lambda: self._retry_send(payload, item, card, target)
                    ))
        except Exception as e:
            item.status = f"Error: {e}"
            if card and self._ui_alive():
                self.root.after(0, lambda: card.update_status(
                    "Failed — click to retry",
                    is_error=True,
                    on_retry=lambda: self._retry_send(payload, item, card, target)
                ))
    
    def _retry_send(
        self,
        payload: str,
        item: MessageItem,
        card: WinUI3MessageCard,
        target: Optional[str] = None
    ) -> None:
        """Retry a failed send."""
        item.status = "Sending…"
        card.update_status("Sending…", is_error=False)
        self._async_service.run_async(self._send_message(payload, item, card, target))
    
    def _handle_switch_conversation(self, cid: str) -> None:
        """Handle conversation switch."""
        self._conv_manager.switch_conversation(cid)
        self._chat_view.refresh_conversation_list()
        self._chat_view.render_conversation()
        self._search_service.set_message_cards(self._chat_view.get_message_cards())
    
    def _handle_begin_reply(self, sender: str, content: str, timestamp: str) -> None:
        """Handle reply request."""
        self._reply_ctx = ReplyContext(sender=sender, content=content, timestamp=timestamp)
        self._chat_view.show_reply_banner(self._reply_ctx)
    
    def _handle_clear_reply(self) -> None:
        """Clear reply context."""
        self._reply_ctx = None
        self._chat_view.hide_reply_banner()
    
    def _handle_export_md(self) -> None:
        """Export current conversation to Markdown."""
        conv = self._conv_manager.get_active_conversation()
        if not conv:
            return
        self._async_service.run_async(self._do_export_md(conv))
    
    async def _do_export_md(self, conv) -> None:
        """Perform Markdown export asynchronously."""
        path = await self._persistence.export_conversation_md(
            self._username, conv.cid, conv.name,
            [item.to_dict() for item in conv.items]
        )
        if path and self._ui_alive():
            self.root.after(0, self._open_logs_folder)
    
    def _handle_export_json(self) -> None:
        """Export current conversation to JSON."""
        conv = self._conv_manager.get_active_conversation()
        if not conv:
            return
        self._async_service.run_async(self._do_export_json(conv))
    
    async def _do_export_json(self, conv) -> None:
        """Perform JSON export asynchronously."""
        path = await self._persistence.export_conversation_json(
            self._username, conv.cid,
            [item.to_dict() for item in conv.items]
        )
        if path and self._ui_alive():
            self.root.after(0, self._open_logs_folder)
    
    def _handle_export_logs(self) -> None:
        """Open logs folder."""
        self._open_logs_folder()
    
    def _open_logs_folder(self) -> None:
        """Open logs folder in file explorer."""
        try:
            folder = os.path.abspath(self._persistence.log_dir)
            if os.name == "nt":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        except Exception as e:
            messagebox.showerror("Export", f"Failed to open logs folder: {e}")
    
    def _handle_logout(self) -> None:
        """Handle logout request."""
        self._running = False
        
        if self._event_service:
            self._async_service.run_async(self._event_service.stop())
        
        self._async_service.run_async(self._do_logout())
    
    async def _do_logout(self) -> None:
        """Perform logout."""
        try:
            await self._api_client.logout()
        except Exception:
            pass
        finally:
            if self._ui_alive():
                self.root.after(0, self._show_auth_view)
    
    def _handle_set_status(self, status: str) -> None:
        """Handle user status change."""
        self._async_service.run_async(self._do_set_status(status))
    
    async def _do_set_status(self, status: str) -> None:
        """Set user status via API."""
        try:
            await self._api_client.set_status(status)
        except Exception as e:
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showwarning("Status", f"Failed to set status: {e}"))
    
    def _handle_refresh_users(self) -> None:
        """Handle refresh users request."""
        self._async_service.run_async(self._do_refresh_users())
    
    async def _do_refresh_users(self) -> None:
        """Refresh online users from API."""
        try:
            result = await self._api_client.get_online_users()
            if result and self._ui_alive():
                users = result.get("users", [])
                for user_data in users:
                    user_id = user_data if isinstance(user_data, str) else user_data.get("user_id")
                    if user_id:
                        self._conv_manager.update_partner_status(user_id, True, "online")
                
                self.root.after(0, self._chat_view.refresh_conversation_list)
        except Exception as e:
            logger.warning("Failed to refresh users: %s", e)
    
    def _handle_user_list(self) -> None:
        """Handle user list button click."""
        if not self._user_list_dialog:
            self._user_list_dialog = UserListDialog(
                self.root,
                on_select_user=self._handle_select_user_from_list,
                on_refresh=self._handle_refresh_users_for_dialog
            )
        self._user_list_dialog.show()
        self._async_service.run_async(self._do_load_users_for_dialog())
    
    def _handle_select_user_from_list(self, user_id: str) -> None:
        """Handle selecting a user from the user list dialog."""
        conv = self._conv_manager.get_conversation(user_id)
        is_online = conv.partner_online if conv else False
        status = conv.partner_status if conv else "offline"
        
        self._conv_manager.create_private_conversation(
            user_id, user_id, is_online=is_online, status=status
        )
        self._conv_manager.switch_conversation(user_id)
        self._chat_view.refresh_conversation_list()
        self._chat_view.render_conversation()
    
    def _handle_refresh_users_for_dialog(self) -> None:
        """Handle refresh button in user list dialog."""
        self._async_service.run_async(self._do_load_users_for_dialog())
    
    async def _do_load_users_for_dialog(self) -> None:
        """Load all registered users from API and update dialog."""
        try:
            result = await self._api_client.get_all_users()
            if result and self._ui_alive():
                users = result.get("users", [])
                
                filtered_users = []
                for user_data in users:
                    if isinstance(user_data, dict):
                        user_id = user_data.get("user_id")
                        if user_id == self._username:
                            continue
                        
                        is_online = user_data.get("is_online", False)
                        status = user_data.get("status", "online" if is_online else "offline")
                        
                        if user_id:
                            self._conv_manager.update_partner_status(user_id, is_online, status)
                            filtered_users.append(user_data)
                
                if self._user_list_dialog:
                    self.root.after(0, lambda: self._user_list_dialog.set_users(filtered_users))
        except Exception as e:
            logger.warning("Failed to load users: %s", e)
    
    def _add_message_to_ui(self, item: MessageItem) -> None:
        """Add a message to the UI."""
        if not self._chat_view:
            return
        card = self._chat_view.add_message_card(item)
        self._search_service.set_message_cards(self._chat_view.get_message_cards())
        self._async_service.run_async(
            self._persistence.log_chat(self._username, item.sender, item.content)
        )
    
    def _add_system_message(self, content: str) -> None:
        """Add a system message."""
        item = MessageItem.create("System", content, is_system=True)
        self._conv_manager.add_message(self._conv_manager.active_cid, item, is_active=True)
        if self._chat_view:
            self._chat_view.add_message_card(item)
        self._async_service.run_async(
            self._persistence.log_chat(self._username, "System", content)
        )
    
    def _open_search(self) -> None:
        """Open search dialog."""
        if self._search_dialog and self._search_dialog.window and self._search_dialog.window.winfo_exists():
            self._search_dialog.window.lift()
            return
        
        self._search_dialog = SearchDialog(
            self.root,
            on_search=self._handle_search,
            on_next=self._handle_search_next,
            on_prev=self._handle_search_prev,
            on_close=self._handle_search_close
        )
        self._search_dialog.show()
    
    def _handle_search(self, query: str) -> int:
        """Handle search query."""
        count = self._search_service.search(query)
        return count
    
    def _handle_search_next(self) -> None:
        """Go to next search result."""
        self._search_service.next_result()
        card = self._search_service.get_current_hit_widget()
        if card and self._chat_view:
            self._chat_view.scroll_to_card(card)
    
    def _handle_search_prev(self) -> None:
        """Go to previous search result."""
        self._search_service.prev_result()
        card = self._search_service.get_current_hit_widget()
        if card and self._chat_view:
            self._chat_view.scroll_to_card(card)
    
    def _handle_search_close(self) -> None:
        """Close search dialog."""
        self._search_service.clear()
        self._search_dialog = None
    
    def _handle_friends(self) -> None:
        """Handle friends button click."""
        if not self._friend_list_dialog:
            self._friend_list_dialog = FriendListDialog(
                self.root,
                on_start_chat=self._handle_start_chat_with_friend,
                on_remove_friend=self._handle_remove_friend,
                on_set_remark=self._handle_set_remark,
                on_refresh=self._handle_refresh_friends,
                on_add_friend=self._handle_add_friend_dialog
            )
        self._friend_list_dialog.show()
        self._async_service.run_async(self._do_load_friends())
    
    def _handle_friend_requests(self) -> None:
        """Handle friend requests button click."""
        if not self._friend_request_dialog:
            self._friend_request_dialog = FriendRequestDialog(
                self.root,
                on_accept=self._handle_accept_friend_request,
                on_reject=self._handle_reject_friend_request,
                on_refresh=self._handle_refresh_friend_requests
            )
        self._friend_request_dialog.show()
        self._async_service.run_async(self._do_load_friend_requests())
    
    def _handle_add_friend_dialog(self) -> None:
        """Open add friend dialog."""
        if not self._add_friend_dialog:
            self._add_friend_dialog = AddFriendDialog(
                self.root,
                on_search=self._handle_search_users,
                on_send_request=self._handle_send_friend_request,
                current_user=self._username
            )
        self._add_friend_dialog.show()
    
    def _handle_start_chat_with_friend(self, friend_id: str) -> None:
        """Start chat with a friend."""
        self._conv_manager.create_private_conversation(
            friend_id, friend_id, is_online=True, status="online"
        )
        self._conv_manager.switch_conversation(friend_id)
        self._chat_view.refresh_conversation_list()
        self._chat_view.render_conversation()
    
    def _handle_remove_friend(self, friend_id: str) -> None:
        """Remove a friend."""
        self._async_service.run_async(self._do_remove_friend(friend_id))
    
    def _handle_set_remark(self, friend_id: str, remark: str) -> None:
        """Set remark for a friend."""
        self._async_service.run_async(self._do_set_remark(friend_id, remark))
    
    def _handle_refresh_friends(self) -> None:
        """Refresh friends list."""
        self._async_service.run_async(self._do_load_friends())
    
    def _handle_refresh_friend_requests(self) -> None:
        """Refresh friend requests."""
        self._async_service.run_async(self._do_load_friend_requests())
    
    def _handle_search_users(self, query: str, callback: Callable[[List[Dict[str, Any]]], None]) -> None:
        """Search for users asynchronously."""
        self._async_service.run_async(self._do_search_users_with_callback(query, callback))
    
    async def _do_search_users_with_callback(self, query: str, callback: Callable[[List[Dict[str, Any]]], None]) -> None:
        """Search users from API and call callback with results."""
        try:
            logger.debug("Searching users with query: %s", query)
            result = await self._api_client.search_users(query)
            logger.debug("Search result: %s", result)
            users = result.get("users", []) if result else []
            logger.debug("Users found: %d", len(users))
            if self._ui_alive():
                self.root.after(0, lambda: callback(users))
        except Exception as e:
            logger.warning("Failed to search users: %s", e)
            if self._ui_alive():
                self.root.after(0, lambda: callback([]))
    
    def _handle_send_friend_request(self, to_user: str, message: str) -> None:
        """Send friend request."""
        self._async_service.run_async(self._do_send_friend_request(to_user, message))
    
    def _handle_accept_friend_request(self, request_id: str) -> None:
        """Accept friend request."""
        self._async_service.run_async(self._do_accept_friend_request(request_id))
    
    def _handle_reject_friend_request(self, request_id: str) -> None:
        """Reject friend request."""
        self._async_service.run_async(self._do_reject_friend_request(request_id))
    
    async def _do_load_friends(self) -> None:
        """Load friends from API."""
        try:
            result = await self._api_client.get_friends()
            if result and self._ui_alive():
                friends = result.get("friends", [])
                if self._friend_list_dialog:
                    self.root.after(0, lambda: self._friend_list_dialog.set_friends(friends))
                
                for friend in friends:
                    friend_id = friend.get("user_id")
                    remark = friend.get("remark", "")
                    is_online = friend.get("is_online", False)
                    status = friend.get("status", "offline")
                    
                    if friend_id:
                        self._conv_manager.update_partner_status(friend_id, is_online, status)
                        self._conv_manager.update_friend_status(friend_id, True, remark)
        except Exception as e:
            logger.warning("Failed to load friends: %s", e)
    
    async def _do_load_friend_requests(self) -> None:
        """Load friend requests from API."""
        try:
            result = await self._api_client.get_pending_friend_requests()
            if result and self._ui_alive():
                requests = result.get("requests", [])
                if self._friend_request_dialog:
                    self.root.after(0, lambda: self._friend_request_dialog.set_requests(requests))
        except Exception as e:
            logger.warning("Failed to load friend requests: %s", e)
    
    async def _do_search_users(self, query: str) -> List[Dict[str, Any]]:
        """Search users from API."""
        try:
            result = await self._api_client.search_users(query)
            if result:
                return result.get("users", [])
        except Exception as e:
            logger.warning("Failed to search users: %s", e)
        return []
    
    async def _do_send_friend_request(self, to_user: str, message: str) -> None:
        """Send friend request via API."""
        try:
            logger.debug("Sending friend request to: %s, token: %s", to_user, self._api_client.token[:20] if self._api_client.token else "None")
            result = await self._api_client.send_friend_request(to_user, message)
            logger.debug("Friend request result: %s", result)
            if self._ui_alive():
                if result.get("success"):
                    self.root.after(0, lambda: messagebox.showinfo("Friend Request", "Friend request sent!"))
                else:
                    error = result.get("error", result.get("message", "Failed to send request"))
                    self.root.after(0, lambda: messagebox.showwarning("Friend Request", error))
        except Exception as e:
            logger.error("Send friend request error: %s", e)
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    async def _do_accept_friend_request(self, request_id: str) -> None:
        """Accept friend request via API."""
        try:
            result = await self._api_client.accept_friend_request(request_id)
            if self._ui_alive():
                if result.get("success"):
                    self.root.after(0, lambda: messagebox.showinfo("Friend Request", "Friend request accepted!"))
                    self._async_service.run_async(self._do_load_friends())
                    self._async_service.run_async(self._do_load_friend_requests())
                else:
                    error = result.get("error", "Failed to accept request")
                    self.root.after(0, lambda: messagebox.showwarning("Friend Request", error))
        except Exception as e:
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    async def _do_reject_friend_request(self, request_id: str) -> None:
        """Reject friend request via API."""
        try:
            result = await self._api_client.reject_friend_request(request_id)
            if self._ui_alive():
                if result.get("success"):
                    self._async_service.run_async(self._do_load_friend_requests())
                else:
                    error = result.get("error", "Failed to reject request")
                    self.root.after(0, lambda: messagebox.showwarning("Friend Request", error))
        except Exception as e:
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    async def _do_remove_friend(self, friend_id: str) -> None:
        """Remove friend via API."""
        try:
            result = await self._api_client.remove_friend(friend_id)
            if self._ui_alive():
                if result.get("success"):
                    self.root.after(0, lambda: messagebox.showinfo("Friend", "Friend removed."))
                    self._conv_manager.update_friend_status(friend_id, False, "")
                    self._async_service.run_async(self._do_load_friends())
                else:
                    error = result.get("error", "Failed to remove friend")
                    self.root.after(0, lambda: messagebox.showwarning("Friend", error))
        except Exception as e:
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    async def _do_set_remark(self, friend_id: str, remark: str) -> None:
        """Set friend remark via API."""
        try:
            result = await self._api_client.set_friend_remark(friend_id, remark)
            if self._ui_alive():
                if result.get("success"):
                    self._conv_manager.update_friend_status(friend_id, True, remark)
                    self._async_service.run_async(self._do_load_friends())
                else:
                    error = result.get("error", "Failed to set remark")
                    self.root.after(0, lambda: messagebox.showwarning("Remark", error))
        except Exception as e:
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    def _on_close(self) -> None:
        """Handle window close."""
        self._closing = True
        self._running = False
        
        if self._event_service:
            self._async_service.run_async(self._event_service.stop())
        
        self._persistence.flush_buffers_sync()
        
        self._async_service.run_async(self._api_client.close())
        
        self._async_service.stop()
        
        try:
            for name in ("username_var", "password_var", "server_var", "port_var",
                        "status_var", "input_var", "search_var"):
                if hasattr(self, name):
                    setattr(self, name, None)
            gc.collect()
        except Exception:
            pass
        
        try:
            if self.root:
                self.root.quit()
                self.root.destroy()
        except Exception:
            pass
        finally:
            self.root = None


__all__ = ['GUIClient']
