"""
AloneChat message protocol types.

MIGRATED from core/message/protocol.py.
This is the CANONICAL MessageType enum. All other modules MUST import from here.
No duplicate MessageType anywhere else.
"""

import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

MAX_MESSAGE_SIZE = 524288  # 512 KiB


class ProtocolError(Exception):
    """Raised when a received message violates the protocol."""


class MessageType(IntEnum):
    """Canonical message type enum.

    All other modules MUST import MessageType from here. Do not define
    duplicate MessageType enums anywhere else.
    """

    TEXT = 1
    JOIN = 2
    LEAVE = 3
    HELP = 4
    COMMAND = 5
    ENCRYPTED = 6
    HEARTBEAT = 7


@dataclass
class Message:
    """A message in the AloneChat protocol.

    Serialization is JSON with ``type`` stored as the integer value of the
    :class:`MessageType` enum.
    """

    type: MessageType
    sender: str
    content: str
    target: Optional[str] = None
    command: Optional[str] = None

    def serialize(self) -> str:
        """Serialize the message to a JSON string."""
        data: dict = {
            "type": self.type.value,
            "sender": self.sender,
            "content": self.content,
        }
        if self.target is not None:
            data["target"] = self.target
        if self.command is not None:
            data["command"] = self.command
        return json.dumps(data)

    @classmethod
    def deserialize(cls, data: str) -> "Message":
        """Deserialize a JSON string back into a :class:`Message`.

        Raises:
            ProtocolError: If the data is invalid.
        """
        if len(data) > MAX_MESSAGE_SIZE:
            raise ProtocolError(
                f"Message too large: {len(data)} bytes"
                f" (max {MAX_MESSAGE_SIZE})"
            )

        try:
            obj = json.loads(data)
        except json.JSONDecodeError as e:
            raise ProtocolError(f"Invalid JSON: {e}") from e

        if not isinstance(obj, dict):
            raise ProtocolError("Message must be a JSON object")

        for field in ("type", "sender", "content"):
            if field not in obj:
                raise ProtocolError(f"Missing required field: {field}")

        try:
            msg_type = MessageType(obj["type"])
        except ValueError as e:
            raise ProtocolError(
                f"Invalid message type: {obj.get('type')}"
            ) from e

        if not isinstance(obj.get("sender"), str):
            raise ProtocolError("Sender must be a string")
        if not isinstance(obj.get("content"), str):
            raise ProtocolError("Content must be a string")

        return cls(
            type=msg_type,
            sender=obj["sender"],
            content=obj["content"],
            target=obj.get("target"),
            command=obj.get("command"),
        )
