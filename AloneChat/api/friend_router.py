"""
Friend routes for AloneChat API.

Extracted from app.py. All friend-related endpoints use the dependency
injection container for services and APIRouter for route grouping.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from AloneChat.di import container
from AloneChat.server import friend  # noqa: F401  — ensure server package is loaded

logger = logging.getLogger(__name__)

friend_router = APIRouter(prefix="/api/friends", tags=["friends"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class FriendRequestModel(BaseModel):
    to_user: str
    message: str = ""


class SetRemarkRequest(BaseModel):
    friend_id: str
    remark: str


class FriendIdRequest(BaseModel):
    friend_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user(request: Request) -> str:
    """Extract authenticated username from request state set by AuthMiddleware."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# Friend management
# ---------------------------------------------------------------------------


@friend_router.post("/add")
async def add_friend(req: FriendIdRequest, request: Request):
    """Directly add a friend relationship (no request/accept flow)."""
    current_user = _get_user(request)
    result = await container.friend_service.add_friend(current_user, req.friend_id)
    return result


@friend_router.post("/remove")
async def remove_friend(req: FriendIdRequest, request: Request):
    """Remove an existing friend relationship."""
    current_user = _get_user(request)
    result = await container.friend_service.remove_friend(current_user, req.friend_id)
    return result


@friend_router.get("/list")
async def get_friends(request: Request):
    """List all friends of the current user with their online status."""
    current_user = _get_user(request)
    friends = await container.friend_service.get_friends(current_user)
    return {
        "success": True,
        "friends": [f.to_dict() for f in friends],
        "count": len(friends),
    }


# ---------------------------------------------------------------------------
# Friend requests
# ---------------------------------------------------------------------------


@friend_router.post("/request")
async def send_friend_request(req: FriendRequestModel, request: Request):
    """Send a friend request to another user."""
    current_user = _get_user(request)
    result = await container.friend_service.send_friend_request(
        current_user, req.to_user, req.message,
    )

    if result.get("success"):
        # Notify the recipient via the message service.
        await container.message_service.send_message(
            sender="SYSTEM",
            recipient=req.to_user,
            content=json.dumps({
                "type": "friend_request",
                "from": current_user,
                "message": req.message,
            }),
        )

    return result


@friend_router.get("/requests/pending")
async def get_pending_friend_requests(request: Request):
    """Get pending friend requests received by the current user."""
    current_user = _get_user(request)
    requests = await container.friend_service.get_pending_requests(current_user)
    return {
        "success": True,
        "requests": [r.to_dict() for r in requests],
        "count": len(requests),
    }


@friend_router.get("/requests/sent")
async def get_sent_friend_requests(request: Request):
    """Get pending friend requests sent by the current user."""
    current_user = _get_user(request)
    requests = await container.friend_service.get_sent_requests(current_user)
    return {
        "success": True,
        "requests": [r.to_dict() for r in requests],
        "count": len(requests),
    }


@friend_router.post("/requests/{request_id}/accept")
async def accept_friend_request(request_id: str, request: Request):
    """Accept a pending friend request by its ID."""
    current_user = _get_user(request)
    result = await container.friend_service.accept_friend_request(
        request_id, current_user,
    )

    if result.get("success"):
        # Notify the sender that their request was accepted.
        friend_req = container.friend_repo.get_friend_request(request_id)
        if friend_req:
            from_user = friend_req.get("from_user")
            if from_user:
                await container.message_service.send_message(
                    sender="SYSTEM",
                    recipient=from_user,
                    content=json.dumps({
                        "type": "friend_request_accepted",
                        "by": current_user,
                    }),
                )

    return result


@friend_router.post("/requests/{request_id}/reject")
async def reject_friend_request(request_id: str, request: Request):
    """Reject a pending friend request by its ID."""
    current_user = _get_user(request)
    result = await container.friend_service.reject_friend_request(
        request_id, current_user,
    )
    return result


@friend_router.post("/remark")
async def set_friend_remark(req: SetRemarkRequest, request: Request):
    """Set or update a friend's display remark."""
    current_user = _get_user(request)
    result = await container.friend_service.set_remark(
        current_user, req.friend_id, req.remark,
    )
    return result


@friend_router.get("/search")
async def search_users(
    request: Request,
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Search for users by username prefix."""
    current_user = _get_user(request)
    users = await container.friend_service.search_users(query, current_user, limit)
    return {"success": True, "users": users, "count": len(users)}
