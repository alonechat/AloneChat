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
"""

import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, List, Dict, Any
from datetime import datetime
import threading
import time
from dataclasses import dataclass

from AloneChat.core.client.client_base import Client
from AloneChat.api.client import AloneChatAPIClient
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT


@dataclass
class Theme:
    """Modern color theme - Light mode default."""
    # Primary
    primary: str = "#0078D4"
    primary_hover: str = "#106EBE"
    primary_active: str = "#005A9E"
    
    # Background
    bg_primary: str = "#FFFFFF"
    bg_secondary: str = "#F5F5F5"
    bg_card: str = "#FFFFFF"
    bg_input: str = "#FFFFFF"
    
    # Text
    text_primary: str = "#1A1A1A"
    text_secondary: str = "#616161"
    text_muted: str = "#9E9E9E"
    text_inverse: str = "#FFFFFF"
    
    # Border
    border: str = "#E0E0E0"
    border_focus: str = "#0078D4"
    
    # Messages
    bubble_self: str = "#0078D4"
    bubble_other: str = "#F0F0F0"
    bubble_system: str = "#FFF8E1"
    
    # Status
    success: str = "#107C10"
    error: str = "#D13438"
    warning: str = "#FFB900"


class ModernStyles:
    """Modern typography and spacing."""
    # Font families
    FONT_FAMILY = "Segoe UI"
    FONT_MONO = "Consolas"
    
    # Sizes
    XS = 10
    SM = 11
    BASE = 12
    LG = 14
    XL = 16
    XXL = 20
    TITLE = 24
    
    # Spacing
    SPACE_1 = 4
    SPACE_2 = 8
    SPACE_3 = 12
    SPACE_4 = 16
    SPACE_5 = 20
    SPACE_6 = 24
    SPACE_8 = 32
    
    # Border radius
    RADIUS_SM = 4
    RADIUS_MD = 8
    RADIUS_LG = 12


class BoundedFrame(ttk.Frame):
    """Frame that properly manages its bounds and children."""
    
    def __init__(self, parent, min_width: int = 200, min_height: int = 100, **kwargs):
        super().__init__(parent, **kwargs)
        self.min_width = min_width
        self.min_height = min_height
        self._setup_responsive_behavior()
    
    def _setup_responsive_behavior(self):
        """Setup responsive sizing behavior."""
        def on_configure(event):
            # Ensure minimum size
            if event.width < self.min_width or event.height < self.min_height:
                self.configure(width=max(event.width, self.min_width),
                             height=max(event.height, self.min_height))
        
        self.bind('<Configure>', on_configure)


class ScrollableFrame(ttk.Frame):
    """Frame with scrollbars that properly manages content bounds."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=Theme.bg_primary)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        # Configure canvas
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Create content frame inside canvas
        self.content = ttk.Frame(self.canvas)
        self.content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        
        # Layout
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        # Setup scrolling
        self._setup_scrolling()
    
    def _setup_scrolling(self):
        """Setup scroll behavior."""
        def on_content_configure(event):
            # Update scroll region when content changes
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            # Keep canvas width matched to frame width
            canvas_width = self.canvas.winfo_width()
            self.canvas.itemconfig(self.content_window, width=canvas_width)
        
        def on_canvas_configure(event):
            # Update content width when canvas resizes
            self.canvas.itemconfig(self.content_window, width=event.width)
        
        self.content.bind('<Configure>', on_content_configure)
        self.canvas.bind('<Configure>', on_canvas_configure)
        
        # Mouse wheel scrolling
        def on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.canvas.bind_all("<MouseWheel>", on_mousewheel)
    
    def scroll_to_bottom(self):
        """Scroll to the bottom of the content."""
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)


