"""
Configuration module for AloneChat application.
Stores all application settings and sensitive information.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Sentinel value to detect unset JWT secret
_DEFAULT_JWT_SECRET = "default-secret-key-change-in-production"


class Config:
    """Application configuration class."""

    # JWT Configuration
    JWT_SECRET = os.environ.get("JWT_SECRET", _DEFAULT_JWT_SECRET)
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = 30

    # Server Configuration
    DEFAULT_HOST = "localhost"
    DEFAULT_SERVER_PORT = 8765
    DEFAULT_API_PORT = 8766

    # User Database (JSON fallback)
    USER_DB_FILE = "user_credentials.json"

    # ClickHouse Configuration
    CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", 9000))
    CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
    CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
    CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "alonechat")
    CLICKHOUSE_ENABLED = os.environ.get("CLICKHOUSE_ENABLED", "false").lower() == "true"



# Create config instance
config = Config()
