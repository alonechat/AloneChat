"""
Test configuration and fixtures for AloneChat server tests.

Provides:
- Server configuration for testing
- Test fixtures for pytest
- Performance metrics collection
- Mock data generation
"""

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, Optional

import pytest
import pytest_asyncio


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
        from AloneChat.config import config
        return config.JWT_SECRET
    
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
        import jwt
        
        if secret is None:
            from AloneChat.config import config
            secret = config.JWT_SECRET
        
        payload = {
            "sub": username,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(scope="session")
def test_config() -> TestConfig:
    """Provide test configuration."""
    return TestConfig()


@pytest.fixture(scope="function")
def performance_metrics() -> PerformanceMetrics:
    """Provide performance metrics collector (fresh for each test)."""
    return PerformanceMetrics()


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


@pytest_asyncio.fixture(scope="function")
async def server_instance(test_config: TestConfig):
    """Create and manage a server instance for testing."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from AloneChat.core.server import UnifiedWebSocketManager
    from AloneChat.core.logging import configure_logging, LogConfig
    
    log_config = LogConfig(
        level="DEBUG",
        log_dir="./logs/test",
        console_output=True,
        file_output=False,
    )
    configure_logging(log_config)
    
    manager = UnifiedWebSocketManager(enable_plugins=False)
    
    server_task = asyncio.create_task(
        manager.start(test_config.host, test_config.port)
    )
    
    await asyncio.sleep(0.5)
    
    yield manager
    
    await manager.stop()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
