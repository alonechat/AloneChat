"""
Authentication view for login/register with sv_ttk styling.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..components import WinUI3Entry
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT


class AuthView:
    """Authentication view with login/register forms - sv_ttk styled."""
    
    def __init__(self, root: tk.Tk, on_login: Callable[[str, str], None],
                 on_register: Callable[[str, str], None],
                 on_server_settings_changed: Optional[Callable[[str, int], None]] = None,
                 default_api_host: str = DEFAULT_HOST,
                 default_api_port: int = DEFAULT_API_PORT):
        self.root = root
        self.on_login = on_login
        self.on_register = on_register
        self.on_server_settings_changed = on_server_settings_changed
        self.default_api_host = default_api_host
        self.default_api_port = default_api_port
        self.frame: Optional[ttk.Frame] = None
        self.username_entry: Optional[WinUI3Entry] = None
        self.password_entry: Optional[WinUI3Entry] = None
        self.api_host_entry: Optional[ttk.Entry] = None
        self.api_port_entry: Optional[ttk.Entry] = None
        self.server_settings_frame: Optional[ttk.LabelFrame] = None
        self.settings_toggle_btn: Optional[ttk.Button] = None
        self.server_settings_visible = False
        
    def show(self):
        """Display the auth view with sv_ttk styling - horizontal layout."""
        # Main frame fills the window using grid to be compatible with other views
        self.frame = ttk.Frame(self.root)
        self.frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure root grid to allow frame to expand
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Use grid layout for proper centering
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=0)  # Separator
        self.frame.grid_columnconfigure(2, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)
        
        # Left side - Title and branding
        left_frame = ttk.Frame(self.frame, padding=(64, 64))
        left_frame.grid(row=0, column=0, sticky="nsew")
        
        # Center content vertically using grid
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_rowconfigure(1, weight=0)
        left_frame.grid_rowconfigure(2, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)
        
        left_content = ttk.Frame(left_frame)
        left_content.grid(row=1, column=0, sticky="w")
        
        # Title - large and prominent
        title = ttk.Label(left_content, text="AloneChat", font=("Segoe UI", 32, "bold"))
        title.pack(anchor="w", pady=(0, 16))
        
        # Subtitle
        subtitle = ttk.Label(left_content, text="Sign in to start chatting", font=("Segoe UI", 14))
        subtitle.pack(anchor="w")
        
        # Vertical separator
        separator = ttk.Separator(self.frame, orient="vertical")
        separator.grid(row=0, column=1, sticky="ns", padx=32)
        
        # Right side - Form fields
        right_frame = ttk.Frame(self.frame, padding=(64, 64))
        right_frame.grid(row=0, column=2, sticky="nsew")
        
        # Center content vertically using grid
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=0)
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        
        # Form container
        form_container = ttk.Frame(right_frame)
        form_container.grid(row=1, column=0, sticky="ew")
        
        # Username entry
        self.username_entry = WinUI3Entry(form_container, label="Username", 
                                         placeholder="Enter your username")
        self.username_entry.pack(fill="x", pady=(0, 16))
        
        # Password entry
        self.password_entry = WinUI3Entry(form_container, label="Password",
                                         placeholder="Enter your password",
                                         password=True)
        self.password_entry.pack(fill="x", pady=(0, 24))
        
        # Buttons
        btn_frame = ttk.Frame(form_container)
        btn_frame.pack(fill="x", pady=(0, 16))
        
        ttk.Button(btn_frame, text="Sign In", 
                  command=self._handle_login).pack(fill="x", pady=(0, 8))
        
        ttk.Button(btn_frame, text="Create Account",
                  command=self._handle_register).pack(fill="x", pady=(0, 8))
        
        # Server Settings Toggle
        settings_toggle_frame = ttk.Frame(form_container)
        settings_toggle_frame.pack(fill="x")
        
        self.settings_toggle_btn = ttk.Button(
            settings_toggle_frame, 
            text="⚙ Server Settings",
            command=self._toggle_server_settings
        )
        self.settings_toggle_btn.pack(side="right")
        
        # Server Settings Frame (initially hidden)
        self.server_settings_frame = ttk.LabelFrame(form_container, text="Server Configuration", padding=16)
        # Don't pack yet - will be shown when toggled
        
        # API Host
        host_frame = ttk.Frame(self.server_settings_frame)
        host_frame.pack(fill="x", pady=8)
        ttk.Label(host_frame, text="API Host:").pack(side="left")
        self.api_host_entry = ttk.Entry(host_frame, width=25)
        self.api_host_entry.pack(side="right", fill="x", expand=True)
        self.api_host_entry.insert(0, self.default_api_host)
        
        # API Port
        port_frame = ttk.Frame(self.server_settings_frame)
        port_frame.pack(fill="x", pady=8)
        ttk.Label(port_frame, text="API Port:").pack(side="left")
        self.api_port_entry = ttk.Entry(port_frame, width=25)
        self.api_port_entry.pack(side="right", fill="x", expand=True)
        self.api_port_entry.insert(0, str(self.default_api_port))
        
        # Apply button
        ttk.Button(
            self.server_settings_frame, 
            text="Apply Settings",
            command=self._apply_server_settings
        ).pack(fill="x", pady=(16, 0))
        
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
    
    def _toggle_server_settings(self):
        """Toggle visibility of server settings frame."""
        if self.server_settings_visible:
            if self.server_settings_frame:
                self.server_settings_frame.pack_forget()
            if self.settings_toggle_btn:
                self.settings_toggle_btn.configure(text="⚙ Server Settings")
            self.server_settings_visible = False
        else:
            if self.server_settings_frame:
                self.server_settings_frame.pack(fill="x", pady=(16, 0))
            if self.settings_toggle_btn:
                self.settings_toggle_btn.configure(text="⚙ Hide Settings")
            self.server_settings_visible = True
    
    def _apply_server_settings(self):
        """Apply server settings and notify callback."""
        if self.on_server_settings_changed:
            host = self.api_host_entry.get() if self.api_host_entry else self.default_api_host
            try:
                port = int(self.api_port_entry.get()) if self.api_port_entry else self.default_api_port
            except ValueError:
                port = self.default_api_port
            self.on_server_settings_changed(host, port)
