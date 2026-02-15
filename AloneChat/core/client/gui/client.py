"""
Modern, simplified GUI client for AloneChat with excellent user experience.

Features:
- Clean, modern interface using ttk (themed tkinter widgets)
- Responsive layout that adapts to window size
- Proper bounds management - no out-of-window elements
- Simple, intuitive user interactions
- Modern card-based design with proper spacing
- Smooth scrolling and message history
- Keyboard shortcuts for power users
- Accessible design with proper contrast
- High-DPI support for modern displays
"""

import asyncio
import gc
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Optional

# noinspection PyUnusedImports
import darkdetect
import sv_ttk

from AloneChat.api.client import AloneChatAPIClient
from AloneChat.core.client.client_base import Client
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT
from .components import WinUI3MessageCard
from .controllers.auth_view import AuthView
from .controllers.chat_view import ChatView
from .controllers.contacts_dialog import ContactsDialog
from .controllers.search_dialog import SearchDialog
from .models.data import MessageItem, ReplyContext
from .services import ConversationManager, SearchService, PersistenceService, AsyncService


# DPI awareness disabled - letting Windows auto-scale for better compatibility
# If you want crisp rendering on high-DPI, consider using DPI awareness with proper scaling

class GUIClient(Client):
    """
    Simplified, modern GUI client with excellent UX.
    
    Features:
    - Clean, modern interface
    - Proper bounds management
    - Simple, intuitive interactions
    - Responsive layout
    """
    
    def __init__(self, api_host: str = DEFAULT_HOST, api_port: int = DEFAULT_API_PORT):
        super().__init__(api_host, api_port)
        
        # API configuration
        self._api_host = api_host
        self._api_port = api_port
        
        # API client
        self._api_client = AloneChatAPIClient(api_host, api_port)
        
        # State
        self._username = ""
        self._token: Optional[str] = None
        self._running = False
        self._closing = False
        
        # UI
        self.root: Optional[tk.Tk] = None
        self._auth_view: Optional[AuthView] = None
        self._chat_view: Optional[ChatView] = None
        self._search_dialog: Optional[SearchDialog] = None
        self._contacts_dialog: Optional[ContactsDialog] = None
        
        # Services
        self._async_service = AsyncService()
        self._conv_manager = ConversationManager()
        self._search_service = SearchService()
        self._persistence = PersistenceService()
        
        # Reply context
        self._reply_ctx: Optional[ReplyContext] = None
        
        # Poll future for cancellation
        self._poll_future = None

        # DM history loading guard (prevents "flash blank" when switching chats)
        self._history_req_seq: int = 0
    
    # ==================== Lifecycle ====================
    
    def run(self):
        """Start the GUI client."""
        # Create main window
        self.root = tk.Tk()
        self.root.title("AloneChat")
        self.root.geometry("1200x640")
        self.root.minsize(800, 500)
        
        # Apply sv_ttk theme (Sun Valley Windows 11 theme) - handles DPI automatically
        sv_ttk.set_theme(darkdetect.theme())
        # self.set_title_bar_color(self.root)

        # Enable DPI awareness for sharp rendering on high-DPI displays
        # Note: sv_ttk uses image-based assets; Windows handles scaling automatically
        # noinspection PyUnresolvedReferences
        # ctypes.windll.shcore.SetProcessDpiAwareness(0)
        
        # Setup async
        self._async_service.start()
        
        # Show auth view
        self._show_auth_view()
        
        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Start
        self.root.mainloop()
    
    def _ui_alive(self) -> bool:
        """Check if UI is still alive."""
        return bool(self.root) and bool(self.root.winfo_exists()) and not self._closing
    
    def _clear_view(self):
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
        if self._contacts_dialog:
            self._contacts_dialog.hide()
            self._contacts_dialog = None
        
        self._search_service.clear()
    
    # ==================== Views ====================
    
    def _show_auth_view(self):
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
    
    def _show_chat_view(self):
        """Show chat view."""
        self._clear_view()
        self._running = True
        
        self._chat_view = ChatView(
            self.root,
            username=self._username,
            conversation_manager=self._conv_manager,
            on_send=self._handle_send,
            on_new_conversation=self._handle_new_conversation,
            on_open_contacts=self._open_contacts,
            on_select_conversation=self._handle_switch_conversation,
            on_toggle_pin=self._toggle_pin_active,
            on_toggle_mute=self._toggle_mute_active,
            on_reply=self._handle_begin_reply,
            on_clear_reply=self._handle_clear_reply,
            on_export_md=self._handle_export_md,
            on_export_json=self._handle_export_json,
            on_export_logs=self._handle_export_logs,
            on_logout=self._handle_logout
        )
        self._chat_view.show()
        
        # Bind search shortcut
        self.root.bind('<Control-f>', lambda e: self._open_search())
        
        # Start polling
        self._poll_future = self._async_service.run_async(self._poll_messages())

        # Sync conversations from server (DM list)
        self._async_service.run_async(self._sync_conversations_from_server())
        
        # Show onboarding if first time
        self._show_onboarding()
        
        # Render conversation
        self._chat_view.render_conversation()

    # ==================== Contacts / Friends ====================

    def _open_contacts(self):
        """Open contacts dialog (friends + incoming requests)."""
        if not self.root or not self._ui_alive():
            return

        if self._contacts_dialog and self._contacts_dialog.window and self._contacts_dialog.window.winfo_exists():
            self._contacts_dialog.window.lift()
        else:
            self._contacts_dialog = ContactsDialog(
                self.root,
                on_refresh=self._refresh_contacts,
                on_start_chat=self._start_chat_with_friend,
                on_send_request=self._send_friend_request,
                on_search_users=self._search_users,
                on_accept=self._accept_friend_request,
                on_reject=self._reject_friend_request,
            )
            self._contacts_dialog.show()

        self._refresh_contacts()

    def _refresh_contacts(self):
        """Refresh friends + requests from server."""
        if not self._token:
            return
        if self._contacts_dialog:
            self._contacts_dialog.set_status("Refreshing…")
        self._async_service.run_async(self._do_refresh_contacts())

    def _search_users(self, query: str):
        if not self._token:
            return
        if self._contacts_dialog:
            self._contacts_dialog.set_status("Searching…")
        self._async_service.run_async(self._do_search_users(query))

    async def _do_search_users(self, query: str):
        try:
            resp = await self._api_client.list_users(q=(query or "").strip(), limit=50)
            users = []
            if resp.get("success"):
                users = [u for u in (resp.get("users") or []) if isinstance(u, dict)]
            if self._ui_alive() and self._contacts_dialog:
                self.root.after(0, lambda: (
                    self._contacts_dialog.set_search_results(users),
                    self._contacts_dialog.set_status("")
                ))
        except Exception as e:
            if self._ui_alive() and self._contacts_dialog:
                self.root.after(0, lambda: self._contacts_dialog and self._contacts_dialog.set_status(f"Error: {e}"))

    async def _do_refresh_contacts(self):
        try:
            friends_resp = await self._api_client.list_friends()
            req_resp = await self._api_client.incoming_friend_requests()
            out_resp = await self._api_client.outgoing_friend_requests()
            friends = []
            if friends_resp.get("success"):
                friends = [x.get("username") for x in friends_resp.get("friends", []) if isinstance(x, dict)]
            requests = []
            if req_resp.get("success"):
                requests = [r for r in (req_resp.get("requests") or []) if isinstance(r, dict)]
            outgoing = []
            if out_resp.get("success"):
                outgoing = [r for r in (out_resp.get("requests") or []) if isinstance(r, dict)]

            pending_incoming = sum(1 for r in requests if str(r.get("status", "pending")).lower() == "pending")

            if self._ui_alive() and self._contacts_dialog:
                def update():
                    if not self._contacts_dialog:
                        return
                    self._contacts_dialog.set_friends(friends)
                    self._contacts_dialog.set_incoming_requests(requests)
                    self._contacts_dialog.set_outgoing_requests(outgoing)
                    self._contacts_dialog.set_status("")
                    # Update badge on main chat view button.
                    if self._chat_view:
                        self._chat_view.set_contacts_badge(pending_incoming)
                self.root.after(0, update)
        except Exception as e:
            if self._ui_alive() and self._contacts_dialog:
                self.root.after(0, lambda: self._contacts_dialog and self._contacts_dialog.set_status(f"Error: {e}"))

    def _send_friend_request(self, to_username: str, message: str):
        if not self._token:
            return
        if self._contacts_dialog:
            self._contacts_dialog.set_status("Sending request…")
        self._async_service.run_async(self._do_send_friend_request(to_username, message))

    async def _do_send_friend_request(self, to_username: str, message: str):
        resp = await self._api_client.send_friend_request(to_username, message)
        if self._ui_alive() and self._contacts_dialog:
            def done():
                if self._contacts_dialog:
                    self._contacts_dialog.set_status(resp.get("message", ""))
            self.root.after(0, done)
        # Refresh lists so "Sent" tab updates immediately.
        if self._ui_alive():
            self.root.after(0, self._refresh_contacts)

    def _accept_friend_request(self, request_id: int):
        if self._contacts_dialog:
            self._contacts_dialog.set_status("Accepting…")
        self._async_service.run_async(self._do_accept_friend_request(request_id))

    async def _do_accept_friend_request(self, request_id: int):
        resp = await self._api_client.accept_friend_request(request_id)
        # refresh lists + sync conversations
        if self._ui_alive():
            self.root.after(0, self._refresh_contacts)
        await self._sync_conversations_from_server()
        if self._ui_alive() and self._contacts_dialog:
            self.root.after(0, lambda: self._contacts_dialog and self._contacts_dialog.set_status(resp.get("message", "")))

    def _reject_friend_request(self, request_id: int):
        if self._contacts_dialog:
            self._contacts_dialog.set_status("Rejecting…")
        self._async_service.run_async(self._do_reject_friend_request(request_id))

    async def _do_reject_friend_request(self, request_id: int):
        resp = await self._api_client.reject_friend_request(request_id)
        if self._ui_alive():
            self.root.after(0, self._refresh_contacts)
        if self._ui_alive() and self._contacts_dialog:
            self.root.after(0, lambda: self._contacts_dialog and self._contacts_dialog.set_status(resp.get("message", "")))

    def _start_chat_with_friend(self, friend_username: str):
        """Start / switch to a DM conversation with a friend."""
        u = (friend_username or "").strip()
        if not u:
            return
        self._conv_manager.create_conversation(u, name=u)
        self._handle_switch_conversation(u)
        if self._contacts_dialog:
            self._contacts_dialog.hide()
            self._contacts_dialog = None
    
    def _show_onboarding(self):
        """Show one-time onboarding tips."""
        state = self._persistence.load_state()
        if not state.get("onboarding_shown", False):
            self._add_system_message(
                "Tips:\n"
                "• Click Send to send messages\n"
                "• If a message fails, click the red status to retry\n"
                "• Open Contacts to add friends and approve requests\n"
            )
            state["onboarding_shown"] = True
            self._persistence.save_state(state)
    
    # ==================== Auth Handlers ====================
    
    def _handle_login_request(self, username: str, password: str):
        """Handle login request from auth view."""
        if not username or not password:
            messagebox.showwarning("Login", "Please enter username and password")
            return
        
        self._async_service.run_async(self._do_login(username, password))
    
    async def _do_login(self, username: str, password: str):
        """Perform login."""
        try:
            response = await self._api_client.login(username, password)
            
            if response.get("success"):
                self._username = username
                self._token = response.get("token")
                self._api_client.username = username
                self._api_client.token = self._token
                
                if self._ui_alive():
                    self.root.after(0, self._show_chat_view)
            else:
                error = response.get("message", "Login failed")
                if self._ui_alive():
                    self.root.after(0, lambda: messagebox.showerror("Login Failed", error))
        except Exception as e:
            if self._ui_alive():
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    def _handle_register_request(self, username: str, password: str):
        """Handle register request from auth view."""
        if not username or not password:
            messagebox.showwarning("Register", "Please enter username and password")
            return
        
        self._async_service.run_async(self._do_register(username, password))
    
    async def _do_register(self, username: str, password: str):
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
    
    def _handle_server_settings_changed(self, api_host: str, api_port: int):
        """Handle server settings change from auth view."""
        self._api_host = api_host
        self._api_port = api_port
        # Recreate API client with new settings
        self._api_client = AloneChatAPIClient(api_host, api_port)
        print(f"Server settings updated: API at {api_host}:{api_port}")
    
    # ==================== Chat Handlers ====================
    
    def _handle_send(self, content: str):
        """Handle send message request."""
        if not content.strip():
            return
        
        # Attach quote if replying
        if self._reply_ctx:
            quote = self._reply_ctx.get_snippet(120)
            content = f"> Reply to {self._reply_ctx.sender} ({self._reply_ctx.timestamp}): {quote}\n{content}"
        
        # Prepare payload
        target_cid = self._conv_manager.active_cid
        payload, cid = self._conv_manager.prepare_send_payload(content, target_cid)
        
        # Create local message
        item = MessageItem.create(self._username, content, is_self=True, status="Sending…")
        self._conv_manager.add_message(cid, item, is_active=(cid == target_cid))
        
        # Update UI if active conversation
        if cid == target_cid:
            card = self._chat_view.add_message_card(item)
            self._search_service.set_message_cards(self._chat_view.get_message_cards())
        else:
            card = None
            self._chat_view.refresh_conversation_list()
        
        # Clear input and reply
        self._chat_view.clear_message_entry()
        self._handle_clear_reply()
        
        # Send via API
        self._async_service.run_async(self._send_message(payload, item, card))
    
    async def _send_message(self, payload: str, item: MessageItem, 
                           card: Optional[WinUI3MessageCard]):
        """Send message via API."""
        try:
            response = await self._api_client.send_message(payload)
            
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
                        on_retry=lambda: self._retry_send(payload, item, card)
                    ))
        except Exception as e:
            item.status = f"Error: {e}"
            if card and self._ui_alive():
                self.root.after(0, lambda: card.update_status(
                    "Failed — click to retry",
                    is_error=True,
                    on_retry=lambda: self._retry_send(payload, item, card)
                ))
    
    def _retry_send(self, payload: str, item: MessageItem, card: WinUI3MessageCard):
        """Retry a failed send."""
        item.status = "Sending…"
        card.update_status("Sending…", is_error=False)
        self._async_service.run_async(self._send_message(payload, item, card))
    
    def _handle_new_conversation(self):
        """Handle new conversation request."""
        # Prefer starting chats via Contacts so friend-audit is visible.
        # Still allow manual entry for power users.
        to_user = simpledialog.askstring(
            "New Conversation",
            "Enter friend's username to chat with (non-friends can't DM until accepted):"
        )
        if not to_user:
            return
        to_user = to_user.strip()
        if not to_user:
            return
        
        self._conv_manager.create_conversation(to_user, name=to_user)
        self._handle_switch_conversation(to_user)
    
    def _handle_switch_conversation(self, cid: str):
        """Handle conversation switch."""
        self._conv_manager.switch_conversation(cid)
        self._chat_view.refresh_conversation_list()
        # Render immediately from local cache (prevents empty/blank UI), then refresh from server.
        # Pull history for DMs from server (SQLite) so the list behaves like WeChat.
        self._chat_view.render_conversation()
        if cid != "global":
            self._async_service.run_async(self._load_history_for(cid))
        self._search_service.set_message_cards(self._chat_view.get_message_cards())

    async def _sync_conversations_from_server(self):
        """Sync DM conversation list from server (based on stored messages)."""
        try:
            resp = await self._api_client.list_conversations(limit=50)
            if not resp.get("success"):
                return
            conversations = resp.get("conversations") or []
            # Update local conversation manager ordering + previews.
            self._conv_manager.sync_conversations(conversations)
            if self._ui_alive() and self._chat_view:
                self.root.after(0, self._chat_view.refresh_conversation_list)
        except Exception:
            # best-effort
            return

    # ==================== Conversation settings (pin/mute) ====================

    def _toggle_pin_active(self):
        """Toggle pin for current DM conversation."""
        cid = self._conv_manager.active_cid
        if cid == "global" or not self._token:
            return
        conv = self._conv_manager.get_conversation(cid)
        target_state = not bool(getattr(conv, "pinned", False))
        self._async_service.run_async(self._do_update_conv_settings(cid, pinned=target_state, muted=None))

    def _toggle_mute_active(self):
        """Toggle mute for current DM conversation."""
        cid = self._conv_manager.active_cid
        if cid == "global" or not self._token:
            return
        conv = self._conv_manager.get_conversation(cid)
        target_state = not bool(getattr(conv, "muted", False))
        self._async_service.run_async(self._do_update_conv_settings(cid, pinned=None, muted=target_state))

    async def _do_update_conv_settings(self, other_user: str, pinned: Optional[bool], muted: Optional[bool]):
        try:
            resp = await self._api_client.update_conversation_settings(other_user, pinned=pinned, muted=muted)
            if not resp.get("success"):
                return
            # Refresh conversation ordering + labels from server.
            await self._sync_conversations_from_server()
            if self._ui_alive() and self._chat_view:
                self.root.after(0, self._chat_view.refresh_conversation_list)
        except Exception:
            return

    async def _load_history_for(self, other_user: str, limit: int = 50):
        """Load DM history from server and render the conversation."""
        other = (other_user or "").strip()
        if not other:
            return

        # Bump request sequence and capture snapshot to prevent stale responses overwriting UI.
        self._history_req_seq += 1
        req_seq = self._history_req_seq
        try:
            resp = await self._api_client.get_history(other, limit=limit)
            if not resp.get("success"):
                # still render what we have
                if self._ui_alive() and self._chat_view:
                    self.root.after(0, self._chat_view.render_conversation)
                return
            messages = resp.get("messages") or []

            # If user already switched away, drop this response.
            if req_seq != self._history_req_seq or self._conv_manager.active_cid != other:
                return

            new_items: list[MessageItem] = []
            for m in messages:
                if not isinstance(m, dict):
                    continue
                sender = str(m.get("sender", ""))
                content = str(m.get("content", ""))
                ts = m.get("created_at")
                try:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(float(ts))
                    time_label = dt.strftime("%H:%M")
                    ts_label = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    time_label = ""
                    ts_label = ""
                new_items.append(
                    MessageItem(
                        sender=sender,
                        content=content,
                        timestamp=time_label,
                        ts=ts_label,
                        is_self=(sender == self._username),
                        is_system=False,
                    )
                )

            # Swap items atomically to avoid "clear then refill" flicker.
            conv = self._conv_manager.create_conversation(other, name=other)
            conv.items = new_items

            if self._ui_alive() and self._chat_view and self._conv_manager.active_cid == other and req_seq == self._history_req_seq:
                self.root.after(0, self._chat_view.render_conversation)
        except Exception:
            if self._ui_alive() and self._chat_view:
                self.root.after(0, self._chat_view.render_conversation)
    
    def _handle_begin_reply(self, sender: str, content: str, timestamp: str):
        """Handle reply request."""
        self._reply_ctx = ReplyContext(sender=sender, content=content, timestamp=timestamp)
        self._chat_view.show_reply_banner(self._reply_ctx)
    
    def _handle_clear_reply(self):
        """Clear reply context."""
        self._reply_ctx = None
        self._chat_view.hide_reply_banner()
    
    def _handle_export_md(self):
        """Export current conversation to Markdown."""
        conv = self._conv_manager.get_active_conversation()
        if not conv:
            return
        path = self._persistence.export_conversation_md(
            self._username, conv.cid, conv.name,
            [item.__dict__ for item in conv.items]
        )
        if path:
            self._open_logs_folder()
    
    def _handle_export_json(self):
        """Export current conversation to JSON."""
        conv = self._conv_manager.get_active_conversation()
        if not conv:
            return
        path = self._persistence.export_conversation_json(
            self._username, conv.cid,
            [item.__dict__ for item in conv.items]
        )
        if path:
            self._open_logs_folder()
    
    def _handle_export_logs(self):
        """Open logs folder."""
        self._open_logs_folder()
    
    def _open_logs_folder(self):
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
    
    def _handle_logout(self):
        """Handle logout request."""
        self._running = False
        self._async_service.run_async(self._do_logout())
    
    async def _do_logout(self):
        """Perform logout."""
        try:
            await self._api_client.logout()
        except:
            pass
        finally:
            if self._ui_alive():
                self.root.after(0, self._show_auth_view)
    
    # ==================== Message Handling ====================
    
    async def _poll_messages(self):
        """Poll for new messages."""
        while self._running and not self._closing:
            try:
                msg = await self._api_client.receive_message()
                
                if isinstance(msg, dict) and msg.get("success"):
                    sender = msg.get("sender")
                    content = msg.get("content")

                    # System events (do NOT render as chat messages)
                    if sender == "SERVER" and isinstance(content, str) and content.startswith("[[EVENT"):
                        # Currently used for: friend_accepted → refresh friends + conversations.
                        try:
                            if "friend_accepted" in content:
                                # Best-effort refresh: conversations (to show new DM) + contacts badge.
                                await self._sync_conversations_from_server()
                                if self._ui_alive():
                                    self.root.after(0, self._refresh_contacts)
                        except Exception:
                            pass
                        await asyncio.sleep(0.05)
                        continue
                    
                    if sender and content and sender != self._username:
                        cid, actual_sender, body = self._conv_manager.process_received_message(
                            sender, content, self._username
                        )
                        
                        if cid:
                            item = MessageItem.create(actual_sender, body, is_self=False)
                            is_active = (cid == self._conv_manager.active_cid)
                            self._conv_manager.add_message(cid, item, is_active=is_active)
                            
                            if self._ui_alive():
                                if is_active:
                                    self.root.after(0, lambda: self._add_message_to_ui(item))
                                else:
                                    self.root.after(0, self._chat_view.refresh_conversation_list)
                
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.5)
    
    def _add_message_to_ui(self, item: MessageItem):
        """Add a message to the UI."""
        if not self._chat_view:
            return
        card = self._chat_view.add_message_card(item)
        self._search_service.set_message_cards(self._chat_view.get_message_cards())
        self._persistence.log_chat(self._username, item.sender, item.content)
    
    def _add_system_message(self, content: str):
        """Add a system message."""
        item = MessageItem.create("System", content, is_system=True)
        self._conv_manager.add_message(self._conv_manager.active_cid, item, is_active=True)
        if self._chat_view:
            self._chat_view.add_message_card(item)
        self._persistence.log_chat(self._username, "System", content)
    
    # ==================== Search ====================
    
    def _open_search(self):
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
    
    def _handle_search_next(self):
        """Go to next search result."""
        self._search_service.next_result()
        card = self._search_service.get_current_hit_widget()
        if card and self._chat_view:
            self._chat_view.scroll_to_card(card)
    
    def _handle_search_prev(self):
        """Go to previous search result."""
        self._search_service.prev_result()
        card = self._search_service.get_current_hit_widget()
        if card and self._chat_view:
            self._chat_view.scroll_to_card(card)
    
    def _handle_search_close(self):
        """Close search dialog."""
        self._search_service.clear()
        self._search_dialog = None
    
    # ==================== Cleanup ====================
    
    def _on_close(self):
        """Handle window close."""
        self._closing = True
        self._running = False
        
        # Cancel poll future
        if self._poll_future and not self._poll_future.done():
            self._poll_future.cancel()
        
        # Stop async service
        self._async_service.stop()
        
        # Drop tk variable references
        try:
            for name in ("username_var", "password_var", "server_var", "port_var",
                        "status_var", "input_var", "search_var"):
                if hasattr(self, name):
                    setattr(self, name, None)
            gc.collect()
        except Exception:
            pass
        
        # Destroy UI
        try:
            if self.root:
                self.root.quit()
                self.root.destroy()
        except Exception:
            pass
        finally:
            self.root = None


__all__ = ['GUIClient']
