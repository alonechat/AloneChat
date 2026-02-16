"""
Input area component for chat view.
Contains reply banner, message entry, and send button.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, TYPE_CHECKING

from ..models.data import ReplyContext


class InputArea:
    """Message input area with reply banner and send button."""
    
    def __init__(self, parent: ttk.Frame,
                 on_send: Callable[[str], None],
                 on_clear_reply: Callable[[], None]):
        self.parent = parent
        self.on_send = on_send
        self.on_clear_reply = on_clear_reply
        
        self.frame: Optional[ttk.LabelFrame] = None
        self.reply_banner: Optional[ttk.Frame] = None
        self.reply_label: Optional[ttk.Label] = None
        self.msg_entry: Optional[ttk.Entry] = None
    
    def build(self) -> ttk.LabelFrame:
        """Build and return the input frame."""
        self.frame = ttk.LabelFrame(self.parent, text="", padding=(16, 12))
        
        self._build_reply_banner()
        self._build_entry_row()
        
        return self.frame
    
    def _build_reply_banner(self):
        """Build the reply banner."""
        self.reply_banner = ttk.Frame(self.frame)
        self.reply_label = ttk.Label(self.reply_banner, text="")
        self.reply_label.pack(side="left", fill="x", expand=True)
        
        close_btn = ttk.Label(self.reply_banner, text="✕", cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.on_clear_reply())
        self.reply_banner.pack_forget()
    
    def _build_entry_row(self):
        """Build the entry row with input and send button."""
        entry_row = ttk.Frame(self.frame)
        entry_row.pack(fill="x", pady=(8, 0))
        
        self.msg_entry = ttk.Entry(entry_row)
        self.msg_entry.pack(side="left", fill="x", expand=True)
        self.msg_entry.bind('<Return>', self._on_enter_pressed)
        
        ttk.Button(entry_row, text="Send",
                  command=self._on_send_clicked).pack(side="right", padx=(12, 0))
    
    def _on_send_clicked(self):
        """Handle send button click."""
        content = self.msg_entry.get() if self.msg_entry else ""
        if content.strip():
            self.on_send(content)
    
    def _on_enter_pressed(self, event=None):
        """Handle Enter key in message entry."""
        self._on_send_clicked()
        return "break"
    
    def show_reply_banner(self, ctx: ReplyContext):
        """Show reply banner with context."""
        if self.reply_banner and self.reply_label:
            snippet = ctx.get_snippet(80)
            self.reply_label.config(
                text=f"Replying to {ctx.sender} ({ctx.timestamp}): {snippet}")
            self.reply_banner.pack(fill="x", pady=(0, 8))
    
    def hide_reply_banner(self):
        """Hide the reply banner."""
        if self.reply_banner:
            self.reply_banner.pack_forget()
    
    def clear_message_entry(self):
        """Clear the message entry field."""
        if self.msg_entry:
            self.msg_entry.delete(0, tk.END)
    
    def destroy(self):
        """Destroy the input frame."""
        if self.frame:
            self.frame.destroy()
            self.frame = None
