"""
Modern, simplified GUI client for AloneChat with excellent user experience.

This module is a compatibility wrapper that re-exports the modular GUI client.
The actual implementation has been moved to the gui/ package for better organization.

Features:
- Clean, modern interface using ttk (themed tkinter widgets)
- Responsive layout that adapts to window size
- Proper bounds management - no out-of-window elements
- Simple, intuitive user interactions
- Modern card-based design with proper spacing
- Smooth scrolling and message history
- Keyboard shortcuts for power users
- Accessible design with proper contrast
"""

# Import the modular GUI client and re-export for backward compatibility
from AloneChat.core.client.gui import GUIClient as SimpleGUIClient
from AloneChat.core.client.gui.components import MessageCard
from AloneChat.core.client.gui.models import Theme, ModernStyles

# Maintain backward compatibility with old exports
__all__ = [
    'SimpleGUIClient',
    'MessageCard',
    'Theme',
    'ModernStyles',
]

# For direct imports, also expose the new modular structure
# Users can now import from either:
#   - AloneChat.core.client.gui_client (legacy)
#   - AloneChat.core.client.gui (new modular)
