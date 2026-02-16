"""
User list dialog for selecting users to chat with - sv_ttk styled.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Dict, Any, Optional


class UserListDialog:
    """Dialog showing list of users with their status."""
    
    def __init__(
        self, 
        root: tk.Tk, 
        on_select_user: Callable[[str], None],
        on_refresh: Optional[Callable[[], None]] = None
    ):
        self.root = root
        self.on_select_user = on_select_user
        self.on_refresh = on_refresh
        
        self.window: Optional[tk.Toplevel] = None
        self.users_listbox: Optional[tk.Listbox] = None
        self.users_data: List[Dict[str, Any]] = []
    
    def show(self):
        """Show the user list dialog."""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return
        
        self.window = tk.Toplevel(self.root)
        self.window.title("Users")
        self.window.geometry("350x450")
        self.window.resizable(True, True)
        
        frm = ttk.Frame(self.window, padding=16)
        frm.pack(fill="both", expand=True)
        
        ttk.Label(frm, text="Select a user to chat:").pack(anchor="w", pady=(0, 8))
        
        list_frame = ttk.Frame(frm)
        list_frame.pack(fill="both", expand=True, pady=(0, 12))
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.users_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode="single",
            height=15,
            font=("", 11)
        )
        self.users_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.users_listbox.yview)
        
        self.users_listbox.bind("<Double-1>", self._on_double_click)
        self.users_listbox.bind("<Return>", self._on_double_click)
        
        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x")
        
        if self.on_refresh:
            ttk.Button(btn_frame, text="Refresh", 
                      command=self._on_refresh).pack(side="left")
        
        ttk.Button(btn_frame, text="Chat", 
                  command=self._on_select).pack(side="right", padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", 
                  command=self.hide).pack(side="right")
        
        self.window.bind("<Escape>", lambda e: self.hide())
        
        self._update_listbox()
    
    def _update_listbox(self):
        """Update the listbox with current users data."""
        if not self.users_listbox:
            return
        
        self.users_listbox.delete(0, tk.END)
        
        for user in self.users_data:
            user_id = user.get("user_id", user.get("display_name", "Unknown"))
            status = user.get("status", "offline")
            is_online = user.get("is_online", False)
            
            status_icon = self._get_status_icon(status, is_online)
            display_text = f"{status_icon} {user_id}"
            
            self.users_listbox.insert(tk.END, display_text)
    
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
    
    def set_users(self, users: List[Any]):
        """Set the list of users to display."""
        self.users_data = []
        
        for user in users:
            if isinstance(user, str):
                self.users_data.append({
                    "user_id": user,
                    "status": "online",
                    "is_online": True
                })
            elif isinstance(user, dict):
                self.users_data.append(user)
        
        self._update_listbox()
    
    def _on_double_click(self, event=None):
        """Handle double click on user."""
        self._on_select()
    
    def _on_select(self):
        """Handle select button click."""
        if not self.users_listbox:
            return
        
        selection = self.users_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if 0 <= idx < len(self.users_data):
            user_id = self.users_data[idx].get("user_id", 
                         self.users_data[idx].get("display_name", ""))
            if user_id:
                self.on_select_user(user_id)
                self.hide()
    
    def _on_refresh(self):
        """Handle refresh button click."""
        if self.on_refresh:
            self.on_refresh()
    
    def hide(self):
        """Hide the dialog."""
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
        self.window = None
        self.users_listbox = None
