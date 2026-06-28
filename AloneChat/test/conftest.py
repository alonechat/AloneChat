"""
Test configuration and fixtures for AloneChat server tests.

Provides:
- TestConfig, PerformanceMetrics, TestDataGenerator utilities
- FastAPI TestClient (httpx.AsyncClient with ASGI transport)
- Test database fixture (override DI container with test ClickHouse or in-memory)
- Auth token fixture (register test user + obtain JWT)
- pytest-asyncio mode=auto config
"""

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, Generator, Optional

import jwt
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from AloneChat.api.app import app
from AloneChat.config import config as app_config
from AloneChat.di import container


# ═══════════════════════════════════════════════════════════════════════════
# Test Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class TestConfig:
    """Configuration for server tests."""
    host: str = "localhost"
    port: int = 18765
    api_port: int = 18766
    timeout: float = 10.0
    max_connections: int = 10
    test_user_prefix: str = "test_user_"
    log_level: str = "DEBUG"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def api_url(self) -> str:
        return f"http://{self.host}:{self.api_port}"


@dataclass
class PerformanceMetrics:
    """Collect and track performance metrics during tests."""
    response_times: list = field(default_factory=list)
    error_count: int = 0
    success_count: int = 0
    connection_times: list = field(default_factory=list)
    message_counts: Dict[str, int] = field(default_factory=dict)

    def record_response_time(self, duration: float) -> None:
        self.response_times.append(duration)

    def record_error(self) -> None:
        self.error_count += 1

    def record_success(self) -> None:
        self.success_count += 1

    def record_connection_time(self, duration: float) -> None:
        self.connection_times.append(duration)

    def record_message(self, message_type: str) -> None:
        self.message_counts[message_type] = self.message_counts.get(message_type, 0) + 1

    @property
    def total_requests(self) -> int:
        return self.success_count + self.error_count

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.error_count / self.total_requests

    @property
    def avg_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    @property
    def min_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return min(self.response_times)

    @property
    def max_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return max(self.response_times)

    @property
    def p95_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * 0.95)
        return sorted_times[min(index, len(sorted_times) - 1)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "error_rate": self.error_rate,
            "avg_response_time_ms": self.avg_response_time * 1000,
            "min_response_time_ms": self.min_response_time * 1000,
            "max_response_time_ms": self.max_response_time * 1000,
            "p95_response_time_ms": self.p95_response_time * 1000,
            "avg_connection_time_ms": (
                sum(self.connection_times) / len(self.connection_times) * 1000
                if self.connection_times else 0
            ),
            "message_counts": self.message_counts,
        }


class TestDataGenerator:
    """Generate test data for server tests."""

    @staticmethod
    def get_jwt_secret() -> str:
        """Get the JWT secret from config."""
        return app_config.JWT_SECRET

    @staticmethod
    def generate_user_credentials(count: int = 5) -> Dict[str, Dict[str, Any]]:
        """Generate test user credentials."""
        users = {}
        for i in range(count):
            username = f"test_user_{i}"
            users[username] = {
                "password": f"password_{i}",
                "is_online": False,
                "created_at": time.time(),
            }
        return users

    @staticmethod
    def generate_messages(count: int = 10) -> list:
        """Generate test messages."""
        messages = []
        for i in range(count):
            messages.append({
                "type": "TEXT",
                "sender": f"test_user_{i % 5}",
                "content": f"Test message {i}",
                "target": None,
                "timestamp": time.time(),
            })
        return messages

    @staticmethod
    def generate_jwt_token(username: str, secret: str = None) -> str:
        """Generate a test JWT token using the config secret."""
        if secret is None:
            secret = app_config.JWT_SECRET

        payload = {
            "sub": username,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        return jwt.encode(payload, secret, algorithm="HS256")


# ═══════════════════════════════════════════════════════════════════════════
# pytest Configuration
# ═══════════════════════════════════════════════════════════════════════════


def pytest_configure(config):
    """Configure pytest with custom markers and asyncio mode=auto.

    pytest-asyncio >= 0.23: auto-detect async test functions so that
    ``@pytest.mark.asyncio`` is never required on async tests.
    """
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    # Enable pytest-asyncio auto mode so async test functions are
    # automatically treated as asyncio coroutines.
    config.option.asyncio_mode = "auto"


# ═══════════════════════════════════════════════════════════════════════════
# Session-scoped Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def test_config() -> TestConfig:
    """Provide test configuration."""
    return TestConfig()


@pytest.fixture(scope="session")
def test_data_generator() -> TestDataGenerator:
    """Provide test data generator."""
    return TestDataGenerator()


@pytest.fixture(scope="session")
def temp_user_db() -> Generator[str, None, None]:
    """Create a temporary user database file for testing."""
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False
    ) as f:
        test_users = TestDataGenerator.generate_user_credentials(10)
        json.dump(test_users, f)
        temp_path = f.name

    yield temp_path

    try:
        os.unlink(temp_path)
    except OSError:
        pass


