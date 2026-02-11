#!/usr/bin/env python3
"""
GUI Client Example for AloneChat

This is the modern GUI client with:
- Clean, modern interface
- Simple user interactions
- Proper bounds management
- Responsive layout
"""

from AloneChat.core.client import SimpleGUIClient


def main():
    """Run the GUI client."""
    # Create client
    client = SimpleGUIClient(
        host="localhost",
        port=8765
    )
    
    # Start the GUI
    client.run()


if __name__ == "__main__":
    main()
