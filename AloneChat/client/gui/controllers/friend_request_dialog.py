"""
Friend request dialog for managing incoming friend requests.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, List, Dict, Any, Optional


class FriendRequestDialog:
    """Dialog for displaying and managing friend requests."""
    
    def __init__(
        self,
        parent: tk.Tk,
        on_accept: Callable[[str], None],
        on_reject: Callable[[str], None],
        on_refresh: Callable[[], None]
    ):
        self.parent = parent
        self.on_accept = on_accept
        self.on_reject = on_reject
        self.on_refresh = on_refresh
        
        self.window: Optional[tk.Toplevel] = None
        self.requests_tree: Optional[ttk.Treeview] = None
        self._requests: List[Dict[str, Any]] = []
    
    def show(self) -> None:
        """Show the dialog."""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return
        
        self.window = tk.Toplevel(self.parent)
        self.window.title("Friend Requests")
        self.window.geometry("420x350")
        self.window.minsize(350, 280)
        self.window.transient(self.parent)
        self.window.resizable(True, True)
        
        self._build_ui()
        
        self.window.update_idletasks()
        self.window.geometry("")
    
    def hide(self) -> None:
        """Hide the dialog."""
        if self.window:
            self.window.destroy()
            self.window = None
    
    def _build_ui(self) -> None:
        """Build the dialog UI."""
        main_frame = ttk.Frame(self.window, padding=16)
        main_frame.pack(fill="both", expand=True)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 12))
        
        ttk.Label(header_frame, text="Incoming Friend Requests", font=('', 11, 'bold')).pack(side="left")
        ttk.Button(header_frame, text="Refresh", command=self._on_refresh, width=10).pack(side="right")
        
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True, pady=(0, 12))
        
        columns = ("from", "message", "time")
        self.requests_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=10)
        self.requests_tree.heading("from", text="From")
        self.requests_tree.heading("message", text="Message")
        self.requests_tree.heading("time", text="Time")
        self.requests_tree.column("from", width=100, minwidth=80)
        self.requests_tree.column("message", width=180, minwidth=100)
        self.requests_tree.column("time", width=120, minwidth=80)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.requests_tree.yview)
        self.requests_tree.configure(yscrollcommand=scrollbar.set)
        
        self.requests_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill="x")
        
        ttk.Button(action_frame, text="Accept", command=self._on_accept, width=10).pack(side="left", padx=(0, 8))
        ttk.Button(action_frame, text="Reject", command=self._on_reject, width=10).pack(side="left")
    
    def set_requests(self, requests: List[Dict[str, Any]]) -> None:
        """Set the request list."""
        self._requests = requests
        self._refresh_list()
    
    def _refresh_list(self) -> None:
        """Refresh the treeview."""
        if not self.requests_tree:
            return
        
        for item in self.requests_tree.get_children():
            self.requests_tree.delete(item)
        
        if not self._requests:
            self.requests_tree.insert("", "end", values=("No pending requests", "", ""))
            return
        
        for req in self._requests:
            request_id = req.get("id", "")
            from_user = req.get("from_user", "")
            message = req.get("message", "")
            created_at = req.get("created_at", "")
            
            if created_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    time_str = created_at[:16] if len(created_at) > 16 else created_at
            else:
                time_str = ""
            
            self.requests_tree.insert("", "end", iid=request_id, values=(from_user, message, time_str))
    
    def _get_selected_request(self) -> Optional[str]:
        """Get selected request ID."""
        if not self.requests_tree:
            return None
        selection = self.requests_tree.selection()
        if selection:
            return selection[0]
        return None
    
    def _on_accept(self) -> None:
        """Accept selected request."""
        request_id = self._get_selected_request()
        if not request_id:
            messagebox.showinfo("Friend Request", "Please select a request")
            return
        
        self.on_accept(request_id)
    
    def _on_reject(self) -> None:
        """Reject selected request."""
        request_id = self._get_selected_request()
        if not request_id:
            messagebox.showinfo("Friend Request", "Please select a request")
            return
        
        if messagebox.askyesno("Reject Request", "Reject this friend request?"):
            self.on_reject(request_id)
    
    def _on_refresh(self) -> None:
        """Refresh request list."""
        self.on_refresh()


__all__ = ['FriendRequestDialog']
