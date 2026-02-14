"""
Search dialog for finding messages - sv_ttk styled.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable


class SearchDialog:
    """Floating search dialog for message search."""
    
    def __init__(self, root: tk.Tk, on_search: Callable[[str], int],
                 on_next: Callable[[], None],
                 on_prev: Callable[[], None],
                 on_close: Callable[[], None]):
        self.root = root
        self.on_search = on_search
        self.on_next = on_next
        self.on_prev = on_prev
        self.on_close = on_close
        
        self.window = None
        self.search_var = None
    
    def show(self):
        """Show the search dialog."""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return
        
        self.window = tk.Toplevel(self.root)
        self.window.title("Search")
        self.window.geometry("420x110")
        self.window.resizable(False, False)
        
        self.search_var = tk.StringVar()
        
        frm = ttk.Frame(self.window, padding=16)
        frm.pack(fill="both", expand=True)
        
        ttk.Label(frm, text="Find in messages:").pack(anchor="w")
        ent = ttk.Entry(frm, textvariable=self.search_var)
        ent.pack(fill="x", pady=8)
        ent.focus_set()
        
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Prev", command=self.on_prev).pack(side="left")
        ttk.Button(btns, text="Next", command=self.on_next).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Close", command=self._on_close).pack(side="right")
        
        ent.bind("<Return>", lambda e: self.on_next())
        self.window.bind("<Escape>", lambda e: self._on_close())
        self.search_var.trace_add("write", lambda *_: self._on_search())
        
        self._on_search()
    
    def _on_search(self):
        """Handle search text change."""
        query = self.search_var.get() if self.search_var else ""
        self.on_search(query)
    
    def _on_close(self):
        """Handle close button."""
        self.on_close()
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
        self.window = None
    
    def hide(self):
        """Hide the search dialog."""
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
        self.window = None
    
    def get_query(self) -> str:
        """Get current search query."""
        return self.search_var.get() if self.search_var else ""
