"""
A command processing system for AloneChat client.
Handles parsing and processing of chat commands.
"""

from AloneChat.core.message.protocol import Message, MessageType


class CommandSystem:
    """
    Static class for processing chat commands.
    Handles command recognition and message creation.
    """
    # Dictionary mapping command strings to their message types and handlers
    COMMANDS = {
        "/help": {"type": MessageType.HELP, "handler": None},
        # TODO: Write these commands
    }

    @classmethod
    def process(cls, input_str, sender):
        """
        Process input string and convert to the appropriate message type.

        Args:
            input_str (str): User input string to process
            sender (str): Username of the message sender

        Returns:
            Message: Processed message object
        """
        if input_str.startswith('/'):
            # Split command and content
            parts = input_str.split(maxsplit=1)
            cmd = parts[0]
            content = parts[1] if len(parts) > 1 else ""

            # Check if command exists and create the appropriate message
            if cmd in cls.COMMANDS:
                return Message(
                    type=cls.COMMANDS[cmd]["type"],
                    sender=sender,
                    content=content,
                    target="None"
                )
        # Return as a regular text message if not a command
        return Message(MessageType.TEXT, sender, input_str)