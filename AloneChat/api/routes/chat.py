"""
Chat routes for AloneChat API.
"""

from fastapi import APIRouter, HTTPException, Request

from AloneChat.api.models import PrivateMessageRequest
from AloneChat.core.message import Message, MessageType
from AloneChat.core.server import (
    get_user_service,
    get_message_service,
    get_chat_service,
    get_friend_service,
)


router = APIRouter(prefix="/api", tags=["chat"])


def _get_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post("/chat/private")
async def send_private_message(msg_req: PrivateMessageRequest, request: Request):
    sender = _get_user(request)

    if not msg_req.content or not msg_req.content.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if sender == msg_req.recipient:
        raise HTTPException(status_code=400, detail="Cannot message yourself")

    user_service = get_user_service()
    chat_service = get_chat_service()
    message_service = get_message_service()

    is_online = user_service.is_online(msg_req.recipient)

    chat_service.record_message(sender, msg_req.recipient, msg_req.content, is_online)

    message = Message(MessageType.TEXT, sender, msg_req.content, target=msg_req.recipient)

    await message_service.send_to_user(msg_req.recipient, message)
    await message_service.send_to_user(sender, message)

    return {"success": True, "message": "Message sent"}


@router.get("/chat/history/{other_user}")
async def get_chat_history(other_user: str, request: Request, limit: int = 50):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    if other_user != current_user and not friend_service.is_friend(current_user, other_user):
        raise HTTPException(status_code=403, detail="Can only view chat history with yourself or friends")

    history = get_chat_service().get_history(current_user, other_user, limit)
    return {"success": True, "messages": history, "count": len(history)}


@router.get("/chat/recent")
async def get_recent_chats(request: Request, limit: int = 10):
    current_user = _get_user(request)

    chats = get_chat_service().get_recent_chats(current_user, limit)
    return {"success": True, "chats": chats, "count": len(chats)}


@router.get("/chat/pending")
async def get_pending_messages(request: Request):
    current_user = _get_user(request)

    pending = get_chat_service().get_pending(current_user)
    messages = [
        {"sender": p.sender, "content": p.message, "timestamp": p.timestamp}
        for p in pending
    ]
    return {"success": True, "messages": messages, "count": len(messages)}


@router.post("/chat/pending/clear")
async def clear_pending_messages(request: Request):
    current_user = _get_user(request)

    count = get_chat_service().clear_pending(current_user)
    return {"success": True, "cleared_count": count}


@router.get("/stats")
async def get_stats(request: Request):
    _get_user(request)

    user_service = get_user_service()
    chat_service = get_chat_service()

    return {
        "success": True,
        "stats": {
            "users": {
                "online": len(user_service.get_online_users()),
            },
            "chats": {
                "sessions": chat_service.get_session_count(),
                "messages": chat_service.get_total_message_count()
            }
        }
    }
