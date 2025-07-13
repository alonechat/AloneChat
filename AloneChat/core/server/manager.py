from dataclasses import dataclass
from typing import Dict
import time
import asyncio
import websockets
from typing import Set
from ..message.protocol import Message, MessageType

@dataclass
class UserSession:
    user_id: str
    last_active: float

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, UserSession] = {}

    def add_session(self, user_id: str):
        self.sessions[user_id] = UserSession(
            user_id=user_id,
            last_active=time.time()
        )

    def remove_session(self, user_id: str):
        self.sessions.pop(user_id, None)

    def check_inactive(self, timeout: int = 300):
        current = time.time()
        inactive = [
            uid for uid, session in self.sessions.items()
            if current - session.last_active > timeout
        ]
        for uid in inactive:
            self.remove_session(uid)
        return inactive
    

class WebSocketManager:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.sessions = {}

    async def handler(self, websocket):
        self.clients.add(websocket)
        try:
            async for message in websocket:
                msg = Message.deserialize(message)
                if msg.type == MessageType.JOIN:
                    self.sessions[msg.sender] = websocket
                await self.process_message(msg)
        finally:
            self.clients.discard(websocket)
            for user, ws in list(self.sessions.items()):
                if ws == websocket:
                    del self.sessions[user]

    async def process_message(self, msg):
        if msg.type == MessageType.KICK and msg.sender == "admin":
            if target_ws := self.sessions.get(msg.target):
                await target_ws.close()
        elif msg.type == MessageType.HELP:
            help_msg = Message(MessageType.TEXT, "SERVER", "Commands: /help, /join, /kick")
            await self.sessions[msg.sender].send(help_msg.serialize())
        else:
            await self.broadcast(msg)

    async def broadcast(self, msg):
        if self.clients:
            tasks = [asyncio.create_task(client.send(msg.serialize())) for client in self.clients]
            await asyncio.gather(*tasks)

    async def run(self):
        async with websockets.serve(self.handler, self.host, self.port):
            print(f"Server running on ws://{self.host}:{self.port}")
            await asyncio.Future()
