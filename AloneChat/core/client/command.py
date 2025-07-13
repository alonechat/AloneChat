from AloneChat.core.message.protocol import Message, MessageType


class CommandSystem:
    COMMANDS = {
        "/help": {"type": MessageType.HELP, "handler": None},
        "/join": {"type": MessageType.COMMAND, "handler": "handle_join"},
        "/kick": {"type": MessageType.KICK, "handler": "handle_kick"}
    }

    @classmethod
    def process(cls, input_str, sender):
        if input_str.startswith('/'):
            parts = input_str.split(maxsplit=1)
            cmd = parts[0]
            content = parts[1] if len(parts) > 1 else ""

            if cmd in cls.COMMANDS:
                return Message(
                    type=cls.COMMANDS[cmd]["type"],
                    sender=sender,
                    content=content,
                    target=content if cmd == "/kick" else None
                )
        return Message(MessageType.TEXT, sender, input_str)