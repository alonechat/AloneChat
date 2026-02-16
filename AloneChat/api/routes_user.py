"""
User and private chat API routes.

Provides high-level API endpoints for user management and private messaging.
"""

import logging
from typing import List, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from .routes_base import app, JWT_SECRET, JWT_ALGORITHM, update_user_online_status
import jwt
import time

logger = logging.getLogger(__name__)


def _get_ws_manager():
    """Get WebSocket manager (lazy import to avoid circular dependency)."""
    from .routes_api import get_ws_manager
    return get_ws_manager()


class UserStatusRequest(BaseModel):
    status: str


class UserStatusResponse(BaseModel):
    success: bool
    user_id: str
    status: str
    message: Optional[str] = None


class UserInfoResponse(BaseModel):
    success: bool
    user_id: str
    display_name: Optional[str] = None
    status: str
    last_seen: Optional[float] = None
    is_online: bool


class OnlineUsersResponse(BaseModel):
    success: bool
    users: List[str]
    count: int


class PrivateMessageRequest(BaseModel):
    recipient: str
    content: str


class PrivateMessageResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    session_id: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    success: bool
    session_id: str
    messages: List[dict]
    count: int


class RecentChatsResponse(BaseModel):
    success: bool
    chats: List[dict]
    count: int


class PendingMessagesResponse(BaseModel):
    success: bool
    messages: List[dict]
    count: int


