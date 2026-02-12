"""
Message card using pure ttk widgets for sv_ttk compatibility.
Clean, modern design with Windows 11 styling.
"""
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable
from datetime import datetime


class WinUI3MessageCard(ttk.Frame):
    """Message card using pure ttk widgets for sv_ttk styling."""
    
    def __init__(self, parent, sender: str, content: str,
                 is_self: bool = False, is_system: bool = False,
                 timestamp: Optional[str] = None,
                 status: Optional[str] = None,
                 on_retry: Optional[Callable[[], None]] = None,
                 on_reply: Optional[Callable[[str, str, str], None]] = None,
                 **kwargs):
        super().__init__(parent, padding=4, **kwargs)
        
        self.sender = sender
        self.content = content
        self.is_self = is_self
        self.is_system = is_system
        self.timestamp = timestamp or datetime.now().strftime("%H:%M")
        self.status = status
        self.on_retry = on_retry
        self.on_reply = on_reply
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the message card UI using ttk widgets."""
        if self.is_system:
            self._build_system_ui()
        elif self.is_self:
            self._build_self_ui()
        else:
            self._build_other_ui()
    
    def _build_system_ui(self):
        """Build system message UI - centered, muted style."""
        container = ttk.Frame(self)
        container.pack(fill="x", expand=True)
        
        # Center frame
        center = ttk.Frame(container)
        center.pack(expand=True)
        
        # System message with separator lines
        sep1 = ttk.Separator(center, orient="horizontal")
        sep1.pack(fill="x", pady=4)
        
        msg_frame = ttk.Frame(center)
        msg_frame.pack(fill="x", padx=20)
        
        ttk.Label(msg_frame, text=self.content, wraplength=500).pack()
        ttk.Label(msg_frame, text=self.timestamp).pack()
        
        sep2 = ttk.Separator(center, orient="horizontal")
        sep2.pack(fill="x", pady=4)
    
    def _build_self_ui(self):
        """Build self (sent) message UI - right aligned in a bubble."""
        outer = ttk.Frame(self)
        outer.pack(fill="x")
        
        # Spacer to push content right
        ttk.Frame(outer).pack(side="left", expand=True, fill="x")
        
        # Message bubble container
        bubble_container = ttk.Frame(outer)
        bubble_container.pack(side="right", padx=8)
        
        # Message bubble using Labelframe for border effect
        bubble = ttk.Labelframe(bubble_container, text="", padding=8)
        bubble.pack(fill="x")
        
        # Reply button in top-right
        if self.on_reply is not None:
            header = ttk.Frame(bubble)
            header.pack(fill="x")
            ttk.Frame(header).pack(side="left", expand=True)
            reply_btn = ttk.Button(header, text="Reply", width=6,
                                  command=lambda: self.on_reply(self.sender, self.content, self.timestamp))
            reply_btn.pack(side="right")
        
        # Message content - wraplength for high-DPI displays
        content_lbl = ttk.Label(bubble, text=self.content, wraplength=500, justify="left")
        content_lbl.pack(anchor="e")
        self._content_label = content_lbl
        
        # Footer with timestamp and status
        footer = ttk.Frame(bubble)
        footer.pack(fill="x", pady=(4, 0))
        
        if self.status:
            self._status_label = ttk.Label(footer, text=self.status)
            self._status_label.pack(side="right", padx=(8, 0))
        
        ttk.Label(footer, text=self.timestamp).pack(side="right")
    
    def _build_other_ui(self):
        """Build other (received) message UI - left aligned in a bubble."""
        outer = ttk.Frame(self)
        outer.pack(fill="x")
        
        # Message bubble container
        bubble_container = ttk.Frame(outer)
        bubble_container.pack(side="left", padx=8)
        
        # Message bubble
        bubble = ttk.Labelframe(bubble_container, text="", padding=8)
        bubble.pack(fill="x")
        
        # Reply button in top-right
        if self.on_reply is not None:
            header = ttk.Frame(bubble)
            header.pack(fill="x")
            ttk.Frame(header).pack(side="left", expand=True)
            reply_btn = ttk.Button(header, text="Reply", width=6,
                                  command=lambda: self.on_reply(self.sender, self.content, self.timestamp))
            reply_btn.pack(side="right")
        
        # Sender name
        sender_frame = ttk.Frame(bubble)
        sender_frame.pack(fill="x")
        ttk.Label(sender_frame, text=self.sender).pack(anchor="w")
        
        # Message content - wraplength for high-DPI displays
        content_lbl = ttk.Label(bubble, text=self.content, wraplength=500, justify="left")
        content_lbl.pack(anchor="w", pady=(4, 0))
        self._content_label = content_lbl
        
        # Footer with timestamp
        footer = ttk.Frame(bubble)
        footer.pack(fill="x", pady=(4, 0))
        ttk.Label(footer, text=self.timestamp).pack(side="left")
        
        # Spacer
        ttk.Frame(outer).pack(side="left", expand=True, fill="x")
    
    def update_status(self, text: str, is_error: bool = False,
                      on_retry: Optional[Callable[[], None]] = None):
        """Update delivery status text for self message."""
        self.status = text
        if hasattr(self, '_status_label') and self._status_label:
            self._status_label.config(text=text)
            if is_error and on_retry:
                self._status_label.config(foreground="red")
                self._status_label.bind("<Button-1>", lambda e: on_retry())
    
    def set_highlight(self, on: bool, strong: bool = False):
        """Highlight this message card."""
        pass


class MessageCard(WinUI3MessageCard):
    """Backward compatibility alias for WinUI3MessageCard."""
    pass
