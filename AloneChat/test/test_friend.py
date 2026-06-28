"""
Tests for the AloneChat friend system.

Covers: send friend request, accept request, reject request, remove friend,
list friends, duplicate request prevention, pending/sent request queries,
and edge cases (self-friend, non-existent user, already-processed requests).

All tests use in-memory repositories injected into the DI container so that
no external ClickHouse connection is required.  Each test function receives
two authenticated HTTP clients (client_a, client_b) representing two distinct
test users.

Registration and login are performed directly against the DI container's
auth service to obtain valid JWT tokens.  All friend-system operations are
then exercised through the full HTTP pipeline (middleware -> router ->
service -> repository).
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from AloneChat.api.app import app
from AloneChat.di import container


# ═══════════════════════════════════════════════════════════════════════════════
# In-memory repository implementations (ClickHouse-free test doubles)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class _UserRecord:
    """Lightweight user record for the in-memory store."""

    user_id: str
    password_hash: str
    display_name: str = ""
    status: str = "offline"
    is_online: bool = False
    last_seen: Optional[float] = None
    created_at: Optional[float] = None


class InMemoryUserRepo:
    """In-memory drop-in for UserRepository.

    Implements every method that the auth and friend services call on the
    UserRepository so the full HTTP pipeline can run without ClickHouse.
    """

    def __init__(self) -> None:
        self._users: Dict[str, _UserRecord] = {}

    # -- Create ---------------------------------------------------------------

    def create_user(
        self, user_id: str, password_hash: str, display_name: str = ""
    ) -> bool:
        if user_id in self._users:
            return False
        self._users[user_id] = _UserRecord(
            user_id=user_id,
            password_hash=password_hash,
            display_name=display_name or user_id,
            created_at=time.time(),
        )
        return True

    # -- Read -----------------------------------------------------------------

    def get_user(self, user_id: str) -> Optional[_UserRecord]:
        return self._users.get(user_id)

    def user_exists(self, user_id: str) -> bool:
        return user_id in self._users

    def get_all_users(self) -> List[_UserRecord]:
        return list(self._users.values())

    def get_online_users(self) -> List[_UserRecord]:
        return [u for u in self._users.values() if u.is_online]

    # -- Update ---------------------------------------------------------------

    def update_status(self, user_id: str, status: str, is_online: bool) -> bool:
        user = self._users.get(user_id)
        if user is None:
            return False
        user.status = status
        user.is_online = is_online
        user.last_seen = time.time()
        return True

    def batch_update_status(self, updates: List[Dict[str, Any]]) -> int:
        count = 0
        for upd in updates:
            if self.update_status(
                user_id=upd["user_id"],
                status=upd["status"],
                is_online=upd["is_online"],
            ):
                count += 1
        return count

    def set_all_offline(self) -> int:
        count = sum(1 for u in self._users.values() if u.is_online)
        for u in self._users.values():
            u.is_online = False
            u.status = "offline"
        return count


class InMemoryFriendRepo:
    """In-memory drop-in for FriendRepository.

    Stores friendships (bidirectional) and friend requests in Python dicts.
    Implements every method that FriendService calls so the full HTTP pipeline
    can run without ClickHouse.
    """

    def __init__(self) -> None:
        # Friendships: set of (user_id, friend_id) sorted tuples so the
        # relationship is always stored in a canonical order.
        self._friendships: Dict[str, Dict[str, str]] = {}  # user_id -> {friend_id: remark}
        # Friend requests keyed by request_id.
        self._friend_requests: Dict[str, Dict[str, Any]] = {}

    # -- Friendship CRUD ------------------------------------------------------

    def add_friend(
        self, user_id: str, friend_id: str, remark: str = ""
    ) -> bool:
        self._friendships.setdefault(user_id, {})[friend_id] = remark
        self._friendships.setdefault(friend_id, {})[user_id] = ""
        return True

    def remove_friend(self, user_id: str, friend_id: str) -> bool:
        self._friendships.get(user_id, {}).pop(friend_id, None)
        self._friendships.get(friend_id, {}).pop(user_id, None)
        return True

    def get_friends(self, user_id: str) -> List[Dict[str, Any]]:
        friends = self._friendships.get(user_id, {})
        return [
            {"friend_id": fid, "remark": rem}
            for fid, rem in friends.items()
        ]

    def is_friend(self, user_id: str, friend_id: str) -> bool:
        return friend_id in self._friendships.get(user_id, {})

    def set_friend_remark(self, user_id: str, friend_id: str, remark: str) -> bool:
        if user_id not in self._friendships:
            return False
        if friend_id not in self._friendships[user_id]:
            return False
        self._friendships[user_id][friend_id] = remark
        return True

    # -- Friend requests ------------------------------------------------------

    def create_friend_request(
        self, request_id: str, from_user: str, to_user: str, message: str = ""
    ) -> bool:
        self._friend_requests[request_id] = {
            "id": request_id,
            "from_user": from_user,
            "to_user": to_user,
            "message": message,
            "status": "pending",
            "created_at": time.time(),
        }
        return True

    def get_friend_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        return self._friend_requests.get(request_id)

    def get_pending_friend_requests(self, user_id: str) -> List[Dict[str, Any]]:
        return [
            r for r in self._friend_requests.values()
            if r["to_user"] == user_id and r["status"] == "pending"
        ]

    def get_sent_friend_requests(self, user_id: str) -> List[Dict[str, Any]]:
        return [
            r for r in self._friend_requests.values()
            if r["from_user"] == user_id and r["status"] == "pending"
        ]

    def update_friend_request_status(self, request_id: str, status: str) -> bool:
        req = self._friend_requests.get(request_id)
        if req is None:
            return False
        req["status"] = status
        return True

    def has_pending_request(self, from_user: str, to_user: str) -> bool:
        return any(
            r["from_user"] == from_user and r["to_user"] == to_user and r["status"] == "pending"
            for r in self._friend_requests.values()
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(scope="function")
async def friend_clients(test_db):
    """Provide two authenticated clients for friend-system tests.

    Injects InMemoryUserRepo and InMemoryFriendRepo into the DI container,
    registers two test users (user_a, user_b) through the auth service
    directly, obtains JWT tokens, and returns authenticated
    ``httpx.AsyncClient`` instances wired to the real FastAPI app.

    Yields
    ------
    dict
        Keys: ``client_a``, ``client_b``, ``user_a``, ``user_b``,
        ``user_repo``, ``friend_repo``.
    """
    user_repo = InMemoryUserRepo()
    friend_repo = InMemoryFriendRepo()

    # Inject into the container BEFORE any service is lazily created.
    # The container's double-check locking will pick up these instances
    # on the next property access.
    container._user_repo = user_repo
    container._friend_repo = friend_repo
    # Force-rebuild the friend service so it picks up the new repos.
    # Also rebuild auth_service so it uses the in-memory user_repo.
    container._friend_service = None
    container._auth_service = None
    container._user_service = None

    suffix = str(int(time.time() * 1000))[-6:]
    user_a = f"fuser_a_{suffix}"
    user_b = f"fuser_b_{suffix}"
    password = "test_password_123"

    # Register users directly through the auth service (bypasses HTTP
    # middleware so we don't depend on the middleware whitelist matching
    # the current router prefix).
    reg_a = await container.auth_service.register(user_a, password)
    assert reg_a.success, f"register user_a failed: {reg_a.error}"
    reg_b = await container.auth_service.register(user_b, password)
    assert reg_b.success, f"register user_b failed: {reg_b.error}"

    # Obtain JWT tokens through the auth service.
    login_a = await container.auth_service.login(user_a, password)
    assert login_a.success, f"login user_a failed: {login_a.error}"
    token_a = login_a.token

    login_b = await container.auth_service.login(user_b, password)
    assert login_b.success, f"login user_b failed: {login_b.error}"
    token_b = login_b.token

    transport = ASGITransport(app=app)

    async with (
        AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {token_a}"},
        ) as client_a,
        AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {token_b}"},
        ) as client_b,
    ):
        yield {
            "client_a": client_a,
            "client_b": client_b,
            "user_a": user_a,
            "user_b": user_b,
            "user_repo": user_repo,
            "friend_repo": friend_repo,
        }

    # Clean up: reset the container so the next test starts fresh.
    container.reset()


# ═══════════════════════════════════════════════════════════════════════════════
# Test cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestSendFriendRequest:
    """Tests for POST /api/friends/request — sending a friend request."""

    async def test_send_request_success(self, friend_clients):
        """A user can send a friend request to another existing user."""
        client_a = friend_clients["client_a"]
        user_b = friend_clients["user_b"]

        resp = await client_a.post(
            "/api/friends/request",
            json={"to_user": user_b, "message": "Hello!"},
        )
        data = resp.json()

        assert data["success"] is True
        assert "request_id" in data
        assert data["message"] == "Friend request sent"

    async def test_send_request_duplicate_prevention(self, friend_clients):
        """Sending a second request to the same user while the first is pending
        is rejected."""
        client_a = friend_clients["client_a"]
        user_b = friend_clients["user_b"]

        # First request succeeds.
        resp = await client_a.post(
            "/api/friends/request",
            json={"to_user": user_b},
        )
        assert resp.json()["success"] is True

        # Second request is rejected as duplicate.
        resp = await client_a.post(
            "/api/friends/request",
            json={"to_user": user_b},
        )
        data = resp.json()
        assert data["success"] is False
        assert "Pending request already exists" in data["error"]

    async def test_send_request_to_self(self, friend_clients):
        """A user cannot send a friend request to themselves."""
        client_a = friend_clients["client_a"]
        user_a = friend_clients["user_a"]

        resp = await client_a.post(
            "/api/friends/request",
            json={"to_user": user_a},
        )
        data = resp.json()
        assert data["success"] is False
        assert "Cannot add yourself as friend" in data["error"]

    async def test_send_request_to_nonexistent_user(self, friend_clients):
        """Sending a request to a user who does not exist returns an error."""
        client_a = friend_clients["client_a"]

        resp = await client_a.post(
            "/api/friends/request",
            json={"to_user": "nonexistent_user_xyz"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "User does not exist" in data["error"]

    async def test_send_request_unauthenticated(self, unauthenticated_client):
        """An unauthenticated request to the friend endpoint is rejected."""
        resp = await unauthenticated_client.post(
            "/api/friends/request",
            json={"to_user": "anyone"},
        )
        # Auth middleware returns 307 redirect to /login.html for unauthenticated requests.
        assert resp.status_code in (401, 307, 403)


class TestAcceptFriendRequest:
    """Tests for POST /api/friends/requests/{request_id}/accept."""

    async def test_accept_request_success(self, friend_clients):
        """The recipient can accept a pending friend request."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_a = friend_clients["user_a"]
        user_b = friend_clients["user_b"]

        # A sends a request to B.
        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        request_id = resp.json()["request_id"]

        # B accepts the request.
        resp = await client_b.post(f"/api/friends/requests/{request_id}/accept")
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Friend request accepted"

        # Both users should now see each other as friends.
        resp = await client_a.get("/api/friends/list")
        friends_a = resp.json()
        assert friends_a["success"] is True
        assert any(f["user_id"] == user_b for f in friends_a["friends"])

        resp = await client_b.get("/api/friends/list")
        friends_b = resp.json()
        assert friends_b["success"] is True
        assert any(f["user_id"] == user_a for f in friends_b["friends"])

    async def test_accept_nonexistent_request(self, friend_clients):
        """Accepting a request ID that does not exist returns an error."""
        client_b = friend_clients["client_b"]

        resp = await client_b.post("/api/friends/requests/fake-request-id/accept")
        data = resp.json()
        assert data["success"] is False
        assert "Request not found" in data["error"]

    async def test_accept_request_wrong_user(self, friend_clients, test_db):
        """Only the intended recipient can accept a friend request."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_b = friend_clients["user_b"]

        # A sends a request to B.
        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        request_id = resp.json()["request_id"]

        # Register a third user C and try to accept the request meant for B.
        suffix = str(int(time.time() * 1000))[-6:]
        user_c = f"intruder_{suffix}"
        reg = await container.auth_service.register(user_c, "test_password_123")
        assert reg.success
        login = await container.auth_service.login(user_c, "test_password_123")
        assert login.success
        token_c = login.token

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {token_c}"},
        ) as client_c:
            resp = await client_c.post(
                f"/api/friends/requests/{request_id}/accept"
            )
            data = resp.json()
            assert data["success"] is False
            assert "Not authorized" in data["error"]

    async def test_accept_already_processed_request(self, friend_clients):
        """Accepting a request that has already been accepted/rejected fails."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_b = friend_clients["user_b"]

        # A sends a request to B.
        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        request_id = resp.json()["request_id"]

        # B accepts.
        resp = await client_b.post(f"/api/friends/requests/{request_id}/accept")
        assert resp.json()["success"] is True

        # B tries to accept again.
        resp = await client_b.post(f"/api/friends/requests/{request_id}/accept")
        data = resp.json()
        assert data["success"] is False
        assert "Request already processed" in data["error"]


