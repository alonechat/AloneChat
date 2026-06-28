"""
User routes extracted from app.py.

Endpoints:
    GET  /api/users/online          — list online users
    GET  /api/users/status/{user_id} — get a user's status
    POST /api/users/status           — set the current user's status
    GET  /api/users/search           — search users by query
"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from AloneChat.di import container
from AloneChat.server import Status

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class UserStatusRequest(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

user_router = APIRouter(prefix="/api/users", tags=["users"])


# ---------------------------------------------------------------------------
# Auth helpers (mirrors app._get_user — kept local to avoid circular imports)
# ---------------------------------------------------------------------------


def _get_user(request: Request) -> str:
    """Extract the authenticated username set by AuthMiddleware."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# GET /api/users/online
# ---------------------------------------------------------------------------


@user_router.get("/online")
async def get_online_users(request: Request):
    """Return the list of currently online users."""
    _get_user(request)
    users = container.user_service.get_online_users()
    return {"success": True, "users": users, "count": len(users)}


# ---------------------------------------------------------------------------
# GET /api/users/status/{user_id}
# ---------------------------------------------------------------------------


@user_router.get("/status/{user_id}")
async def get_user_status(user_id: str, request: Request):
    """Return the status of a specific user."""
    _get_user(request)

    info = container.user_service.get_user_info(user_id)
    if not info:
        return {"success": False, "user_id": user_id, "status": "unknown"}

    return {
        "success": True,
        "user_id": user_id,
        "status": info.status.name.lower(),
        "is_online": info.status != Status.OFFLINE,
    }


# ---------------------------------------------------------------------------
# POST /api/users/status
# ---------------------------------------------------------------------------


@user_router.post("/status")
async def set_user_status(status_req: UserStatusRequest, request: Request):
    """Set the current user's online status."""
    username = _get_user(request)

    status_map = {
        "online": Status.ONLINE,
        "away": Status.AWAY,
        "busy": Status.BUSY,
        "offline": Status.OFFLINE,
    }

    status_str = status_req.status.lower()
    if status_str not in status_map:
        raise HTTPException(status_code=400, detail="Invalid status")

    await container.user_service.set_status(username, status_map[status_str])
    return {"success": True, "user_id": username, "status": status_str}


# ---------------------------------------------------------------------------
# GET /api/users/search
# ---------------------------------------------------------------------------


@user_router.get("/search")
async def search_users(
    request: Request,
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Search users by name (delegates to the friend service)."""
    current_user = _get_user(request)

    if not query.strip():
        return {"success": True, "users": [], "count": 0}

    users = await container.friend_service.search_users(query, current_user, limit)
    return {"success": True, "users": users, "count": len(users)}
