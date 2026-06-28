"""
AloneChat Server — clean public API.

Re-exports all services from the DI container for convenience.
This module is the recommended entry point for code that needs
to access server-side business logic.

Usage::

    from AloneChat.server import get_container

    container = get_container()
    auth_svc = container.auth_service
    user_svc = container.user_service

    # Or access types directly:
    from AloneChat.server import AuthService, Status, UserInfo
"""

# -- Auth ---------------------------------------------------------------
from AloneChat.server.auth import AuthService, AuthResult, RegisterResult

# -- User ---------------------------------------------------------------
from AloneChat.server.user import UserService, UserInfo, Status

# -- Message ------------------------------------------------------------
from AloneChat.server.message import MessageService, MessageQueue, DeliveryResult

# -- Chat ---------------------------------------------------------------
from AloneChat.server.chat import ChatService, ChatSession

# -- Friend -------------------------------------------------------------
from AloneChat.server.friend import FriendService, FriendInfo, FriendRequest

__all__ = [
    # Container (preferred entry point)
    "AppContainer",
    "get_container",

    # Auth
    "AuthService",
    "AuthResult",
    "RegisterResult",

    # User
    "UserService",
    "UserInfo",
    "Status",

    # Message
    "MessageService",
    "MessageQueue",
    "DeliveryResult",

    # Chat
    "ChatService",
    "ChatSession",

    # Friend
    "FriendService",
    "FriendInfo",
    "FriendRequest",
]
