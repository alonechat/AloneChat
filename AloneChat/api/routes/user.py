"""
User routes for AloneChat API.
"""

from fastapi import APIRouter, HTTPException, Request

from AloneChat.api.models import UserStatusRequest
from AloneChat.core.server import get_user_service, get_friend_service, Status


router = APIRouter(prefix="/api", tags=["users"])


def _get_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/user/status/{user_id}")
async def get_user_status(user_id: str, request: Request):
    current_user = _get_user(request)

    friend_service = get_friend_service()

    if user_id != current_user and not friend_service.is_friend(current_user, user_id):
        raise HTTPException(status_code=403, detail="Can only view your own or friends' status")

    info = get_user_service().get_user_info(user_id)

    if not info:
        return {"success": False, "user_id": user_id, "status": "unknown"}

    return {
        "success": True,
        "user_id": user_id,
        "status": info.status.name.lower(),
        "is_online": info.status != Status.OFFLINE
    }


@router.post("/user/status")
async def set_user_status(status_req: UserStatusRequest, request: Request):
    username = _get_user(request)

    status_map = {"online": Status.ONLINE, "away": Status.AWAY,
                  "busy": Status.BUSY, "offline": Status.OFFLINE}

    status_str = status_req.status.lower()
    if status_str not in status_map:
        raise HTTPException(status_code=400, detail="Invalid status")

    get_user_service().set_status(username, status_map[status_str])
    return {"success": True, "user_id": username, "status": status_str}


@router.get("/users/online")
async def get_online_users(request: Request):
    _get_user(request)
    users = get_user_service().get_online_users()
    return {"success": True, "users": users, "count": len(users)}


@router.get("/users/all")
async def get_all_users(request: Request):
    _get_user(request)
    users = get_user_service().get_all_users()
    return {"success": True, "users": users, "count": len(users)}
