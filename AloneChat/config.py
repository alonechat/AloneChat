"""
Configuration module for AloneChat application.
Stores all application settings and sensitive information.
Container-aware CPU detection for Docker deployments.
"""

import multiprocessing as mp
import os
import secrets
import string
from typing import Dict, Any

import logging
logger = logging.getLogger(__name__)

def _generate_strong_secret(length: int = 64) -> str:
    """Generate a cryptographically strong random secret."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _get_env_mode() -> str:
    """Get current environment mode."""
    return os.environ.get('ENV_MODE', 'development').lower()


def _validate_jwt_secret() -> str:
    """Validate and return JWT secret with strong defaults."""
    secret = os.environ.get("JWT_SECRET", "")
    env_mode = _get_env_mode()
    
    if secret and len(secret) >= 32:
        return secret
    
    if env_mode in ('production', 'prod'):
        raise ValueError(
            "JWT_SECRET must be set with at least 32 characters in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    
    generated = _generate_strong_secret()
    logger.warning(f"Using auto-generated JWT_SECRET for {env_mode} mode. This is not secure for production!")
    return generated


def get_container_cpu_count() -> int:
    """Get actual CPU count available in container (cgroup aware)."""
    try:
        with open('/sys/fs/cgroup/cpu.max', 'r') as f:
            content = f.read().strip()
            if content != 'max':
                quota, period = content.split()
                if quota != 'max':
                    return max(1, int(quota) // int(period))
    except (FileNotFoundError, ValueError):
        pass
    
    try:
        with open('/sys/fs/cgroup/cpu/cpu.cfs_quota_us', 'r') as f:
            quota = int(f.read().strip())
        with open('/sys/fs/cgroup/cpu/cpu.cfs_period_us', 'r') as f:
            period = int(f.read().strip())
        if quota > 0 and period > 0:
            return max(1, quota // period)
    except (FileNotFoundError, ValueError):
        pass
    
    try:
        with open('/proc/cpuinfo', 'r') as f:
            return f.read().count('processor')
    except FileNotFoundError:
        pass
    
    return max(1, mp.cpu_count())


_CONTAINER_CPU_COUNT = get_container_cpu_count()


class Config:
    """Application configuration class."""

    # JWT Configuration
    JWT_SECRET = _validate_jwt_secret()
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = 30

    # CORS Configuration
    CORS_ALLOW_ORIGINS = \
        os.environ.get("CORS_ALLOW_ORIGINS", "").split(",") if os.environ.get("CORS_ALLOW_ORIGINS") \
        else ["http://localhost:8123", "http://localhost:8766"]
    CORS_ALLOW_CREDENTIALS = os.environ.get("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

    # Server Configuration
    DEFAULT_HOST = "localhost"
    DEFAULT_SERVER_PORT = 8765
    DEFAULT_API_PORT = 8766

    # User Database (JSON fallback)
    USER_DB_FILE = "user_credentials.json"

    # Default Server Address
    DEFAULT_SERVER_ADDRESS = "ws://localhost:8765"

    # Default API Address (for internal API communication)
    DEFAULT_API_ADDRESS = 8766

    # ClickHouse Configuration
    CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", 9000))
    CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
    CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
    CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "alonechat")
    CLICKHOUSE_ENABLED = os.environ.get("CLICKHOUSE_ENABLED", "false").lower() == "true"

    # Parallel Processing Configuration
    PROCESS_WORKERS = int(os.environ.get("AC_PROCESS_WORKERS", max(1, _CONTAINER_CPU_COUNT - 1)))
    THREAD_WORKERS = int(os.environ.get("AC_THREAD_WORKERS", max(4, _CONTAINER_CPU_COUNT * 4)))
    IO_WORKERS = int(os.environ.get("AC_IO_WORKERS", max(8, _CONTAINER_CPU_COUNT * 2)))
    DB_WORKERS = int(os.environ.get("AC_DB_WORKERS", max(4, _CONTAINER_CPU_COUNT)))
    MAX_TASKS_PER_CHILD = int(os.environ.get("AC_MAX_TASKS_PER_CHILD", 1000))
    TASK_TIMEOUT = float(os.environ.get("AC_TASK_TIMEOUT", 30.0))
    PARALLEL_QUEUE_SIZE = int(os.environ.get("AC_QUEUE_SIZE", 10000))
    
    # Multi-process Server Configuration
    WORKERS = int(os.environ.get("AC_WORKERS", 1))
    WORKER_CLASS = os.environ.get("AC_WORKER_CLASS", "uvicorn.workers.UvicornWorker")
    WORKER_CONNECTIONS = int(os.environ.get("AC_WORKER_CONNECTIONS", 1000))
    KEEPALIVE = int(os.environ.get("AC_KEEPALIVE", 5))
    
    # Database Connection Pool
    DB_POOL_SIZE = int(os.environ.get("AC_DB_POOL_SIZE", max(10, _CONTAINER_CPU_COUNT * 2)))
    DB_POOL_OVERFLOW = int(os.environ.get("AC_DB_POOL_OVERFLOW", 10))
    DB_POOL_TIMEOUT = float(os.environ.get("AC_DB_POOL_TIMEOUT", 30.0))
    
    # Message Queue Configuration
    MESSAGE_QUEUE_SIZE = int(os.environ.get("AC_MESSAGE_QUEUE_SIZE", 10000))
    BROADCAST_CONCURRENCY = int(os.environ.get("AC_BROADCAST_CONCURRENCY", 1024))

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Get all configuration values as a dictionary."""
        return {
            "JWT_SECRET": cls.JWT_SECRET,
            "JWT_ALGORITHM": cls.JWT_ALGORITHM,
            "JWT_EXPIRE_MINUTES": cls.JWT_EXPIRE_MINUTES,
            "DEFAULT_HOST": cls.DEFAULT_HOST,
            "DEFAULT_SERVER_PORT": cls.DEFAULT_SERVER_PORT,
            "DEFAULT_API_PORT": cls.DEFAULT_API_PORT,
            "DEFAULT_SERVER_ADDRESS": cls.DEFAULT_SERVER_ADDRESS,
            "DEFAULT_API_ADDRESS": cls.DEFAULT_API_ADDRESS,
            "USER_DB_FILE": cls.USER_DB_FILE,
            "CLICKHOUSE_HOST": cls.CLICKHOUSE_HOST,
            "CLICKHOUSE_PORT": cls.CLICKHOUSE_PORT,
            "CLICKHOUSE_USER": cls.CLICKHOUSE_USER,
            "CLICKHOUSE_PASSWORD": cls.CLICKHOUSE_PASSWORD,
            "CLICKHOUSE_DATABASE": cls.CLICKHOUSE_DATABASE,
            "CLICKHOUSE_ENABLED": cls.CLICKHOUSE_ENABLED,
            "PROCESS_WORKERS": cls.PROCESS_WORKERS,
            "THREAD_WORKERS": cls.THREAD_WORKERS,
            "IO_WORKERS": cls.IO_WORKERS,
            "DB_WORKERS": cls.DB_WORKERS,
            "MAX_TASKS_PER_CHILD": cls.MAX_TASKS_PER_CHILD,
            "TASK_TIMEOUT": cls.TASK_TIMEOUT,
            "PARALLEL_QUEUE_SIZE": cls.PARALLEL_QUEUE_SIZE,
            "WORKERS": cls.WORKERS,
            "WORKER_CLASS": cls.WORKER_CLASS,
            "WORKER_CONNECTIONS": cls.WORKER_CONNECTIONS,
            "KEEPALIVE": cls.KEEPALIVE,
            "DB_POOL_SIZE": cls.DB_POOL_SIZE,
            "DB_POOL_OVERFLOW": cls.DB_POOL_OVERFLOW,
            "DB_POOL_TIMEOUT": cls.DB_POOL_TIMEOUT,
            "MESSAGE_QUEUE_SIZE": cls.MESSAGE_QUEUE_SIZE,
            "BROADCAST_CONCURRENCY": cls.BROADCAST_CONCURRENCY,
        }


# Create config instance
config = Config()