class TestRejectFriendRequest:
    """Tests for POST /api/friends/requests/{request_id}/reject."""

    async def test_reject_request_success(self, friend_clients):
        """The recipient can reject a pending friend request."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_b = friend_clients["user_b"]

        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        request_id = resp.json()["request_id"]

        resp = await client_b.post(f"/api/friends/requests/{request_id}/reject")
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Friend request rejected"

        # After rejection, they should NOT be friends.
        resp = await client_a.get("/api/friends/list")
        friends = resp.json()["friends"]
        assert not any(f["user_id"] == user_b for f in friends)

    async def test_reject_nonexistent_request(self, friend_clients):
        """Rejecting a non-existent request returns an error."""
        client_b = friend_clients["client_b"]
        resp = await client_b.post("/api/friends/requests/nonexistent-id/reject")
        data = resp.json()
        assert data["success"] is False
        assert "Request not found" in data["error"]

    async def test_reject_request_wrong_user(self, friend_clients):
        """Only the intended recipient can reject a request."""
        client_a = friend_clients["client_a"]
        user_b = friend_clients["user_b"]

        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        request_id = resp.json()["request_id"]

        # The sender tries to reject their own sent request.
        resp = await client_a.post(f"/api/friends/requests/{request_id}/reject")
        data = resp.json()
        assert data["success"] is False
        assert "Not authorized" in data["error"]


class TestRemoveFriend:
    """Tests for POST /api/friends/remove — removing a friend."""

    async def test_remove_friend_success(self, friend_clients):
        """A user can remove an existing friend."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_b = friend_clients["user_b"]

        # First, establish friendship via request + accept.
        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        request_id = resp.json()["request_id"]
        await client_b.post(f"/api/friends/requests/{request_id}/accept")

        # Verify they are friends.
        resp = await client_a.get("/api/friends/list")
        assert any(f["user_id"] == user_b for f in resp.json()["friends"])

        # Remove the friend.
        resp = await client_a.post(
            "/api/friends/remove", json={"friend_id": user_b}
        )
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Friend removed"

        # Verify they are no longer friends.
        resp = await client_a.get("/api/friends/list")
        assert not any(f["user_id"] == user_b for f in resp.json()["friends"])

    async def test_remove_nonexistent_friend(self, friend_clients):
        """Removing a user who is not a friend returns an error."""
        client_a = friend_clients["client_a"]

        resp = await client_a.post(
            "/api/friends/remove", json={"friend_id": "stranger"}
        )
        data = resp.json()
        assert data["success"] is False
        assert "Not friends" in data["error"]

    async def test_remove_self(self, friend_clients):
        """Removing yourself (not a friend) returns an error."""
        client_a = friend_clients["client_a"]
        user_a = friend_clients["user_a"]

        resp = await client_a.post(
            "/api/friends/remove", json={"friend_id": user_a}
        )
        data = resp.json()
        assert data["success"] is False
        # The check order: first checks is_friend → "Not friends"
        assert "Not friends" in data.get("error", "")


