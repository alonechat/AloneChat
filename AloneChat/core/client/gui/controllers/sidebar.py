"""Sidebar component for chat view.

Includes:
- Chats tab: conversation dropdown + refresh + user list
- Friends tab: friend list + requests + users (sub-tabs) so nothing is hidden

Why sub-tabs instead of a single long scroll:
On some Windows setups, nested widgets (Treeview/Listbox) swallow mouse-wheel
messages, making a full-page scroll container feel "not scrollable".
Sub-tabs keep every section accessible without relying on page scrolling.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from typing import Callable, Optional, TYPE_CHECKING, List, Dict, Any

if TYPE_CHECKING:
    from ..services.conversation_manager import ConversationManager


class Sidebar:
    """Sidebar with conversations and (optional) friends UI."""

    def __init__(
        self,
        parent: ttk.Frame,
        conversation_manager: 'ConversationManager',
        on_select_conversation: Callable[[str], None],
        on_user_list: Optional[Callable[[], None]] = None,
        on_refresh_users: Optional[Callable[[], None]] = None,
        # Friends callbacks (optional)
        on_open_private: Optional[Callable[[str], None]] = None,
        on_friends_refresh: Optional[Callable[[], None]] = None,
        on_friend_request: Optional[Callable[[str], None]] = None,
        on_friend_accept: Optional[Callable[[str], None]] = None,
        on_friend_reject: Optional[Callable[[str], None]] = None,
    ):
        self.parent = parent
        self.conv_manager = conversation_manager
        self.on_select_conversation = on_select_conversation
        self.on_user_list = on_user_list
        self.on_refresh_users = on_refresh_users

        self.on_open_private = on_open_private
        self.on_friends_refresh = on_friends_refresh
        self.on_friend_request = on_friend_request
        self.on_friend_accept = on_friend_accept
        self.on_friend_reject = on_friend_reject

        self.frame: Optional[ttk.Frame] = None
        self._notebook: Optional[ttk.Notebook] = None

        # Chats UI
        self._conv_tab: Optional[ttk.Frame] = None
        self.conv_combo: Optional[ttk.Combobox] = None
        self.partner_status_label: Optional[ttk.Label] = None

        # Friends UI
        self._friends_tab: Optional[ttk.Frame] = None
        self._friend_add_entry: Optional[ttk.Entry] = None
        self._friends_list: Optional[tk.Listbox] = None
        self._friends_scroll: Optional[ttk.Scrollbar] = None

        # Users (also kept in Chats via "User list" dialog)
        self._users_list: Optional[tk.Listbox] = None
        self._users_scroll: Optional[ttk.Scrollbar] = None
        self._users: List[Dict[str, Any]] = []

        self._incoming_tree: Optional[ttk.Treeview] = None
        self._outgoing_tree: Optional[ttk.Treeview] = None

        self._friends: List[str] = []
        self._incoming: List[Dict[str, Any]] = []
        self._outgoing: List[Dict[str, Any]] = []

    def build(self) -> ttk.Frame:
        """Build and return the sidebar frame."""
        self.frame = ttk.Frame(self.parent, padding=8)

        self._notebook = ttk.Notebook(self.frame)
        self._notebook.pack(fill="both", expand=True)

        self._build_conversations_tab()

        friends_enabled = any([
            self.on_open_private,
            self.on_friends_refresh,
            self.on_friend_request,
            self.on_friend_accept,
            self.on_friend_reject
        ])
        if friends_enabled:
            self._build_friends_tab()

        return self.frame

    # ---------------- Chats ----------------
    def _build_conversations_tab(self) -> None:
        self._conv_tab = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(self._conv_tab, text="Chats")

        ttk.Label(self._conv_tab, text="Conversations:").pack(anchor="w")
        self.conv_combo = ttk.Combobox(self._conv_tab, state="readonly")
        self.conv_combo.pack(fill="x", pady=(6, 8))
        self.conv_combo.bind("<<ComboboxSelected>>", self._on_conv_select)

        self.partner_status_label = ttk.Label(self._conv_tab, text="")
        self.partner_status_label.pack(anchor="w", pady=(0, 8))

        btns = ttk.Frame(self._conv_tab)
        btns.pack(fill="x")
        ttk.Button(btns, text="Refresh", command=self.refresh_conversation_list).pack(side="left", fill="x", expand=True)
        ttk.Button(btns, text="User list", command=self._on_user_list).pack(side="left", padx=(8, 0), fill="x", expand=True)

        ttk.Separator(self._conv_tab).pack(fill="x", pady=(10, 10))
        self.refresh_conversation_list()

    def _on_user_list(self) -> None:
        if self.on_user_list:
            self.on_user_list()

    def _on_conv_select(self, event=None) -> None:
        if not self.conv_combo:
            return
        selection = self.conv_combo.current()
        if selection < 0:
            return
        conv_ids = self.conv_manager.conversation_ids
        if 0 <= selection < len(conv_ids):
            cid = conv_ids[selection]
            self.on_select_conversation(cid)
            self._update_partner_status_label(cid)

    def _update_partner_status_label(self, cid: str) -> None:
        if not self.partner_status_label:
            return
        conv = self.conv_manager.get_conversation(cid)
        if conv and self.conv_manager.is_private_conversation(cid):
            status_text = f"Status: {conv.partner_status}"
            if conv.partner_online:
                status_text += " (online)"
            self.partner_status_label.config(text=status_text)
        else:
            self.partner_status_label.config(text="")

    def refresh_conversation_list(self) -> None:
        if not self.conv_combo:
            return
        labels = self.conv_manager.get_conversation_labels()
        self.conv_combo["values"] = labels
        try:
            idx = self.conv_manager.conversation_ids.index(self.conv_manager.active_cid)
            self.conv_combo.current(idx)
            self._update_partner_status_label(self.conv_manager.active_cid)
        except Exception:
            # no active conversation yet
            pass

    def update_partner_status(self, partner_id: str, is_online: bool, status: str) -> None:
        self.conv_manager.update_partner_status(partner_id, is_online, status)
        if self.conv_manager.active_cid == partner_id:
            self._update_partner_status_label(partner_id)

    # ---------------- Friends ----------------
    def _build_friends_tab(self) -> None:
        self._friends_tab = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(self._friends_tab, text="Friends")

        add_row = ttk.Frame(self._friends_tab)
        add_row.pack(fill="x")
        ttk.Label(add_row, text="Add friend:").pack(side="left")
        self._friend_add_entry = ttk.Entry(add_row)
        self._friend_add_entry.pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(add_row, text="Send", command=self._on_send_request).pack(side="left")
        ttk.Button(add_row, text="Refresh", command=self._on_refresh_friends).pack(side="left", padx=(8, 0))

        ttk.Separator(self._friends_tab).pack(fill="x", pady=(10, 10))

        sub = ttk.Notebook(self._friends_tab)
        sub.pack(fill="both", expand=True)

        # Friends list
        friends_page = ttk.Frame(sub, padding=10)
        sub.add(friends_page, text="Friends")
        ttk.Label(friends_page, text="Your friends (double click to chat):").pack(anchor="w")
        friends_box = ttk.Frame(friends_page)
        friends_box.pack(fill="both", expand=True, pady=(6, 0))
        self._friends_list = tk.Listbox(friends_box)
        self._friends_scroll = ttk.Scrollbar(friends_box, orient="vertical", command=self._friends_list.yview)
        self._friends_list.configure(yscrollcommand=self._friends_scroll.set)
        self._friends_list.pack(side="left", fill="both", expand=True)
        self._friends_scroll.pack(side="right", fill="y")
        self._friends_list.bind("<Double-Button-1>", self._on_friend_double_click)

        # Requests
        reqs_page = ttk.Frame(sub, padding=10)
        sub.add(reqs_page, text="Requests")
        reqs_tabs = ttk.Notebook(reqs_page)
        reqs_tabs.pack(fill="both", expand=True)

        incoming_page = ttk.Frame(reqs_tabs, padding=10)
        outgoing_page = ttk.Frame(reqs_tabs, padding=10)
        reqs_tabs.add(incoming_page, text="Incoming")
        reqs_tabs.add(outgoing_page, text="Outgoing")

        self._incoming_tree = self._build_req_tree(incoming_page)
        buttons = ttk.Frame(incoming_page)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Accept", command=self._on_accept_selected).pack(side="left")
        ttk.Button(buttons, text="Reject", command=self._on_reject_selected).pack(side="left", padx=(8, 0))

        self._outgoing_tree = self._build_req_tree(outgoing_page)

        # Users (kept here for convenience, but Chats keeps User list dialog too)
        users_page = ttk.Frame(sub, padding=10)
        sub.add(users_page, text="Users")
        top = ttk.Frame(users_page)
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text="Refresh users", command=self._on_refresh_users).pack(side="left")
        ttk.Button(top, text="Request selected", command=self._on_request_selected_user).pack(side="left", padx=(8, 0))

        list_box = ttk.Frame(users_page)
        list_box.pack(fill="both", expand=True)
        self._users_list = tk.Listbox(list_box)
        self._users_scroll = ttk.Scrollbar(list_box, orient="vertical", command=self._users_list.yview)
        self._users_list.configure(yscrollcommand=self._users_scroll.set)
        self._users_list.pack(side="left", fill="both", expand=True)
        self._users_scroll.pack(side="right", fill="y")
        # Double-click behavior:
        # - If the user is already a friend: open private chat
        # - Otherwise: send a friend request (simplified flow)
        self._users_list.bind("<Double-Button-1>", self._on_users_double_click)

        self._render_friends()
        self._render_users()
        self._render_requests()

    def _build_req_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=("user", "status", "time"), show="headings", height=10)
        tree.heading("user", text="User")
        tree.heading("status", text="Status")
        tree.heading("time", text="Updated")
        tree.column("user", width=140, anchor="w")
        tree.column("status", width=90, anchor="center")
        tree.column("time", width=160, anchor="w")
        tree.pack(fill="both", expand=True)
        return tree

    # ---- Data setters ----
    def set_users_data(self, users: Optional[List[Any]] = None) -> None:
        if users is not None:
            parsed: List[Dict[str, Any]] = []
            for u in users:
                if isinstance(u, str):
                    parsed.append({"user_id": u, "is_online": True, "status": "online"})
                elif isinstance(u, dict):
                    parsed.append(u)
            self._users = parsed
        self._render_users()

    def set_friends_data(
        self,
        friends: Optional[List[str]] = None,
        incoming: Optional[List[Dict[str, Any]]] = None,
        outgoing: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        if friends is not None:
            self._friends = list(sorted(set([str(x) for x in friends if x])))
        if incoming is not None:
            self._incoming = incoming
        if outgoing is not None:
            self._outgoing = outgoing

        self._render_friends()
        self._render_users()
        self._render_requests()

    # ---- Render helpers ----
    def _render_friends(self) -> None:
        if not self._friends_list:
            return
        self._friends_list.delete(0, tk.END)
        for u in self._friends:
            self._friends_list.insert(tk.END, u)

    def _render_users(self) -> None:
        if not self._users_list:
            return
        self._users_list.delete(0, tk.END)
        for u in self._users or []:
            user_id = u.get("user_id", u.get("display_name", "Unknown"))
            is_online = bool(u.get("is_online", False))
            status = u.get("status", "online" if is_online else "offline")
            icon = "●" if is_online and status != "offline" else "○"
            self._users_list.insert(tk.END, f"{icon} {user_id}")

    def _render_requests(self) -> None:
        if self._incoming_tree:
            self._incoming_tree.delete(*self._incoming_tree.get_children())
            for r in self._incoming or []:
                user = r.get("from_user") or r.get("from") or r.get("user") or ""
                status = r.get("status", "")
                t = r.get("updated_at") or r.get("created_at") or ""
                self._incoming_tree.insert("", "end", values=(user, status, str(t)))
        if self._outgoing_tree:
            self._outgoing_tree.delete(*self._outgoing_tree.get_children())
            for r in self._outgoing or []:
                user = r.get("to_user") or r.get("to") or r.get("user") or ""
                status = r.get("status", "")
                t = r.get("updated_at") or r.get("created_at") or ""
                self._outgoing_tree.insert("", "end", values=(user, status, str(t)))

    # ---- Actions ----
    def _on_refresh_users(self) -> None:
        if self.on_refresh_users:
            try:
                self.on_refresh_users()
            except Exception as e:
                messagebox.showwarning("Users", f"Failed to refresh users: {e}")

    def _on_request_selected_user(self) -> None:
        if not self._users_list or not self.on_friend_request:
            return
        sel = self._users_list.curselection()
        if not sel:
            return
        text = self._users_list.get(sel[0])
        user = text[2:].strip() if len(text) > 2 else text.strip()
        if user:
            self.on_friend_request(user)

    def _on_users_double_click(self, event=None) -> None:
        if not self._users_list:
            return
        sel = self._users_list.curselection()
        if not sel:
            return
        text = self._users_list.get(sel[0])
        user = text[2:].strip() if len(text) > 2 else text.strip()
        user = (user or "").strip()
        if not user:
            return

        # Friend => chat
        if user in set(self._friends or []):
            if self.on_open_private:
                self.on_open_private(user)
            return

        # Not friend => request (confirm to avoid accidental spam)
        if self.on_friend_request:
            if messagebox.askyesno("Add friend", f"Send a friend request to {user}?"):
                self.on_friend_request(user)

    def _on_refresh_friends(self) -> None:
        if self.on_friends_refresh:
            self.on_friends_refresh()

    def _on_send_request(self) -> None:
        if not self.on_friend_request or not self._friend_add_entry:
            return
        to_user = self._friend_add_entry.get().strip()
        if not to_user:
            messagebox.showinfo("Friends", "Please enter a username.")
            return
        self.on_friend_request(to_user)

    def _selected_incoming_user(self) -> Optional[str]:
        if not self._incoming_tree:
            return None
        sel = self._incoming_tree.selection()
        if not sel:
            return None
        vals = self._incoming_tree.item(sel[0], "values")
        return str(vals[0]) if vals else None

    def _on_accept_selected(self) -> None:
        if not self.on_friend_accept:
            return
        u = self._selected_incoming_user()
        if not u:
            messagebox.showinfo("Friends", "Select an incoming request first.")
            return
        self.on_friend_accept(u)

    def _on_reject_selected(self) -> None:
        if not self.on_friend_reject:
            return
        u = self._selected_incoming_user()
        if not u:
            messagebox.showinfo("Friends", "Select an incoming request first.")
            return
        self.on_friend_reject(u)

    def _on_friend_double_click(self, event=None) -> None:
        if not self.on_open_private or not self._friends_list:
            return
        idx = self._friends_list.curselection()
        if not idx:
            return
        friend = self._friends_list.get(idx[0])
        if friend:
            self.on_open_private(str(friend))

    def destroy(self) -> None:
        if self.frame:
            self.frame.destroy()
            self.frame = None
