"""
Components using sv_ttk (Sun Valley theme) - standard ttk widgets.
"""
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable


class WinUI3Button(ttk.Frame):
    """Button using ttk with sv_ttk theme."""
    
    def __init__(self, parent, text: str, command: Optional[Callable] = None,
                 variant: str = "accent", width: int = 20, **kwargs):
        super().__init__(parent, **kwargs)
        
        # Create ttk button
        self.button = ttk.Button(self, text=text, command=command, width=width)
        self.button.pack(fill="both", expand=True)


class ModernButton(WinUI3Button):
    """Backward compatibility."""
    pass


class WinUI3Entry(ttk.Frame):
    """Entry field using ttk with sv_ttk theme.
    
    NOTE: Placeholder functionality removed to avoid widget lifecycle issues.
    Use set() method to pre-populate if needed.
    """
    
    def __init__(self, parent, label: str = "", placeholder: str = "",
                 password: bool = False, width: int = 40, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.placeholder = placeholder  # Kept for API compatibility
        
        # Label
        if label:
            self.label_widget = ttk.Label(self, text=label)
            self.label_widget.pack(anchor="w", pady=(0, 4))
        
        # Entry widget - simple ttk.Entry without placeholder magic
        self.entry = ttk.Entry(self, width=width, show="*" if password else "")
        self.entry.pack(fill="x")
    
    def get(self) -> str:
        """Get entry value."""
        try:
            return self.entry.get()
        except tk.TclError:
            # Widget was destroyed
            return ""
    
    def set(self, value: str):
        """Set entry value."""
        try:
            self.entry.delete(0, tk.END)
            self.entry.insert(0, value)
        except tk.TclError:
            # Widget was destroyed
            pass


class ModernEntry(WinUI3Entry):
    """Backward compatibility."""
    pass


class BoundedFrame(ttk.Frame):
    """Frame with bounds management."""
    
    def __init__(self, parent, min_width: int = 200, min_height: int = 100, **kwargs):
        super().__init__(parent, **kwargs)
        self.min_width = min_width
        self.min_height = min_height
        self._setup_responsive_behavior()
    
    def _setup_responsive_behavior(self):
        """Setup responsive sizing behavior."""
        def on_configure(event):
            if event.width < self.min_width or event.height < self.min_height:
                self.configure(width=max(event.width, self.min_width),
                             height=max(event.height, self.min_height))
        
        self.bind('<Configure>', on_configure)


class WinUI3ScrollableFrame(ttk.Frame):
    """Scrollable frame using ttk with sv_ttk theme."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self, highlightthickness=0)
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
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            canvas_width = self.canvas.winfo_width()
            self.canvas.itemconfig(self.content_window, width=canvas_width)
        
        def on_canvas_configure(event):
            self.canvas.itemconfig(self.content_window, width=event.width)
        
        self.content.bind('<Configure>', on_content_configure)
        self.canvas.bind('<Configure>', on_canvas_configure)
        
        def on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.canvas.bind_all("<MouseWheel>", on_mousewheel)
    
    def scroll_to_bottom(self):
        """Scroll to bottom."""
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)
    
    def scroll_to_widget(self, widget: tk.Widget):
        """Scroll to widget."""
        try:
            self.canvas.update_idletasks()
            y = widget.winfo_y()
            h = max(1, self.content.winfo_height())
            pos = max(0.0, min(1.0, (y - 20) / h))
            self.canvas.yview_moveto(pos)
        except Exception:
            pass


class ScrollableFrame(WinUI3ScrollableFrame):
    """Backward compatibility."""
    pass
