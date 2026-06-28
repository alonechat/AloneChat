"""
Friend management service for AloneChat server.

Provides friend management logic including friend requests, friendships,
and user search.  All data access is delegated to FriendRepository and
UserRepository, which are received via __init__ (DI pattern).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from AloneChat.server.repositories.friend_repo import FriendRepository
from AloneChat.server.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class FriendRequest:
    """Represents a single friend request."""

    id: str
    from_user: str
    to_user: str
    message: str = ""
    status: str = "pending"
    created_at: Any = None

    def to_dict(self) -> Dict[str, Any]:
        if self.created_at is None:
            created_at_val = None
        elif hasattr(self.created_at, "isoformat"):
            created_at_val = self.created_at.isoformat()
        else:
            created_at_val = str(self.created_at)

        return {
            "id": self.id,
            "from_user": self.from_user,
            "to_user": self.to_user,
            "message": self.message,
            "status": self.status,
            "created_at": created_at_val,
        }


@dataclass
class FriendInfo:
    """Summarised information about a single friend."""

    user_id: str
    display_name: str = ""
    remark: str = ""
    status: str = "offline"
    is_online: bool = False
    last_seen: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        if self.last_seen is None:
            last_seen_val = 0.0
        elif isinstance(self.last_seen, (int, float)):
            last_seen_val = float(self.last_seen)
        elif isinstance(self.last_seen, datetime):
            last_seen_val = self.last_seen.timestamp()
        elif hasattr(self.last_seen, "timestamp"):
            last_seen_val = self.last_seen.timestamp()
        else:
            last_seen_val = 0.0

        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "remark": self.remark,
            "status": self.status,
            "is_online": self.is_online,
            "last_seen": last_seen_val,
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FriendService:
    """Friend management service.

    All database access is delegated to the injected ``FriendRepository`` and
    ``UserRepository`` instances.  No global singletons are accessed inside
    this class.

    Parameters
    ----------
    friend_repo : FriendRepository
        Data-access layer for friendships and friend requests.
    user_repo : UserRepository
        Data-access layer for user records.
    """

    def __init__(
        self,
        friend_repo: FriendRepository,
        user_repo: UserRepository,
    ) -> None:
        self._friend_repo = friend_repo
        self._user_repo = user_repo

    # ------------------------------------------------------------------
    # Friend requests
    # ------------------------------------------------------------------

    async def send_friend_request(
        self,
        from_user: str,
        to_user: str,
        message: str = "",
    ) -> Dict[str, Any]:
        """Send a friend request from ``from_user`` to ``to_user``."""
        if from_user == to_user:
            return {"success": False, "error": "Cannot add yourself as friend"}

        if not self._user_repo.user_exists(to_user):
            return {"success": False, "error": "User does not exist"}

        if self._friend_repo.is_friend(from_user, to_user):
            return {"success": False, "error": "Already friends"}

        if self._friend_repo.has_pending_request(from_user, to_user):
            return {"success": False, "error": "Pending request already exists"}

        request_id = str(uuid.uuid4())
        if self._friend_repo.create_friend_request(
            request_id, from_user, to_user, message
        ):
            logger.info("Friend request sent: %s -> %s", from_user, to_user)
            return {
                "success": True,
                "request_id": request_id,
                "message": "Friend request sent",
            }

        return {"success": False, "error": "Failed to send request"}

    async def accept_friend_request(
        self, request_id: str, user_id: str
    ) -> Dict[str, Any]:
        """Accept a pending friend request."""
        request = self._friend_repo.get_friend_request(request_id)

        if not request:
            return {"success": False, "error": "Request not found"}

        if request["to_user"] != user_id:
            return {"success": False, "error": "Not authorized"}

        if request["status"] != "pending":
            return {"success": False, "error": "Request already processed"}

        # Create the friendship FIRST so we can rollback the request
        # status if friendship creation fails.
        if not self._friend_repo.add_friend(request["from_user"], request["to_user"]):
            return {"success": False, "error": "Failed to create friendship"}

        if self._friend_repo.update_friend_request_status(request_id, "accepted"):
            logger.info(
                "Friend request accepted: %s <-> %s",
                request["from_user"],
                request["to_user"],
            )
            return {"success": True, "message": "Friend request accepted"}

        # Rollback: friendship was created but status update failed.
        self._friend_repo.remove_friend(request["from_user"], request["to_user"])
        logger.error(
            "Friend request status update failed, rolled back friendship: %s",
            request_id,
        )
        return {"success": False, "error": "Failed to accept request"}

    async def reject_friend_request(
        self, request_id: str, user_id: str
    ) -> Dict[str, Any]:
        """Reject a pending friend request."""
        request = self._friend_repo.get_friend_request(request_id)

        if not request:
            return {"success": False, "error": "Request not found"}

        if request["to_user"] != user_id:
            return {"success": False, "error": "Not authorized"}

        if request["status"] != "pending":
            return {"success": False, "error": "Request already processed"}

        if self._friend_repo.update_friend_request_status(request_id, "rejected"):
            logger.info(
                "Friend request rejected: %s -> %s",
                request["from_user"],
                request["to_user"],
            )
            return {"success": True, "message": "Friend request rejected"}

        return {"success": False, "error": "Failed to reject request"}

    # ------------------------------------------------------------------
    # Friendship management
    # ------------------------------------------------------------------

    async def add_friend(
        self,
        user_id: str,
        friend_id: str,
        remark: str = "",
    ) -> Dict[str, Any]:
        """Directly create a bidirectional friendship (no request flow).

        This is a convenience method for programmatic friendship creation
        that bypasses the request/accept workflow.
        """
        if user_id == friend_id:
            return {"success": False, "error": "Cannot add yourself as friend"}

        if not self._user_repo.user_exists(friend_id):
            return {"success": False, "error": "User does not exist"}

        if self._friend_repo.is_friend(user_id, friend_id):
            return {"success": False, "error": "Already friends"}

        if self._friend_repo.add_friend(user_id, friend_id, remark):
            logger.info("Friendship created: %s <-> %s", user_id, friend_id)
            return {"success": True, "message": "Friend added"}

        return {"success": False, "error": "Failed to add friend"}

    async def remove_friend(
        self, user_id: str, friend_id: str
    ) -> Dict[str, Any]:
        """Remove a friend relationship."""
        if not self._friend_repo.is_friend(user_id, friend_id):
            return {"success": False, "error": "Not friends"}

        if self._friend_repo.remove_friend(user_id, friend_id):
            logger.info("Friend removed: %s <-> %s", user_id, friend_id)
            return {"success": True, "message": "Friend removed"}

        return {"success": False, "error": "Failed to remove friend"}

    async def get_friends(self, user_id: str) -> List[FriendInfo]:
        """Return all active friends of ``user_id`` with their current status."""
        friends_data = self._friend_repo.get_friends(user_id)
        result: List[FriendInfo] = []

        for friend in friends_data:
            friend_id = friend["friend_id"]
            remark = friend.get("remark", "")

            user_data = self._user_repo.get_user(friend_id)
            if user_data:
                result.append(
                    FriendInfo(
                        user_id=friend_id,
                        display_name=user_data.display_name or friend_id,
                        remark=remark,
                        status=user_data.status or "offline",
                        is_online=bool(user_data.is_online),
                        last_seen=(
                            user_data.last_seen.timestamp()
                            if user_data.last_seen
                            else None
                        ),
                    )
                )
            else:
                result.append(
                    FriendInfo(
                        user_id=friend_id,
                        display_name=friend_id,
                        remark=remark,
                        status="offline",
                        is_online=False,
                        last_seen=None,
                    )
                )

        return result

    async def set_remark(
        self, user_id: str, friend_id: str, remark: str
    ) -> Dict[str, Any]:
        """Set a display remark for an existing friend."""
        if not self._friend_repo.is_friend(user_id, friend_id):
            return {"success": False, "error": "Not friends"}

        if self._friend_repo.set_friend_remark(user_id, friend_id, remark):
            return {"success": True, "message": "Remark updated"}

        return {"success": False, "error": "Failed to update remark"}

    async def is_friend(self, user_id: str, friend_id: str) -> bool:
        """Check whether two users are currently friends."""
        return self._friend_repo.is_friend(user_id, friend_id)

    # ------------------------------------------------------------------
    # Friend request queries
    # ------------------------------------------------------------------

    async def get_pending_requests(self, user_id: str) -> List[FriendRequest]:
        """Return all pending friend requests received by ``user_id``."""
        requests = self._friend_repo.get_pending_friend_requests(user_id)
        return [
            FriendRequest(
                id=r.get("id", ""),
                from_user=r.get("from_user", ""),
                to_user=r.get("to_user", ""),
                message=r.get("message", ""),
                status=r.get("status", "pending"),
                created_at=r.get("created_at"),
            )
            for r in requests
        ]

    async def get_sent_requests(self, user_id: str) -> List[FriendRequest]:
        """Return all pending friend requests sent by ``user_id``."""
        requests = self._friend_repo.get_sent_friend_requests(user_id)
        return [
            FriendRequest(
                id=r.get("id", ""),
                from_user=r.get("from_user", ""),
                to_user=r.get("to_user", ""),
                message=r.get("message", ""),
                status=r.get("status", "pending"),
                created_at=r.get("created_at"),
            )
            for r in requests
        ]

    # ------------------------------------------------------------------
    # User search
    # ------------------------------------------------------------------

    async def search_users(
        self,
        query: str,
        current_user: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search for users by user ID substring match.

        Results exclude ``current_user`` and include friendship status
        relative to ``current_user``.
        """
        all_users = self._user_repo.get_all_users()
        query_lower = query.lower()

        results: List[Dict[str, Any]] = []
        for user in all_users:
            if user.user_id == current_user:
                continue

            if query_lower not in user.user_id.lower():
                continue

            is_friend_val = self._friend_repo.is_friend(current_user, user.user_id)
            has_pending = self._friend_repo.has_pending_request(
                current_user, user.user_id
            )

            results.append(
                {
                    "user_id": user.user_id,
                    "display_name": user.display_name or user.user_id,
                    "status": user.status or "offline",
                    "is_online": bool(user.is_online),
                    "is_friend": is_friend_val,
                    "has_pending_request": has_pending,
                }
            )

            if len(results) >= limit:
                break

        return results
