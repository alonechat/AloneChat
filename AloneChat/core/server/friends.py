"""Friend system service.

This module implements a minimal friend mechanism:
 - Users can send friend requests
 - Recipients can accept/reject
 - Only friends are allowed to start private chats

The API layer should call this service; the Database layer provides persistence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from AloneChat.core.logging import get_logger
from .database import get_database

logger = get_logger(__name__)


@dataclass
class FriendRequest:
    request_id: str
    from_user: str
    to_user: str
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FriendService:
    def __init__(self):
        self._db = get_database()

    def are_friends(self, user_id: str, other_user_id: str) -> bool:
        return self._db.are_friends(user_id, other_user_id)

    def list_friends(self, user_id: str) -> List[str]:
        return self._db.list_friends(user_id)

    def send_request(self, from_user: str, to_user: str) -> Dict:
        if from_user == to_user:
            return {"success": False, "error": "Cannot add yourself"}

        if not self._db.user_exists(to_user):
            return {"success": False, "error": "User does not exist"}

        if self._db.are_friends(from_user, to_user):
            return {"success": False, "error": "Already friends"}

        latest = self._db.get_latest_friend_request(from_user, to_user)
        if latest and latest.get('status') == 'pending':
            return {"success": True, "request_id": latest['request_id'], "status": "pending"}

        request_id = str(uuid.uuid4())
        ok = self._db.create_friend_request(from_user, to_user, request_id)
        if not ok:
            return {"success": False, "error": "Failed to create request"}

        return {"success": True, "request_id": request_id, "status": "pending"}

    def accept_request(self, current_user: str, from_user: str) -> Dict:
        # Find latest incoming request from from_user -> current_user
        latest = self._db.get_latest_friend_request(from_user, current_user)
        if not latest:
            return {"success": False, "error": "No request found"}
        if latest.get('status') != 'pending':
            return {"success": False, "error": f"Request is {latest.get('status')}"}

        rid = latest['request_id']
        if not self._db.upsert_friend_request_status(rid, 'accepted'):
            return {"success": False, "error": "Failed to update request"}

        if not self._db.add_friend_pair(current_user, from_user):
            return {"success": False, "error": "Failed to create friendship"}

        return {"success": True, "status": "accepted", "friend": from_user}

    def reject_request(self, current_user: str, from_user: str) -> Dict:
        latest = self._db.get_latest_friend_request(from_user, current_user)
        if not latest:
            return {"success": False, "error": "No request found"}
        if latest.get('status') != 'pending':
            return {"success": False, "error": f"Request is {latest.get('status')}"}

        rid = latest['request_id']
        ok = self._db.upsert_friend_request_status(rid, 'rejected')
        return {"success": bool(ok), "status": "rejected" if ok else "error"}

    def list_requests(self, user_id: str, direction: str = 'incoming', limit: int = 100) -> List[Dict]:
        return self._db.list_friend_requests(user_id, direction=direction, limit=limit)


_friend_service: Optional[FriendService] = None


def get_friend_service() -> FriendService:
    global _friend_service
    if _friend_service is None:
        _friend_service = FriendService()
    return _friend_service
