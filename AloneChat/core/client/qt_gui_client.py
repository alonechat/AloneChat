"""
Qt (PyQt6) GUI client for AloneChat.

Goal:
- Provide a cross-platform GUI replacement for the legacy tkinter "gui" client.
- Keep all networking/protocol behavior identical by reusing AloneChatAPIClient and
  the existing GUI services/models (ConversationManager, MessageItem, etc.).
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from AloneChat.api.client import AloneChatAPIClient
from AloneChat.core.client.client_base import Client
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT

from AloneChat.core.client.gui.models.data import MessageItem
# ReplyContext lives in gui.models.data in the upstream project.
from AloneChat.core.client.gui.models.data import ReplyContext
from AloneChat.core.client.gui.services.async_service import AsyncService
from AloneChat.core.client.gui.services.conversation_manager import ConversationManager
from AloneChat.core.client.gui.services.persistence_service import PersistenceService
from AloneChat.core.client.gui.services.search_service import SearchService


class _UiBridge(QtCore.QObject):
    """Thread-safe bridge for updating Qt UI from async thread."""
    message_added = QtCore.pyqtSignal(object, bool)  # (MessageItem, is_active)
    convo_list_changed = QtCore.pyqtSignal()
    system_message = QtCore.pyqtSignal(str)
    login_ok = QtCore.pyqtSignal(str)  # username
    login_failed = QtCore.pyqtSignal(str)
    register_ok = QtCore.pyqtSignal(str)
    register_failed = QtCore.pyqtSignal(str)


class _AuthDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("AloneChat - Login")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel("AloneChat")
        f = title.font()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)

        form = QtWidgets.QFormLayout()
        self.username = QtWidgets.QLineEdit()
        self.username.setPlaceholderText("Username")
        self.password = QtWidgets.QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        layout.addLayout(form)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #b00020;")
        layout.addWidget(self.status)

        btns = QtWidgets.QHBoxLayout()
        self.login_btn = QtWidgets.QPushButton("Login")
        self.register_btn = QtWidgets.QPushButton("Register")
        btns.addWidget(self.login_btn)
        btns.addWidget(self.register_btn)
        layout.addLayout(btns)

        self.login_btn.setDefault(True)



class _IncomingRequestsList(QtWidgets.QListWidget):
    """Incoming friend requests list with WeChat-like shortcuts."""

    def __init__(self, owner: "QtGUIClient"):
        super().__init__()
        self._owner = owner

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        key = event.key()
        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            self._owner._accept_or_reject_selected(True)
            return
        if key == QtCore.Qt.Key.Key_Delete:
            self._owner._accept_or_reject_selected(False)
            return
        super().keyPressEvent(event)

class QtGUIClient(Client):
    """
    Cross-platform GUI client (Qt).
    Keeps protocol/network behavior identical by using AloneChatAPIClient and
    the GUI services from the legacy GUI client.
    """

    def __init__(self, api_host: str = DEFAULT_HOST, api_port: int = DEFAULT_API_PORT):
        super().__init__(api_host, api_port)

        self._api_host = api_host
        self._api_port = api_port
        self._api_client = AloneChatAPIClient(api_host, api_port)

        self._username = ""
        self._token: Optional[str] = None
        self._running = False
        self._closing = False

        # Services (same as legacy GUI)
        self._async_service = AsyncService()
        self._conv_manager = ConversationManager()
        self._search_service = SearchService()
        self._persistence = PersistenceService()

        self._reply_ctx: Optional[ReplyContext] = None
        self._poll_future = None

        self._bridge = _UiBridge()

        # Qt widgets (created in run)
        self._app: Optional[QtWidgets.QApplication] = None
        self._win: Optional[QtWidgets.QMainWindow] = None
        self._convos: Optional[QtWidgets.QListWidget] = None
        self._messages: Optional[QtWidgets.QTextBrowser] = None
        self._input: Optional[QtWidgets.QPlainTextEdit] = None
        self._send_btn: Optional[QtWidgets.QPushButton] = None
        # Friends & Moments (WeChat-like features backed by API)
        self._tabs: Optional[QtWidgets.QTabWidget] = None

        # Chats tab extras
        self._contacts_btn: Optional[QtWidgets.QPushButton] = None
        self._pin_btn: Optional[QtWidgets.QPushButton] = None
        self._mute_btn: Optional[QtWidgets.QPushButton] = None

        # Friends tab
        self._friends_tabs: Optional[QtWidgets.QTabWidget] = None
        self._friends_list: Optional[QtWidgets.QListWidget] = None
        self._incoming_requests: Optional[QtWidgets.QListWidget] = None
        self._outgoing_requests: Optional[QtWidgets.QListWidget] = None
        self._user_search_input: Optional[QtWidgets.QLineEdit] = None
        self._user_search_btn: Optional[QtWidgets.QPushButton] = None
        self._user_search_results: Optional[QtWidgets.QListWidget] = None
        self._add_friend_to: Optional[QtWidgets.QLineEdit] = None
        self._add_friend_msg: Optional[QtWidgets.QLineEdit] = None
        self._add_friend_btn: Optional[QtWidgets.QPushButton] = None
        self._remove_friend_btn: Optional[QtWidgets.QPushButton] = None
        self._chat_friend_btn: Optional[QtWidgets.QPushButton] = None
        self._accept_req_btn: Optional[QtWidgets.QPushButton] = None
        self._reject_req_btn: Optional[QtWidgets.QPushButton] = None
        self._refresh_friends_btn: Optional[QtWidgets.QPushButton] = None
        self._refresh_incoming_btn: Optional[QtWidgets.QPushButton] = None
        self._refresh_outgoing_btn: Optional[QtWidgets.QPushButton] = None

        # Poll timer for friend-request badge
        self._badge_timer: Optional[QtCore.QTimer] = None

        # Moments (local feed)
        self._moments_feed: Optional[QtWidgets.QListWidget] = None
        self._moment_input: Optional[QtWidgets.QPlainTextEdit] = None
        self._post_moment_btn: Optional[QtWidgets.QPushButton] = None

        # Emoji

        self._emoji_btn: Optional[QtWidgets.QToolButton] = None
        self._emoji_menu: Optional[QtWidgets.QMenu] = None
        self._reply_label: Optional[QtWidgets.QLabel] = None

        # Prevent stale history loads from clearing UI when switching conversations quickly.
        self._history_req_seq: int = 0

    # -------------------- Lifecycle --------------------

    def run(self):
        # Qt app
        self._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self._app.aboutToQuit.connect(self._save_local_state)
        self._setup_main_window()
        self._wire_bridge()

        # Start async thread loop (same as legacy GUI)
        self._async_service.start()

        # Login dialog
        auth = _AuthDialog(self._win)
        auth.login_btn.clicked.connect(lambda: self._start_login(auth))
        auth.register_btn.clicked.connect(lambda: self._start_register(auth))

        # Enter triggers login
        auth.password.returnPressed.connect(auth.login_btn.click)

        # show
        auth.show()
        auth.raise_()

        # On login success, close dialog handled by signal
        self._bridge.login_ok.connect(lambda u: auth.accept())
        self._bridge.login_failed.connect(lambda m: auth.status.setText(m))
        self._bridge.register_ok.connect(lambda u: auth.status.setText(f"Registered as {u}. You can login now."))
        self._bridge.register_failed.connect(lambda m: auth.status.setText(m))

        if auth.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            self._shutdown()
            return

        # Load client-side features (friends / moments) after successful login
        self._load_local_state()
        # Sync WeChat-like state from server (friends / requests / conversations)
        self._async_service.run_async(self._initial_sync())
        self._start_badge_timer()


        self._win.show()
        self._win.raise_()

        # Initial render (global conversation exists by default)
        self._refresh_convo_list()
        self._render_active_conversation()

        # start polling
        self._running = True
        self._poll_future = self._async_service.run_async(self._poll_messages())

        # initial convo list
        self._refresh_convo_list()

        # Run Qt loop
        self._app.exec()
        self._shutdown()

    def _shutdown(self):
        self._closing = True
        self._running = False
        try:
            if self._poll_future:
                self._poll_future.cancel()
        except Exception:
            pass
        try:
            self._async_service.stop()
        except Exception:
            pass

    # -------------------- UI setup --------------------

    def _setup_main_window(self):
        self._win = QtWidgets.QMainWindow()
        self._win.setWindowTitle("AloneChat")
        self._win.resize(1200, 640)

        central = QtWidgets.QWidget()
        self._win.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        # Top-level tabs (Chats / Friends / Moments)
        self._tabs = QtWidgets.QTabWidget()
        root.addWidget(self._tabs, 1)

        # ---------------- Chats tab ----------------
        chats = QtWidgets.QWidget()
        self._tabs.addTab(chats, "Chats")
        main = QtWidgets.QHBoxLayout(chats)

        # Left: conversations
        left = QtWidgets.QVBoxLayout()
        self._convos = QtWidgets.QListWidget()
        self._convos.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

        left.addWidget(QtWidgets.QLabel("Conversations"))
        left.addWidget(self._convos, 1)
        btn_row = QtWidgets.QHBoxLayout()
        search_btn = QtWidgets.QPushButton("Search")
        logout_btn = QtWidgets.QPushButton("Logout")
        btn_row.addWidget(search_btn)
        btn_row.addWidget(logout_btn)
        left.addLayout(btn_row)

        # Pin / Mute (per-conversation settings; persisted on server)
        pm_row = QtWidgets.QHBoxLayout()
        self._pin_btn = QtWidgets.QPushButton("Pin")
        self._mute_btn = QtWidgets.QPushButton("Mute")
        pm_row.addWidget(self._pin_btn)
        pm_row.addWidget(self._mute_btn)
        left.addLayout(pm_row)

        # Right: messages + input
        right = QtWidgets.QVBoxLayout()

        self._messages = QtWidgets.QTextBrowser()
        self._messages.setOpenExternalLinks(True)
        self._messages.setReadOnly(True)

        self._reply_label = QtWidgets.QLabel("")
        self._reply_label.setStyleSheet("color: #666;")
        self._reply_label.setWordWrap(True)
        self._reply_label.hide()

        # Search bar (Ctrl+F)
        self._search_bar = QtWidgets.QWidget()
        sb = QtWidgets.QHBoxLayout(self._search_bar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.addWidget(QtWidgets.QLabel("Find:"))
        self._search_input = QtWidgets.QLineEdit()
        self._search_input.setPlaceholderText("Type to search in current conversation…")
        sb.addWidget(self._search_input, 1)
        self._search_prev_btn = QtWidgets.QToolButton(); self._search_prev_btn.setText("◀")
        self._search_next_btn = QtWidgets.QToolButton(); self._search_next_btn.setText("▶")
        self._search_close_btn = QtWidgets.QToolButton(); self._search_close_btn.setText("✕")
        sb.addWidget(self._search_prev_btn)
        sb.addWidget(self._search_next_btn)
        sb.addWidget(self._search_close_btn)
        self._search_bar.hide()

        # Input row: emoji + editor + send
        input_row = QtWidgets.QHBoxLayout()
        self._emoji_btn = QtWidgets.QToolButton()
        self._emoji_btn.setText("😊")
        self._emoji_btn.setToolTip("Insert emoji")
        self._emoji_btn.setAutoRaise(True)
        input_row.addWidget(self._emoji_btn)

        self._input = QtWidgets.QPlainTextEdit()
        self._input.setPlaceholderText("Type a message… (Ctrl+Enter to send)")
        self._input.setFixedHeight(110)
        input_row.addWidget(self._input, 1)

        self._send_btn = QtWidgets.QPushButton("Send")
        input_row.addWidget(self._send_btn)

        right.addWidget(self._messages, 1)
        right.addWidget(self._reply_label)
        right.addWidget(self._search_bar)
        right.addLayout(input_row)

        splitter = QtWidgets.QSplitter()
        left_w = QtWidgets.QWidget(); left_w.setLayout(left)
        left_w.setMinimumWidth(220)
        right_w = QtWidgets.QWidget(); right_w.setLayout(right)
        splitter.addWidget(left_w)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 900])
        main.addWidget(splitter, 1)

        # ---------------- Friends tab ----------------
        friends = QtWidgets.QWidget()
        self._tabs.addTab(friends, "Friends")
        f_layout = QtWidgets.QVBoxLayout(friends)

        # Tabs: Friends / New Friends / Sent / Search
        self._friends_tabs = QtWidgets.QTabWidget()
        f_layout.addWidget(self._friends_tabs, 1)

        # --- Friends list ---
        friends_page = QtWidgets.QWidget()
        self._friends_tabs.addTab(friends_page, "Friends")
        fp = QtWidgets.QVBoxLayout(friends_page)
        self._friends_list = QtWidgets.QListWidget()
        fp.addWidget(self._friends_list, 1)
        f_btns = QtWidgets.QHBoxLayout()
        self._chat_friend_btn = QtWidgets.QPushButton("Chat")
        self._remove_friend_btn = QtWidgets.QPushButton("Remove")
        self._refresh_friends_btn = QtWidgets.QPushButton("Refresh")
        f_btns.addWidget(self._chat_friend_btn)
        f_btns.addWidget(self._remove_friend_btn)
        f_btns.addStretch(1)
        f_btns.addWidget(self._refresh_friends_btn)
        fp.addLayout(f_btns)

        # --- Incoming requests (New Friends) ---
        incoming_page = QtWidgets.QWidget()
        self._friends_tabs.addTab(incoming_page, "New Friends")
        ip = QtWidgets.QVBoxLayout(incoming_page)
        self._incoming_requests = _IncomingRequestsList(self)
        ip.addWidget(self._incoming_requests, 1)
        req_btns = QtWidgets.QHBoxLayout()
        self._accept_req_btn = QtWidgets.QPushButton("Accept")
        self._reject_req_btn = QtWidgets.QPushButton("Reject")
        self._refresh_incoming_btn = QtWidgets.QPushButton("Refresh")
        req_btns.addWidget(self._accept_req_btn)
        req_btns.addWidget(self._reject_req_btn)
        req_btns.addStretch(1)
        req_btns.addWidget(self._refresh_incoming_btn)
        ip.addLayout(req_btns)
        ip_hint = QtWidgets.QLabel("Tips: Double-click or press Enter to accept; press Delete to reject. Pending items are highlighted.")
        ip_hint.setStyleSheet("color:#666;")
        ip_hint.setWordWrap(True)
        ip.addWidget(ip_hint)

        # --- Outgoing requests (Sent) ---
        outgoing_page = QtWidgets.QWidget()
        self._friends_tabs.addTab(outgoing_page, "Sent")
        op = QtWidgets.QVBoxLayout(outgoing_page)
        self._outgoing_requests = QtWidgets.QListWidget()
        op.addWidget(self._outgoing_requests, 1)
        out_btns = QtWidgets.QHBoxLayout()
        self._refresh_outgoing_btn = QtWidgets.QPushButton("Refresh")
        out_btns.addStretch(1)
        out_btns.addWidget(self._refresh_outgoing_btn)
        op.addLayout(out_btns)

        # --- Search users + send request ---
        search_page = QtWidgets.QWidget()
        self._friends_tabs.addTab(search_page, "Search")
        sp = QtWidgets.QVBoxLayout(search_page)

        search_row = QtWidgets.QHBoxLayout()
        self._user_search_input = QtWidgets.QLineEdit()
        self._user_search_input.setPlaceholderText("Search users…")
        self._user_search_btn = QtWidgets.QPushButton("Search")
        search_row.addWidget(self._user_search_input, 1)
        search_row.addWidget(self._user_search_btn)
        sp.addLayout(search_row)

        self._user_search_results = QtWidgets.QListWidget()
        sp.addWidget(self._user_search_results, 1)

        add_row = QtWidgets.QHBoxLayout()
        self._add_friend_to = QtWidgets.QLineEdit()
        self._add_friend_to.setPlaceholderText("Username to add (or select above)")
        self._add_friend_msg = QtWidgets.QLineEdit()
        self._add_friend_msg.setPlaceholderText("Verification message (optional)")
        self._add_friend_btn = QtWidgets.QPushButton("Send Request")
        add_row.addWidget(self._add_friend_to, 2)
        add_row.addWidget(self._add_friend_msg, 3)
        add_row.addWidget(self._add_friend_btn, 1)
        sp.addLayout(add_row)

        # ---------------- Moments tab ----------------
        moments = QtWidgets.QWidget()
        self._tabs.addTab(moments, "Moments")
        m_layout = QtWidgets.QVBoxLayout(moments)
        m_layout.addWidget(QtWidgets.QLabel("Moments (local feed)"))
        self._moments_feed = QtWidgets.QListWidget()
        m_layout.addWidget(self._moments_feed, 1)
        self._moment_input = QtWidgets.QPlainTextEdit()
        self._moment_input.setPlaceholderText("Write a moment… (stored locally)")
        self._moment_input.setFixedHeight(90)
        m_layout.addWidget(self._moment_input)
        self._post_moment_btn = QtWidgets.QPushButton("Post")
        m_layout.addWidget(self._post_moment_btn)

        # Events
        self._send_btn.clicked.connect(self._handle_send_clicked)
        self._convos.currentItemChanged.connect(self._handle_convo_selected)
        search_btn.clicked.connect(self._handle_search)
        logout_btn.clicked.connect(self._handle_logout)
        if self._pin_btn:
            self._pin_btn.clicked.connect(self._toggle_pin)
        if self._mute_btn:
            self._mute_btn.clicked.connect(self._toggle_mute)

        # Friends tab signals
        if self._add_friend_btn:
            self._add_friend_btn.clicked.connect(self._send_friend_request_from_ui)
        if self._user_search_btn:
            self._user_search_btn.clicked.connect(self._search_users_from_ui)
        if self._user_search_results:
            self._user_search_results.itemSelectionChanged.connect(self._sync_selected_user_to_add_box)

        if self._refresh_friends_btn:
            self._refresh_friends_btn.clicked.connect(lambda: self._async_service.run_async(self._refresh_friends()))
        if self._refresh_incoming_btn:
            self._refresh_incoming_btn.clicked.connect(lambda: self._async_service.run_async(self._refresh_incoming()))
        if self._refresh_outgoing_btn:
            self._refresh_outgoing_btn.clicked.connect(lambda: self._async_service.run_async(self._refresh_outgoing()))

        if self._chat_friend_btn:
            self._chat_friend_btn.clicked.connect(self._chat_selected_friend)
        if self._remove_friend_btn:
            self._remove_friend_btn.clicked.connect(self._remove_selected_friend)

        if self._friends_list:
            self._friends_list.itemDoubleClicked.connect(lambda _=None: self._chat_selected_friend())

        if self._accept_req_btn:
            self._accept_req_btn.clicked.connect(lambda: self._accept_or_reject_selected(True))
        if self._reject_req_btn:
            self._reject_req_btn.clicked.connect(lambda: self._accept_or_reject_selected(False))

        if self._incoming_requests:
            self._incoming_requests.itemDoubleClicked.connect(lambda _=None: self._accept_or_reject_selected(True))

        self._post_moment_btn.clicked.connect(self._handle_post_moment)
        self._emoji_btn.clicked.connect(self._show_emoji_menu)

        # Search bar events / shortcuts
        self._search_input.textChanged.connect(lambda _=None: self._refresh_search_highlight())
        self._search_input.returnPressed.connect(lambda: self._find_next(wrap=True))
        self._search_next_btn.clicked.connect(lambda: self._find_next(wrap=True))
        self._search_prev_btn.clicked.connect(lambda: self._find_prev(wrap=True))
        self._search_close_btn.clicked.connect(self._hide_search_bar)

        find_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), self._win)
        find_shortcut.activated.connect(self._handle_search)
        next_shortcut = QtGui.QShortcut(QtGui.QKeySequence("F3"), self._win)
        next_shortcut.activated.connect(lambda: self._find_next(wrap=True))
        prev_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Shift+F3"), self._win)
        prev_shortcut.activated.connect(lambda: self._find_prev(wrap=True))
        esc_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Esc"), self._win)
        esc_shortcut.activated.connect(self._hide_search_bar)

        # Ctrl+Enter to send
        send_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self._win)
        send_shortcut.activated.connect(self._handle_send_clicked)

    def _wire_bridge(self):
        self._bridge.message_added.connect(self._on_message_added)
        self._bridge.convo_list_changed.connect(self._refresh_convo_list)
        self._bridge.system_message.connect(self._add_system_message_ui)

    # -------------------- Auth --------------------

    def _start_login(self, dlg: _AuthDialog):
        u = dlg.username.text().strip()
        p = dlg.password.text()
        if not u or not p:
            dlg.status.setText("Please enter username and password.")
            return
        dlg.status.setText("Logging in…")
        self._async_service.run_async(self._do_login(u, p))

    async def _do_login(self, username: str, password: str):
        try:
            res = await self._api_client.login(username, password)
            if isinstance(res, dict) and res.get("success"):
                self._username = username
                self._token = res.get("token")
                self._bridge.login_ok.emit(username)
                # greet
                self._bridge.system_message.emit(f"Logged in as {username}.")
            else:
                msg = (res or {}).get("message", "Login failed.")
                self._bridge.login_failed.emit(str(msg))
        except Exception as e:
            self._bridge.login_failed.emit(str(e))

    def _start_register(self, dlg: _AuthDialog):
        u = dlg.username.text().strip()
        p = dlg.password.text()
        if not u or not p:
            dlg.status.setText("Please enter username and password.")
            return
        dlg.status.setText("Registering…")
        self._async_service.run_async(self._do_register(u, p))

    async def _do_register(self, username: str, password: str):
        try:
            res = await self._api_client.register(username, password)
            if isinstance(res, dict) and res.get("success"):
                self._bridge.register_ok.emit(username)
            else:
                msg = (res or {}).get("message", "Register failed.")
                self._bridge.register_failed.emit(str(msg))
        except Exception as e:
            self._bridge.register_failed.emit(str(e))

    # -------------------- Messaging --------------------

    async def _poll_messages(self):
        while self._running and not self._closing:
            try:
                msg = await self._api_client.receive_message()
                if isinstance(msg, dict) and msg.get("success"):
                    sender = msg.get("sender")
                    content = msg.get("content")
                    if sender and content and sender != self._username:
                        # Handle server-side events (do not render as chat messages).
                        if str(sender).upper() == "SERVER":
                            m = re.match(r"^\[\[EVENT\s+([a-zA-Z0-9_]+)\s*(.*?)\]\]$", str(content).strip())
                            if m:
                                evt = m.group(1)
                                # Refresh server-backed state.
                                if evt in ("friend_accepted", "conversation_created", "refresh"):
                                    self._async_service.run_async(self._refresh_conversations())
                                    self._async_service.run_async(self._refresh_friends())
                                    self._async_service.run_async(self._refresh_incoming(light=True))
                                    self._async_service.run_async(self._refresh_outgoing())
                                await asyncio.sleep(0.05)
                                continue
                        cid, actual_sender, body = self._conv_manager.process_received_message(
                            sender, content, self._username
                        )
                        if cid:
                            item = MessageItem.create(actual_sender, body, is_self=False)
                            is_active = (cid == self._conv_manager.active_cid)
                            self._conv_manager.add_message(cid, item, is_active=is_active)
                            self._bridge.message_added.emit(item, is_active)
                            if not is_active:
                                self._bridge.convo_list_changed.emit()
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.5)

    def _handle_send_clicked(self):
        if self._input is None:
            return
        content = self._input.toPlainText()
        if not content.strip():
            return
        self._input.clear()
        self._handle_send(content)

    def _handle_send(self, content: str):
        # Attach quote if replying
        if self._reply_ctx:
            quote = self._reply_ctx.get_snippet(120)
            content = f"> Reply to {self._reply_ctx.sender} ({self._reply_ctx.timestamp}): {quote}\n{content}"
            self._reply_ctx = None
            if self._reply_label:
                self._reply_label.hide()
                self._reply_label.setText("")


        target_cid = self._conv_manager.active_cid
        payload, cid = self._conv_manager.prepare_send_payload(content, target_cid)

        item = MessageItem.create(self._username, content, is_self=True, status="Sending…")
        self._conv_manager.add_message(cid, item, is_active=True)
        self._append_message(item)

        # async send
        self._async_service.run_async(self._send_message(payload, item, cid))

    async def _send_message(self, payload: str, item: MessageItem, cid: str):
        try:
            res = await self._api_client.send_message(payload)
            ok = isinstance(res, dict) and res.get("success")
            # Update status locally (UI only)
            item.status = None if ok else (res or {}).get("message", "Failed")
        except Exception as e:
            item.status = str(e)
        finally:
            # refresh active messages if needed
            self._bridge.message_added.emit(item, True)

    # -------------------- Conversation UI --------------------

    def _refresh_convo_list(self):
        """Rebuild the conversation list with WeChat-like preview + timestamp + badges."""
        if self._convos is None:
            return

        # Remember selection
        current_cid = None
        cur = self._convos.currentItem()
        if cur is not None:
            current_cid = cur.data(QtCore.Qt.ItemDataRole.UserRole)

        # Sort conversations: global first, then pinned, then recent
        try:
            ids = list(self._conv_manager.conversation_ids)
        except Exception:
            ids = ["global"]

        if "global" not in ids:
            ids = ["global"] + ids
        else:
            ids = ["global"] + [c for c in ids if c != "global"]

        def score(cid: str):
            conv = self._conv_manager.get_conversation(cid)
            pinned = bool(getattr(conv, "pinned", False)) if conv else False
            ts = float(getattr(conv, "last_created_at", 0.0) or 0.0) if conv else 0.0
            if not ts and conv:
                ts = float(getattr(conv, "updated_at", 0.0) or 0.0)
            return (1 if pinned else 0, ts)

        rest = ids[1:]
        rest.sort(key=score, reverse=True)
        ids = ["global"] + rest

        # Update internal order so ConversationManager labels follow this order
        try:
            self._conv_manager._conv_ids = ids  # type: ignore[attr-defined]
        except Exception:
            pass

        try:
            labels = self._conv_manager.get_conversation_labels()
        except Exception:
            labels = ids

        self._convos.blockSignals(True)
        self._convos.clear()

        for cid, label in zip(ids, labels):
            it = QtWidgets.QListWidgetItem(str(label))
            it.setData(QtCore.Qt.ItemDataRole.UserRole, cid)
            self._convos.addItem(it)

            if (current_cid and cid == current_cid) or (
                not current_cid and cid == getattr(self._conv_manager, "active_cid", "global")
            ):
                self._convos.setCurrentItem(it)

        self._convos.blockSignals(False)
        self._update_pin_mute_buttons()

    def _handle_convo_selected(self, current, _prev):
        if not current:
            return
        cid = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if cid:
            if hasattr(self._conv_manager, "switch_conversation"):
                self._conv_manager.switch_conversation(cid)
            else:
                self._conv_manager.active_cid = cid
            self._update_pin_mute_buttons()
            self._render_active_conversation()
            # Pull DM history from server (global is real-time only)
            self._history_req_seq += 1
            req_id = self._history_req_seq
            self._async_service.run_async(self._load_history_for_active(req_id=req_id, expected_cid=str(cid)))

    def _render_active_conversation(self):
        if self._messages is None:
            return
        self._messages.clear()
        conv = self._conv_manager.get_conversation(self._conv_manager.active_cid)
        items = conv.items if conv else []
        for item in items:
            self._append_message(item)
        self._refresh_search_highlight()

    def _append_message(self, item: MessageItem):
        if self._messages is None:
            return
        sender = QtCore.QCoreApplication.translate("QtGUIClient", item.sender)
        content = QtCore.QCoreApplication.translate("QtGUIClient", item.content)
        ts = item.timestamp
        status = f" <span style='color:#888'>[{item.status}]</span>" if item.status else ""
        bubble_style = "background:#f2f2f2;border-radius:8px;padding:8px;" if not item.is_self else "background:#e8f0ff;border-radius:8px;padding:8px;"
        html = f"""
        <div style="margin:8px 0;">
          <div style="font-size:12px;color:#666;">{sender} · {ts}{status}</div>
          <div style="{bubble_style}; white-space: pre-wrap;">{self._escape_html(content)}</div>
        </div>
        """
        self._messages.append(html)
        self._messages.verticalScrollBar().setValue(self._messages.verticalScrollBar().maximum())
        self._search_service.set_message_cards([])  # placeholder: legacy used cards; we keep service for logs
        self._persistence.log_chat(self._username, item.sender, item.content)

    def _on_message_added(self, item: MessageItem, is_active: bool):
        # Re-render only if message belongs to active convo or it's a local status update
        if self._messages is None:
            return
        if is_active:
            # If active convo contains this item, just append if it's new; for status updates,
            # re-render active convo to reflect status change.
            self._render_active_conversation()

    def _add_system_message_ui(self, content: str):
        item = MessageItem.create("System", content, is_system=True)
        self._conv_manager.add_message(self._conv_manager.active_cid, item, is_active=True)
        self._append_message(item)

    # -------------------- Tools --------------------

    def _open_dm(self, username: str):
        """Open/switch to a DM conversation keyed by username."""
        cid = (username or "").strip()
        if not cid:
            return
        if cid.lower() == (self._username or "").lower():
            return

        if self._conv_manager.get_conversation(cid) is None:
            self._conv_manager.create_conversation(cid, name=cid)

        if hasattr(self._conv_manager, "switch_conversation"):
            self._conv_manager.switch_conversation(cid)
        else:
            self._conv_manager.active_cid = cid

        self._refresh_convo_list()
        self._update_pin_mute_buttons()
        self._render_active_conversation()
        self._history_req_seq += 1
        req_id = self._history_req_seq
        self._async_service.run_async(self._load_history_for_active(req_id=req_id, expected_cid=str(cid)))

    def _handle_search(self):
        # Toggle search bar
        if self._win is None or self._messages is None:
            return
        if getattr(self, "_search_bar", None) is None:
            return
        if self._search_bar.isVisible():
            self._hide_search_bar()
        else:
            self._show_search_bar()

    def _show_search_bar(self):
        if self._search_bar is None:
            return
        self._search_bar.show()
        self._search_input.setFocus()
        self._search_input.selectAll()
        self._refresh_search_highlight()

    def _hide_search_bar(self):
        if self._search_bar is None:
            return
        self._search_bar.hide()
        self._messages.setTextCursor(self._messages.textCursor())  # no-op, keeps cursor valid
        # Clear current selection
        c = self._messages.textCursor()
        c.clearSelection()
        self._messages.setTextCursor(c)

    def _refresh_search_highlight(self):
        # Reset cursor and find first match (if any)
        if self._messages is None or self._search_bar is None or not self._search_bar.isVisible():
            return
        query = (self._search_input.text() or "").strip()
        if not query:
            return
        # Move to start and search forward
        cursor = self._messages.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.Start)
        self._messages.setTextCursor(cursor)
        self._find_next(wrap=False)

    def _find_next(self, wrap: bool = True):
        if self._messages is None:
            return
        q = (self._search_input.text() or "").strip()
        if not q:
            return
        found = self._messages.find(q)
        if not found and wrap:
            cursor = self._messages.textCursor()
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.Start)
            self._messages.setTextCursor(cursor)
            self._messages.find(q)

    def _find_prev(self, wrap: bool = True):
        if self._messages is None:
            return
        q = (self._search_input.text() or "").strip()
        if not q:
            return
        found = self._messages.find(q, QtGui.QTextDocument.FindFlag.FindBackward)
        if not found and wrap:
            cursor = self._messages.textCursor()
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
            self._messages.setTextCursor(cursor)
            self._messages.find(q, QtGui.QTextDocument.FindFlag.FindBackward)

    def _handle_logout(self):
        if self._win is None:
            return
        if QtWidgets.QMessageBox.question(self._win, "Logout", "Logout and close client?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._win.close()

    # -------------------- Friends / Moments (client-side) --------------------

    def _load_local_state(self):
        """Load local-only state (moments). Friends/requests are loaded from server."""
        try:
            state = self._persistence.load_state() or {}
        except Exception:
            state = {}

        moments = state.get("moments") or []
        if isinstance(moments, list) and self._moments_feed is not None:
            self._moments_feed.clear()
            for m in reversed(moments[-200:]):
                ts = m.get("ts", "") if isinstance(m, dict) else ""
                text = m.get("text", "") if isinstance(m, dict) else str(m)
                self._moments_feed.addItem(f"[{ts}] {text}")

    def _save_local_state(self):
        """Persist local-only state (moments)."""
        try:
            state = self._persistence.load_state() or {}
        except Exception:
            state = {}
        try:
            self._persistence.save_state(state)
        except Exception:
            pass

    # -------------------- Friends / Conversations (server-backed) --------------------

    def _open_contacts(self):
        """Open Contacts quickly and focus on New Friends if there are pending requests."""
        if self._tabs is None:
            return
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i).startswith("Friends"):
                self._tabs.setCurrentIndex(i)
                break
        if self._friends_tabs is not None:
            txt = self._friends_tabs.tabText(1) if self._friends_tabs.count() > 1 else ""
            if "New Friends" in txt and "(" in txt:
                self._friends_tabs.setCurrentIndex(1)

    async def _initial_sync(self):
        await self._refresh_conversations()
        await self._refresh_friends()
        await self._refresh_incoming()
        await self._refresh_outgoing()
        self._update_contacts_badge()

    def _start_badge_timer(self):
        if self._badge_timer is not None:
            return
        self._badge_timer = QtCore.QTimer()
        self._badge_timer.setInterval(4000)
        self._badge_timer.timeout.connect(lambda: self._async_service.run_async(self._refresh_incoming(light=True)))
        self._badge_timer.start()

    def _update_contacts_badge(self, pending: int | None = None):
        if pending is None:
            pending = 0
            if self._incoming_requests is not None:
                for i in range(self._incoming_requests.count()):
                    it = self._incoming_requests.item(i)
                    if it and it.data(QtCore.Qt.ItemDataRole.UserRole):
                        pending += 1
        # Chats tab no longer has a Contacts button (WeChat-style UX).
        if self._tabs is not None:
            for i in range(self._tabs.count()):
                if self._tabs.tabText(i).startswith("Friends"):
                    self._tabs.setTabText(i, f"Friends ({pending})" if pending > 0 else "Friends")
                    break
        if self._friends_tabs is not None and self._friends_tabs.count() >= 2:
            self._friends_tabs.setTabText(1, f"New Friends ({pending})" if pending > 0 else "New Friends")

    async def _refresh_conversations(self):
        try:
            res = await self._api_client.list_conversations(limit=50)
            if isinstance(res, dict) and res.get("success"):
                convs = res.get("conversations") or []
                self._conv_manager.sync_conversations(convs)
                self._bridge.convo_list_changed.emit()
        except Exception:
            pass

    async def _refresh_friends(self):
        if self._friends_list is None:
            return
        try:
            res = await self._api_client.list_friends()
            if isinstance(res, dict) and res.get("success"):
                friends = res.get("friends") or []
                self._friends_list.clear()
                for f in friends:
                    name = f.get("username") if isinstance(f, dict) else str(f)
                    online = f.get("is_online") if isinstance(f, dict) else None
                    label = f"{name}  ·  {'online' if online else 'offline'}" if online is not None else str(name)
                    it = QtWidgets.QListWidgetItem(label)
                    it.setData(QtCore.Qt.ItemDataRole.UserRole, str(name))
                    self._friends_list.addItem(it)
        except Exception as e:
            self._bridge.system_message.emit(f"Failed to load friends: {e}")

    async def _refresh_incoming(self, light: bool = False):
        if self._incoming_requests is None:
            return
        try:
            res = await self._api_client.incoming_friend_requests()
            if isinstance(res, dict) and res.get("success"):
                reqs = res.get("requests") or []
                if light:
                    pending = sum(1 for r in reqs if isinstance(r, dict) and r.get('status') == 'pending')
                    self._update_contacts_badge(pending)
                    return

                self._incoming_requests.clear()
                pending_count = 0
                for r in reqs:
                    if not isinstance(r, dict):
                        continue
                    rid = r.get("id")
                    frm = r.get("from")
                    msg = r.get("message") or ""
                    status = r.get("status") or "pending"
                    when = r.get("created_at") or ""
                    text = f"{frm}  ·  {msg}" if msg else f"{frm}"
                    if when:
                        text = f"{text}  ·  {when}"
                    it = QtWidgets.QListWidgetItem(text)
                    if status == "pending":
                        pending_count += 1
                        it.setBackground(QtGui.QColor(255, 245, 230))
                        it.setData(QtCore.Qt.ItemDataRole.UserRole, int(rid) if rid is not None else None)
                    else:
                        it.setForeground(QtGui.QBrush(QtGui.QColor('#777')))
                        it.setData(QtCore.Qt.ItemDataRole.UserRole, None)
                    self._incoming_requests.addItem(it)

                self._update_contacts_badge(pending_count)
        except Exception as e:
            if not light:
                self._bridge.system_message.emit(f"Failed to load requests: {e}")

    async def _refresh_outgoing(self):
        if self._outgoing_requests is None:
            return
        try:
            res = await self._api_client.outgoing_friend_requests()
            if isinstance(res, dict) and res.get("success"):
                reqs = res.get("requests") or []
                self._outgoing_requests.clear()
                for r in reqs:
                    if not isinstance(r, dict):
                        continue
                    to = r.get("to")
                    msg = r.get("message") or ""
                    status = r.get("status") or "pending"
                    when = r.get("created_at") or ""
                    text = f"To {to}  ·  {status}"
                    if msg:
                        text += f"  ·  {msg}"
                    if when:
                        text += f"  ·  {when}"
                    self._outgoing_requests.addItem(text)
        except Exception as e:
            self._bridge.system_message.emit(f"Failed to load outgoing: {e}")

    def _sync_selected_user_to_add_box(self):
        if self._user_search_results is None or self._add_friend_to is None:
            return
        it = self._user_search_results.currentItem()
        if not it:
            return
        username = it.data(QtCore.Qt.ItemDataRole.UserRole) or ""
        if username:
            self._add_friend_to.setText(str(username))

    def _search_users_from_ui(self):
        if self._user_search_input is None:
            return
        q = (self._user_search_input.text() or "").strip()
        self._async_service.run_async(self._search_users(q))

    async def _search_users(self, q: str):
        if self._user_search_results is None:
            return
        try:
            res = await self._api_client.list_users(q=q, limit=50)
            self._user_search_results.clear()
            if isinstance(res, dict) and res.get("success"):
                users = res.get("users") or []
                for u in users:
                    if not isinstance(u, dict):
                        continue
                    name = u.get("username")
                    if not name or name == self._username:
                        continue
                    online = bool(u.get("is_online", False))
                    label = f"{name}  ·  {'online' if online else 'offline'}"
                    it = QtWidgets.QListWidgetItem(label)
                    it.setData(QtCore.Qt.ItemDataRole.UserRole, str(name))
                    self._user_search_results.addItem(it)
        except Exception as e:
            self._bridge.system_message.emit(f"Search failed: {e}")

    def _send_friend_request_from_ui(self):
        if self._add_friend_to is None:
            return
        to_user = (self._add_friend_to.text() or "").strip()
        msg = (self._add_friend_msg.text() or "").strip() if self._add_friend_msg is not None else ""
        if not to_user:
            return
        self._async_service.run_async(self._send_friend_request(to_user, msg))

    async def _send_friend_request(self, to_user: str, msg: str):
        try:
            res = await self._api_client.send_friend_request(to_username=to_user, message=msg)
            if isinstance(res, dict) and res.get("success"):
                self._bridge.system_message.emit(f"Friend request sent to {to_user}.")
                await self._refresh_outgoing()
                if self._add_friend_msg is not None:
                    self._add_friend_msg.setText("")
            else:
                self._bridge.system_message.emit(str((res or {}).get("message", "Failed to send request")))
        except Exception as e:
            self._bridge.system_message.emit(f"Failed: {e}")

    def _chat_selected_friend(self):
        if self._friends_list is None:
            return
        it = self._friends_list.currentItem()
        if not it:
            return
        user = it.data(QtCore.Qt.ItemDataRole.UserRole) or it.text().split('·')[0].strip()
        self._open_dm(str(user))

    def _remove_selected_friend(self):
        if self._win is None:
            return
        QtWidgets.QMessageBox.information(self._win, "Not supported", "Removing friends is not implemented on server in this version.")

    def _accept_or_reject_selected(self, accept: bool):
        if self._incoming_requests is None:
            return
        it = self._incoming_requests.currentItem()
        if not it:
            return
        rid = it.data(QtCore.Qt.ItemDataRole.UserRole)
        if not rid:
            return
        self._async_service.run_async(self._accept_or_reject(int(rid), accept))

    async def _accept_or_reject(self, request_id: int, accept: bool):
        try:
            res = await (self._api_client.accept_friend_request(request_id) if accept else self._api_client.reject_friend_request(request_id))
            if isinstance(res, dict) and res.get("success"):
                await self._refresh_incoming()
                await self._refresh_friends()
                await self._refresh_conversations()
            else:
                self._bridge.system_message.emit(str((res or {}).get("message", "Operation failed")))
        except Exception as e:
            self._bridge.system_message.emit(f"Operation failed: {e}")

    def _toggle_pin(self):
        self._async_service.run_async(self._set_conversation_setting("pinned"))

    def _toggle_mute(self):
        self._async_service.run_async(self._set_conversation_setting("muted"))

    async def _set_conversation_setting(self, which: str):
        cid = getattr(self._conv_manager, "active_cid", "global")
        if cid == "global":
            return
        conv = self._conv_manager.get_conversation(cid)
        pinned = bool(getattr(conv, "pinned", False)) if conv else False
        muted = bool(getattr(conv, "muted", False)) if conv else False
        try:
            res = await (self._api_client.update_conversation_settings(cid, pinned=not pinned) if which == "pinned" else self._api_client.update_conversation_settings(cid, muted=not muted))
            if isinstance(res, dict) and res.get("success"):
                await self._refresh_conversations()
        except Exception as e:
            self._bridge.system_message.emit(f"Failed to update setting: {e}")

    def _update_pin_mute_buttons(self):
        cid = getattr(self._conv_manager, "active_cid", "global")
        if cid == "global":
            if self._pin_btn:
                self._pin_btn.setEnabled(False)
            if self._mute_btn:
                self._mute_btn.setEnabled(False)
            return
        conv = self._conv_manager.get_conversation(cid)
        pinned = bool(getattr(conv, "pinned", False)) if conv else False
        muted = bool(getattr(conv, "muted", False)) if conv else False
        if self._pin_btn:
            self._pin_btn.setEnabled(True)
            self._pin_btn.setText("Unpin" if pinned else "Pin")
        if self._mute_btn:
            self._mute_btn.setEnabled(True)
            self._mute_btn.setText("Unmute" if muted else "Mute")

    async def _load_history_for_active(self, req_id: int, expected_cid: str):
        """Load server history for the active DM.

        Fixes UI "flash to blank" by:
        - not wiping UI immediately
        - dropping stale async responses when user switches conversations
        - parsing server payload keys correctly (content/message)
        - avoiding wiping local cache if server returns empty
        """
        cid = getattr(self._conv_manager, "active_cid", "global")
        if cid == "global":
            return
        # Stale response guard
        if req_id != self._history_req_seq or str(cid) != str(expected_cid):
            return
        try:
            res = await self._api_client.get_history(cid, limit=60)
            if not (isinstance(res, dict) and res.get("success")):
                return
            msgs = res.get("messages") or []
            conv = self._conv_manager.get_conversation(cid) or self._conv_manager.create_conversation(cid, name=cid)

            new_items: list[MessageItem] = []
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                sender = m.get("sender") or ""
                body = m.get("content") if m.get("content") is not None else (m.get("message") or "")
                ts = m.get("created_at") or ""
                is_self = (str(sender).lower() == str(self._username).lower())
                item = MessageItem.create(str(sender), str(body), is_self=is_self)
                if ts:
                    item.timestamp = str(ts)
                new_items.append(item)

            # If server returns empty but we already have local content, don't wipe it.
            if new_items or not getattr(conv, "items", None):
                conv.items = []
                for it in new_items:
                    conv.add_message(it)
            conv.mark_read()

            # Still active? then re-render.
            if req_id == self._history_req_seq and str(getattr(self._conv_manager, "active_cid", "")) == str(expected_cid):
                self._bridge.convo_list_changed.emit()
                self._bridge.message_added.emit(MessageItem.create("System", "", is_system=True), True)
        except Exception:
            pass

    def _handle_post_moment(self):
        if self._moment_input is None or self._moments_feed is None:
            return
        text = (self._moment_input.toPlainText() or "").strip()
        if not text:
            return
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # persist structured
        try:
            state = self._persistence.load_state() or {}
        except Exception:
            state = {}
        moments = state.get("moments")
        if not isinstance(moments, list):
            moments = []
        moments.append({"ts": ts, "text": text})
        state["moments"] = moments
        try:
            self._persistence.save_state(state)
        except Exception:
            pass
        # update UI
        self._moments_feed.insertItem(0, f"[{ts}] {text}")
        self._moment_input.setPlainText("")

    # -------------------- Emoji --------------------

    def _show_emoji_menu(self):
        if self._emoji_btn is None or self._input is None:
            return
        if self._emoji_menu is None:
            self._emoji_menu = QtWidgets.QMenu(self._win)
            # A small, curated set (fast, cross-platform).
            emojis = [
                "😀", "😅", "😂", "😊", "😍", "😘", "😎", "🤔", "😭", "😡",
                "👍", "👎", "🙏", "👏", "💪", "🎉", "🔥", "✅", "❌", "❤️",
                "💯", "✨", "⭐", "🌙", "☕", "🍜", "🍺", "🎮", "📌", "📎",
            ]
            for e in emojis:
                act = self._emoji_menu.addAction(e)
                act.triggered.connect(lambda _=False, x=e: self._insert_text(x))
        self._emoji_menu.exec(self._emoji_btn.mapToGlobal(QtCore.QPoint(0, self._emoji_btn.height())))

    def _insert_text(self, text: str):
        if self._input is None:
            return
        cursor = self._input.textCursor()
        cursor.insertText(text)
        self._input.setTextCursor(cursor)

    # -------------------- Utils --------------------

    @staticmethod
    def _escape_html(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))