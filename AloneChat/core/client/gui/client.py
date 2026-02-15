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
from tkinter import messagebox, simpledialog, ttk
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
from .controllers.friends_view import FriendsView
from .controllers.search_dialog import SearchDialog
from .models.data import MessageItem, ReplyContext
from .services import ConversationManager, SearchService, PersistenceService, AsyncService


# DPI awareness disabled - letting Windows auto-scale for better compatibility
# If you want crisp rendering on high-DPI, consider using DPI awareness with proper scaling

# noinspection PyTypeChecker
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
        
        # Services
        self._async_service = AsyncService()
        self._conv_manager = ConversationManager()
        self._search_service = SearchService()
        self._persistence = PersistenceService()
        
        # Reply context
        self._reply_ctx: Optional[ReplyContext] = None
        
        # Poll future for cancellation
        self._poll_future = None
    
    # ==================== Lifecycle ====================
    
    def run(self):
        """Start the GUI client."""
        # Create main window
        self.root = tk.Tk()
        self.root.title("AloneChat")
        self.root.geometry("1200x640")
        self.root.minsize(800, 500)

        # Add icon if available
        # noinspection PyBroadException
        try:
            self.root.iconphoto(False, tk.PhotoImage(file="../../../../assets/icon.jpg"))
        # noinspection PyBroadException
        except Exception:
            pass
        
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
        """Show main UI with Chats / Friends / Moments."""
        self._clear_view()
        self._running = True

        # Main tabs
        self._main_tabs = ttk.Notebook(self.root)

        # Chats tab
        self._tab_chats = ttk.Frame(self._main_tabs)
        self._main_tabs.add(self._tab_chats, text="Chats")

        # Friends tab
        self._tab_friends = ttk.Frame(self._main_tabs)
        self._main_tabs.add(self._tab_friends, text="Friends")

        # Moments tab (placeholder)
        self._tab_moments = ttk.Frame(self._main_tabs)
        self._main_tabs.add(self._tab_moments, text="Moments")

        self._main_tabs.pack(fill="both", expand=True)

        # Chats UI (keep existing style)
        self._chat_view = ChatView(
            self._tab_chats,
            username=self._username,
            conversation_manager=self._conv_manager,
            on_send=self._handle_send,
            on_new_conversation=self._handle_new_conversation,
            on_select_conversation=self._handle_switch_conversation,
            on_reply=self._handle_begin_reply,
            on_clear_reply=self._handle_clear_reply,
            on_export_md=self._handle_export_md,
            on_export_json=self._handle_export_json,
            on_export_logs=self._handle_export_logs,
            on_logout=self._handle_logout
        )
        self._chat_view.show()

        # Friends UI (separate from chats)
        self._friends_view = FriendsView(
            self._tab_friends,
            username=self._username,
            api_client=self._api_client,
            run_async=self._async_service.run_async,
            on_open_dm=self._open_dm_from_friends,
        )
        self._friends_view.show()
        self._friends_view.refresh_all()

        ttk.Label(self._tab_moments, text="(Moments - coming soon)").pack(padx=20, pady=20, anchor="nw")

        # Start background loops
        self._async_service.run_async(self._poll_messages())
        self._async_service.run_async(self._heartbeat_loop())

    

    def _show_onboarding(self):
        """Show one-time onboarding tips."""
        state = self._persistence.load_state()
        if not state.get("onboarding_shown", False):
            self._add_system_message(
                "Tips:\n"
                "• Click Send to send messages\n"
                "• If a message fails, click the red status to retry\n"
                "• Use Export to open your local chat logs folder\n"
                "• Need help? Contact to us with tonytao2022 @outlook.com | zhang.chenyun @outlook.com"
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
            # ConversationManager uses active_cid ("global" or username for DM).
            # For DM we keep the legacy DM header in payload and also pass target so the server routes privately.
            active_cid = getattr(self._conv_manager, "active_cid", "global")
            target = active_cid if active_cid != "global" else None
            response = await self._api_client.send_message(payload, target=target)
            
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
        """Handle new conversation request.

        Direct username DM creation is disabled. Use Friends tab to add friends first.
        """
        try:
            messagebox.showinfo(
                "New Conversation Disabled",
                "Please add the user as a friend first (Friends → Search → Send Request).\nThen open the chat by double-clicking the friend."
            )
        except Exception:
            pass

        # Jump to Friends tab for convenience
        try:
            if hasattr(self, "_main_tabs") and self._main_tabs:
                self._main_tabs.select(1)  # Friends
        except Exception:
            pass
        return

    def _handle_switch_conversation(self, cid: str):
        """Handle conversation switch."""
        self._conv_manager.switch_conversation(cid)
        self._chat_view.refresh_conversation_list()
        self._chat_view.render_conversation()
        self._search_service.set_message_cards(self._chat_view.get_message_cards())
    
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
        # noinspection PyBroadException
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
            # noinspection PyBroadException
            try:
                msg = await self._api_client.receive_message()
                
                if isinstance(msg, dict) and msg.get("success"):
                    sender = msg.get("sender")
                    content = msg.get("content")
                    
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
    
    async def _heartbeat_loop(self):
        """Send heartbeat periodically so server can compute online users."""
        while self._running:
            try:
                await self._api_client.heartbeat()
            except Exception:
                pass
            await asyncio.sleep(10)

    def _open_dm_from_friends(self, friend_username: str):
        """Create/switch to a DM conversation and jump to Chats tab."""
        if not friend_username:
            return
        self._conv_manager.create_conversation(friend_username, name=friend_username)
        self._conv_manager.switch_conversation(friend_username)
        if hasattr(self, "_chat_view") and self._chat_view:
            self._chat_view.refresh_conversation_list()
            # ChatView public API
            self._chat_view.render_conversation()
        if hasattr(self, "_main_tabs") and self._main_tabs:
            try:
                # Chats tab is index 0
                self._main_tabs.select(0)
            except Exception:
                pass


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
        # noinspection PyBroadException
        try:
            for name in ("username_var", "password_var", "server_var", "port_var",
                        "status_var", "input_var", "search_var"):
                if hasattr(self, name):
                    setattr(self, name, None)
            gc.collect()
        except Exception:
            pass
        
        # Destroy UI
        # noinspection PyBroadException
        try:
            if self.root:
                self.root.quit()
                self.root.destroy()
        except Exception:
            pass
        finally:
            self.root = None


__all__ = ['GUIClient']
