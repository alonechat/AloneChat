"""
Message area component for chat view.
Contains scrollable message display and message card management.
"""
from typing import Optional, List, TYPE_CHECKING

from ..components import WinUI3ScrollableFrame, WinUI3MessageCard
from ..models.data import MessageItem

if TYPE_CHECKING:
    from ..services.conversation_manager import ConversationManager


class MessageArea:
    """Scrollable message display area."""
    
    def __init__(self, parent, conversation_manager: 'ConversationManager',
                 on_reply: Optional[callable] = None):
        self.parent = parent
        self.conv_manager = conversation_manager
        self.on_reply = on_reply
        
        self.container: Optional[WinUI3ScrollableFrame] = None
        self.message_cards: List[WinUI3MessageCard] = []
    
    def build(self) -> WinUI3ScrollableFrame:
        """Build and return the message container."""
        self.container = WinUI3ScrollableFrame(self.parent)
        return self.container
    
    def render_conversation(self):
        """Render the active conversation messages."""
        if not self.container:
            return
        
        if hasattr(self.container, 'content') and self.container.content:
            for w in list(self.container.content.winfo_children()):
                w.destroy()
        self.message_cards = []
        
        conv = self.conv_manager.get_active_conversation()
        if not conv:
            return
        
        for item in conv.items:
            card = self._create_message_card(item)
            card.pack(fill="x", pady=4)
            self.message_cards.append(card)
        
        if hasattr(self.container, 'scroll_to_bottom'):
            self.container.scroll_to_bottom()
    
    def _create_message_card(self, item: MessageItem) -> WinUI3MessageCard:
        """Create a message card from a message item."""
        on_reply = None if item.is_system else self.on_reply
        return WinUI3MessageCard(
            self.container.content,
            sender=item.sender,
            content=item.content,
            is_self=item.is_self,
            is_system=item.is_system,
            timestamp=item.timestamp,
            status=item.status,
            on_reply=on_reply,
        )
    
    def add_message_card(self, item: MessageItem) -> WinUI3MessageCard:
        """Add a single message card to the view."""
        card = self._create_message_card(item)
        card.pack(fill="x", pady=4)
        self.message_cards.append(card)
        self.container.scroll_to_bottom()
        return card
    
    def scroll_to_bottom(self):
        """Scroll to bottom of messages."""
        if self.container:
            self.container.scroll_to_bottom()
    
    def scroll_to_card(self, card: WinUI3MessageCard):
        """Scroll to a specific message card."""
        if self.container:
            self.container.scroll_to_widget(card)
    
    def get_message_cards(self) -> List[WinUI3MessageCard]:
        """Get all message cards in current view."""
        return self.message_cards
    
    def destroy(self):
        """Destroy the message container."""
        if self.container:
            self.container.destroy()
            self.container = None
        self.message_cards = []
