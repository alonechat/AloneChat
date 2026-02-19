"""
Authentication view for login/register with modern UI design.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..components import WinUI3Entry, LoadingButton, StatusMessage, CollapsibleSection
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT


class AuthView:
    """Modern authentication view with improved UX."""
    
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
        self.server_settings_frame: Optional[ttk.Frame] = None
        self.status_message: Optional[StatusMessage] = None
        self.login_btn: Optional[LoadingButton] = None
        self.register_btn: Optional[LoadingButton] = None
        self.remember_var: Optional[tk.BooleanVar] = None
        
    def show(self):
        """Display the modern auth view."""
        self.frame = ttk.Frame(self.root)
        self.frame.grid(row=0, column=0, sticky="nsew")
        
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=0)
        self.frame.grid_columnconfigure(2, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)
        
        self._create_left_panel()
        self._create_separator()
        self._create_right_panel()
        
        self.root.unbind('<Return>')
        self.root.bind('<Return>', lambda e: self._handle_login())
        
        self.root.after(100, lambda: self.username_entry.focus() if self.username_entry else None)
    
    def _create_left_panel(self):
        left_frame = ttk.Frame(self.frame, padding=(80, 80))
        left_frame.grid(row=0, column=0, sticky="nsew")
        
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_rowconfigure(1, weight=0)
        left_frame.grid_rowconfigure(2, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)
        
        left_content = ttk.Frame(left_frame)
        left_content.grid(row=1, column=0, sticky="w")
        
        logo_frame = ttk.Frame(left_content)
        logo_frame.pack(anchor="w", pady=(0, 24))
        
        logo_icon = ttk.Label(logo_frame, text="💬", font=("Segoe UI", 48))
        logo_icon.pack(anchor="w")
        
        title = ttk.Label(logo_frame, text="AloneChat", font=("Segoe UI", 36, "bold"))
        title.pack(anchor="w", pady=(16, 0))
        
        subtitle = ttk.Label(left_content, text="Sign in to start chatting", 
                            font=("Segoe UI", 14))
        subtitle.pack(anchor="w", pady=(0, 32))
        
        features_frame = ttk.Frame(left_content)
        features_frame.pack(anchor="w")
        
        features = [
            ("🔒", "End-to-end encrypted messaging"),
            ("⚡", "Real-time communication"),
            ("🌐", "Self-hosted & private")
        ]
        
        for icon, text in features:
            feature_row = ttk.Frame(features_frame)
            feature_row.pack(anchor="w", pady=6)
            
            ttk.Label(feature_row, text=icon, font=("Segoe UI", 12)).pack(side="left", padx=(0, 12))
            ttk.Label(feature_row, text=text, font=("Segoe UI", 11)).pack(side="left")
    
    def _create_separator(self):
        separator_frame = ttk.Frame(self.frame)
        separator_frame.grid(row=0, column=1, sticky="ns", padx=24)
        
        separator = ttk.Separator(separator_frame, orient="vertical")
        separator.pack(fill="y", expand=True)
    
    def _create_right_panel(self):
        right_frame = ttk.Frame(self.frame, padding=(80, 80))
        right_frame.grid(row=0, column=2, sticky="nsew")
        
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=0)
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        
        form_container = ttk.Frame(right_frame)
        form_container.grid(row=1, column=0, sticky="ew")
        
        form_header = ttk.Frame(form_container)
        form_header.pack(fill="x", pady=(0, 24))
        
        ttk.Label(form_header, text="Welcome back", 
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(form_header, text="Enter your credentials to continue",
                 font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 0))
        
        self.username_entry = WinUI3Entry(
            form_container, 
            label="Username",
            placeholder="Enter your username",
            icon="👤"
        )
        self.username_entry.pack(fill="x", pady=(0, 16))
        
        self.password_entry = WinUI3Entry(
            form_container,
            label="Password",
            placeholder="Enter your password",
            password=True,
            icon="🔑"
        )
        self.password_entry.pack(fill="x", pady=(0, 8))
        
        self.remember_var = tk.BooleanVar(value=False)
        remember_frame = ttk.Frame(form_container)
        remember_frame.pack(fill="x", pady=(0, 16))
        
        remember_check = ttk.Checkbutton(
            remember_frame,
            text="Remember me",
            variable=self.remember_var
        )
        remember_check.pack(side="left")
        
        self.status_message = StatusMessage(form_container)
        self.status_message.pack(fill="x", pady=(0, 8))
        
        self.login_btn = LoadingButton(
            form_container,
            text="Sign In",
            command=self._handle_login,
            primary=True
        )
        self.login_btn.pack(fill="x", pady=(0, 8))
        
        self.register_btn = LoadingButton(
            form_container,
            text="Create Account",
            command=self._handle_register,
            primary=False
        )
        self.register_btn.pack(fill="x", pady=(0, 16))
        
        self._create_server_settings(form_container)
    
    def _create_server_settings(self, parent):
        settings_container = ttk.Frame(parent)
        settings_container.pack(fill="x")
        
        self.settings_section = CollapsibleSection(settings_container, "Server Settings")
        self.settings_section.pack(fill="x")
        
        settings_content = ttk.Frame(settings_container)
        self.settings_section.set_content(settings_content)
        
        host_frame = ttk.Frame(settings_content)
        host_frame.pack(fill="x", pady=(8, 8))
        
        ttk.Label(host_frame, text="API Host:", font=("Segoe UI", 10)).pack(side="left")
        self.api_host_entry = ttk.Entry(host_frame, width=25, font=("Segoe UI", 10))
        self.api_host_entry.pack(side="right", fill="x", expand=True)
        self.api_host_entry.insert(0, self.default_api_host)
        
        port_frame = ttk.Frame(settings_content)
        port_frame.pack(fill="x", pady=(0, 8))
        
        ttk.Label(port_frame, text="API Port:", font=("Segoe UI", 10)).pack(side="left")
        self.api_port_entry = ttk.Entry(port_frame, width=25, font=("Segoe UI", 10))
        self.api_port_entry.pack(side="right", fill="x", expand=True)
        self.api_port_entry.insert(0, str(self.default_api_port))
        
        ttk.Button(
            settings_content,
            text="Apply Settings",
            command=self._apply_server_settings
        ).pack(fill="x", pady=(8, 0))
    
    def hide(self):
        if self.frame:
            self.frame.destroy()
            self.frame = None
    
    def show_loading(self):
        if self.login_btn:
            self.login_btn.start_loading()
    
    def hide_loading(self):
        if self.login_btn:
            self.login_btn.stop_loading()
    
    def show_error(self, message: str):
        if self.status_message:
            self.status_message.show_error(message)
        if self.login_btn:
            self.login_btn.stop_loading()
    
    def show_success(self, message: str):
        if self.status_message:
            self.status_message.show_success(message)
    
    def _handle_login(self):
        username = self.username_entry.get() if self.username_entry else ""
        password = self.password_entry.get() if self.password_entry else ""
        
        if not username.strip():
            self.show_error("Please enter your username")
            return
        if not password:
            self.show_error("Please enter your password")
            return
        
        self.show_loading()
        self.on_login(username, password)
    
    def _handle_register(self):
        username = self.username_entry.get() if self.username_entry else ""
        password = self.password_entry.get() if self.password_entry else ""
        
        if not username.strip():
            self.show_error("Please enter a username")
            return
        if not password:
            self.show_error("Please enter a password")
            return
        if len(password) < 6:
            self.show_error("Password must be at least 6 characters")
            return
        
        self.register_btn.start_loading()
        self.on_register(username, password)
    
    def _apply_server_settings(self):
        if self.on_server_settings_changed:
            host = self.api_host_entry.get() if self.api_host_entry else self.default_api_host
            try:
                port = int(self.api_port_entry.get()) if self.api_port_entry else self.default_api_port
            except ValueError:
                self.show_error("Invalid port number")
                return
            self.on_server_settings_changed(host, port)
            self.show_success("Server settings applied")
