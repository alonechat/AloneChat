"""
Add friend dialog for searching and adding friends.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, List, Dict, Any, Optional


class AddFriendDialog:
    """Dialog for searching users and sending friend requests."""
    
    def __init__(
        self,
        parent: tk.Tk,
        on_search: Callable[[str, Callable[[List[Dict[str, Any]]], None]], None],
        on_send_request: Callable[[str, str], None],
        current_user: str
    ):
        self.parent = parent
        self.on_search = on_search
        self.on_send_request = on_send_request
        self.current_user = current_user
        
        self.window: Optional[tk.Toplevel] = None
        self.search_entry: Optional[ttk.Entry] = None
        self.results_tree: Optional[ttk.Treeview] = None
        self.message_entry: Optional[ttk.Entry] = None
        self._results: List[Dict[str, Any]] = []
    
    def show(self) -> None:
        """Show the dialog."""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return
        
        self.window = tk.Toplevel(self.parent)
        self.window.title("Add Friend")
        self.window.geometry("420x380")
        self.window.minsize(350, 300)
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
        
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill="x", pady=(0, 12))
        
        ttk.Label(search_frame, text="Search:").pack(side="left", padx=(0, 8))
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self._do_search())
        ttk.Button(search_frame, text="Search", command=self._do_search, width=10).pack(side="left")
        
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True, pady=(0, 12))
        
        columns = ("name", "status", "relation")
        self.results_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=10)
        self.results_tree.heading("name", text="Username")
        self.results_tree.heading("status", text="Status")
        self.results_tree.heading("relation", text="Relation")
        self.results_tree.column("name", width=120, minwidth=80)
        self.results_tree.column("status", width=100, minwidth=80)
        self.results_tree.column("relation", width=100, minwidth=80)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        self.results_tree.bind("<Double-1>", self._on_double_click)
        
        msg_frame = ttk.Frame(main_frame)
        msg_frame.pack(fill="x", pady=(0, 12))
        
        ttk.Label(msg_frame, text="Message (optional):").pack(anchor="w", pady=(0, 4))
        self.message_entry = ttk.Entry(msg_frame)
        self.message_entry.pack(fill="x")
        
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill="x")
        
        ttk.Button(action_frame, text="Add Friend", command=self._on_add, width=12).pack(side="left")
    
    def _do_search(self) -> None:
        """Execute search."""
        if not self.search_entry:
            return
        
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showinfo("Search", "Please enter a username to search")
            return
        
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.results_tree.insert("", "end", values=("Searching...", "", ""))
        
        self.on_search(query, self._on_search_result)
    
    def _on_search_result(self, results: List[Dict[str, Any]]) -> None:
        """Callback when search results are ready."""
        if not self.window or not self.window.winfo_exists():
            return
        
        self._results = results
        self._refresh_results()
    
    def _refresh_results(self) -> None:
        """Refresh the results treeview."""
        if not self.results_tree:
            return
        
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        if not self._results:
            self.results_tree.insert("", "end", values=("No users found", "", ""))
            return
        
        for user in self._results:
            user_id = user.get("user_id", "")
            status = user.get("status", "offline")
            is_online = user.get("is_online", False)
            is_friend = user.get("is_friend", False)
            has_pending = user.get("has_pending_request", False)
            
            status_text = f"{'🟢' if is_online else '⚫'} {status}"
            
            if is_friend:
                relation_text = "Friend"
            elif has_pending:
                relation_text = "Pending"
            else:
                relation_text = "-"
            
            self.results_tree.insert("", "end", iid=user_id, values=(user_id, status_text, relation_text))
    
    def _get_selected_user(self) -> Optional[str]:
        """Get selected user ID."""
        if not self.results_tree:
            return None
        selection = self.results_tree.selection()
        if selection:
            return selection[0]
        return None
    
    def _on_double_click(self, event) -> None:
        """Handle double click to add friend."""
        self._on_add()
    
    def _on_add(self) -> None:
        """Send friend request to selected user."""
        user_id = self._get_selected_user()
        if not user_id:
            messagebox.showinfo("Add Friend", "Please select a user")
            return
        
        for user in self._results:
            if user.get("user_id") == user_id:
                if user.get("is_friend"):
                    messagebox.showinfo("Add Friend", "Already friends with this user")
                    return
                if user.get("has_pending_request"):
                    messagebox.showinfo("Add Friend", "A pending request already exists")
                    return
                break
        
        message = ""
        if self.message_entry:
            message = self.message_entry.get().strip()
        
        self.on_send_request(user_id, message)
        self._do_search()


__all__ = ['AddFriendDialog']
