"""
Header bar component for chat view.
Contains title, username, status selector, and action buttons.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class HeaderBar:
    """Header bar with title, user info, status, and action buttons."""
    
    def __init__(self, parent: tk.Tk, username: str,
                 on_logout: Callable[[], None],
                 on_export_logs: Callable[[], None],
                 on_refresh_users: Optional[Callable[[], None]] = None,
                 on_set_status: Optional[Callable[[str], None]] = None):
        self.parent = parent
        self.username = username
        self.on_logout = on_logout
        self.on_export_logs = on_export_logs
        self.on_refresh_users = on_refresh_users
        self.on_set_status = on_set_status
        
        self.frame: Optional[ttk.Frame] = None
        self.status_var: Optional[tk.StringVar] = None
        self.status_combo: Optional[ttk.Combobox] = None
    
    def build(self) -> ttk.Frame:
        """Build and return the header frame."""
        self.frame = ttk.Frame(self.parent, padding=(16, 12))
        
        header_left = ttk.Frame(self.frame)
        header_left.pack(side="left")
        
        title = ttk.Label(header_left, text="AloneChat")
        title.pack(side="left")
        
        user_label = ttk.Label(header_left, text=f"  |  {self.username}")
        user_label.pack(side="left")
        
        if self.on_set_status:
            self._build_status_selector(header_left)
        
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(side="right")
        
        if self.on_refresh_users:
            ttk.Button(btn_frame, text="Refresh",
                      command=self.on_refresh_users).pack(side="right", padx=4)
        
        ttk.Button(btn_frame, text="Export",
                  command=self.on_export_logs).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="Logout",
                  command=self.on_logout).pack(side="right", padx=4)
        
        return self.frame
    
    def _build_status_selector(self, parent: ttk.Frame):
        """Build the status selector combobox."""
        self.status_var = tk.StringVar(value="online")
        self.status_combo = ttk.Combobox(
            parent,
            textvariable=self.status_var,
            values=["online", "away", "busy", "offline"],
            state="readonly",
            width=8
        )
        self.status_combo.pack(side="left", padx=(8, 0))
        self.status_combo.bind("<<ComboboxSelected>>", self._on_status_change)
    
    def _on_status_change(self, event):
        """Handle status change."""
        if self.status_var and self.on_set_status:
            status = self.status_var.get()
            self.on_set_status(status)
    
    def destroy(self):
        """Destroy the header frame."""
        if self.frame:
            self.frame.destroy()
            self.frame = None
