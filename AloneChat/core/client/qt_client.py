"""
Qt (PyQt6) client for AloneChat.

Goal: keep *network/protocol/data handling* identical to the terminal client,
while replacing only the UI layer to support Windows/macOS/Linux without curses.

This client reuses:
- AloneChatAPIClient for all server interactions (unchanged)
- AuthFlow for login/registration (unchanged API calls)
- MessageBuffer for message formatting/history (unchanged)

Qt is imported lazily so importing AloneChat does not require GUI libraries.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from AloneChat.api.client import AloneChatAPIClient
from .auth import AuthFlow
from .client_base import Client
from .ui import MessageBuffer
from .utils import DEFAULT_HOST, DEFAULT_API_PORT, REFRESH_RATE_HZ


__all__ = ["QtClient"]


class QtRenderer:
    """
    Minimal renderer interface compatible with AuthFlow expectations.

    For the chat session, actual painting is handled by MainWindow.
    For auth prompts, we use simple modal dialogs.
    """

    def __init__(self, window: "MainWindow"):
        self._window = window

    # --- Methods used by AuthFlow ---
    def draw_prompt(self, lines: list[str]) -> None:
        # Show prompt text in the window status area for context.
        text = "\n".join(lines)
        self._window.set_prompt_text(text)

    def clear(self) -> None:
        self._window.set_prompt_text("")

    def get_input_at_position(self, y: int, x: int, initial: str = "", mask: bool = False) -> str:
        # Coordinates are ignored in Qt; we use a modal input dialog.
        from PyQt6.QtWidgets import QInputDialog, QLineEdit

        echo = QLineEdit.EchoMode.Password if mask else QLineEdit.EchoMode.Normal
        value, ok = QInputDialog.getText(
            self._window,
            "AloneChat",
            "Input:",
            echo,
            text=initial,
        )
        return value if ok else ""

    def show_error(self, message: str, duration: float = 2.0) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self._window, "AloneChat - Error", message)

    def show_success(self, message: str, duration: float = 1.0) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self._window, "AloneChat", message)

    # --- Chat rendering ---
    def update_display(self, message_buffer: MessageBuffer, input_buffer: str) -> None:
        self._window.render_messages(message_buffer)


class MainWindow:  # QMainWindow subclass created lazily to avoid Qt import at module load
    pass


class QtClient(Client):
    """
    Qt-based chat client.

    Network/protocol behavior is the same as the terminal client because all
    server interaction is delegated to AloneChatAPIClient unchanged.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_API_PORT, max_history: int = 1000):
        super().__init__(host, port)

        self._api_client = AloneChatAPIClient(host, port)

        self._renderer: Optional[QtRenderer] = None
        self._message_buffer: Optional[MessageBuffer] = None
        self._auth_flow: Optional[AuthFlow] = None

        self._username: str = ""
        self._token: Optional[str] = None
        self._running: bool = False

        self._tasks: list[asyncio.Task] = []

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    async def _send_message(self, content: str) -> None:
        if not self.is_authenticated:
            if self._message_buffer:
                self._message_buffer.add_error_message("Not authenticated")
            return

        try:
            response = await self._api_client.send_message(content)
            if not response.get("success"):
                if self._message_buffer:
                    self._message_buffer.add_error_message(f"Failed to send: {response.get('message', 'Unknown error')}")
        except Exception as e:
            if self._message_buffer:
                self._message_buffer.add_error_message(f"Send error: {e}")

    async def _authenticate(self) -> bool:
        assert self._auth_flow is not None
        session = await self._auth_flow.show_auth_menu()
        if session is None:
            return False

        self._username = session.username
        self._token = session.token
        self._api_client.token = self._token
        self._api_client.username = self._username
        return True

    async def _handle_messages(self) -> None:
        assert self._message_buffer is not None
        while self._running:
            try:
                msg_data = await self._api_client.receive_message()

                if not isinstance(msg_data, dict):
                    await asyncio.sleep(0.1)
                    continue

                if not msg_data.get("success"):
                    error = msg_data.get("error")
                    if error and error != "Timeout waiting for message":
                        self._message_buffer.add_error_message(f"Receive error: {error}")
                    await asyncio.sleep(0.1)
                    continue

                sender = msg_data.get("sender")
                content = msg_data.get("content")
                if sender and content:
                    self._message_buffer.add_message(sender, content)

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    async def _render_loop(self) -> None:
        assert self._renderer is not None
        assert self._message_buffer is not None
        while self._running:
            try:
                self._renderer.update_display(self._message_buffer, "")
                await asyncio.sleep(1.0 / REFRESH_RATE_HZ)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def _cancel_tasks(self) -> None:
        for t in list(self._tasks):
            if not t.done():
                t.cancel()

    async def _async_main(self, window: "MainWindow") -> None:
        # Init components
        self._message_buffer = MessageBuffer(max_history=1000)
        self._renderer = QtRenderer(window)
        self._auth_flow = AuthFlow(self._renderer, self._api_client)
        self._running = True

        # Authenticate
        ok = await self._authenticate()
        if not ok:
            self._running = False
            window.request_close()
            return

        # Start chat session
        self._message_buffer.add_system_message("Connected to server using API")

        # Wire input submission
        window.set_submit_callback(self._send_message, self._message_buffer)

        # Run background tasks
        self._tasks = [
            asyncio.create_task(self._handle_messages(), name="qt_handle_messages"),
            asyncio.create_task(self._render_loop(), name="qt_render_loop"),
        ]

        try:
            await asyncio.gather(*self._tasks)
        finally:
            self._cancel_tasks()

    def run(self) -> None:
        """
        Start the Qt client.

        Uses qasync to run the asyncio event loop inside the Qt event loop, keeping
        all networking behavior identical to the async terminal client.
        """
        try:
            from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTextEdit, QLineEdit, QLabel
            from PyQt6.QtCore import Qt
            from qasync import QEventLoop
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Qt client requires PyQt6 and qasync.\n"
                "Install with: pip install PyQt6 qasync"
            ) from e

        class _MainWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("AloneChat (Qt)")
                self._submit_cb = None
                self._message_buffer: Optional[MessageBuffer] = None

                central = QWidget()
                self.setCentralWidget(central)
                layout = QVBoxLayout(central)

                self.prompt_label = QLabel("")
                self.prompt_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.prompt_label.setWordWrap(True)

                self.message_view = QTextEdit()
                self.message_view.setReadOnly(True)

                self.input_line = QLineEdit()
                self.input_line.setPlaceholderText("Type a message and press Enter…")

                layout.addWidget(self.prompt_label)
                layout.addWidget(self.message_view, 1)
                layout.addWidget(self.input_line)

                self.input_line.returnPressed.connect(self._on_return_pressed)

            def set_prompt_text(self, text: str) -> None:
                self.prompt_label.setText(text)

            def render_messages(self, message_buffer: MessageBuffer) -> None:
                # Determine how many lines can fit; keep same semantics as terminal:
                # show a window of messages based on buffer scroll offset.
                self._message_buffer = message_buffer
                visible_lines = self._calc_visible_lines()

                msgs = message_buffer.get_visible_messages(visible_lines)
                self.message_view.setPlainText("\n".join(msgs))

                if message_buffer.auto_scroll:
                    cursor = self.message_view.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.message_view.setTextCursor(cursor)

            
            def _calc_visible_lines(self) -> int:
                fm = self.message_view.fontMetrics()
                line_h = max(1, fm.lineSpacing())
                return max(5, int(self.message_view.viewport().height() / line_h) - 1)

            def set_submit_callback(self, cb, message_buffer: MessageBuffer) -> None:
                self._submit_cb = cb
                self._message_buffer = message_buffer

            def _on_return_pressed(self):
                text = self.input_line.text()
                if not text.strip():
                    return
                self.input_line.clear()
                if self._message_buffer:
                    self._message_buffer.auto_scroll = True
                if self._submit_cb:
                    # schedule coroutine on asyncio loop
                    asyncio.create_task(self._submit_cb(text))

            def request_close(self):
                self.close()

            def closeEvent(self, event):
                # Stop client when window closes
                try:
                    if hasattr(self, '_client_ref') and self._client_ref is not None:
                        self._client_ref._running = False
                        self._client_ref._cancel_tasks()
                except Exception:
                    pass
                event.accept()

            def keyPressEvent(self, event):
                # Scroll shortcuts to match terminal behavior
                if self._message_buffer is not None:
                    from AloneChat.core.client.ui.message_buffer import ScrollDirection
                    key = event.key()
                    if key == Qt.Key.Key_PageUp:
                        self._message_buffer.auto_scroll = False
                        self._message_buffer.scroll(ScrollDirection.PAGE_UP, self._calc_visible_lines())
                        event.accept()
                        return
                    if key == Qt.Key.Key_PageDown:
                        self._message_buffer.auto_scroll = False
                        self._message_buffer.scroll(ScrollDirection.PAGE_DOWN, self._calc_visible_lines())
                        event.accept()
                        return
                    if key == Qt.Key.Key_Home:
                        self._message_buffer.auto_scroll = False
                        self._message_buffer.scroll(ScrollDirection.HOME, self._calc_visible_lines())
                        event.accept()
                        return
                    if key == Qt.Key.Key_End:
                        self._message_buffer.auto_scroll = True
                        self._message_buffer.scroll(ScrollDirection.END, self._calc_visible_lines())
                        event.accept()
                        return

                super().keyPressEvent(event)

        # Bind instance for renderer typing
        global MainWindow
        MainWindow = _MainWindow  # type: ignore

        app = QApplication([])
        window = _MainWindow()
        window.show()

        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)

        # Attach running flag to window so closeEvent can stop loops
        window._client_ref = self  # type: ignore

        with loop:
            loop.create_task(self._async_main(window))
            loop.run_forever()

        # Cleanup
        self._running = False
        self._cancel_tasks()
