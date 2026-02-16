"""
AloneChat Server - Pure computation and service layer.

This module provides business logic services without any transport concerns.
The API layer handles all HTTP/WebSocket interactions.

Architecture:
    Server Layer (this module):
        - auth.py: Authentication service
        - user.py: User management service
        - message.py: Message routing service
        - chat.py: Chat session service
        - database.py: Data persistence service
    
    API Layer (AloneChat.api):
        - Handles HTTP requests/responses
        - Handles WebSocket connections
        - Delegates all business logic to server services
"""

from .auth import AuthService, AuthResult, RegisterResult, get_auth_service
from .chat import ChatService, ChatSession, PendingMessage, get_chat_service
from .database import Database, UserData, get_database
from .friends import FriendService, FriendRequest, get_friend_service
from .message import DeliveryResult, MessageQueue, MessageService, get_message_service
from .user import Status, UserInfo, UserService, get_user_service, shutdown_user_service

__all__ = [
    'AuthService',
    'AuthResult', 
    'RegisterResult',
    'get_auth_service',
    
    'UserService',
    'UserInfo',
    'Status',
    'get_user_service',
    'shutdown_user_service',
    
    'MessageService',
    'MessageQueue',
    'DeliveryResult',
    'get_message_service',
    
    'ChatService',
    'ChatSession',
    'PendingMessage',
    'get_chat_service',
    
    'Database',
    'UserData',
    'get_database',

    'FriendService',
    'FriendRequest',
    'get_friend_service',
]
