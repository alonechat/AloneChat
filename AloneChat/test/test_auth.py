"""
Tests for the authentication flow.

Covers:
- Registration with valid / invalid / duplicate data
- Login with valid / invalid credentials
- Token validation and expiry
- Protected-endpoint access
- Full round-trip: register -> login -> access protected route
"""

import time

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from AloneChat.api.app import app
from AloneChat.config import config
from AloneChat.server.repositories.base import reset_memory_store


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _unique_username() -> str:
    """Return a unique username for a test user so tests don't collide.

    The auth service enforces 3–20 characters, so the combined prefix +
    suffix must stay within that range.
    """
    # 6 hex digits (16 777 216 combinations) from the current microsecond
    # timestamp, plus a short prefix, keeps us inside the 20-char limit.
    suffix = hex(int(time.time() * 1_000_000))[2:]  # strip "0x"
    return f"au_{suffix}"[:20]


async def _make_client(auth_token: str = None) -> AsyncClient:
    """Create an ASGI-backed ``AsyncClient``, optionally pre-authenticated."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", headers=headers)


# ──────────────────────────────────────────────────────────────────────
# Fixtures (function-scoped, in-memory DB is reset each test)
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_memory_store():
    """Ensure every test starts with a clean in-memory database."""
    reset_memory_store()
    yield
    reset_memory_store()


@pytest.fixture
def unauth_client():
    """Return an httpx.AsyncClient with no Authorization header."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ──────────────────────────────────────────────────────────────────────
# Registration tests
# ──────────────────────────────────────────────────────────────────────


class TestRegistration:
    """Tests for ``POST /api/auth/register``."""

    @pytest.mark.asyncio
    async def test_register_valid(self, unauth_client: AsyncClient):
        """Registering a new user succeeds and returns success=True."""
        username = _unique_username()
        resp = await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": "secure123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "successful" in data.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_register_duplicate(self, unauth_client: AsyncClient):
        """Registering the same username twice returns success=False."""
        username = _unique_username()
        # First registration — succeeds
        resp1 = await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": "secure123"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["success"] is True

        # Second registration — fails
        resp2 = await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": "different456"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["success"] is False
        assert "already exists" in resp2.json().get("message", "").lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "username, password, expected_error_fragment",
        [
            # Username too short
            ("ab", "secure123", "3-20"),
            # Username too long
            ("a" * 21, "secure123", "3-20"),
            # Empty username
            ("", "secure123", "3-20"),
            # Password too short
            ("validuser", "12345", "6"),
            # Empty password
            ("validuser", "", "6"),
            # Both invalid
            ("x", "x", "3-20"),  # username error takes precedence
        ],
    )
    async def test_register_invalid(
        self,
        unauth_client: AsyncClient,
        username: str,
        password: str,
        expected_error_fragment: str,
    ):
        """Invalid registration data returns success=False with an error message."""
        resp = await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert expected_error_fragment in data.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, unauth_client: AsyncClient):
        """Missing fields result in a validation error (422)."""
        resp = await unauth_client.post(
            "/api/auth/register",
            json={"username": "someone"},
        )
        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Login tests
# ──────────────────────────────────────────────────────────────────────


