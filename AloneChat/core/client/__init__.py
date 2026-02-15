"""AloneChat client package.

This module intentionally avoids importing optional UI backends (curses / GUI)
at import time so that starting the server does not require any GUI or terminal
UI dependencies.

UI backends are imported lazily by `run_client()`.
"""

from .client_base import Client
from .runner import run_client

# Optional UI backends (lazy/optional)
try:
    from .curses_client import CursesClient  # type: ignore
except Exception:  # pragma: no cover
    CursesClient = None  # type: ignore

try:
    from .qt_client import QtClient  # type: ignore
except Exception:  # pragma: no cover
    QtClient = None  # type: ignore

try:
    from .qt_gui_client import QtGUIClient  # type: ignore
except Exception:  # pragma: no cover
    QtGUIClient = None  # type: ignore

try:
    from .gui_client import SimpleGUIClient  # type: ignore
except Exception:  # pragma: no cover
    SimpleGUIClient = None  # type: ignore

__all__ = [
    'Client',
    'run_client',
    'CursesClient',
    'QtClient',
    'QtGUIClient',
    'SimpleGUIClient',
]
