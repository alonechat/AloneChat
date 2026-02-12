"""
Search service for finding messages.
"""
from typing import List, Callable, Optional
from ..components.message_card import WinUI3MessageCard


class SearchService:
    """Service for searching messages in the UI."""
    
    def __init__(self):
        self._message_cards: List[WinUI3MessageCard] = []
        self._search_hits: List[int] = []
        self._search_idx: int = -1
        self._query: str = ""
    
    def set_message_cards(self, cards: List[WinUI3MessageCard]) -> None:
        """Update the list of message cards to search."""
        self._message_cards = cards
        self._recompute()
    
    def search(self, query: str) -> int:
        """Perform search and return number of hits."""
        self._query = query.strip().lower()
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
            if self._query in (card.content or "").lower():
                self._search_hits.append(i)
                card.set_highlight(True, strong=False)
        
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
                card.set_highlight(True, strong=True)
            elif i in self._search_hits:
                card.set_highlight(True, strong=False)
    
    def _clear_highlight(self) -> None:
        """Clear all highlights."""
        for card in self._message_cards:
            card.set_highlight(False)
    
    def clear(self) -> None:
        """Clear search state."""
        self._clear_highlight()
        self._search_hits = []
        self._search_idx = -1
        self._query = ""
    
    def get_current_hit_widget(self) -> Optional[WinUI3MessageCard]:
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
