"""
Configuration module for AloneChat application.
Stores all application settings and sensitive information.
"""

import os
from typing import Dict, Any


class Config:
    """Application configuration class."""

    # JWT Configuration
    JWT_SECRET = os.environ.get("JWT_SECRET", "default-secret-key-change-in-production")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = 30

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
    # Native protocol (commonly used by clickhouse-driver)
    CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "127.0.0.1")
    CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", 9000))
    CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
    CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
    CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "alonechat")
    CLICKHOUSE_ENABLED = os.environ.get("CLICKHOUSE_ENABLED", "false").lower() == "true"

    # ClickHouse HTTP interface (commonly used by REST/HTTP clients)
    # NOTE: ClickHouse native client port is usually 9000, HTTP is usually 8123.
    CLICKHOUSE_HTTP_HOST = os.environ.get("CLICKHOUSE_HTTP_HOST", "127.0.0.1")
    CLICKHOUSE_HTTP_PORT = int(os.environ.get("CLICKHOUSE_HTTP_PORT", 8123))

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
            "CLICKHOUSE_HTTP_HOST": cls.CLICKHOUSE_HTTP_HOST,
            "CLICKHOUSE_HTTP_PORT": cls.CLICKHOUSE_HTTP_PORT,
        }


# Create config instance
config = Config()
