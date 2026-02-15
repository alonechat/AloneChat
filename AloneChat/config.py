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

    # User Database
    USER_DB_FILE = "user_credentials.json"

    # SQLite database (friendship graph, conversations, message history)
    SQLITE_DB_FILE = os.environ.get("ALONECHAT_DB", "alonechat.db")

    # Default Server Address
    DEFAULT_SERVER_ADDRESS = "ws://localhost:8765"

    # Default API Address (for internal API communication)
    DEFAULT_API_ADDRESS = 8766

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
            "SQLITE_DB_FILE": cls.SQLITE_DB_FILE
        }


# Create config instance
config = Config()
