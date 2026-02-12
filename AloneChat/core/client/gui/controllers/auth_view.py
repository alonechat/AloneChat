"""
Authentication view for login/register with sv_ttk styling.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from ..components import WinUI3Entry


class AuthView:
    """Authentication view with login/register forms - sv_ttk styled."""
    
    def __init__(self, root: tk.Tk, on_login: Callable[[str, str], None],
                 on_register: Callable[[str, str], None]):
        self.root = root
        self.on_login = on_login
        self.on_register = on_register
        self.frame: Optional[ttk.Frame] = None
        self.username_entry: Optional[WinUI3Entry] = None
        self.password_entry: Optional[WinUI3Entry] = None
        
    def show(self):
        """Display the auth view with sv_ttk styling."""
        self.frame = ttk.Frame(self.root)
        self.frame.place(relx=0.5, rely=0.5, anchor="center")
        
        # Title - let sv_ttk handle styling
        title = ttk.Label(self.frame, text="AloneChat")
        title.pack(pady=(0, 8))
        
        # Subtitle
        subtitle = ttk.Label(self.frame, text="Sign in to start chatting")
        subtitle.pack(pady=(0, 24))
        
        # Card frame
        card = ttk.LabelFrame(self.frame, text="", padding=32)
        card.pack(fill="x")
        
        # Username entry
        self.username_entry = WinUI3Entry(card, label="Username", 
                                         placeholder="Enter your username")
        self.username_entry.pack(fill="x", pady=16)
        
        # Password entry
        self.password_entry = WinUI3Entry(card, label="Password",
                                         placeholder="Enter your password",
                                         password=True)
        self.password_entry.pack(fill="x", pady=16)
        
        # Buttons
        btn_frame = ttk.Frame(card)
        btn_frame.pack(fill="x", pady=(24, 0))
        
        ttk.Button(btn_frame, text="Sign In", 
                  command=self._handle_login).pack(fill="x", pady=8)
        
        ttk.Button(btn_frame, text="Create Account",
                  command=self._handle_register).pack(fill="x", pady=8)
        
        # Bind Enter key
        self.root.unbind('<Return>')
        self.root.bind('<Return>', lambda e: self._handle_login())
    
    def hide(self):
        """Hide the auth view."""
        if self.frame:
            self.frame.destroy()
            self.frame = None
    
    def _handle_login(self):
        """Handle login button click."""
        username = self.username_entry.get() if self.username_entry else ""
        password = self.password_entry.get() if self.password_entry else ""
        self.on_login(username, password)
    
    def _handle_register(self):
        """Handle register button click."""
        username = self.username_entry.get() if self.username_entry else ""
        password = self.password_entry.get() if self.password_entry else ""
        self.on_register(username, password)