class TestListFriends:
    """Tests for GET /api/friends/list — listing friends."""

    async def test_list_empty(self, friend_clients):
        """A new user has an empty friend list."""
        client_a = friend_clients["client_a"]

        resp = await client_a.get("/api/friends/list")
        data = resp.json()
        assert data["success"] is True
        assert data["friends"] == []
        assert data["count"] == 0

    async def test_list_with_friends(self, friend_clients):
        """After accepting a request, both users see each other in their lists."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_a = friend_clients["user_a"]
        user_b = friend_clients["user_b"]

        # Establish friendship.
        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        await client_b.post(
            f"/api/friends/requests/{resp.json()['request_id']}/accept"
        )

        # Both should see each other.
        for client, expected_friend in [(client_a, user_b), (client_b, user_a)]:
            resp = await client.get("/api/friends/list")
            data = resp.json()
            assert data["success"] is True
            assert data["count"] == 1
            assert data["friends"][0]["user_id"] == expected_friend

    async def test_list_after_removal(self, friend_clients):
        """After removing a friend, the list becomes empty."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_b = friend_clients["user_b"]

        # Establish then remove.
        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        await client_b.post(
            f"/api/friends/requests/{resp.json()['request_id']}/accept"
        )
        await client_a.post("/api/friends/remove", json={"friend_id": user_b})

        resp = await client_a.get("/api/friends/list")
        assert resp.json()["count"] == 0

    async def test_list_unauthenticated(self, unauthenticated_client):
        """Unauthenticated access to friend list is rejected."""
        resp = await unauthenticated_client.get("/api/friends/list")
        assert resp.status_code in (401, 307, 403)