@pytest.fixture(scope="session")
def temp_log_dir() -> Generator[str, None, None]:
    """Create a temporary log directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="alonechat_test_logs_")
    yield temp_dir
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Function-scoped Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="function")
def performance_metrics() -> PerformanceMetrics:
    """Provide performance metrics collector (fresh for each test)."""
    return PerformanceMetrics()


@pytest.fixture(scope="function")
def test_db():
    """Override the DI container database for testing.

    Resets the container and sets environment variables so that ClickHouse
    connections target a test-specific database.  After the test the original
    state is restored.

    When ClickHouse is unavailable (CLICKHOUSE_ENABLED=false), the container
    services fall back to in-memory storage automatically through the
    repository layer.
    """
    # Remember original env values
    _orig_db = os.environ.get("CLICKHOUSE_DATABASE")
    _orig_enabled = os.environ.get("CLICKHOUSE_ENABLED")

    # Point to a test-specific database so production data is never touched
    os.environ["CLICKHOUSE_DATABASE"] = "alonechat_test"
    os.environ["CLICKHOUSE_ENABLED"] = os.environ.get(
        "CLICKHOUSE_ENABLED", "false"
    )

    # Drop every cached singleton so the new env values take effect
    container.reset()

    yield

    # Restore original environment
    if _orig_db is not None:
        os.environ["CLICKHOUSE_DATABASE"] = _orig_db
    else:
        os.environ.pop("CLICKHOUSE_DATABASE", None)

    if _orig_enabled is not None:
        os.environ["CLICKHOUSE_ENABLED"] = _orig_enabled
    else:
        os.environ.pop("CLICKHOUSE_ENABLED", None)

    # Reset again so the next test gets a clean slate
    container.reset()


@pytest_asyncio.fixture(scope="function")
async def auth_token(test_db) -> str:
    """Register a test user and return a valid JWT bearer token.

    Calls the auth service directly (bypasses HTTP middleware) so the
    token is obtained through the real ``hash_password`` / ``verify_password``
    crypto integration.
    """
    suffix = str(int(time.time() * 1000))[-6:]
    username = f"test_user_{suffix}"
    password = "test_password_123"

    result = await container.auth_service.register(username, password)
    assert result.success, f"Register failed: {result.error}"

    result = await container.auth_service.login(username, password)
    assert result.success, f"Login failed: {result.error}"
    token = result.token
    assert token is not None

    return token


@pytest_asyncio.fixture(scope="function")
async def test_client(
    test_db, auth_token: str
) -> AsyncGenerator[AsyncClient, None]:
    """Return an httpx.AsyncClient pre-configured with ASGI transport and auth.

    The client talks directly to the FastAPI app through the ASGI transport
    (no network socket).  Every request includes the test user's JWT in the
    ``Authorization`` header.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {auth_token}"},
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def unauthenticated_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """Return an httpx.AsyncClient with ASGI transport but no auth header.

    Useful for testing login, register, and other public endpoints.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client
