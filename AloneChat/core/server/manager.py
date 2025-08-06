"""
Server session management module for AloneChat application.
Handles user sessions and their lifecycle management.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict
from typing import Set

import websockets

from AloneChat.core.client.command import COMMANDS as COMMANDS
from ..message.protocol import Message, MessageType


@dataclass
class UserSession:
    """
    Data class representing a user session.

    Attributes:
        user_id (str): Unique identifier for the user
        last_active (float): Timestamp of last user activity
    """
    user_id: str
    last_active: float

class SessionManager:
    """
    Manages user sessions and their states in the chat server.
    Handles session creation, removal, and activity monitoring.
    """
    def __init__(self):
        """Initialize an empty session manager."""
        self.sessions: Dict[str, UserSession] = {}

    def add_session(self, user_id: str):
        """
        Add a new user session.

        Args:
            user_id (str): Unique identifier for the user
        """
        self.sessions[user_id] = UserSession(
            user_id=user_id,
            last_active=time.time()
        )

    def remove_session(self, user_id: str):
        """
        Remove a user session.

        Args:
            user_id (str): Unique identifier for the user to remove
        """
        self.sessions.pop(user_id, None)

    def check_inactive(self, timeout: int = 300):
        """
        Check for inactive sessions based on a timeout period.

        Args:
            timeout (int): Timeout period in seconds (default: 300)

        Returns:
            list: List of inactive user IDs
        """
        current = time.time()
        inactive = [
            uid for uid, session in self.sessions.items()
            if current - session.last_active > timeout
        ]
        for uid in inactive:
            self.remove_session(uid)
        return inactive
    

class WebSocketManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(WebSocketManager, cls).__new__(cls)
        return cls._instance

    @staticmethod
    def get_instance():
        if WebSocketManager._instance is None:
            return WebSocketManager()
        return WebSocketManager._instance
    
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        if not hasattr(self, 'clients'):
            self.clients = set()
        if not hasattr(self, 'sessions'):
            self.sessions = {}
        # 确保每次初始化都更新端口
        print(f"WebSocketManager initialized with port: {self.port}")

    async def handler(self, websocket):
        # 验证认证令牌
        try:
            from urllib.parse import urlparse, parse_qs
            import jwt
            from AloneChat.config import config
            # 导入更新用户在线状态的函数
            from AloneChat.web.routes import update_user_online_status
            JWT_SECRET = config.JWT_SECRET
            JWT_ALGORITHM = config.JWT_ALGORITHM

            print("开始WebSocket连接认证")
            # 尝试从URL参数获取令牌
            request_path = websocket.request.path
            print(f"请求路径: {request_path}")
            query_params = {}
            if '?' in request_path:
                path_part, query_part = request_path.split('?', 1)
                query_params = parse_qs(query_part)
                print(f"查询参数: {query_params}")
            token = query_params.get('token', [None])[0]
            print(f"从URL获取的令牌: {token}")

            # 如果URL中没有令牌，尝试从请求头的Cookie中获取
            if not token:
                cookie_header = websocket.request.headers.get('Cookie', '')
                print(f"Cookie头: {cookie_header}")
                for cookie in cookie_header.split(';'):
                    if 'authToken=' in cookie:
                        token = cookie.split('=')[1].strip()
                        print(f"从Cookie获取的令牌: {token}")
                        break

                if not token:
                    error_msg = Message(MessageType.TEXT, "SERVER", "缺少认证令牌，请先登录")
                    await websocket.send(error_msg.serialize())
                    await websocket.close(code=1008, reason="未授权访问")
                    return

            # 验证令牌
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                username = payload.get('sub')
                if not username:
                    raise ValueError("令牌中缺少用户名")

                # 使用令牌中的用户名注册会话
                if username in self.sessions:
                    error_msg = Message(MessageType.TEXT, "SERVER", f"用户名 '{username}' 已在其他地方登录")
                    await websocket.send(error_msg.serialize())
                    await websocket.close(code=1008, reason="用户名已登录")
                    return
                self.sessions[username] = websocket
                print(f"User {username} connected")

                # 更新用户在线状态为在线
                update_user_online_status(username, True)

                # 发送用户加入消息
                join_msg = Message(MessageType.JOIN, username, "用户加入了聊天室")
                await self.broadcast(join_msg)
            except jwt.ExpiredSignatureError:
                error_msg = Message(MessageType.TEXT, "SERVER", "令牌已过期，请重新登录")
                await websocket.send(error_msg.serialize())
                await websocket.close(code=1008, reason="令牌过期")
                return
            except jwt.InvalidTokenError as e:
                error_msg = Message(MessageType.TEXT, "SERVER", f"无效的令牌: {str(e)}")
                await websocket.send(error_msg.serialize())
                await websocket.close(code=1008, reason="无效令牌")
                return
        except Exception as e:
            error_msg = Message(MessageType.TEXT, "SERVER", f"认证过程出错: {str(e)}")
            await websocket.send(error_msg.serialize())
            await websocket.close(code=1011, reason="服务器错误")
            return

        self.clients.add(websocket)
        try:
            async for message in websocket:
                msg = Message.deserialize(message)
                # 忽略JOIN消息，已通过令牌验证用户名
                if msg.type == MessageType.JOIN:
                    continue
                elif msg.type == MessageType.HEARTBEAT:
                    # 处理心跳消息，更新用户活动时间
                    if msg.sender in self.sessions:
                        # 可以在这里添加用户活动时间更新逻辑
                        pass
                await self.process_message(msg)
        except websockets.exceptions.ConnectionClosedError:
            # 处理连接关闭错误
            pass
        finally:
            # 确保移除客户端
            self.clients.discard(websocket)
            # 移除会话
            for username, ws in list(self.sessions.items()):
                if ws == websocket:
                    del self.sessions[username]
                    # 更新用户在线状态
                    update_user_online_status(username, False)
                    break

    async def process_message(self, msg):
        """
        Process incoming messages based on their type.
        """
        # 检查发送者是否在会话中
        if msg.sender not in self.sessions:
            print(f"警告: 收到来自未登录用户 {msg.sender} 的消息")
            return

        if msg.type == MessageType.COMMAND:
            parts = msg.content.split(maxsplit=1)
            cmd = parts[0]
            if cmd in list(COMMANDS.keys()):
                command_msg = Message(MessageType.TEXT, "COMMAND", COMMANDS[cmd]["handler"]())
                await self.sessions[msg.sender].send(command_msg.serialize())
        elif msg.type == MessageType.HEARTBEAT:  # 处理心跳消息
            # 回复pong消息以保持连接活跃
            pong_msg = Message(MessageType.HEARTBEAT, "SERVER", "pong")
            await self.sessions[msg.sender].send(pong_msg.serialize())
        else:
            await self.broadcast(msg)

    async def broadcast(self, msg):
        if self.clients:
            # 创建发送任务列表
            tasks = []
            for client in self.clients:
                # 为每个客户端创建一个发送任务，并添加异常处理
                task = asyncio.create_task(self._safe_send(client, msg.serialize()))
                tasks.append(task)
            # 等待所有任务完成
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, client, message):
        """
        安全地向客户端发送消息，处理可能的异常
        """
        # 导入更新用户在线状态的函数
        from AloneChat.web.routes import update_user_online_status
        try:
            await client.send(message)
        except Exception as e:
            # 记录错误但不中断其他消息发送
            print(f"发送消息失败: {e}")
            # 从客户端集合中移除无效连接
            if client in self.clients:
                self.clients.discard(client)
            # 查找并移除对应的会话
            for username, ws in list(self.sessions.items()):
                if ws == client:
                    del self.sessions[username]
                    # 更新用户在线状态
                    update_user_online_status(username, False)
                    # 广播用户离开的消息
                    leave_msg = Message(MessageType.LEAVE, username, "用户离开了聊天室")
                    await self.broadcast(leave_msg)
                    break

    async def run(self):
        # noinspection PyTypeChecker
        # 适配websockets 15.0.1版本API
        async with websockets.serve(
                self.handler,
                self.host, self.port
        ):
            print(f"Server running on ws://{self.host}:{self.port}")
            await asyncio.Future()
