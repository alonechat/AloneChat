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
        self._reply_label: Optional[QtWidgets.QLabel] = None

    # -------------------- Lifecycle --------------------

    def run(self):
        # Qt app
        self._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
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

        main = QtWidgets.QHBoxLayout(central)

        # Left: conversations
        left = QtWidgets.QVBoxLayout()
        self._convos = QtWidgets.QListWidget()
        self._convos.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

        left.addWidget(QtWidgets.QLabel("Conversations"))
        left.addWidget(self._convos, 1)

        btn_row = QtWidgets.QHBoxLayout()
        new_btn = QtWidgets.QPushButton("New DM")
        search_btn = QtWidgets.QPushButton("Search")
        logout_btn = QtWidgets.QPushButton("Logout")
        btn_row.addWidget(new_btn)
        btn_row.addWidget(search_btn)
        btn_row.addWidget(logout_btn)
        left.addLayout(btn_row)

        # Right: messages + input
        right = QtWidgets.QVBoxLayout()

        self._messages = QtWidgets.QTextBrowser()
        self._messages.setOpenExternalLinks(True)
        self._messages.setReadOnly(True)

        self._reply_label = QtWidgets.QLabel("")
        self._reply_label.setStyleSheet("color: #666;")
        self._reply_label.setWordWrap(True)
        self._reply_label.hide()

        self._input = QtWidgets.QPlainTextEdit()
        self._input.setPlaceholderText("Type a message… (Ctrl+Enter to send)")
        self._input.setFixedHeight(110)

        self._send_btn = QtWidgets.QPushButton("Send")

        right.addWidget(self._messages, 1)
        right.addWidget(self._reply_label)
        right.addWidget(self._input)
        right.addWidget(self._send_btn)

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

        # Events
        self._send_btn.clicked.connect(self._handle_send_clicked)
        self._convos.currentItemChanged.connect(self._handle_convo_selected)
        new_btn.clicked.connect(self._handle_new_dm)
        search_btn.clicked.connect(self._handle_search)
        logout_btn.clicked.connect(self._handle_logout)

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
        """Rebuild the left conversation list from ConversationManager.

        IMPORTANT: we must not assume extra helper APIs exist on ConversationManager.
        The canonical storage in the legacy GUI is an internal dict of conversations.
        So we detect the available shape and derive the cid list accordingly.
        """
        if self._convos is None:
            return

        # Remember selection
        current_cid = None
        cur = self._convos.currentItem()
        if cur is not None:
            current_cid = cur.data(QtCore.Qt.ItemDataRole.UserRole)

        # Derive conversation ids from the legacy data model
        cids = []
        if hasattr(self._conv_manager, "conversation_ids"):
            try:
                cids = list(self._conv_manager.conversation_ids)
            except Exception:
                cids = []
        if not cids:
            for attr in ("_conversations", "conversations"):
                if hasattr(self._conv_manager, attr):
                    store = getattr(self._conv_manager, attr)
                    if isinstance(store, dict):
                        cids = list(store.keys())
                    else:
                        try:
                            # list/iterable of Conversation
                            cids = [getattr(c, "cid", None) or getattr(c, "id", None) for c in store]
                            cids = [c for c in cids if c]
                        except Exception:
                            cids = []
                    if cids:
                        break

        # Ensure global exists and is first (matches legacy GUI expectations)
        if "global" not in cids:
            cids = ["global"] + cids
        else:
            cids = ["global"] + [c for c in cids if c != "global"]

        self._convos.blockSignals(True)
        self._convos.clear()

        for cid in cids:
            conv = None
            try:
                conv = self._conv_manager.get_conversation(cid)
            except Exception:
                conv = None
            if not conv and hasattr(self._conv_manager, "_conversations"):
                conv = getattr(self._conv_manager, "_conversations", {}).get(cid)
            if not conv:
                # Ensure the conversation exists in the manager (legacy GUI always has 'global')
                if hasattr(self._conv_manager, "create_conversation"):
                    try:
                        default_name = "Global" if cid == "global" else cid
                        self._conv_manager.create_conversation(cid, name=default_name)
                    except Exception:
                        pass
                # Re-fetch after attempting creation
                try:
                    conv = self._conv_manager.get_conversation(cid)
                except Exception:
                    conv = None
                if not conv and hasattr(self._conv_manager, "_conversations"):
                    conv = getattr(self._conv_manager, "_conversations", {}).get(cid)
            if not conv:
                continue

            label = getattr(conv, "name", cid) or cid
            unread = getattr(conv, "unread", 0) or 0
            if unread > 0:
                label = f"{label} ({unread})"

            it = QtWidgets.QListWidgetItem(label)
            it.setData(QtCore.Qt.ItemDataRole.UserRole, cid)
            self._convos.addItem(it)

            # Restore selection
            if (current_cid and cid == current_cid) or (not current_cid and cid == getattr(self._conv_manager, "active_cid", "global")):
                self._convos.setCurrentItem(it)

        self._convos.blockSignals(False)


    def _handle_convo_selected(self, current, _prev):
        if not current:
            return
        cid = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if cid:
            # Keep semantics aligned with original GUI implementation
            if hasattr(self._conv_manager, 'switch_conversation'):
                self._conv_manager.switch_conversation(cid)
            else:
                self._conv_manager.active_cid = cid
            self._render_active_conversation()

    def _render_active_conversation(self):
        if self._messages is None:
            return
        self._messages.clear()
        conv = self._conv_manager.get_conversation(self._conv_manager.active_cid)
        items = conv.items if conv else []
        for item in items:
            self._append_message(item)

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

    def _handle_new_dm(self):
        if self._win is None:
            return
        user, ok = QtWidgets.QInputDialog.getText(self._win, "New DM", "Send DM to username:")
        if not ok or not user.strip():
            return
        cid = user.strip()
        # DM conversations are keyed by username; keep behavior consistent with original GUI ConversationManager
        self._conv_manager.create_conversation(cid, name=cid)
        # Keep semantics aligned with original GUI implementation
        if hasattr(self._conv_manager, 'switch_conversation'):
            self._conv_manager.switch_conversation(cid)
        else:
            self._conv_manager.active_cid = cid
        self._refresh_convo_list()
        self._render_active_conversation()

        self._add_system_message_ui(f"DM started with {user.strip()}.")

    def _handle_search(self):
        if not self._win or not self._messages:
            return
        q, ok = QtWidgets.QInputDialog.getText(self._win, "Search", "Search text in current conversation:")
        if not ok or not q.strip():
            return
        # simple highlight in rendered HTML by re-rendering with <mark>
        cid = self._conv_manager.active_cid
        self._messages.clear()
        conv = self._conv_manager.get_conversation(cid)
        items = conv.items if conv else []
        for item in items:
            content = item.content
            if q.strip().lower() in content.lower():
                content = re.sub(re.escape(q.strip()), lambda m: f"<mark>{m.group(0)}</mark>", content, flags=re.IGNORECASE)
            tmp = MessageItem(sender=item.sender, content=content, timestamp=item.timestamp, ts=item.ts, is_self=item.is_self, is_system=item.is_system, status=item.status)
            self._append_message(tmp)

    def _handle_logout(self):
        if self._win is None:
            return
        if QtWidgets.QMessageBox.question(self._win, "Logout", "Logout and close client?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._win.close()

    # -------------------- Utils --------------------

    @staticmethod
    def _escape_html(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))