class ModernButton(ttk.Button):
    """Modern styled button with consistent sizing."""
    
    def __init__(self, parent, text: str, command: Optional[Callable] = None, 
                 variant: str = "primary", width: int = 15, **kwargs):
        # Create style if not exists
        style_name = f"{variant.capitalize()}.TButton"
        self._ensure_style(parent, variant)
        
        super().__init__(parent, text=text, command=command, 
                        style=style_name, width=width, **kwargs)
    
    def _ensure_style(self, parent, variant: str):
        """Ensure the button style exists."""
        style = ttk.Style()
        style_name = f"{variant.capitalize()}.TButton"
        
        if variant == "primary":
            style.configure(style_name,
                          font=(ModernStyles.FONT_FAMILY, ModernStyles.BASE, "bold"),
                          background=Theme.primary,
                          foreground=Theme.text_inverse)
            style.map(style_name,
                     background=[('active', Theme.primary_hover), ('pressed', Theme.primary_active)])
        else:
            style.configure(style_name,
                          font=(ModernStyles.FONT_FAMILY, ModernStyles.BASE))


class ModernEntry(ttk.Frame):
    """Modern entry field with label and proper bounds."""
    
    def __init__(self, parent, label: str = "", placeholder: str = "", 
                 password: bool = False, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.placeholder = placeholder
        self.password = password
        self.is_password = password
        
        # Label
        if label:
            self.label_widget = ttk.Label(self, text=label, 
                                         font=(ModernStyles.FONT_FAMILY, ModernStyles.SM))
            self.label_widget.pack(anchor="w", pady=(0, ModernStyles.SPACE_1))
        
        # Entry container with border
        self.entry_container = ttk.Frame(self)
        self.entry_container.pack(fill="x")
        
        # Entry widget
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self.entry_container, textvariable=self.var,
                              font=(ModernStyles.FONT_FAMILY, ModernStyles.BASE),
                              show="*" if password else "")
        self.entry.pack(fill="x", ipady=6)
        
        # Placeholder handling
        if placeholder:
            self._setup_placeholder()
    
    def _setup_placeholder(self):
        """Setup placeholder text behavior."""
        self.entry.insert(0, self.placeholder)
        self.entry.config(foreground=Theme.text_muted)
        
        def on_focus_in(event):
            if self.var.get() == self.placeholder:
                self.var.set("")
                self.entry.config(foreground=Theme.text_primary)
                if self.is_password:
                    self.entry.config(show="*")
        
        def on_focus_out(event):
            if not self.var.get():
                self.var.set(self.placeholder)
                self.entry.config(foreground=Theme.text_muted)
                if self.is_password:
                    self.entry.config(show="")
        
        self.entry.bind('<FocusIn>', on_focus_in)
        self.entry.bind('<FocusOut>', on_focus_out)
    
    def get(self) -> str:
        """Get entry value."""
        value = self.var.get()
        return "" if value == self.placeholder else value
    
    def set(self, value: str):
        """Set entry value."""
        self.var.set(value)
        self.entry.config(foreground=Theme.text_primary)


