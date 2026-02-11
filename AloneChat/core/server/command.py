"""
A command processing system for AloneChat client.
Handles parsing and processing of chat commands.
"""

from AloneChat.core.client.plugin_loader import PluginManager
from AloneChat.core.message.protocol import Message, MessageType

COMMANDS = {}
MANAGER = PluginManager()


def load() -> dict | None:
    return MANAGER.load()

class CommandSystem:
    """
    Static class for processing chat commands.
    Handles command recognition and message creation.
    """
    global COMMANDS, MANAGER
    # Dictionary mapping command strings to their message types and handlers
    loaded_modules = load()

    if loaded_modules is not None:
        COMMANDS.update(load()) # type: ignore

    @classmethod
    def process(cls, input_str, sender, target=None):
        """
        Process input string and convert to the appropriate message type.

        Args:
            input_str (str): User input string to process
            sender (str): Username of the message sender
            target (str, optional): Target user for the message, if needed

        Returns:
            Message: Processed message object
        """
        # Check if command exists and create the appropriate message
        for cmd in COMMANDS:
            input_str = cmd["handler"].execute(input_str)

        # Return as a regular text message if not a command
        return Message(MessageType.TEXT, sender, input_str)