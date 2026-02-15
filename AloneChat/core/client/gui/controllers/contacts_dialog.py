"""Contacts / friend-audit dialog (WeChat-like).

This dialog is intentionally lightweight and uses only ttk widgets so it works
consistently with the existing sv_ttk theme.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, List, Dict, Any


class ContactsDialog:
    """A dialog that shows Friends and Incoming friend requests."""

    def __init__(
        self,
        root: tk.Tk,
        on_refresh: Callable[[], None],
        on_start_chat: Callable[[str], None],
        on_send_request: Callable[[str, str], None],
        on_search_users: Callable[[str], None],
        on_accept: Callable[[int], None],
        on_reject: Callable[[int], None],
    ):
        self.root = root
        self.on_refresh = on_refresh
        self.on_start_chat = on_start_chat
        self.on_send_request = on_send_request
        self.on_search_users = on_search_users
        self.on_accept = on_accept
        self.on_reject = on_reject

        self.window: Optional[tk.Toplevel] = None
        self._friends_tree: Optional[ttk.Treeview] = None
        self._requests_tree: Optional[ttk.Treeview] = None
        self._outgoing_tree: Optional[ttk.Treeview] = None
        self._search_tree: Optional[ttk.Treeview] = None
        self._search_var: Optional[tk.StringVar] = None
        self._status_var: Optional[tk.StringVar] = None

        # cached request rows: index -> request_id
        self._incoming_request_ids: List[int] = []
        self._outgoing_request_ids: List[int] = []

    def show(self):
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return

        self.window = tk.Toplevel(self.root)
        self.window.title("Contacts")
        self.window.geometry("720x460")
        self.window.minsize(640, 420)
        self.window.transient(self.root)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(outer)
        notebook.grid(row=0, column=0, sticky="nsew")

        friends_tab = ttk.Frame(notebook, padding=12)
        incoming_tab = ttk.Frame(notebook, padding=12)
        outgoing_tab = ttk.Frame(notebook, padding=12)
        search_tab = ttk.Frame(notebook, padding=12)
        notebook.add(friends_tab, text="Friends")
        notebook.add(incoming_tab, text="New Friends")
        notebook.add(outgoing_tab, text="Sent")
        notebook.add(search_tab, text="Search")

        self._build_friends_tab(friends_tab)
        self._build_incoming_tab(incoming_tab)
        self._build_outgoing_tab(outgoing_tab)
        self._build_search_tab(search_tab)

        # Footer
        footer = ttk.Frame(outer)
        footer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)

        self._status_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self._status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Refresh", command=self.on_refresh).grid(row=0, column=1, sticky="e")

        self.window.protocol("WM_DELETE_WINDOW", self.hide)

    def hide(self):
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
        self._friends_tree = None
        self._requests_tree = None
        self._outgoing_tree = None
        self._search_tree = None
        self._search_var = None
        self._status_var = None
        self._incoming_request_ids = []
        self._outgoing_request_ids = []

    def set_status(self, text: str):
        if self._status_var is not None:
            self._status_var.set(text)

    # ---------------- UI building ----------------

    def _build_friends_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Your friends").pack(side="left")

        ttk.Button(top, text="Start Chat", command=self._on_start_chat_clicked).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Add Friend", command=self._on_add_friend_clicked).pack(side="right")

        cols = ("username",)
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=12)
        tree.heading("username", text="Username")
        tree.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        tree.bind("<Double-1>", lambda e: self._on_start_chat_clicked())

        yscroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=1, column=1, sticky="ns", pady=(10, 0))

        self._friends_tree = tree

    def _build_incoming_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Incoming friend requests").pack(side="left")
        ttk.Button(top, text="Accept", command=self._on_accept_clicked).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Reject", command=self._on_reject_clicked).pack(side="right")

        cols = ("from", "message", "status")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=12)
        tree.heading("from", text="From")
        tree.heading("message", text="Message")
        tree.heading("status", text="Status")
        tree.column("from", width=140, anchor="w")
        tree.column("message", width=420, anchor="w")
        tree.column("status", width=100, anchor="w")
        tree.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        yscroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=1, column=1, sticky="ns", pady=(10, 0))

        self._requests_tree = tree

        # Quick actions: double-click accept; Enter accept; Delete reject
        tree.bind("<Double-1>", lambda e: self._on_accept_clicked())
        tree.bind("<Return>", lambda e: self._on_accept_clicked())
        tree.bind("<Delete>", lambda e: self._on_reject_clicked())

        # Highlight pending rows
        try:
            tree.tag_configure("pending", background="#fff7d6")
        except Exception:
            pass

    def _build_outgoing_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Sent friend requests").pack(side="left")
        ttk.Button(top, text="Refresh", command=self.on_refresh).pack(side="right")

        cols = ("to", "message", "status")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=12)
        tree.heading("to", text="To")
        tree.heading("message", text="Message")
        tree.heading("status", text="Status")
        tree.column("to", width=140, anchor="w")
        tree.column("message", width=420, anchor="w")
        tree.column("status", width=100, anchor="w")
        tree.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        yscroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=1, column=1, sticky="ns", pady=(10, 0))

        self._outgoing_tree = tree

    def _build_search_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Search users:").pack(side="left")
        self._search_var = tk.StringVar(value="")
        entry = ttk.Entry(top, textvariable=self._search_var, width=26)
        entry.pack(side="left", padx=(8, 8))

        def do_search():
            q = (self._search_var.get() if self._search_var else "").strip()
            self.on_search_users(q)

        ttk.Button(top, text="Search", command=do_search).pack(side="left")
        ttk.Button(top, text="Add Selected", command=self._on_add_from_search).pack(side="right")

        cols = ("username", "online")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=12)
        tree.heading("username", text="Username")
        tree.heading("online", text="Online")
        tree.column("username", width=260, anchor="w")
        tree.column("online", width=80, anchor="w")
        tree.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        yscroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=1, column=1, sticky="ns", pady=(10, 0))

        self._search_tree = tree
        entry.bind("<Return>", lambda e: do_search())

    # ---------------- Data population ----------------

    def set_friends(self, friends: List[str]):
        if not self._friends_tree:
            return
        self._friends_tree.delete(*self._friends_tree.get_children())
        for u in sorted(set([x for x in friends if x])):
            self._friends_tree.insert("", "end", values=(u,))

    def set_incoming_requests(self, requests: List[Dict[str, Any]]):
        if not self._requests_tree:
            return

        self._requests_tree.delete(*self._requests_tree.get_children())
        self._incoming_request_ids = []

        for r in requests or []:
            try:
                rid = int(r.get("id"))
            except Exception:
                continue
            self._incoming_request_ids.append(rid)
            status = str(r.get("status", "pending"))
            tags = ("pending",) if status.lower() == "pending" else ()
            self._requests_tree.insert(
                "",
                "end",
                values=(
                    str(r.get("from_user", "")),
                    str(r.get("message", "")),
                    status,
                ),
                tags=tags,
            )

    def set_outgoing_requests(self, requests: List[Dict[str, Any]]):
        if not self._outgoing_tree:
            return
        self._outgoing_tree.delete(*self._outgoing_tree.get_children())
        self._outgoing_request_ids = []

        for r in requests or []:
            try:
                rid = int(r.get("id"))
            except Exception:
                continue
            self._outgoing_request_ids.append(rid)
            self._outgoing_tree.insert(
                "",
                "end",
                values=(
                    str(r.get("to_user", "")),
                    str(r.get("message", "")),
                    str(r.get("status", "pending")),
                ),
            )

    def set_search_results(self, users: List[Dict[str, Any]]):
        if not self._search_tree:
            return
        self._search_tree.delete(*self._search_tree.get_children())
        for u in users or []:
            if not isinstance(u, dict):
                continue
            name = str(u.get("username", "")).strip()
            if not name:
                continue
            online = "yes" if bool(u.get("is_online")) else "no"
            self._search_tree.insert("", "end", values=(name, online))

    # ---------------- Event handlers ----------------

    def _selected_friend(self) -> Optional[str]:
        if not self._friends_tree:
            return None
        sel = self._friends_tree.selection()
        if not sel:
            return None
        values = self._friends_tree.item(sel[0], "values")
        return str(values[0]) if values else None

    def _selected_request_id(self) -> Optional[int]:
        if not self._requests_tree:
            return None
        sel = self._requests_tree.selection()
        if not sel:
            return None
        idx = self._requests_tree.index(sel[0])
        if 0 <= idx < len(self._incoming_request_ids):
            return int(self._incoming_request_ids[idx])
        return None

    def _on_start_chat_clicked(self):
        u = self._selected_friend()
        if u:
            self.on_start_chat(u)

    def _on_add_friend_clicked(self):
        self._open_send_request_dialog("")

    def _selected_search_user(self) -> Optional[str]:
        if not self._search_tree:
            return None
        sel = self._search_tree.selection()
        if not sel:
            return None
        values = self._search_tree.item(sel[0], "values")
        return str(values[0]) if values else None

    def _on_add_from_search(self):
        u = self._selected_search_user()
        if u:
            self._open_send_request_dialog(u)

    def _open_send_request_dialog(self, preset_username: str = ""):
        dialog = tk.Toplevel(self.window or self.root)
        dialog.title("Send Friend Request")
        dialog.transient(self.window or self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Username:").grid(row=0, column=0, sticky="w")
        username_var = tk.StringVar(value=(preset_username or ""))
        entry_u = ttk.Entry(frame, textvariable=username_var, width=30)
        entry_u.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(frame, text="Message (optional):").grid(row=1, column=0, sticky="w", pady=(10, 0))
        msg_var = tk.StringVar(value="")
        entry_m = ttk.Entry(frame, textvariable=msg_var, width=40)
        entry_m.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(10, 0))

        frame.columnconfigure(1, weight=1)

        btns = ttk.Frame(frame)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def submit():
            u2 = (username_var.get() or "").strip()
            m2 = (msg_var.get() or "").strip()
            if u2:
                self.on_send_request(u2, m2)
            dialog.destroy()

        ttk.Button(btns, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(btns, text="Send", command=submit).pack(side="right", padx=(0, 8))

        entry_u.focus_set()

    def _on_accept_clicked(self):
        rid = self._selected_request_id()
        if rid is not None:
            self.on_accept(rid)

    def _on_reject_clicked(self):
        rid = self._selected_request_id()
        if rid is not None:
            self.on_reject(rid)
