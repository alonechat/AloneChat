"""Friends view (WeChat-like) for AloneChat GUI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, List, Dict, Any
import time


class FriendsView:
    def __init__(
        self,
        parent,
        username: str,
        api_client,
        run_async: Callable,
        on_open_dm: Callable[[str], None],
    ):
        self.parent = parent
        self.username = username
        self.api = api_client
        self.run_async = run_async
        self.on_open_dm = on_open_dm

        self.root = ttk.Frame(parent)
        self.subtabs = ttk.Notebook(self.root)

        self.tab_friends = ttk.Frame(self.subtabs)
        self.tab_new = ttk.Frame(self.subtabs)
        self.tab_sent = ttk.Frame(self.subtabs)
        self.tab_search = ttk.Frame(self.subtabs)

        self.subtabs.add(self.tab_friends, text="Friends")
        self.subtabs.add(self.tab_new, text="New Friends")
        self.subtabs.add(self.tab_sent, text="Sent")
        self.subtabs.add(self.tab_search, text="Search")
        self.subtabs.pack(fill="both", expand=True, padx=10, pady=10)

        # Friends list
        self.friends_list = tk.Listbox(self.tab_friends, height=20)
        self.friends_list.pack(fill="both", expand=True, padx=6, pady=6)
        self.friends_list.bind("<Double-Button-1>", self._on_friend_double_click)

        btn_row = ttk.Frame(self.tab_friends)
        btn_row.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btn_row, text="Refresh", command=self.refresh_all).pack(side="right")

        # New requests
        self.in_list = tk.Listbox(self.tab_new, height=20)
        self.in_list.pack(fill="both", expand=True, padx=6, pady=6)
        self.in_list.bind("<Double-Button-1>", lambda e: self._accept_selected())
        self.in_list.bind("<Return>", lambda e: self._accept_selected())
        self.in_list.bind("<Delete>", lambda e: self._reject_selected())

        btn_row2 = ttk.Frame(self.tab_new)
        btn_row2.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btn_row2, text="Accept", command=self._accept_selected).pack(side="left")
        ttk.Button(btn_row2, text="Reject", command=self._reject_selected).pack(side="left", padx=(6,0))
        ttk.Button(btn_row2, text="Refresh", command=self.refresh_incoming).pack(side="right")
        ttk.Label(self.tab_new, text="Tips: Double-click or press Enter to accept; press Delete to reject.").pack(
            anchor="w", padx=8, pady=(0,8)
        )

        # Sent list
        self.sent_list = tk.Listbox(self.tab_sent, height=20)
        self.sent_list.pack(fill="both", expand=True, padx=6, pady=6)
        btn_row3 = ttk.Frame(self.tab_sent)
        btn_row3.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btn_row3, text="Refresh", command=self.refresh_sent).pack(side="right")

        # Search
        top = ttk.Frame(self.tab_search)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Keyword").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=40)
        self.search_entry.pack(side="left", padx=(8,8), fill="x", expand=True)
        ttk.Button(top, text="Search", command=self._do_search).pack(side="left")

        self.search_list = tk.Listbox(self.tab_search, height=18)
        self.search_list.pack(fill="both", expand=True, padx=6, pady=(0,6))
        self.search_list.bind("<Double-Button-1>", self._on_search_double_click)

        # footer for request
        footer = ttk.Frame(self.tab_search)
        footer.pack(fill="x", padx=6, pady=(0,6))
        self.req_to_var = tk.StringVar()
        self.req_msg_var = tk.StringVar()
        ttk.Label(footer, textvariable=self.req_to_var, width=16).pack(side="left")
        self.req_msg_entry = ttk.Entry(footer, textvariable=self.req_msg_var, width=50)
        self.req_msg_entry.pack(side="left", padx=(6,6), fill="x", expand=True)
        ttk.Button(footer, text="Send Request", command=self._send_request).pack(side="left")

        self._last_search_items: List[Dict[str, Any]] = []
        self._last_incoming_items: List[Dict[str, Any]] = []
        self._last_sent_items: List[Dict[str, Any]] = []

    def show(self):
        self.root.pack(fill="both", expand=True)

    def destroy(self):
        self.root.destroy()

    def _fmt_user(self, username: str, online: bool) -> str:
        dot = "•" if online else "·"
        status = "online" if online else "offline"
        return f"{username}  {dot}  {status}"

    def _ui(self, fn: Callable[[], None]) -> None:
        self.root.after(0, fn)

    def refresh_all(self):
        self.refresh_friends()
        self.refresh_incoming()
        self.refresh_sent()

    def refresh_friends(self):
        fut = self.run_async(self.api.friends_list())
        if not fut:
            return
        def done(_):
            try:
                res = fut.result()
            except Exception:
                res = {"success": False}
            def apply():
                self.friends_list.delete(0, tk.END)
                if isinstance(res, dict) and res.get("success"):
                    for it in res.get("items", []):
                        self.friends_list.insert(tk.END, self._fmt_user(it.get("username",""), bool(it.get("online"))))
                else:
                    self.friends_list.insert(tk.END, "(failed to load friends)")
            self._ui(apply)
        fut.add_done_callback(done)

    def refresh_incoming(self):
        fut = self.run_async(self.api.friend_requests_incoming())
        if not fut:
            return
        def done(_):
            try:
                res = fut.result()
            except Exception:
                res = {"success": False}
            def apply():
                self.in_list.delete(0, tk.END)
                self._last_incoming_items = []
                if isinstance(res, dict) and res.get("success"):
                    items = res.get("items", [])
                    self._last_incoming_items = items
                    for r in items:
                        ts = r.get("created_at", 0)
                        timestr = time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else ""
                        frm = r.get("from_user", "")
                        msg = r.get("message", "")
                        self.in_list.insert(tk.END, f"{frm}  ·  {msg}  ·  {timestr}")
                else:
                    self.in_list.insert(tk.END, "(failed to load requests)")
            self._ui(apply)
        fut.add_done_callback(done)

    def refresh_sent(self):
        fut = self.run_async(self.api.friend_requests_sent())
        if not fut:
            return
        def done(_):
            try:
                res = fut.result()
            except Exception:
                res = {"success": False}
            def apply():
                self.sent_list.delete(0, tk.END)
                self._last_sent_items = []
                if isinstance(res, dict) and res.get("success"):
                    items = res.get("items", [])
                    self._last_sent_items = items
                    for r in items:
                        ts = r.get("created_at", 0)
                        timestr = time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else ""
                        to = r.get("to_user", "")
                        st = r.get("status", "")
                        msg = r.get("message", "")
                        self.sent_list.insert(tk.END, f"to {to}  ·  {st}  ·  {msg}  ·  {timestr}")
                else:
                    self.sent_list.insert(tk.END, "(failed to load sent)")
            self._ui(apply)
        fut.add_done_callback(done)

    def _on_friend_double_click(self, _evt=None):
        sel = self.friends_list.curselection()
        if not sel:
            return
        text = self.friends_list.get(sel[0])
        user = text.split()[0]
        self.on_open_dm(user)

    def _do_search(self):
        keyword = (self.search_var.get() or "").strip()
        fut = self.run_async(self.api.users_search(keyword))
        if not fut:
            return
        def done(_):
            try:
                res = fut.result()
            except Exception:
                res = {"success": False}
            def apply():
                self.search_list.delete(0, tk.END)
                self._last_search_items = []
                if isinstance(res, dict) and res.get("success"):
                    items = res.get("items", [])
                    self._last_search_items = items
                    for it in items:
                        self.search_list.insert(tk.END, self._fmt_user(it.get("username",""), bool(it.get("online"))))
                else:
                    self.search_list.insert(tk.END, "(search failed)")
            self._ui(apply)
        fut.add_done_callback(done)

    def _on_search_double_click(self, _evt=None):
        sel = self.search_list.curselection()
        if not sel:
            return
        text = self.search_list.get(sel[0])
        user = text.split()[0]
        self.req_to_var.set(user)
        self.req_msg_var.set("")
        self.req_msg_entry.focus_set()

    def _send_request(self):
        user = (self.req_to_var.get() or "").strip()
        if not user:
            messagebox.showinfo("Friend Request", "Double-click a user first.")
            return
        msg = (self.req_msg_var.get() or "").strip()
        fut = self.run_async(self.api.send_friend_request(user, msg))
        if not fut:
            return
        def done(_):
            try:
                res = fut.result()
            except Exception:
                res = {"success": False, "message": "request failed"}
            def apply():
                messagebox.showinfo("Friend Request", res.get("message", "done"))
                self.refresh_incoming()
                self.refresh_sent()
                self.refresh_friends()
            self._ui(apply)
        fut.add_done_callback(done)

    def _selected_incoming_from(self) -> str | None:
        sel = self.in_list.curselection()
        if not sel:
            return None
        idx = sel[0]
        if idx < 0 or idx >= len(self._last_incoming_items):
            return None
        return self._last_incoming_items[idx].get("from_user")

    def _accept_selected(self):
        frm = self._selected_incoming_from()
        if not frm:
            return
        fut = self.run_async(self.api.respond_friend_request(frm, True))
        if not fut:
            return
        def done(_):
            try:
                res = fut.result()
            except Exception:
                res = {"success": False, "message": "failed"}
            def apply():
                messagebox.showinfo("Friend Request", res.get("message", "done"))
                self.refresh_all()
            self._ui(apply)
        fut.add_done_callback(done)

    def _reject_selected(self):
        frm = self._selected_incoming_from()
        if not frm:
            return
        fut = self.run_async(self.api.respond_friend_request(frm, False))
        if not fut:
            return
        def done(_):
            try:
                res = fut.result()
            except Exception:
                res = {"success": False, "message": "failed"}
            def apply():
                messagebox.showinfo("Friend Request", res.get("message", "done"))
                self.refresh_all()
            self._ui(apply)
        fut.add_done_callback(done)
