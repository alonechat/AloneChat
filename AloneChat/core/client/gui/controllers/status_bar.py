"""
Status bar component for displaying connection status.
Designed to match Sun Valley / WinUI3 style.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional


class StatusBar(ttk.Frame):
    """
    Status bar for displaying connection and application status.
    
    Designed to match Sun Valley / WinUI3 design language:
    - Subtle separator at top
    - Compact padding
    - Muted colors for status text
    """
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self._connected = False
        
        self._separator: Optional[ttk.Separator] = None
        self._status_frame: Optional[ttk.Frame] = None
        self._status_icon: Optional[ttk.Label] = None
        self._status_label: Optional[ttk.Label] = None
        
        self._build_ui()
    
    def _build_ui(self) -> None:
        """Build the status bar UI."""
        self.columnconfigure(1, weight=1)
        
        self._separator = ttk.Separator(self, orient="horizontal")
        self._separator.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 1))
        
        self._status_frame = ttk.Frame(self)
        self._status_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 6))
        
        self._status_icon = ttk.Label(
            self._status_frame,
            text="○",
            font=("Segoe UI", 10),
            foreground="#888888"
        )
        self._status_icon.pack(side="left")
        
        self._status_label = ttk.Label(
            self._status_frame,
            text="Disconnected",
            font=("Segoe UI", 9),
            foreground="#888888"
        )
        self._status_label.pack(side="left", padx=(6, 0))
        
        version_label = ttk.Label(
            self._status_frame,
            text="AloneChat",
            font=("Segoe UI", 9),
            foreground="#666666"
        )
        version_label.pack(side="right")
    
    def set_connected(self, connected: bool, message: Optional[str] = None) -> None:
        """
        Set connection status.
        
        Args:
            connected: Whether connected to server
            message: Optional status message
        """
        self._connected = connected
        
        if not self._status_icon or not self._status_label:
            return
        
        if connected:
            self._status_icon.config(text="●", foreground="#107c10")
            self._status_label.config(
                text=message or "Connected",
                foreground="#107c10"
            )
        else:
            icon_text = "◐" if message and "reconnect" in message.lower() else "○"
            icon_color = "#d83b01" if message and "reconnect" in message.lower() else "#888888"
            text_color = "#d83b01" if message and "reconnect" in message.lower() else "#888888"
            
            self._status_icon.config(text=icon_text, foreground=icon_color)
            self._status_label.config(
                text=message or "Disconnected",
                foreground=text_color
            )
    
    def set_status(self, message: str, color: Optional[str] = None) -> None:
        """
        Set custom status message.
        
        Args:
            message: Status message to display
            color: Optional text color (hex or named color)
        """
        if self._status_label:
            self._status_label.config(
                text=message,
                foreground=color or "#888888"
            )
    
    def set_connecting(self) -> None:
        """Set status to connecting state."""
        if self._status_icon and self._status_label:
            self._status_icon.config(text="◐", foreground="#ff8c00")
            self._status_label.config(text="Connecting...", foreground="#ff8c00")


__all__ = ['StatusBar']
