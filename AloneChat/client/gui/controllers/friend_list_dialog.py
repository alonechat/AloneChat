"""
Friend list dialog for managing friends.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, List, Dict, Any, Optional


class FriendListDialog:
    """Dialog for displaying and managing friends."""
    
    def __init__(
        self,
        parent: tk.Tk,
        on_start_chat: Callable[[str], None],
        on_remove_friend: Callable[[str], None],
        on_set_remark: Callable[[str, str], None],
        on_refresh: Callable[[], None],
        on_add_friend: Optional[Callable[[], None]] = None
    ):
        self.parent = parent
        self.on_start_chat = on_start_chat
        self.on_remove_friend = on_remove_friend
        self.on_set_remark = on_set_remark
        self.on_refresh = on_refresh
        self.on_add_friend = on_add_friend
        
        self.window: Optional[tk.Toplevel] = None
        self.friends_tree: Optional[ttk.Treeview] = None
        self._friends: List[Dict[str, Any]] = []
    
    def show(self) -> None:
        """Show the dialog."""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return
        
        self.window = tk.Toplevel(self.parent)
        self.window.title("Friends")
        self.window.geometry("420x400")
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
        
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 12))
        
        ttk.Label(header_frame, text="My Friends", font=('', 11, 'bold')).pack(side="left")
        
        btn_header_frame = ttk.Frame(header_frame)
        btn_header_frame.pack(side="right")
        
        ttk.Button(btn_header_frame, text="Refresh", command=self._on_refresh, width=10).pack(side="left", padx=(0, 4))
        
        if self.on_add_friend:
            ttk.Button(btn_header_frame, text="Add Friend", command=self.on_add_friend, width=10).pack(side="left")
        
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True, pady=(0, 12))
        
        columns = ("name", "status", "remark")
        self.friends_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=12)
        self.friends_tree.heading("name", text="Name")
        self.friends_tree.heading("status", text="Status")
        self.friends_tree.heading("remark", text="Remark")
        self.friends_tree.column("name", width=120, minwidth=80)
        self.friends_tree.column("status", width=100, minwidth=80)
        self.friends_tree.column("remark", width=150, minwidth=80)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.friends_tree.yview)
        self.friends_tree.configure(yscrollcommand=scrollbar.set)
        
        self.friends_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        self.friends_tree.bind("<Double-1>", self._on_double_click)
        self.friends_tree.bind("<Button-3>", self._on_right_click)
        
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill="x")
        
        ttk.Button(action_frame, text="Chat", command=self._on_chat, width=10).pack(side="left", padx=(0, 8))
        ttk.Button(action_frame, text="Set Remark", command=self._on_set_remark, width=10).pack(side="left", padx=(0, 8))
        ttk.Button(action_frame, text="Remove", command=self._on_remove, width=10).pack(side="left")
    
    def set_friends(self, friends: List[Dict[str, Any]]) -> None:
        """Set the friend list."""
        self._friends = friends
        self._refresh_list()
    
    def _refresh_list(self) -> None:
        """Refresh the treeview."""
        if not self.friends_tree:
            return
        
        for item in self.friends_tree.get_children():
            self.friends_tree.delete(item)
        
        if not self._friends:
            self.friends_tree.insert("", "end", values=("No friends yet", "", ""))
            return
        
        for friend in self._friends:
            user_id = friend.get("user_id", "")
            display_name = friend.get("display_name", user_id)
            remark = friend.get("remark", "")
            status = friend.get("status", "offline")
            is_online = friend.get("is_online", False)
            
            status_text = f"{'🟢' if is_online else '⚫'} {status}"
            name_text = remark if remark else display_name
            
            self.friends_tree.insert("", "end", iid=user_id, values=(name_text, status_text, remark))
    
    def _get_selected_friend(self) -> Optional[str]:
        """Get selected friend ID."""
        if not self.friends_tree:
            return None
        selection = self.friends_tree.selection()
        if selection:
            return selection[0]
        return None
    
    def _on_double_click(self, event) -> None:
        """Handle double click to start chat."""
        self._on_chat()
    
    def _on_right_click(self, event) -> None:
        """Handle right click for context menu."""
        friend_id = self._get_selected_friend()
        if not friend_id:
            return
        
        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label="Start Chat", command=self._on_chat)
        menu.add_command(label="Set Remark", command=self._on_set_remark)
        menu.add_separator()
        menu.add_command(label="Remove Friend", command=self._on_remove)
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _on_chat(self) -> None:
        """Start chat with selected friend."""
        friend_id = self._get_selected_friend()
        if friend_id:
            self.on_start_chat(friend_id)
            self.hide()
    
    def _on_set_remark(self) -> None:
        """Set remark for selected friend."""
        friend_id = self._get_selected_friend()
        if not friend_id:
            return
        
        current_remark = ""
        for f in self._friends:
            if f.get("user_id") == friend_id:
                current_remark = f.get("remark", "")
                break
        
        dialog = tk.Toplevel(self.window)
        dialog.title("Set Remark")
        dialog.geometry("320x120")
        dialog.minsize(280, 100)
        dialog.transient(self.window)
        dialog.grab_set()
        dialog.resizable(True, False)
        
        main_frame = ttk.Frame(dialog, padding=16)
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(main_frame, text=f"Remark for {friend_id}:").pack(anchor="w", pady=(0, 8))
        
        entry = ttk.Entry(main_frame)
        entry.insert(0, current_remark)
        entry.pack(fill="x", pady=(0, 12))
        entry.focus_set()
        entry.select_range(0, tk.END)
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x")
        
        def on_ok():
            remark = entry.get().strip()
            self.on_set_remark(friend_id, remark)
            dialog.destroy()
        
        ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).pack(side="left")
        
        entry.bind("<Return>", lambda e: on_ok())
        entry.bind("<Escape>", lambda e: dialog.destroy())
    
    def _on_remove(self) -> None:
        """Remove selected friend."""
        friend_id = self._get_selected_friend()
        if not friend_id:
            return
        
        if messagebox.askyesno("Remove Friend", f"Remove {friend_id} from friends?"):
            self.on_remove_friend(friend_id)
    
    def _on_refresh(self) -> None:
        """Refresh friend list."""
        self.on_refresh()


__all__ = ['FriendListDialog']