def _get_current_user(request: Request) -> str:
    """Extract current user from request."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No valid authentication token provided")
    
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/user/status/{user_id}", response_model=UserStatusResponse)
async def get_user_status(user_id: str, request: Request):
    """
    Get user status.
    
    Args:
        user_id: User identifier
        
    Returns:
        User status information
    """
    _ = _get_current_user(request)
    
    manager = _get_ws_manager()
    user_info = manager.user_manager.get_user(user_id)
    
    if not user_info:
        return UserStatusResponse(
            success=False,
            user_id=user_id,
            status="unknown",
            message="User not found"
        )
    
    return UserStatusResponse(
        success=True,
        user_id=user_id,
        status=user_info.status.name.lower()
    )


@app.post("/api/user/status", response_model=UserStatusResponse)
async def set_user_status(status_req: UserStatusRequest, request: Request):
    """
    Set current user's status.
    
    Args:
        status_req: Status request with new status
        
    Returns:
        Updated status information
    """
    username = _get_current_user(request)
    
    from AloneChat.core.server.user import UserStatus
    
    status_map = {
        "online": UserStatus.ONLINE,
        "away": UserStatus.AWAY,
        "busy": UserStatus.BUSY,
        "offline": UserStatus.OFFLINE
    }
    
    status_str = status_req.status.lower()
    if status_str not in status_map:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {list(status_map.keys())}")
    
    manager = _get_ws_manager()
    new_status = status_map[status_str]
    
    success = manager.user_manager.set_status(username, new_status)
    
    if not success:
        return UserStatusResponse(
            success=False,
            user_id=username,
            status=status_str,
            message="Failed to update status"
        )
    
    if status_str == "offline":
        update_user_online_status(username, False)
    else:
        update_user_online_status(username, True)
    
    return UserStatusResponse(
        success=True,
        user_id=username,
        status=status_str,
        message="Status updated successfully"
    )


@app.get("/api/user/info/{user_id}", response_model=UserInfoResponse)
async def get_user_info(user_id: str, request: Request):
    """
    Get detailed user information.
    
    Args:
        user_id: User identifier
        
    Returns:
        Detailed user information
    """
    _ = _get_current_user(request)
    
    manager = _get_ws_manager()
    user_info = manager.user_manager.get_user(user_id)
    
    if not user_info:
        return UserInfoResponse(
            success=False,
            user_id=user_id,
            status="unknown",
            is_online=False
        )
    
    return UserInfoResponse(
        success=True,
        user_id=user_id,
        display_name=user_info.display_name,
        status=user_info.status.name.lower(),
        last_seen=user_info.last_seen,
        is_online=user_info.status.name.lower() != "offline"
    )


@app.get("/api/users/online", response_model=OnlineUsersResponse)
async def get_online_users(request: Request):
    """
    Get list of online users.
    
    Returns:
        List of online user IDs
    """
    _ = _get_current_user(request)
    
    manager = _get_ws_manager()
    online_users = manager.user_manager.get_online_users()
    
    return OnlineUsersResponse(
        success=True,
        users=list(online_users),
        count=len(online_users)
    )


@app.get("/api/users/all")
async def get_all_users(request: Request):
    """
    Get all registered users with their status.
    
    Returns:
        List of all users with status
    """
    _ = _get_current_user(request)
    
    manager = _get_ws_manager()
    all_users = manager.user_manager.get_all_users()
    
    users_list = [
        {
            "user_id": user_id,
            "display_name": info.display_name,
            "status": info.status.name.lower(),
            "is_online": info.status.name.lower() != "offline"
        }
        for user_id, info in all_users.items()
    ]
    
    return {
        "success": True,
        "users": users_list,
        "count": len(users_list)
    }


@app.post("/api/chat/private", response_model=PrivateMessageResponse)
async def send_private_message(msg_req: PrivateMessageRequest, request: Request):
    """
    Send a private message to another user.
    
    Args:
        msg_req: Private message request with recipient and content
        
    Returns:
        Message delivery status
    """
    sender = _get_current_user(request)
    recipient = msg_req.recipient
    content = msg_req.content
    
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")
    
    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient is required")
    
    if sender == recipient:
        raise HTTPException(status_code=400, detail="Cannot send message to yourself")
    
    manager = _get_ws_manager()
    
    is_online = manager.user_manager.is_online(recipient)
    
    session = manager.private_chat_manager.record_message(
        sender=sender,
        recipient=recipient,
        content=content,
        is_delivered=is_online
    )
    
    from AloneChat.core.message.protocol import Message, MessageType
    
    message = Message(
        MessageType.TEXT,
        sender,
        content,
        target=recipient
    )
    
    if is_online:
        await manager.send_to_user(recipient, message)
        await manager.send_to_user(sender, message)
    else:
        await manager.send_to_user(sender, message)
    
    return PrivateMessageResponse(
        success=True,
        message="Message sent successfully",
        session_id=session.session_id
    )


@app.get("/api/chat/history/{other_user}", response_model=ChatHistoryResponse)
async def get_chat_history(other_user: str, request: Request, limit: int = 50):
    """
    Get chat history with another user.
    
    Args:
        other_user: The other user in the conversation
        limit: Maximum number of messages to return
        
    Returns:
        Chat history
    """
    current_user = _get_current_user(request)
    
    manager = _get_ws_manager()
    
    session_id = manager.private_chat_manager.generate_session_id(current_user, other_user)
    history = manager.private_chat_manager.get_chat_history(current_user, other_user, limit)
    
    messages = [
        {
            "sender": msg[0],
            "content": msg[1],
            "timestamp": msg[2]
        }
        for msg in history
    ]
    
    return ChatHistoryResponse(
        success=True,
        session_id=session_id,
        messages=messages,
        count=len(messages)
    )


@app.get("/api/chat/recent", response_model=RecentChatsResponse)
async def get_recent_chats(request: Request, limit: int = 10):
    """
    Get recent private chat sessions.
    
    Args:
        limit: Maximum number of sessions to return
        
    Returns:
        List of recent chat sessions
    """
    current_user = _get_current_user(request)
    
    manager = _get_ws_manager()
    sessions = manager.private_chat_manager.get_recent_chats(current_user, limit)
    
    chats = [
        {
            "session_id": session.session_id,
            "partner": session.get_partner(current_user),
            "last_activity": session.last_activity,
            "message_count": session.message_count
        }
        for session in sessions
    ]
    
    return RecentChatsResponse(
        success=True,
        chats=chats,
        count=len(chats)
    )


@app.get("/api/chat/pending", response_model=PendingMessagesResponse)
async def get_pending_messages(request: Request):
    """
    Get pending messages for current user (messages received while offline).
    
    Returns:
        List of pending messages
    """
    current_user = _get_current_user(request)
    
    manager = _get_ws_manager()
    pending = manager.private_chat_manager.get_pending_messages(current_user)
    
    messages = [
        {
            "sender": msg.sender,
            "content": msg.message,
            "timestamp": msg.timestamp,
            "delivered": msg.delivered
        }
        for msg in pending
    ]
    
    return PendingMessagesResponse(
        success=True,
        messages=messages,
        count=len(messages)
    )


@app.post("/api/chat/pending/clear")
async def clear_pending_messages(request: Request):
    """
    Clear all pending messages for current user.
    
    Returns:
        Number of messages cleared
    """
    current_user = _get_current_user(request)
    
    manager = _get_ws_manager()
    count = manager.private_chat_manager.clear_pending_messages(current_user)
    
    return {
        "success": True,
        "cleared_count": count,
        "message": f"Cleared {count} pending messages"
    }


@app.get("/api/chat/sessions")
async def get_chat_sessions(request: Request):
    """
    Get all private chat sessions for current user.
    
    Returns:
        List of all chat sessions
    """
    current_user = _get_current_user(request)
    
    manager = _get_ws_manager()
    sessions = manager.private_chat_manager.get_user_sessions(current_user)
    
    sessions_list = [
        {
            "session_id": session.session_id,
            "partner": session.get_partner(current_user),
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "message_count": session.message_count
        }
        for session in sessions
    ]
    
    return {
        "success": True,
        "sessions": sessions_list,
        "count": len(sessions_list)
    }


@app.delete("/api/chat/session/{other_user}")
async def end_chat_session(other_user: str, request: Request):
    """
    End a private chat session.
    
    Args:
        other_user: The other user in the session
        
    Returns:
        Status of operation
    """
    current_user = _get_current_user(request)
    
    manager = _get_ws_manager()
    success = manager.private_chat_manager.end_session(current_user, other_user)
    
    if not success:
        return {
            "success": False,
            "message": "Session not found"
        }
    
    return {
        "success": True,
        "message": "Session ended successfully"
    }


@app.get("/api/stats")
async def get_server_stats(request: Request):
    """
    Get server statistics.
    
    Returns:
        Server statistics including user and chat counts
    """
    _ = _get_current_user(request)
    
    manager = _get_ws_manager()
    
    return {
        "success": True,
        "stats": {
            "users": {
                "total": manager.user_manager.get_user_count(),
                "online": manager.user_manager.get_online_count()
            },
            "private_chats": {
                "active_sessions": manager.private_chat_manager.get_session_count(),
                "total_messages": manager.private_chat_manager.get_total_message_count()
            },
            "server": {
                "is_running": manager.is_running
            }
        }
    }
