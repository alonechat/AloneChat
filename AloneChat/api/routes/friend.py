"""
Friend routes for AloneChat API.
"""

import json
from fastapi import APIRouter, HTTPException, Request

from AloneChat.api.models import FriendRequestModel, FriendActionRequest, SetRemarkRequest
from AloneChat.core.message import Message, MessageType
from AloneChat.core.server import get_friend_service, get_message_service


router = APIRouter(prefix="/api", tags=["friends"])


def _get_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/friends")
async def get_friends(request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    friends = friend_service.get_friends(current_user)

    return {
        "success": True,
        "friends": [f.to_dict() for f in friends],
        "count": len(friends)
    }


@router.post("/friends/request")
async def send_friend_request(req: FriendRequestModel, request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    result = friend_service.send_friend_request(current_user, req.to_user, req.message)

    if result.get('success'):
        message_service = get_message_service()
        notification = Message(
            MessageType.TEXT,
            "SYSTEM",
            json.dumps({
                "type": "friend_request",
                "from": current_user,
                "message": req.message
            }),
            target=req.to_user
        )
        await message_service.send_to_user(req.to_user, notification)

    return result


@router.post("/friends/accept")
async def accept_friend_request(req: FriendActionRequest, request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    result = friend_service.accept_friend_request(req.request_id, current_user)

    if result.get('success'):
        friend_request = friend_service._db.get_friend_request(req.request_id)
        if friend_request:
            from_user = friend_request.get('from_user')
            if from_user:
                message_service = get_message_service()
                notification = Message(
                    MessageType.TEXT,
                    "SYSTEM",
                    json.dumps({
                        "type": "friend_request_accepted",
                        "by": current_user
                    }),
                    target=from_user
                )
                await message_service.send_to_user(from_user, notification)

    return result


@router.post("/friends/reject")
async def reject_friend_request(req: FriendActionRequest, request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    result = friend_service.reject_friend_request(req.request_id, current_user)

    return result


@router.post("/friends/remove")
async def remove_friend(req: FriendActionRequest, request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    result = friend_service.remove_friend(current_user, req.request_id)

    return result


@router.post("/friends/remark")
async def set_friend_remark(req: SetRemarkRequest, request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    result = friend_service.set_remark(current_user, req.friend_id, req.remark)

    return result


@router.get("/friends/requests/pending")
async def get_pending_friend_requests(request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    requests = friend_service.get_pending_requests(current_user)

    return {
        "success": True,
        "requests": [r.to_dict() for r in requests],
        "count": len(requests)
    }


@router.get("/friends/requests/sent")
async def get_sent_friend_requests(request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    requests = friend_service.get_sent_requests(current_user)

    return {
        "success": True,
        "requests": [r.to_dict() for r in requests],
        "count": len(requests)
    }


@router.get("/friends/search")
async def search_users(request: Request, query: str, limit: int = 20):
    current_user = _get_user(request)

    if not query or len(query) < 1:
        return {"success": True, "users": [], "count": 0}

    friend_service = get_friend_service()
    users = friend_service.search_users(query, current_user, limit)

    return {
        "success": True,
        "users": users,
        "count": len(users)
    }


@router.get("/friends/check/{user_id}")
async def check_friendship(user_id: str, request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()
    is_friend = friend_service.is_friend(current_user, user_id)

    return {
        "success": True,
        "is_friend": is_friend,
        "user_id": user_id
    }