class TestLogin:
    """Tests for ``POST /api/auth/login``."""

    @pytest.mark.asyncio
    async def test_login_valid(self, unauth_client: AsyncClient):
        """Login with valid credentials returns a JWT token."""
        username = _unique_username()
        password = "secure123"
        # Register first
        await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        # Login
        resp = await unauth_client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        token = data.get("token")
        assert token is not None
        # Verify the token can be decoded
        payload = jwt.decode(
            token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
        assert payload["sub"] == username

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, unauth_client: AsyncClient):
        """Login with a wrong password returns success=False."""
        username = _unique_username()
        await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": "correct123"},
        )
        resp = await unauth_client.post(
            "/api/auth/login",
            json={"username": username, "password": "wrong_password"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "invalid credentials" in data.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, unauth_client: AsyncClient):
        """Login with a non-existent username returns success=False."""
        resp = await unauth_client.post(
            "/api/auth/login",
            json={"username": "no_such_user_xyz", "password": "whatever"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_login_empty_credentials(self, unauth_client: AsyncClient):
        """Login with empty username/password returns success=False."""
        resp = await unauth_client.post(
            "/api/auth/login",
            json={"username": "", "password": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, unauth_client: AsyncClient):
        """Missing login fields result in a validation error (422)."""
        resp = await unauth_client.post(
            "/api/auth/login",
            json={"username": "someone"},
        )
        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Token validation and expiry tests
# ──────────────────────────────────────────────────────────────────────


class TestTokenValidation:
    """Tests for JWT token validation logic."""

    @pytest.mark.asyncio
    async def test_valid_token_accesses_protected_route(
        self, unauth_client: AsyncClient
    ):
        """A valid JWT token allows access to a protected endpoint."""
        username = _unique_username()
        password = "secure123"

        await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        login_resp = await unauth_client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        token = login_resp.json()["token"]

        # Access a protected route (logout requires auth)
        auth_client = await _make_client(auth_token=token)
        try:
            resp = await auth_client.post("/api/auth/logout")
            assert resp.status_code == 200
            assert resp.json()["success"] is True
        finally:
            await auth_client.aclose()

    @pytest.mark.asyncio
    async def test_invalid_token_is_rejected(self):
        """A malformed or invalid JWT token gets a 307 redirect."""
        auth_client = await _make_client(auth_token="not.a.real.token")
        try:
            resp = await auth_client.post("/api/auth/logout")
            # The AuthMiddleware redirects to /login.html with 307
            assert resp.status_code in (307, 401)
        finally:
            await auth_client.aclose()

    @pytest.mark.asyncio
    async def test_expired_token_is_rejected(self):
        """An expired JWT token is rejected."""
        # Create a token that has already expired
        expired_payload = {
            "sub": "testuser",
            "exp": int(time.time()) - 3600,  # 1 hour in the past
            "iat": int(time.time()) - 7200,
        }
        expired_token = jwt.encode(
            expired_payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM
        )

        auth_client = await _make_client(auth_token=expired_token)
        try:
            resp = await auth_client.post("/api/auth/logout")
            assert resp.status_code in (307, 401)
        finally:
            await auth_client.aclose()

    @pytest.mark.asyncio
    async def test_missing_token_is_redirected(self):
        """A request with no Authorization header gets redirected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post("/api/auth/logout")
            # AuthMiddleware redirects unauthenticated requests
            assert resp.status_code in (307, 401)

    @pytest.mark.asyncio
    async def test_register_then_login_then_logout(self, unauth_client: AsyncClient):
        """Full round-trip: register -> login -> logout."""
        username = _unique_username()
        password = "full_flow_123"

        # 1. Register
        reg_resp = await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        assert reg_resp.json()["success"] is True, reg_resp.json()

        # 2. Login
        login_resp = await unauth_client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert login_resp.json()["success"] is True
        token = login_resp.json()["token"]
        assert token is not None

        # 3. Logout (with auth)
        auth_client = await _make_client(auth_token=token)
        try:
            logout_resp = await auth_client.post("/api/auth/logout")
            assert logout_resp.status_code == 200
            assert logout_resp.json()["success"] is True
        finally:
            await auth_client.aclose()


# ──────────────────────────────────────────────────────────────────────
# Edge-case tests
# ──────────────────────────────────────────────────────────────────────


class TestAuthEdgeCases:
    """Auth edge-case and boundary tests."""

    @pytest.mark.asyncio
    async def test_register_special_characters(self, unauth_client: AsyncClient):
        """Usernames with special characters are accepted."""
        username = f"sp_{_unique_username()}"[:20]
        resp = await unauth_client.post(
            "/api/auth/register",
            json={"username": username, "password": "secure123"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_multiple_users_independent(self, unauth_client: AsyncClient):
        """Registering multiple users works, each with their own credentials."""
        user_a = _unique_username()
        user_b = _unique_username()

        # Register both
        resp_a = await unauth_client.post(
            "/api/auth/register",
            json={"username": user_a, "password": "passA123"},
        )
        resp_b = await unauth_client.post(
            "/api/auth/register",
            json={"username": user_b, "password": "passB456"},
        )
        assert resp_a.json()["success"] is True
        assert resp_b.json()["success"] is True

        # Login as user_a
        login_a = await unauth_client.post(
            "/api/auth/login",
            json={"username": user_a, "password": "passA123"},
        )
        assert login_a.json()["success"] is True
        token_a = login_a.json()["token"]

        # Login as user_b
        login_b = await unauth_client.post(
            "/api/auth/login",
            json={"username": user_b, "password": "passB456"},
        )
        assert login_b.json()["success"] is True
        token_b = login_b.json()["token"]

        # Tokens should differ
        assert token_a != token_b

        # Each token decodes to the correct user
        payload_a = jwt.decode(
            token_a, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
        payload_b = jwt.decode(
            token_b, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
        assert payload_a["sub"] == user_a
        assert payload_b["sub"] == user_b
