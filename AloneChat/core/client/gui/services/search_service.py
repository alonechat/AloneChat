"""AloneChat GUI search service.

This repository supports multiple UI front-ends:

* Tk/ttk GUI (legacy)
* Qt (PyQt6) GUI

The original implementation typed the searchable widgets as a Tk-specific
``WinUI3MessageCard``. That created an unnecessary hard dependency on
``tkinter`` even when running the Qt client (on some Linux builds, Python is
installed without Tk bindings).

This module is now UI-agnostic: it works with any "message card" object that
provides:

* ``content``: str
* optional ``set_highlight(on: bool, strong: bool = False)``

The Qt client currently performs search directly within a ``QTextBrowser`` and
passes an empty list here; keeping this service maintains compatibility with
the legacy GUI layer and persistence hooks.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class MessageCardLike(Protocol):
    """Duck-typed interface for searchable message items."""

    content: str

    def set_highlight(self, on: bool, strong: bool = False) -> Any:  # pragma: no cover
        ...


class SearchService:
    """Service for searching messages in the UI."""

    def __init__(self):
        self._message_cards: List[MessageCardLike] = []
        self._search_hits: List[int] = []
        self._search_idx: int = -1
        self._query: str = ""

    def set_message_cards(self, cards: List[MessageCardLike]) -> None:
        """Update the list of message cards to search."""
        self._message_cards = cards
        self._recompute()

    def search(self, query: str) -> int:
        """Perform search and return number of hits."""
        self._query = (query or "").strip().lower()
        self._recompute()
        return len(self._search_hits)

    def _recompute(self) -> None:
        """Recompute search hits."""
        self._clear_highlight()
        self._search_hits = []
        self._search_idx = -1

        if not self._query:
            return

        for i, card in enumerate(self._message_cards):
            if self._query in ((getattr(card, "content", "") or "").lower()):
                self._search_hits.append(i)
                self._safe_highlight(card, on=True, strong=False)

        if self._search_hits:
            self._search_idx = 0
            self._focus_current()

    def next_result(self) -> Optional[int]:
        """Move to next search result. Returns index or None."""
        if not self._search_hits:
            return None
        self._search_idx = (self._search_idx + 1) % len(self._search_hits)
        self._focus_current()
        return self._search_hits[self._search_idx]

    def prev_result(self) -> Optional[int]:
        """Move to previous search result. Returns index or None."""
        if not self._search_hits:
            return None
        self._search_idx = (self._search_idx - 1) % len(self._search_hits)
        self._focus_current()
        return self._search_hits[self._search_idx]

    def _focus_current(self) -> None:
        """Highlight current hit and dim others."""
        if not self._search_hits:
            return

        idx = self._search_hits[self._search_idx]
        for i, card in enumerate(self._message_cards):
            if i == idx:
                self._safe_highlight(card, on=True, strong=True)
            elif i in self._search_hits:
                self._safe_highlight(card, on=True, strong=False)

    def _safe_highlight(self, card: MessageCardLike, on: bool, strong: bool) -> None:
        """Call highlight if present. Qt client may pass plain objects."""
        if hasattr(card, "set_highlight"):
            try:
                # type: ignore[misc]
                card.set_highlight(on, strong=strong)
            except Exception:
                pass

    def _clear_highlight(self) -> None:
        """Clear all highlights."""
        for card in self._message_cards:
            self._safe_highlight(card, on=False, strong=False)

    def clear(self) -> None:
        """Clear search state."""
        self._clear_highlight()
        self._search_hits = []
        self._search_idx = -1
        self._query = ""

    def get_current_hit_widget(self) -> Optional[MessageCardLike]:
        """Get the currently highlighted message card."""
        if not self._search_hits or self._search_idx < 0:
            return None
        idx = self._search_hits[self._search_idx]
        if 0 <= idx < len(self._message_cards):
            return self._message_cards[idx]
        return None

    @property
    def hit_count(self) -> int:
        """Number of search hits."""
        return len(self._search_hits)

    @property
    def current_index(self) -> int:
        """Current position in search results (0-based)."""
        return self._search_idx if self._search_idx >= 0 else 0
