import json
from enum import Enum
from dataclasses import dataclass

class MessageType(Enum):
    TEXT = 1
    JOIN = 2
    LEAVE = 3
    HELP = 4
    COMMAND = 5
    KICK = 6
    ENCRYPTED = 7

@dataclass
class Message:
    type: MessageType
    sender: str
    content: str
    target: str = None

    def serialize(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "sender": self.sender,
            "content": self.content,
            "target": self.target
        })

    @classmethod
    def deserialize(cls, data: str) -> 'Message':
        obj = json.loads(data)
        return cls(
            type=MessageType(obj["type"]),
            sender=obj["sender"],
            content=obj["content"],
            target=obj.get("target")
        )