class MessageCard(ttk.Frame):
    """Modern message card with proper sizing and layout."""
    
    def __init__(self, parent, sender: str, content: str, 
                 is_self: bool = False, is_system: bool = False,
                 timestamp: Optional[str] = None, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.sender = sender
        self.content = content
        self.is_self = is_self
        self.is_system = is_system
        self.timestamp = timestamp or datetime.now().strftime("%H:%M")
        
        self._setup_style()
        self._build_ui()
    
    def _setup_style(self):
        """Setup visual style based on message type."""
        if self.is_system:
            self.bg_color = Theme.bubble_system
            self.fg_color = Theme.text_primary
            self.align = "center"
        elif self.is_self:
            self.bg_color = Theme.bubble_self
            self.fg_color = Theme.text_inverse
            self.align = "right"
        else:
            self.bg_color = Theme.bubble_other
            self.fg_color = Theme.text_primary
            self.align = "left"
    
    def _build_ui(self):
        """Build the message card UI."""
        # Container with padding
        container = ttk.Frame(self)
        container.pack(fill="x", padx=ModernStyles.SPACE_3, pady=ModernStyles.SPACE_1)
        
        # Alignment frame
        align_frame = ttk.Frame(container)
        if self.align == "right":
            align_frame.pack(side="right")
        elif self.align == "left":
            align_frame.pack(side="left")
        else:
            align_frame.pack(expand=True)
        
        # Message bubble
        bubble = tk.Frame(align_frame, bg=self.bg_color, 
                         padx=ModernStyles.SPACE_3, pady=ModernStyles.SPACE_2)
        # Convert our alignment to tkinter anchor values (e/w/center instead of right/left/center)
        tk_anchor = {"right": "e", "left": "w", "center": "center"}.get(self.align, "center")
        bubble.pack(anchor=tk_anchor)
        
        # Sender name (for others)
        if not self.is_self and not self.is_system:
            sender_label = tk.Label(bubble, text=self.sender,
                                   font=(ModernStyles.FONT_FAMILY, ModernStyles.XS, "bold"),
                                   bg=self.bg_color, fg=Theme.primary)
            sender_label.pack(anchor="w")
        
        # Message content
        content_label = tk.Label(bubble, text=self.content,
                                font=(ModernStyles.FONT_FAMILY, ModernStyles.BASE),
                                bg=self.bg_color, fg=self.fg_color,
                                wraplength=400, justify="left")
        content_label.pack(anchor="w", pady=(ModernStyles.SPACE_1, 0))
        
        # Timestamp
        time_label = tk.Label(bubble, text=self.timestamp,
                             font=(ModernStyles.FONT_FAMILY, ModernStyles.XS),
                             bg=self.bg_color, 
                             fg=self.fg_color if self.is_self else Theme.text_muted)
        time_label.pack(anchor="e" if self.is_self else "w", 
                       pady=(ModernStyles.SPACE_1, 0))


class SimpleGUIClient(Client):
    """
    Simplified, modern GUI client with excellent UX.
    
    Features:
    - Clean, modern interface
    - Proper bounds management
    - Simple, intuitive interactions
    - Responsive layout
    """
    
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_API_PORT):
        super().__init__(host, port)
        
        self._api_client = AloneChatAPIClient(host, port)
        self._username = ""
        self._token: Optional[str] = None
        self._running = False
        
        # UI components
        self.root: Optional[tk.Tk] = None
        self.current_view: Optional[ttk.Frame] = None
        self.messages_container: Optional[ScrollableFrame] = None
        
        # Async
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
    
    def run(self):
        """Start the GUI client."""
        # Create main window
        self.root = tk.Tk()
        self.root.title("AloneChat")
        self.root.geometry("800x600")
        self.root.minsize(400, 300)
        self.root.configure(bg=Theme.bg_primary)
        
        # Setup theme
        self._setup_theme()
        
        # Setup async
        self._setup_async()
        
        # Show auth view
        self._show_auth_view()
        
        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Start
        self.root.mainloop()
    
    def _setup_theme(self):
        """Setup ttk theme."""
        style = ttk.Style()
        style.theme_use('clam')  # Use clam as base for better customization
        
        # Configure common elements
        style.configure('TFrame', background=Theme.bg_primary)
        style.configure('TLabel', background=Theme.bg_primary, 
                       foreground=Theme.text_primary,
                       font=(ModernStyles.FONT_FAMILY, ModernStyles.BASE))
        style.configure('TButton', font=(ModernStyles.FONT_FAMILY, ModernStyles.BASE))
        style.configure('TEntry', font=(ModernStyles.FONT_FAMILY, ModernStyles.BASE))
    
    def _setup_async(self):
        """Setup async event loop in background thread."""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        
        while self._loop is None:
            time.sleep(0.01)
    
    def _clear_view(self):
        """Clear current view."""
        if self.current_view:
            self.current_view.destroy()
        
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Frame):
                widget.destroy()
    
    def _show_auth_view(self):
        """Show authentication view."""
        self._clear_view()
        
        # Main container with padding
        container = ttk.Frame(self.root, padding=ModernStyles.SPACE_6)
        container.place(relx=0.5, rely=0.5, anchor="center")
        
        # Title
        title = ttk.Label(container, text="AloneChat",
                         font=(ModernStyles.FONT_FAMILY, ModernStyles.TITLE, "bold"),
                         foreground=Theme.primary)
        title.pack(pady=(0, ModernStyles.SPACE_2))
        
        subtitle = ttk.Label(container, text="Sign in to start chatting",
                            font=(ModernStyles.FONT_FAMILY, ModernStyles.LG),
                            foreground=Theme.text_secondary)
        subtitle.pack(pady=(0, ModernStyles.SPACE_6))
        
        # Card
        card = ttk.Frame(container, padding=ModernStyles.SPACE_6)
        card.pack(fill="x")
        
        # Username
        self.auth_username = ModernEntry(card, label="Username", 
                                        placeholder="Enter your username")
        self.auth_username.pack(fill="x", pady=ModernStyles.SPACE_3)
        
        # Password
        self.auth_password = ModernEntry(card, label="Password",
                                        placeholder="Enter your password",
                                        password=True)
        self.auth_password.pack(fill="x", pady=ModernStyles.SPACE_3)
        
        # Buttons
        btn_frame = ttk.Frame(card)
        btn_frame.pack(fill="x", pady=ModernStyles.SPACE_6)
        
        self.login_btn = ModernButton(btn_frame, text="Sign In", 
                                     command=self._on_login,
                                     variant="primary")
        self.login_btn.pack(fill="x", pady=ModernStyles.SPACE_2)
        
        self.register_btn = ModernButton(btn_frame, text="Create Account",
                                        command=self._on_register)
        self.register_btn.pack(fill="x", pady=ModernStyles.SPACE_2)
        
        # Bind Enter key
        self.root.bind('<Return>', lambda e: self._on_login())
        
        self.current_view = container
    
    def _on_login(self):
        """Handle login."""
        username = self.auth_username.get()
        password = self.auth_password.get()
        
        if not username or not password:
            messagebox.showwarning("Login", "Please enter username and password")
            return
        
        asyncio.run_coroutine_threadsafe(
            self._do_login(username, password), self._loop
        )
    
    async def _do_login(self, username: str, password: str):
        """Perform login."""
        try:
            response = await self._api_client.login(username, password)
            
            if response.get("success"):
                self._username = username
                self._token = response.get("token")
                self._api_client.username = username
                self._api_client.token = self._token
                
                self.root.after(0, self._show_chat_view)
            else:
                error = response.get("message", "Login failed")
                self.root.after(0, lambda: messagebox.showerror("Login Failed", error))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    def _on_register(self):
        """Handle register."""
        username = self.auth_username.get()
        password = self.auth_password.get()
        
        if not username or not password:
            messagebox.showwarning("Register", "Please enter username and password")
            return
        
        asyncio.run_coroutine_threadsafe(
            self._do_register(username, password), self._loop
        )
    
    async def _do_register(self, username: str, password: str):
        """Perform registration."""
        try:
            response = await self._api_client.register(username, password)
            
            if response.get("success"):
                self.root.after(0, lambda: messagebox.showinfo(
                    "Success", "Account created! Please sign in."
                ))
            else:
                error = response.get("message", "Registration failed")
                self.root.after(0, lambda: messagebox.showerror("Registration Failed", error))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    def _show_chat_view(self):
        """Show chat view."""
        self._clear_view()
        self._running = True
        
        # Configure grid
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ttk.Frame(self.root, padding=ModernStyles.SPACE_3)
        header.grid(row=0, column=0, sticky="ew")
        
        header_left = ttk.Frame(header)
        header_left.pack(side="left")
        
        title = ttk.Label(header_left, text="AloneChat",
                         font=(ModernStyles.FONT_FAMILY, ModernStyles.LG, "bold"))
        title.pack(side="left")
        
        user_label = ttk.Label(header_left, text=f"  |  {self._username}",
                              font=(ModernStyles.FONT_FAMILY, ModernStyles.SM),
                              foreground=Theme.text_secondary)
        user_label.pack(side="left")
        
        logout_btn = ModernButton(header, text="Logout", 
                                 command=self._on_logout, width=10)
        logout_btn.pack(side="right")
        
        # Messages area
        self.messages_container = ScrollableFrame(self.root)
        self.messages_container.grid(row=1, column=0, sticky="nsew", 
                                    padx=ModernStyles.SPACE_4, pady=ModernStyles.SPACE_3)
        
        # Input area
        input_frame = ttk.Frame(self.root, padding=ModernStyles.SPACE_4)
        input_frame.grid(row=2, column=0, sticky="ew")
        
        self.msg_entry = ModernEntry(input_frame, placeholder="Type a message...")
        self.msg_entry.pack(side="left", fill="x", expand=True)
        
        send_btn = ModernButton(input_frame, text="Send", 
                               command=self._on_send, width=10)
        send_btn.pack(side="right", padx=(ModernStyles.SPACE_3, 0))
        
        # Bind shortcuts
        self.msg_entry.entry.bind('<Return>', lambda e: self._on_send())
        self.root.bind('<Control-l>', lambda e: self._on_logout())
        
        # Start polling
        asyncio.run_coroutine_threadsafe(self._poll_messages(), self._loop)
        
        # Add welcome message
        self._add_system_message("Connected to server")
    
    def _on_send(self):
        """Handle send."""
        content = self.msg_entry.get()
        if not content.strip():
            return
        
        self.msg_entry.var.set("")
        
        asyncio.run_coroutine_threadsafe(
            self._send_message(content), self._loop
        )
    
    async def _send_message(self, content: str):
        """Send message."""
        try:
            response = await self._api_client.send_message(content)
            
            if response.get("success"):
                self.root.after(0, lambda: self._add_message(
                    self._username, content, is_self=True
                ))
            else:
                error = response.get("message", "Failed to send")
                self.root.after(0, lambda: self._add_system_message(f"Error: {error}"))
        except Exception as e:
            self.root.after(0, lambda: self._add_system_message(f"Error: {str(e)}"))
    
    async def _poll_messages(self):
        """Poll for messages."""
        while self._running:
            try:
                msg = await self._api_client.receive_message()
                
                if isinstance(msg, dict) and msg.get("success"):
                    sender = msg.get("sender")
                    content = msg.get("content")
                    
                    if sender and content and sender != self._username:
                        self.root.after(0, lambda s=sender, c=content: 
                                       self._add_message(s, c, is_self=False))
                
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.5)
    
    def _add_message(self, sender: str, content: str, is_self: bool = False):
        """Add message to chat."""
        card = MessageCard(self.messages_container.content, sender, content, is_self)
        card.pack(fill="x", pady=ModernStyles.SPACE_1)
        self.messages_container.scroll_to_bottom()
    
    def _add_system_message(self, content: str):
        """Add system message."""
        card = MessageCard(self.messages_container.content, "System", content, 
                          is_system=True)
        card.pack(fill="x", pady=ModernStyles.SPACE_1)
        self.messages_container.scroll_to_bottom()
    
    def _on_logout(self):
        """Handle logout."""
        self._running = False
        asyncio.run_coroutine_threadsafe(self._do_logout(), self._loop)
    
    async def _do_logout(self):
        """Perform logout."""
        try:
            await self._api_client.logout()
        except:
            pass
        finally:
            self.root.after(0, self._show_auth_view)
    
    def _on_close(self):
        """Handle window close."""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.root.destroy()


__all__ = ['SimpleGUIClient', 'ModernButton', 'ModernEntry', 'MessageCard', 
           'ScrollableFrame', 'Theme', 'ModernStyles']
