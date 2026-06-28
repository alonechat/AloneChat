"""
Tests for the AloneChat crypto module — password hashing and verification.

Covers:
- Hash / verify round-trip correctness
- Wrong-password rejection
- Rehash detection for fresh and stale parameters
- Invalid / edge-case input handling
- Integration smoke tests: register → login flows that exercise crypto
  through the real FastAPI app with in-memory storage.

All async tests use function-scoped event loops (pytest-asyncio auto mode
configured in conftest.py).
"""

import time

import pytest

from AloneChat.crypto.password_hash import (
    hash_password,
    verify_password,
    needs_rehash,
    get_backend_info,
)
from AloneChat.di import container

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

SAFE_PASSWORD = "Correct-Horse.Battery-Staple*2026"
SHORT_PASSWORD = "abc123"
LONG_PASSWORD = "x" * 512
UNICODE_PASSWORD = "パスワード🔐测试密码🎭"


def _unique_username() -> str:
    """Return a username unique to this millisecond for isolation."""
    return f"cu{int(time.time() * 1000) % 1000000}"


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests — synchronous crypto primitives
# ═══════════════════════════════════════════════════════════════════════════════


class TestHashPassword:
    """Tests for :func:`hash_password`."""

    def test_returns_string(self):
        """Hashing a plain password returns a non-empty string."""
        result = hash_password(SAFE_PASSWORD)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_does_not_contain_plaintext(self):
        """The output hash must not leak the original password."""
        result = hash_password(SAFE_PASSWORD)
        assert SAFE_PASSWORD not in result

    def test_different_salts_produce_different_hashes(self):
        """Two calls with the same password yield different output (random salt)."""
        h1 = hash_password(SAFE_PASSWORD)
        h2 = hash_password(SAFE_PASSWORD)
        assert h1 != h2

    def test_empty_password(self):
        """Hash accepts an empty string as password."""
        result = hash_password("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_very_long_password(self):
        """Hash handles very long passwords gracefully."""
        result = hash_password(LONG_PASSWORD)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unicode_characters(self):
        """Hash handles non-ASCII / multi-byte characters."""
        result = hash_password(UNICODE_PASSWORD)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_special_characters(self):
        """Hash handles SQL / newline / control characters."""
        result = hash_password("DROP TABLE users; --\n\x00\x1b\t")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_whitespace_only_password(self):
        """Hash handles a password consisting solely of whitespace."""
        result = hash_password("     ")
        assert isinstance(result, str)
        assert len(result) > 0


class TestVerifyPassword:
    """Tests for :func:`verify_password`."""

    # -- Happy path ------------------------------------------------------------

    def test_round_trip_correct_password(self):
        """hash → verify with the SAME password returns True."""
        hashed = hash_password(SAFE_PASSWORD)
        assert verify_password(SAFE_PASSWORD, hashed) is True

    def test_round_trip_unicode_password(self):
        """hash → verify with unicode password returns True."""
        hashed = hash_password(UNICODE_PASSWORD)
        assert verify_password(UNICODE_PASSWORD, hashed) is True

    def test_round_trip_empty_password(self):
        """hash → verify with empty string returns True."""
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    # -- Wrong password --------------------------------------------------------

    def test_wrong_password_returns_false(self):
        """A wrong password must NOT verify."""
        hashed = hash_password(SAFE_PASSWORD)
        assert verify_password("wrong_password", hashed) is False

    def test_case_mismatch(self):
        """Passwords are case-sensitive; different case fails."""
        hashed = hash_password("CaseSensitive")
        assert verify_password("casesensitive", hashed) is False
        assert verify_password("CASESENSITIVE", hashed) is False

    def test_extra_whitespace(self):
        """Trailing / leading whitespace makes the password different."""
        hashed = hash_password(SAFE_PASSWORD)
        assert verify_password(SAFE_PASSWORD + " ", hashed) is False
        assert verify_password(" " + SAFE_PASSWORD, hashed) is False

    def test_similar_but_different(self):
        """A password that differs by one character must fail."""
        hashed = hash_password("hello_world_1")
        assert verify_password("hello_world_2", hashed) is False

    # -- Invalid / edge-case inputs --------------------------------------------

    def test_empty_hash_returns_false(self):
        """An empty hash string returns False (not an exception)."""
        assert verify_password(SAFE_PASSWORD, "") is False

    def test_garbage_hash_returns_false(self):
        """A completely invalid hash returns False."""
        assert verify_password(SAFE_PASSWORD, "not_a_valid_hash!") is False

    def test_none_like_hash_string(self):
        """The literal string 'None' is not a valid hash."""
        assert verify_password(SAFE_PASSWORD, "None") is False

    def test_none_password(self):
        """Passing None as password is caught by the broad exception handler."""
        hashed = hash_password(SAFE_PASSWORD)
        # The argon2 library raises an internal error on None, which is
        # caught by the broad ``except Exception`` in verify_password.
        assert verify_password(None, hashed) is False  # type: ignore[arg-type]

    def test_none_hash(self):
        """Passing None as the stored hash is caught by broad exception handler."""
        # Argon2 raises an internal error on a None hash, caught by
        # verify_password's broad ``except Exception``.
        assert verify_password(SAFE_PASSWORD, None) is False  # type: ignore[arg-type]

    # -- Repeated verification ------------------------------------------------

    def test_repeated_verification_same_instance(self):
        """The same hash can be verified multiple times."""
        hashed = hash_password(SAFE_PASSWORD)
        for _ in range(10):
            assert verify_password(SAFE_PASSWORD, hashed) is True

    def test_repeated_rejection_stable(self):
        """Wrong password is consistently rejected across calls."""
        hashed = hash_password(SAFE_PASSWORD)
        for _ in range(10):
            assert verify_password("wrong", hashed) is False


class TestNeedsRehash:
    """Tests for :func:`needs_rehash`."""

    def test_fresh_hash_no_rehash_needed(self):
        """A hash just created with current parameters should not need rehash."""
        hashed = hash_password(SAFE_PASSWORD)
        assert needs_rehash(hashed) is False

    def test_empty_hash_no_rehash(self):
        """An empty string does not trigger a rehash (returns False)."""
        assert needs_rehash("") is False

    def test_garbage_hash_no_rehash(self):
        """A garbage string does not trigger a rehash."""
        assert needs_rehash("not_a_hash") is False

    def test_none_hash_returns_false(self):
        """None hash value is caught by the broad exception handler."""
        # Argon2 raises an internal error on None, caught by
        # needs_rehash's broad ``except Exception``.
        assert needs_rehash(None) is False  # type: ignore[arg-type]

    def test_multiple_fresh_hashes(self):
        """Multiple fresh hashes all report no rehash needed."""
        for pw in (SAFE_PASSWORD, SHORT_PASSWORD, UNICODE_PASSWORD, ""):
            h = hash_password(pw)
            assert needs_rehash(h) is False, f"Unexpected rehash for pw={pw!r}"


class TestGetBackendInfo:
    """Tests for :func:`get_backend_info`."""

    def test_returns_dict(self):
        """Must return a dictionary."""
        info = get_backend_info()
        assert isinstance(info, dict)

    def test_required_keys_present(self):
        """Check that expected keys exist and have correct types."""
        info = get_backend_info()
        assert info["algorithm"] == "argon2id"
        assert isinstance(info["available"], bool)
        assert info["available"] is True
        assert isinstance(info["time_cost"], int)
        assert isinstance(info["memory_cost"], int)
        assert isinstance(info["parallelism"], int)
        assert info["time_cost"] > 0
        assert info["memory_cost"] > 0
        assert info["parallelism"] > 0

    def test_backend_is_reported_available(self):
        """When argon2-cffi is installed, 'available' should be True."""
        info = get_backend_info()
        assert info["available"] is True, (
            "Argon2 backend should be available in this test environment"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — direct auth service calls that exercise crypto
# ═══════════════════════════════════════════════════════════════════════════════
#
# These tests call ``container.auth_service`` directly, bypassing the HTTP
# layer.  The ``test_db`` fixture disables ClickHouse and sets up the
# in-memory fallback so that ``register`` / ``login`` exercise the real
# ``hash_password`` / ``verify_password`` integration end-to-end.
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuthFlowExercisesCrypto:
    """Integration tests that verify crypto through the real AuthService."""

    async def test_register_hashes_and_stores_password(self, test_db):
        """Registration creates a user; stored password is not plaintext."""
        username = _unique_username()
        password = SAFE_PASSWORD

        result = await container.auth_service.register(username, password)
        assert result.success is True, f"Register failed: {result.error}"

        # Verify the stored hash is NOT the plaintext password
        user = container.user_repo.get_user(username)
        assert user is not None
        assert user.password_hash != password
        assert len(user.password_hash) > 0

    async def test_login_succeeds_with_correct_password(self, test_db):
        """Login verifies the password hash and returns a JWT."""
        username = _unique_username()
        password = SAFE_PASSWORD

        await container.auth_service.register(username, password)

        result = await container.auth_service.login(username, password)
        assert result.success is True, f"Login failed: {result.error}"
        assert result.token is not None
        assert len(result.token) > 0

    async def test_login_fails_with_wrong_password(self, test_db):
        """Wrong password is rejected (verify_password returns False)."""
        username = _unique_username()

        await container.auth_service.register(username, SAFE_PASSWORD)

        result = await container.auth_service.login(username, "wrong_password_xyz")
        assert result.success is False

    async def test_login_fails_for_nonexistent_user(self, test_db):
        """Login for a user that was never registered must fail."""
        result = await container.auth_service.login(
            "nonexistent_user_12345", "x"
        )
        assert result.success is False

    async def test_register_rejects_short_password(self, test_db):
        """The auth service rejects passwords shorter than 6 chars."""
        result = await container.auth_service.register(
            _unique_username(), "abc"
        )
        assert result.success is False
        assert "Password" in result.error

    async def test_register_rejects_short_username(self, test_db):
        """The auth service rejects usernames shorter than 3 chars."""
        result = await container.auth_service.register("ab", SAFE_PASSWORD)
        assert result.success is False
        assert "Username" in result.error

    async def test_register_duplicate_username(self, test_db):
        """Registering the same username twice is rejected."""
        username = _unique_username()

        r1 = await container.auth_service.register(username, SAFE_PASSWORD)
        assert r1.success is True

        r2 = await container.auth_service.register(username, "another_password123")
        assert r2.success is False

    async def test_full_register_login_token_validation_flow(self, test_db):
        """Full flow: register → login → validate the returned JWT."""
        username = _unique_username()
        password = SAFE_PASSWORD

        # 1. Register
        reg = await container.auth_service.register(username, password)
        assert reg.success is True, f"Register failed: {reg.error}"

        # 2. Login
        login = await container.auth_service.login(username, password)
        assert login.success is True
        token = login.token
        assert token is not None

        # 3. Validate the token
        validated_user = await container.auth_service.validate_token(token)
        assert validated_user == username

    async def test_invalid_token_rejected_by_validate(self, test_db):
        """A garbage JWT token is rejected by token validation."""
        result = await container.auth_service.validate_token(
            "not.a.real.jwt.token"
        )
        assert result is None

    async def test_multiple_register_login_cycles(self, test_db):
        """Multiple register-login cycles with different users work correctly."""
        for i in range(3):
            username = _unique_username()
            password = f"multi_password_{i}_xyz"

            reg = await container.auth_service.register(username, password)
            assert reg.success is True

            login = await container.auth_service.login(username, password)
            assert login.success is True
            assert login.token is not None

    async def test_wrong_password_after_register(self, test_db):
        """Verify that a slightly wrong password is always rejected."""
        username = _unique_username()
        password = "MySecurePassword!2026"

        await container.auth_service.register(username, password)

        # Try similar passwords — all should fail
        wrong_passwords = [
            "MySecurePassword!2027",
            "mysecurepassword!2026",
            "MySecurePassword!2026 ",
            " MySecurePassword!2026",
            "MySecurePassword2026!",
        ]
        for wp in wrong_passwords:
            result = await container.auth_service.login(username, wp)
            assert result.success is False, f"Unexpected success for '{wp}'"


class TestAuthFlowTokenFixture:
    """Tests using the pre-authenticated ``auth_token`` fixture.

    The ``auth_token`` fixture registers a user and obtains a real JWT
    through the auth service, proving the full crypto integration.
    """

    async def test_auth_token_is_valid_jwt(self, test_db, auth_token):
        """The auth_token fixture returns a non-empty JWT string."""
        assert isinstance(auth_token, str)
        assert len(auth_token) > 0
        assert auth_token.count(".") == 2  # JWT has three dot-separated parts

    async def test_auth_token_can_be_validated(self, test_db, auth_token):
        """The token from the fixture can be validated."""
        result = await container.auth_service.validate_token(auth_token)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
