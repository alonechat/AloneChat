import asyncio
import websockets
from typing import Set
from .protocol import Message, MessageType

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

    def start(self):
        asyncio.run(self.run())