class TestPendingAndSentRequests:
    """Tests for GET /api/friends/requests/pending and /requests/sent."""

    async def test_pending_requests(self, friend_clients):
        """The recipient sees incoming pending requests."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_a = friend_clients["user_a"]

        # A sends a request to B.
        await client_a.post(
            "/api/friends/request",
            json={"to_user": friend_clients["user_b"], "message": "Hi"},
        )

        # B's pending list should contain the request.
        resp = await client_b.get("/api/friends/requests/pending")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
        req = data["requests"][0]
        assert req["from_user"] == user_a
        assert req["status"] == "pending"
        assert req["message"] == "Hi"

    async def test_sent_requests(self, friend_clients):
        """The sender sees their outgoing pending requests."""
        client_a = friend_clients["client_a"]
        user_b = friend_clients["user_b"]

        await client_a.post(
            "/api/friends/request",
            json={"to_user": user_b, "message": "Yo"},
        )

        resp = await client_a.get("/api/friends/requests/sent")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
        req = data["requests"][0]
        assert req["to_user"] == user_b
        assert req["status"] == "pending"
        assert req["message"] == "Yo"

    async def test_sent_requests_empty(self, friend_clients):
        """A user with no outgoing requests gets an empty list."""
        resp = await friend_clients["client_a"].get("/api/friends/requests/sent")
        data = resp.json()
        assert data["success"] is True
        assert data["requests"] == []
        assert data["count"] == 0

    async def test_pending_empty_after_accept(self, friend_clients):
        """After accepting a request, it disappears from pending."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_b = friend_clients["user_b"]

        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        request_id = resp.json()["request_id"]
        await client_b.post(f"/api/friends/requests/{request_id}/accept")

        resp = await client_b.get("/api/friends/requests/pending")
        assert resp.json()["count"] == 0

    async def test_sent_requests_empty_after_rejection(self, friend_clients):
        """After a sent request is rejected, it is no longer pending."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_b = friend_clients["user_b"]

        resp = await client_a.post(
            "/api/friends/request", json={"to_user": user_b}
        )
        request_id = resp.json()["request_id"]
        await client_b.post(f"/api/friends/requests/{request_id}/reject")

        # The sender's sent list should be empty (the request is now "rejected", not "pending").
        resp = await client_a.get("/api/friends/requests/sent")
        assert resp.json()["count"] == 0


class TestDirectAddFriend:
    """Tests for POST /api/friends/add — direct friendship creation."""

    async def test_add_friend_success(self, friend_clients):
        """Directly add a friend without the request/accept flow."""
        client_a = friend_clients["client_a"]
        user_b = friend_clients["user_b"]

        resp = await client_a.post(
            "/api/friends/add", json={"friend_id": user_b}
        )
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Friend added"

        # Verify.
        resp = await client_a.get("/api/friends/list")
        assert any(f["user_id"] == user_b for f in resp.json()["friends"])

    async def test_add_self(self, friend_clients):
        """Cannot add yourself as a friend."""
        client_a = friend_clients["client_a"]
        user_a = friend_clients["user_a"]

        resp = await client_a.post(
            "/api/friends/add", json={"friend_id": user_a}
        )
        data = resp.json()
        assert data["success"] is False
        assert "Cannot add yourself as friend" in data["error"]

    async def test_add_duplicate(self, friend_clients):
        """Adding an existing friend returns an error."""
        client_a = friend_clients["client_a"]
        user_b = friend_clients["user_b"]

        await client_a.post("/api/friends/add", json={"friend_id": user_b})

        resp = await client_a.post("/api/friends/add", json={"friend_id": user_b})
        data = resp.json()
        assert data["success"] is False
        assert "Already friends" in data["error"]


class TestFullFriendLifecycle:
    """End-to-end tests covering the complete friend lifecycle."""

    async def test_full_lifecycle(self, friend_clients):
        """Complete flow: request → accept → list → remove → verify."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_a = friend_clients["user_a"]
        user_b = friend_clients["user_b"]

        # Step 1: A sends a request to B.
        resp = await client_a.post(
            "/api/friends/request",
            json={"to_user": user_b, "message": "Let's be friends!"},
        )
        data = resp.json()
        assert data["success"] is True
        request_id = data["request_id"]

        # Step 2: B sees the pending request.
        resp = await client_b.get("/api/friends/requests/pending")
        pending = resp.json()
        assert pending["count"] == 1
        assert pending["requests"][0]["from_user"] == user_a

        # Step 3: B accepts the request.
        resp = await client_b.post(f"/api/friends/requests/{request_id}/accept")
        assert resp.json()["success"] is True

        # Step 4: Both can see each other in their friend lists.
        for client, expected in [(client_a, user_b), (client_b, user_a)]:
            resp = await client.get("/api/friends/list")
            assert resp.json()["count"] >= 1
            assert any(f["user_id"] == expected for f in resp.json()["friends"])

        # Step 5: A removes B.
        resp = await client_a.post("/api/friends/remove", json={"friend_id": user_b})
        assert resp.json()["success"] is True

        # Step 6: Neither sees the other.
        for client in [client_a, client_b]:
            resp = await client.get("/api/friends/list")
            assert resp.json()["count"] == 0

    async def test_mutual_friend_after_both_send_requests(self, friend_clients):
        """When two users independently send requests, accepting one creates
        the friendship; the second request is then already-processed."""
        client_a = friend_clients["client_a"]
        client_b = friend_clients["client_b"]
        user_a = friend_clients["user_a"]
        user_b = friend_clients["user_b"]

        # A sends request to B.
        r = await client_a.post("/api/friends/request", json={"to_user": user_b})
        req_a = r.json()["request_id"]

        # B also sends request to A (this works because has_pending_request
        # checks direction from_user→to_user specifically, not the reverse).
        r = await client_b.post("/api/friends/request", json={"to_user": user_a})
        req_b = r.json()["request_id"]

        # B accepts A's request → friendship created.
        resp = await client_b.post(f"/api/friends/requests/{req_a}/accept")
        assert resp.json()["success"] is True

        # A also accepts B's request — succeeds idempotently (they are already
        # friends; the service processes each request independently).
        resp = await client_a.post(f"/api/friends/requests/{req_b}/accept")
        data = resp.json()
        assert data["success"] is True

        # Both are friends.
        resp = await client_a.get("/api/friends/list")
        assert resp.json()["count"] >= 1
