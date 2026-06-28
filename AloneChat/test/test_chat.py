"""
Tests for the chat module: send, receive (queue polling), history,
session listing, and queue overflow behaviour.

Covers the /api/chat endpoints:
    POST   /api/chat/send
    GET    /api/chat/history
    POST   /api/chat/recv
    POST   /api/chat/recv/clear
    GET    /api/chat/sessions

Uses the shared ``test_db`` fixture from ``conftest.py``.  ClickHouse
is disabled for all tests so services fall back to in-memory storage.

Users are registered directly through the DI container (bypassing the
HTTP auth layer) so that the tests are not coupled to the auth
middleware's behaviour.
"""

import asyncio
import time as _time

import jwt
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from AloneChat.api.app import app
from AloneChat.config import config
from AloneChat.di import container


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(username: str) -> str:
    """Create a valid JWT for *username* using the app's secret."""
    payload = {
        "sub": username,
        "exp": int(_time.time()) + 3600,
        "iat": int(_time.time()),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def _make_client(token: str) -> AsyncClient:
    """Return an ASGI :class:`AsyncClient` with the given Bearer token."""
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def two_users(test_db):
    """Create two test users and return ``(client_a, client_b, user_a, user_b)``.

    Each client is pre-authenticated with a valid JWT token.  Users are
    registered and logged in directly through the DI container so there is
    no dependency on the HTTP auth endpoints.
    """
    suffix_a = str(int(_time.time() * 1000))[-6:]
    suffix_b = str(int(_time.time() * 1000) + 1)[-6:]
    user_a = f"alice_{suffix_a}"
    user_b = f"bob_{suffix_b}"
    pw = "test_password_123"

    await container.auth_service.register(user_a, pw)
    await container.auth_service.register(user_b, pw)
    await container.auth_service.login(user_a, pw)
    await container.auth_service.login(user_b, pw)

    token_a = _make_token(user_a)
    token_b = _make_token(user_b)

    client_a = _make_client(token_a)
    client_b = _make_client(token_b)

    yield client_a, client_b, user_a, user_b

    await client_a.aclose()
    await client_b.aclose()


# ---------------------------------------------------------------------------
# POST /api/chat/send
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Tests for ``POST /api/chat/send``."""

    async def test_send_message_success(self, two_users):
        """Sending a message to another registered user returns success."""
        client_a, _client_b, _user_a, user_b = two_users

        resp = await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "Hello from test!"},
        )
        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["message"] == "Message sent"

    async def test_send_message_to_self(self, two_users):
        """Sending a message to yourself returns 400."""
        client_a, _client_b, user_a, _user_b = two_users

        resp = await client_a.post(
            "/api/chat/send",
            json={"recipient": user_a, "content": "Should fail"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "Cannot message yourself" in data["detail"]

    async def test_send_message_empty_content(self, two_users):
        """Empty or whitespace-only content is rejected."""
        client_a, _client_b, _user_a, user_b = two_users

        resp = await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "   "},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    async def test_send_message_missing_fields(self, two_users):
        """Missing required fields triggers a 422 validation error."""
        client_a, _client_b, _user_a, _user_b = two_users

        resp = await client_a.post(
            "/api/chat/send",
            json={"content": "No recipient field"},
        )
        assert resp.status_code == 422

    async def test_send_to_nonexistent_user(self, two_users):
        """Sending to a user that does not exist still reports success
        (recipient existence is not validated at send time)."""
        client_a, _client_b, _user_a, _user_b = two_users

        resp = await client_a.post(
            "/api/chat/send",
            json={
                "recipient": "no_such_user_42",
                "content": "Hello ghost!",
            },
        )
        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is True

    async def test_send_multiple_to_same_recipient(self, two_users):
        """Sending several messages in succession all succeed."""
        client_a, _client_b, _user_a, user_b = two_users

        for i in range(5):
            resp = await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": f"Msg {i}"},
            )
            assert resp.status_code == 200
            assert resp.json()["success"] is True


# ---------------------------------------------------------------------------
# POST /api/chat/recv  (queue polling for pending messages)
# ---------------------------------------------------------------------------


class TestRecvMessages:
    """Tests for ``POST /api/chat/recv``."""

    async def test_recv_receives_sent_message(self, two_users):
        """After user A sends a message to user B, user B can poll and
        receive it via /recv."""
        client_a, client_b, user_a, user_b = two_users

        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "Hey Bob!"},
        )

        resp = await client_b.post("/api/chat/recv")
        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["count"] >= 1

        messages = data["messages"]
        senders = [m["sender"] for m in messages]
        assert user_a in senders
        contents = [m["content"] for m in messages]
        assert "Hey Bob!" in contents

    async def test_recv_drains_queue(self, two_users):
        """Repeated /recv calls drain the queue -- messages are not
        re-delivered."""
        client_a, client_b, user_a, user_b = two_users

        for i in range(3):
            await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": f"Msg {i}"},
            )

        # First poll -- should have messages.
        resp1 = await client_b.post("/api/chat/recv")
        assert resp1.json()["count"] > 0

        # Second poll -- queue should be empty.
        resp2 = await client_b.post("/api/chat/recv")
        assert resp2.json()["count"] == 0

    async def test_recv_no_pending_when_empty(self, two_users):
        """Polling when no messages are waiting returns an empty list."""
        _client_a, client_b, _user_a, _user_b = two_users

        resp = await client_b.post("/api/chat/recv")
        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["count"] == 0
        assert data["messages"] == []

    async def test_recv_message_includes_type(self, two_users):
        """Received messages carry the correct type field."""
        client_a, client_b, user_a, user_b = two_users

        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "Typed!"},
        )
        resp = await client_b.post("/api/chat/recv")
        msgs = resp.json()["messages"]
        assert len(msgs) > 0
        for m in msgs:
            assert "sender" in m
            assert "content" in m
            assert "type" in m

    async def test_recv_clear_discards_all(self, two_users):
        """``/recv/clear`` discards all pending messages."""
        client_a, client_b, user_a, user_b = two_users

        for i in range(5):
            await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": f"Spam {i}"},
            )

        # Clear before polling.
        resp = await client_b.post("/api/chat/recv/clear")
        assert resp.json()["success"] is True
        assert resp.json()["cleared_count"] >= 1

        # Now poll -- should be empty.
        resp2 = await client_b.post("/api/chat/recv")
        assert resp2.json()["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------


class TestChatHistory:
    """Tests for ``GET /api/chat/history``."""

    async def test_history_returns_sent_messages(self, two_users):
        """After sending several messages, both users can retrieve them
        via the history endpoint."""
        client_a, client_b, user_a, user_b = two_users

        messages = ["First", "Second", "Third"]
        for m in messages:
            await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": m},
            )

        # User A's perspective.
        resp_a = await client_a.get(
            "/api/chat/history", params={"other_user": user_b}
        )
        data_a = resp_a.json()
        assert data_a["success"] is True
        assert data_a["count"] == len(messages)
        contents_a = [m["content"] for m in data_a["messages"]]
        for msg in messages:
            assert msg in contents_a

        # User B's perspective.
        resp_b = await client_b.get(
            "/api/chat/history", params={"other_user": user_a}
        )
        data_b = resp_b.json()
        assert data_b["success"] is True
        assert data_b["count"] == len(messages)

    async def test_history_empty_for_new_users(self, two_users):
        """Two users who have never exchanged messages see an empty history."""
        client_a, _client_b, _user_a, user_b = two_users

        resp = await client_a.get(
            "/api/chat/history", params={"other_user": user_b}
        )
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["messages"] == []

    async def test_history_respects_limit(self, two_users):
        """The *limit* query parameter caps the number of returned messages."""
        client_a, _client_b, _user_a, user_b = two_users

        for i in range(20):
            await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": f"msg-{i:02d}"},
            )

        resp = await client_a.get(
            "/api/chat/history",
            params={"other_user": user_b, "limit": 5},
        )
        data = resp.json()
        assert data["count"] <= 5
        assert data["count"] > 0

    async def test_history_limit_bounds(self, two_users):
        """Out-of-range limit values are rejected with 422."""
        client_a, _client_b, _user_a, _user_b = two_users

        resp = await client_a.get(
            "/api/chat/history",
            params={"other_user": "someone", "limit": 0},
        )
        assert resp.status_code == 422

        resp2 = await client_a.get(
            "/api/chat/history",
            params={"other_user": "someone", "limit": 999},
        )
        assert resp2.status_code == 422

    async def test_history_chronological_order(self, two_users):
        """Messages appear in chronological order (oldest first)."""
        client_a, _client_b, _user_a, user_b = two_users

        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "oldest"},
        )
        await asyncio.sleep(0.02)
        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "middle"},
        )
        await asyncio.sleep(0.02)
        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "newest"},
        )

        resp = await client_a.get(
            "/api/chat/history", params={"other_user": user_b}
        )
        msgs = resp.json()["messages"]
        contents = [m["content"] for m in msgs]
        assert contents == ["oldest", "middle", "newest"]


# ---------------------------------------------------------------------------
# GET /api/chat/sessions
# ---------------------------------------------------------------------------


class TestChatSessions:
    """Tests for ``GET /api/chat/sessions``."""

    async def test_sessions_lists_active_chats(self, two_users):
        """After chatting with user B, user A sees a session entry."""
        client_a, _client_b, _user_a, user_b = two_users

        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "Hello session!"},
        )

        resp = await client_a.get("/api/chat/sessions")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 1

        partners = [s["partner"] for s in data["sessions"]]
        assert user_b in partners

    async def test_sessions_empty_for_new_user(self, two_users):
        """A user who has never sent a message sees no sessions."""
        client_a, _client_b, _user_a, _user_b = two_users

        resp = await client_a.get("/api/chat/sessions")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["sessions"] == []

    async def test_sessions_includes_message_count(self, two_users):
        """Each session entry includes the total message count."""
        client_a, _client_b, _user_a, user_b = two_users

        for i in range(5):
            await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": f"Chat {i}"},
            )

        resp = await client_a.get("/api/chat/sessions")
        sessions = resp.json()["sessions"]
        for s in sessions:
            if s["partner"] == user_b:
                assert s["message_count"] >= 5
                break
        else:
            pytest.fail(f"Session with partner {user_b} not found")

    async def test_sessions_respects_limit(self, two_users):
        """The *limit* query parameter caps the number of returned sessions."""
        client_a, _client_b, _user_a, _user_b = two_users

        resp = await client_a.get(
            "/api/chat/sessions", params={"limit": 1}
        )
        data = resp.json()
        assert data["count"] <= 1

    async def test_sessions_has_expected_keys(self, two_users):
        """Each session dict contains the expected fields."""
        client_a, _client_b, _user_a, user_b = two_users

        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "Session keys test"},
        )

        resp = await client_a.get("/api/chat/sessions")
        sessions = resp.json()["sessions"]
        assert len(sessions) > 0
        for s in sessions:
            assert "session_id" in s
            assert "partner" in s
            assert "last_activity" in s
            assert "message_count" in s


# ---------------------------------------------------------------------------
# Queue overflow behaviour
# ---------------------------------------------------------------------------


class TestQueueOverflow:
    """Tests for message queue overflow behaviour."""

    async def test_many_messages_queued_and_received(self, two_users):
        """Sending a moderate number of messages queues them all and the
        recipient can drain them."""
        client_a, client_b, user_a, user_b = two_users

        count = 50
        for i in range(count):
            await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": f"Queue msg {i}"},
            )

        total_received = 0
        for _ in range(5):
            resp = await client_b.post("/api/chat/recv")
            batch = resp.json()
            total_received += batch["count"]
            if batch["count"] == 0:
                break

        assert total_received == count

    async def test_queue_overflow_drops_oldest(self, two_users):
        """When the queue exceeds its max size, oldest messages are dropped
        to make room for new ones."""
        client_a, client_b, user_a, user_b = two_users

        # Default MessageQueue max_size is 500.
        overflow_count = 600
        for i in range(overflow_count):
            await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": f"Overflow {i}"},
            )

        total_received = 0
        for _ in range(10):
            resp = await client_b.post("/api/chat/recv")
            batch = resp.json()
            total_received += batch["count"]
            if batch["count"] == 0:
                break

        # Should have received <= max_size messages (some were dropped).
        assert total_received <= 500
        assert total_received > 0

    async def test_clear_after_overflow(self, two_users):
        """After overflow, /recv/clear successfully discards remaining
        messages."""
        client_a, client_b, user_a, user_b = two_users

        for i in range(100):
            await client_a.post(
                "/api/chat/send",
                json={"recipient": user_b, "content": f"Clear {i}"},
            )

        clear_resp = await client_b.post("/api/chat/recv/clear")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["cleared_count"] > 0

        resp = await client_b.post("/api/chat/recv")
        assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# POST /api/chat/recv/clear  (edge cases)
# ---------------------------------------------------------------------------


class TestRecvClearEdgeCases:
    """Edge-case tests for ``POST /api/chat/recv/clear``."""

    async def test_clear_when_empty(self, two_users):
        """Clearing when no messages exist returns zero."""
        client_a, _client_b, _user_a, _user_b = two_users

        resp = await client_a.post("/api/chat/recv/clear")
        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["cleared_count"] == 0

    async def test_clear_then_send_then_recv(self, two_users):
        """Messages sent AFTER a clear are still receivable."""
        client_a, client_b, user_a, user_b = two_users

        # Send a message, clear it, send another -- only the second arrives.
        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "Will be cleared"},
        )
        await client_b.post("/api/chat/recv/clear")

        await client_a.post(
            "/api/chat/send",
            json={"recipient": user_b, "content": "After clear"},
        )

        resp = await client_b.post("/api/chat/recv")
        msgs = resp.json()["messages"]
        assert len(msgs) == 1
        assert msgs[0]["content"] == "After clear"
